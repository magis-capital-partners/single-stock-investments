"""Phase 7 (index ladder): daily-bar dwell rules and capitulation breadth.

The production ladder only publishes a state after the SAME raw state on two
consecutive sessions. On daily bars that suppresses every exhaustion rung,
because the confirmations (up day, close in the upper half...) flip daily.
Variants, all re-using the replayed raw states:

  current    upgrade dwell 2 (same raw state), downgrade dwell 3   [production]
  fast_up    upgrade dwell 1, downgrade dwell 3
  window     upgrade when raw >= target on 2 of the last 3 sessions, downgrade 3

Capitulation breadth: the share of dashboard US stocks in panic-or-worse that
day, tested as a market timing signal at several thresholds.

DESIGN on S&P 500 index 1962-2006 (and 1990-2006 for breadth); TEST on SPY
2007-2026 and the sector ETFs (2007-2026). Reports forward returns, further
drawdown, drawdown-matched edge, and bottom-timing recall/precision.
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
from common import DATA, INDEX_SIGNALS, RESULTS, SCRIPTS, manifest  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from criticality import flow_stress  # noqa: E402

import index_analysis as ia  # noqa: E402

MAN = manifest()
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
RANK_NAME = {v: k for k, v in flow_stress.STATE_RANK.items()}


def hysteresis(raw: np.ndarray, mode: str) -> np.ndarray:
    names = [RANK_NAME[int(r)] for r in raw]
    out = np.zeros(len(raw), dtype=int)
    if mode == "current":
        mem = None
        for i, n in enumerate(names):
            s, mem = flow_stress.apply_state_hysteresis(n, mem)
            out[i] = flow_stress.STATE_RANK[s]
        return out
    if mode == "fast_up":
        mem = None
        for i, n in enumerate(names):
            s, mem = flow_stress.apply_state_hysteresis(n, mem, upgrade_dwell=1, downgrade_dwell=3)
            out[i] = flow_stress.STATE_RANK[s]
        return out
    if mode == "window":
        cur, down = 0, 0
        for i in range(len(raw)):
            lo = max(0, i - 2)
            win = raw[lo:i + 1]
            # highest rank reached on at least 2 of the last 3 sessions
            target = 0
            for rank in range(4, 0, -1):
                if (win >= rank).sum() >= 2:
                    target = rank
                    break
            if target > cur:
                cur, down = target, 0
            elif raw[i] < cur:
                down += 1
                if down >= 3:
                    cur, down = int(raw[i]), 0
            else:
                down = 0
            out[i] = cur
        return out
    raise ValueError(mode)


def frame_for(symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    sig = pd.read_parquet(INDEX_SIGNALS / MAN[symbol]["file"])
    f = ia.outcomes(ia.bars(symbol)).merge(sig, on="date", how="inner").sort_values("date").reset_index(drop=True)
    for mode in ("current", "fast_up", "window"):
        f[f"pub_{mode}"] = hysteresis(f["raw_state"].to_numpy(), mode)
    if start:
        f = f[f["date"] >= start]
    if end:
        f = f[f["date"] < end]
    return f.reset_index(drop=True)


def evaluate(f: pd.DataFrame, conds: dict[str, np.ndarray]) -> dict:
    res = {}
    eps = ia.correction_episodes(f)
    for k, m in conds.items():
        s = ia.cond_stats(f, m)
        t = ia.timing(f, eps, m)
        dmatch = ia.drawdown_matched(f, m)
        res[k] = {"days": s["days"], "entries": s["entries"], "episodes": s["episodes"],
                  "h21_entry": s["h21"]["entry_mean"], "h63_entry": s["h63"]["entry_mean"], "h63_entry_ci": s["h63"]["entry_ci95"],
                  "h63_all_days_diff": s["h63"]["diff_vs_uncond"], "h63_t": s["h63"]["diff_t_nw"],
                  "h252_entry": s["h252"]["entry_mean"], "mae63_entry": s["mae63_entry_mean"],
                  "p_mae5_entry": s["p_mae63_lt_-5_entry"], "dd_matched_h63": dmatch["weighted_diff"],
                  "recall10": t["recall_at_k"], "precision10": t["precision_at_k"], "corrections": t["episodes"]}
    return res


def ladder_conditions(f: pd.DataFrame) -> dict[str, np.ndarray]:
    out = {}
    for mode in ("current", "fast_up", "window"):
        p = f[f"pub_{mode}"].to_numpy()
        out[f"{mode}:stress+"] = p >= 2
        out[f"{mode}:candidate+"] = p >= 3
        out[f"{mode}:confirmed"] = p >= 4
    meaningful = f["exhaustion_meaningful"].to_numpy(bool)
    out["raw:confirmed"] = f["raw_state"].to_numpy() >= 4
    out["meaningful&exh>=65"] = meaningful & (f["exhaustion"].to_numpy() >= 65)
    return out


def breadth_series() -> pd.Series:
    st = ds.dataset(DATA / "phase5_panel.parquet").to_table(columns=["date", "state", "us", "dash"]).to_pandas()
    st = st[st["us"] & st["dash"]]
    g = st.groupby("date")
    br = g["state"].agg(lambda s: float((s >= 2).mean()))
    n = g.size()
    br = br[n >= 100]
    br.index = pd.to_datetime(br.index.astype(str)).strftime("%Y-%m-%d")
    return br


def main() -> int:
    out: dict = {"design": {}, "test": {}}
    # design: S&P 500 index 1962-2006
    g = frame_for("^GSPC", "1962-06-01", "2007-01-01")
    out["design"]["GSPC_1962_2006"] = evaluate(g, ladder_conditions(g))
    # test: SPY 2007-2026 and sectors
    spy = frame_for("SPY", "2007-01-01")
    out["test"]["SPY_2007_2026"] = evaluate(spy, ladder_conditions(spy))
    sec = {}
    for s in SECTORS:
        f = frame_for(s, "2007-01-01")
        sec[s] = evaluate(f, ladder_conditions(f))
    # pooled sector summary: mean of entry h63 by condition
    keys = next(iter(sec.values())).keys()
    out["test"]["sectors_mean"] = {k: {m: float(np.nanmean([sec[s][k][m] for s in sec if sec[s][k][m] is not None])) if any(sec[s][k][m] is not None for s in sec) else None
                                      for m in ("entries", "h63_entry", "dd_matched_h63", "recall10", "precision10", "p_mae5_entry")} for k in keys}
    print("ladder variants done", flush=True)
    # capitulation breadth
    br = breadth_series()
    spy_all = frame_for("SPY")
    spy_all["breadth"] = spy_all["date"].map(br)
    vix = ia.bars("^VIX").set_index("date")["close"]
    spy_all["vix"] = spy_all["date"].map(vix)
    bres = {}
    for label, (lo, hi) in {"design_1993_2006": ("1993-01-01", "2007-01-01"), "test_2007_2026": ("2007-01-01", "2100-01-01")}.items():
        f = spy_all[(spy_all["date"] >= lo) & (spy_all["date"] < hi)].reset_index(drop=True)
        b = f["breadth"].to_numpy(float)
        conds = {f"breadth>={t:.2f}": b >= t for t in (0.15, 0.25, 0.35, 0.50)}
        conds["ladder_stress+"] = f["pub_current"].to_numpy() >= 2
        conds["vix>=30"] = f["vix"].to_numpy(float) >= 30
        bres[label] = evaluate(f, conds)
        bres[label]["breadth_quantiles"] = {str(q): float(np.nanquantile(b, q)) for q in (0.5, 0.9, 0.95, 0.99)}
    out["breadth"] = bres
    (RESULTS / "phase7_ladder.json").write_text(json.dumps(out, indent=1, default=float))
    for split in ("design", "test"):
        for name, res in out[split].items():
            if name == "sectors_mean":
                continue
            print(split, name)
            for k, v in res.items():
                print(f"   {k:22s} entries={v['entries']:4d} h63_entry={'n/a' if v['h63_entry'] is None else round(100*v['h63_entry'],2)} ddm={'n/a' if v['dd_matched_h63'] is None else round(100*v['dd_matched_h63'],2)} rec={v['recall10']} prec={v['precision10'] if v['precision10'] is None else round(v['precision10'],2)}")
    for label, res in bres.items():
        print("breadth", label, res.get("breadth_quantiles"))
        for k, v in res.items():
            if k == "breadth_quantiles":
                continue
            print(f"   {k:16s} days={v['days']:5d} entries={v['entries']:4d} h63_entry={'n/a' if v['h63_entry'] is None else round(100*v['h63_entry'],2)} all_diff={'n/a' if v['h63_all_days_diff'] is None else round(100*v['h63_all_days_diff'],2)} t={'n/a' if v['h63_t'] is None else round(v['h63_t'],1)} ddm={'n/a' if v['dd_matched_h63'] is None else round(100*v['dd_matched_h63'],2)} rec={v['recall10']} prec={v['precision10'] if v['precision10'] is None else round(v['precision10'],2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
