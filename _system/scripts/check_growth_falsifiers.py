#!/usr/bin/env python3
"""Evaluate growth falsifiers against filing_facts and refresh valuation.json growth paths.

Usage:
  python3 _system/scripts/check_growth_falsifiers.py --ticker GOOGL
  python3 _system/scripts/check_growth_falsifiers.py --ticker TPL --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from growth_theory import enrich_growth_explanation, load_filing_facts  # noqa: E402
from marvin_valuation import compute_valuation, load_valuation, valuation_path_for_ticker  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Check growth falsifiers vs filings")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--write", action="store_true", help="Write valuation.json after recompute")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    path = valuation_path_for_ticker(ticker)
    data = load_valuation(path)
    facts = load_filing_facts(ticker)

    enrich_growth_explanation(data, facts)
    computed = compute_valuation(data)

    if args.write:
        path.write_text(json.dumps(computed, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")

    ge = computed.get("growth_explanation", {})
    ir = computed.get("implied_return", {})
    print(f"{ticker} growth_explanation.status: {ge.get('status')}")
    ti = ge.get("theory_implied") or {}
    fa = ge.get("falsifier_adjusted") or {}
    print(f"  theory_implied: Y1-5={ti.get('y1_5')} Y6-10={ti.get('y6_10')}")
    print(f"  falsifier_adjusted: Y1-5={fa.get('y1_5')} Y6-10={fa.get('y6_10')}")
    print(f"  triggered: {len(fa.get('triggered') or [])}")
    print(f"  primary IRR (falsifier-adjusted): {ir.get('base_pct')}%")
    print(f"  lawrence_legacy: {ir.get('lawrence_legacy_pct')}%")

    if args.json:
        print(json.dumps({"growth_explanation": ge, "implied_return": ir}, indent=2))


if __name__ == "__main__":
    main()
