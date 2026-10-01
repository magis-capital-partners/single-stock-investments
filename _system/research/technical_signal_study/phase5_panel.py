"""Phase 5b: one enriched, point-in-time stock-day panel shared by phases 5 and 7.

Adds to every replayed stock-day (dashboard names + former S&P 500 members):

* beta        rolling 252-session OLS beta of daily log returns vs the stock's
              benchmark, using data up to and including the day (>=126 obs);
* resid21/63  forward log return minus beta x benchmark forward log return
              (beta-adjusted, so a high-beta rebound is not counted as skill);
* idio5/20    trailing company-specific log return: own minus beta x benchmark;
* sys5/20     trailing market-driven log return: beta x benchmark;
* spread      Abdi-Ranaldo (2017) close-high-low effective spread estimate,
              21-session mean of day-(t-1, t) products, floored at 0;
* dvol        log 20-session average dollar volume;
* member      S&P 500 membership on the day (point-in-time, from phase5_universe).

Rows follow stock_stage1's filters: full 756-session percentile window, no
window within +/-252 sessions of a >3x one-day move, no spike days.
"""
from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fear_vec  # noqa: E402
from common import BARS, DATA, STOCK_SIGNALS, manifest  # noqa: E402

PANEL = DATA / "phase5_panel.parquet"
MEMBERSHIP = DATA / "sp500_membership.parquet"
MIN_HIST = 756
BAD_MOVE = float(np.log(3.0))
CONTAM = 252
EXCLUDE = {"DNP"}
SIG_COLS = (["date", "close", "hist_rows", "spike", "panic", "pressure", "exhaustion", "coverage", "state", "phase", "direction",
             "confirmations", "trend_z", "stretch_z", "relative60_z", "rsi14", "cmf20",
             "fam_price_dislocation", "fam_selling_climax", "fam_volatility_stress", "fam_relative_path_stress",
             "f_return_5d", "f_return_20d", "mom_12_1", "f_rv_20d", "f_drawdown_252d", "f_distance_50d", "f_volume_log_20d",
             "f_close_location", "mae_63", "mfe_63", "fwd_vol21",
             "r_nc_5", "r_nc_21", "r_nc_63", "r_nc_252", "b_nc_5", "b_nc_21", "b_nc_63", "b_nc_252"])
PCT_COLS = ["pct_return_1d_fear", "pct_return_5d_fear", "pct_return_20d_fear", "pct_drawdown_fear", "pct_distance_50d_fear",
            "pct_volume_climax", "pct_range_climax", "pct_gap_fear", "pct_volatility_fear", "pct_vol_acceleration", "pct_vcr",
            "pct_trend_shape", "pct_negative_consistency", "pct_downside_share"]

_MAN = None
_BENCH: dict[str, pd.Series] = {}
_MEM: pd.DataFrame | None = None


def _init():
    global _MAN, _MEM
    _MAN = manifest()
    _MEM = pd.read_parquet(MEMBERSHIP) if MEMBERSHIP.exists() else pd.DataFrame()


def bench_close(symbol: str) -> pd.Series:
    if symbol not in _BENCH:
        if symbol == "SPY":
            spy = fear_vec.production_rows(pd.read_parquet(BARS / _MAN["SPY"]["file"])).set_index("date")["close"]
            gspc = fear_vec.production_rows(pd.read_parquet(BARS / _MAN["^GSPC"]["file"])).set_index("date")["close"]
            scale = spy.iloc[0] / gspc.loc[spy.index[0]]
            _BENCH[symbol] = pd.concat([gspc[gspc.index < spy.index[0]] * scale, spy])
        else:
            _BENCH[symbol] = fear_vec.production_rows(pd.read_parquet(BARS / _MAN[symbol]["file"])).set_index("date")["close"]
    return _BENCH[symbol]


def membership_mask(symbol: str, dates: np.ndarray) -> np.ndarray:
    out = np.zeros(len(dates), dtype=bool)
    if _MEM is None or _MEM.empty:
        return out
    if symbol.endswith(".VENDOR"):  # vendor history for a member Yahoo no longer serves
        base = symbol[: -len(".VENDOR")]
        rows = _MEM[(_MEM["ticker"] == base) & _MEM["coverage"].astype(str).str.startswith("missing")]
    else:
        rows = _MEM[(_MEM["yahoo"] == symbol) & _MEM["coverage"].isin(["ok", "reused_or_late"])]
    for r in rows.itertuples(index=False):
        end = r.end if isinstance(r.end, str) and r.end not in ("None", "NaT", "nan", "") else "2100-01-01"
        start = r.start if isinstance(r.start, str) and r.start not in ("None", "NaT", "nan", "") else "1900-01-01"
        out |= (dates >= start) & (dates < end)
    return out


