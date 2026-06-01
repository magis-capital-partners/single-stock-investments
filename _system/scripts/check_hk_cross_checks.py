#!/usr/bin/env python3
"""Verify HK-indexed tickers have hk_scan and cross_check files.

Usage:
  python _system/scripts/check_hk_cross_checks.py
  python _system/scripts/check_hk_cross_checks.py TPL MSB
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "_system" / "reference" / "investment-wisdom" / "hk_ticker_index.json"


def check_ticker(ticker: str, entry: dict) -> list[str]:
    errors: list[str] = []
    tp = ROOT / ticker / "third-party-analyses"
    scans = list(tp.glob("hk_scan_*.md")) if tp.is_dir() else []
    if not scans:
        errors.append(f"{ticker}: missing third-party-analyses/hk_scan_*.md — run scan_hk_sources.py")

    cc = entry.get("cross_check")
    if not cc:
        errors.append(f"{ticker}: no cross_check path in hk_ticker_index.json")
    else:
        cc_path = ROOT / cc
        if not cc_path.exists():
            errors.append(f"{ticker}: cross_check missing: {cc}")
        elif cc_path.stat().st_size < 500:
            errors.append(f"{ticker}: cross_check too short (stub?): {cc}")

    research = ROOT / ticker / "research"
    local = sorted(research.glob("cross_check*.md")) if research.is_dir() else []
    if not local and not (cc and (ROOT / cc).exists()):
        errors.append(f"{ticker}: no cross_check_*.md in research/")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HK cross-checks for indexed tickers")
    parser.add_argument("tickers", nargs="*", help="Optional subset; default all indexed")
    args = parser.parse_args()

    if not INDEX.exists():
        print(f"ERROR: missing {INDEX}")
        return 1

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    tickers = args.tickers or sorted(data.get("tickers", {}).keys())
    tickers = [t.upper() for t in tickers]

    all_errors: list[str] = []
    for ticker in tickers:
        entry = data.get("tickers", {}).get(ticker)
        if not entry:
            all_errors.append(f"{ticker}: not in hk_ticker_index.json")
            continue
        all_errors.extend(check_ticker(ticker, entry))

    if all_errors:
        for e in all_errors:
            print(f"FAIL {e}")
        return 1

    print(f"OK: HK cross-checks verified for {', '.join(tickers)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
