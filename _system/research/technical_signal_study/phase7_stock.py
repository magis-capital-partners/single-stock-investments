"""Phase 7 (stocks): recalibrate with a holdout.

Splits (pre-registered): TRAIN 1990-2009 fits, VALID 2010-2017 chooses,
HOLDOUT 2018-2026 is reported once. All features are point-in-time.

A  labels    gated "stabilizing" and a company-vs-market selloff split
B  returns   a rebound score (ridge / boosted trees on daily cross-sectional
             ranks) vs panic alone and plain 5-day reversal
C  risk      next-month volatility and P(fall another 15% within 63 sessions),
             calibrated, vs panic alone and realized volatility alone

Outputs results/phase7_stock.json and results/phase7_models.json (the frozen
coefficients the production model uses).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stats_util as su  # noqa: E402
from common import DATA, INDEX_SIGNALS, RESULTS  # noqa: E402

PANEL = DATA / "phase5_panel.parquet"
TRAIN = (19900101, 20100101)
VALID = (20100101, 20180101)
HOLD = (20180101, 20990101)
MIN_STOCKS = 40
FEATURES = [
    "panic", "pressure", "exhaustion", "fam_price_dislocation", "fam_selling_climax", "fam_volatility_stress",
    "fam_relative_path_stress", "pct_return_1d_fear", "pct_return_5d_fear", "pct_return_20d_fear", "pct_drawdown_fear",
    "pct_distance_50d_fear", "pct_volume_climax", "pct_range_climax", "pct_gap_fear", "pct_volatility_fear",
    "pct_vol_acceleration", "pct_vcr", "pct_trend_shape", "pct_negative_consistency", "pct_downside_share",
    "f_return_5d", "f_return_20d", "idio5", "idio20", "sys5", "sys20", "mom_12_1", "f_rv_20d", "f_drawdown_252d",
    "f_distance_50d", "f_volume_log_20d", "f_close_location", "rsi14", "beta", "spread", "dvol",
]
MARKET = ["spy_panic", "spy_state", "breadth_panic"]


def nw(values, lag):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if len(v) < 30:
        return {"mean": None, "t": None, "n": int(len(v))}
    m = su.nw_mean(v, lag)
    return {"mean": float(m["mean"]), "t": float(m["t"]), "n": int(m["n"])}


def market_frame(panel_dates: np.ndarray) -> pd.DataFrame:
    m = pd.read_parquet(INDEX_SIGNALS / "SPY_macro_fear.parquet", columns=["date", "state", "panic"])
    m["date"] = m["date"].str.replace("-", "").astype(np.int32)
    m = m.rename(columns={"state": "spy_state", "panic": "spy_panic"})
    st = ds.dataset(PANEL).to_table(columns=["date", "state", "us", "dash"]).to_pandas()
    st = st[st["us"] & st["dash"]]
    br = st.groupby("date")["state"].agg(lambda s: float((s >= 2).mean())).rename("breadth_panic").reset_index()
    return m.merge(br, on="date", how="outer")


def load_sample(every: int = 3) -> pd.DataFrame:
    dset = ds.dataset(PANEL)
    dates = np.sort(dset.to_table(columns=["date"]).to_pandas()["date"].unique())
    dates = dates[dates >= TRAIN[0]]
    keep = dates[::every]
    cols = ["date", "sym", "us", "dash", "state", "phase"] + FEATURES + ["x21", "x63", "resid21", "resid63", "mae_63", "fwd_vol21"]
    t = dset.to_table(columns=cols, filter=ds.field("date").isin(keep) & ds.field("us") & ds.field("dash")).to_pandas(strings_to_categorical=True)
    return t


def rank_features(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    g = df.groupby("date")
    out = pd.DataFrame(index=df.index)
    for c in cols:
        out[c] = (g[c].rank(pct=True) - 0.5).astype("float32")
    return out


def daily_ic(dates: np.ndarray, score: np.ndarray, target: np.ndarray) -> pd.Series:
    frame = pd.DataFrame({"date": dates, "s": score, "y": target}).dropna()
    g = frame.groupby("date")
    rs = g["s"].rank(pct=True)
    ry = g["y"].rank(pct=True)
    rs = rs - rs.groupby(frame["date"]).transform("mean")
    ry = ry - ry.groupby(frame["date"]).transform("mean")
    t = pd.DataFrame({"date": frame["date"], "xy": rs * ry, "xx": rs * rs, "yy": ry * ry}).groupby("date").sum()
    n = g.size()
    ic = t["xy"] / np.sqrt(t["xx"] * t["yy"])
    return ic[n >= MIN_STOCKS]


def spread_net(dates, score, target, spread) -> dict:
    f = pd.DataFrame({"date": dates, "s": score, "y": target, "c": spread}).dropna(subset=["s", "y"])
    q = f.groupby("date")["s"].rank(pct=True)
    top = f[q >= 0.9].groupby("date").agg(y=("y", "mean"), c=("c", "mean"))
    bot = f[q <= 0.1].groupby("date").agg(y=("y", "mean"), c=("c", "mean"))
    d = (top["y"] - bot["y"]).dropna()
    return {"gross": nw(d.to_numpy(), 21), "avg_cost_rt": float(np.nanmean((top["c"] + bot["c"]).reindex(d.index))) + 0.0004}


def split_mask(dates, rng):
    return (dates >= rng[0]) & (dates < rng[1])


def main() -> int:
    out: dict = {"splits": {"train": TRAIN, "valid": VALID, "holdout": HOLD}}
    df = load_sample(5)
    mk = market_frame(df["date"].unique())
    df = df.merge(mk, on="date", how="left")
    print("sample rows", len(df), flush=True)
    dates = df["date"].to_numpy()
    segs = {"train": split_mask(dates, TRAIN), "valid": split_mask(dates, VALID), "holdout": split_mask(dates, HOLD)}

    # ------------------------------------------------------------------ A. labels (pooled, by split)
    lab = {}
    base = {k: {"x63": float(df.loc[m, "resid63"].mean()), "hit": float((df.loc[m, "resid63"] > 0).mean()),
                "p_mae15": float((df.loc[m, "mae_63"] < -0.15).mean())} for k, m in segs.items()}
    lab["baseline_resid63"] = base
    # rolling max state over the previous 10 sessions per symbol needs contiguous rows -> computed in phase7_labels
    out["labels_note"] = "see phase7_labels.py for stabilizing / selloff-type labels (needs contiguous rows)"

    # ------------------------------------------------------------------ B. return models
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge

    X = rank_features(df, FEATURES)
    for c in MARKET:  # market-level: same for every stock on a date -> keep raw, scaled
        X[c] = df[c].astype("float32")
    X["spy_panic"] = (X["spy_panic"] - 50.0) / 25.0
    X["spy_state"] = X["spy_state"] / 5.0
    # interactions that encode the regime split (company-specific vs market-wide stress)
    X["panic_x_spy"] = X["panic"] * X["spy_panic"]
    X["idio20_x_spy"] = X["idio20"] * X["spy_panic"]
    X["panic_x_breadth"] = X["panic"] * X["breadth_panic"]
    cols = list(X.columns)
    y21 = df.groupby("date")["resid21"].rank(pct=True) - 0.5
    y63 = df.groupby("date")["resid63"].rank(pct=True) - 0.5
    tr = segs["train"] & y21.notna().to_numpy()
    Xtr = X[tr].fillna(0.0).to_numpy(np.float32)
    Xall = X.fillna(0.0).to_numpy(np.float32)
    models = {}
    ridge = Ridge(alpha=50.0).fit(Xtr, y21[tr].to_numpy())
    models["ridge21"] = ridge
    gbr = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=2000,
                                        l2_regularization=1.0, random_state=0).fit(Xtr, y21[tr].to_numpy())
    models["gbr21"] = gbr
    tr63 = segs["train"] & y63.notna().to_numpy()
    ridge63 = Ridge(alpha=50.0).fit(Xall[tr63], y63[tr63].to_numpy())
    models["ridge63"] = ridge63
    preds = {
        "panic": df["panic"].to_numpy(float),
        "reversal_5d": -df["f_return_5d"].to_numpy(float),
        "ridge21": ridge.predict(Xall),
        "gbr21": gbr.predict(Xall),
        "ridge63": ridge63.predict(Xall),
    }
    ret = {}
    for name, p in preds.items():
        ret[name] = {}
        for seg, m in segs.items():
            ic21 = daily_ic(dates[m], p[m], df["resid21"].to_numpy(float)[m])
            ic63 = daily_ic(dates[m], p[m], df["resid63"].to_numpy(float)[m])
            ret[name][seg] = {"ic_resid21": nw(ic21.to_numpy(), 7), "ic_resid63": nw(ic63.to_numpy(), 21),
                              "spread21": spread_net(dates[m], p[m], df["resid21"].to_numpy(float)[m], df["spread"].to_numpy(float)[m])}
        print("model", name, {s: round(v["ic_resid21"]["mean"] or 0, 4) for s, v in ret[name].items()}, flush=True)
    out["returns"] = ret
    out["ridge21_coef"] = dict(zip(cols, map(float, ridge.coef_)))
    out["ridge63_coef"] = dict(zip(cols, map(float, ridge63.coef_)))

    # ------------------------------------------------------------------ C. risk models
    from sklearn.linear_model import LinearRegression, LogisticRegression

    lv = np.log(df["fwd_vol21"].clip(lower=0.02)).to_numpy()
    raw_feats = pd.DataFrame({
        "log_rv20": np.log(df["f_rv_20d"].clip(lower=0.02)),
        "panic": df["panic"] / 100.0, "pressure": df["pressure"] / 100.0,
        "vol_stress": df["fam_volatility_stress"] / 100.0, "climax": df["fam_selling_climax"] / 100.0,
        "dd252": df["f_drawdown_252d"], "beta": df["beta"], "spy_panic": df["spy_panic"] / 100.0,
        "beta_x_spy": df["beta"] * df["spy_panic"] / 100.0, "log_spread": np.log(df["spread"].clip(lower=1e-4)),
        "dvol": df["dvol"] / 20.0,
    }).astype("float64")
    ok = np.isfinite(lv) & raw_feats.notna().all(axis=1).to_numpy()
    trm = segs["train"] & ok
    vol_model = LinearRegression().fit(raw_feats[trm].to_numpy(), lv[trm])
    vol_rv_only = LinearRegression().fit(raw_feats[["log_rv20"]][trm].to_numpy(), lv[trm])
    vol_panic_only = LinearRegression().fit(raw_feats[["panic"]][trm].to_numpy(), lv[trm])
    ydd = (df["mae_63"] < -0.15).astype(float).where(df["mae_63"].notna()).to_numpy()
    okd = ok & np.isfinite(ydd)
    trd = segs["train"] & okd
    dd_model = LogisticRegression(C=1.0, max_iter=500).fit(raw_feats[trd].to_numpy(), ydd[trd])
    dd_panic = LogisticRegression(max_iter=500).fit(raw_feats[["panic"]][trd].to_numpy(), ydd[trd])
    dd_rv = LogisticRegression(max_iter=500).fit(raw_feats[["log_rv20"]][trd].to_numpy(), ydd[trd])
    risk = {}
    for seg, m in segs.items():
        mm = m & ok
        md = m & okd
        def r2(model, cols_):
            p = model.predict(raw_feats[cols_][mm].to_numpy())
            yy = lv[mm]
            return float(1 - np.sum((yy - p) ** 2) / np.sum((yy - yy.mean()) ** 2))
        def dd(model, cols_):
            p = model.predict_proba(raw_feats[cols_][md].to_numpy())[:, 1]
            yy = ydd[md]
            brier = float(np.mean((p - yy) ** 2))
            base_rate = float(yy.mean())
            bins = pd.qcut(p, 10, labels=False, duplicates="drop")
            calib = [{"pred": float(p[bins == b].mean()), "obs": float(yy[bins == b].mean()), "n": int((bins == b).sum())} for b in np.unique(bins)]
            return {"auc": su.auc(p, yy), "brier": brier, "brier_climatology": float(base_rate * (1 - base_rate)), "calibration": calib}
        allc = list(raw_feats.columns)
        risk[seg] = {
            "vol_r2_full": r2(vol_model, allc), "vol_r2_rv_only": r2(vol_rv_only, ["log_rv20"]), "vol_r2_panic_only": r2(vol_panic_only, ["panic"]),
            "drop15_full": dd(dd_model, allc), "drop15_rv_only": dd(dd_rv, ["log_rv20"]), "drop15_panic_only": dd(dd_panic, ["panic"]),
        }
        print("risk", seg, round(risk[seg]["vol_r2_full"], 3), round(risk[seg]["vol_r2_rv_only"], 3), round(risk[seg]["vol_r2_panic_only"], 3),
              round(risk[seg]["drop15_full"]["auc"], 3), round(risk[seg]["drop15_rv_only"]["auc"], 3), round(risk[seg]["drop15_panic_only"]["auc"], 3), flush=True)
    out["risk"] = risk
    # refit risk models on train+valid for production (holdout stays untouched for the report)
    tv = (segs["train"] | segs["valid"])
    vol_final = LinearRegression().fit(raw_feats[tv & ok].to_numpy(), lv[tv & ok])
    dd_final = LogisticRegression(C=1.0, max_iter=500).fit(raw_feats[tv & okd].to_numpy(), ydd[tv & okd])
    frozen = {
        "trained_on": "1990-2017 US dashboard stock-days (every 5th session), holdout 2018-2026 untouched",
        "risk_features": list(raw_feats.columns),
        "vol21": {"intercept": float(vol_final.intercept_), "coef": dict(zip(raw_feats.columns, map(float, vol_final.coef_))),
                  "target": "log annualized realized volatility over the next 21 sessions"},
        "drop15_63d": {"intercept": float(dd_final.intercept_[0]), "coef": dict(zip(raw_feats.columns, map(float, dd_final.coef_[0]))),
                       "target": "P(close falls >= 15% below the signal close within 63 sessions)"},
    }
    # production rebound score: the same ridge, refit on TRAIN+VALID (holdout untouched)
    tv21 = (segs["train"] | segs["valid"]) & y21.notna().to_numpy()
    ridge_final = Ridge(alpha=50.0).fit(Xall[tv21], y21[tv21].to_numpy())
    frozen["rebound21"] = {
        "target": "daily cross-sectional rank of the next-21-session beta-adjusted return (US stocks)",
        "transform": {
            "stock_features": FEATURES,
            "stock_feature_transform": "cross-sectional percentile rank among US stocks that day, minus 0.5; missing -> 0",
            "market_features": {"spy_panic": "(spy_panic - 50) / 25", "spy_state": "state_code / 5", "breadth_panic": "share of US stocks in panic-or-worse"},
            "interactions": {"panic_x_spy": "panic_rank * spy_panic_scaled", "idio20_x_spy": "idio20_rank * spy_panic_scaled",
                             "panic_x_breadth": "panic_rank * breadth_panic"},
        },
        "intercept": float(ridge_final.intercept_),
        "coef": dict(zip(cols, map(float, ridge_final.coef_))),
        "holdout_2018_2026_train_only_fit": {k: out["returns"]["ridge21"]["holdout"][k] for k in ("ic_resid21", "ic_resid63")},
    }
    (RESULTS / "phase7_models.json").write_text(json.dumps(frozen, indent=1))
    (RESULTS / "phase7_stock.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote phase7_stock.json / phase7_models.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
