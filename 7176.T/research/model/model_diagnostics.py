#!/usr/bin/env python3
"""PM-grade diagnostics for 7176.T earnings model (IS/OOS R² per target).

Called from model.py after fitting. Writes:
  model_diagnostics.json, spec_comparison.json, residuals_halfyear.csv,
  coefficient_bootstrap.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
OTHER_REV_M = 200.0
N_BOOT = 1000
RNG = np.random.default_rng(42)

# Import shared helpers from model (same package)
from model import (  # noqa: E402
    AUM_PROXY_PRE2023,
    _aum_proxy,
    _fit_reduced,
    effective_excess_ret,
    enrich,
    fit_base_rate,
    fit_bridge,
    fit_perf,
    fit_perf_v2,
    predict_base,
    predict_earnings,
    predict_perf,
    predict_perf_v2,
    walk_forward,
)


def compute_r2(actual: np.ndarray, fitted: np.ndarray) -> float:
    a = np.asarray(actual, dtype=float)
    f = np.asarray(fitted, dtype=float)
    mask = np.isfinite(a) & np.isfinite(f)
    if mask.sum() < 2:
        return float("nan")
    a, f = a[mask], f[mask]
    ss_res = float(((a - f) ** 2).sum())
    ss_tot = float(((a - a.mean()) ** 2).sum())
    if ss_tot <= 0:
        return float("nan")
    return 1.0 - ss_res / ss_tot


def compute_adj_r2(r2: float, n: int, k: int) -> float:
    if not np.isfinite(r2) or n <= k + 1:
        return float("nan")
    return 1.0 - (1.0 - r2) * (n - 1) / (n - k - 1)


def error_stats(actual: pd.Series, fitted: pd.Series) -> dict:
    m = pd.DataFrame({"actual": actual, "fitted": fitted}).dropna()
    if len(m) == 0:
        return dict(rmse_jpym=float("nan"), mae_jpym=float("nan"), mape_pct=float("nan"), n=0)
    err = m["fitted"] - m["actual"]
    return dict(
        rmse_jpym=round(float(np.sqrt((err ** 2).mean())), 1),
        mae_jpym=round(float(err.abs().mean()), 1),
        mape_pct=round(float((err.abs() / m["actual"].abs().replace(0, np.nan)).mean() * 100), 1),
        n=len(m),
    )


def directional_hit(actual: pd.Series, fitted: pd.Series) -> float:
    m = pd.DataFrame({"actual": actual, "fitted": fitted}).dropna()
    if len(m) < 2:
        return float("nan")
    return float(
        (np.sign(m["fitted"].diff()) == np.sign(m["actual"].diff())).mean()
    )


def metrics_block(
    actual: pd.Series,
    fitted: pd.Series,
    n_params: int = 1,
    naive_rw: pd.Series | None = None,
) -> dict:
    m = pd.DataFrame({"actual": actual, "fitted": fitted}).dropna()
    n = len(m)
    if n == 0:
        return dict(
            r2=float("nan"), adj_r2=float("nan"), n=0, n_params=n_params,
            rmse_jpym=float("nan"), mae_jpym=float("nan"), mape_pct=float("nan"),
            directional_hit=float("nan"), theil_u=float("nan"),
        )
    r2 = compute_r2(m["actual"].values, m["fitted"].values)
    es = error_stats(m["actual"], m["fitted"])
    theil_u = float("nan")
    if naive_rw is not None:
        rw = pd.DataFrame({"actual": m["actual"], "fitted": m["fitted"], "rw": naive_rw.loc[m.index]}).dropna()
        if len(rw):
            rmse_m = float(np.sqrt(((rw["fitted"] - rw["actual"]) ** 2).mean()))
            rmse_rw = float(np.sqrt(((rw["rw"] - rw["actual"]) ** 2).mean()))
            theil_u = round(rmse_m / rmse_rw, 3) if rmse_rw > 0 else float("nan")
    return dict(
        r2=round(r2, 4) if np.isfinite(r2) else None,
        adj_r2=round(compute_adj_r2(r2, n, n_params), 4) if np.isfinite(r2) else None,
        directional_hit=round(directional_hit(m["actual"], m["fitted"]), 2),
        theil_u=theil_u if np.isfinite(theil_u) else None,
        n_params=n_params,
        **es,
    )


def _naive_benchmarks(df: pd.DataFrame, actual_col: str) -> dict[str, pd.Series]:
    """Same-half-last-year and random-walk naive per row index."""
    ly = []
    rw = []
    for i, r in df.iterrows():
        hist = df.loc[:i - 1] if i > 0 else df.iloc[0:0]
        same = hist[hist["half"] == r["half"]][actual_col]
        ly.append(float(same.iloc[-1]) if len(same) else np.nan)
        rw.append(float(hist[actual_col].iloc[-1]) if len(hist) else np.nan)
    return {
        "naive_lastyear": pd.Series(ly, index=df.index),
        "naive_randomwalk": pd.Series(rw, index=df.index),
    }


def walk_forward_target(
    df: pd.DataFrame,
    target_col: str,
    predict_fn,
    min_train: int = 3,
) -> pd.DataFrame:
    """Expanding-window OOS predictions for a component target."""
    d = df.dropna(subset=[target_col]).reset_index(drop=True)
    rows = []
    for i in range(len(d)):
        test = d.iloc[i]
        train = d.iloc[:i]
        if len(train) < min_train:
            continue
        if len(train[train["half"] == test["half"]]) < 1:
            continue
        try:
            pred = predict_fn(train, test)
        except Exception:
            continue
        if pred is None or not np.isfinite(pred):
            continue
        ly = train[train["half"] == test["half"]][target_col]
        rw = train[target_col].iloc[-1]
        rows.append(dict(
            label=f"FY{int(test['fy'])}{test['half']}",
            period_end=str(test["period_end"].date()) if hasattr(test["period_end"], "date") else str(test["period_end"]),
            half=test["half"],
            actual=float(test[target_col]),
            fitted=float(pred),
            naive_lastyear=float(ly.iloc[-1]) if len(ly) else np.nan,
            naive_randomwalk=float(rw),
        ))
    return pd.DataFrame(rows)


def _predict_perf_oos(train: pd.DataFrame, test: pd.Series, use_v2: bool = False) -> float:
    if use_v2:
        params, _ = fit_perf_v2(train)
        return float(predict_perf_v2(test.to_frame().T, params).iloc[0])
    params, _ = fit_perf(train)
    return float(predict_perf(test.to_frame().T, params).iloc[0])


def _predict_base_oos(train: pd.DataFrame, test: pd.Series) -> float:
    rate, _ = fit_base_rate(train)
    return float(predict_base(test.to_frame().T, rate).iloc[0])


def _predict_revenue_oos(train: pd.DataFrame, test: pd.Series, use_v2: bool = False) -> float:
    base_floor, ks = _fit_reduced(train)
    k = ks.get(test["half"], np.nan)
    if np.isnan(k):
        return float("nan")
    excess = effective_excess_ret(test) if use_v2 else max(0.0, float(test["nikkei_ret"]))
    drive = _aum_proxy(test) * excess
    return float(base_floor + k * drive)


def _predict_ordinary_oos(train: pd.DataFrame, test: pd.Series) -> float:
    bridge = fit_bridge(train)
    rev_hat = _predict_revenue_oos(train, test, use_v2=False)
    ordn, _ = predict_earnings(rev_hat, bridge)
    return float(ordn)


def _predict_ni_oos(train: pd.DataFrame, test: pd.Series) -> float:
    bridge = fit_bridge(train)
    rev_hat = _predict_revenue_oos(train, test, use_v2=False)
    _, ni = predict_earnings(rev_hat, bridge)
    return float(ni)


def bootstrap_coefficients(df: pd.DataFrame) -> dict:
    """Block-bootstrap by fiscal year."""
    sub = df.dropna(subset=["base_fee_m", "aum_avg_jpym", "perf_fee_m", "nikkei_ret"])
    if len(sub) < 4:
        return {}
    fys = sub["fy"].unique()
    samples = {k: [] for k in ["base_rate_ann", "k_H1", "k_H2", "ord_slope", "ord_intercept", "tax_rate"]}

    for _ in range(N_BOOT):
        drawn_fys = RNG.choice(fys, size=len(fys), replace=True)
        boot = pd.concat([sub[sub["fy"] == fy] for fy in drawn_fys], ignore_index=True)
        if len(boot) < 3:
            continue
        try:
            rate, _ = fit_base_rate(boot)
            samples["base_rate_ann"].append(rate)
            pp, _ = fit_perf(boot)
            samples["k_H1"].append(pp.get("H1", np.nan))
            samples["k_H2"].append(pp.get("H2", np.nan))
            br = fit_bridge(boot)
            samples["ord_slope"].append(br["ord_slope"])
            samples["ord_intercept"].append(br["ord_intercept"])
            samples["tax_rate"].append(br["tax_rate"])
        except Exception:
            continue

    out = {}
    for name, vals in samples.items():
        arr = np.array([v for v in vals if np.isfinite(v)])
        if len(arr) < 50:
            continue
        out[name] = dict(
            point=round(float(np.median(arr)), 6),
            p05=round(float(np.percentile(arr, 5)), 6),
            p50=round(float(np.median(arr)), 6),
            p95=round(float(np.percentile(arr, 95)), 6),
            method="block_bootstrap_fy",
            n_boot=len(arr),
        )
    return out


def _target_metrics(
    df: pd.DataFrame,
    mask: pd.Series,
    actual_col: str,
    fitted_col: str,
    n_params: int,
    wf: pd.DataFrame | None = None,
) -> dict:
    sub = df.loc[mask].copy()
    actual = sub[actual_col]
    fitted = sub[fitted_col]
    naive = _naive_benchmarks(sub, actual_col)

    is_block = metrics_block(actual, fitted, n_params=n_params, naive_rw=naive["naive_randomwalk"])

    oos_block = dict(r2=None, adj_r2=None, rmse_jpym=None, mae_jpym=None, mape_pct=None,
                     directional_hit=None, theil_u=None, n=0, n_params=n_params)
    benchmarks_oos = {}

    if wf is not None and len(wf):
        oos_block = metrics_block(
            wf["actual"], wf["fitted"], n_params=n_params,
            naive_rw=wf["naive_randomwalk"],
        )
        for bname, col in [("naive_lastyear", "naive_lastyear"), ("naive_randomwalk", "naive_randomwalk")]:
            bm = wf.dropna(subset=[col])
            if len(bm):
                r2_b = compute_r2(bm["actual"].values, bm[col].values)
                rmse_b = float(np.sqrt(((bm[col] - bm["actual"]) ** 2).mean()))
                rmse_m = float(np.sqrt(((bm["fitted"] - bm["actual"]) ** 2).mean()))
                benchmarks_oos[bname] = dict(
                    rmse_jpym=round(rmse_b, 1),
                    r2=round(r2_b, 4) if np.isfinite(r2_b) else None,
                    beats_model=bool(rmse_b < rmse_m),
                )

    overfit_gap = None
    if is_block.get("r2") is not None and oos_block.get("r2") is not None:
        overfit_gap = round(is_block["r2"] - oos_block["r2"], 4)

    return dict(
        in_sample=is_block,
        out_of_sample=oos_block,
        overfit_gap=overfit_gap,
        benchmarks_oos=benchmarks_oos,
    )


def spec_leaderboard(df: pd.DataFrame) -> list[dict]:
    """Compare v1 vs v2 on revenue and perf_fee H2 OOS."""
    wf_v1 = walk_forward(df, use_v2=False)
    wf_v2 = walk_forward(df, use_v2=True)

    def _oos_rmse_r2(wf: pd.DataFrame, filt=None) -> tuple[float, float]:
        if not len(wf):
            return float("nan"), float("nan")
        w = wf.copy()
        if filt is not None:
            w = w[w["label"].str.contains(filt, na=False)]
        if not len(w):
            return float("nan"), float("nan")
        pred_col = "fitted" if "fitted" in w.columns else "model"
        rmse = float(np.sqrt(((w[pred_col] - w["actual"]) ** 2).mean()))
        r2 = compute_r2(w["actual"].values, w[pred_col].values)
        return round(rmse, 1), round(r2, 4) if np.isfinite(r2) else None

    rev_v1_rmse, rev_v1_r2 = _oos_rmse_r2(wf_v1)
    rev_v2_rmse, rev_v2_r2 = _oos_rmse_r2(wf_v2)

    wf_perf_v1 = walk_forward_target(df, "perf_fee_m", lambda tr, te: _predict_perf_oos(tr, te, False))
    wf_perf_v2 = walk_forward_target(df, "perf_fee_m", lambda tr, te: _predict_perf_oos(tr, te, True))

    def _comp_wf(wf: pd.DataFrame, h2_only: bool) -> tuple[float, float]:
        if not len(wf):
            return float("nan"), float("nan")
        w = wf[wf["half"] == "H2"] if h2_only else wf
        if h2_only:
            w = w[w["actual"] > 0]
        if not len(w):
            return float("nan"), float("nan")
        rmse = float(np.sqrt(((w["fitted"] - w["actual"]) ** 2).mean()))
        r2 = compute_r2(w["actual"].values, w["fitted"].values)
        return round(rmse, 1), round(r2, 4) if np.isfinite(r2) else None

    p1_rmse, p1_r2 = _comp_wf(wf_perf_v1, True)
    p2_rmse, p2_r2 = _comp_wf(wf_perf_v2, True)

    return [
        dict(spec="v1", revenue_oos_rmse=rev_v1_rmse, revenue_oos_r2=rev_v1_r2,
             perf_fee_h2_oos_rmse=p1_rmse, perf_fee_h2_oos_r2=p1_r2, production_default=True),
        dict(spec="v2", revenue_oos_rmse=rev_v2_rmse, revenue_oos_r2=rev_v2_r2,
             perf_fee_h2_oos_rmse=p2_rmse, perf_fee_h2_oos_r2=p2_r2,
             production_default=False,
             note="v2 worse on revenue OOS RMSE; keep v1 as production default"),
    ]


def residual_attribution(df: pd.DataFrame) -> list[dict]:
    rows = []
    callouts = {
        "FY2024H2": "Strong March crystallization",
        "FY2026H2": "PBR/value rally + perf spike",
        "FY2025H2": "Model base-floor stuck; weak market",
    }
    for label, note in callouts.items():
        fy = int(label[2:6])
        half = label[6:]
        r = df[(df["fy"] == fy) & (df["half"] == half)]
        if r.empty:
            continue
        r = r.iloc[0]
        rows.append(dict(
            label=label,
            target="revenue_total",
            actual=round(float(r["revenue_m"]), 1),
            fitted=round(float(r["rev_hat_m"]), 1),
            residual=round(float(r["rev_hat_m"] - r["revenue_m"]), 1),
            perf_actual=round(float(r["perf_fee_m"]), 1) if pd.notna(r.get("perf_fee_m")) else None,
            perf_fitted=round(float(r["perf_hat_m"]), 1),
            note=note,
        ))
    return rows


def build_residuals_csv(
    df: pd.DataFrame,
    wf_revenue: pd.DataFrame,
    wf_perf: pd.DataFrame,
    wf_base: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        label = f"FY{int(r['fy'])}{r['half']}"
        pe = r["period_end"].strftime("%Y-%m-%d") if hasattr(r["period_end"], "strftime") else str(r["period_end"])
        for target, actual, fitted in [
            ("revenue_total", r["revenue_m"], r["rev_hat_m"]),
            ("base_fee", r.get("base_fee_m"), r.get("base_hat_m")),
            ("perf_fee", r.get("perf_fee_m"), r.get("perf_hat_m")),
            ("ordinary_profit", r.get("ordinary_m"), r.get("ordinary_hat_m")),
            ("net_income", r.get("net_income_m"), r.get("net_income_hat_m")),
        ]:
            if pd.isna(actual) or pd.isna(fitted):
                continue
            rows.append(dict(
                period_end=pe, label=label, target=target,
                actual=round(float(actual), 3), fitted=round(float(fitted), 3),
                residual=round(float(fitted - actual), 3), is_oos=0,
            ))
    for wf, target in [(wf_revenue, "revenue_total"), (wf_perf, "perf_fee"), (wf_base, "base_fee")]:
        for _, r in wf.iterrows():
            rows.append(dict(
                period_end=r.get("period_end", ""),
                label=r["label"], target=target,
                actual=round(r["actual"], 3), fitted=round(r["fitted"], 3),
                residual=round(r["fitted"] - r["actual"], 3), is_oos=1,
            ))
    return pd.DataFrame(rows)


def run_diagnostics(df: pd.DataFrame | None = None) -> dict:
    if df is None:
        df = enrich(pd.read_csv(OUT / "panel_halfyear.csv", parse_dates=["period_end"]))

    rate, _ = fit_base_rate(df)
    perf_params, _ = fit_perf(df)
    perf_params_v2, _ = fit_perf_v2(df)
    bridge = fit_bridge(df)

    df["base_hat_m"] = predict_base(df, rate)
    df["perf_hat_m"] = predict_perf(df, perf_params)
    df["perf_hat_v2_m"] = predict_perf_v2(df, perf_params_v2)
    df["rev_hat_m"] = df["base_hat_m"].fillna(0) + df["perf_hat_m"].fillna(0) + OTHER_REV_M
    df["ordinary_hat_m"] = bridge["ord_intercept"] + bridge["ord_slope"] * df["rev_hat_m"]
    df["net_income_hat_m"] = df["ordinary_hat_m"] * (1.0 - bridge["tax_rate"])

    # Walk-forward panels
    wf_rev = walk_forward(df, use_v2=False).rename(columns={"model": "fitted"})
    wf_rev["half"] = wf_rev["label"].str[-2:]
    wf_rev["period_end"] = ""

    wf_perf = walk_forward_target(df, "perf_fee_m", lambda tr, te: _predict_perf_oos(tr, te, False))
    wf_perf_pos_h2 = wf_perf[(wf_perf["half"] == "H2") & (wf_perf["actual"] > 0)].copy()
    wf_base = walk_forward_target(
        df.dropna(subset=["base_fee_m"]), "base_fee_m", _predict_base_oos,
    )
    wf_ord = walk_forward_target(df.dropna(subset=["ordinary_m"]), "ordinary_m", _predict_ordinary_oos)
    wf_ni = walk_forward_target(df.dropna(subset=["net_income_m"]), "net_income_m", _predict_ni_oos)

    wf_rev_h2 = wf_rev[wf_rev["half"] == "H2"].copy()

    targets = {
        "revenue_total": _target_metrics(
            df, df["revenue_m"].notna(), "revenue_m", "rev_hat_m", n_params=3, wf=wf_rev,
        ),
        "revenue_h2_only": _target_metrics(
            df, (df["half"] == "H2") & df["revenue_m"].notna(),
            "revenue_m", "rev_hat_m", n_params=3, wf=wf_rev_h2,
        ),
        "base_fee": _target_metrics(
            df, df["base_fee_m"].notna(), "base_fee_m", "base_hat_m", n_params=1, wf=wf_base,
        ),
        "perf_fee": _target_metrics(
            df, df["perf_fee_m"].notna(), "perf_fee_m", "perf_hat_m", n_params=2, wf=wf_perf,
        ),
        "perf_fee_h2_positive": _target_metrics(
            df,
            (df["half"] == "H2") & df["perf_fee_m"].notna() & (df["perf_fee_m"] > 0),
            "perf_fee_m", "perf_hat_m", n_params=2, wf=wf_perf_pos_h2,
        ),
        "ordinary_profit": _target_metrics(
            df, df["ordinary_m"].notna(), "ordinary_m", "ordinary_hat_m", n_params=2, wf=wf_ord,
        ),
        "net_income": _target_metrics(
            df, df["net_income_m"].notna(), "net_income_m", "net_income_hat_m", n_params=3, wf=wf_ni,
        ),
    }

    leaderboard = spec_leaderboard(df)
    coeffs = bootstrap_coefficients(df)
    attribution = residual_attribution(df)

    diag = dict(
        as_of=str(date.today()),
        production_spec="v1",
        primary_kpi="perf_fee_h2_positive.out_of_sample.r2",
        estimation_window=dict(start="2020-H1", end="2026-H2", n_halfyears=int(len(df)), excluded="pre-2018 HK legacy"),
        targets=targets,
        coefficients=coeffs,
        spec_leaderboard=leaderboard,
        residual_attribution=attribution,
        walk_forward=wf_rev.to_dict(orient="records"),
        caveats=[
            "Primary KPI: perf_fee_h2_positive OOS R² (not total-revenue IS R²).",
            "perf_fee_h2_positive OOS n is small (fee split disclosed only from FY2024).",
            "v2 blended excess worsens revenue OOS RMSE; production_spec remains v1.",
            "Naive same-half-last-year beats model on revenue OOS RMSE (¥3,230m vs ¥4,336m).",
            f"n≈{len(df)} half-years; negative OOS R² is valid (model worse than mean).",
        ],
        version="v3_pm_diagnostics",
    )

    spec_comp = dict(
        as_of=str(date.today()),
        production_spec="v1",
        leaderboard=leaderboard,
        acceptance_rule="Reject spec if perf_fee_h2_oos_rmse worsens vs prior",
    )

    residuals = build_residuals_csv(df, wf_rev, wf_perf, wf_base)

    def _json_safe(obj):
        if isinstance(obj, dict):
            return {k: _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_json_safe(v) for v in obj]
        if isinstance(obj, float) and not np.isfinite(obj):
            return None
        return obj

    OUT.joinpath("model_diagnostics.json").write_text(
        json.dumps(_json_safe(diag), indent=2), encoding="utf-8"
    )
    OUT.joinpath("spec_comparison.json").write_text(
        json.dumps(_json_safe(spec_comp), indent=2), encoding="utf-8"
    )
    OUT.joinpath("coefficient_bootstrap.json").write_text(
        json.dumps(_json_safe(coeffs), indent=2), encoding="utf-8"
    )
    residuals.to_csv(OUT / "residuals_halfyear.csv", index=False)

    return diag


if __name__ == "__main__":
    d = run_diagnostics()
    kpi = d["targets"]["perf_fee_h2_positive"]["out_of_sample"]
    print("Primary KPI (perf fee H2+, OOS):")
    print(json.dumps(kpi, indent=2))
    print("\nSpec leaderboard:")
    print(json.dumps(d["spec_leaderboard"], indent=2))
