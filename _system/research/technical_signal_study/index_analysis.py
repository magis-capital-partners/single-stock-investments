"""Index-level study: does the daily capitulation ladder (and the SPY "market
fear" read) say anything about forward returns, risk, and bottom timing?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fear_vec  # noqa: E402
import stats_util as su  # noqa: E402
from common import BARS, INDEX_SIGNALS as SIG, RESULTS as RES, manifest  # noqa: E402

RES.mkdir(exist_ok=True)
MANIFEST = manifest()
H = [1, 5, 10, 21, 63, 126, 252]
START = {"^GSPC": "1962-01-02", "^IXIC": "1984-10-11"}
LADDER = {0: "normal", 1: "observe", 2: "stress", 3: "exhaustion_candidate", 4: "confirmed_exhaustion"}


def bars(symbol: str) -> pd.DataFrame:
    df = fear_vec.production_rows(pd.read_parquet(BARS / MANIFEST[symbol]["file"]))
    if symbol in START:
        df = df[df["date"] >= START[symbol]].reset_index(drop=True)
    return df


def outcomes(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"].to_numpy(float)
    o = df["open"].to_numpy(float)
    n = len(c)
    out = pd.DataFrame({"date": df["date"].to_numpy(), "close": c})
    for h in H:
        nc = np.full(n, np.nan)
        nc[: n - h - 1] = c[h + 1:] / c[1: n - h] - 1.0
        cc = np.full(n, np.nan)
        cc[: n - h] = c[h:] / c[: n - h] - 1.0
        no = np.full(n, np.nan)
        o1 = np.concatenate([o[1:], [np.nan]])
        ex = np.full(n, np.nan)
        ex[: n - h] = c[h:]
        no = ex / o1 - 1.0
        out[f"r_nc_{h}"] = nc
        out[f"r_cc_{h}"] = cc
        out[f"r_no_{h}"] = no
    for h in (21, 63):
        rev = pd.Series(c[::-1]).rolling(h, min_periods=h).min().to_numpy()[::-1]
        mn = np.concatenate([rev[1:], [np.nan]])
        out[f"mae_{h}"] = mn / c - 1.0
    lr = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    fv = pd.Series(lr[::-1]).rolling(21, min_periods=21).std().to_numpy()[::-1] * np.sqrt(252)
    out["fwd_vol21"] = np.concatenate([fv[1:], [np.nan]])
    # simple baselines
    diff = np.diff(c, prepend=np.nan)
    g = pd.Series(np.where(diff > 0, diff, 0.0)).rolling(14).mean()
    lo = pd.Series(np.where(diff < 0, -diff, 0.0)).rolling(14).mean()
    out["rsi14"] = (100 - 100 / (1 + g / lo.replace(0, np.nan))).to_numpy()
    out["ret5"] = pd.Series(c).pct_change(5).to_numpy()
    out["dd252"] = c / pd.Series(c).rolling(252, min_periods=1).max().to_numpy() - 1.0
    return out


def entries(mask: np.ndarray) -> np.ndarray:
    m = np.asarray(mask, bool)
    prev = np.concatenate([[False], m[:-1]])
    return m & ~prev


def cond_stats(frame: pd.DataFrame, mask: np.ndarray, key: str = "r_nc") -> dict:
    """All-days and entry-day conditional outcomes vs the unconditional sample."""
    mask = np.asarray(mask, bool)
    ent = entries(mask)
    idx = np.flatnonzero(ent)
    ep = su.episodes(idx, 63)
    res = {"days": int(mask.sum()), "share": float(mask.mean()), "entries": int(ent.sum()),
           "episodes": int(ep.max() + 1) if len(ep) else 0}
    for h in (5, 21, 63, 252):
        r = frame[f"{key}_{h}"].to_numpy(float)
        ok = np.isfinite(r)
        base = r[ok].mean()
        d = su.nw_mean_diff(r[ok], mask[ok], lags=h)
        er = r[idx]
        m_e, lo_e, hi_e = su.cluster_bootstrap_mean(er, ep) if len(idx) else (np.nan, np.nan, np.nan)
        res[f"h{h}"] = {
            "all_days_mean": float(np.nanmean(r[mask])) if mask.any() else None,
            "uncond_mean": float(base),
            "diff_vs_uncond": float(d["diff"]), "diff_t_nw": float(d["t"]),
            "all_days_hit": float(np.nanmean(r[mask & ok] > 0)) if (mask & ok).any() else None,
            "uncond_hit": float(np.mean(r[ok] > 0)),
            "entry_mean": None if not np.isfinite(m_e) else float(m_e),
            "entry_ci95": None if not np.isfinite(lo_e) else [float(lo_e), float(hi_e)],
            "entry_hit": float(np.nanmean(er[np.isfinite(er)] > 0)) if np.isfinite(er).any() else None,
            "entry_n": int(np.isfinite(er).sum()),
        }
    mae = frame["mae_63"].to_numpy(float)
    res["mae63_entry_mean"] = float(np.nanmean(mae[idx])) if len(idx) else None
    res["mae63_uncond_mean"] = float(np.nanmean(mae))
    res["p_mae63_lt_-5_entry"] = float(np.nanmean(mae[idx] < -0.05)) if len(idx) else None
    res["p_mae63_lt_-5_uncond"] = float(np.nanmean(mae[np.isfinite(mae)] < -0.05))
    fv = frame["fwd_vol21"].to_numpy(float)
    res["fwd_vol21_days"] = float(np.nanmean(fv[mask])) if mask.any() else None
    res["fwd_vol21_uncond"] = float(np.nanmean(fv))
    return res


def drawdown_matched(frame: pd.DataFrame, mask: np.ndarray, h: int = 63) -> dict:
    """Signal-vs-no-signal forward return inside the same drawdown band."""
    bins = [-1.0, -0.30, -0.20, -0.15, -0.10, -0.05, 0.0001]
    dd = frame["dd252"].to_numpy(float)
    r = frame[f"r_nc_{h}"].to_numpy(float)
    rows, wdiff, wsum = [], 0.0, 0
    for lo, hi in zip(bins[:-1], bins[1:]):
        band = (dd >= lo) & (dd < hi) & np.isfinite(r)
        s = band & mask
        ns = band & ~mask
        if s.sum() >= 5 and ns.sum() >= 20:
            diff = r[s].mean() - r[ns].mean()
            rows.append({"band": f"[{lo:.0%},{hi:.0%})", "signal_days": int(s.sum()), "signal_mean": float(r[s].mean()),
                         "other_days": int(ns.sum()), "other_mean": float(r[ns].mean()), "diff": float(diff)})
            wdiff += diff * s.sum()
            wsum += s.sum()
    return {"bands": rows, "weighted_diff": float(wdiff / wsum) if wsum else None, "matched_signal_days": int(wsum)}


def correction_episodes(frame: pd.DataFrame, depth: float = -0.10, merge_gap: int = 10) -> list[dict]:
    dd = frame["dd252"].to_numpy(float)
    c = frame["close"].to_numpy(float)
    deep = np.flatnonzero(dd <= depth)
    eps = []
    if len(deep) == 0:
        return eps
    start = deep[0]
    prev = deep[0]
    for i in list(deep[1:]) + [None]:
        if i is None or i - prev > merge_gap:
            seg = np.arange(start, prev + 1)
            trough = seg[np.argmin(c[seg])]
            # walk back to the first day of the selloff (drawdown <= -5%)
            s5 = start
            while s5 > 0 and dd[s5 - 1] <= -0.05:
                s5 -= 1
            eps.append({"start5": int(s5), "start10": int(start), "trough": int(trough), "end": int(prev),
                        "depth": float(dd[trough])})
            if i is not None:
                start = i
        if i is not None:
            prev = i
    return eps


def timing(frame: pd.DataFrame, eps: list[dict], mask: np.ndarray, k: int = 10) -> dict:
    ent_idx = np.flatnonzero(entries(mask))
    dates = frame["date"].to_numpy()
    rows = []
    hit = 0
    for e in eps:
        lo, hi = e["start5"] - 5, e["end"] + 21
        inside = ent_idx[(ent_idx >= lo) & (ent_idx <= hi)]
        first = int(inside[0]) if len(inside) else None
        nearest = int(inside[np.argmin(np.abs(inside - e["trough"]))]) if len(inside) else None
        near = nearest is not None and abs(nearest - e["trough"]) <= k
        hit += int(near)
        c = frame["close"].to_numpy(float)
        rows.append({
            "trough_date": str(dates[e["trough"]]), "depth": round(e["depth"] * 100, 1),
            "first_signal": None if first is None else str(dates[first]),
            "first_minus_trough_sessions": None if first is None else first - e["trough"],
            "decline_done_at_first_pct": None if first is None else round(
                100 * (1 - (c[first] - c[e["trough"]]) / max(c[e["start5"]] - c[e["trough"]], 1e-9)), 0),
            "nearest_minus_trough": None if nearest is None else nearest - e["trough"],
        })
    # precision: entries within +/-k sessions of ANY episode trough
    troughs = np.array([e["trough"] for e in eps])
    prec = float(np.mean([np.min(np.abs(troughs - i)) <= k for i in ent_idx])) if len(ent_idx) and len(troughs) else None
    return {"recall_at_k": hit / len(eps) if eps else None, "precision_at_k": prec, "k": k,
            "signal_entries": int(len(ent_idx)), "episodes": len(eps), "rows": rows}


def panic_deciles(frame: pd.DataFrame, score: str, key: str = "r_nc") -> dict:
    s = frame[score].to_numpy(float)
    out = {}
    q = pd.qcut(pd.Series(s), 10, labels=False, duplicates="drop").to_numpy()
    for h in (5, 21, 63, 252):
        r = frame[f"{key}_{h}"].to_numpy(float)
        ok = np.isfinite(r) & np.isfinite(s)
        tab = []
        for d in range(10):
            m = ok & (q == d)
            if m.any():
                tab.append({"decile": d + 1, "score_lo": float(np.nanmin(s[m])), "score_hi": float(np.nanmax(s[m])),
                            "mean": float(r[m].mean()), "hit": float((r[m] > 0).mean()), "n": int(m.sum())})
        z = (s - np.nanmean(s)) / np.nanstd(s)
        beta, se = su.nw_ollsafe(r[ok], np.column_stack([np.ones(ok.sum()), z[ok]]), h)
        out[f"h{h}"] = {"ic": su.spearman(s[ok], r[ok]), "slope_per_sd": float(beta[1]), "slope_t_nw": float(beta[1] / se[1]) if se[1] > 0 else None,
                        "deciles": tab}
    fv = frame["fwd_vol21"].to_numpy(float)
    ok = np.isfinite(fv) & np.isfinite(s)
    out["fwd_vol21_ic"] = su.spearman(s[ok], fv[ok])
    out["fwd_vol21_by_decile"] = [float(np.nanmean(fv[ok & (q == d)])) for d in range(10)]
    return out


def analyze(symbol: str, vix: pd.Series | None) -> dict:
    sig = pd.read_parquet(SIG / MANIFEST[symbol]["file"])
    frame = outcomes(bars(symbol)).merge(sig, on="date", how="inner")
    frame = frame.sort_values("date").reset_index(drop=True)
    st = frame["state"].to_numpy()
    raw = frame["raw_state"].to_numpy()
    meaningful = frame["exhaustion_meaningful"].to_numpy(bool)
    exh = frame["exhaustion"].to_numpy(float)
    panic = frame["panic"].to_numpy(float)
    conds = {
        "published_normal": st == 0, "published_observe": st == 1, "published_stress": st == 2,
        "published_exhaustion_candidate": st == 3, "published_confirmed": st == 4, "published_ge_stress": st >= 2,
        "raw_stress": raw == 2, "raw_exhaustion_candidate": raw == 3, "raw_confirmed": raw == 4, "raw_ge_candidate": raw >= 3,
        "meaningful": meaningful, "meaningful_exh_ge45": meaningful & (exh >= 45), "meaningful_exh_ge65": meaningful & (exh >= 65),
        "meaningful_exh_lt45": meaningful & (exh < 45),
        "panic_ge70": panic >= 70, "panic_ge80": panic >= 80, "panic_ge90": panic >= 90,
        "baseline_dd_le_10": frame["dd252"].to_numpy() <= -0.10, "baseline_dd_le_20": frame["dd252"].to_numpy() <= -0.20,
        "baseline_rsi_lt_30": frame["rsi14"].to_numpy() < 30, "baseline_ret5_le_-5": frame["ret5"].to_numpy() <= -0.05,
    }
    if vix is not None:
        v = vix.reindex(frame["date"]).to_numpy(float)
        conds["baseline_vix_ge_30"] = v >= 30
        conds["baseline_vix_ge_40"] = v >= 40
    result = {"symbol": symbol, "first": str(frame["date"].iloc[0]), "last": str(frame["date"].iloc[-1]), "sessions": len(frame),
              "conditions": {k: cond_stats(frame, m) for k, m in conds.items()}}
    result["conditions_next_open"] = {k: cond_stats(frame, m, "r_no") for k, m in conds.items() if k.startswith(("published", "raw", "meaningful"))}
    result["conditions_signal_close"] = {k: cond_stats(frame, m, "r_cc") for k, m in conds.items() if k.startswith(("published", "raw", "meaningful"))}
    result["deciles"] = {s: panic_deciles(frame, s) for s in ("panic", "pressure", "exhaustion")}
    result["deciles_in_drawdown"] = {s: panic_deciles(frame[frame["dd252"] <= -0.05].reset_index(drop=True), s) for s in ("panic", "exhaustion")}
    result["drawdown_matched"] = {k: drawdown_matched(frame, conds[k]) for k in (
        "published_ge_stress", "raw_ge_candidate", "meaningful_exh_ge65", "meaningful_exh_lt45", "panic_ge80", "baseline_rsi_lt_30")}
    eps = correction_episodes(frame)
    result["episodes"] = len(eps)
    result["timing"] = {k: timing(frame, eps, conds[k]) for k in (
        "published_ge_stress", "published_exhaustion_candidate", "raw_ge_candidate", "raw_confirmed",
        "meaningful_exh_ge65", "panic_ge80", "baseline_rsi_lt_30", "baseline_dd_le_20")}
    return result


def macro(symbol_file: str, symbol: str) -> dict:
    sig = pd.read_parquet(SIG / symbol_file)
    frame = outcomes(bars(symbol)).merge(sig[["date", "pressure", "panic", "exhaustion", "state", "phase"]], on="date")
    st = frame["state"].to_numpy()
    conds = {fear_vec.STATE_NAMES[c]: st == c for c in range(6)}
    conds["ge_candidate"] = st >= 3
    conds["phase_falling_knife"] = frame["phase"].to_numpy() == fear_vec.PHASE_CODES["falling_knife"]
    conds["phase_stabilizing"] = frame["phase"].to_numpy() == fear_vec.PHASE_CODES["stabilizing"]
    eps = correction_episodes(frame)
    return {"symbol": symbol, "first": str(frame["date"].iloc[0]), "sessions": len(frame),
            "conditions": {k: cond_stats(frame, m) for k, m in conds.items()},
            "deciles": {s: panic_deciles(frame, s) for s in ("panic", "pressure", "exhaustion")},
            "timing": {k: timing(frame, eps, conds[k]) for k in ("panic", "capitulation_candidate", "ge_candidate", "confirmed_exhaustion")},
            "drawdown_matched": {k: drawdown_matched(frame, conds[k]) for k in ("panic", "ge_candidate", "stress_building")}}


def main() -> int:
    vix = bars("^VIX").set_index("date")["close"]
    out = {"ladder": {}, "macro": {}}
    for symbol in ["SPY", "^GSPC", "QQQ", "IWM", "DIA", "^NDX", "^RUT", "EFA", "EEM", "EWJ", "HYG", "LQD", "TLT",
                   "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]:
        out["ladder"][symbol] = analyze(symbol, vix if symbol in ("SPY", "^GSPC", "QQQ", "IWM", "DIA", "^NDX", "^RUT") else None)
        print("done", symbol, flush=True)
    out["macro"]["SPY"] = macro("SPY_macro_fear.parquet", "SPY")
    out["macro"]["^GSPC"] = macro("GSPC_macro_fear.parquet", "^GSPC")
    import gzip  # noqa: PLC0415

    with gzip.open(RES / "index_results.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), default=float)
    print("wrote results/index_results.json.gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
