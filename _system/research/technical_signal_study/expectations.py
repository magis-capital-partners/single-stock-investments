"""Backtest expectations for the live signal track record (phase 6).

Computes, from the point-in-time panel, what each published signal has been
followed by historically. It uses exactly the outcome definitions the nightly
grader (_system/scripts/build_signal_track_record.py) applies to live signals:
simple return from the next session's close, minus SPY's over the same window;
P(close falls >= 15% below the signal close within 63 sessions); realized
next-month volatility.

Writes _system/scripts/technical_signal_expectations.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import index_analysis as ia  # noqa: E402
from common import DATA, INDEX_SIGNALS, RESULTS, SCRIPTS, manifest  # noqa: E402

PANEL = DATA / "phase5_panel.parquet"
OUT = SCRIPTS / "technical_signal_expectations.json"
CONFIG = json.loads((SCRIPTS / "technical_model_v3.json").read_text(encoding="utf-8"))
STATE_NAMES = {0: "normal", 1: "stress_building", 2: "panic", 3: "capitulation_candidate", 4: "exhaustion_emerging", 5: "confirmed_exhaustion"}
PERIODS = {"full": (19900101, 20990101), "recent": (20180101, 20990101)}


def stats(frame: pd.DataFrame) -> dict:
    out = {"n": int(len(frame))}
    for h in (21, 63):
        x = frame[f"sx{h}"].to_numpy(float)
        ok = np.isfinite(x)
        ra = frame[f"sra{h}"].to_numpy(float)
        oka = np.isfinite(ra)
        out[f"h{h}"] = {"n": int(ok.sum()), "mean_excess": float(np.mean(x[ok])) if ok.any() else None,
                        "mean_beta_adjusted": float(np.mean(ra[oka])) if oka.any() else None,
                        "median_excess": float(np.median(x[ok])) if ok.any() else None,
                        "hit": float(np.mean(x[ok] > 0)) if ok.any() else None,
                        "mean_return": float(np.nanmean(frame[f"sr{h}"])) if ok.any() else None}
    mae = frame["mae_63"].to_numpy(float)
    okm = np.isfinite(mae)
    out["p_drop15_63d"] = float(np.mean(mae[okm] < -0.15)) if okm.any() else None
    vol = frame["fwd_vol21"].to_numpy(float)
    out["realized_vol21"] = float(np.nanmean(vol)) if np.isfinite(vol).any() else None
    return out


def rebound_scores(df: pd.DataFrame, market: pd.DataFrame) -> pd.Series:
    reb = CONFIG["rebound21"]
    feats = reb["transform"]["stock_features"]
    g = df.groupby("date")
    X = pd.DataFrame({f: (g[f].rank(pct=True) - 0.5) for f in feats}).fillna(0.0)
    m = df[["date"]].merge(market, on="date", how="left")
    sp = ((m["spy_panic"] - 50.0) / 25.0).to_numpy()
    ss = (m["spy_state"] / 5.0).to_numpy()
    br = m["breadth"].to_numpy()
    X["spy_panic"], X["spy_state"], X["breadth_panic"] = sp, ss, br
    X["panic_x_spy"] = X["panic"] * sp
    X["idio20_x_spy"] = X["idio20"] * sp
    X["panic_x_breadth"] = X["panic"] * br
    raw = reb["intercept"] + sum(X[k].to_numpy() * c for k, c in reb["coef"].items())
    raw = pd.Series(raw, index=df.index)
    return (raw.groupby(df["date"]).rank(pct=True) * 100.0)


def risk_probability(df: pd.DataFrame, market: pd.DataFrame) -> np.ndarray:
    cfg = CONFIG["drop15_63d"]
    m = df[["date"]].merge(market, on="date", how="left")
    spy = m["spy_panic"].to_numpy() / 100.0
    feats = {
        "log_rv20": np.log(np.clip(df["f_rv_20d"].to_numpy(float), 0.02, None)), "panic": df["panic"].to_numpy() / 100.0,
        "pressure": df["pressure"].to_numpy() / 100.0, "vol_stress": df["fam_volatility_stress"].to_numpy() / 100.0,
        "climax": df["fam_selling_climax"].to_numpy() / 100.0, "dd252": df["f_drawdown_252d"].to_numpy(float),
        "beta": df["beta"].to_numpy(float), "spy_panic": spy, "beta_x_spy": df["beta"].to_numpy(float) * spy,
        "log_spread": np.log(np.clip(df["spread"].to_numpy(float), 1e-4, None)), "dvol": df["dvol"].to_numpy(float) / 20.0,
    }
    z = cfg["intercept"] + sum(feats[k] * c for k, c in cfg["coef"].items())
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def main() -> int:
    feats = CONFIG["rebound21"]["transform"]["stock_features"]
    cols = sorted(set(["sym", "date", "us", "dash", "state", "direction", "rsi14", "idio20", "sys20", "panic", "pressure",
                       "exhaustion", "lr21", "lr63", "x21", "x63", "mae_63", "fwd_vol21", "f_rv_20d",
                       "fam_volatility_stress", "fam_selling_climax", "f_drawdown_252d", "beta", "spread", "dvol"] + feats))
    dset = ds.dataset(PANEL)
    all_dates = np.sort(dset.to_table(columns=["date"], filter=ds.field("date") >= 19900101).to_pandas()["date"].unique())
    keep = all_dates[::3]  # every 3rd session: averages need no more, and per-date ranks stay exact
    df = dset.to_table(columns=cols, filter=ds.field("us") & ds.field("dash") & ds.field("date").isin(keep)).to_pandas(strings_to_categorical=True)
    # simple returns, matching the live grader
    for h in (21, 63):
        df[f"sr{h}"] = np.expm1(df[f"lr{h}"])
        df[f"sx{h}"] = df[f"sr{h}"] - np.expm1(df[f"lr{h}"] - df[f"x{h}"])
        df[f"sra{h}"] = df[f"sr{h}"] - df["beta"] * np.expm1(df[f"lr{h}"] - df[f"x{h}"])
    macro = pd.read_parquet(INDEX_SIGNALS / "SPY_macro_fear.parquet", columns=["date", "state", "panic"])
    macro["date"] = macro["date"].str.replace("-", "").astype(np.int32)
    breadth = df.groupby("date")["state"].agg(lambda s: float((s >= 2).mean())).rename("breadth").reset_index()
    market = macro.rename(columns={"state": "spy_state", "panic": "spy_panic"}).merge(breadth, on="date", how="inner")
    df["rebound"] = rebound_scores(df, market).to_numpy()
    df["p_drop15"] = risk_probability(df, market)
    st = df["state"].to_numpy()
    selloff_market = (df["sys20"].to_numpy() < 0) & (np.abs(df["sys20"].to_numpy()) >= np.abs(df["idio20"].to_numpy()))
    phase = np.where(st >= 2, np.where(selloff_market, "market_selloff", "company_selloff"),
                     np.where(df["direction"].to_numpy() == 1, "trend_intact",
                              np.where(df["rsi14"].to_numpy() < 35, "oversold_watch", "indeterminate")))
    df["phase_v3"] = phase
    p = df["p_drop15"].to_numpy()
    df["risk_band"] = np.where(p < 0.10, "low", np.where(p < 0.20, "normal", np.where(p < 0.35, "elevated", "high")))
    out: dict = {"generated_from": "_system/research/technical_signal_study/expectations.py",
                 "definition": "simple return from the next session's close; excess = minus SPY over the same window",
                 "periods": {k: [str(a), str(b)] for k, (a, b) in PERIODS.items()}, "groups": {}}
    for period, (lo, hi) in PERIODS.items():
        sub = df[(df["date"] >= lo) & (df["date"] < hi)]
        grp = {"all": {"all": stats(sub)}}
        grp["stock_state"] = {STATE_NAMES[k]: stats(b) for k, b in sub.groupby("state", observed=True)}
        grp["stock_phase"] = {k: stats(b) for k, b in sub.groupby("phase_v3")}
        grp["panic_bucket"] = {f"{int(k) * 10}-{int(k) * 10 + 10}": stats(b)
                               for k, b in sub.groupby(np.clip(np.floor(sub["panic"] / 10), 0, 9)) if len(b) >= 500}
        grp["rebound_decile"] = {f"{int(k) + 1}": stats(b) for k, b in sub.groupby(np.clip(np.floor(sub["rebound"] / 10), 0, 9))}
        bands = {}
        for k, b in sub.groupby("risk_band"):
            s = stats(b)
            s["mean_predicted_p_drop15"] = float(b["p_drop15"].mean())
            bands[k] = s
        grp["risk_band"] = bands
        out["groups"][period] = grp
        print(period, "rows", len(sub), flush=True)
    # SPY ladder, all days in each published rung
    man = manifest()
    sig = pd.read_parquet(INDEX_SIGNALS / man["SPY"]["file"])
    f = ia.outcomes(ia.bars("SPY")).merge(sig, on="date", how="inner")
    lad = {}
    names = {0: "normal", 1: "observe", 2: "stress", 3: "exhaustion_candidate", 4: "confirmed_exhaustion"}
    for period, (lo, hi) in PERIODS.items():
        g = f[(f["date"] >= f"{str(lo)[:4]}-01-01") & (f["date"] < (f"{str(hi)[:4]}-01-01" if hi < 20990101 else "2100-01-01"))]
        res = {}
        for code, name in names.items():
            b = g[g["state"] == code]
            if b.empty:
                res[name] = {"n": 0}
                continue
            res[name] = {"n": int(len(b)),
                         "h21": {"mean_return": float(b["r_nc_21"].mean()), "hit": float((b["r_nc_21"] > 0).mean())},
                         "h63": {"mean_return": float(b["r_nc_63"].mean()), "hit": float((b["r_nc_63"] > 0).mean())},
                         "p_drop5_63d": float((b["mae_63"] < -0.05).mean())}
        res["all_days"] = {"n": int(len(g)), "h21": {"mean_return": float(g["r_nc_21"].mean()), "hit": float((g["r_nc_21"] > 0).mean())},
                           "h63": {"mean_return": float(g["r_nc_63"].mean()), "hit": float((g["r_nc_63"] > 0).mean())},
                           "p_drop5_63d": float((g["mae_63"] < -0.05).mean())}
        lad[period] = res
    out["ladder_spy"] = lad
    # per-stock verdicts from the study
    pt = pd.read_csv(RESULTS / "per_stock_table.csv")
    verdicts = {}
    for r in pt.itertuples(index=False):
        if not isinstance(r.panic_x63_ic, float) or not math.isfinite(r.panic_x63_ic):
            continue
        years = r.usable_rows / 252.0
        verdict = ("too_short" if years < 5 else "positive" if (r.panic_x63_fdr10 and r.panic_x63_ic > 0)
                   else "negative" if (r.panic_x63_fdr10 and r.panic_x63_ic < 0) else "none")
        verdicts[str(r.ticker)] = {"verdict": verdict, "ic63_shrunk": round(float(r.panic_x63_ic_shrunk), 4),
                                   "ic63": round(float(r.panic_x63_ic), 4), "years": round(years, 1),
                                   "days_panic": int(r.days_panic), "first": str(r.first)[:10]}
    out["by_ticker"] = verdicts
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print("wrote", OUT, f"{OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
