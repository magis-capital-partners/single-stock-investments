#!/usr/bin/env python3
"""Upgrade Phase-3 scaffold valuations via proof-first automation.

Only touches tickers whose component_valuation schedule is entirely Phase-3
provisional scaffolds — never overwrites carefully built multi-component maps.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automate_valuation_readiness as automation  # noqa: E402


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def is_pure_scaffold(ticker: str) -> bool:
    valuation = read_json(ROOT / ticker / "research" / "valuation.json")
    comps = (valuation.get("component_valuation") or {}).get("components") or []
    if not comps:
        return False
    flags = []
    for row in comps:
        val = row.get("valuation") or {}
        text = f"{val.get('assumption_summary') or ''}{val.get('evidence') or ''}"
        flags.append("Phase 3" in text or "provisional valuation range" in text)
    return bool(flags) and all(flags)


def discover(explicit: list[str] | None) -> list[str]:
    if explicit:
        return [t.upper() for t in explicit]
    tickers = []
    for path in sorted(ROOT.glob("*/research/valuation.json")):
        ticker = path.parts[-3]
        if ticker.startswith(("_", ".")):
            continue
        contract = read_json(ROOT / ticker / "research" / "valuation_contract.json")
        if contract.get("status") != "evidence_blocked":
            continue
        if is_pure_scaffold(ticker):
            tickers.append(ticker)
    return tickers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", type=str.upper)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--collect", action="store_true", help="Download filings / companyfacts first")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tickers = discover(args.tickers)
    print(json.dumps({"candidate_count": len(tickers), "tickers": tickers}, indent=2))
    if args.dry_run or not tickers:
        return 0
    results = []
    failures = []
    for ticker in tickers:
        if not is_pure_scaffold(ticker) and args.tickers:
            # Explicit override still allowed, but warn.
            print(f"WARN {ticker}: not a pure Phase-3 scaffold; running anyway because --tickers was set")
        try:
            result = automation.run_ticker(ticker, args.date, args.collect, full_rerun=True)
        except Exception as exc:
            result = {"ticker": ticker, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            failures.append(ticker)
        results.append(result)
        print(json.dumps(result))
    grade = sum(1 for row in results if row.get("status") == "decision_grade")
    print(json.dumps({"upgraded": len(results), "decision_grade": grade, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
