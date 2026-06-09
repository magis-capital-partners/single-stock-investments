#!/usr/bin/env python3
"""Business-line bucket returns and weighted perf drivers for 7176.T."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aum_sleeves import business_line_aum_jpym


def _f(row: pd.Series, col: str, fallback: str = "nikkei_ret") -> float:
    v = row.get(col)
    if pd.notna(v):
        return float(v)
    fb = row.get(fallback)
    return float(fb) if pd.notna(fb) else 0.0


def bucket_half_return(row: pd.Series, bucket: dict[str, Any]) -> float:
    """Half-year return for a business-line bucket using panel factor columns."""
    col = bucket.get("return_col", "nikkei_ret")
    if col == "etf_perf_basket_ret":
        v = row.get("etf_perf_basket_ret")
        if pd.isna(v):
            v = row.get("etf_basket_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    if col == "value_factor_ret":
        v = row.get("value_factor_ret")
        if pd.isna(v):
            v = row.get("value_pbr_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    if col == "topix_ret":
        v = row.get("topix_ret") or row.get("topix_etf_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    if col == "growth_ret":
        v = row.get("growth_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    return _f(row, col)


def bucket_march_return(row: pd.Series, bucket: dict[str, Any]) -> float:
    """Jan–Mar crystallization window return for H2 buckets."""
    col = bucket.get("march_col", "march_nikkei_ret")
    v = row.get(col)
    if pd.notna(v):
        return float(v)
    if col == "march_value_ret":
        v = row.get("march_blended_ret")
        return float(v) if pd.notna(v) else 0.0
    v = row.get("march_blended_ret") or row.get("march_nikkei_ret")
    return float(v) if pd.notna(v) else 0.0


def bucket_excess(
    row: pd.Series,
    bucket: dict[str, Any],
    *,
    half: str,
    use_march: bool = True,
) -> tuple[float, float, str]:
    """Return (period_return, excess_vs_hurdle, source_tag)."""
    bm = bucket.get("benchmark", "nikkei")
    bm_ret = _benchmark_ret_from_row(row, bm)
    period_ret = bucket_half_return(row, bucket)
    hurdle = float(bucket.get("hurdle") or 0.0)
    excess = max(0.0, period_ret - bm_ret - hurdle)
    source = "bucket_factor_proxy"

    if half == "H2" and use_march:
        march_ret = bucket_march_return(row, bucket)
        march_exc = max(0.0, march_ret - hurdle)
        if march_exc > excess:
            excess = march_exc
            source = "bucket_march_proxy"
    return period_ret, excess, source


def _benchmark_ret_from_row(row: pd.Series, bm: str) -> float:
    if bm in ("value_pbr", "value"):
        v = row.get("value_factor_ret")
        if pd.isna(v):
            v = row.get("value_pbr_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    if bm == "topix":
        v = row.get("topix_ret") or row.get("topix_etf_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    if bm == "etf_basket":
        v = row.get("etf_perf_basket_ret") or row.get("etf_basket_ret")
        return float(v) if pd.notna(v) else _f(row, "nikkei_ret")
    return _f(row, "nikkei_ret")


def build_bucket_weighted_proxy(panel: pd.DataFrame, registry: dict) -> pd.DataFrame:
    """Weighted business-line return + excess for each fiscal half."""
    buckets = registry.get("business_line_buckets") or []
    if panel.empty or not buckets:
        return pd.DataFrame()

    rows: list[dict] = []
    for _, r in panel.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        half = r["half"]
        bl_aum = business_line_aum_jpym(pe, r.get("aum_end_jpym"))
        w_ret, w_exc, w_march = 0.0, 0.0, 0.0
        w_sum = 0.0
        out: dict[str, Any] = {"period_end": pe, "half": half, "tag": "[Proxy/Derived]"}

        for bucket in buckets:
            bid = bucket["id"]
            aum = bl_aum.get(bid, 0.0)
            if aum <= 0:
                continue
            pret, exc, _ = bucket_excess(r, bucket, half=half)
            mret = bucket_march_return(r, bucket) if half == "H2" else pret
            w_ret += aum * pret
            w_exc += aum * exc
            w_march += aum * mret
            w_sum += aum
            out[f"bucket_{bid}_ret"] = round(pret, 6)
            out[f"bucket_{bid}_excess"] = round(exc, 6)
            out[f"bucket_{bid}_aum_jpym"] = round(aum, 1)

        if w_sum > 0:
            out["bucket_weighted_ret"] = round(w_ret / w_sum, 6)
            out["bucket_weighted_excess"] = round(w_exc / w_sum, 6)
            out["bucket_weighted_march_ret"] = round(w_march / w_sum, 6)
            out["perf_eligible_excess_ret"] = out["bucket_weighted_excess"]
        else:
            out["bucket_weighted_ret"] = np.nan
            out["bucket_weighted_excess"] = np.nan
            out["bucket_weighted_march_ret"] = np.nan
            out["perf_eligible_excess_ret"] = np.nan
        rows.append(out)
    return pd.DataFrame(rows)
