#!/usr/bin/env python3
"""Build persona lenses for one or all tickers (deterministic)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from persona_lens_common import (  # noqa: E402
    UNIVERSE_STATS_PATH,
    build_lenses_for_ticker,
    build_universe_stats,
    list_tickers_with_valuation,
    stable_json,
)

from persona_consensus import apply_lens_consensus_to_valuation  # noqa: E402


def write_universe_stats() -> dict:
    stats = build_universe_stats()
    UNIVERSE_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_STATS_PATH.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return stats


def process_ticker(ticker: str, stats: dict, *, write_valuation: bool = True) -> dict | None:
    payload = build_lenses_for_ticker(ticker, stats)
    if not payload:
        return None
    out = ROOT / ticker / "research" / "lenses.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(stable_json(payload), encoding="utf-8")
    if write_valuation:
        apply_lens_consensus_to_valuation(ticker, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build persona lenses from valuation.json")
    parser.add_argument("ticker", nargs="?", help="Ticker symbol (omit for --all)")
    parser.add_argument("--all", action="store_true", help="Process all tickers with valuation.json")
    parser.add_argument("--skip-valuation", action="store_true", help="Do not patch valuation.json")
    args = parser.parse_args()

    stats = write_universe_stats()
    tickers: list[str]
    if args.all:
        tickers = list_tickers_with_valuation()
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        parser.error("Provide TICKER or --all")

    n = 0
    for t in tickers:
        result = process_ticker(t, stats, write_valuation=not args.skip_valuation)
        if result:
            n += 1
            print(f"OK {t} lenses.json ({len(result['lenses'])} personas, blend={result['valuation_blend'].get('blended_return_pct')})")
        else:
            print(f"SKIP {t} (no valuation.json)")

    print(f"Wrote {n}/{len(tickers)} lenses.json; universe stats -> {UNIVERSE_STATS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
