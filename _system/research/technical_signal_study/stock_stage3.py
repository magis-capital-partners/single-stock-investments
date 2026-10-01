"""Stage 3: per-stock verdicts.

Each stock's time-series IC (panic vs its own forward return) is judged against
a circular-shift null built from the SAME stock (same autocorrelation, alignment
broken). z = IC / null_sd, Benjamini-Hochberg across stocks, then empirical-Bayes
shrinkage of each IC toward the cross-stock mean.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import RESULTS as RES  # noqa: E402


def bh(p: np.ndarray, q: float = 0.10) -> np.ndarray:
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), bool)
    ps = p[ok]
    order = np.argsort(ps)
    m = len(ps)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = ps[order] <= thresh
    if passed.any():
        kmax = np.max(np.flatnonzero(passed))
        sel = np.zeros(m, bool)
        sel[order[: kmax + 1]] = True
        out[np.flatnonzero(ok)] = sel
    return out


def shrink(ic: np.ndarray, se: np.ndarray) -> tuple[np.ndarray, float, float]:
    ok = np.isfinite(ic) & np.isfinite(se) & (se > 0)
    w = 1.0 / se[ok] ** 2
    mu = float(np.sum(w * ic[ok]) / np.sum(w))
    tau2 = float(max(0.0, np.var(ic[ok], ddof=1) - np.mean(se[ok] ** 2)))
    out = np.full(len(ic), np.nan)
    out[ok] = mu + tau2 / (tau2 + se[ok] ** 2) * (ic[ok] - mu)
    return out, mu, math.sqrt(tau2)


def main() -> int:
    ps = pd.read_parquet(RES / "per_stock.parquet")
    ps = ps[ps["usable_rows"] >= 756].reset_index(drop=True)  # >= 3 more years after the 3-year warm-up
    summary = {"stocks": int(len(ps))}
    for kind in ("x", "r"):
        for h in (21, 63, 252):
            ic = ps[f"panic_{kind}{h}_ic"].to_numpy(float)
            sd = ps[f"panic_{kind}{h}_null_sd"].to_numpy(float)
            z = ic / sd
            p = 2 * (1 - norm.cdf(np.abs(z)))
            sig = bh(p, 0.10)
            sh, mu, tau = shrink(ic, sd)
            ps[f"panic_{kind}{h}_z"] = z
            ps[f"panic_{kind}{h}_p"] = p
            ps[f"panic_{kind}{h}_fdr10"] = sig
            ps[f"panic_{kind}{h}_ic_shrunk"] = sh
            summary[f"{kind}{h}"] = {
                "mean_ic": float(np.nanmean(ic)), "median_ic": float(np.nanmedian(ic)),
                "share_positive": float(np.nanmean(ic > 0)),
                "share_p_lt_05": float(np.nanmean(p < 0.05)), "expected_under_null": 0.05,
                "share_p_lt_05_pos": float(np.nanmean((p < 0.05) & (ic > 0))),
                "share_p_lt_05_neg": float(np.nanmean((p < 0.05) & (ic < 0))),
                "fdr10_count": int(sig.sum()), "fdr10_pos": int((sig & (ic > 0)).sum()), "fdr10_neg": int((sig & (ic < 0)).sum()),
                "pooled_mu": mu, "between_stock_sd_tau": tau, "mean_null_sd": float(np.nanmean(sd)),
                "ic_quantiles": {str(q): float(np.nanquantile(ic, q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
                "r2_implied_median": float(np.nanmedian(ic ** 2)),
            }
    for s in ("exhaustion", "pressure"):
        for h in (21, 63):
            ic = ps[f"{s}_x{h}_ic"].to_numpy(float)
            sd = ps[f"{s}_x{h}_null_sd"].to_numpy(float)
            z = ic / sd
            p = 2 * (1 - norm.cdf(np.abs(z)))
            summary[f"{s}_x{h}"] = {"mean_ic": float(np.nanmean(ic)), "share_positive": float(np.nanmean(ic > 0)),
                                     "share_p_lt_05": float(np.nanmean(p < 0.05)), "fdr10_count": int(bh(p).sum())}
    # conditional means: panic >= 70 vs all days, per stock
    for h in (21, 63, 252):
        d = ps[f"x{h}_panic70"] - ps[f"x{h}_all"]
        summary[f"x{h}_panic70_minus_all"] = {"median": float(np.nanmedian(d)), "share_positive": float(np.nanmean(d > 0)),
                                              "n": int(np.isfinite(d).sum())}
    (RES / "per_stock_summary.json").write_text(json.dumps(summary, indent=1))
    keep = ["ticker", "symbol", "benchmark", "first", "last", "usable_rows", "days_panic", "days_capitulation_candidate",
            "days_exhaustion_emerging", "days_confirmed_exhaustion", "entries_panic_or_worse",
            "panic_x21_ic", "panic_x21_p", "panic_x63_ic", "panic_x63_p", "panic_x63_ic_shrunk", "panic_x63_fdr10",
            "panic_x252_ic", "panic_x252_p", "panic_r63_ic", "panic_r63_p",
            "exhaustion_x63_ic", "pressure_x63_ic",
            "x21_all", "x21_panic70", "x63_all", "x63_panic70", "hit_x63_all", "hit_x63_panic70", "x63_panic_lt30",
            "x252_all", "x252_panic70"]
    table = ps[[c for c in keep if c in ps.columns]].sort_values("panic_x63_ic")
    table.to_csv(RES / "per_stock_table.csv", index=False, float_format="%.4f")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
