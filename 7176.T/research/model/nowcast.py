#!/usr/bin/env python3
"""Live monthly nowcast for 7176.T current-period revenue / earnings.

Re-run anytime: it pulls fresh market data, takes the latest disclosed AUM as the
anchor, marks AUM to market for the elapsed part of the current fiscal half, and
applies the fitted base-fee rate + crystallization-weighted perf-fee coefficient.

This is the piece a naive benchmark CANNOT do: it produces a number BEFORE the
company reports, updated as markets move.

Usage:
  python3 nowcast.py [--half H1|H2]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent


def load_params():
    res = json.loads((OUT / "model_results.json").read_text())
    rate = res["base_fee_model"]["base_rate_ann_est_pct"] / 100.0
    kH1 = res["perf_fee_model"]["k_H1"]
    kH2 = res["perf_fee_model"]["k_H2"]
    bridge = res["earnings_bridge"]
    aum0 = res["latest_anchor"]["aum_end_jpym"]
    anchor_date = res["latest_anchor"]["period_end"]
    return rate, {"H1": kH1, "H2": kH2}, bridge, aum0, anchor_date


def current_half(today: dt.date):
    if 4 <= today.month <= 9:
        return "H1", dt.date(today.year, 4, 1), dt.date(today.year, 9, 30)
    if today.month >= 10:
        return "H2", dt.date(today.year, 10, 1), dt.date(today.year + 1, 3, 31)
    return "H2", dt.date(today.year - 1, 10, 1), dt.date(today.year, 3, 31)


def market_return(start: dt.date, end: dt.date) -> float:
    import yfinance as yf

    h = yf.Ticker("^N225").history(start=str(start - dt.timedelta(days=10)),
                                   end=str(end + dt.timedelta(days=1)), auto_adjust=True)
    if len(h) < 2:
        return 0.0
    h.index = pd.to_datetime(h.index).tz_localize(None)
    base = h[h.index < pd.Timestamp(start)]["Close"]
    start_px = base.iloc[-1] if len(base) else h["Close"].iloc[0]
    return float(h["Close"].iloc[-1] / start_px - 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", choices=["H1", "H2"], default=None)
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD override")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.asof) if args.asof else dt.date.today()
    half, hs, he = current_half(today)
    if args.half:
        half = args.half

    rate, ks, bridge, aum0, anchor_date = load_params()
    try:
        ret_to_date = market_return(hs, min(today, he))
    except Exception as exc:
        print(f"[warn] market fetch failed ({exc}); using 0 return")
        ret_to_date = 0.0

    # mark AUM to market over elapsed portion; assume flat net flows [Assumption]
    avg_aum = aum0 * (1 + ret_to_date / 2)
    base_hat = rate / 2.0 * avg_aum
    k = ks.get(half) or 0.0
    perf_hat = k * avg_aum * max(0.0, ret_to_date)
    other = 200.0
    rev_hat = base_hat + perf_hat + other
    ordinary = bridge["ord_intercept"] + bridge["ord_slope"] * rev_hat
    ni = ordinary * (1 - bridge["tax_rate"])

    out = dict(
        asof=str(today), fiscal_half=half, half_window=[str(hs), str(he)],
        aum_anchor_date=anchor_date, aum_anchor_jpym=aum0,
        nikkei_return_to_date=round(ret_to_date, 4),
        nowcast_jpym=dict(
            base_fee=round(base_hat), perf_fee=round(perf_hat),
            revenue=round(rev_hat), ordinary_profit=round(ordinary),
            net_income=round(ni),
        ),
        caveats=[
            "Perf fee crystallizes near fiscal year-end (Mar); H1 nowcast of perf is low-confidence.",
            "Assumes flat net flows; replace with per-ETF NAV*units + JITA flows for real edge.",
            "Single-driver (Nikkei); add value/PBR factor and fund-level NAV for precision.",
        ],
    )
    (OUT / "nowcast_latest.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
