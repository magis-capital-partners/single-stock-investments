#!/usr/bin/env python3
"""Scan all third-party sources for a ticker (HK, Substacks, PDFs, pending, shorts).

Outputs:
  {TICKER}/third-party-analyses/source_inventory_{date}.json
  {TICKER}/third-party-analyses/source_inventory_{date}.md

Usage:
  python _system/scripts/scan_third_party_sources.py GOOGL
  python _system/scripts/scan_third_party_sources.py --all
  python _system/scripts/scan_third_party_sources.py APLD --date 2026-06-01 --with-hk
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry
from third_party_inventory import write_inventory

HK_INDEX = ROOT / "_system" / "reference" / "investment-wisdom" / "hk_ticker_index.json"
PY = sys.executable


def registry_tickers() -> list[str]:
    reg = load_registry()
    holdings = reg.get("holdings", {})
    if isinstance(holdings, dict):
        return sorted(holdings.keys())
    return sorted({h["ticker"] for h in holdings})


def maybe_hk_scan(ticker: str, out_date: str) -> None:
    if not HK_INDEX.exists():
        return
    idx = json.loads(HK_INDEX.read_text(encoding="utf-8"))
    if ticker.upper() not in idx.get("tickers", {}):
        return
    subprocess.run(
        [PY, str(SCRIPTS / "scan_hk_sources.py"), ticker, "--date", out_date, "--write-references"],
        cwd=ROOT,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan all third-party sources for ticker(s)")
    parser.add_argument("tickers", nargs="*", help="Ticker symbol(s)")
    parser.add_argument("--all", action="store_true", help="All holdings in registry.json")
    parser.add_argument("--date", default=date.today().isoformat(), help="Scan date YYYY-MM-DD")
    parser.add_argument("--with-hk", action="store_true", help="Also run scan_hk_sources.py when indexed")
    args = parser.parse_args()

    tickers = registry_tickers() if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        parser.error("Provide tickers or --all")

    for ticker in tickers:
        if args.with_hk:
            maybe_hk_scan(ticker, args.date)
        json_path, md_path = write_inventory(ticker, args.date)
        n = json.loads(json_path.read_text())["source_count"]
        print(f"OK {ticker}: {n} sources -> {md_path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
