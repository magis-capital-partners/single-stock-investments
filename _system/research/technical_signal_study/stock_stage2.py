"""Stage 2: cross-sectional tests on the thin panel (US stocks, one year at a time).

Per date: Spearman IC of each score vs forward log excess return, top-minus-bottom
decile spread, and a Fama-MacBeth regression of ranked forward returns on the
ranked score plus standard technical controls (5d/20d reversal, 12-1 momentum,
20d volatility, 52-week drawdown). The per-date series are then averaged with
Newey-West errors (lags = horizon) -- overall and by era.
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
from common import CROSS_SECTION_DAILY, RESULTS as RES, THIN_PANEL  # noqa: E402

SCORES = ["panic", "pressure", "exhaustion"]
CONTROLS = ["ret5", "ret20", "mom", "rv20", "dd252"]
PREDICTORS = SCORES + ["rsi14"] + CONTROLS
OUTS = {"x5": 5, "x21": 21, "x63": 63, "x252": 252}
RISKS = ["mae63", "vol21"]
ERAS = [("1975-1989", 19750101, 19900101), ("1990-1999", 19900101, 20000101), ("2000-2009", 20000101, 20100101),
        ("2010-2019", 20100101, 20200101), ("2020-2026", 20200101, 20990101)]
MIN_STOCKS = 50


def nw_series(values: np.ndarray, lag: int) -> dict:
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if len(v) < 30:
        return {"mean": None, "t": None, "n": int(len(v))}
    m = su.nw_mean(v, lag)
    return {"mean": float(m["mean"]), "t": float(m["t"]), "n": int(m["n"])}


def per_date(block: pd.DataFrame) -> dict:
    """All per-date statistics for one cross-section."""
    out: dict = {}
    n = len(block)
    k = {c: block[c].rank(pct=True).to_numpy(float) - 0.5 for c in PREDICTORS + list(OUTS) + RISKS}
    for a in PREDICTORS:
        for b in list(OUTS) + RISKS:
            m = np.isfinite(k[a]) & np.isfinite(k[b])
            if m.sum() >= MIN_STOCKS:
                out[f"ic|{a}|{b}"] = float(np.corrcoef(k[a][m], k[b][m])[0, 1])
    for s in SCORES:
        dec = (k[s] + 0.5) * 10
        for o in OUTS:
            v = block[o].to_numpy(float)
            top = (dec >= 9) & np.isfinite(v)
            bot = (dec < 1) & np.isfinite(v)
            if top.sum() >= 5 and bot.sum() >= 5:
                out[f"spread|{s}|{o}"] = float(v[top].mean() - v[bot].mean())
                out[f"top|{s}|{o}"] = float(v[top].mean())
                out[f"bot|{s}|{o}"] = float(v[bot].mean())
    for s in SCORES:
        for o in ("x21", "x63"):
            cols = [s] + CONTROLS
            X = np.column_stack([k[c] for c in cols])
            y = k[o]
            m = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
            if m.sum() >= MIN_STOCKS:
                Xf = np.column_stack([np.ones(m.sum()), X[m]])
                beta = np.linalg.lstsq(Xf, y[m], rcond=None)[0]
                for i, c in enumerate(cols):
                    out[f"fmb|{s}|{o}|{c}"] = float(beta[i + 1])
                beta1 = np.linalg.lstsq(Xf[:, :2], y[m], rcond=None)[0]
                out[f"fmb_alone|{s}|{o}"] = float(beta1[1])
    out["n_stocks"] = n
    return out


def main() -> int:
    dataset = ds.dataset(THIN_PANEL)
    cols = ["date", "sid", "us", *SCORES, *CONTROLS, "rsi14", *OUTS, *RISKS]
    records = []
    for year in range(1975, 2027):
        tbl = dataset.to_table(columns=cols, filter=(ds.field("date") >= year * 10000) & (ds.field("date") < (year + 1) * 10000) & ds.field("us"))
        df = tbl.to_pandas()
        if df.empty:
            continue
        for d, block in df.groupby("date", sort=True):
            if len(block) < MIN_STOCKS:
                continue
            rec = per_date(block)
            rec["date"] = int(d)
            records.append(rec)
        print(year, len(df), flush=True)
    daily = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    daily.to_parquet(CROSS_SECTION_DAILY, index=False)
    out: dict = {"meta": {"dates": int(len(daily)), "first": int(daily["date"].iloc[0]), "last": int(daily["date"].iloc[-1]),
                          "median_stocks": float(daily["n_stocks"].median())}}
    for col in daily.columns:
        if col in ("date", "n_stocks"):
            continue
        parts = col.split("|")
        outc = parts[2] if len(parts) > 2 else "x21"
        lag = OUTS.get(outc, 21)
        res = nw_series(daily[col].to_numpy(), lag)
        res["by_era"] = {name: nw_series(daily.loc[(daily["date"] >= lo) & (daily["date"] < hi), col].to_numpy(), lag) for name, lo, hi in ERAS}
        out[col] = res
    (RES / "cross_section.json").write_text(json.dumps(out, indent=1))
    print("wrote cross_section.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
