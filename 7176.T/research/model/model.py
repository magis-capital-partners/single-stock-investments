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

OUT = Path(__file__).resolve().parent
PANEL = OUT / "panel_halfyear.csv"

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


# ---------------------------------------------------------------------------
# Component 3 — COSTS / EARNINGS BRIDGE
#   ordinary margin on revenue; NI = ordinary * (1 - tax). Estimate from history.
# ---------------------------------------------------------------------------
def fit_bridge(df: pd.DataFrame):
    sub = df.dropna(subset=["ordinary_m", "revenue_m", "net_income_m"])
    # variable-cost model: ordinary = a + b*revenue (operating leverage)
    X = sub["revenue_m"].values
    y = sub["ordinary_m"].values
    b, a = np.polyfit(X, y, 1)
    tax = 1.0 - float((sub["net_income_m"] / sub["ordinary_m"]).mean())
    return dict(ord_intercept=float(a), ord_slope=float(b), tax_rate=tax)


def predict_earnings(rev_m, bridge):
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


def _aum_proxy(row) -> float:
    return float(row["aum_avg_jpym"]) if pd.notna(row["aum_avg_jpym"]) else AUM_PROXY_PRE2023


def _fit_reduced(train: pd.DataFrame):
    """base_floor from low-perf (H1, weak-market) periods; k_half by no-intercept LS."""
    base_floor = float(train["revenue_m"].min())  # robust floor proxy
    ks = {}
    for half in ["H1", "H2"]:
        s = train[train["half"] == half].copy()
        if len(s) == 0:
            ks[half] = np.nan
            continue
        drive = s.apply(lambda r: _aum_proxy(r) * max(0.0, r["nikkei_ret"]), axis=1)
        resid = (s["revenue_m"] - base_floor).clip(lower=0)
        denom = (drive ** 2).sum()
        ks[half] = float((drive * resid).sum() / denom) if denom > 0 else 0.0
    return base_floor, ks


def walk_forward(df: pd.DataFrame):
    d = df.dropna(subset=["revenue_m", "nikkei_ret"]).reset_index(drop=True)
    rows = []
    for i in range(len(d)):
        test = d.iloc[i]
        train = d.iloc[:i]
        if len(train[train["half"] == test["half"]]) < 1 or len(train) < 3:
            continue
        base_floor, ks = _fit_reduced(train)
        k = ks.get(test["half"], np.nan)
        if np.isnan(k):
            continue
        drive = _aum_proxy(test) * max(0.0, test["nikkei_ret"])
        rev_hat = base_floor + k * drive
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
    bridge = fit_bridge(df)

    df["base_hat_m"] = predict_base(df, rate)
    df["perf_hat_m"] = predict_perf(df, perf_params)
    df["rev_hat_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_m"].fillna(0) + 200.0

    res = walk_forward(df)
    mt = metrics(res) if len(res) else {}

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
        "walk_forward": res.to_dict(orient="records"),
        "oos_metrics": mt,
        "latest_anchor": {
            "period_end": str(latest["period_end"].date()),
            "aum_end_jpym": float(latest["aum_end_jpym"]),
        },
    }
    (OUT / "model_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    df.to_csv(OUT / "panel_fitted.csv", index=False)

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
        rev_hat = base_hat + (perf_hat if not np.isnan(perf_hat) else 0) + 200.0
        ordn, ni = predict_earnings(rev_hat, bridge)
        fc_rows.append(dict(
            horizon=f"next_{half}", scenario=scen, nikkei_ret=ret,
            avg_aum_jpym=round(avg_aum), base_fee_m=round(base_hat),
            perf_fee_m=None if np.isnan(perf_hat) else round(perf_hat),
            revenue_m=round(rev_hat), ordinary_m=round(ordn), net_income_m=round(ni),
        ))
    fc = pd.DataFrame(fc_rows)
    fc.to_csv(OUT / "forecasts.csv", index=False)

    print(f"Base rate (ann): {rate*100:.3f}%")
    print(f"Perf k: H1={perf_params.get('H1')}, H2={perf_params.get('H2')}")
    print(f"Bridge: {bridge}")
    print("\nWalk-forward OOS metrics:")
    print(json.dumps(mt, indent=2))
    print("\nForecasts:")
    print(fc.to_string(index=False))


if __name__ == "__main__":
    main()
