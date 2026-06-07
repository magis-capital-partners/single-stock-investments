#!/usr/bin/env python3
"""Live monthly nowcast for 7176.T current-period revenue / earnings.

Re-run anytime: it pulls fresh market data, takes the latest disclosed AUM as the
anchor, marks AUM to market for the elapsed part of the current fiscal half, and
applies the fitted base-fee rate + crystallization-weighted perf-fee coefficient.

Uses P0-P3 data when available:
  - ETF AUM from etf_aum_daily.csv (NAV x shares, summed)
  - ETF implied flows from etf_flows_daily.csv
  - v2 perf driver (fund proxy or 0.65*Nikkei + 0.35*value factor)

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
DATA = OUT / "data"


def load_params():
    res = json.loads((OUT / "model_results.json").read_text())
    rate = res["base_fee_model"]["base_rate_ann_est_pct"] / 100.0
    kH1 = res["perf_fee_model"]["k_H1"]
    kH2 = res["perf_fee_model"]["k_H2"]
    v2 = res.get("perf_fee_model_v2", {})
    kH1_v2 = v2.get("k_H1")
    kH2_v2 = v2.get("k_H2")
    v5 = res.get("perf_fee_model_v5", {})
    k_scale_v5 = v5.get("k_scale", 1.0)
    split_rates = v5.get("split_base_rates", {})
    bridge = res["earnings_bridge"]
    production_spec = res.get("production_spec", "v1")
    aum0 = res["latest_anchor"]["aum_end_jpym"]
    anchor_date = res["latest_anchor"]["period_end"]
    return rate, {"H1": kH1, "H2": kH2}, {"H1": kH1_v2, "H2": kH2_v2}, bridge, aum0, anchor_date, production_spec, k_scale_v5, split_rates


def current_half(today: dt.date):
    if 4 <= today.month <= 9:
        return "H1", dt.date(today.year, 4, 1), dt.date(today.year, 9, 30)
    if today.month >= 10:
        return "H2", dt.date(today.year, 10, 1), dt.date(today.year + 1, 3, 31)
    return "H2", dt.date(today.year - 1, 10, 1), dt.date(today.year, 3, 31)


def market_returns(start: dt.date, end: dt.date) -> dict[str, float]:
    import yfinance as yf

    tickers = {"nikkei": "^N225", "value_pbr": "2080.T"}
    out = {}
    for name, tk in tickers.items():
        try:
            h = yf.Ticker(tk).history(
                start=str(start - dt.timedelta(days=10)),
                end=str(end + dt.timedelta(days=1)),
                auto_adjust=True,
            )
            if len(h) < 2:
                out[name] = 0.0
                continue
            h.index = pd.to_datetime(h.index).tz_localize(None)
            base = h[h.index < pd.Timestamp(start)]["Close"]
            start_px = base.iloc[-1] if len(base) else h["Close"].iloc[0]
            out[name] = float(h["Close"].iloc[-1] / start_px - 1.0)
        except Exception:
            out[name] = 0.0
    return out


def effective_excess(ret: dict[str, float]) -> float:
    nik = max(0.0, ret.get("nikkei", 0.0))
    val = ret.get("value_pbr", np.nan)
    if pd.notna(val):
        return 0.65 * nik + 0.35 * max(0.0, float(val))
    return nik


def etf_aum_now(asof: dt.date) -> tuple[float | None, str | None]:
    path = DATA / "etf_aum_daily.csv"
    if not path.exists():
        return None, None
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["date"] <= pd.Timestamp(asof)]
    if df.empty:
        return None, None
    latest = df["date"].max()
    snap = df[df["date"] == latest].dropna(subset=["aum_jpym"])
    if snap.empty:
        return None, None
    return float(snap["aum_jpym"].sum()), str(latest.date())


def etf_flows_ytd(hs: dt.date, asof: dt.date) -> float | None:
    path = DATA / "etf_flows_daily.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    win = df[(df["date"] >= pd.Timestamp(hs)) & (df["date"] <= pd.Timestamp(asof))]
    if win.empty:
        return None
    return float(win["flow_jpym"].sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", choices=["H1", "H2"], default=None)
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD override")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.asof) if args.asof else dt.date.today()
    half, hs, he = current_half(today)
    if args.half:
        half = args.half

    rate, ks, ks_v2, bridge, aum0, anchor_date, production_spec, k_scale_v5, split_rates = load_params()
    try:
        rets = market_returns(hs, min(today, he))
    except Exception as exc:
        print(f"[warn] market fetch failed ({exc}); using 0 return")
        rets = {"nikkei": 0.0, "value_pbr": 0.0}

    nik_ret = rets.get("nikkei", 0.0)
    excess_v2 = effective_excess(rets)

    etf_aum, etf_aum_date = etf_aum_now(today)
    flow_ytd = etf_flows_ytd(hs, today)

    panel = pd.read_csv(OUT / "panel_halfyear.csv", parse_dates=["period_end"])
    latest = panel.dropna(subset=["aum_end_jpym"]).iloc[-1]

    # AUM mark: filing anchor + market move + optional flow overlay
    if etf_aum is not None:
        # Scale non-ETF AUM by Nikkei; add live ETF AUM from registry tickers
        latest_etf = panel.dropna(subset=["aum_end_jpym", "aum_etf_jpym"]).iloc[-1]
        non_etf = float(latest_etf["aum_end_jpym"] - latest_etf["aum_etf_jpym"])
        avg_aum = non_etf * (1 + nik_ret / 2) + etf_aum
        aum_source = f"etf_nav_filing_anchor ({etf_aum_date}) + non-ETF MTM"
    else:
        avg_aum = aum0 * (1 + nik_ret / 2)
        aum_source = "filing anchor MTM [Assumption flat flows]"

    if flow_ytd is not None and pd.notna(flow_ytd):
        avg_aum += flow_ytd / 2.0  # spread YTD flow over half
        aum_source += f"; +ETF flow YTD ¥{flow_ytd:.0f}m"

    base_hat = rate / 2.0 * avg_aum
    if production_spec == "v5" and split_rates:
        nl = float(latest["aum_nonlisted_jpym"]) if pd.notna(latest.get("aum_nonlisted_jpym")) else avg_aum * 0.81
        etf = float(latest["aum_etf_jpym"]) if pd.notna(latest.get("aum_etf_jpym")) else avg_aum * 0.19
        base_hat = split_rates.get("rate_nonlisted_ann", rate) / 2 * nl + split_rates.get("rate_etf_ann", rate) / 2 * etf

    k = ks.get(half) or 0.0
    k_v2 = ks_v2.get(half) or k
    perf_hat = k * avg_aum * max(0.0, nik_ret)
    perf_hat_v2 = k_v2 * avg_aum * excess_v2
    other = 200.0
    rev_hat = base_hat + perf_hat + other
    rev_hat_v2 = base_hat + perf_hat_v2 + other
    slope = bridge.get("ord_slope_rev", bridge.get("ord_slope", 0.579))
    perf_slope = bridge.get("ord_slope_perf", 0.0)
    ordinary = bridge["ord_intercept"] + slope * rev_hat + perf_slope * perf_hat
    ni = ordinary * (1 - bridge["tax_rate"])
    ordinary_v2 = bridge["ord_intercept"] + slope * rev_hat_v2 + perf_slope * perf_hat_v2
    ni_v2 = ordinary_v2 * (1 - bridge["tax_rate"])

    out = dict(
        asof=str(today), fiscal_half=half, half_window=[str(hs), str(he)],
        aum_anchor_date=anchor_date, aum_anchor_jpym=aum0,
        aum_nowcast_jpym=round(avg_aum), aum_source=aum_source,
        nikkei_return_to_date=round(nik_ret, 4),
        effective_excess_ret_v2=round(excess_v2, 4),
        etf_flow_ytd_jpym=None if flow_ytd is None else round(flow_ytd),
        nowcast_jpym=dict(
            base_fee=round(base_hat), perf_fee=round(perf_hat),
            revenue=round(rev_hat), ordinary_profit=round(ordinary),
            net_income=round(ni),
        ),
        production_spec=production_spec,
        nowcast_v2_jpym=dict(
            perf_fee=round(perf_hat_v2), revenue=round(rev_hat_v2),
            ordinary_profit=round(ordinary_v2), net_income=round(ni_v2),
        ),
        nowcast_v5_jpym=dict(
            k_scale=k_scale_v5,
            note="Live v5 uses v1 perf proxy until mandate detail refreshed for current half",
        ),
        caveats=[
            "Perf fee crystallizes near fiscal year-end (Mar); H1 nowcast of perf is low-confidence.",
            "v2 uses fund-proxy excess when panel has it; live nowcast uses 0.65*Nikkei + 0.35*value.",
            "JITA industry flows pending; ETF implied flows are [Derived] proxy only.",
        ],
    )
    (OUT / "nowcast_latest.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
