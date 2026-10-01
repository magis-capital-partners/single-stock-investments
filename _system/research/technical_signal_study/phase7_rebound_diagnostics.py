"""Phase 7: what exactly does the risk-adjusted rank predict? (holdout 2018-2026)

The rebound model was fit to the cross-sectional rank of the next-21-session
BETA-ADJUSTED return. This checks it against both that target and the raw
return versus SPY, by decile, so the dashboard copy can say what it does and
does not do. Writes results/phase7_rebound_diagnostics.json.
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
import expectations as ex  # noqa: E402
import stats_util as su  # noqa: E402
from common import DATA, INDEX_SIGNALS, RESULTS  # noqa: E402

PANEL = DATA / "phase5_panel.parquet"


def main() -> int:
    feats = ex.CONFIG["rebound21"]["transform"]["stock_features"]
    dset = ds.dataset(PANEL)
    dates = np.sort(dset.to_table(columns=["date"], filter=ds.field("date") >= 20180101).to_pandas()["date"].unique())[::5]
    cols = sorted(set(["sym", "date", "us", "dash", "state", "x21", "x63", "resid21", "resid63", "lr21", "beta", "f_rv_20d", "panic"] + feats))
    df = dset.to_table(columns=cols, filter=ds.field("us") & ds.field("dash") & ds.field("date").isin(dates)).to_pandas(strings_to_categorical=True)
    macro = pd.read_parquet(INDEX_SIGNALS / "SPY_macro_fear.parquet", columns=["date", "state", "panic"])
    macro["date"] = macro["date"].str.replace("-", "").astype(np.int32)
    br = df.groupby("date")["state"].agg(lambda s: float((s >= 2).mean())).rename("breadth").reset_index()
    market = macro.rename(columns={"state": "spy_state", "panic": "spy_panic"}).merge(br, on="date")
    df["reb"] = ex.rebound_scores(df, market).to_numpy()

    def ic(score, target, lag):
        f = df[["date", score, target]].dropna()
        g = f.groupby("date")
        a = g[score].rank(pct=True)
        b = g[target].rank(pct=True)
        a = a - a.groupby(f["date"]).transform("mean")
        b = b - b.groupby(f["date"]).transform("mean")
        t = pd.DataFrame({"d": f["date"], "xy": a * b, "xx": a * a, "yy": b * b}).groupby("d").sum()
        v = (t.xy / np.sqrt(t.xx * t.yy)).to_numpy()
        m = su.nw_mean(v, lag)
        return {"ic": float(m["mean"]), "t": float(m["t"]), "dates": int(m["n"])}

    out = {"sample": "US dashboard stocks, every 5th session, 2018-2026 (holdout)",
           "ic": {s: {t: ic(s, t, lag) for t, lag in (("resid21", 5), ("x21", 5), ("resid63", 13), ("x63", 13))}
                  for s in ("reb", "panic")}}
    df["dec"] = np.clip(np.floor(df["reb"] / 10), 0, 9).astype(int) + 1
    df["sx21"] = np.expm1(df["lr21"]) - np.expm1(df["lr21"] - df["x21"])
    dec = df.groupby("dec").agg(n=("x21", "size"), mean_simple_excess_21=("sx21", "mean"), median_simple_excess_21=("sx21", "median"),
                                beat_spy_21=("x21", lambda s: float((s > 0).mean())), mean_beta_adjusted_21=("resid21", "mean"),
                                beta=("beta", "mean"), rv20=("f_rv_20d", "mean"))
    out["deciles"] = {str(k): {c: float(v) for c, v in row.items()} for k, row in dec.iterrows()}
    (RESULTS / "phase7_rebound_diagnostics.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["ic"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
