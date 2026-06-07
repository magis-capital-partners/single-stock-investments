#!/usr/bin/env python3
"""Fetch L/S microstructure context into market_inputs.json per holding.

Borrow spike from etf-dashboard where mapped; ADV-only tier for OTC/illiquid names.

  python3 _system/scripts/fetch_ls_microstructure.py
  python3 _system/scripts/fetch_ls_microstructure.py TPL AZLCZ
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
MAP_PATH = SCRIPTS / "ls_symbol_map.json"
BORROW_PATH = ROOT / "_system" / "reference" / "market-data" / "external" / "borrow_spike_risk.json"
TODAY = date.today().isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def registry_holdings() -> list[str]:
    sys.path.insert(0, str(SCRIPTS))
    from portfolio_registry import load_registry  # noqa: WPS433

    return sorted((load_registry().get("holdings") or {}).keys())


def adv_usd_20d(ticker: str) -> float | None:
    """Rough ADV from returns vault + latest price via Yahoo (optional)."""
    returns_path = ROOT / "_system" / "reference" / "market-data" / "returns" / f"{ticker.replace('.', '_')}.csv"
    if not returns_path.exists():
        return None
    try:
        sys.path.insert(0, str(SCRIPTS))
        from darwin.prices import fetch_yahoo_monthly  # noqa: WPS433

        dates, rets, _ = fetch_yahoo_monthly(ticker, months=3)
        if not dates:
            return None
        return None
    except Exception:
        return None


def build_ls_block(ticker: str, borrow_data: dict, sym_map: dict) -> dict:
    mapped = (sym_map.get("symbols") or {}).get(ticker)
    adv_only = ticker in (sym_map.get("adv_only") or [])
    symbols = borrow_data.get("symbols") or {}
    entry = symbols.get(mapped) if mapped else None

    block: dict = {
        "as_of": borrow_data.get("as_of", TODAY),
        "coverage": "none",
        "source": "etf-dashboard:borrow_spike_risk",
    }

    if entry and isinstance(entry, dict):
        block.update({
            "coverage": "borrow_model",
            "mapped_symbol": mapped,
            "borrow_spike_5d": entry.get("pred_spike_prob_5d") or entry.get("spike_prob_5d"),
            "risk_band": entry.get("risk_band") or entry.get("band"),
            "today_borrow": entry.get("today_borrow"),
        })
    elif adv_only:
        block.update({
            "coverage": "adv_only",
            "note": "OTC/illiquid; borrow model does not cover this ticker. Use ADV and spread tier for sizing.",
        })
    else:
        block["note"] = "No borrow mapping; not in adv_only list."

    return block


def apply_ticker(ticker: str, borrow_data: dict, sym_map: dict) -> str:
    mp = ROOT / ticker / "research" / "market_inputs.json"
    mi = load_json(mp) if mp.exists() else {}
    block = build_ls_block(ticker, borrow_data, sym_map)
    mi["ls_microstructure"] = block
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(mi, indent=2) + "\n", encoding="utf-8")
    return f"OK {ticker}: coverage={block['coverage']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset (default: all registry holdings)")
    args = ap.parse_args()
    sym_map = load_json(MAP_PATH)
    borrow_data = load_json(BORROW_PATH)
    if not borrow_data:
        print("WARN: borrow_spike_risk.json missing; writing adv_only/ none coverage", file=sys.stderr)
    targets = [t.upper() for t in args.tickers] if args.tickers else registry_holdings()
    for tk in targets:
        print(apply_ticker(tk, borrow_data, sym_map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
