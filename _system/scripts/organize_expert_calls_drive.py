#!/usr/bin/env python3
"""Plan Expert Calls folders. Default is a dry run that writes a CSV.

Matched calls go to Expert Calls/{TICKER}/ under YYYY-MM-DD_TICKER_Company_topic.
Low-confidence names go to Expert Calls/_Unmatched and keep their names.
``(1)`` copies, stub markdown, and orphan Word or markdown files go to
Expert Calls/_Duplicates. Nothing is removed.

``--apply`` performs those moves on Drive after a live listing. Do not pass
it until the CSV has been reviewed. A file listing cannot be applied, because
the current parent id has to come from Drive.

New uploads that land in the Expert Calls root are planned the same way on
the next run. Files already inside a subfolder are left where they are.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from expert_call_match import plan_expert_calls, summarize_plan  # noqa: E402
from import_drive_expert_calls import load_listing, matcher_for  # noqa: E402
from licensed_drive_common import (  # noqa: E402
    DRIVE_ROOT_ID,
    EXPERT_PLAN_PATH,
    EXPERT_PLAN_SUMMARY_PATH,
    now_iso,
    write_json,
)
from licensed_publish import write_plan_csv  # noqa: E402


def apply_plan(service, plans: list[dict], expert_root_id: str, drive_root_id: str) -> dict:
    """Move and rename. This function does not remove files."""
    from drive_store_common import execute_with_retry

    from licensed_drive_list import FOLDER_MIME, child_folder, list_children

    cache: dict[tuple[str, str], str] = {}
    for item in list_children(service, expert_root_id):
        if item.get("mimeType") == FOLDER_MIME and item.get("name") and item.get("id"):
            cache[(expert_root_id, item["name"])] = str(item["id"])
    moved = 0
    skipped = 0
    for row in plans:
        if row.get("bucket") == "already_filed":
            skipped += 1
            continue
        parents = [parent for parent in (row.get("source_parents") or []) if parent]
        if not parents:
            raise SystemExit(
                f"Refusing to move {row.get('file_id')}: current parent is unknown. "
                "Apply lists Drive; it does not replay an offline CSV."
            )
        if row.get("bucket") == "misfiled_vic":
            dest_id = drive_root_id
            for part in [part for part in str(row.get("dest_folder") or "").split("/") if part]:
                dest_id = child_folder(service, dest_id, part, cache)
        else:
            folder_name = str(row.get("dest_folder") or "").split("/")[-1]
            dest_id = child_folder(service, expert_root_id, folder_name, cache)
        new_name = row.get("new_name") or row.get("original_name")
        same_name = new_name == row.get("original_name")
        if dest_id in parents and same_name:
            skipped += 1
            continue
        kwargs = {
            "fileId": row["file_id"],
            "addParents": dest_id,
            "supportsAllDrives": True,
            "fields": "id,name,parents",
        }
        remove = [parent for parent in parents if parent != dest_id]
        if remove:
            kwargs["removeParents"] = ",".join(remove)
        if not same_name:
            kwargs["body"] = {
                "name": new_name,
                "description": f"Original filename: {row.get('original_name') or ''}",
            }
        execute_with_retry(service.files().update(**kwargs))
        moved += 1
    return {"moved": moved, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-listing", type=Path, help="Offline JSON listing. Cannot be combined with --apply.")
    parser.add_argument(
        "--from-plans",
        type=Path,
        help="Write the CSV from a plan JSON. Skips listing and matching.",
    )
    parser.add_argument("--apply", action="store_true", help="Move and rename on Drive. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Write the CSV and do not change Drive.")
    parser.add_argument("--fetch-sec", action="store_true")
    parser.add_argument("--output", type=Path, default=EXPERT_PLAN_PATH)
    parser.add_argument("--summary", type=Path, default=EXPERT_PLAN_SUMMARY_PATH)
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("Pass either --apply or --dry-run.")
    if args.apply and (args.from_listing or args.from_plans):
        parser.error("--apply lists the live Expert Calls folder. It does not replay a file.")

    folder_id = ""
    source = "drive"
    if args.from_plans:
        plans = json.loads(args.from_plans.read_text(encoding="utf-8"))
        if not isinstance(plans, list):
            raise SystemExit("--from-plans must be a JSON list")
        source = "plans"
    elif args.from_listing:
        source_rows = load_listing(args.from_listing)
        plans = plan_expert_calls(source_rows, matcher_for(args.fetch_sec))
        source = "listing"
    else:
        from licensed_drive_list import list_expert_call_files

        source_rows, folder_id = list_expert_call_files()
        plans = plan_expert_calls(source_rows, matcher_for(args.fetch_sec))
    summary = summarize_plan(plans)
    summary["reasons"] = dict(Counter(str(row.get("reason") or "") for row in plans))
    summary.update(
        {
            "generated_at": now_iso(),
            "applied": False,
            "expert_calls_folder_id": folder_id,
            "source": source,
            "note": (
                "Dry run. Nothing on Drive was moved or removed. "
                "original_name is the pre-rename filename. "
                "A later --apply sets the Drive description to that name. "
                "Files already in a subfolder stay there. "
                "New files dropped in the Expert Calls root are filed the same way."
            ),
        }
    )
    write_plan_csv(args.output, plans)
    write_json(args.summary, summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "note"}, indent=2))
    print(f"Wrote {args.output}")
    if not args.apply:
        print("Dry run only. Drive was not changed.")
        return 0

    from drive_store_common import drive_service

    service = drive_service(readonly=False)
    result = apply_plan(service, plans, folder_id, DRIVE_ROOT_ID)
    summary["applied"] = True
    summary["apply_result"] = result
    summary["note"] = "Applied. Files were moved or renamed. None were removed."
    write_json(args.summary, summary)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
