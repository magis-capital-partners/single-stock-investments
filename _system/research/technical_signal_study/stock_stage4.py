"""Stage 4: state-entry event study for the per-stock model.

Each event = first day a stock enters a state / phase. Outcomes are compared to
the unconditional per-stock-day baseline. Inference clusters by calendar month
(crisis months produce hundreds of simultaneous events that are one draw, not
hundreds). Splits: market regime (SPY macro fear state on the same date) and era.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stats_util as su  # noqa: E402
from common import EVENTS, INDEX_SIGNALS as SIG, RESULTS as RES  # noqa: E402

OUTS = ["x_nc_21", "x_nc_63", "x_nc_252", "r_nc_21", "r_nc_63", "r_nc_252"]


def baseline() -> dict:
    acc = pd.read_parquet(RES / "bucket_acc.parquet")
    a = acc[(acc["dim"] == "all") & (acc["era"] == "ALL")].groupby("outcome")[["sum", "n", "npos"]].sum()
    return {o: {"mean": float(r["sum"] / r["n"]), "hit": float(r["npos"] / r["n"]), "n": int(r["n"])} for o, r in a.iterrows()}


def describe(ev: pd.DataFrame) -> dict:
    month = ev["date"].str[:7].to_numpy()
    out = {"events": int(len(ev)), "stocks": int(ev["symbol"].nunique()), "months": int(len(np.unique(month))),
           "dates": int(ev["date"].nunique())}
    for o in OUTS:
        v = ev[o].to_numpy(float)
        m, lo, hi = su.cluster_bootstrap_mean(v, month, B=2000)
        ok = np.isfinite(v)
        out[o] = {"mean": m, "ci95": [lo, hi], "median": float(np.nanmedian(v)), "hit": float(np.mean(v[ok] > 0)) if ok.any() else None,
                  "p10": float(np.nanpercentile(v, 10)), "p90": float(np.nanpercentile(v, 90))}
    mae = ev["mae_63"].to_numpy(float)
    out["mae63_mean"] = float(np.nanmean(mae))
    out["p_mae63_lt_-15"] = float(np.nanmean(mae[np.isfinite(mae)] < -0.15))
    out["p_mae63_lt_-25"] = float(np.nanmean(mae[np.isfinite(mae)] < -0.25))
    out["fwd_vol21"] = float(np.nanmean(ev["fwd_vol21"]))
    return out


def main() -> int:
    ev = pd.read_parquet(EVENTS)
    macro = pd.read_parquet(SIG / "SPY_macro_fear.parquet", columns=["date", "state", "panic"]).rename(
        columns={"state": "spy_state", "panic": "spy_panic"})
    ladder = pd.read_parquet(SIG / "SPY.parquet", columns=["date", "state", "drawdown_pct"]).rename(
        columns={"state": "spy_ladder", "drawdown_pct": "spy_dd"})
    ev = ev.merge(macro, on="date", how="left").merge(ladder, on="date", how="left")
    base = baseline()
    out = {"baseline": base, "events": {}, "by_market": {}, "by_era": {}, "by_drawdown": {}}
    for name, block in ev.groupby("event"):
        out["events"][name] = describe(block)
        regimes = {
            "spy_normal": block["spy_state"] == 0,
            "spy_stress_building": block["spy_state"] == 1,
            "spy_panic_or_worse": block["spy_state"] >= 2,
        }
        out["by_market"][name] = {k: describe(block[m]) for k, m in regimes.items() if m.sum() >= 30}
        eras = {"pre-2000": block["date"] < "2000", "2000-2009": (block["date"] >= "2000") & (block["date"] < "2010"),
                "2010-2019": (block["date"] >= "2010") & (block["date"] < "2020"), "2020-2026": block["date"] >= "2020"}
        out["by_era"][name] = {k: describe(block[m]) for k, m in eras.items() if m.sum() >= 30}
        dd = block["f_drawdown_252d"]
        bands = {"dd_0_to_-10": dd > -0.10, "dd_-10_to_-25": (dd <= -0.10) & (dd > -0.25),
                 "dd_-25_to_-50": (dd <= -0.25) & (dd > -0.50), "dd_below_-50": dd <= -0.50}
        out["by_drawdown"][name] = {k: describe(block[m]) for k, m in bands.items() if m.sum() >= 30}
        print("done", name, len(block), flush=True)
    (RES / "events_summary.json").write_text(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
