#!/usr/bin/env python3
"""Import hedge-fund letter PDFs from Google Drive into the local superinvestor corpus.

Scans the shared PDF store (``hedge_fund_letters`` root) for PDFs under
``Letters/{YYYY Qn}/`` and legacy ``{YYYY Qn}`` / ``{YYYY nQ}`` folders, downloads
them into ``_system/reference/superinvestor-letters/{YYYY}Q{n}/``, and optionally
extracts text and runs the insights build pipeline.

Requires ``GOOGLE_APPLICATION_CREDENTIALS`` pointing at the pdf-store service account.

Usage:
  python _system/scripts/import_drive_letter_orphans.py --dry-run
  python _system/scripts/import_drive_letter_orphans.py --since-year 2020
  python _system/scripts/import_drive_letter_orphans.py --quarter 2025Q4 --build
  python _system/scripts/import_drive_letter_orphans.py --all --build
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
from vault_paths import letters_root  # noqa: E402

LETTERS_ROOT = letters_root()
MANIFEST_PATH = LETTERS_ROOT / "drive_import_manifest.json"
IMPORT_LOG = LETTERS_ROOT / "drive_import_log.jsonl"
FILENAME_INDEX_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_filename_index.json"
PDF_MIME = "application/pdf"

LETTERS_PATH_RE = re.compile(
    r"(?:^|/)Letters/(20\d{2})\s+Q([1-4])(?:/|$)",
    re.I,
)
LEGACY_PATH_RE = re.compile(
    r"(?:^|/)(20\d{2})\s+([1-4])Q(?:/|$)",
    re.I,
)
LEGACY_PATH_RE2 = re.compile(
    r"(?:^|/)(20\d{2})\s+Q([1-4])(?:/|$)",
    re.I,
)
STEM_QUARTER_RE = re.compile(
    r"\b(20\d{2})\s*Q([1-4])\b|\bQ([1-4])\s*['']?(20\d{2})\b|\b([1-4])Q\s*(20\d{2})\b",
    re.I,
)

sys.path.insert(0, str(SCRIPTS))
from drive_store_common import (  # noqa: E402
    CONFIG_PATH,
    FOLDER_INDEX_PATH,
    drive_service,
    item_paths,
    list_drive_items,
    load_json,
    write_json,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_event(event: dict) -> None:
    LETTERS_ROOT.mkdir(parents=True, exist_ok=True)
    event["ts"] = now_iso()
    with IMPORT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def safe_filename(name: str, fallback: str = "letter.pdf") -> str:
    base = Path(name or fallback).name
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", base)
    base = re.sub(r"\s+", " ", base).strip(" .")
    if not base.lower().endswith(".pdf"):
        base = f"{base or Path(fallback).stem}.pdf"
    return base[:180] or fallback


def quarter_from_drive_path(path: str) -> str | None:
    text = str(path or "").replace("\\", "/")
    for pattern in (LETTERS_PATH_RE, LEGACY_PATH_RE, LEGACY_PATH_RE2):
        m = pattern.search(text)
        if m:
            return f"{m.group(1)}Q{m.group(2)}"
    return None


def quarter_matches_filter(quarter_id: str | None, quarter_filter: str | None, since_year: int | None) -> bool:
    if not quarter_id:
        return False
    if quarter_filter and quarter_id.upper() != quarter_filter.upper():
        return False
    if since_year and int(quarter_id[:4]) < since_year:
        return False
    return True


def load_manifest() -> dict:
    data = load_json(MANIFEST_PATH)
    data.setdefault("schema_version", 1)
    data.setdefault("files", {})
    return data


def download_pdf(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload  # noqa: WPS433

    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    data = buffer.getvalue()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"Drive file {file_id} is not a PDF.")
    return data


def unique_dest(dest_dir: Path, name: str, drive_file_id: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / safe_filename(name)
    if not candidate.exists():
        return candidate
    stem = Path(safe_filename(name)).stem
    alt = dest_dir / f"{stem}-{drive_file_id[:8]}.pdf"
    return alt if not alt.exists() else dest_dir / f"{stem}-{drive_file_id}.pdf"


def should_skip_download(local_pdf: Path, drive_size: int | None, manifest_entry: dict | None) -> bool:
    if not local_pdf.exists():
        return False
    if manifest_entry and manifest_entry.get("sha256"):
        try:
            local_sha = hashlib.sha256(local_pdf.read_bytes()).hexdigest()
            if local_sha == manifest_entry["sha256"]:
                return True
        except OSError:
            return False
    if drive_size and local_pdf.stat().st_size == int(drive_size):
        return True
    return False


def extract_texts(pdfs: list[Path], *, max_pages: int = 40, max_files: int | None = None) -> int:
    from pdf_ocr import extract_pdf_text  # noqa: WPS433

    updated = 0
    todo = pdfs[:max_files] if max_files else pdfs
    for i, pdf in enumerate(todo, 1):
        txt = pdf.with_suffix(".txt")
        if txt.exists() and txt.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        if i % 25 == 1 or i == len(todo):
            print(f"  Text extract {i}/{len(todo)}: {pdf.name}", flush=True)
        result = extract_pdf_text(pdf, max_pages=max_pages)
        text = (result.get("text") or "").strip()
        if len(text) < 50:
            result = extract_pdf_text(pdf, max_pages=max_pages, force_ocr=True)
            text = (result.get("text") or "").strip()
        txt.write_text(text + "\n", encoding="utf-8")
        updated += 1
    return updated


def run_build_pipeline() -> None:
    py = sys.executable
    steps = [
        ("drive filename index", SCRIPTS / "build_drive_filename_index.py", []),
        ("superinvestor insights", SCRIPTS / "build_superinvestor_insights.py", []),
        ("letter drive links", SCRIPTS / "build_letter_drive_links.py", []),
        ("insights merge", SCRIPTS / "build_insights.py", []),
        ("document registry", SCRIPTS / "build_document_registry.py", []),
        ("dashboard data", SCRIPTS / "build_dashboard_data.py", []),
    ]
    for label, script, args in steps:
        if not script.exists():
            continue
        print(f"  {label}...", flush=True)
        r = subprocess.run([py, str(script), *args], cwd=str(ROOT))
        if r.returncode != 0:
            raise SystemExit(f"FAIL: {label}")


def folder_id_to_path() -> dict[str, str]:
    payload = load_json(FOLDER_INDEX_PATH)
    out: dict[str, str] = {}
    for path, meta in (payload.get("folders") or {}).items():
        folder_id = (meta or {}).get("id")
        if folder_id:
            out[str(folder_id)] = str(path)
    return out


def parent_folder_path(parent_ids: list[str], id_to_path: dict[str, str]) -> str:
    for parent_id in parent_ids or []:
        path = id_to_path.get(parent_id)
        if path:
            return path
    return ""


def collect_letter_pdfs_from_index(
    *,
    quarter_filter: str | None,
    since_year: int | None,
) -> list[dict]:
    """Use cached drive_filename_index when live API access is unavailable."""
    index = load_json(FILENAME_INDEX_PATH)
    id_to_path = folder_id_to_path()
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for _key, row in (index.get("by_filename") or {}).items():
        file_id = row.get("id")
        if not file_id or file_id in seen_ids:
            continue
        seen_ids.add(file_id)
        parent_path = parent_folder_path(row.get("parents") or [], id_to_path)
        drive_path = "/".join([p for p in [parent_path, row.get("name") or ""] if p])
        quarter = quarter_from_drive_path(drive_path) or quarter_from_drive_path(parent_path)
        if not quarter_matches_filter(quarter, quarter_filter, since_year):
            continue
        rows.append(
            {
                "file_id": file_id,
                "name": row.get("name") or "letter.pdf",
                "drive_path": drive_path,
                "quarter": quarter,
                "size_bytes": 0,
                "webViewLink": row.get("webViewLink"),
                "modifiedTime": None,
            }
        )
    rows.sort(key=lambda r: (r["quarter"] or "", r["name"].lower()))
    return rows


def collect_letter_pdfs(
    service,
    root_ids: list[str],
    *,
    quarter_filter: str | None,
    since_year: int | None,
) -> list[dict]:
    items = list_drive_items(service, root_ids)
    paths, _child_map = item_paths(items, root_ids)
    rows: list[dict] = []
    for item in items:
        if item.get("mimeType") != PDF_MIME:
            continue
        file_id = item["id"]
        full_path = paths.get(file_id) or item.get("name") or ""
        quarter = quarter_from_drive_path(full_path)
        if not quarter_matches_filter(quarter, quarter_filter, since_year):
            continue
        rows.append(
            {
                "file_id": file_id,
                "name": item.get("name") or "letter.pdf",
                "drive_path": full_path,
                "quarter": quarter,
                "size_bytes": int(item.get("size") or 0),
                "webViewLink": item.get("webViewLink"),
                "modifiedTime": item.get("modifiedTime"),
            }
        )
    rows.sort(key=lambda r: (r["quarter"] or "", r["name"].lower()))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import hedge fund letter PDFs from Google Drive")
    parser.add_argument("--all", action="store_true", help="Import all letter quarters found on Drive")
    parser.add_argument("--quarter", help="Single quarter id e.g. 2025Q4")
    parser.add_argument("--since-year", type=int, help="Only import quarters from this year onward")
    parser.add_argument("--from-index", action="store_true", help="Use cached drive_filename_index.json instead of live Drive API listing")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without downloading")
    parser.add_argument("--skip-download", action="store_true", help="Only run text extraction on existing PDFs")
    parser.add_argument("--skip-text", action="store_true", help="Skip PDF -> txt extraction")
    parser.add_argument("--max-files", type=int, help="Limit downloads/extractions (smoke test)")
    parser.add_argument("--build", action="store_true", help="Run insights + dashboard build after import")
    args = parser.parse_args()

    if not args.all and not args.quarter and not args.skip_download:
        parser.error("Provide --all, --quarter 2025Q4, or --skip-download")

    config = load_json(CONFIG_PATH)
    root_ids = [
        (config.get("drive_roots") or {}).get("hedge_fund_letters", {}).get("folder_id"),
    ]
    root_ids = [rid for rid in root_ids if rid]
    if not root_ids:
        raise SystemExit("hedge_fund_letters folder_id missing in google_drive_config.json")

    quarter_filter = args.quarter.upper() if args.quarter else None
    since_year = args.since_year

    print(f"=== import_drive_letter_orphans (roots={len(root_ids)}) ===", flush=True)
    service = None if (args.dry_run and args.from_index) else drive_service(readonly=args.dry_run or args.skip_download)
    manifest = load_manifest()
    manifest_files: dict = manifest["files"]

    if args.skip_download:
        pdfs = sorted(LETTERS_ROOT.glob("*/*.pdf"))
        if quarter_filter:
            pdfs = [p for p in pdfs if p.parent.name.upper() == quarter_filter]
        if since_year:
            pdfs = [p for p in pdfs if int(p.parent.name[:4]) >= since_year]
        if args.max_files:
            pdfs = pdfs[: args.max_files]
        print(f"  Existing local PDFs: {len(pdfs)}")
    else:
        if args.from_index:
            candidates = collect_letter_pdfs_from_index(
                quarter_filter=quarter_filter,
                since_year=since_year,
            )
        else:
            candidates = collect_letter_pdfs(
                service,
                root_ids,
                quarter_filter=quarter_filter,
                since_year=since_year,
            )
        if args.max_files:
            candidates = candidates[: args.max_files]
        print(f"  Drive letter PDFs matched: {len(candidates)}")
        if args.dry_run:
            by_q: dict[str, int] = {}
            for row in candidates:
                by_q[row["quarter"] or "?"] = by_q.get(row["quarter"] or "?", 0) + 1
            for q in sorted(by_q):
                print(f"    {q}: {by_q[q]}")
            return 0

        downloaded: list[Path] = []
        skipped = 0
        errors = 0
        for i, row in enumerate(candidates, 1):
            quarter = row["quarter"]
            dest_dir = LETTERS_ROOT / quarter
            dest = unique_dest(dest_dir, row["name"], row["file_id"])
            entry = manifest_files.get(row["file_id"])
            if should_skip_download(dest, row.get("size_bytes"), entry):
                skipped += 1
                downloaded.append(dest)
                continue
            if i % 25 == 1 or i == len(candidates):
                print(f"  Download {i}/{len(candidates)}: {row['drive_path']}", flush=True)
            try:
                data = download_pdf(service, row["file_id"])
                dest.write_bytes(data)
                sha = hashlib.sha256(data).hexdigest()
                manifest_files[row["file_id"]] = {
                    "drive_file_id": row["file_id"],
                    "drive_path": row["drive_path"],
                    "local_pdf_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
                    "quarter": quarter,
                    "sha256": sha,
                    "size_bytes": len(data),
                    "webViewLink": row.get("webViewLink"),
                    "imported_at": now_iso(),
                }
                downloaded.append(dest)
                log_event({"action": "download", "file_id": row["file_id"], "path": manifest_files[row["file_id"]]["local_pdf_path"]})
            except Exception as exc:
                errors += 1
                print(f"  WARN: failed {row['name']}: {exc}", file=sys.stderr, flush=True)
        manifest["generated_at"] = now_iso()
        manifest["file_count"] = len(manifest_files)
        write_json(MANIFEST_PATH, manifest)
        print(f"  Downloaded/kept {len(downloaded)} PDFs ({skipped} skipped, {errors} errors)")
        pdfs = downloaded

    if not args.skip_text and pdfs:
        updated = extract_texts(pdfs, max_files=args.max_files)
        print(f"  Wrote/updated {updated} text extracts")

    if args.build:
        print("\n=== build pipeline ===", flush=True)
        run_build_pipeline()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
