#!/usr/bin/env python3
"""Determinism lint — re-run persona_lens and diff lenses.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from persona_lens_common import build_lenses_for_ticker, build_universe_stats, stable_json  # noqa: E402


def lint_ticker(ticker: str, stats: dict) -> list[str]:
    path = ROOT / ticker / "research" / "lenses.json"
    if not path.exists():
        return [f"{ticker}: missing lenses.json"]
    existing = path.read_text(encoding="utf-8")
    rebuilt = build_lenses_for_ticker(ticker, stats)
    if rebuilt is None:
        return [f"{ticker}: cannot rebuild"]
    new_text = stable_json(rebuilt)
    if existing != new_text:
        return [f"{ticker}: lenses.json not deterministic (re-run persona_lens.py)"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", help="Single ticker or omit for portfolio")
    parser.add_argument("--portfolio", action="store_true")
    args = parser.parse_args()

    stats = build_universe_stats()
    tickers: list[str] = []
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.portfolio:
        for p in ROOT.iterdir():
            if p.is_dir() and (p / "research" / "lenses.json").exists():
                tickers.append(p.name)
        tickers.sort()
    else:
        parser.error("Provide TICKER or --portfolio")

    errors: list[str] = []
    for t in tickers:
        errors.extend(lint_ticker(t, stats))

    if errors:
        for e in errors:
            print(f"FAIL {e}")
        return 1
    print(f"OK persona lens determinism ({len(tickers)} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
