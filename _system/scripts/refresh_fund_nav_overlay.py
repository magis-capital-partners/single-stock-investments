#!/usr/bin/env python3
"""Recompute fund_nav_overlay discount fields from price + reported NAV inputs.

Does not invent recovery probabilities for zero-marked sleeves.
Usage:
  python _system/scripts/refresh_fund_nav_overlay.py CEE
  python _system/scripts/refresh_fund_nav_overlay.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pct_discount(price: float | None, nav: float | None) -> float | None:
    if price is None or nav is None or nav == 0:
        return None
    return round((price / nav - 1.0) * 100.0, 2)


def refresh_ticker(ticker: str, write: bool = True) -> dict | None:
    path = ROOT / ticker / "research" / "valuation.json"
    if not path.exists():
        print(f"{ticker}: no valuation.json", file=sys.stderr)
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    overlay = data.get("fund_nav_overlay")
    if not isinstance(overlay, dict):
        print(f"{ticker}: no fund_nav_overlay", file=sys.stderr)
        return None

    inputs = data.setdefault("inputs", {})
    price = overlay.get("market_price")
    if price is None:
        price = inputs.get("price")
    reported = overlay.get("reported_nav")
    liquid = overlay.get("liquid_nav_per_share")
    complete = overlay.get("complete_nav_per_share_base")

    overlay["discount_to_reported_nav_pct"] = _pct_discount(
        float(price) if price is not None else None,
        float(reported) if reported is not None else None,
    )
    overlay["discount_to_liquid_nav_pct"] = _pct_discount(
        float(price) if price is not None else None,
        float(liquid) if liquid is not None else None,
    )
    overlay["discount_to_complete_nav_pct"] = _pct_discount(
        float(price) if price is not None else None,
        float(complete) if complete is not None else None,
    )
    if price is not None:
        inputs["price"] = price
    overlay["refreshed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["fund_nav_overlay"] = overlay

    if write:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"{ticker}: price={price} reported_nav={reported} "
        f"disc_reported={overlay.get('discount_to_reported_nav_pct')}% "
        f"edge={overlay.get('edge')}"
    )
    return overlay


def iter_fund_tickers() -> list[str]:
    sleeves = ROOT / "_system" / "portfolio" / "investment_sleeves.json"
    if sleeves.exists():
        doc = json.loads(sleeves.read_text(encoding="utf-8"))
        meta = (doc.get("sleeves") or {}).get("fund_nav_discounts") or {}
        return [str(t) for t in meta.get("tickers") or []]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="*", help="Tickers with fund_nav_overlay")
    ap.add_argument("--all", action="store_true", help="All fund_nav_discounts sleeve members")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tickers = list(args.tickers)
    if args.all or not tickers:
        tickers = iter_fund_tickers()
    if not tickers:
        print("No fund tickers", file=sys.stderr)
        return 1
    ok = 0
    for t in tickers:
        if refresh_ticker(t, write=not args.dry_run):
            ok += 1
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
