#!/usr/bin/env python3
"""Build the 7176.T modeling panel.

Combines:
  (1) Hand-extracted financials from primary filings (発行者情報 / 中間発行者情報 /
      決算短信), each value traceable to a source PDF (see data_dictionary.md).
  (2) Market drivers from Yahoo Finance, aggregated to Japanese fiscal half-years.

Japanese fiscal year ends 31 March.
  H1 (interim, 中間) = Apr 1 .. Sep 30
  H2                 = Oct 1 .. Mar 31 (contains the year-end perf-fee crystallization)

Outputs:
  panel_halfyear.csv   one row per fiscal half (the primary modeling frame)
  panel_annual.csv     one row per fiscal year
  market_monthly.csv   raw monthly market series (audit trail)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# (1) FILING-EXTRACTED FINANCIALS  [Filing]
#     Units: JPY thousands for P&L, JPY 100m (億円) converted to JPY m for AUM.
#     period_end is the half-year end date. half in {H1,H2}. fy = fiscal year end year.
# ---------------------------------------------------------------------------

# Annual operating revenue / ordinary profit / parent NI (JPY thousands) [Filing]
ANNUAL = [
    # fy ending Mar, revenue, ordinary_profit, net_income_parent, opex_sga, op_profit, headcount
    (2021, 12_065_096, 6_382_772, 4_631_090, None,      None,      None),
    (2022,  7_829_178, 3_145_400, 2_303_815, None,      None,      47),
    (2023,  8_905_724, 4_162_993, 3_021_369, 4_811_000, 4_094_724, 49),
    (2024, 14_966_959, 8_809_777, 6_609_192, 6_293_000, 8_673_000, 51),
    (2025, 16_254_501, 9_448_599, 7_056_222, 6_916_000, 9_337_000, 55),
    (2026, 22_512_000, 13_970_000, 10_631_000, 8_542_000, 13_970_000, 55),
]

# Interim (H1, Sep) operating revenue / ordinary / interim NI (JPY thousands) [Filing]
H1 = [
    # fy ending Mar, h1_revenue, h1_ordinary, h1_net_income, h1_base_fee, h1_perf_fee, h1_headcount
    (2021, 3_074_713, 1_653_517, 1_178_219, None,      None,      None),
    (2022, 3_526_469, 1_958_008, 1_423_167, None,      None,      50),
    (2023, 3_319_298, 1_926_574, 1_358_671, None,      None,      49),
    (2024, 3_804_623, 2_488_758, 1_791_219, 2_872_000, 932_000,   49),
    (2025, 5_353_003, 3_810_200, 2_799_791, 3_266_000, 1_996_000, 51),
    (2026, 5_577_537, 3_974_829, 2_861_532, 3_711_000, 1_713_000, 58),
]

# AUM by period end — canonical dict lives in aum_sleeves.py (shared with acquire_data)
from aum_sleeves import AUM_BY_PERIOD as AUM  # noqa: E402

# Share count (issued, as filed) and split-adjusted to Nov-2025 units [Filing/Derived]
# Used for EPS; split-adjusted series lives in research/shares_outstanding_split_adjusted.json
SHARES_ADJ = {  # period_end : split-adjusted shares (Nov-2025 units)
    "2025-03-31": 27_120_000,   # approx post-cancellation, pre-split economic count
    "2026-03-31": 27_120_000,
}


def fy_half_end(fy: int, half: str) -> str:
    if half == "H1":
        return f"{fy-1}-09-30"
    return f"{fy}-03-31"


def build_financials() -> pd.DataFrame:
    rows = []
    ann = {r[0]: r for r in ANNUAL}
    h1 = {r[0]: r for r in H1}
    for fy in sorted(ann):
        a = ann[fy]
        h = h1.get(fy)
        # H1 row
        if h:
            rows.append(
                dict(
                    fy=fy, half="H1", period_end=fy_half_end(fy, "H1"),
                    revenue=h[1], ordinary=h[2], net_income=h[3],
                    base_fee=h[4], perf_fee=h[5], headcount=h[6],
                )
            )
        # H2 row = annual minus H1 (flows); profit similarly
        if h:
            rows.append(
                dict(
                    fy=fy, half="H2", period_end=fy_half_end(fy, "H2"),
                    revenue=a[1] - h[1],
                    ordinary=(a[2] - h[2]) if a[2] is not None else None,
                    net_income=(a[3] - h[3]) if a[3] is not None else None,
                    base_fee=None, perf_fee=None, headcount=a[6],
                )
            )
    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"])
    return df.sort_values("period_end").reset_index(drop=True)


def attach_aum(df: pd.DataFrame) -> pd.DataFrame:
    from aum_sleeves import resolve_aum_jpym

    aum_tot, aum_nl, aum_etf, aum_tags = [], [], [], []
    for pe in df["period_end"]:
        key = pe.strftime("%Y-%m-%d")
        t = AUM.get(key)
        if t:
            tot, nl, etf, tag = resolve_aum_jpym(key, t[0], t[1], t[2])
            aum_tot.append(tot)
            aum_nl.append(nl)
            aum_etf.append(etf)
            aum_tags.append(tag)
        else:
            aum_tot.append(np.nan)
            aum_nl.append(np.nan)
            aum_etf.append(np.nan)
            aum_tags.append("")
    df["aum_end_jpym"] = aum_tot
    df["aum_nonlisted_jpym"] = aum_nl
    df["aum_etf_jpym"] = aum_etf
    df["aum_sleeve_tag"] = aum_tags
    # average AUM over the half = mean(prior end, this end)
    df = df.sort_values("period_end").reset_index(drop=True)
    df["aum_avg_jpym"] = (df["aum_end_jpym"] + df["aum_end_jpym"].shift(1)) / 2.0
    return df


# ---------------------------------------------------------------------------
# (2) MARKET DRIVERS  [Market data]
# ---------------------------------------------------------------------------

def fetch_market() -> pd.DataFrame:
    import yfinance as yf

    tickers = {
        "nikkei": "^N225",
        "topix_etf": "1306.T",  # NOTE: ETF unit split ~2024 corrupts raw return; use Nikkei as primary
        "usdjpy": "JPY=X",
        "nk_lev": "1570.T",  # Nikkei leveraged ETF -> lev/inverse demand & vol proxy
    }
    frames = {}
    for name, tk in tickers.items():
        h = yf.Ticker(tk).history(start="2019-09-01", interval="1d", auto_adjust=True)
        if len(h):
            frames[name] = h["Close"].rename(name)
    if not frames:
        cache = OUT / "market_monthly.csv"
        if cache.exists():
            print("[warn] yfinance empty; reusing market_monthly.csv")
            m = pd.read_csv(cache, index_col=0, parse_dates=True)
            return m
        return pd.DataFrame()
    m = pd.concat(frames.values(), axis=1)
    m.index = pd.to_datetime(m.index).tz_localize(None)
    return m


def half_window(period_end: pd.Timestamp):
    """Return (start, end) covering the fiscal half that ends at period_end."""
    if period_end.month == 9:  # H1 Apr-Sep
        return pd.Timestamp(period_end.year, 4, 1), period_end
    # H2 Oct-Mar
    return pd.Timestamp(period_end.year - 1, 10, 1), period_end


def market_features(df: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    feats = []
    for pe in df["period_end"]:
        s, e = half_window(pe)
        win = m[(m.index >= s) & (m.index <= e)]
        prev = m[m.index < s]
        row = {}
        for col in ["nikkei", "topix_etf", "usdjpy", "nk_lev"]:
            if col in win and len(win[col].dropna()) > 1:
                start_px = prev[col].dropna().iloc[-1] if len(prev[col].dropna()) else win[col].dropna().iloc[0]
                end_px = win[col].dropna().iloc[-1]
                ret = end_px / start_px - 1.0
                daily = win[col].pct_change().dropna()
                vol = daily.std() * np.sqrt(252)
                row[f"{col}_ret"] = ret
                row[f"{col}_endlevel"] = end_px
                row[f"{col}_vol"] = vol
            else:
                row[f"{col}_ret"] = np.nan
                row[f"{col}_endlevel"] = np.nan
                row[f"{col}_vol"] = np.nan
        feats.append(row)
    fdf = pd.DataFrame(feats, index=df.index)
    return pd.concat([df, fdf], axis=1)


def merge_acquired(fin: pd.DataFrame) -> pd.DataFrame:
    """Merge P0-P3 outputs from acquire_data.py (if present)."""
    data_dir = OUT / "data"
    if not data_dir.exists():
        return fin
    fin = fin.copy()
    fin["period_key"] = fin["period_end"].dt.strftime("%Y-%m-%d")

    merges = [
        ("fund_nav_proxy_halfyear.csv", ["perf_eligible_excess_ret", "etf_perf_basket_ret", "value_factor_ret"]),
        ("factor_returns_halfyear.csv", ["value_pbr_ret", "growth_ret", "reit_ret", "leveraged_ret", "topix_ret", "value_factor_ret"]),
        ("fund_return_halfyear.csv", ["etf_basket_ret", "etf_perf_basket_ret", "etf_basket_vol"]),
        ("flows_halfyear.csv", ["etf_implied_flow_jpym", "jita_equity_flow_bn", "jita_etf_flow_bn"]),
        ("aum_pools_halfyear.csv", ["perf_eligible_aum_jpym", "nonlisted_share", "etf_share"]),
        ("comp_bridge_halfyear.csv", ["opex_sga_jpy_million", "incremental_margin"]),
        ("march_window_halfyear.csv", ["march_nikkei_ret", "march_value_ret", "march_blended_ret"]),
        ("mandate_nav_halfyear.csv", ["mandate_weighted_excess", "mandate_weighted_return", "mandate_count"]),
        ("aum_rollforward_halfyear.csv", ["aum_end_nowcast_jpym", "aum_avg_nowcast_jpym"]),
        ("perf_eligible_aum_halfyear.csv", ["perf_eligible_aum_jpym"]),
        ("other_revenue_halfyear.csv", ["other_revenue_jpym"]),
    ]
    for fname, cols in merges:
        path = data_dir / fname
        if not path.exists():
            continue
        extra = pd.read_csv(path)
        if "period_end" not in extra.columns:
            continue
        extra["period_key"] = pd.to_datetime(extra["period_end"]).dt.strftime("%Y-%m-%d")
        use_cols = ["period_key"] + [c for c in cols if c in extra.columns]
        fin = fin.merge(extra[use_cols], on="period_key", how="left", suffixes=("", "_dup"))
        for c in cols:
            dup = f"{c}_dup"
            if dup in fin.columns:
                fin[c] = fin[c].fillna(fin[dup])
                fin.drop(columns=[dup], inplace=True)
    fin.drop(columns=["period_key"], inplace=True, errors="ignore")
    return fin


def run_acquire() -> None:
    script = OUT / "acquire_data.py"
    if not script.exists():
        return
    import subprocess
    import sys

    subprocess.run([sys.executable, str(script)], cwd=str(OUT), check=False)


def main() -> None:
    from parse_aum_filings import apply_to_aum_sleeves, scan_evidence

    try:
        filing_df = scan_evidence()
        if not filing_df.empty:
            OUT = Path(__file__).resolve().parent / "data" / "aum_filings_parsed.csv"
            OUT.parent.mkdir(parents=True, exist_ok=True)
            filing_df.to_csv(OUT, index=False)
            apply_to_aum_sleeves(filing_df)
    except Exception as exc:
        print(f"[warn] AUM filing parse skipped: {exc}")

    run_acquire()
    fin = build_financials()
    fin = attach_aum(fin)
    try:
        m = fetch_market()
        m.to_csv(OUT / "market_monthly.csv")
        fin = market_features(fin, m)
    except Exception as exc:  # offline fallback
        print(f"[warn] market fetch failed ({exc}); writing financial panel only")

    fin = merge_acquired(fin)

    # convenience derived fields
    fin["is_h2"] = (fin["half"] == "H2").astype(int)
    # base_fee is JPY thousands, aum_avg JPY millions -> divide base_fee by 1000 first
    fin["base_fee_rate_ann"] = np.where(
        fin["base_fee"].notna() & fin["aum_avg_jpym"].notna(),
        (fin["base_fee"] / 1000.0) / fin["aum_avg_jpym"] * 2.0,  # semiannual -> annualized
        np.nan,
    )
    fin["opmargin"] = np.where(fin["revenue"] > 0, fin["ordinary"] / fin["revenue"], np.nan)
    if "value_factor_ret" not in fin.columns or fin["value_factor_ret"].isna().all():
        if "value_pbr_ret" in fin.columns:
            fin["value_factor_ret"] = fin["value_pbr_ret"]

    fin.to_csv(OUT / "panel_halfyear.csv", index=False)

    # annual frame
    ann = pd.DataFrame(ANNUAL, columns=[
        "fy", "revenue", "ordinary", "net_income", "opex_sga", "op_profit", "headcount"])
    ann.to_csv(OUT / "panel_annual.csv", index=False)

    print("Wrote panel_halfyear.csv, panel_annual.csv")
    print(fin[["fy", "half", "period_end", "revenue", "base_fee", "perf_fee",
               "aum_avg_jpym", "nikkei_ret", "is_h2"]].to_string(index=False))


if __name__ == "__main__":
    main()
