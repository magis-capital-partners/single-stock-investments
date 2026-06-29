#!/usr/bin/env python3
"""Import manually uploaded PDFs from Google Drive intake folders into the repo.

Intake layout under the configured Shared Drive root:
  Admin/Intake/VIC/{TICKER}/*.pdf
  Admin/Intake/Research/{TICKER}/*.pdf
  Admin/Intake/Company/{TICKER}/*.pdf

Canonical repo destinations:
  {TICKER}/third-party-analyses/vic/*.pdf
  {TICKER}/third-party-analyses/drive-intake/*.pdf
  {TICKER}/investor-documents/drive-intake/*.pdf
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
MANIFEST_PATH = ROOT / "_system" / "data" / "drive_intake_manifest.json"
REPORT_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_intake_latest.json"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
PDF_MIME = "application/pdf"
INTAKE_PREFIX = "Admin/Intake"
INTAKE_TYPES = {
    "vic": "VIC",
    "research": "Research",
    "company": "Company",
}

sys.path.insert(0, str(SCRIPTS))
from drive_store_common import (  # noqa: E402
    CONFIG_PATH,
    drive_service,
    execute_with_retry,
    item_paths,
    list_drive_items,
    load_json,
    now_iso,
    web_folder_url,
    write_json,
)
from third_party_inventory import write_inventory  # noqa: E402


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


def parse_intake_path(path: str) -> dict | None:
    parts = [p for p in path.split("/") if p]
    if len(parts) < 4 or parts[0:2] != ["Admin", "Intake"]:
        return None
    intake_kind = parts[2].lower()
    if intake_kind not in INTAKE_TYPES:
        return None
    filename = parts[-1]
    if not filename.lower().endswith(".pdf"):
        return None
    ticker = normalize_ticker(parts[3]) if len(parts) >= 5 else None
    if not ticker:
        ticker = infer_ticker_from_name(filename)
    if not ticker:
        return {
            "error": "missing_or_unknown_ticker",
            "intake_kind": intake_kind,
            "path": path,
            "filename": filename,
        }
    return {
        "intake_kind": intake_kind,
        "ticker": ticker,
        "filename": filename,
        "path": path,
    }


def destination_for(ticker: str, intake_kind: str, filename: str, *, drive_file_id: str) -> Path:
    safe_name = safe_filename(filename)
    if intake_kind == "vic":
        dest_dir = ROOT / ticker / "third-party-analyses" / "vic"
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


def import_intake(dry_run: bool, limit: int, force: bool, include_kinds: set[str]) -> dict:
    config = load_json(CONFIG_PATH)
    root_ids = [root.get("folder_id") for root in (config.get("drive_roots") or {}).values() if root.get("folder_id")]
    root_ids = sorted(set(root_ids))
    if not root_ids:
        raise SystemExit(f"No drive roots configured in {CONFIG_PATH}")
    service = drive_service(readonly=True)
    items = list_drive_items(service, root_ids)
    paths, _children = item_paths(items, root_ids)
    manifest = load_manifest()
    imported: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    touched_tickers: set[str] = set()

    for item in sorted(items, key=lambda i: paths.get(i.get("id", ""), "")):
        if item.get("mimeType") != PDF_MIME:
            continue
        file_id = item["id"]
        parsed = parse_intake_path(paths.get(file_id, ""))
        if not parsed:
            continue
        if parsed.get("error"):
            errors.append({"drive_file_id": file_id, **parsed})
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

    if not dry_run:
        manifest["generated_at"] = now_iso()
        write_json(MANIFEST_PATH, manifest)
        for ticker in sorted(touched_tickers):
            write_inventory(ticker)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "intake_prefix": INTAKE_PREFIX,
        "configured_root_folders": [web_folder_url(root_id) for root_id in root_ids],
        "summary": {
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "touched_ticker_count": len(touched_tickers),
        },
        "imported": imported,
        "skipped": skipped[:200],
        "errors": errors[:200],
    }
    if not dry_run:
        write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Drive intake PDFs into canonical repo folders.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--kind",
        choices=sorted(INTAKE_TYPES),
        action="append",
        help="Restrict to intake kind. May be passed multiple times.",
    )
    args = parser.parse_args()
    include_kinds = set(args.kind or INTAKE_TYPES)
    report = import_intake(args.dry_run, args.limit, args.force, include_kinds)
    print("Drive intake import")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    if report["errors"]:
        print("  errors: inspect Admin/Intake paths; expected Admin/Intake/{VIC,Research,Company}/{TICKER}/*.pdf")
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
