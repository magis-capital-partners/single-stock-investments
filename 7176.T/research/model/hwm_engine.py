#!/usr/bin/env python3
"""High-water-mark roll-forward for 7176.T perf-fee crystallization."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


@lru_cache(maxsize=1)
def load_mandate_monthly() -> pd.DataFrame:
    path = DATA / "mandate_nav_monthly.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["as_of"])
    return df.sort_values(["fund_id", "as_of"])


def _fiscal_year(ts: pd.Timestamp) -> int:
    """Japanese FY ending March: Apr–Mar."""
    return ts.year if ts.month <= 3 else ts.year + 1


def roll_hwm_series(fund_id: str, monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-month NAV and rolled HWM with fiscal-year-end reset (Apr–Mar)."""
    monthly = monthly if monthly is not None else load_mandate_monthly()
    sub = monthly[monthly["fund_id"] == fund_id].sort_values("as_of").copy()
    if sub.empty:
        return pd.DataFrame()
    hwm = np.nan
    prev_fy = None
    rows = []
    for _, r in sub.iterrows():
        nav = r.get("nav_jpy")
        if pd.isna(nav) or float(nav) <= 0:
            continue
        nav = float(nav)
        fy = _fiscal_year(r["as_of"])
        if prev_fy is not None and fy != prev_fy:
            hwm = nav
        disclosed = r.get("high_water_mark_jpy")
        if pd.notna(disclosed) and float(disclosed) > 0:
            hwm = float(disclosed)
        elif pd.isna(hwm):
            hwm = nav
        else:
            hwm = max(hwm, nav)
        prev_fy = fy
        rows.append({"as_of": r["as_of"], "nav_jpy": nav, "hwm_jpy": hwm})
    return pd.DataFrame(rows)


def nav_hwm_at(fund_id: str, period_end: pd.Timestamp, monthly: pd.DataFrame | None = None) -> tuple[float, float]:
    """Latest NAV and HWM on or before period_end."""
    series = roll_hwm_series(fund_id, monthly)
    if series.empty:
        return np.nan, np.nan
    sub = series[series["as_of"] <= period_end]
    if sub.empty:
        return np.nan, np.nan
    last = sub.iloc[-1]
    return float(last["nav_jpy"]), float(last["hwm_jpy"])


def hwm_excess_return(nav: float, hwm: float, hurdle: float = 0.0) -> float:
    if not np.isfinite(nav) or not np.isfinite(hwm) or hwm <= 0:
        return 0.0
    return max(0.0, nav / hwm - 1.0 - hurdle)


def enrich_etf_monthly_hwm(monthly: pd.DataFrame) -> pd.DataFrame:
    """Synthetic HWM = fiscal-year cummax NAV for ETF funds."""
    if monthly.empty:
        return monthly
    out = monthly.copy()
    if "high_water_mark_jpy" not in out.columns:
        out["high_water_mark_jpy"] = np.nan
    for fid in out["fund_id"].unique():
        if not str(fid).startswith("etf_"):
            continue
        mask = out["fund_id"] == fid
        sub = out.loc[mask].sort_values("as_of").copy()
        hwm_vals = []
        hwm = np.nan
        prev_fy = None
        for _, r in sub.iterrows():
            nav = r.get("nav_jpy")
            if pd.isna(nav):
                hwm_vals.append(np.nan)
                continue
            nav = float(nav)
            fy = _fiscal_year(r["as_of"])
            if prev_fy is not None and fy != prev_fy:
                hwm = nav
            hwm = nav if pd.isna(hwm) else max(hwm, nav)
            prev_fy = fy
            hwm_vals.append(hwm)
        out.loc[mask, "high_water_mark_jpy"] = out.loc[mask, "high_water_mark_jpy"].fillna(
            pd.Series(hwm_vals, index=sub.index)
        )
    return out
