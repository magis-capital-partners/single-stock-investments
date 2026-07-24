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
from vault_paths import letters_root, path_to_letters_ref  # noqa: E402

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


def shard_bucket(identifier: str, shard_count: int) -> int:
    """Deterministic shard index in ``[0, shard_count)`` from a stable id."""
    if shard_count <= 1:
        return 0
    digest = hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % shard_count


def in_shard(identifier: str, *, shard_index: int, shard_count: int) -> bool:
    if shard_count <= 1:
        return True
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"shard_index {shard_index} out of range for shard_count {shard_count}")
    return shard_bucket(identifier, shard_count) == shard_index


def filter_shard(
    rows: list,
    *,
    shard_index: int,
    shard_count: int,
    key_fn,
) -> list:
    if shard_count <= 1:
        return rows
    return [row for row in rows if in_shard(key_fn(row), shard_index=shard_index, shard_count=shard_count)]


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


def _manifest_local_paths(manifest_entry: dict | None) -> list[Path]:
    """Resolve possible on-disk paths recorded in drive_import_manifest.json."""
    if not manifest_entry:
        return []
    ref = str(manifest_entry.get("local_pdf_path") or "").replace("\\", "/")
    if not ref:
        return []
    paths: list[Path] = []
    raw = Path(ref)
    if raw.is_absolute():
        paths.append(raw)
    else:
        paths.append(ROOT / ref)
        marker = "/superinvestor-letters/"
        if marker in f"/{ref}":
            suffix = ref.split("superinvestor-letters/", 1)[1]
            paths.append(LETTERS_ROOT / suffix)
    return paths


def unique_dest(dest_dir: Path, name: str, drive_file_id: str) -> Path:
    """Return a writable path for a new download (collision-safe).

    Prefer :func:`resolve_local_pdf` for import loops — this helper only
    allocates a path and intentionally avoids the existing-file skip path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / safe_filename(name)
    if not candidate.exists():
        return candidate
    stem = Path(safe_filename(name)).stem
    alt = dest_dir / f"{stem}-{drive_file_id[:8]}.pdf"
    return alt if not alt.exists() else dest_dir / f"{stem}-{drive_file_id}.pdf"


def text_extract_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".txt")


def nontrivial_text_extract(path: Path, *, min_chars: int = 50) -> bool:
    """True when a committed letter extract already exists (PDFs are gitignored)."""
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return False
    return len(text) >= min_chars


def should_skip_download(local_pdf: Path, drive_size: int | None, manifest_entry: dict | None) -> bool:
    # Vault commits .txt extracts only; treat a good extract as "already ingested".
    if nontrivial_text_extract(text_extract_path(local_pdf)):
        return True
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


def resolve_local_pdf(
    dest_dir: Path,
    name: str,
    drive_file_id: str,
    *,
    drive_size: int | None,
    manifest_entry: dict | None,
) -> tuple[Path, bool]:
    """Return ``(path, skip_download)`` for a Drive letter PDF.

    Reuse an existing local file for this Drive id when content matches
    (manifest sha256 or byte size), or when a nontrivial ``.txt`` extract
    already exists in the vault (PDFs are gitignored and not restored on
    CI checkout). Only mint a file-id-suffixed name when the basename is
    already occupied by a *different* file.

    Prior bug: ``unique_dest`` returned a fresh suffix path whenever the
    basename existed, so ``should_skip_download`` never saw the existing PDF
    and weekly backfill re-downloaded the entire ~20k corpus (then timed out
    mid text-extract).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = safe_filename(name)
    stem = Path(safe).stem
    candidate = dest_dir / safe
    alt_short = dest_dir / f"{stem}-{drive_file_id[:8]}.pdf"
    alt_full = dest_dir / f"{stem}-{drive_file_id}.pdf"

    for existing in (*_manifest_local_paths(manifest_entry), candidate, alt_short, alt_full):
        if should_skip_download(existing, drive_size, manifest_entry):
            return existing, True

    if not candidate.exists() and not nontrivial_text_extract(text_extract_path(candidate)):
        return candidate, False
    if not alt_short.exists() and not nontrivial_text_extract(text_extract_path(alt_short)):
        return alt_short, False
    return alt_full, False


