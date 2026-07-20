#!/usr/bin/env python3
"""Plan the Google Drive PDF store reorganization without mutating Drive."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict

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

REPORT_PATH = REGISTRY_PATH.parents[2] / "_system" / "reference" / "document-store" / "drive_reorg_plan.json"
LEGACY_TOP_LEVEL = {
    "superinvestor-letters",
    "company-documents",
    "third-party-research",
    "sumzero-research",
    "dropbox-ingestion",
    "uncategorized",
}


def build_plan() -> dict:
    config = load_json(CONFIG_PATH)
    registry = load_json(REGISTRY_PATH)
    service = drive_service(readonly=True)
    root_ids = configured_root_ids(config)
    items = list_drive_items(service, root_ids)
    folder_paths = build_folder_paths(items, root_ids)
    paths, children = item_paths(items, root_ids)
    by_id = {item["id"]: item for item in items}

    registry_docs = registry.get("documents") or []
    registry_file_ids = {doc.get("drive_file_id") for doc in registry_docs if doc.get("drive_file_id")}
    registry_doc_ids = {doc.get("document_id") for doc in registry_docs if doc.get("document_id")}
    target_paths = Counter(doc.get("drive_folder_path") or "" for doc in registry_docs)

    move_needed = []
    already_canonical = 0
    missing_drive_file = 0
    for doc in registry_docs:
        file_id = doc.get("drive_file_id")
        target = doc.get("drive_folder_path") or ""
        if not file_id or file_id not in by_id:
            missing_drive_file += 1
            continue
        parent_paths = [folder_paths.get(parent, "") for parent in by_id[file_id].get("parents") or []]
        if target in parent_paths:
            already_canonical += 1
        else:
            move_needed.append(
                {
                    "document_id": doc.get("document_id"),
                    "title": doc.get("title"),
                    "file_id": file_id,
                    "current_parent_paths": parent_paths,
                    "target_folder_path": target,
                    "local_pdf_path": doc.get("local_pdf_path"),
                }
            )

    folder_counts: dict[str, dict] = {}
    folder_registry_counts: Counter[str] = Counter()
    folder_orphan_counts: Counter[str] = Counter()
    folder_missing_sha_counts: Counter[str] = Counter()
    for item in items:
        if item.get("mimeType") != "application/pdf":
            continue
        parents = item.get("parents") or []
        props = item.get("appProperties") or {}
        is_registry = item.get("id") in registry_file_ids or props.get("document_id") in registry_doc_ids
        for parent in parents:
            folder_path = folder_paths.get(parent, "")
            if is_registry:
                folder_registry_counts[folder_path] += 1
            else:
                folder_orphan_counts[folder_path] += 1
            if not props.get("sha256"):
                folder_missing_sha_counts[folder_path] += 1

    for folder_id, path in folder_paths.items():
        child_count = len(children.get(path, []))
        if not path:
            continue
        folder_counts[path] = {
            "folder_id": folder_id,
            "child_count": child_count,
            "registry_pdf_count": folder_registry_counts.get(path, 0),
            "orphan_pdf_count": folder_orphan_counts.get(path, 0),
            "missing_sha_pdf_count": folder_missing_sha_counts.get(path, 0),
            "legacy_top_level": path.split("/", 1)[0] in LEGACY_TOP_LEVEL,
        }

    top_level = Counter(path.split("/", 1)[0] for path in folder_paths.values() if path)
    duplicate_name_groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item.get("mimeType") == FOLDER_MIME:
            duplicate_name_groups[item.get("name") or ""].append({"id": item["id"], "path": paths.get(item["id"])})
    duplicate_name_groups = {k: v for k, v in duplicate_name_groups.items() if len(v) > 1 and k}

    return {
        "generated_at": now_iso(),
        "summary": {
            "drive_item_count": len(items),
            "drive_folder_count": sum(1 for i in items if i.get("mimeType") == FOLDER_MIME),
            "drive_pdf_count": sum(1 for i in items if i.get("mimeType") == "application/pdf"),
            "registry_document_count": len(registry_docs),
            "registry_uploaded_count": len(registry_file_ids),
            "already_canonical_count": already_canonical,
            "move_needed_count": len(move_needed),
            "missing_drive_file_count": missing_drive_file,
            "target_folder_count": len(target_paths),
            "legacy_folder_count": sum(1 for p in folder_counts if p.split("/", 1)[0] in LEGACY_TOP_LEVEL),
            "duplicate_folder_name_count": len(duplicate_name_groups),
        },
        "top_level_folders": dict(sorted(top_level.items())),
        "target_folders": dict(sorted(target_paths.items())),
        "folders": dict(sorted(folder_counts.items())),
        "move_needed": move_needed[:500],
        "duplicate_folder_names": duplicate_name_groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan Drive PDF store reorganization")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()
    plan = build_plan()
    write_json(REPORT_PATH, plan)
    if args.json:
        import json

        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print("Drive reorg plan")
        for key, value in plan["summary"].items():
            print(f"  {key}: {value}")
        print(f"  report_path: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
