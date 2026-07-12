#!/usr/bin/env python3
"""Run dashboard rebuild script lists by CI profile.

Profiles (aliases in parentheses):
  minimal              — build_dashboard_data only
  insights (pages-fast)— letters/index/insights/research_memory + dashboard
  activist             — activist feed + document registry slice
  darwin (darwin-full) — IRA tier download + Darwin portfolio + dashboard
  full (intake-full)    — nightly full rebuild (~30 scripts)

Removed: darwin-fast (use insights or darwin).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALIASES = {
    "pages-fast": "insights",
    "darwin-full": "darwin",
    "intake-full": "full",
}

# Each entry is argv after `python` (script path relative to repo root + args).
PROFILES: dict[str, list[list[str]]] = {
    "minimal": [
        ["_system/scripts/build_dashboard_data.py"],
    ],
    "insights": [
        ["_system/scripts/enrich_cusip_ticker_map.py", "--skip-fetch"],
        ["_system/scripts/build_specialist_13f_signals.py"],
        ["_system/scripts/build_biotech_spend_value.py"],
        ["_system/scripts/build_biotech_insider_scores.py"],
        ["_system/scripts/build_biotech_peer_short_stub.py"],
        ["_system/scripts/build_biotech_composite.py"],
        ["_system/scripts/build_research_memory.py"],
        ["_system/scripts/repair_letter_dates.py", "--apply"],
        ["_system/scripts/build_index_membership.py"],
        ["_system/scripts/build_insights.py"],
        ["_system/scripts/build_dashboard_data.py"],
        ["_system/scripts/validate_research_memory.py"],
    ],
    "activist": [
        ["_system/scripts/build_document_registry.py"],
        ["_system/scripts/clean_activist_indexes.py"],
        ["_system/scripts/cleanup_activist_false_positives.py"],
        ["_system/scripts/activist_triage.py", "--apply", "--fetch-sec"],
        ["_system/scripts/build_activist_feed.py"],
        ["_system/scripts/auto_resolve_filing_events.py"],
        ["_system/scripts/build_letter_drive_links.py"],
        ["_system/scripts/build_index_membership.py"],
        ["_system/scripts/build_dashboard_data.py"],
    ],
    "darwin": [
        ["_system/scripts/download_ira_research.py", "--tier", "A"],
        ["_system/scripts/download_ira_research.py", "--tier", "B"],
        ["_system/scripts/build_darwin_portfolio.py"],
        ["_system/scripts/build_dashboard_data.py"],
    ],
    "full": [
        ["_system/scripts/build_document_registry.py"],
        ["_system/scripts/audit_drive_pdf_store.py"],
        ["_system/scripts/build_drive_filename_index.py"],
        ["_system/scripts/build_letter_drive_links.py"],
        ["_system/scripts/sync_pdf_store_google_drive.py", "--root-key", "general_pdfs", "--workers", "4"],
        ["_system/scripts/build_document_registry.py"],
        ["_system/scripts/build_drive_filename_index.py"],
        ["_system/scripts/build_letter_drive_links.py"],
        ["_system/scripts/build_fundamental_series.py"],
        ["_system/scripts/fetch_insider_transactions.py", "--offline"],
        ["_system/scripts/build_equity_model_dashboard.py"],
        ["_system/scripts/extract_equity_kpi_observations.py"],
        ["_system/scripts/build_kpi_trends.py"],
        ["_system/scripts/repair_letter_dates.py", "--apply"],
        ["_system/scripts/build_superinvestor_insights.py"],
        ["_system/scripts/build_index_membership.py"],
        ["_system/scripts/build_insights.py"],
        ["_system/scripts/enrich_cusip_ticker_map.py", "--skip-fetch"],
        ["_system/scripts/build_specialist_13f_signals.py"],
        ["_system/scripts/build_biotech_spend_value.py"],
        ["_system/scripts/build_biotech_insider_scores.py"],
        ["_system/scripts/build_biotech_peer_short_stub.py"],
        ["_system/scripts/build_biotech_composite.py"],
        ["_system/scripts/build_research_memory.py"],
        ["_system/scripts/build_power_zones.py"],
        ["_system/scripts/clean_activist_indexes.py"],
        ["_system/scripts/cleanup_activist_false_positives.py"],
        ["_system/scripts/activist_triage.py", "--apply", "--fetch-sec"],
        ["_system/scripts/build_activist_feed.py"],
        ["_system/scripts/auto_resolve_filing_events.py"],
        ["_system/scripts/build_dashboard_data.py"],
    ],
}


def resolve_profile(name: str) -> str:
    key = name.strip()
    if key == "none":
        raise SystemExit("profile 'none' means skip rebuild; do not invoke this script")
    if key == "darwin-fast":
        raise SystemExit(
            "profile 'darwin-fast' was removed; use 'darwin' (full Darwin) or 'insights' (pages)"
        )
    return ALIASES.get(key, key)


def run_profile(profile: str, *, dry_run: bool = False) -> int:
    resolved = resolve_profile(profile)
    steps = PROFILES.get(resolved)
    if steps is None:
        known = ", ".join(sorted(set(PROFILES) | set(ALIASES)))
        raise SystemExit(f"Unknown rebuild profile: {profile!r} (known: {known})")

    print(f"ci_rebuild_profile: profile={profile} resolved={resolved} steps={len(steps)}")
    env = os.environ.copy()
    for step in steps:
        cmd = [sys.executable, *step]
        print("+", " ".join(cmd))
        if dry_run:
            continue
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", help="Rebuild profile name")
    parser.add_argument("--dry-run", action="store_true", help="Print steps only")
    parser.add_argument("--list", action="store_true", help="List profiles and exit")
    args = parser.parse_args()
    if args.list:
        for name in sorted(PROFILES):
            print(f"{name}: {len(PROFILES[name])} steps")
        for alias, target in sorted(ALIASES.items()):
            print(f"{alias} -> {target}")
        return 0
    if not args.profile:
        parser.error("profile is required unless --list")
    return run_profile(args.profile, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