def extract_texts(pdfs: list[Path], *, max_pages: int = 40, max_files: int | None = None) -> int:
    updated = 0
    skipped = 0
    extract_pdf_text = None
    todo = pdfs[:max_files] if max_files else pdfs
    for i, pdf in enumerate(todo, 1):
        txt = pdf.with_suffix(".txt")
        if txt.exists():
            try:
                existing = txt.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                existing = ""
            # Skip when extract is fresh vs PDF, or when a non-trivial extract
            # already exists (guards against checkout/download mtime churn
            # forcing a full-corpus OCR pass inside the 5h job budget).
            if existing and (
                txt.stat().st_mtime >= pdf.stat().st_mtime or len(existing) >= 50
            ):
                skipped += 1
                continue
        if extract_pdf_text is None:
            from pdf_ocr import extract_pdf_text as _extract_pdf_text  # noqa: WPS433

            extract_pdf_text = _extract_pdf_text
        if i % 25 == 1 or i == len(todo):
            print(f"  Text extract {i}/{len(todo)}: {pdf.name}", flush=True)
        result = extract_pdf_text(pdf, max_pages=max_pages)
        text = (result.get("text") or "").strip()
        if len(text) < 50:
            result = extract_pdf_text(pdf, max_pages=max_pages, force_ocr=True)
            text = (result.get("text") or "").strip()
        txt.write_text(text + "\n", encoding="utf-8")
        updated += 1
    if skipped:
        print(f"  Text extract skipped {skipped} existing extracts", flush=True)
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
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        help="Zero-based shard to process (with --shard-count). Deterministic by file id / path.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=1,
        help="Split work into N deterministic shards so each CI job stays under timeout.",
    )
    parser.add_argument("--build", action="store_true", help="Run insights + dashboard build after import")
    parser.add_argument("--report", action="store_true", help="Write letter_drive_gaps report without importing")
    args = parser.parse_args()

    if args.shard_count < 1:
        parser.error("--shard-count must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        parser.error(f"--shard-index must be in [0, {args.shard_count})")

    if args.report:
        from datetime import date as date_cls

        report_date = date_cls.today().isoformat()
        out = ROOT / "_system" / "research" / f"letter_drive_gaps_{report_date}.md"
        links_path = ROOT / "_system" / "reference" / "document-store" / "letter_drive_links.json"
        insights_path = ROOT / "dashboard" / "data" / "insights.json"
        letter_count = 0
        matched = 0
        if insights_path.exists():
            letter_count = len(json.loads(insights_path.read_text(encoding="utf-8")).get("letter_index") or [])
        if links_path.exists():
            matched = int(json.loads(links_path.read_text(encoding="utf-8")).get("matched_count") or 0)
        lines = [
            "# Letter Drive link gaps",
            "",
            f"**Date:** {report_date}",
            f"**Letter index rows:** {letter_count}",
            f"**Drive links matched:** {matched}",
            "",
        ]
        if letter_count and matched < letter_count:
            lines.append(f"Unmatched estimate: {letter_count - matched}")
        else:
            lines.append("No gaps detected in summary counts.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {out.relative_to(ROOT)}")
        return 0

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

    print(
        f"=== import_drive_letter_orphans (roots={len(root_ids)}, "
        f"shard={args.shard_index}/{args.shard_count}) ===",
        flush=True,
    )
    service = None if args.skip_download or (args.dry_run and args.from_index) else drive_service(readonly=args.dry_run)
    manifest = load_manifest()
    manifest_files: dict = manifest["files"]

    if args.skip_download:
        pdfs = sorted(LETTERS_ROOT.glob("*/*.pdf"))
        if quarter_filter:
            pdfs = [p for p in pdfs if p.parent.name.upper() == quarter_filter]
        if since_year:
            pdfs = [p for p in pdfs if int(p.parent.name[:4]) >= since_year]
        before_shard = len(pdfs)
        pdfs = filter_shard(
            pdfs,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            key_fn=lambda p: f"{p.parent.name}/{p.name}".replace("\\", "/"),
        )
        if args.max_files:
            pdfs = pdfs[: args.max_files]
        print(
            f"  Existing local PDFs: {len(pdfs)} "
            f"(from {before_shard} after shard {args.shard_index}/{args.shard_count})"
        )
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
        before_shard = len(candidates)
        candidates = filter_shard(
            candidates,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            key_fn=lambda row: row.get("file_id") or row.get("drive_path") or row.get("name") or "",
        )
        if args.max_files:
            candidates = candidates[: args.max_files]
        print(
            f"  Drive letter PDFs matched: {len(candidates)} "
            f"(from {before_shard} after shard {args.shard_index}/{args.shard_count})"
        )
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
        new_downloads = 0
        for i, row in enumerate(candidates, 1):
            quarter = row["quarter"]
            dest_dir = LETTERS_ROOT / quarter
            entry = manifest_files.get(row["file_id"])
            dest, skip = resolve_local_pdf(
                dest_dir,
                row["name"],
                row["file_id"],
                drive_size=row.get("size_bytes"),
                manifest_entry=entry,
            )
            if skip:
                skipped += 1
                downloaded.append(dest)
                # Refresh manifest path if we resolved via size/text match without an entry.
                if row["file_id"] not in manifest_files:
                    txt_only = nontrivial_text_extract(text_extract_path(dest)) and not dest.exists()
                    size_bytes = int(row.get("size_bytes") or 0)
                    if dest.exists():
                        size_bytes = int(dest.stat().st_size)
                    manifest_files[row["file_id"]] = {
                        "drive_file_id": row["file_id"],
                        "drive_path": row["drive_path"],
                        "local_pdf_path": path_to_letters_ref(dest) or str(dest).replace("\\", "/"),
                        "quarter": quarter,
                        "size_bytes": size_bytes,
                        "webViewLink": row.get("webViewLink"),
                        "imported_at": now_iso(),
                        "skipped_existing": True,
                        "skipped_existing_text": txt_only,
                    }
                continue
            if new_downloads % 25 == 0 or i == len(candidates):
                print(
                    f"  Download {i}/{len(candidates)} "
                    f"(new {new_downloads}, skipped {skipped}): {row['drive_path']}",
                    flush=True,
                )
            try:
                data = download_pdf(service, row["file_id"])
                dest.write_bytes(data)
                sha = hashlib.sha256(data).hexdigest()
                manifest_files[row["file_id"]] = {
                    "drive_file_id": row["file_id"],
                    "drive_path": row["drive_path"],
                    "local_pdf_path": path_to_letters_ref(dest) or str(dest).replace("\\", "/"),
                    "quarter": quarter,
                    "sha256": sha,
                    "size_bytes": len(data),
                    "webViewLink": row.get("webViewLink"),
                    "imported_at": now_iso(),
                }
                downloaded.append(dest)
                new_downloads += 1
                log_event({"action": "download", "file_id": row["file_id"], "path": manifest_files[row["file_id"]]["local_pdf_path"]})
            except Exception as exc:
                errors += 1
                print(f"  WARN: failed {row['name']}: {exc}", file=sys.stderr, flush=True)
        manifest["generated_at"] = now_iso()
        manifest["file_count"] = len(manifest_files)
        write_json(MANIFEST_PATH, manifest)
        print(
            f"  Downloaded/kept {len(downloaded)} PDFs "
            f"({new_downloads} new, {skipped} skipped, {errors} errors)"
        )
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
