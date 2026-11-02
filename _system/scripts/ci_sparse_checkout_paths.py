#!/usr/bin/env python3
"""Emit git sparse-checkout paths for CI profiles (one path per line).

Profiles:
  news         — portfolio news ingest (holdings news JSON only)
  marvin-pick  — marvin_pick_ticker metadata (holdings research md/json)
  downloads    — same research trees as marvin-pick; document batches are added later
  drive        — ticker research, third-party analyses, and Drive intake folders
  two-phase-watch — INV Accelsius cooling watch (eight ticker trees + INV shard)
  dashboard    — deploy rebuild checkout (base paths only)
  thirteen-f   — Data Pipeline 13F job (the dashboard files that job reads)
  buyback-radar — buyback snapshots, consumer shards, and the two books it patches
  activist     — Data Pipeline activist job (downloads trees plus third-party analyses)

Base paths (_system, .github, and for most profiles the whole dashboard
tree) are set by ci_checkout_workspace.sh. This script emits the extra
paths. thirteen-f emits dashboard files instead of ticker trees; the shell
passes files-only so the whole dashboard tree stays out of the checkout.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

# Soft cap for the dashboard profile (must stay tiny — SPX-scale explosion caused 5h checkouts).
BASE_PROFILE_PATH_CAP = 200


def load_holdings() -> list[str]:
    if not REGISTRY_PATH.exists():
        return []
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return sorted((reg.get("holdings") or {}).keys())


def tracked_company_dirs() -> list[str]:
    """Top-level company trees in git, not holdings only.

    Drive intake accepts a PDF for any ticker folder in the repo. Listing
    those trees from git avoids checking out the filing PDFs under them.
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "-d", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git ls-tree failed")
    skip = {
        ".claude",
        ".cursor",
        ".github",
        ".vscode",
        "_eval",
        "_external",
        "_system",
        "contracts",
        "dashboard",
        "docs",
        "ops-watchdog",
        "outputs",
        "tests",
    }
    return sorted(
        name
        for name in result.stdout.splitlines()
        if name and name not in skip and not name.startswith(".")
    )


def paths_for_profile(profile: str) -> list[str]:
    holdings = load_holdings()
    paths: list[str] = []

    if profile == "news":
        for ticker in holdings:
            paths.append(f"{ticker}/research/news")
        return paths

    if profile in {"marvin-pick", "downloads"}:
        for ticker in holdings:
            paths.extend(
                [
                    f"{ticker}/research/news",
                    f"{ticker}/research",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
                    f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
                ]
            )
        return paths

    if profile == "two-phase-watch":
        tickers = ["NVDA", "AMD", "VRT", "JCI", "SMCI", "DELL", "HPE", "INV"]
        extra: list[str] = []
        for ticker in tickers:
            extra.extend(
                [
                    f"{ticker}/research",
                    f"{ticker}/investor-documents",
                ]
            )
        extra.append("dashboard/data/tickers/INV.json")
        return extra

    if profile == "marvin-forecast":
        ticker = os.environ.get("CI_FORECAST_TICKER", "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9.^_-]+", ticker):
            raise SystemExit("CI_FORECAST_TICKER is required and must be a safe ticker")
        if ticker not in holdings:
            raise SystemExit(f"CI_FORECAST_TICKER is not in the portfolio registry: {ticker}")
        return [
            f"{ticker}/research",
            f"{ticker}/.onboard_status.json",
            f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
            f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
        ]

    if profile == "dashboard":
        # The pages rebuild reads market-data / portfolio / dashboard under
        # _system and dashboard/ (already in base sparse set). No ticker trees.
        return []

    if profile == "thirteen-f":
        # Read by build_overlap_holdings.py / ingest_13f.py, and rewritten by
        # the thirteen-f job. holdings/ covers by_ticker, by_manager, the
        # managers index, and the feed. Not the rest of dashboard/data.
        return [
            "dashboard/data/overlap_holders.json",
            "dashboard/data/overlap_holdings.json",
            "dashboard/data/fund_holdings_summary.json",
            "dashboard/data/index_membership.json",
            "dashboard/data/holdings",
        ]

    if profile == "buyback-radar":
        # ci_checkout_workspace.sh passes "listed", so this is the whole
        # checkout plus .github. No ticker filings and no activist-report tree.
        return [
            "_system/scripts",
            "_system/portfolio",
            "_system/data/buyback_radar",
            "_system/reference/market-data/fundamentals",
            ".gitattributes",
            "dashboard/private-assets.json",
            "dashboard/data/buyback_radar.json",
            "dashboard/data/buyback_companies.json",
            "dashboard/data/buyback_manifest.json",
            "dashboard/data/buyback_snapshots",
            "dashboard/data/tickers",
            "dashboard/data/agent_shards",
            "dashboard/data/special_situations.json",
            "dashboard/data/short_alpha.json",
        ]

    if profile == "activist":
        # The scan reads and writes third-party-analyses/ (reports, indexes,
        # short_reports, inventory) and research/activist_reconcile.md. The
        # rebuild step runs build_dashboard_data on the same trees the
        # downloads job keeps. Report refs point here or into _system, never
        # into the filing PDFs, which stay out.
        for ticker in holdings:
            paths.extend(
                [
                    f"{ticker}/README.md",
                    f"{ticker}/research",
                    f"{ticker}/third-party-analyses",
                    f"{ticker}/.onboard_status.json",
                    f"{ticker}/INDEX.csv",
                    f"{ticker}/_download_log.txt",
                    f"{ticker}/investor-documents/DOWNLOAD_MANIFEST.json",
                    f"{ticker}/investor-documents/TRANSCRIPT_MANIFEST.json",
                    f"{ticker}/investor-documents/research-notes",
                ]
            )
        return paths

    if profile == "drive":
        # README makes the ticker directory exist for normalize_ticker.
        # research/ and third-party-analyses/ are what import and the insights
        # rebuild read. drive-intake/ is the company-PDF destination.
        # investor-documents/*.pdf and *.htm stay out: that tree is 41 GiB.
        paths = []
        for ticker in tracked_company_dirs():
            paths.extend(
                [
                    f"{ticker}/README.md",
                    f"{ticker}/research",
                    f"{ticker}/third-party-analyses",
                    f"{ticker}/investor-documents/drive-intake",
                ]
            )
        return paths

    raise SystemExit(f"Unknown sparse profile: {profile}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    count_only = False
    if args and args[0] == "--count":
        count_only = True
        args = args[1:]
    if len(args) != 1:
        raise SystemExit(f"Usage: {sys.argv[0]} [--count] <profile>")
    profile = args[0].strip()
    seen: set[str] = set()
    out: list[str] = []
    for path in paths_for_profile(profile):
        if path not in seen:
            seen.add(path)
            out.append(path)

    if profile == "dashboard" and len(out) > BASE_PROFILE_PATH_CAP:
        raise SystemExit(
            f"ERROR: sparse profile {profile!r} has {len(out)} paths "
            f"(cap {BASE_PROFILE_PATH_CAP}). Refusing SPX-scale checkout explosion."
        )

    if count_only:
        print(len(out))
        return

    for path in out:
        print(path)


if __name__ == "__main__":
    main()
