#!/usr/bin/env python3
"""Run the separation flow model for every active register record.

Appends one point-in-time row per (separation, side) per run date to
``separation_flows.jsonl``.  A re-run on the same day is a no-op (first
write wins).  Market inputs come from the same loaders the index model uses;
missing inputs produce ``n_a`` legs, never invented numbers.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_flow_impact import load_aum_registry, load_rules  # noqa: E402
from index_market_inputs import load_fundamentals_cache, market_inputs_for_ticker  # noqa: E402
from separation_common import (  # noqa: E402
    FLOWS_PATH,
    ROOT,
    SEPARATION_DIR,
    finite,
    read_json,
    append_jsonl,
    latest_registry,
    load_jsonl,
)
from separation_flow_impact import compute_separation_flow  # noqa: E402

INDEX_MEMBERSHIP_PATH = ROOT / "dashboard" / "data" / "index_membership.json"
SEED_PATH = ROOT / "_system" / "data" / "index_memberships_seed.json"
CONSTITUENT_DIR = ROOT / "_system" / "reference" / "market-data" / "index"
CONSTITUENT_FILES = {
    "sp500": "sp500_constituents.json",
    "nasdaq_100": "nasdaq100_constituents.json",
    "ftse_100": "ftse100_constituents.json",
    "tsx_composite": "tsx_composite_constituents.json",
}
_CONSTITUENTS: dict[str, set[str]] | None = None


def _constituents() -> dict[str, set[str]]:
    global _CONSTITUENTS
    if _CONSTITUENTS is None:
        out: dict[str, set[str]] = {}
        for index_id, name in CONSTITUENT_FILES.items():
            path = CONSTITUENT_DIR / name
            if not path.exists():
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            tickers = doc.get("tickers") if isinstance(doc, dict) else doc
            out[index_id] = {str(t).upper() for t in (tickers or [])}
        _CONSTITUENTS = out
    return _CONSTITUENTS


def _registry_meta() -> dict[str, dict]:
    path = ROOT / "_system" / "portfolio" / "registry.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("holdings") or {}


def parent_memberships(ticker: str) -> list[str]:
    """Current index memberships from the committed index payload, then the seed."""
    if INDEX_MEMBERSHIP_PATH.exists():
        try:
            doc = json.loads(INDEX_MEMBERSHIP_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = {}
        entry = (doc.get("by_ticker") or {}).get(ticker) or {}
        mems = entry.get("current_memberships") or []
        if mems:
            return [str(m) for m in mems]
    if SEED_PATH.exists():
        try:
            seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            seed = {}
        entry = (seed.get("by_ticker") or {}).get(ticker) or {}
        mems = entry.get("memberships") or [] if isinstance(entry, dict) else []
        if mems:
            return [str(m) for m in mems]
    # Dated provider constituent lists (harvest_index_constituents.py inputs).
    return sorted(index_id for index_id, members in _constituents().items() if ticker.upper() in members)


MARKET_PATH = SEPARATION_DIR / "separation_market.json"


def market_inputs(ticker: str | None, *, holdings: dict, cache: dict, market: dict | None = None) -> dict:
    """Offline index inputs, then the separations delayed-quote file for price and ADV."""
    if not ticker:
        return {}
    meta = holdings.get(ticker) or {}
    try:
        mi = market_inputs_for_ticker(ticker, holdings_meta=meta, fundamentals_cache=cache) or {}
    except Exception:  # noqa: BLE001 - a bad per-ticker file must not stop the batch
        mi = {}
    quote = ((market or {}).get("quotes") or {}).get(ticker) or {}
    if finite(mi.get("price")) is None and finite(quote.get("close")) is not None:
        mi["price"] = float(quote["close"])
    if finite(mi.get("adv_shares")) is None and finite(quote.get("avg_volume_10d")) is not None:
        mi["adv_shares"] = float(quote["avg_volume_10d"])
    return mi


def build_rows(*, today: date, include_closed: bool = False) -> list[dict]:
    registry = load_aum_registry()
    rules = load_rules()
    holdings = _registry_meta()
    cache = load_fundamentals_cache()
    market = read_json(MARKET_PATH, {}) or {}
    rows: list[dict] = []
    for rec in latest_registry():
        if rec.get("lifecycle") == "closed" and not include_closed:
            continue
        parent = rec.get("parent_ticker")
        spinco = rec.get("spinco_ticker")
        p_mi = market_inputs(parent, holdings=holdings, cache=cache, market=market)
        s_mi = market_inputs(spinco, holdings=holdings, cache=cache, market=market)
        mems = parent_memberships(parent) if parent else []
        for side in ("parent", "spinco"):
            if side == "spinco" and not spinco and not rec.get("spinco_name"):
                continue
            rows.append(
                compute_separation_flow(
                    rec, side=side, spinco_mi=s_mi, parent_mi=p_mi, parent_memberships=mems,
                    registry=registry, rules=rules, today=today, run_date=today.isoformat(),
                )
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-closed", action="store_true", help="also model closed separations (backfill)")
    parser.add_argument("--as-of", default=None, help="run date YYYY-MM-DD (default today)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_day = date.fromisoformat(args.as_of) if args.as_of else date.today()
    rows = build_rows(today=run_day, include_closed=args.include_closed)
    if args.dry_run:
        print(json.dumps(rows, indent=1)[:4000])
        return 0
    added = append_jsonl(FLOWS_PATH, rows, identity_key="flow_id")
    ok = sum(1 for r in rows if r.get("status") == "ok")
    print(f"separation flows: modelled={len(rows)} ok={ok} appended={added} total_rows={len(load_jsonl(FLOWS_PATH))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
