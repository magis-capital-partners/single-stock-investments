#!/usr/bin/env python3
"""Trash redundant legacy folders from the Google Drive PDF store."""
from __future__ import annotations

import argparse
import time
from collections import defaultdict

from googleapiclient.errors import HttpError

from drive_store_common import (
    CONFIG_PATH,
    FOLDER_MIME,
    REGISTRY_PATH,
    build_folder_paths,
    configured_root_ids,
    drive_service,
    item_paths,
    list_drive_items,
    load_json,
    now_iso,
    write_json,
)

REPORT_PATH = REGISTRY_PATH.parents[2] / "_system" / "reference" / "document-store" / "drive_cleanup_report.json"
LEGACY_TOP_LEVEL = {
    "superinvestor-letters",
    "company-documents",
    "third-party-research",
    "sumzero-research",
    "dropbox-ingestion",
    "uncategorized",
}
CANONICAL_TOP_LEVEL = {"Single Stocks", "Letters", "Research Sources", "Admin"}


def execute_with_retry(request, attempts: int = 6):
    delay = 2.0
    for attempt in range(attempts):
        try:
            return request.execute()
        except Exception as exc:
            retryable = True
            if isinstance(exc, HttpError):
                retryable = exc.resp.status in {403, 429, 500, 502, 503, 504}
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60.0)


def descendants(folder_id: str, child_ids_by_parent: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    stack = list(child_ids_by_parent.get(folder_id, []))
    while stack:
        item_id = stack.pop()
        if item_id in out:
            continue
        out.add(item_id)
        stack.extend(child_ids_by_parent.get(item_id, []))
    return out


def cleanup(dry_run: bool, trash_legacy: bool, trash_empty_duplicates: bool) -> dict:
    config = load_json(CONFIG_PATH)
    registry = load_json(REGISTRY_PATH)
    service = drive_service(readonly=False)
    root_ids = configured_root_ids(config)
    items = list_drive_items(service, root_ids)
    by_id = {item["id"]: item for item in items}
    folder_paths = build_folder_paths(items, root_ids)
    paths, _children_by_path = item_paths(items, root_ids)

    child_ids_by_parent: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for parent in item.get("parents") or []:
            child_ids_by_parent[parent].append(item["id"])

    registry_file_ids = {doc.get("drive_file_id") for doc in registry.get("documents") or [] if doc.get("drive_file_id")}
    folders_to_trash: list[dict] = []
    skipped: list[dict] = []

    if trash_legacy:
        for folder_id, path in folder_paths.items():
            if "/" in path or path not in LEGACY_TOP_LEVEL:
                continue
            desc = descendants(folder_id, child_ids_by_parent)
            registry_desc = sorted(desc & registry_file_ids)
            folder = by_id[folder_id]
            row = {
                "folder_id": folder_id,
                "path": path,
                "name": folder.get("name"),
                "descendant_count": len(desc),
                "registry_linked_descendant_count": len(registry_desc),
            }
            if registry_desc:
                skipped.append({**row, "reason": "registry-linked files remain"})
            else:
                folders_to_trash.append(row)

    if trash_empty_duplicates:
        by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for folder_id, path in folder_paths.items():
            name = by_id[folder_id].get("name") or ""
            if name:
                by_name[name].append((folder_id, path))
        for name, rows in by_name.items():
            if len(rows) <= 1:
                continue
            for folder_id, path in rows:
                top = path.split("/", 1)[0]
                if top in CANONICAL_TOP_LEVEL:
                    continue
                desc = descendants(folder_id, child_ids_by_parent)
                if desc:
                    continue
                if any(row["folder_id"] == folder_id for row in folders_to_trash):
                    continue
                folders_to_trash.append(
                    {
                        "folder_id": folder_id,
                        "path": path,
                        "name": name,
                        "descendant_count": 0,
                        "registry_linked_descendant_count": 0,
                        "reason": "empty duplicate folder name",
                    }
                )

    trashed = []
    errors = []
    if not dry_run:
        for idx, row in enumerate(folders_to_trash, start=1):
            try:
                execute_with_retry(
                    service.files().update(
                        fileId=row["folder_id"],
                        body={"trashed": True},
                        fields="id,trashed",
                        supportsAllDrives=True,
                    )
                )
                trashed.append(row)
                if idx % 100 == 0:
                    print(f"Trashed {idx}/{len(folders_to_trash)} folder(s).", flush=True)
            except Exception as exc:
                errors.append({**row, "error": str(exc)})
                print(f"Skipped folder {row['folder_id']}: {exc}", flush=True)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "summary": {
            "candidate_folder_count": len(folders_to_trash),
            "trashed_folder_count": len(trashed),
            "skipped_folder_count": len(skipped),
            "error_count": len(errors),
        },
        "candidates": folders_to_trash,
        "trashed": trashed,
        "skipped": skipped,
        "errors": errors,
    }
    write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Trash redundant legacy Drive folders")
    parser.add_argument("--dry-run", action="store_true", help="Report cleanup without changing Drive")
    parser.add_argument("--apply", action="store_true", help="Trash selected folders")
    parser.add_argument("--trash-legacy-folders", action="store_true", help="Trash legacy top-level folders after safety checks")
    parser.add_argument("--trash-empty-duplicates", action="store_true", help="Trash empty duplicate folders outside canonical roots")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        raise SystemExit("Pass --dry-run or --apply.")
    report = cleanup(
        dry_run=not args.apply,
        trash_legacy=args.trash_legacy_folders,
        trash_empty_duplicates=args.trash_empty_duplicates,
    )
    print("Drive cleanup")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"  report_path: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
