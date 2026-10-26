#!/usr/bin/env python3
"""Match Expert Call filenames to registry tickers and store the markdown.

Default is a dry run. ``--apply`` downloads matched markdown into the vault.
It does not move or rename anything on Drive. Drive organization is
``organize_expert_calls_drive.py``, and that apply step is separate.

Empty stubs, ``(1)`` copies, and orphan Word/markdown files are not imported.
The HQI VIC writeup is flagged rather than stored as a call.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from expert_call_match import (  # noqa: E402
    CompanyMatcher,
    plan_expert_calls,
    summarize_plan,
)
from licensed_drive_common import (  # noqa: E402
    EXPERT_OVERRIDE_PATH,
    EXPERT_UNMATCHED_PATH,
    EXPERT_VIC_FLAG_PATH,
    PUBLIC_EXPERT_CALLS_PATH,
    PUBLIC_LICENSED_SOURCES,
    load_expert_overrides,
    load_json,
    load_registry_companies,
    vault_subdir,
    write_json,
)
from licensed_publish import (  # noqa: E402
    expert_public,
    upsert_licensed_sources,
    write_expert_unmatched,
    write_json_public,
)
from licensed_vault import download_drive_bytes, expert_relative, file_in_shard, import_documents, prepare_tree  # noqa: E402

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_UA = "Marvin Research single-stock-investments (contact: portfolio@local)"


def load_listing(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("files") or payload.get("items") or []
    if not isinstance(payload, list):
        raise SystemExit(f"{path} is not a file listing")
    return [row for row in payload if isinstance(row, dict)]


def sec_titles(registry: dict[str, str]) -> dict[str, str]:
    """SEC titles for tickers already in the registry. Fail soft."""
    import urllib.request

    from sec_client import sec_user_agent

    payload = None
    agents = (
        sec_user_agent(),
        SEC_UA,
        "Sample Company Name AdminContact@example.com",
    )
    for agent in agents:
        request = urllib.request.Request(
            SEC_TICKERS_URL,
            headers={"User-Agent": agent, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:  # noqa: BLE001
            print(f"SEC company_tickers unavailable with one user agent ({exc}).")
            payload = None
    if not payload:
        print("Matching registry names only.")
        return {}
    titles: dict[str, str] = {}
    rows = payload.values() if isinstance(payload, dict) else payload
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        title = str(row.get("title") or "").strip()
        if ticker in registry and title:
            titles[ticker] = title
    print(f"SEC titles for registry tickers: {len(titles)}")
    return titles


def matcher_for(fetch_sec: bool) -> CompanyMatcher:
    registry = load_registry_companies()
    by_company, by_id = load_expert_overrides()
    titles = sec_titles(registry) if fetch_sec else {}
    return CompanyMatcher(registry, titles, by_company, by_id)


def write_public(plans: list[dict]) -> None:
    by_ticker, insights = expert_public(plans)
    existing = load_json(PUBLIC_LICENSED_SOURCES, {})
    licensed = upsert_licensed_sources(existing, expert=by_ticker)
    write_json_public(PUBLIC_EXPERT_CALLS_PATH, insights)
    write_json_public(PUBLIC_LICENSED_SOURCES, licensed)
    unmatched = write_expert_unmatched(EXPERT_UNMATCHED_PATH, plans)
    vic = [row for row in plans if row.get("bucket") == "misfiled_vic"]
    write_json(
        EXPERT_VIC_FLAG_PATH,
        {
            "note": "Misfiled VIC writeups found in Expert Calls. Not ingested as calls and not moved.",
            "files": [
                {
                    "file_id": row.get("file_id"),
                    "original_name": row.get("original_name"),
                    "ticker": row.get("ticker"),
                    "company": row.get("company"),
                    "date": row.get("date"),
                    "drive_url": row.get("drive_url"),
                    "suggested_folder": row.get("dest_folder"),
                }
                for row in vic
            ],
        },
    )
    print(f"Public expert-call labels: {len(by_ticker)} tickers; unmatched files: {unmatched}; VIC flags: {len(vic)}")


def vault_jobs(plans: list[dict], shard_index: int, shard_count: int) -> list[dict]:
    jobs = []
    for row in plans:
        relative = expert_relative(row)
        file_id = row.get("file_id") or ""
        if not relative or not file_id:
            continue
        if not file_in_shard(file_id, shard_index, shard_count):
            continue
        jobs.append(
            {
                "file_id": file_id,
                "relative": relative,
                "meta": {
                    "ticker": row.get("ticker") or "",
                    "date": row.get("date") or "",
                    "company": row.get("company") or "",
                    "drive_url": row.get("drive_url") or "",
                    "original_name": row.get("original_name") or "",
                    "vault_name": row.get("new_name") or "",
                },
            }
        )
    return jobs


def decode_markdown(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-listing", type=Path, help="JSON file listing (Name, Size, ID). Skips Drive.")
    parser.add_argument("--apply", action="store_true", help="Download matched markdown into the research vault.")
    parser.add_argument("--write-public", action="store_true")
    parser.add_argument("--fetch-sec", action="store_true", help="Add SEC titles for registry tickers.")
    parser.add_argument("--plans-out", type=Path, help="Write the match plan JSON for a later sharded import.")
    parser.add_argument("--from-plans", type=Path, help="Use a plan JSON from an earlier listing. Skips matching.")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args(argv)
    if not EXPERT_OVERRIDE_PATH.exists():
        print(f"No override file at {EXPERT_OVERRIDE_PATH.name}; using registry names only.")

    if args.from_plans:
        plans = json.loads(args.from_plans.read_text(encoding="utf-8"))
        if not isinstance(plans, list):
            raise SystemExit("--from-plans must be a JSON list")
        print(f"Expert Call rows in plan file: {len(plans)}")
    elif args.from_listing:
        source_rows = load_listing(args.from_listing)
        plans = plan_expert_calls(source_rows, matcher_for(args.fetch_sec))
    else:
        from licensed_drive_list import list_expert_call_files

        source_rows, _folder_id = list_expert_call_files()
        plans = plan_expert_calls(source_rows, matcher_for(args.fetch_sec))
    summary = summarize_plan(plans)
    print(json.dumps(summary, indent=2))
    if args.plans_out:
        args.plans_out.parent.mkdir(parents=True, exist_ok=True)
        args.plans_out.write_text(json.dumps(plans), encoding="utf-8")
        print(f"Wrote {args.plans_out}")
    if args.write_public:
        write_public(plans)
    jobs = vault_jobs(plans, args.shard_index, args.shard_count)
    print(f"Vault markdown jobs in this shard: {len(jobs)}")
    if not args.apply:
        print("Dry run. No call text downloaded and no Drive files moved.")
        return 0
    vault = vault_subdir("expert-calls", create=True)
    if vault is None:
        print("Research vault is not available. Set RESEARCH_VAULT_ROOT. Nothing was written.", file=sys.stderr)
        return 2
    root = prepare_tree(vault.parent, "expert-calls")
    from drive_store_common import drive_service

    service = drive_service(readonly=True)

    def download(file_id: str) -> bytes:
        return download_drive_bytes(service, file_id)

    counts = import_documents(root=root, jobs=jobs, download=download, decode=decode_markdown, dry_run=False)
    print(json.dumps(counts))
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
