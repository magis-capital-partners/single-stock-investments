#!/usr/bin/env python3
"""Audit uploaded PDFs in the configured Google Shared Drive."""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
CONFIG_PATH = ROOT / "_system" / "reference" / "document-store" / "google_drive_config.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def drive_service():
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise SystemExit("Set GOOGLE_APPLICATION_CREDENTIALS to the service-account JSON before auditing Drive.")
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def configured_root_ids(config: dict) -> list[str]:
    roots = config.get("drive_roots") or {}
    ids = []
    for root in roots.values():
        root_id = root.get("folder_id")
        if root_id and root_id not in ids:
            ids.append(root_id)
    return ids


def drive_id_for_root(service, root_id: str) -> str:
    meta = service.files().get(fileId=root_id, fields="id,name,driveId", supportsAllDrives=True).execute()
    drive_id = meta.get("driveId")
    if not drive_id:
        raise SystemExit(f"Root {root_id} is not inside a Shared Drive.")
    return drive_id


def list_drive_pdfs(service, drive_id: str) -> list[dict]:
    files: list[dict] = []
    page_token = None
    while True:
        res = service.files().list(
            corpora="drive",
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            q="mimeType = 'application/pdf' and trashed = false",
            fields="nextPageToken,files(id,name,size,webViewLink,appProperties,parents)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()
        files.extend(res.get("files") or [])
        page_token = res.get("nextPageToken")
        if not page_token:
            return files


def build_audit(root_id: str | None = None) -> dict:
    registry = load_json(REGISTRY_PATH)
    config = load_json(CONFIG_PATH)
    service = drive_service()
    root_ids = [root_id] if root_id else configured_root_ids(config)
    registry_docs = registry.get("documents") or []
    registry_file_ids = {doc.get("drive_file_id") for doc in registry_docs if doc.get("drive_file_id")}
    registry_doc_ids = {doc.get("document_id") for doc in registry_docs if doc.get("document_id")}

    files: list[dict] = []
    for configured_root_id in root_ids:
        drive_id = drive_id_for_root(service, configured_root_id)
        files.extend(list_drive_pdfs(service, drive_id))

    by_file_id = {f["id"]: f for f in files}
    by_sha: defaultdict[str, list[dict]] = defaultdict(list)
    no_sha: list[dict] = []
    orphans: list[dict] = []
    for file in by_file_id.values():
        props = file.get("appProperties") or {}
        sha = props.get("sha256")
        document_id = props.get("document_id")
        if sha:
            by_sha[sha].append(file)
        else:
            no_sha.append(file)
        if file.get("id") not in registry_file_ids and document_id not in registry_doc_ids:
            orphans.append(file)

    duplicate_sha = {sha: rows for sha, rows in by_sha.items() if len(rows) > 1}
    return {
        "summary": {
            "drive_pdf_count": len(by_file_id),
            "registry_uploaded_count": len(registry_file_ids),
            "duplicate_sha_count": len(duplicate_sha),
            "missing_sha_app_property_count": len(no_sha),
            "orphan_drive_pdf_count": len(orphans),
        },
        "duplicate_sha": duplicate_sha,
        "missing_sha_app_property": no_sha,
        "orphan_drive_pdfs": orphans,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PDFs in the configured Google Shared Drive")
    parser.add_argument("--root-id", help="Specific Shared Drive root folder ID to audit")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when duplicates or orphans are present")
    args = parser.parse_args()

    audit = build_audit(args.root_id)
    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True))
    else:
        print("Drive PDF store audit")
        for key, value in audit["summary"].items():
            print(f"  {key}: {value}")
        for key in ("duplicate_sha", "missing_sha_app_property", "orphan_drive_pdfs"):
            rows = audit[key]
            if rows:
                print(f"\n{key} (first 20):")
                iterable = rows.items() if isinstance(rows, dict) else enumerate(rows)
                for _key, row in list(iterable)[:20]:
                    print(f"  {_key}: {row}")

    actionable = (
        audit["summary"]["duplicate_sha_count"]
        or audit["summary"]["missing_sha_app_property_count"]
        or audit["summary"]["orphan_drive_pdf_count"]
    )
    return 1 if args.strict and actionable else 0


if __name__ == "__main__":
    raise SystemExit(main())
