#!/usr/bin/env python3
"""Back-solve implied perf excess and bucket k calibration from disclosed fees."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _eligible_aum(row: pd.Series) -> float:
    for col in ("perf_eligible_aum_jpym", "aum_avg_jpym", "aum_end_jpym"):
        v = row.get(col)
        if pd.notna(v) and float(v) > 0:
            return float(v)
    return np.nan


def backsolve_implied_excess(panel: pd.DataFrame, registry: dict | None = None) -> pd.DataFrame:
    """Implied average excess return from disclosed perf fees (¥m)."""
    registry = registry or {}
    avg_rate = 0.15
    buckets = registry.get("business_line_buckets") or []
    if buckets:
        num = sum(float(b.get("perf_rate") or 0.15) * float(b.get("share_sep2025") or 0) for b in buckets)
        den = sum(float(b.get("share_sep2025") or 0) for b in buckets)
        if den > 0:
            avg_rate = num / den

    rows: list[dict] = []
    for _, r in panel.iterrows():
        perf_m = r.get("perf_fee_m")
        if pd.isna(perf_m) and pd.notna(r.get("perf_fee")):
            perf_m = float(r["perf_fee"]) / 1000.0
        if pd.isna(perf_m) or float(perf_m) <= 0:
            continue
        aum = _eligible_aum(r)
        if not np.isfinite(aum) or aum <= 0:
            continue
        cryst = 1.0 if r.get("half") == "H2" else 0.35
        implied = float(perf_m) / (aum * avg_rate * cryst)
        rows.append({
            "period_end": r["period_end"].strftime("%Y-%m-%d"),
            "half": r["half"],
            "perf_fee_m": round(float(perf_m), 2),
            "eligible_aum_jpym": round(aum, 1),
            "avg_perf_rate_assumed": round(avg_rate, 4),
            "crystallization_weight": cryst,
            "implied_excess_ret": round(implied, 6),
            "tag": "[Derived/Filing]",
        })
    return pd.DataFrame(rows)


def calibrate_bucket_k(
    panel: pd.DataFrame,
    detail: pd.DataFrame,
    implied: pd.DataFrame,
) -> dict:
    """Per-mandate k multiplier: disclosed perf / structural drive."""
    if detail.empty or implied.empty:
        return {"buckets": {}, "global_k": 1.0}

    implied_map = implied.set_index("period_end")["implied_excess_ret"].to_dict()
    bucket_k: dict[str, list[float]] = {}
    global_ratios: list[float] = []

    for _, r in panel.iterrows():
        pe = r["period_end"].strftime("%Y-%m-%d")
        perf_m = r.get("perf_fee_m")
        if pd.isna(perf_m) and pd.notna(r.get("perf_fee")):
            perf_m = float(r["perf_fee"]) / 1000.0
        if pd.isna(perf_m) or float(perf_m) <= 0:
            continue
        half = r["half"]
        sub = detail[(detail["period_end"] == pe) & (detail["half"] == half)]
        if sub.empty:
            continue
        struct = 0.0
        for _, s in sub.iterrows():
            aum = s.get("aum_jpym")
            if pd.isna(aum) or float(aum) <= 0:
                continue
            exc = max(0.0, float(s.get("excess_vs_hurdle") or s.get("hwm_excess") or 0))
            rate = float(s.get("perf_rate") or 0.15)
            struct += float(aum) * exc * rate
        if struct <= 0:
            continue
        ratio = float(perf_m) / struct
        global_ratios.append(ratio)
        for mid, g in sub.groupby("mandate_id"):
            drive = 0.0
            for _, s in g.iterrows():
                aum = s.get("aum_jpym")
                if pd.isna(aum) or float(aum) <= 0:
                    continue
                exc = max(0.0, float(s.get("excess_vs_hurdle") or s.get("hwm_excess") or 0))
                rate = float(s.get("perf_rate") or 0.15)
                drive += float(aum) * exc * rate
            if drive > 0:
                bucket_k.setdefault(str(mid), []).append(float(perf_m) * (drive / struct) / drive)

    out_buckets = {
        mid: round(float(np.median(vals)), 4)
        for mid, vals in bucket_k.items()
        if vals
    }
    global_k = round(float(np.median(global_ratios)), 4) if global_ratios else 1.0
    return {
        "global_k": global_k,
        "buckets": out_buckets,
        "n_calibration_halves": len(global_ratios),
        "implied_halves": len(implied),
    }


def apply_bucket_k_to_detail(detail: pd.DataFrame, calibration: dict) -> pd.DataFrame:
    """Scale excess on nonlisted / proxy rows by calibrated bucket k."""
    if detail.empty or not calibration:
        return detail
    d = detail.copy()
    buckets = calibration.get("buckets") or {}
    global_k = float(calibration.get("global_k") or 1.0)
    for i, row in d.iterrows():
        fid = str(row.get("fund_id", ""))
        if not fid.startswith("nonlisted_") and fid not in buckets:
            continue
        mid = str(row.get("mandate_id", ""))
        k = float(buckets.get(mid, global_k))
        if k <= 0 or not np.isfinite(k):
            continue
        for col in ("excess_vs_hurdle", "hwm_excess", "march_excess"):
            if col in d.columns and pd.notna(row.get(col)):
                d.at[i, col] = max(0.0, float(row[col]) * k)
        if pd.notna(row.get("excess_vs_hurdle")):
            d.at[i, "calibration_k"] = k
    return d


def run_perf_calibration(panel: pd.DataFrame, detail: pd.DataFrame, registry: dict) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Write implied excess CSV + calibration JSON (diagnostic; model uses fit_k_scale)."""
    implied = backsolve_implied_excess(panel, registry)
    if not implied.empty:
        implied.to_csv(DATA / "perf_implied_excess_halfyear.csv", index=False)
    cal = calibrate_bucket_k(panel, detail, implied)
    cal_path = DATA / "bucket_k_calibration.json"
    cal_path.write_text(json.dumps(cal, indent=2), encoding="utf-8")
    return implied, cal, detail
