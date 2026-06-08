#!/usr/bin/env python3
"""Fund-level performance-fee engine (v3b / v5) for 7176.T earnings model."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OTHER_REV_M = 200.0
AUM_PROXY_PRE2023 = 1_250_000.0


@lru_cache(maxsize=1)
def load_mandate_terms() -> dict:
    path = ROOT / "mandate_terms.json"
    if not path.exists():
        return {"funds": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_mandate_detail() -> pd.DataFrame:
    path = DATA / "mandate_nav_detail.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "period_end" in df.columns:
        df["period_end"] = pd.to_datetime(df["period_end"]).dt.strftime("%Y-%m-%d")
    return df


def crystallization_applies(fund_id: str, half: str, terms: dict | None = None) -> bool:
    terms = terms or load_mandate_terms()
    fund = terms.get("funds", {}).get(fund_id, {})
    cryst = fund.get("crystallization", ["H2"])
    return half in cryst


def _drive_excess(row: pd.Series, use_march: bool = False) -> float:
    hwm_exc = row.get("hwm_excess")
    if pd.notna(hwm_exc) and float(hwm_exc) > 0:
        return float(hwm_exc)
    if use_march and pd.notna(row.get("march_excess")):
        me = float(row["march_excess"])
        if me > 0:
            return me
    if pd.notna(row.get("excess_vs_hurdle")):
        eh = max(0.0, float(row["excess_vs_hurdle"]))
        if eh > 0:
            return eh
    ret = float(row.get("period_return") or 0)
    bm = float(row.get("benchmark_return") or 0)
    return max(0.0, ret - bm)


def structural_perf_sum(
    period_end: str,
    half: str,
    detail: pd.DataFrame | None = None,
    terms: dict | None = None,
    use_march: bool = False,
) -> float:
    """Summable perf fee driver in ¥m before calibration scalar."""
    detail = detail if detail is not None else load_mandate_detail()
    if detail.empty:
        return float("nan")
    terms = terms or load_mandate_terms()
    pe = pd.Timestamp(period_end).strftime("%Y-%m-%d")
    sub = detail[(detail["period_end"] == pe) & (detail["half"] == half)]
    total = 0.0
    for _, s in sub.iterrows():
        fid = s.get("fund_id", "")
        if not crystallization_applies(str(fid), half, terms):
            continue
        aum = s.get("aum_jpym")
        if pd.isna(aum) or float(aum) <= 0:
            continue
        excess = _drive_excess(s, use_march=use_march)
        rate = float(s.get("perf_rate") or terms.get("funds", {}).get(str(fid), {}).get("perf_rate") or 0.15)
        total += float(aum) * excess * rate
    return total if total > 0 else 0.0


def fit_k_scale(train: pd.DataFrame, use_march: bool = False) -> float:
    """No-intercept calibration: perf_fee_m ≈ k × structural_sum."""
    detail = load_mandate_detail()
    if detail.empty:
        return 1.0
    sub = train.dropna(subset=["perf_fee_m"]).copy()
    drives, actuals = [], []
    for _, r in sub.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d") if hasattr(r["period_end"], "strftime") else str(r["period_end"])[:10]
        drive = structural_perf_sum(pe, r["half"], detail, use_march=use_march)
        if np.isfinite(drive) and drive > 0:
            drives.append(drive)
            actuals.append(float(r["perf_fee_m"]))
    if len(drives) < 1:
        return 1.0
    d = np.array(drives)
    a = np.array(actuals)
    denom = float((d ** 2).sum())
    return float((d * a).sum() / denom) if denom > 0 else 1.0


def predict_perf_v3b_row(
    row: pd.Series,
    k_scale: float = 1.0,
    use_march: bool = False,
    detail: pd.DataFrame | None = None,
) -> float:
    pe = row["period_end"].strftime("%Y-%m-%d") if hasattr(row["period_end"], "strftime") else str(row["period_end"])[:10]
    drive = structural_perf_sum(pe, row["half"], detail, use_march=use_march)
    if not np.isfinite(drive):
        return 0.0
    return float(k_scale * drive)


def predict_perf_v3b(df: pd.DataFrame, k_scale: float = 1.0, use_march: bool = False) -> pd.Series:
    detail = load_mandate_detail()
    return df.apply(lambda r: predict_perf_v3b_row(r, k_scale, use_march, detail), axis=1)


def fit_split_base_rates(df: pd.DataFrame) -> dict:
    """Two-pool base fee rates (nonlisted vs ETF) from disclosed splits."""
    terms = load_mandate_terms()
    defaults = terms.get("base_fee_rates_ann", {})
    sub = df.dropna(subset=["base_fee_m", "aum_nonlisted_jpym", "aum_etf_jpym"]).copy()
    if len(sub) < 2:
        return {
            "rate_nonlisted_ann": defaults.get("nonlisted", 0.0055),
            "rate_etf_ann": defaults.get("etf", 0.0065),
        }
    nl_rates, etf_rates = [], []
    for _, r in sub.iterrows():
        bf = float(r["base_fee_m"])
        aum_nl = float(r["aum_nonlisted_jpym"]) if pd.notna(r["aum_nonlisted_jpym"]) else np.nan
        aum_etf = float(r["aum_etf_jpym"]) if pd.notna(r["aum_etf_jpym"]) else np.nan
        if pd.notna(aum_nl) and aum_nl > 0:
            nl_rates.append(bf * 0.5 / aum_nl * 2)  # rough split assumption
        if pd.notna(aum_etf) and aum_etf > 0:
            etf_rates.append(bf * 0.5 / aum_etf * 2)
    return {
        "rate_nonlisted_ann": float(np.median(nl_rates)) if nl_rates else defaults.get("nonlisted", 0.0055),
        "rate_etf_ann": float(np.median(etf_rates)) if etf_rates else defaults.get("etf", 0.0065),
    }


def predict_base_split(row: pd.Series, rates: dict) -> float:
    aum_nl = row.get("aum_nonlisted_jpym")
    aum_etf = row.get("aum_etf_jpym")
    aum_avg = row.get("aum_avg_jpym")
    if pd.isna(aum_nl) and pd.notna(aum_avg) and pd.notna(aum_etf):
        aum_nl = float(aum_avg) - float(aum_etf)
    if pd.isna(aum_nl) or pd.isna(aum_etf):
        rate = (rates["rate_nonlisted_ann"] + rates["rate_etf_ann"]) / 2
        aum = float(aum_avg) if pd.notna(aum_avg) else AUM_PROXY_PRE2023
        return rate / 2.0 * aum
    return rates["rate_nonlisted_ann"] / 2.0 * float(aum_nl) + rates["rate_etf_ann"] / 2.0 * float(aum_etf)


def aum_nowcast_avg(row: pd.Series) -> float:
    """Prefer roll-forward nowcast AUM; fall back to filing average."""
    if pd.notna(row.get("aum_avg_nowcast_jpym")):
        return float(row["aum_avg_nowcast_jpym"])
    if pd.notna(row.get("aum_avg_jpym")):
        return float(row["aum_avg_jpym"])
    return AUM_PROXY_PRE2023


def fit_bridge_v2(df: pd.DataFrame) -> dict:
    """Ordinary = fixed + slope_rev × revenue + slope_perf × perf_fee."""
    sub = df.dropna(subset=["ordinary_m", "revenue_m", "net_income_m"]).copy()
    if len(sub) < 4:
        return fit_bridge_simple(sub)
    perf = sub["perf_fee_m"].fillna(0.0).values
    rev = sub["revenue_m"].values
    y = sub["ordinary_m"].values
    X = np.column_stack([np.ones(len(sub)), rev, perf])
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    tax = 1.0 - float((sub["net_income_m"] / sub["ordinary_m"]).mean())
    return dict(
        ord_intercept=float(coef[0]),
        ord_slope_rev=float(coef[1]),
        ord_slope_perf=float(coef[2]),
        tax_rate=tax,
        bridge_type="variable_comp",
    )


def fit_bridge_simple(sub: pd.DataFrame) -> dict:
    if len(sub) < 2:
        return dict(ord_intercept=-157.0, ord_slope_rev=0.579, ord_slope_perf=0.0, tax_rate=0.264, bridge_type="linear")
    b, a = np.polyfit(sub["revenue_m"].values, sub["ordinary_m"].values, 1)
    tax = 1.0 - float((sub["net_income_m"] / sub["ordinary_m"]).mean())
    return dict(ord_intercept=float(a), ord_slope_rev=float(b), ord_slope_perf=0.0, tax_rate=tax, bridge_type="linear")


def predict_earnings_v2(rev_m: float, perf_m: float, bridge: dict) -> tuple[float, float]:
    ordinary = (
        bridge["ord_intercept"]
        + bridge["ord_slope_rev"] * rev_m
        + bridge.get("ord_slope_perf", 0.0) * perf_m
    )
    ni = ordinary * (1.0 - bridge["tax_rate"])
    return ordinary, ni


def revenue_from_components(base_m: float, perf_m: float, other_m: float = OTHER_REV_M) -> float:
    return float(base_m) + float(perf_m) + float(other_m)
