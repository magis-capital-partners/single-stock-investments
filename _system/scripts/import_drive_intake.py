#!/usr/bin/env python3
"""Import manually uploaded PDFs from Google Drive intake folders into the repo.

Configured intake root (google_drive_config.json drive_intake.folder_id) should be
Admin/Intake on the Shared Drive. Relative paths from that root:

  VIC/{TICKER}.pdf
  Research/{TICKER}.pdf
  Company/{TICKER}.pdf

Also accepted (absolute-style paths if the scan root is higher up):
  Admin/Intake/VIC/{TICKER}.pdf
  Admin/VIC/{TICKER}.pdf

Use --ensure-folders to create VIC/Research/Company/Activist drop folders
under the configured intake root before scanning.

Canonical repo destinations:
  {TICKER}/third-party-analyses/vic/*.pdf
  {TICKER}/third-party-analyses/drive-intake/*.pdf
  {TICKER}/investor-documents/drive-intake/*.pdf
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
MANIFEST_PATH = ROOT / "_system" / "data" / "drive_intake_manifest.json"
REPORT_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_intake_latest.json"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
PDF_MIME = "application/pdf"
INTAKE_PREFIX = "Admin"
LEGACY_INTAKE_PREFIX = "Admin/Intake"
INTAKE_TYPES = {
    "vic": "VIC",
    "research": "Research",
    "company": "Company",
    "activist_long": "Activist/Long",
    "activist_short": "Activist/Short",
}
# Paths relative to drive_intake.folder_id (Admin/Intake). Do not prepend Admin/
# here or --ensure-folders nests Admin/VIC inside Intake/VIC.
INTAKE_FOLDER_PATHS = {
    intake_kind: folder_name
    for intake_kind, folder_name in INTAKE_TYPES.items()
}
ACCEPTED_INTAKE_PREFIXES = (INTAKE_PREFIX, LEGACY_INTAKE_PREFIX, "")
# Misfiled intake PDFs (e.g. bare VIC numeric ids) are reported but must not block CI.
NON_FATAL_ERRORS = frozenset({"missing_or_unknown_ticker"})

sys.path.insert(0, str(SCRIPTS))
from drive_store_common import (  # noqa: E402
    CONFIG_PATH,
    drive_service,
    ensure_folder_path,
    folder_id_by_parent_name,
    item_paths,
    list_drive_items,
    load_json,
    now_iso,
    web_folder_url,
    write_json,
)
from third_party_inventory import write_inventory  # noqa: E402

try:
    from activist_common import load_ticker_index, save_ticker_index, upsert_report  # noqa: E402
    from extract_activist_text import extract_ticker_activist_text  # noqa: E402
except ImportError:
    load_ticker_index = save_ticker_index = upsert_report = None  # type: ignore
    extract_ticker_activist_text = None  # type: ignore


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(value: str, fallback: str = "document.pdf") -> str:
    name = Path(value or fallback).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", name).strip(" .-")
    if not name.lower().endswith(".pdf"):
        name = f"{name or Path(fallback).stem}.pdf"
    return name[:140] or fallback


def normalize_ticker(value: str) -> str | None:
    ticker = str(value or "").strip().upper()
    return ticker if TICKER_RE.match(ticker) and (ROOT / ticker).is_dir() else None


def infer_ticker_from_name(name: str) -> str | None:
    stem = Path(name).stem.upper()
    for token in re.split(r"[\s_\-]+", stem):
        ticker = normalize_ticker(token)
        if ticker:
            return ticker
    return None


def intake_path_parts(path: str) -> tuple[str, list[str], str] | None:
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 4 and parts[0] == "Admin" and parts[1].lower() == "activist":
        side = parts[2].lower()
        if side in ("long", "short"):
            return f"activist_{side}", parts[3:], INTAKE_PREFIX
    if len(parts) >= 3 and parts[0] == "Admin" and parts[1].lower() in INTAKE_TYPES:
        return parts[1].lower(), parts[2:], INTAKE_PREFIX
    if len(parts) >= 4 and parts[0:2] == ["Admin", "Intake"] and parts[2].lower() in INTAKE_TYPES:
        return parts[2].lower(), parts[3:], LEGACY_INTAKE_PREFIX
    if len(parts) >= 3 and parts[0].lower() == "activist" and parts[1].lower() in ("long", "short"):
        return f"activist_{parts[1].lower()}", parts[2:], "root-relative"
    if len(parts) >= 2 and parts[0].lower() in INTAKE_TYPES:
        return parts[0].lower(), parts[1:], "root-relative"
    return None


def parse_intake_path(path: str) -> dict | None:
    parsed_parts = intake_path_parts(path)
    if not parsed_parts:
        return None
    intake_kind, rest, intake_prefix = parsed_parts
    filename = rest[-1]
    if not filename.lower().endswith(".pdf"):
        return None
    ticker = normalize_ticker(rest[0]) if len(rest) >= 2 else None
    if not ticker:
        ticker = infer_ticker_from_name(filename)
    if not ticker:
        return {
            "error": "missing_or_unknown_ticker",
            "intake_kind": intake_kind,
            "intake_prefix": intake_prefix,
            "path": path,
            "filename": filename,
        }
    return {
        "intake_kind": intake_kind,
        "intake_prefix": intake_prefix,
        "ticker": ticker,
        "filename": filename,
        "path": path,
    }


def destination_for(ticker: str, intake_kind: str, filename: str, *, drive_file_id: str) -> Path:
    safe_name = safe_filename(filename)
    if intake_kind == "vic":
        dest_dir = ROOT / ticker / "third-party-analyses" / "vic"
    elif intake_kind == "activist_long":
        dest_dir = ROOT / ticker / "third-party-analyses" / "activist_reports" / "long"
    elif intake_kind == "activist_short":
        dest_dir = ROOT / ticker / "third-party-analyses" / "activist_reports" / "short"
    elif intake_kind == "company":
        dest_dir = ROOT / ticker / "investor-documents" / "drive-intake"
    else:
        dest_dir = ROOT / ticker / "third-party-analyses" / "drive-intake"
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / safe_name
    if not candidate.exists():
        return candidate
    return dest_dir / f"{Path(safe_name).stem}-{drive_file_id[:8]}.pdf"


def download_pdf(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    data = buffer.getvalue()
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"Drive file {file_id} did not download as a PDF.")
    return data


def load_manifest() -> dict:
    manifest = load_json(MANIFEST_PATH)
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("files", {})
    return manifest


def is_dry_run_folder_id(folder_id: str) -> bool:
    return str(folder_id).startswith("dry-run:")


def ensure_intake_folders(service, root_ids: list[str], items: list[dict], dry_run: bool) -> list[dict]:
    existing = folder_id_by_parent_name(items)
    ensured: list[dict] = []
    for root_id in root_ids:
        for intake_kind, folder_path in INTAKE_FOLDER_PATHS.items():
            folder_id = ensure_folder_path(service, root_id, folder_path, dry_run, existing)
            ensured.append(
                {
                    "intake_kind": intake_kind,
                    "path": folder_path,
                    "drive_folder_id": folder_id,
                    "drive_folder_url": None if is_dry_run_folder_id(folder_id) else web_folder_url(folder_id),
                }
            )
    return ensured


def configured_intake_root_ids(config: dict) -> list[str]:
    root_ids: list[str] = []
    intake = config.get("drive_intake") or {}
    if intake.get("folder_id"):
        root_ids.append(intake["folder_id"])
    for root in (config.get("drive_intake_roots") or {}).values():
        if root.get("folder_id"):
            root_ids.append(root["folder_id"])
    if not root_ids:
        root_ids = [
            root.get("folder_id")
            for root in (config.get("drive_roots") or {}).values()
            if root.get("folder_id")
        ]
    return sorted(set(root_ids))


def write_sidecar(dest: Path, item: dict, parsed: dict, digest: str) -> None:
    sidecar = dest.with_suffix(".source.json")
    payload = {
        "imported_at": now_iso(),
        "source": "google_drive_intake",
        "intake_kind": parsed["intake_kind"],
        "ticker": parsed["ticker"],
        "drive_file_id": item.get("id"),
        "drive_name": item.get("name"),
        "drive_path": parsed.get("path"),
        "drive_web_view_link": item.get("webViewLink"),
        "drive_created_time": item.get("createdTime"),
        "drive_modified_time": item.get("modifiedTime"),
        "sha256": digest,
    }
    write_json(sidecar, payload)


def import_intake(
    dry_run: bool,
    limit: int,
    force: bool,
    include_kinds: set[str],
    ensure_folders: bool,
) -> dict:
    config = load_json(CONFIG_PATH)
    root_ids = configured_intake_root_ids(config)
    if not root_ids:
        raise SystemExit(f"No drive roots configured in {CONFIG_PATH}")
    service = drive_service(readonly=not ensure_folders or dry_run)
    items = list_drive_items(service, root_ids)
    ensured_folders: list[dict] = []
    if ensure_folders:
        ensured_folders = ensure_intake_folders(service, root_ids, items, dry_run)
        if not dry_run:
            items = list_drive_items(service, root_ids)
    paths, _children = item_paths(items, root_ids)
    manifest = load_manifest()
    imported: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    warnings: list[dict] = []
    touched_tickers: set[str] = set()

    for item in sorted(items, key=lambda i: paths.get(i.get("id", ""), "")):
        if item.get("mimeType") != PDF_MIME:
            continue
        file_id = item["id"]
        parsed = parse_intake_path(paths.get(file_id, ""))
        if not parsed:
            continue
        if parsed.get("error"):
            entry = {"drive_file_id": file_id, **parsed}
            if parsed["error"] in NON_FATAL_ERRORS:
                warnings.append(entry)
            else:
                errors.append(entry)
            continue
        if parsed["intake_kind"] not in include_kinds:
            continue
        prior = manifest["files"].get(file_id)
        if prior and not force and (ROOT / prior.get("local_pdf_path", "")).exists():
            skipped.append({"drive_file_id": file_id, "reason": "already_imported", **parsed})
            continue
        if limit and len(imported) >= limit:
            skipped.append({"drive_file_id": file_id, "reason": "limit_reached", **parsed})
            continue
        dest = destination_for(parsed["ticker"], parsed["intake_kind"], parsed["filename"], drive_file_id=file_id)
        if dry_run:
            imported.append({"drive_file_id": file_id, "dry_run": True, "target": rel(dest), **parsed})
            continue
        data = download_pdf(service, file_id)
        digest = sha256_bytes(data)
        if dest.exists() and sha256_bytes(dest.read_bytes()) == digest:
            status = "already_present"
        else:
            dest.write_bytes(data)
            status = "imported"
        write_sidecar(dest, item, parsed, digest)
        manifest["files"][file_id] = {
            "imported_at": now_iso(),
            "status": status,
            "intake_kind": parsed["intake_kind"],
            "ticker": parsed["ticker"],
            "drive_file_id": file_id,
            "drive_name": item.get("name"),
            "drive_path": parsed.get("path"),
            "drive_web_view_link": item.get("webViewLink"),
            "local_pdf_path": rel(dest),
            "sha256": digest,
            "size_bytes": len(data),
        }
        imported.append({**manifest["files"][file_id], "target": rel(dest)})
        touched_tickers.add(parsed["ticker"])
        if parsed["intake_kind"] in ("activist_long", "activist_short") and upsert_report:
            side = "long" if parsed["intake_kind"] == "activist_long" else "short"
            index = load_ticker_index(parsed["ticker"])
            upsert_report(
                index,
                {
                    "firm_id": "drive_intake",
                    "firm_name": "Drive intake",
                    "side": side,
                    "report_date": (item.get("createdTime") or now_iso())[:10],
                    "title": parsed["filename"],
                    "source": "google_drive_intake",
                    "source_url": item.get("webViewLink"),
                    "local_pdf": rel(dest),
                    "local_file": rel(dest),
                    "status": "new",
                    "tier": "context",
                    "confidence": 1.0,
                },
            )
            save_ticker_index(parsed["ticker"], index)

    if not dry_run:
        manifest["generated_at"] = now_iso()
        write_json(MANIFEST_PATH, manifest)
        for ticker in sorted(touched_tickers):
            write_inventory(ticker)
            if extract_ticker_activist_text:
                extract_ticker_activist_text(ticker)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "intake_prefix": INTAKE_PREFIX,
        "accepted_intake_prefixes": ACCEPTED_INTAKE_PREFIXES,
        "configured_root_folders": [web_folder_url(root_id) for root_id in root_ids],
        "intake_folder_paths": INTAKE_FOLDER_PATHS,
        "ensured_intake_folders": ensured_folders,
        "summary": {
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "touched_ticker_count": len(touched_tickers),
        },
        "imported": imported,
        "skipped": skipped[:200],
        "warnings": warnings[:200],
        "errors": errors[:200],
    }
    if not dry_run:
        write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Drive intake PDFs into canonical repo folders.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--ensure-folders",
        action="store_true",
        help="Create Admin/{VIC,Research,Company} folders before scanning.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--kind",
        choices=sorted(INTAKE_TYPES),
        action="append",
        help="Restrict to intake kind. May be passed multiple times.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when intake PDFs lack a repo ticker filename.",
    )
    args = parser.parse_args()
    include_kinds = set(args.kind or INTAKE_TYPES)
    report = import_intake(args.dry_run, args.limit, args.force, include_kinds, args.ensure_folders)
    print("Drive intake import")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    if report["warnings"]:
        print(
            "  warnings: rename intake PDFs to repo tickers "
            "(for example FRMI.pdf or FRMI/writeup.pdf); see drive_intake_latest.json"
        )
    if report["errors"]:
        print("  errors: inspect intake paths; expected Admin/{VIC,Research,Company}/{TICKER}.pdf or ticker subfolders")
    if args.strict and report["warnings"]:
        return 2
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
