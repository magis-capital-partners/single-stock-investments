#!/usr/bin/env python3
"""Move non-registry top-level Drive folders under the canonical PDF store roots."""
from __future__ import annotations

import argparse
import re
import time

from googleapiclient.errors import HttpError

from drive_store_common import (
    CONFIG_PATH,
    FOLDER_MIME,
    REGISTRY_PATH,
    build_folder_paths,
    configured_root_ids,
    drive_service,
    drive_quote,
    ensure_folder_path,
    folder_id_by_parent_name,
    item_paths,
    list_drive_items,
    load_json,
    now_iso,
    write_json,
)

REPORT_PATH = REGISTRY_PATH.parents[2] / "_system" / "reference" / "document-store" / "drive_orphan_folder_organize_report.json"
CANONICAL_TOP = {"Letters", "Single Stocks", "Research Sources", "Admin"}
SKIP_TOP = CANONICAL_TOP | {"_Historical Letters"}
QUARTER_RE = re.compile(r"^(\d{4})\s+([1-4])Q(?:\s+Letters)?$", re.IGNORECASE)
HISTORICAL_QUARTER_RE = re.compile(r"^_Historical Letters/(?:\d{4}/)?(\d{4})\s+([1-4])Q(?:\s+Letters)?$", re.IGNORECASE)
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


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


def folder_exists_query(service, parent_id: str, name: str) -> str | None:
    res = execute_with_retry(
        service.files().list(
            q=(
                f"'{parent_id}' in parents and "
                f"name = '{drive_quote(name)}' and "
                f"mimeType = '{FOLDER_MIME}' and trashed = false"
            ),
            fields="files(id,name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        )
    )
    rows = res.get("files") or []
    return rows[0]["id"] if rows else None


def move_folder(service, folder_id: str, current_parents: list[str], target_parent_id: str, new_name: str | None, dry_run: bool) -> None:
    if dry_run:
        return
    params = {
        "fileId": folder_id,
        "supportsAllDrives": True,
        "enforceSingleParent": True,
        "fields": "id,name,parents",
    }
    if target_parent_id not in current_parents:
        params["addParents"] = target_parent_id
    remove = [parent for parent in current_parents if parent != target_parent_id]
    if remove:
        params["removeParents"] = ",".join(remove)
    body = {"name": new_name} if new_name else {}
    execute_with_retry(service.files().update(body=body, **params))


def target_for_folder(path: str) -> tuple[str, str] | None:
    top = path.split("/", 1)[0]
    if top in CANONICAL_TOP:
        return None
    m = QUARTER_RE.match(top)
    if m and path == top:
        return f"Letters/{m.group(1)} Q{m.group(2)}", "quarter"
    m = HISTORICAL_QUARTER_RE.match(path)
    if m:
        return f"Letters/{m.group(1)} Q{m.group(2)}", "historical_quarter"
    if path == "_Historical Letters":
        return "Research Sources/Legacy Drive Copies/_Historical Letters", "historical_root"
    if "/" not in path and TICKER_RE.match(top):
        return f"Single Stocks/{top}/Legacy Drive Copies/{top}", "ticker_legacy"
    if "/" not in path and top not in SKIP_TOP:
        return f"Research Sources/Legacy Drive Copies/{top}", "other_legacy"
    return None


def organize(dry_run: bool) -> dict:
    config = load_json(CONFIG_PATH)
    service = drive_service(readonly=False)
    root_ids = configured_root_ids(config)
    root_id = root_ids[0]
    items = list_drive_items(service, root_ids)
    by_id = {item["id"]: item for item in items}
    folder_paths = build_folder_paths(items, root_ids)
    paths, _children = item_paths(items, root_ids)
    existing = folder_id_by_parent_name(items)

    actions: list[dict] = []
    errors: list[dict] = []
    moved = 0
    for folder_id, path in sorted(folder_paths.items(), key=lambda kv: kv[1].count("/"), reverse=True):
        target = target_for_folder(path)
        if not target:
            continue
        target_path, reason = target
        target_parts = [p for p in target_path.split("/") if p]
        target_name = target_parts[-1]
        target_parent_path = "/".join(target_parts[:-1])
        target_parent_id = ensure_folder_path(service, root_id, target_parent_path, dry_run, existing)
        existing_target = None if dry_run else folder_exists_query(service, target_parent_id, target_name)
        final_parent_id = target_parent_id
        final_name = target_name
        if existing_target and existing_target != folder_id:
            current_name = by_id[folder_id].get("name") or target_name
            if target_parent_path == "Letters":
                final_parent_id = ensure_folder_path(service, root_id, f"Letters/{target_name}/Legacy Drive Copies", dry_run, existing)
                final_name = current_name
            else:
                final_name = f"{current_name}-{folder_id[:6]}"
        item = by_id[folder_id]
        action = {
            "folder_id": folder_id,
            "current_path": path,
            "current_name": item.get("name"),
            "target_path": "/".join([p for p in [target_parent_path, final_name] if p]),
            "reason": reason,
        }
        actions.append(action)
        try:
            move_folder(service, folder_id, item.get("parents") or [], final_parent_id, final_name, dry_run)
            moved += 0 if dry_run else 1
            if moved and moved % 25 == 0:
                print(f"Moved {moved} folder(s).", flush=True)
        except Exception as exc:
            errors.append({**action, "error": str(exc)})
            print(f"Skipped {folder_id}: {exc}", flush=True)

    report = {
        "generated_at": now_iso(),
        "dry_run": dry_run,
        "summary": {
            "candidate_folder_count": len(actions),
            "moved_folder_count": moved,
            "error_count": len(errors),
        },
        "actions": actions,
        "errors": errors,
    }
    write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Organize non-registry Drive folders under canonical roots")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        raise SystemExit("Pass --dry-run or --apply.")
    report = organize(dry_run=not args.apply)
    print("Drive orphan folder organization")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"  report_path: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
