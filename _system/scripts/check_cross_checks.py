#!/usr/bin/env python3
"""Verify every universe ticker has a third-party cross-check covering indexed sources.

Usage:
  python _system/scripts/check_cross_checks.py
  python _system/scripts/check_cross_checks.py GOOGL APLD
  python _system/scripts/check_cross_checks.py --strict
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry
from third_party_inventory import load_latest_inventory, write_inventory
from scaffold_cross_check import STUB_MARKER, existing_cross_check

MIN_CROSS_CHECK_BYTES = 400


def registry_tickers() -> list[str]:
    reg = load_registry()
    holdings = reg.get("holdings", {})
    if isinstance(holdings, dict):
        return sorted(holdings.keys())
    return sorted({h["ticker"] for h in holdings})


def source_covered(text: str, path: str, source_id: str = "") -> bool:
    if not path:
        return True
    base = Path(path).name
    if source_id in ("ssi", "lci") and ("Substacks" in text or source_id in text or "Lemon Cakes" in text):
        return True
    return path in text or base in text


def check_ticker(ticker: str, *, strict: bool) -> list[str]:
    errors: list[str] = []
    cc = existing_cross_check(ticker)
    if not cc or not cc.exists():
        errors.append(f"{ticker}: missing research/cross_check*.md — run scaffold_cross_check.py")
        return errors
    if cc.stat().st_size < MIN_CROSS_CHECK_BYTES:
        errors.append(f"{ticker}: cross-check too short: {cc.relative_to(ROOT)}")

    text = cc.read_text(encoding="utf-8", errors="ignore")
    if strict and STUB_MARKER in text and "*[Complete after" in text:
        errors.append(f"{ticker}: cross-check still stub — complete synthesis in {cc.name}")

    inv = load_latest_inventory(ticker)
    if not inv:
        write_inventory(ticker)
        inv = load_latest_inventory(ticker)
    if not inv:
        return errors

    tp = ROOT / ticker / "third-party-analyses"
    if not list(tp.glob("source_inventory_*.md")):
        errors.append(f"{ticker}: missing source_inventory_*.md — run scan_third_party_sources.py")

    for s in inv.get("sources", []):
        if s.get("status") == "approved" and not source_covered(
            text, s.get("path", ""), s.get("source_id", "")
        ):
            errors.append(f"{ticker}: approved source not cited in cross-check: {s.get('path', '')}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify third-party cross-checks for universe")
    parser.add_argument("tickers", nargs="*", help="Optional subset; default all registry holdings")
    parser.add_argument("--strict", action="store_true", help="Fail if cross-check is still scaffold stub")
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers] if args.tickers else registry_tickers()
    all_errors: list[str] = []
    for ticker in tickers:
        all_errors.extend(check_ticker(ticker, strict=args.strict))

    if all_errors:
        for e in all_errors:
            print(f"FAIL {e}")
        return 1

    print(f"OK: cross-checks verified for {len(tickers)} ticker(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
