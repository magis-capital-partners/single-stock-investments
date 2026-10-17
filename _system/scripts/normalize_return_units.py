#!/usr/bin/env python3
"""Normalize return units and canonical returns blocks across valuation/cards.

Legacy fields already store percent (``display: "0.12%"`` proves sub-1 values
are percent, not fractions). This migration makes the unit explicit and adds
one canonical ``returns`` block so agents never rescale or guess:

  thesis_card.json -> schema_version 2.0, base_irr_unit, returns{...}
  valuation.json   -> schema_version magis.valuation.v2, returns{...}

Idempotent via ``atomic_io``; safe to run in CI refresh pipelines.

Usage:
  python _system/scripts/normalize_return_units.py --all
  python _system/scripts/normalize_return_units.py GOOGL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import RETURN_UNIT, canonical_returns  # noqa: E402
from atomic_io import write_json_if_changed  # noqa: E402


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_ticker(ticker: str, *, root: Path = ROOT) -> dict[str, bool]:
    research = root / ticker / "research"
    valuation_path = research / "valuation.json"
    card_path = research / "thesis_card.json"
    valuation = _load(valuation_path)
    card = _load(card_path)
    changed = {"valuation": False, "thesis_card": False}
    if not valuation and not card:
        return changed

    returns = canonical_returns(valuation, card)

    if valuation:
        updated = dict(valuation)
        updated["schema_version"] = "magis.valuation.v2"
        updated["returns"] = returns
        # Stable-first ordering: volatile generated stamps stay in legacy spots;
        # canonical blocks are inserted deterministically at write time by key reuse.
        changed["valuation"] = write_json_if_changed(valuation_path, updated)

    if card:
        updated_card = dict(card)
        updated_card["schema_version"] = "2.0"
        if isinstance(returns.get("base_irr_pct"), (int, float)):
            updated_card["base_irr_pct"] = returns["base_irr_pct"]
        updated_card["base_irr_unit"] = RETURN_UNIT
        updated_card["returns"] = returns
        # Canonical digest wins over any dated pointer.
        canonical_digest = research / "evidence" / "filing_digest.md"
        if canonical_digest.is_file():
            updated_card["filing_digest"] = canonical_digest.relative_to(root).as_posix()
        changed["thesis_card"] = write_json_if_changed(card_path, updated_card)
    return changed


def ticker_dirs(root: Path = ROOT) -> list[str]:
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "_"))
        and entry.name not in ("dashboard", "docs", "tmp", "terminals")
        and (entry / "research").is_dir()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    targets = ticker_dirs() if args.all or not args.tickers else [t.upper() for t in args.tickers]
    v_changed = c_changed = 0
    for ticker in targets:
        result = normalize_ticker(ticker)
        v_changed += int(result["valuation"])
        c_changed += int(result["thesis_card"])
    print(f"OK normalize returns: tickers={len(targets)} valuation_written={v_changed} cards_written={c_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
