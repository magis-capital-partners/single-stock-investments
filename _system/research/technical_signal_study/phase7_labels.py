"""Phase 7 (labels): do re-defined setup labels mean what their names claim?

Evaluated on entry days (the first day a stock enters a label), per split,
with beta-adjusted 63-session returns, hit rate and further-drawdown risk:

* stabilizing (current): exhaustion >= 40 on any day
* stabilizing_gated: same, AND the stock was in panic-or-worse within the
  previous 10 sessions AND it is at least 10% below its 252-session high
* stabilizing_gated_soft: as above but "stress building" counts as stress
* falling_knife (current)
* company_selloff: panic-or-worse with most of the 20-session drop
  company-specific (|idio20| > |sys20|, idio20 < 0)
* market_selloff: panic-or-worse with most of the drop market-driven
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
SPLITS = {"train": (19900101, 20100101), "valid": (20100101, 20180101), "holdout": (20180101, 20990101)}


def block(frame: pd.DataFrame) -> dict:
    v = frame["resid63"].to_numpy(float)
    month = (frame["date"] // 100).to_numpy()
    m, lo, hi = su.cluster_bootstrap_mean(v, month, B=1000)
    ok = np.isfinite(v)
    mae = frame["mae_63"].to_numpy(float)
    okm = np.isfinite(mae)
    return {"n": int(ok.sum()), "months": int(len(np.unique(month[ok]))) if ok.any() else 0,
            "resid63": m, "ci95": [lo, hi], "hit": float(np.mean(v[ok] > 0)) if ok.any() else None,
            "p_mae15": float(np.mean(mae[okm] < -0.15)) if okm.any() else None}


def main() -> int:
    cols = ["sym", "date", "us", "dash", "state", "phase", "exhaustion", "panic", "f_drawdown_252d", "idio20", "sys20",
            "resid63", "mae_63"]
    df = ds.dataset(PANEL).to_table(columns=cols, filter=ds.field("us") & ds.field("dash") & (ds.field("date") >= 19900101)).to_pandas()
    df = df.sort_values(["sym", "date"]).reset_index(drop=True)
    m = pd.read_parquet(INDEX_SIGNALS / "SPY_macro_fear.parquet", columns=["date", "state"])
    m["date"] = m["date"].str.replace("-", "").astype(np.int32)
    df = df.merge(m.rename(columns={"state": "spy_state"}), on="date", how="left")
    g = df.groupby("sym", sort=False)
    prev_max_state = g["state"].transform(lambda s: s.shift(1).rolling(10, min_periods=1).max()).fillna(0).to_numpy()
    st = df["state"].to_numpy()
    ph = df["phase"].to_numpy()
    dd = df["f_drawdown_252d"].to_numpy(float)
    labels = {
        "stabilizing": ph == 3,
        "stabilizing_gated": (ph == 3) & (prev_max_state >= 2) & (dd <= -0.10),
        "stabilizing_gated_soft": (ph == 3) & (prev_max_state >= 1) & (dd <= -0.10),
        "falling_knife": ph == 4,
        "panic_or_worse": st >= 2,
        "company_selloff": (st >= 2) & (df["idio20"].to_numpy() < 0) & (np.abs(df["idio20"].to_numpy()) > np.abs(df["sys20"].to_numpy())),
        "market_selloff": (st >= 2) & (df["sys20"].to_numpy() < 0) & (np.abs(df["sys20"].to_numpy()) >= np.abs(df["idio20"].to_numpy())),
        "company_selloff_spy_calm": (st >= 2) & (df["spy_state"].to_numpy() == 0) & (df["idio20"].to_numpy() < 0) & (np.abs(df["idio20"].to_numpy()) > np.abs(df["sys20"].to_numpy())),
        "market_selloff_spy_stressed": (st >= 2) & (df["spy_state"].to_numpy() >= 1) & (df["sys20"].to_numpy() < 0) & (np.abs(df["sys20"].to_numpy()) >= np.abs(df["idio20"].to_numpy())),
    }
    sym = df["sym"].to_numpy()
    new_sym = np.concatenate([[True], sym[1:] != sym[:-1]])
    out = {"baseline": {}, "labels": {}}
    dates = df["date"].to_numpy()
    for split, (lo, hi) in SPLITS.items():
        sm = (dates >= lo) & (dates < hi)
        out["baseline"][split] = block(df[sm])
    for name, mask in labels.items():
        entry = mask & (new_sym | ~np.concatenate([[False], mask[:-1]]))
        res = {"share_of_days": float(mask.mean())}
        for split, (lo, hi) in SPLITS.items():
            sm = (dates >= lo) & (dates < hi)
            res[split] = {"entries": block(df[entry & sm]), "all_days": block(df[mask & sm])}
        out["labels"][name] = res
        print(name, round(res["share_of_days"], 3), {s: round(res[s]["entries"]["resid63"] or 0, 4) for s in SPLITS}, flush=True)
    (RESULTS / "phase7_labels.json").write_text(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
