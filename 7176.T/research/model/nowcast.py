#!/usr/bin/env python3
"""Live monthly nowcast for 7176.T current-period revenue / earnings.

Re-run anytime: it pulls fresh market data, takes the latest disclosed AUM as the
anchor, marks AUM to market for the elapsed part of the current fiscal half, and
applies the fitted base-fee rate + crystallization-weighted perf-fee coefficient.

Uses filing AUM sleeves (non-listed + listed ETF), not summed product-market AUM.

Usage:
  python3 nowcast.py [--half H1|H2] [--asof YYYY-MM-DD]
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


def _return_from_series(series: pd.Series, start: dt.date, end: dt.date) -> float | None:
    s = series.dropna()
    if s.empty:
        return None
    win = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    prev = s[s.index < pd.Timestamp(start)]
    if win.empty:
        return None
    start_px = float(prev.iloc[-1]) if len(prev) else float(win.iloc[0])
    end_px = float(win.iloc[-1])
    if start_px <= 0:
        return None
    return end_px / start_px - 1.0


def market_returns_cached(start: dt.date, end: dt.date) -> dict[str, float]:
    out: dict[str, float] = {}
    mm = OUT / "market_monthly.csv"
    if mm.exists():
        m = pd.read_csv(mm, index_col=0, parse_dates=True)
        if "nikkei" in m.columns:
            ret = _return_from_series(m["nikkei"], start, end)
            if ret is not None:
                out["nikkei"] = ret
    nav_path = DATA / "etf_nav_daily.csv"
    if nav_path.exists():
        nav = pd.read_csv(nav_path, parse_dates=["date"])
        for name, tk in [("value_pbr", "2080.T"), ("nikkei", "1321.T")]:
            if name in out and out[name] != 0.0:
                continue
            sub = nav.loc[nav["ticker"] == tk].set_index("date")["nav_jpy"].sort_index()
            ret = _return_from_series(sub, start, end)
            if ret is not None:
                out[name] = ret
    return out


def market_returns(start: dt.date, end: dt.date) -> tuple[dict[str, float], str]:
    import yfinance as yf

    tickers = {"nikkei": "^N225", "value_pbr": "2080.T"}
    out: dict[str, float] = {}
    live_ok = False
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
            live_ok = True
        except Exception:
            out[name] = 0.0
    if live_ok and any(abs(v) > 1e-6 for v in out.values()):
        return out, "yfinance_live"
    cached = market_returns_cached(start, end)
    if cached:
        print("[warn] yfinance empty; reusing cached market_monthly.csv / etf_nav_daily.csv")
        return cached, "cached_market_nav"
    return out, "fallback_zero"


def effective_excess(ret: dict[str, float]) -> float:
    nik = max(0.0, ret.get("nikkei", 0.0))
    val = ret.get("value_pbr", np.nan)
    if pd.notna(val):
        return 0.65 * nik + 0.35 * max(0.0, float(val))
    return nik


def filing_sleeves(panel: pd.DataFrame, aum0: float) -> tuple[float, float, float]:
    """Return (total, nonlisted_sleeve, etf_sleeve) in ¥m from latest filing row."""
    pref = panel.dropna(subset=["aum_end_jpym"])
    if not pref.empty:
        detailed = pref.dropna(subset=["aum_etf_jpym"])
        row = detailed.iloc[-1] if not detailed.empty else pref.iloc[-1]
        total = float(row["aum_end_jpym"])
        etf = float(row["aum_etf_jpym"]) if pd.notna(row.get("aum_etf_jpym")) else total * 0.19
        nl = float(row["aum_nonlisted_jpym"]) if pd.notna(row.get("aum_nonlisted_jpym")) else total - etf
        return total, nl, etf
    return aum0, aum0 * 0.81, aum0 * 0.19


def etf_basket_return(start: dt.date, end: dt.date) -> float:
    nav_path = DATA / "etf_nav_daily.csv"
    reg_path = OUT / "fund_registry.json"
    if not nav_path.exists() or not reg_path.exists():
        return 0.0
    registry = json.loads(reg_path.read_text())
    nav = pd.read_csv(nav_path, parse_dates=["date"])
    rets = []
    weights = []
    for etf in registry.get("etfs", []):
        tk = etf["ticker"]
        w = float(etf.get("weight", 0))
        sub = nav.loc[nav["ticker"] == tk].set_index("date")["nav_jpy"].sort_index()
        ret = _return_from_series(sub, start, end)
        if ret is not None and w > 0:
            rets.append(ret)
            weights.append(w)
    if not rets:
        return 0.0
    w = np.array(weights)
    w = w / w.sum()
    return float(np.dot(w, rets))


def company_etf_flows_ytd(hs: dt.date, asof: dt.date, aum0: float, etf_sleeve: float) -> float | None:
    path = DATA / "etf_flows_daily.csv"
    reg_path = OUT / "fund_registry.json"
    if not path.exists() or not reg_path.exists():
        return None
    registry = json.loads(reg_path.read_text())
    weights = {e["ticker"]: float(e.get("weight", 0)) for e in registry.get("etfs", [])}
    w_sum = sum(weights.values()) or 1.0
    df = pd.read_csv(path, parse_dates=["date"])
    win = df[(df["date"] >= pd.Timestamp(hs)) & (df["date"] <= pd.Timestamp(asof))]
    if win.empty:
        return None
    # Scale product-level flows to company ETF sleeve using registry weights.
    total = 0.0
    for tk, g in win.groupby("ticker"):
        w = weights.get(tk, 0.0) / w_sum
        total += float(g["flow_jpym"].sum()) * w
    cap = max(etf_sleeve, aum0 * 0.19) * 0.10
    if abs(total) > cap:
        print(f"[warn] ETF flow YTD ¥{total:.0f}m exceeds cap ¥{cap:.0f}m; skipping flow overlay")
        return None
    return total


def mark_aum_to_market(
    aum0: float,
    nl: float,
    etf: float,
    nik_ret: float,
    etf_ret: float,
    flow_ytd: float | None,
) -> tuple[float, str]:
    avg_aum = nl * (1 + nik_ret / 2) + etf * (1 + etf_ret / 2)
    source = "filing sleeves MTM (non-listed Nikkei + ETF basket)"
    if avg_aum > 2 * aum0 or avg_aum < 0.5 * aum0:
        print(f"[warn] sleeve MTM ¥{avg_aum:.0f}m outside [0.5×, 2×] anchor ¥{aum0:.0f}m; clamping")
        avg_aum = aum0 * (1 + nik_ret / 2)
        source = "filing anchor MTM [sanity clamp]"
    if flow_ytd is not None and pd.notna(flow_ytd):
        avg_aum += flow_ytd / 2.0
        source += f"; +company ETF flow YTD ¥{flow_ytd:.0f}m"
    return avg_aum, source


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
    rets, market_source = market_returns(hs, min(today, he))
    nik_ret = rets.get("nikkei", 0.0)
    etf_ret = etf_basket_return(hs, min(today, he))
    excess_v2 = effective_excess(rets)

    panel = pd.read_csv(OUT / "panel_halfyear.csv", parse_dates=["period_end"])
    latest = panel.dropna(subset=["aum_end_jpym"]).iloc[-1]
    _, nl, etf_sleeve = filing_sleeves(panel, aum0)
    flow_ytd = company_etf_flows_ytd(hs, today, aum0, etf_sleeve)
    avg_aum, aum_source = mark_aum_to_market(aum0, nl, etf_sleeve, nik_ret, etf_ret, flow_ytd)

    base_hat = rate / 2.0 * avg_aum
    if production_spec == "v5" and split_rates:
        nl_use = nl * (1 + nik_ret / 2)
        etf_use = etf_sleeve * (1 + etf_ret / 2)
        base_hat = (
            split_rates.get("rate_nonlisted_ann", rate) / 2 * nl_use
            + split_rates.get("rate_etf_ann", rate) / 2 * etf_use
        )

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

    caveats = [
        "Perf fee crystallizes near fiscal year-end (Mar); H1 nowcast of perf is low-confidence.",
        "v2 uses fund-proxy excess when panel has it; live nowcast uses 0.65*Nikkei + 0.35*value.",
        "AUM uses filing non-listed + ETF sleeves, not summed product-market AUM.",
    ]
    if market_source != "yfinance_live":
        caveats.append(f"Market return from {market_source}; verify before trading on nowcast.")
    if abs(nik_ret) < 1e-6:
        caveats.append("Nikkei return to date is ~0; check live market data availability.")

    out = dict(
        asof=str(today), fiscal_half=half, half_window=[str(hs), str(he)],
        aum_anchor_date=anchor_date, aum_anchor_jpym=aum0,
        aum_nonlisted_jpym=round(nl), aum_etf_sleeve_jpym=round(etf_sleeve),
        aum_nowcast_jpym=round(avg_aum), aum_source=aum_source,
        market_source=market_source,
        nikkei_return_to_date=round(nik_ret, 4),
        etf_basket_return_to_date=round(etf_ret, 4),
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
        caveats=caveats,
    )
    (OUT / "nowcast_latest.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
