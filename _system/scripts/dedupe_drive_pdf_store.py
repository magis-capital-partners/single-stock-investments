#!/usr/bin/env python3
"""Remove duplicate PDFs from the configured Google Shared Drive."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "dashboard" / "data" / "document_registry.json"
CONFIG_PATH = ROOT / "_system" / "reference" / "document-store" / "google_drive_config.json"
AUDIT_PATH = ROOT / "_system" / "reference" / "document-store" / "drive_dedupe_report.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]
_THREAD_LOCAL = threading.local()


def execute_with_retry(request, attempts: int = 6):
    delay = 2.0
    for attempt in range(attempts):
        try:
            return request.execute()
        except HttpError as exc:
            if exc.resp.status not in {403, 429, 500, 503} or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60.0)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def drive_service():
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise SystemExit("Set GOOGLE_APPLICATION_CREDENTIALS to the service-account JSON before deduping Drive.")
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def thread_drive_service():
    service = getattr(_THREAD_LOCAL, "drive_service", None)
    if service is None:
        service = drive_service()
        _THREAD_LOCAL.drive_service = service
    return service


def trash_file(file_id: str) -> str:
    request = thread_drive_service().files().update(
        fileId=file_id,
        body={"trashed": True},
        supportsAllDrives=True,
    )
    execute_with_retry(request)
    return file_id


def configured_root_ids(config: dict) -> list[str]:
    roots = config.get("drive_roots") or {}
    ids: list[str] = []
    for root in roots.values():
        root_id = root.get("folder_id")
        if root_id and root_id not in ids:
            ids.append(root_id)
    return ids


def list_drive_pdfs(service, drive_id: str) -> list[dict]:
    files: list[dict] = []
    page_token = None
    while True:
        res = execute_with_retry(
            service.files().list(
                corpora="drive",
                driveId=drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                q="mimeType = 'application/pdf' and trashed = false",
                fields="nextPageToken,files(id,name,size,webViewLink,appProperties,parents)",
                pageSize=1000,
                pageToken=page_token,
            )
        )
        files.extend(res.get("files") or [])
        page_token = res.get("nextPageToken")
        if not page_token:
            return files


def choose_canonical(files: list[dict], registry_by_file_id: dict[str, dict], registry_by_sha: dict[str, dict]) -> str:
    for file in files:
        props = file.get("appProperties") or {}
        sha = props.get("sha256")
        if sha and sha in registry_by_sha:
            keep_id = registry_by_sha[sha].get("drive_file_id")
            if keep_id and any(f.get("id") == keep_id for f in files):
                return keep_id
    for file in files:
        if file.get("id") in registry_by_file_id:
            return file["id"]
    for file in files:
        props = file.get("appProperties") or {}
        doc_id = props.get("document_id")
        if doc_id and any(d.get("document_id") == doc_id for d in registry_by_file_id.values()):
            return file["id"]
    return sorted(files, key=lambda f: f.get("id") or "")[0]["id"]


def build_plan(registry: dict, files: list[dict]) -> dict:
    docs = registry.get("documents") or []
    registry_by_file_id = {d["drive_file_id"]: d for d in docs if d.get("drive_file_id")}
    registry_by_sha = {d["sha256"]: d for d in docs if d.get("sha256")}

    by_sha: defaultdict[str, list[dict]] = defaultdict(list)
    by_name_size: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for file in files:
        props = file.get("appProperties") or {}
        sha = props.get("sha256")
        if sha:
            by_sha[sha].append(file)
        name = file.get("name") or ""
        size = str(file.get("size") or "")
        if name and size:
            by_name_size[(name, size)].append(file)

    trash_ids: set[str] = set()
    keep_ids: set[str] = set()
    duplicate_groups: list[dict] = []

    for sha, group in by_sha.items():
        if len(group) <= 1:
            continue
        keep_id = choose_canonical(group, registry_by_file_id, registry_by_sha)
        keep_ids.add(keep_id)
        trash = [f for f in group if f.get("id") != keep_id]
        for file in trash:
            trash_ids.add(file["id"])
        duplicate_groups.append(
            {
                "sha256": sha,
                "keep_id": keep_id,
                "trash_ids": [f["id"] for f in trash],
                "count": len(group),
            }
        )

    for (_name, _size), group in by_name_size.items():
        if len(group) <= 1:
            continue
        keep_id = choose_canonical(group, registry_by_file_id, registry_by_sha)
        for file in group:
            file_id = file.get("id")
            if not file_id or file_id == keep_id or file_id in keep_ids:
                continue
            if file_id in trash_ids:
                continue
            props = file.get("appProperties") or {}
            if props.get("sha256"):
                continue
            if file_id not in registry_by_file_id and keep_id in registry_by_file_id:
                trash_ids.add(file_id)

    trash_ids -= keep_ids
    return {
        "summary": {
            "drive_pdf_count": len(files),
            "duplicate_sha_groups": len(duplicate_groups),
            "keep_count": len(keep_ids),
            "trash_count": len(trash_ids),
        },
        "duplicate_groups": duplicate_groups[:100],
        "trash_ids": sorted(trash_ids),
    }


def apply_trash(service, trash_ids: list[str], dry_run: bool, workers: int = 4) -> int:
    if dry_run:
        return len(trash_ids)
    del service

    trashed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(trash_file, file_id) for file_id in trash_ids]
        for future in concurrent.futures.as_completed(futures):
            future.result()
            trashed += 1
            if trashed % 100 == 0:
                print(f"Trashed {trashed}/{len(trash_ids)} duplicate file(s)...", flush=True)
    return trashed


def main() -> int:
    parser = argparse.ArgumentParser(description="Trash duplicate PDFs from the configured Google Shared Drive")
    parser.add_argument("--dry-run", action="store_true", help="Report duplicates without trashing them")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    registry = load_json(REGISTRY_PATH)
    config = load_json(CONFIG_PATH)
    service = drive_service()

    files: list[dict] = []
    for root_id in configured_root_ids(config):
        meta = service.files().get(fileId=root_id, fields="id,driveId", supportsAllDrives=True).execute()
        drive_id = meta.get("driveId")
        if not drive_id:
            raise SystemExit(f"Root {root_id} is not inside a Shared Drive.")
        files.extend(list_drive_pdfs(service, drive_id))

    plan = build_plan(registry, files)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print("Drive dedupe plan")
        for key, value in plan["summary"].items():
            print(f"  {key}: {value}")
        print(f"  report_path: {AUDIT_PATH}")

    trashed = apply_trash(service, plan["trash_ids"], args.dry_run)
    if not args.dry_run and trashed:
        print(f"Trashed {trashed} duplicate PDF(s).")
    elif args.dry_run:
        print(f"Dry run only — would trash {trashed} duplicate PDF(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
