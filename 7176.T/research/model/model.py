#!/usr/bin/env python3
"""7176.T earnings model — revenue identity decomposition + walk-forward CV.

Philosophy (see ../earnings_model_prompt.md):
  Asset-manager revenue is nearly an accounting identity:
      Revenue = BaseFee + PerfFee + Other
      BaseFee = base_rate * avg_AUM            (recurring, highly predictable)
      PerfFee = convex f(equity return, crystallization)   (the hard, alpha part)
  With only ~12 half-year observations we estimate FEW parameters per equation,
  regularize, and validate OUT-OF-SAMPLE against naive benchmarks.

Run:  python3 model.py   (after build_panel.py)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from perf_engine import (
    OTHER_REV_M,
    aum_nowcast_avg,
    fit_bridge_v2,
    fit_k_scale,
    fit_split_base_rates,
    predict_base_split,
    predict_earnings_v2,
    predict_perf_v3b,
    revenue_from_components,
)

OUT = Path(__file__).resolve().parent
PANEL = OUT / "panel_halfyear.csv"
OTHER_REV = OTHER_REV_M

# ---------------------------------------------------------------------------
# Derived fee splits [Derived from filings — provenance in data_dictionary.md]
# Annual base/perf fees (JPY m); H1 disclosed, H2 = annual - H1.
# ---------------------------------------------------------------------------
ANNUAL_FEES = {  # fy : (base_fee_m, perf_fee_m)   [Filing/Derived]
    2024: (None, 8_907),     # perf disclosed (+203.1% to JPY8,907m); base not split
    2025: (6_720, 9_320),    # base/perf derived from FY2026 YoY (+17.1% / +53.6%)
    2026: (7_869, 14_316),   # disclosed in Pnotice2026-1
}
H1_FEES = {  # fy : (base_fee_m, perf_fee_m)  [Filing]
    2024: (2_872, 932),
    2025: (3_266, 1_996),
    2026: (3_711, 1_713),
}


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["base_fee_m"] = np.nan
    df["perf_fee_m"] = np.nan
    for i, r in df.iterrows():
        fy, half = int(r["fy"]), r["half"]
        if half == "H1" and fy in H1_FEES:
            df.at[i, "base_fee_m"] = H1_FEES[fy][0]
            df.at[i, "perf_fee_m"] = H1_FEES[fy][1]
        elif half == "H2" and fy in ANNUAL_FEES and fy in H1_FEES:
            ab, ap = ANNUAL_FEES[fy]
            hb, hp = H1_FEES[fy]
            df.at[i, "base_fee_m"] = (ab - hb) if (ab is not None and hb is not None) else np.nan
            df.at[i, "perf_fee_m"] = (ap - hp) if (ap is not None and hp is not None) else np.nan
    df["revenue_m"] = df["revenue"] / 1000.0  # thousands -> millions
    df["ordinary_m"] = df["ordinary"] / 1000.0
    df["net_income_m"] = df["net_income"] / 1000.0
    return df


# ---------------------------------------------------------------------------
# Component 1 — BASE FEE  (identity: base = base_rate/2 * avg_AUM per half)
# ---------------------------------------------------------------------------
def fit_base_rate(df: pd.DataFrame):
    sub = df.dropna(subset=["base_fee_m", "aum_avg_jpym"]).copy()
    # annualized base rate per clean observation
    rates = (sub["base_fee_m"] / sub["aum_avg_jpym"] * 2.0)
    rate = float(rates.mean())
    obs = sub.assign(
        period=sub["period_end"].dt.strftime("%Y-%m-%d"),
        base_rate_ann_pct=(rates * 100).round(4),
    )[["period", "base_rate_ann_pct"]]
    return rate, obs


def predict_base(df: pd.DataFrame, rate: float) -> pd.Series:
    return rate / 2.0 * df["aum_avg_jpym"]


# ---------------------------------------------------------------------------
# Component 2 — PERFORMANCE FEE  (convex, crystallization-weighted)
#   perf_m ~ k * perf_base * max(0, eq_ret - hurdle)
#   perf_base proxied by avg_AUM (or end AUM); crystallization captured by is_h2.
#   Fit k separately by half because H2 (Mar year-end) crystallizes the bulk.
# ---------------------------------------------------------------------------
def fit_perf(df: pd.DataFrame, hurdle: float = 0.0):
    sub = df.dropna(subset=["perf_fee_m", "nikkei_ret", "aum_avg_jpym"]).copy()
    sub["excess"] = np.maximum(0.0, sub["nikkei_ret"] - hurdle)
    sub["drive"] = sub["aum_avg_jpym"] * sub["excess"]
    params = {}
    for half in ["H1", "H2"]:
        s = sub[sub["half"] == half]
        if len(s) >= 1 and s["drive"].sum() > 0:
            # no-intercept least squares slope (k) : perf = k*drive
            k = float((s["drive"] * s["perf_fee_m"]).sum() / (s["drive"] ** 2).sum())
        else:
            k = np.nan
        params[half] = k
    return params, sub


def predict_perf(df: pd.DataFrame, params: dict, hurdle: float = 0.0) -> pd.Series:
    excess = np.maximum(0.0, df["nikkei_ret"] - hurdle)
    drive = df["aum_avg_jpym"] * excess
    k = df["half"].map(params)
    return (k * drive).fillna(0.0)


def effective_excess_ret(row) -> float:
    """P0/P2 blended excess return: fund proxy when available, else Nikkei + value."""
    if "perf_eligible_excess_ret" in row.index and pd.notna(row.get("perf_eligible_excess_ret")):
        return float(row["perf_eligible_excess_ret"])
    nik = max(0.0, float(row.get("nikkei_ret") or 0))
    val = row.get("value_factor_ret", row.get("value_pbr_ret", np.nan))
    if pd.notna(val):
        return 0.65 * nik + 0.35 * max(0.0, float(val))
    return nik


def mandate_excess_ret(row) -> float:
    """P4 scraped mandate pool excess vs benchmark (half-year)."""
    if pd.notna(row.get("mandate_weighted_excess")):
        return max(0.0, float(row["mandate_weighted_excess"]))
    if pd.notna(row.get("mandate_weighted_return")):
        return max(0.0, float(row["mandate_weighted_return"]))
    return effective_excess_ret(row)


def driver_return(row, spec: str = "v1") -> float:
    """v1 Nikkei; v2 blended; v3a March window; v4 mandate NAV scrape."""
    if spec == "v4":
        return mandate_excess_ret(row)
    if spec == "v3a" and row.get("half") == "H2":
        if pd.notna(row.get("march_blended_ret")):
            return max(0.0, float(row["march_blended_ret"]))
        if pd.notna(row.get("march_nikkei_ret")):
            return max(0.0, float(row["march_nikkei_ret"]))
    if spec in ("v2", "v3a"):
        return effective_excess_ret(row)
    return max(0.0, float(row.get("nikkei_ret") or 0))


def fit_perf_v2(df: pd.DataFrame):
    sub = df.dropna(subset=["perf_fee_m", "aum_avg_jpym"]).copy()
    sub["excess"] = sub.apply(effective_excess_ret, axis=1)
    sub["drive"] = sub["aum_avg_jpym"] * sub["excess"]
    params = {}
    for half in ["H1", "H2"]:
        s = sub[sub["half"] == half]
        if len(s) >= 1 and s["drive"].sum() > 0:
            k = float((s["drive"] * s["perf_fee_m"]).sum() / (s["drive"] ** 2).sum())
        else:
            k = np.nan
        params[half] = k
    return params, sub


def predict_perf_v2(df: pd.DataFrame, params: dict) -> pd.Series:
    excess = df.apply(effective_excess_ret, axis=1)
    drive = df["aum_avg_jpym"] * excess
    k = df["half"].map(params)
    return (k * drive).fillna(0.0)


def fit_perf_v3a(df: pd.DataFrame):
    sub = df.dropna(subset=["perf_fee_m", "aum_avg_jpym"]).copy()
    sub["excess"] = sub.apply(lambda r: driver_return(r, "v3a"), axis=1)
    sub["drive"] = sub["aum_avg_jpym"] * sub["excess"]
    params = {}
    for half in ["H1", "H2"]:
        s = sub[sub["half"] == half]
        if len(s) >= 1 and s["drive"].sum() > 0:
            k = float((s["drive"] * s["perf_fee_m"]).sum() / (s["drive"] ** 2).sum())
        else:
            k = np.nan
        params[half] = k
    return params, sub


def predict_perf_v3a(df: pd.DataFrame, params: dict) -> pd.Series:
    excess = df.apply(lambda r: driver_return(r, "v3a"), axis=1)
    drive = df["aum_avg_jpym"] * excess
    k = df["half"].map(params)
    return (k * drive).fillna(0.0)


def fit_perf_v4(df: pd.DataFrame):
    sub = df.dropna(subset=["perf_fee_m", "aum_avg_jpym"]).copy()
    sub["excess"] = sub.apply(lambda r: driver_return(r, "v4"), axis=1)
    sub["drive"] = sub["aum_avg_jpym"] * sub["excess"]
    params = {}
    for half in ["H1", "H2"]:
        s = sub[sub["half"] == half]
        if len(s) >= 1 and s["drive"].sum() > 0:
            k = float((s["drive"] * s["perf_fee_m"]).sum() / (s["drive"] ** 2).sum())
        else:
            k = np.nan
        params[half] = k
    return params, sub


def predict_perf_v4(df: pd.DataFrame, params: dict) -> pd.Series:
    excess = df.apply(lambda r: driver_return(r, "v4"), axis=1)
    drive = df["aum_avg_jpym"] * excess
    k = df["half"].map(params)
    return (k * drive).fillna(0.0)


# ---------------------------------------------------------------------------
# Component 2b — v3b summable fund-level perf (P4 mandate detail)
# ---------------------------------------------------------------------------
def fit_perf_v3b(df: pd.DataFrame, use_march: bool = False) -> dict:
    k = fit_k_scale(df, use_march=use_march)
    return {"k_scale": k, "use_march": use_march}


def predict_perf_v3b_series(df: pd.DataFrame, params: dict) -> pd.Series:
    return predict_perf_v3b(df, params["k_scale"], params.get("use_march", False))


def fit_base_split(df: pd.DataFrame) -> dict:
    return fit_split_base_rates(df)


def predict_base_v5(df: pd.DataFrame, rates: dict) -> pd.Series:
    return df.apply(lambda r: predict_base_split(r, rates), axis=1)


# ---------------------------------------------------------------------------
# Component 3 — COSTS / EARNINGS BRIDGE
#   ordinary margin on revenue; NI = ordinary * (1 - tax). Estimate from history.
# ---------------------------------------------------------------------------
def fit_bridge(df: pd.DataFrame):
    sub = df.dropna(subset=["ordinary_m", "revenue_m", "net_income_m"])
    if len(sub) >= 4 and sub["perf_fee_m"].notna().sum() >= 3:
        return fit_bridge_v2(sub)
    # variable-cost model: ordinary = a + b*revenue (operating leverage)
    X = sub["revenue_m"].values
    y = sub["ordinary_m"].values
    b, a = np.polyfit(X, y, 1)
    tax = 1.0 - float((sub["net_income_m"] / sub["ordinary_m"]).mean())
    return dict(ord_intercept=float(a), ord_slope=float(b), ord_slope_rev=float(b),
                ord_slope_perf=0.0, tax_rate=tax, bridge_type="linear")


def predict_earnings(rev_m, bridge, perf_m=0.0):
    if bridge.get("bridge_type") == "variable_comp":
        return predict_earnings_v2(rev_m, perf_m, bridge)
    ordinary = bridge["ord_intercept"] + bridge["ord_slope"] * rev_m
    ni = ordinary * (1.0 - bridge["tax_rate"])
    return ordinary, ni


# ---------------------------------------------------------------------------
# Walk-forward validation of TOTAL HALF REVENUE vs naive benchmarks
#
# Reduced-form model (uses ALL 12 half-year revenue points; inputs known
# BEFORE the print): a stable base floor + crystallization-weighted equity
# upside. Only 3 free params (base_floor, k_H1, k_H2), fit by half on an
# expanding window. AUM proxy backfilled to a documented constant pre-2023.
# ---------------------------------------------------------------------------
AUM_PROXY_PRE2023 = 1_250_000.0  # JPY m, ~stable ¥1.25tn [Assumption]


def _load_acquisition_manifest() -> dict | None:
    path = OUT / "data" / "data_acquisition_manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _aum_proxy(row) -> float:
    return float(row["aum_avg_jpym"]) if pd.notna(row["aum_avg_jpym"]) else AUM_PROXY_PRE2023


def _fit_reduced(train: pd.DataFrame, spec: str = "v1"):
    """base_floor from low-perf periods; k_half or v3b k_scale by spec."""
    base_floor = float(train["revenue_m"].min())
    if spec in ("v3b", "v5"):
        use_march = spec == "v5"
        k_scale = fit_k_scale(train, use_march=use_march)
        return base_floor, {"k_scale": k_scale, "use_march": use_march}
    ks = {}
    for half in ["H1", "H2"]:
        s = train[train["half"] == half].copy()
        if len(s) == 0:
            ks[half] = np.nan
            continue
        drive = s.apply(lambda r: _aum_proxy(r) * driver_return(r, spec), axis=1)
        resid = (s["revenue_m"] - base_floor).clip(lower=0)
        denom = (drive ** 2).sum()
        ks[half] = float((drive * resid).sum() / denom) if denom > 0 else 0.0
    return base_floor, ks


def _predict_revenue_row(test, train, spec: str, base_floor, params, rate=None, split_rates=None):
    if spec in ("v3b", "v5"):
        k = params.get("k_scale", 1.0)
        use_march = params.get("use_march", spec == "v5")
        perf = float(predict_perf_v3b(test.to_frame().T, k, use_march).iloc[0])
        if spec == "v5" and split_rates:
            row = test.copy()
            if pd.notna(row.get("aum_avg_nowcast_jpym")):
                row["aum_avg_jpym"] = row["aum_avg_nowcast_jpym"]
            base = float(predict_base_split(row, split_rates))
        elif rate is not None:
            base = float(predict_base(test.to_frame().T, rate).iloc[0])
        else:
            base = base_floor
        return revenue_from_components(base, perf, OTHER_REV)
    k = params.get(test["half"], np.nan)
    if np.isnan(k):
        return float("nan")
    excess = driver_return(test, spec)
    drive = _aum_proxy(test) * excess
    return float(base_floor + k * drive)


def walk_forward(df: pd.DataFrame, use_v2: bool = False, use_v3a: bool = False, use_v4: bool = False,
                 use_v3b: bool = False, use_v5: bool = False):
    d = df.dropna(subset=["revenue_m", "nikkei_ret"]).reset_index(drop=True)
    rows = []
    for i in range(len(d)):
        test = d.iloc[i]
        train = d.iloc[:i]
        if len(train[train["half"] == test["half"]]) < 1 or len(train) < 3:
            continue
        if use_v5:
            spec = "v5"
        elif use_v3b:
            spec = "v3b"
        elif use_v4:
            spec = "v4"
        elif use_v3a:
            spec = "v3a"
        elif use_v2:
            spec = "v2"
        else:
            spec = "v1"
        base_floor, params = _fit_reduced(train, spec=spec)
        rate, _ = fit_base_rate(train) if spec == "v5" else (None, None)
        split_rates = fit_split_base_rates(train) if spec == "v5" else None
        rev_hat = _predict_revenue_row(test, train, spec, base_floor, params, rate, split_rates)
        if not np.isfinite(rev_hat):
            continue
        ly = train[train["half"] == test["half"]]["revenue_m"]
        rw = train["revenue_m"].iloc[-1]
        rows.append(dict(
            label=f"FY{int(test['fy'])}{test['half']}",
            actual=float(test["revenue_m"]),
            model=float(rev_hat),
            naive_lastyear=float(ly.iloc[-1]) if len(ly) else np.nan,
            naive_randomwalk=float(rw),
        ))
    return pd.DataFrame(rows)


def metrics(res: pd.DataFrame):
    out = {}
    if not len(res):
        return out
    for col in ["model", "naive_lastyear", "naive_randomwalk"]:
        m = res.dropna(subset=[col])
        if not len(m):
            continue
        err = m[col] - m["actual"]
        hit = float(
            (np.sign(m[col].diff().fillna(0)) == np.sign(m["actual"].diff().fillna(0))).mean()
        ) if len(m) > 1 else float("nan")
        rmse = float(np.sqrt((err ** 2).mean()))
        mape = float((err.abs() / m["actual"].abs()).mean() * 100)
        out[col] = dict(rmse_jpym=round(rmse, 1), mape_pct=round(mape, 1),
                        directional_hit=round(hit, 2), n=len(m))
    return out


def main() -> None:
    df = enrich(pd.read_csv(PANEL, parse_dates=["period_end"]))

    rate, base_obs = fit_base_rate(df)
    perf_params, perf_obs = fit_perf(df)
    perf_params_v2, _ = fit_perf_v2(df)
    perf_params_v3a, _ = fit_perf_v3a(df)
    perf_params_v4, _ = fit_perf_v4(df)
    perf_params_v3b = fit_perf_v3b(df, use_march=False)
    perf_params_v5 = fit_perf_v3b(df, use_march=True)
    split_rates = fit_base_split(df)
    bridge = fit_bridge(df)

    df["base_hat_m"] = predict_base(df, rate)
    df["base_hat_v5_m"] = predict_base_v5(df, split_rates)
    df["perf_hat_m"] = predict_perf(df, perf_params)
    df["perf_hat_v2_m"] = predict_perf_v2(df, perf_params_v2)
    df["perf_hat_v3a_m"] = predict_perf_v3a(df, perf_params_v3a)
    df["perf_hat_v4_m"] = predict_perf_v4(df, perf_params_v4)
    df["perf_hat_v3b_m"] = predict_perf_v3b_series(df, perf_params_v3b)
    df["perf_hat_v5_m"] = predict_perf_v3b_series(df, perf_params_v5)
    df["rev_hat_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_m"].fillna(0) + OTHER_REV
    df["rev_hat_v2_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_v2_m"].fillna(0) + OTHER_REV
    df["rev_hat_v3a_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_v3a_m"].fillna(0) + OTHER_REV
    df["rev_hat_v4_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_v4_m"].fillna(0) + OTHER_REV
    df["rev_hat_v3b_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_v3b_m"].fillna(0) + OTHER_REV
    df["rev_hat_v5_m"] = df["base_hat_v5_m"].fillna(0) + df["perf_hat_v5_m"].fillna(0) + OTHER_REV

    res = walk_forward(df, use_v2=False)
    res_v2 = walk_forward(df, use_v2=True)
    res_v3a = walk_forward(df, use_v3a=True)
    res_v4 = walk_forward(df, use_v4=True)
    res_v3b = walk_forward(df, use_v3b=True)
    res_v5 = walk_forward(df, use_v5=True)
    mt = metrics(res) if len(res) else {}
    mt_v2 = {}
    mt_v3a = {}
    mt_v4 = {}
    mt_v3b = {}
    mt_v5 = {}

    def _merge_wf_spec(res_spec, col_name, bucket):
        nonlocal res
        if not len(res_spec):
            return {}
        merged = res_spec.rename(columns={"model": col_name})
        res = res.merge(merged[["label", col_name]], on="label", how="left")
        err = res.dropna(subset=[col_name])
        if not len(err):
            return {}
        e = err[col_name] - err["actual"]
        hit = float(
            (np.sign(err[col_name].diff().fillna(0)) == np.sign(err["actual"].diff().fillna(0))).mean()
        ) if len(err) > 1 else float("nan")
        return {
            col_name: dict(
                rmse_jpym=round(float(np.sqrt((e ** 2).mean())), 1),
                mape_pct=round(float((e.abs() / err["actual"].abs()).mean() * 100), 1),
                directional_hit=round(hit, 2) if np.isfinite(hit) else None,
                n=len(err),
            )
        }

    if len(res_v3a):
        mt_v3a = _merge_wf_spec(res_v3a, "model_v3a", "v3a").get("model_v3a", {})
        if isinstance(mt_v3a, dict) and "rmse_jpym" not in mt_v3a:
            err_v3 = res.dropna(subset=["model_v3a"])
            if len(err_v3):
                e3 = err_v3["model_v3a"] - err_v3["actual"]
                mt_v3a = {"model_v3a": dict(
                    rmse_jpym=round(float(np.sqrt((e3 ** 2).mean())), 1),
                    mape_pct=round(float((e3.abs() / err_v3["actual"].abs()).mean() * 100), 1),
                    n=len(err_v3),
                )}
    if len(res_v2):
        mt_v2 = _merge_wf_spec(res_v2, "model_v2", "v2").get("model_v2", {})
        if not mt_v2:
            err_v2 = res.dropna(subset=["model_v2"])
            if len(err_v2):
                e = err_v2["model_v2"] - err_v2["actual"]
                hit = float(
                    (np.sign(err_v2["model_v2"].diff().fillna(0)) == np.sign(err_v2["actual"].diff().fillna(0))).mean()
                ) if len(err_v2) > 1 else float("nan")
                mt_v2 = {
                    "model_v2": dict(
                        rmse_jpym=round(float(np.sqrt((e ** 2).mean())), 1),
                        mape_pct=round(float((e.abs() / err_v2["actual"].abs()).mean() * 100), 1),
                        directional_hit=round(hit, 2),
                        n=len(err_v2),
                    )
                }
    if len(res_v4):
        mt_v4 = _merge_wf_spec(res_v4, "model_v4", "v4").get("model_v4", {})
        if not mt_v4:
            err_v4 = res.dropna(subset=["model_v4"])
            if len(err_v4):
                e4 = err_v4["model_v4"] - err_v4["actual"]
                mt_v4 = {"model_v4": dict(
                    rmse_jpym=round(float(np.sqrt((e4 ** 2).mean())), 1),
                    mape_pct=round(float((e4.abs() / err_v4["actual"].abs()).mean() * 100), 1),
                    n=len(err_v4),
                )}
    if len(res_v3b):
        mt_v3b = _merge_wf_spec(res_v3b, "model_v3b", "v3b")
    if len(res_v5):
        mt_v5 = _merge_wf_spec(res_v5, "model_v5", "v5")

    # ----- current/next period nowcast -----
    # Use latest known AUM and a market-return input (set live each month).
    latest = df.dropna(subset=["aum_end_jpym"]).iloc[-1]
    summary = {
        "as_of": "2026-06-04",
        "base_fee_model": {
            "form": "base_fee_half = base_rate/2 * avg_AUM",
            "base_rate_ann_est_pct": round(rate * 100, 4),
            "observations": base_obs.to_dict(orient="records"),
            "note": "Effective base rate ~0.5-0.56%/yr, mild upward drift (mix shift to higher-fee active/ETF).",
        },
        "perf_fee_model": {
            "form": "perf_fee_half = k_half * avg_AUM * max(0, nikkei_ret - hurdle)",
            "k_H1": None if np.isnan(perf_params.get("H1", np.nan)) else round(perf_params["H1"], 5),
            "k_H2": None if np.isnan(perf_params.get("H2", np.nan)) else round(perf_params["H2"], 5),
            "note": "k_H2 >> k_H1: performance fees crystallize at the March fiscal year-end. "
                    "This seasonality (H2 revenue ~2-3x H1) is the core forecastable structure.",
        },
        "earnings_bridge": bridge,
        "perf_fee_model_v2": {
            "form": "perf_fee_half = k_half * avg_AUM * effective_excess_ret",
            "effective_excess": "fund_nav_proxy if available else 0.65*Nikkei + 0.35*value_factor",
            "k_H1": None if np.isnan(perf_params_v2.get("H1", np.nan)) else round(perf_params_v2["H1"], 5),
            "k_H2": None if np.isnan(perf_params_v2.get("H2", np.nan)) else round(perf_params_v2["H2"], 5),
        },
        "perf_fee_model_v3a": {
            "form": "perf_fee_half = k_half * avg_AUM * driver_return (March Jan-Mar window on H2)",
            "k_H1": None if np.isnan(perf_params_v3a.get("H1", np.nan)) else round(perf_params_v3a["H1"], 5),
            "k_H2": None if np.isnan(perf_params_v3a.get("H2", np.nan)) else round(perf_params_v3a["H2"], 5),
        },
        "perf_fee_model_v4": {
            "form": "perf_fee_half = k_half * avg_AUM * mandate_weighted_excess (P4 scrape)",
            "k_H1": None if np.isnan(perf_params_v4.get("H1", np.nan)) else round(perf_params_v4["H1"], 5),
            "k_H2": None if np.isnan(perf_params_v4.get("H2", np.nan)) else round(perf_params_v4["H2"], 5),
        },
        "perf_fee_model_v3b": {
            "form": "perf_fee_half = k_scale × Σ_fund (AUM_f × excess_f × perf_rate_f × cryst_flag)",
            "k_scale": round(perf_params_v3b["k_scale"], 4),
            "use_march": False,
        },
        "perf_fee_model_v5": {
            "form": "v3b march_excess + split base fee + AUM roll-forward",
            "k_scale": round(perf_params_v5["k_scale"], 4),
            "use_march": True,
            "split_base_rates": split_rates,
        },
        "walk_forward": res.to_dict(orient="records"),
        "oos_metrics": mt,
        "oos_metrics_v2": mt_v2 if isinstance(mt_v2, dict) else {},
        "oos_metrics_v3a": mt_v3a if isinstance(mt_v3a, dict) else {},
        "oos_metrics_v4": mt_v4 if isinstance(mt_v4, dict) else {},
        "oos_metrics_v3b": mt_v3b if isinstance(mt_v3b, dict) else {},
        "oos_metrics_v5": mt_v5 if isinstance(mt_v5, dict) else {},
        "data_acquisition": _load_acquisition_manifest(),
        "latest_anchor": {
            "period_end": str(latest["period_end"].date()),
            "aum_end_jpym": float(latest["aum_end_jpym"]),
        },
    }
    (OUT / "model_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    df.to_csv(OUT / "panel_fitted.csv", index=False)

    from model_diagnostics import run_diagnostics

    diag = run_diagnostics(df)
    summary["production_spec"] = diag.get("production_spec", "v1")
    summary["primary_kpi"] = diag.get("primary_kpi")
    summary["diagnostics"] = {
        "version": diag.get("version"),
        "perf_fee_h2_positive_oos": diag["targets"]["perf_fee_h2_positive"]["out_of_sample"],
        "revenue_total_oos": diag["targets"]["revenue_total"]["out_of_sample"],
        "overfit_gap_revenue": diag["targets"]["revenue_total"].get("overfit_gap"),
        "spec_leaderboard": diag.get("spec_leaderboard"),
    }
    (OUT / "model_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ----- forecasts for next interim and full year (scenario on Nikkei return) -----
    fc_rows = []
    aum0 = float(latest["aum_end_jpym"])
    for half, scen, ret in [
        ("H1", "bear", -0.10), ("H1", "base", 0.03), ("H1", "bull", 0.12),
        ("H2", "bear", -0.10), ("H2", "base", 0.04), ("H2", "bull", 0.14),
    ]:
        avg_aum = aum0 * (1 + ret / 2)  # crude mark-to-market on AUM over the half
        base_hat = rate / 2.0 * avg_aum
        k = perf_params.get(half, np.nan)
        perf_hat = (k * avg_aum * max(0.0, ret)) if not np.isnan(k) else np.nan
        rev_hat = base_hat + (perf_hat if not np.isnan(perf_hat) else 0) + OTHER_REV
        ordn, ni = predict_earnings(rev_hat, bridge, perf_hat if not np.isnan(perf_hat) else 0)
        fc_rows.append(dict(
            horizon=f"next_{half}", scenario=scen, nikkei_ret=ret,
            avg_aum_jpym=round(avg_aum), base_fee_m=round(base_hat),
            perf_fee_m=None if np.isnan(perf_hat) else round(perf_hat),
            revenue_m=round(rev_hat), ordinary_m=round(ordn), net_income_m=round(ni),
        ))
    fc = pd.DataFrame(fc_rows)
    if len(res):
        oos_std = float((res["model"] - res["actual"]).std())
        slope = bridge.get("ord_slope_rev", bridge.get("ord_slope", 0.579))
        fc["revenue_lo80"] = (fc["revenue_m"] - 1.28 * oos_std).round(0)
        fc["revenue_hi80"] = (fc["revenue_m"] + 1.28 * oos_std).round(0)
        fc["net_income_lo80"] = (fc["net_income_m"] - 1.28 * oos_std * slope).round(0)
        fc["net_income_hi80"] = (fc["net_income_m"] + 1.28 * oos_std * slope).round(0)
    fc.to_csv(OUT / "forecasts.csv", index=False)

    print(f"Base rate (ann): {rate*100:.3f}%")
    print(f"Perf k: H1={perf_params.get('H1')}, H2={perf_params.get('H2')}")
    print(f"Bridge: {bridge}")
    print("\nWalk-forward OOS metrics (v1 Nikkei):")
    print(json.dumps(mt, indent=2))
    if mt_v2:
        print("\nWalk-forward OOS metrics (v2 blended excess):")
        print(json.dumps(mt_v2, indent=2))
    print("\nForecasts:")
    print(fc.to_string(index=False))
    print("\nPrimary KPI (perf fee H2+, OOS R²):")
    print(json.dumps(diag["targets"]["perf_fee_h2_positive"]["out_of_sample"], indent=2))


if __name__ == "__main__":
    main()
