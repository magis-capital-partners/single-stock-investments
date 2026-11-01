#!/usr/bin/env python3
"""Classify ValueLine reports and, with --apply, store extracts in the vault.

Default is a dry run. It does not download PDFs and does not write the vault.
``--write-public`` refreshes dashboard labels and the unmatched-name report.

The ticker is the last filename token before the date. It is kept only when
that token is in the registry (or an explicit alias). Other tokens are logged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from licensed_drive_common import (  # noqa: E402
    FILENAME_INDEX_PATH,
    PUBLIC_LICENSED_SOURCES,
    PUBLIC_VALUELINE_PATH,
    VALUELINE_EDITION_BY_ID,
    VALUELINE_SUMMARY_PATH,
    VALUELINE_UNMATCHED_PATH,
    drive_file_url,
    load_json,
    load_registry_companies,
    load_ticker_aliases,
    vault_subdir,
)
from licensed_publish import (  # noqa: E402
    summarize_valueline,
    upsert_licensed_sources,
    valueline_public,
    write_json_public,
    write_valueline_unmatched,
)
from licensed_vault import (  # noqa: E402
    download_drive_bytes,
    extract_pdf_bytes,
    file_in_shard,
    import_documents,
    prepare_tree,
    valueline_relative,
)
from valueline_names import classify_valueline_file  # noqa: E402


def rows_from_index(path: Path) -> list[dict]:
    doc = load_json(path, {})
    edition_ids = set(VALUELINE_EDITION_BY_ID)
    rows = []
    for row in (doc.get("by_filename") or {}).values():
        if not isinstance(row, dict):
            continue
        parents = [parent for parent in (row.get("parents") or []) if parent]
        if not any(parent in edition_ids for parent in parents):
            continue
        rows.append(row)
    return rows


def classify_rows(rows: list[dict], registry: dict[str, str], aliases: dict[str, str]) -> list[dict]:
    classified = []
    for row in rows:
        classified.append(
            classify_valueline_file(
                name=str(row.get("name") or ""),
                file_id=str(row.get("id") or ""),
                parents=list(row.get("parents") or []),
                web_view=drive_file_url(row.get("id"), row.get("webViewLink")),
                path=str(row.get("path") or ""),
                registry=registry,
                aliases=aliases,
                edition_by_id=VALUELINE_EDITION_BY_ID,
            )
        )
    return classified


def vault_jobs(rows: list[dict], shard_index: int, shard_count: int) -> list[dict]:
    jobs = []
    for row in rows:
        relative = valueline_relative(row)
        file_id = row.get("drive_file_id") or ""
        if not relative or not file_id:
            continue
        if not file_in_shard(file_id, shard_index, shard_count):
            continue
        jobs.append(
            {
                "file_id": file_id,
                "relative": relative,
                "sha256": row.get("sha256") or "",
                "meta": {
                    "ticker": row.get("ticker") or "",
                    "edition": row.get("edition") or "",
                    "report_date": row.get("report_date") or "",
                    "drive_url": row.get("drive_url") or "",
                    "original_name": row.get("original_name") or "",
                    "status": row.get("status") or "",
                },
            }
        )
    return jobs


def write_public(rows: list[dict], summary: dict) -> None:
    by_ticker, insights = valueline_public(rows)
    existing = load_json(PUBLIC_LICENSED_SOURCES, {})
    licensed = upsert_licensed_sources(existing, valueline=by_ticker)
    write_json_public(PUBLIC_VALUELINE_PATH, insights)
    write_json_public(PUBLIC_LICENSED_SOURCES, licensed)
    write_json_public(VALUELINE_SUMMARY_PATH, summary)
    unmatched = write_valueline_unmatched(VALUELINE_UNMATCHED_PATH, rows)
    print(
        f"Public ValueLine labels: {len(by_ticker)} tickers; "
        f"unmatched report rows: {unmatched}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-index",
        nargs="?",
        const=str(FILENAME_INDEX_PATH),
        default=None,
        help="Classify the committed filename index instead of listing Drive. "
        "Pass a path, or the flag alone for the default index.",
    )
    parser.add_argument("--apply", action="store_true", help="Download extracts into the research vault.")
    parser.add_argument("--write-public", action="store_true", help="Write dashboard metadata and the unmatched CSV.")
    parser.add_argument(
        "--classified-out",
        type=Path,
        help="Write the classification JSON for a later sharded --from-classified import.",
    )
    parser.add_argument(
        "--from-classified",
        type=Path,
        help="Import a classification JSON produced earlier. Skips the Drive listing.",
    )
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args(argv)

    registry = load_registry_companies()
    aliases = load_ticker_aliases()
    if args.from_classified:
        classified = json.loads(Path(args.from_classified).read_text(encoding="utf-8"))
        if not isinstance(classified, list):
            raise SystemExit("--from-classified must be a JSON list")
        print(f"ValueLine rows in classification file: {len(classified)}")
    else:
        if args.from_index:
            source_rows = rows_from_index(Path(args.from_index))
            print(f"ValueLine rows in filename index: {len(source_rows)}")
        else:
            from licensed_drive_list import list_valueline_pdfs

            source_rows = list_valueline_pdfs()
            print(f"ValueLine PDFs listed from Drive: {len(source_rows)}")
        classified = classify_rows(source_rows, registry, aliases)
    summary = summarize_valueline(classified)
    print(json.dumps({key: value for key, value in summary.items() if key != "note"}, indent=2))
    if args.classified_out:
        args.classified_out.parent.mkdir(parents=True, exist_ok=True)
        args.classified_out.write_text(json.dumps(classified), encoding="utf-8")
        print(f"Wrote {args.classified_out}")
    if args.write_public:
        write_public(classified, summary)
    jobs = vault_jobs(classified, args.shard_index, args.shard_count)
    print(f"Vault jobs in this shard: {len(jobs)}")
    if not args.apply:
        print("Dry run. No PDFs downloaded and no vault files written.")
        return 0
    vault = vault_subdir("valueline", create=True)
    if vault is None:
        print("Research vault is not available. Set RESEARCH_VAULT_ROOT. Nothing was written.", file=sys.stderr)
        return 2
    root = prepare_tree(vault.parent, "valueline")
    from drive_store_common import drive_service

    service = drive_service(readonly=True)

    def download(file_id: str) -> bytes:
        return download_drive_bytes(service, file_id)

    counts = import_documents(root=root, jobs=jobs, download=download, decode=extract_pdf_bytes, dry_run=False)
    print(json.dumps(counts))
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