def one(symbol: str):
    meta = _MAN[symbol]
    path = STOCK_SIGNALS / meta["file"]
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path, columns=SIG_COLS + PCT_COLS)
    except Exception:  # noqa: BLE001
        return None
    bars = fear_vec.production_rows(pd.read_parquet(BARS / meta["file"]))
    bars = bars.set_index("date").reindex(df["date"])
    n = len(df)
    c = df["close"].to_numpy(float)
    lr1 = np.concatenate([[0.0], np.diff(np.log(c))])
    jump = (np.abs(lr1) > BAD_MOVE).astype(float)
    cs = np.concatenate([[0.0], np.cumsum(jump)])
    ii = np.arange(n)
    contaminated = (cs[np.minimum(n, ii + CONTAM + 1)] - cs[np.maximum(0, ii - CONTAM)]) > 0
    spike = df["spike"].to_numpy(bool)
    keep = (df["hist_rows"].to_numpy() >= MIN_HIST) & ~contaminated & ~spike & ~np.concatenate([spike[1:], [False]])

    # beta (point-in-time) vs the stock's benchmark
    bsym = meta.get("benchmark") or "SPY"
    b = bench_close(bsym).reindex(df["date"]).ffill().to_numpy(float)
    rs = pd.Series(lr1)
    rb = pd.Series(np.concatenate([[np.nan], np.diff(np.log(b))]))
    cov = rs.rolling(252, min_periods=126).cov(rb)
    var = rb.rolling(252, min_periods=126).var()
    beta = (cov / var).clip(-1.0, 4.0).to_numpy()
    beta = np.where(np.isfinite(beta), beta, 1.0)

    def lg(x):
        return np.log1p(np.clip(np.asarray(x, float), -0.99, None))

    out = pd.DataFrame({"date": np.char.replace(df["date"].to_numpy().astype("U10"), "-", "").astype(np.int32)})
    out["sym"] = symbol
    for col in SIG_COLS[1:] + PCT_COLS:
        if col in ("hist_rows", "spike", "close"):
            continue
        v = df[col]
        out[col] = v.astype("float32") if v.dtype.kind == "f" else v
    for h in (5, 21, 63, 252):
        r = lg(df[f"r_nc_{h}"])
        bb = lg(df[f"b_nc_{h}"])
        out[f"lr{h}"] = r.astype("float32")
        out[f"x{h}"] = (r - bb).astype("float32")
        out[f"resid{h}"] = (r - beta * bb).astype("float32")
    out = out.drop(columns=[f"r_nc_{h}" for h in (5, 21, 63, 252)] + [f"b_nc_{h}" for h in (5, 21, 63, 252)])
    sp5 = pd.Series(np.log(b)).diff(5).to_numpy()
    sp20 = pd.Series(np.log(b)).diff(20).to_numpy()
    own5 = lg(df["f_return_5d"])
    own20 = lg(df["f_return_20d"])
    out["beta"] = beta.astype("float32")
    out["sys5"] = (beta * sp5).astype("float32")
    out["sys20"] = (beta * sp20).astype("float32")
    out["idio5"] = (own5 - beta * sp5).astype("float32")
    out["idio20"] = (own20 - beta * sp20).astype("float32")
    # Abdi-Ranaldo (2017) spread, point-in-time
    hi = np.log(bars["high"].to_numpy(float))
    lo = np.log(bars["low"].to_numpy(float))
    lc = np.log(bars["close"].to_numpy(float))
    eta = (hi + lo) / 2.0
    prod = (np.concatenate([[np.nan], lc[:-1]]) - np.concatenate([[np.nan], eta[:-1]])) * (np.concatenate([[np.nan], lc[:-1]]) - eta)
    s2 = 4.0 * pd.Series(prod).rolling(21, min_periods=10).mean().to_numpy()
    out["spread"] = np.sqrt(np.clip(s2, 0.0, None)).astype("float32")
    vol = bars["volume"].to_numpy(float)
    dv = pd.Series(np.where(np.isfinite(vol) & (vol > 0), vol * bars["close"].to_numpy(float), np.nan)).rolling(20, min_periods=10).mean()
    out["dvol"] = np.log(dv.to_numpy()).astype("float32")
    out["member"] = membership_mask(symbol, df["date"].to_numpy().astype(str))
    out["us"] = bool(bsym == "SPY")
    out["dash"] = meta.get("kind") == "stock"
    return out[keep].reset_index(drop=True)


def main(workers: int = 2) -> int:
    _init()
    syms = sorted(s for s, m in _MAN.items() if m.get("kind") in ("stock", "pit_extra", "vendor_delisted") and not m.get("error") and s not in EXCLUDE)
    writer = None
    done = 0
    rows = 0
    with Pool(workers, initializer=_init, maxtasksperchild=60) as pool:
        for part in pool.imap_unordered(one, syms, chunksize=4):
            done += 1
            if part is None or part.empty:
                continue
            table = pa.Table.from_pandas(part, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(PANEL, table.schema)
            writer.write_table(table.cast(writer.schema))
            rows += len(part)
            if done % 100 == 0:
                print(f"{done}/{len(syms)} rows={rows:,}", flush=True)
    if writer:
        writer.close()
    print(f"panel written: {rows:,} rows -> {PANEL}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2))
