#!/usr/bin/env python3
"""Build a complete Drive PDF filename index for dashboard source links.

The audit file only stores duplicate/orphan PDFs. Letter PDFs uploaded with registry
metadata (or after the last audit) are missing from that subset. This script writes
``drive_filename_index.json`` with every PDF visible to the service account.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "_system/reference/document-store/drive_audit_latest.json"
REGISTRY_PATH = ROOT / "dashboard/data/document_registry.json"
OUTPUT_PATH = ROOT / "_system/reference/document-store/drive_filename_index.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit_pdf_rows(audit: dict) -> list[dict]:
    rows: list[dict] = []
    for value in audit.values():
        if not isinstance(value, list):
            continue
        for item in value:
            name = item.get("name")
            link = item.get("webViewLink") or item.get("webContentLink")
            if name and link and str(name).lower().endswith(".pdf"):
                rows.append(item)
    return rows


def registry_pdf_rows(registry: dict) -> list[dict]:
    rows: list[dict] = []
    for doc in registry.get("documents") or []:
        link = doc.get("drive_web_view_link") or doc.get("drive_web_content_link")
        path = doc.get("local_pdf_path")
        if not link or not path:
            continue
        rows.append(
            {
                "id": doc.get("drive_file_id"),
                "name": Path(str(path)).name,
                "parents": [doc.get("drive_folder_id")] if doc.get("drive_folder_id") else [],
                "webViewLink": link,
                "source": "registry",
            }
        )
    return rows


def merge_rows(*groups: list[dict]) -> dict[str, dict]:
    by_filename: dict[str, dict] = {}
    for rows in groups:
        for row in rows:
            name = str(row.get("name") or "").strip()
            link = row.get("webViewLink") or row.get("webContentLink")
            if not name or not link:
                continue
            key = name.lower()
            current = by_filename.get(key)
            if current and current.get("source") == "drive_api" and row.get("source") != "drive_api":
                continue
            by_filename[key] = {
                "name": name,
                "webViewLink": str(link),
                "id": row.get("id"),
                "parents": row.get("parents") or [],
                "source": row.get("source") or "merged",
            }
    return by_filename


def fetch_drive_pdf_rows() -> list[dict]:
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return []
    from drive_store_common import CONFIG_PATH as DRIVE_CONFIG_PATH
    from drive_store_common import configured_root_ids, drive_service, list_drive_items

    config = load_json(DRIVE_CONFIG_PATH, {})
    service = drive_service(readonly=True)
    root_ids = configured_root_ids(config)
    rows: list[dict] = []
    for item in list_drive_items(service, root_ids):
        if item.get("mimeType") != "application/pdf":
            continue
        link = item.get("webViewLink") or item.get("webContentLink")
        if not link:
            continue
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "parents": item.get("parents") or [],
                "webViewLink": link,
                "source": "drive_api",
            }
        )
    return rows


def build() -> dict:
    audit = load_json(AUDIT_PATH, {})
    registry = load_json(REGISTRY_PATH, {})
    drive_rows = fetch_drive_pdf_rows()
    by_filename = merge_rows(drive_rows, audit_pdf_rows(audit), registry_pdf_rows(registry))
    return {
        "generated_at": now_iso(),
        "source": "drive_api" if drive_rows else "merged_audit_registry",
        "pdf_count": len(by_filename),
        "by_filename": by_filename,
    }


def main() -> int:
    payload = build()
    write_json(OUTPUT_PATH, payload)
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} "
        f"({payload['pdf_count']} PDFs via {payload['source']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
