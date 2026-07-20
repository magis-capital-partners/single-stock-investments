#!/usr/bin/env python3
"""Move registry-linked Drive PDFs into the canonical folder layout."""
from __future__ import annotations

import argparse
import time

from googleapiclient.errors import HttpError

from drive_store_common import (
    CONFIG_PATH,
    FOLDER_INDEX_PATH,
    REGISTRY_PATH,
    build_folder_paths,
    configured_root_ids,
    drive_service,
    folder_id_by_parent_name,
    item_paths,
    list_drive_items,
    load_json,
    now_iso,
    web_folder_url,
    write_json,
    ensure_folder_path,
)

REPORT_PATH = REGISTRY_PATH.parents[2] / "_system" / "reference" / "document-store" / "drive_layout_migration_report.json"


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


def refresh_folder_index(service, root_ids: list[str]) -> dict:
    items = list_drive_items(service, root_ids)
    folder_paths = build_folder_paths(items, root_ids)
    folders = {
        path: {
            "id": folder_id,
            "webViewLink": web_folder_url(folder_id),
        }
        for folder_id, path in folder_paths.items()
        if path
    }
    payload = {"generated_at": now_iso(), "folders": dict(sorted(folders.items()))}
    write_json(FOLDER_INDEX_PATH, payload)
    return payload


def migrate(dry_run: bool, limit: int = 0, save_every: int = 100) -> dict:
    config = load_json(CONFIG_PATH)
    registry = load_json(REGISTRY_PATH)
    docs = registry.get("documents") or []
    service = drive_service(readonly=False)
    root_ids = configured_root_ids(config)
    items = list_drive_items(service, root_ids)
    by_id = {item["id"]: item for item in items}
    folder_paths = build_folder_paths(items, root_ids)
    existing_folders = folder_id_by_parent_name(items)

    moved: list[dict] = []
    already_ok = 0
    missing: list[dict] = []
    errors: list[dict] = []
    changed_docs = 0
    processed = 0
    touched = 0

    for doc in docs:
        file_id = doc.get("drive_file_id")
        if not file_id:
            missing.append({"document_id": doc.get("document_id"), "reason": "missing drive_file_id"})
            continue
        item = by_id.get(file_id)
        if not item:
            missing.append({"document_id": doc.get("document_id"), "file_id": file_id, "reason": "file not visible"})
            continue
        root_id = doc.get("drive_root_folder_id") or root_ids[0]
        target_path = doc.get("drive_folder_path") or ""
        target_folder_id = ensure_folder_path(service, root_id, target_path, dry_run, existing_folders)
        current_parents = item.get("parents") or []
        current_parent_paths = [folder_paths.get(parent, "") for parent in current_parents]
        extra_parents = [parent for parent in current_parents if parent != target_folder_id]
        needs_parent_move = target_folder_id not in current_parents or extra_parents
        props = item.get("appProperties") or {}
        target_props = {
            "document_id": doc.get("document_id") or "",
            "sha256": doc.get("sha256") or "",
            "source_type": doc.get("source_type") or "pdf",
        }
        needs_props = any(target_props[k] and props.get(k) != target_props[k] for k in target_props)
        if not needs_parent_move and not needs_props:
            already_ok += 1
            doc["drive_folder_id"] = target_folder_id
            touched += 1
            continue

        action = {
            "document_id": doc.get("document_id"),
            "title": doc.get("title"),
            "file_id": file_id,
            "current_parent_paths": current_parent_paths,
            "target_folder_path": target_path,
            "target_folder_id": target_folder_id,
            "parent_move": needs_parent_move,
            "metadata_update": needs_props,
        }
        moved.append(action)
        processed += 1
        if not dry_run:
            params = {
                "fileId": file_id,
                "supportsAllDrives": True,
                "enforceSingleParent": True,
                "fields": "id,name,size,mimeType,webViewLink,webContentLink,appProperties,parents",
            }
            if needs_parent_move:
                if target_folder_id not in current_parents:
                    params["addParents"] = target_folder_id
                if extra_parents:
                    params["removeParents"] = ",".join(extra_parents)
            body = {}
            if needs_props:
                body["appProperties"] = {k: v for k, v in target_props.items() if v}
            try:
                updated = execute_with_retry(service.files().update(body=body, **params))
            except HttpError as exc:
                errors.append({**action, "error": str(exc)})
                print(f"Skipped {file_id}: {exc}", flush=True)
                continue
            by_id[file_id] = updated
            doc["drive_folder_id"] = target_folder_id
            doc["drive_web_view_link"] = updated.get("webViewLink") or doc.get("drive_web_view_link")
            doc["drive_web_content_link"] = updated.get("webContentLink") or doc.get("drive_web_content_link")
            doc["upload_status"] = "moved_canonical" if needs_parent_move else doc.get("upload_status", "linked_existing")
            changed_docs += 1
            touched += 1
            if changed_docs % 100 == 0:
                print(f"Changed {changed_docs} document(s); latest target {target_path}", flush=True)
            if save_every and changed_docs % save_every == 0:
                registry["generated_at"] = now_iso()
                write_json(REGISTRY_PATH, registry)
                print(f"Saved migration checkpoint after {changed_docs} changed document(s).", flush=True)
        if limit and processed >= limit:
            break

    if not dry_run:
        registry["generated_at"] = now_iso()
        write_json(REGISTRY_PATH, registry)
        refresh_folder_index(service, root_ids)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "summary": {
            "registry_document_count": len(docs),
            "already_ok_count": already_ok,
            "move_or_metadata_needed_count": len(moved),
            "changed_doc_count": changed_docs,
            "missing_count": len(missing),
            "error_count": len(errors),
            "limit": limit,
        },
        "changed": moved[:1000],
        "missing": missing[:500],
        "errors": errors[:500],
    }
    write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Move registry-linked PDFs into canonical Drive folders")
    parser.add_argument("--dry-run", action="store_true", help="Report actions without changing Drive or registry")
    parser.add_argument("--apply", action="store_true", help="Apply Drive parent moves and registry folder IDs")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N changed files")
    parser.add_argument("--save-every", type=int, default=100, help="Save registry progress every N processed documents")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        raise SystemExit("Pass --dry-run or --apply.")
    report = migrate(dry_run=not args.apply, limit=args.limit, save_every=max(1, args.save_every))
    print("Drive layout migration")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"  report_path: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
