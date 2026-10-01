"""Per-stock point-in-time signal replay + forward outcomes, one file per stock.

Benchmarks: US stocks use SPY (production); before SPY existed (1993-01-29) the
series is spliced to ^GSPC (price index, scaled at the splice). Relative-strength
inputs are production-identical from ~1996-05 onward; earlier rows are flagged
``era='extension'`` downstream.
"""
from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fear_vec  # noqa: E402
from common import BARS, DATA, STOCK_SIGNALS, manifest  # noqa: E402

OUT = STOCK_SIGNALS
OUT.mkdir(parents=True, exist_ok=True)
MANIFEST = manifest()
HORIZONS = [1, 5, 10, 21, 63, 126, 252]
F32 = np.float32


def load(symbol: str) -> pd.DataFrame:
    return fear_vec.production_rows(pd.read_parquet(BARS / MANIFEST[symbol]["file"]))


_BENCH_CACHE: dict[str, pd.Series] = {}


def benchmark(symbol: str) -> pd.Series:
    if symbol in _BENCH_CACHE:
        return _BENCH_CACHE[symbol]
    if symbol == "SPY":
        spy = load("SPY").set_index("date")["close"]
        gspc = load("^GSPC").set_index("date")["close"]
        first = spy.index[0]
        scale = spy.iloc[0] / gspc.loc[first]
        early = gspc[gspc.index < first] * scale
        series = pd.concat([early, spy])
    else:
        series = load(symbol).set_index("date")["close"]
    _BENCH_CACHE[symbol] = series
    return series


def fwd(c: np.ndarray, h: int, lag: int = 0) -> np.ndarray:
    """c[t+lag+h] / c[t+lag] - 1."""
    n = len(c)
    out = np.full(n, np.nan)
    if n > h + lag:
        out[: n - h - lag] = c[h + lag:] / c[lag: n - h] - 1.0
    return out


def run(symbol: str) -> tuple[str, int, float, str | None]:
    t0 = time.time()
    meta = MANIFEST[symbol]
    target = OUT / meta["file"]
    if target.exists():
        return symbol, -1, 0.0, None
    try:
        df = load(symbol)
        if len(df) < 120:
            return symbol, len(df), 0.0, "fewer than 120 rows"
        bsym = meta.get("benchmark") or "SPY"
        bench = benchmark(bsym)
        sig = fear_vec.compute(df, bench)
        c = df["close"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)
        h_ = df["high"].to_numpy(dtype=float)
        l_ = df["low"].to_numpy(dtype=float)
        n = len(c)
        bc = bench.reindex(df["date"]).ffill().to_numpy(dtype=float)
        cols: dict[str, np.ndarray] = {}
        o1 = np.concatenate([o[1:], [np.nan]])
        hi1 = np.concatenate([h_[1:], [np.nan]])
        lo1 = np.concatenate([l_[1:], [np.nan]])
        open_ok = np.isfinite(o1) & (o1 > 0) & (o1 <= hi1 * 1.0001) & (o1 >= lo1 * 0.9999)
        for hz in HORIZONS:
            cols[f"r_cc_{hz}"] = fwd(c, hz)            # signal close -> close t+h
            cols[f"r_nc_{hz}"] = fwd(c, hz, lag=1)     # next close -> close t+1+h
            exit_c = np.full(n, np.nan)
            if n > hz:
                exit_c[: n - hz] = c[hz:]
            cols[f"r_no_{hz}"] = np.where(open_ok, exit_c / np.where(open_ok, o1, 1.0) - 1.0, np.nan)  # next open -> close t+h
            cols[f"b_cc_{hz}"] = fwd(bc, hz)
            cols[f"b_nc_{hz}"] = fwd(bc, hz, lag=1)
        # path risk after the signal (closes t+1..t+h vs signal close)
        for hz in (21, 63):
            win = pd.Series(c[::-1]).rolling(hz, min_periods=hz).agg(["min", "max"]).to_numpy()[::-1]
            # win[t] covers c[t..t+hz-1]; shift by one to get c[t+1..t+hz]
            mn = np.concatenate([win[1:, 0], [np.nan]])
            mx = np.concatenate([win[1:, 1], [np.nan]])
            cols[f"mae_{hz}"] = mn / c - 1.0
            cols[f"mfe_{hz}"] = mx / c - 1.0
        lr = np.full(n, np.nan)
        lr[1:] = np.log(c[1:] / c[:-1])
        fv = pd.Series(lr[::-1]).rolling(21, min_periods=21).std().to_numpy()[::-1] * np.sqrt(252)
        cols["fwd_vol21"] = np.concatenate([fv[1:], [np.nan]])
        # trailing controls
        c_21 = np.full(n, np.nan)
        c_252 = np.full(n, np.nan)
        if n > 21:
            c_21[21:] = c[:-21]
        if n > 252:
            c_252[252:] = c[:-252]
        cols["mom_12_1"] = c_21 / c_252 - 1.0
        r1 = np.concatenate([[np.nan], c[1:] / c[:-1] - 1.0])
        r1n = np.concatenate([r1[1:], [np.nan]])
        cols["spike"] = ((r1 > 1.0) & (r1n < -0.5)) | ((r1 < -0.5) & (r1n > 1.0))
        cols["hist_rows"] = np.arange(1, n + 1)
        out = sig.copy()
        out.insert(1, "close", c)
        for k, v in cols.items():
            out[k] = v
        for k in out.columns:
            if out[k].dtype == np.float64:
                out[k] = out[k].astype(F32)
        out["hist_rows"] = out["hist_rows"].astype(np.int32)
        out.to_parquet(target, index=False)
        return symbol, n, time.time() - t0, None
    except Exception as exc:  # noqa: BLE001
        return symbol, 0, time.time() - t0, repr(exc)[:300]


def main(workers: int = 2) -> int:
    symbols = [s for s, m in MANIFEST.items() if m.get("kind") == "stock" and not m.get("error")]
    symbols.sort(key=lambda s: -MANIFEST[s].get("rows", 0))
    print(f"{len(symbols)} stocks, workers={workers}", flush=True)
    errors = {}
    done = 0
    with Pool(workers, maxtasksperchild=40) as pool:
        for symbol, n, secs, err in pool.imap_unordered(run, symbols):
            done += 1
            if err:
                errors[symbol] = err
                print(f"ERR {symbol}: {err}", flush=True)
            if done % 25 == 0:
                print(f"{done}/{len(symbols)} last={symbol} n={n} {secs:.1f}s", flush=True)
    (DATA / "stock_batch_errors.json").write_text(json.dumps(errors, indent=1))
    print(f"done, errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2))
