"""Stage 1 (streaming, one stock at a time):
  * per-stock time-series predictive statistics (IC, NW t, circular-shift null)
  * global bucket accumulators (score bins, states, phases) by era  [vectorized]
  * state-entry event rows                                           [streamed]
  * a thin panel for the cross-sectional stage                       [streamed]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fear_vec  # noqa: E402
import stats_util as su  # noqa: E402
from common import EVENTS, RESULTS as RES, STOCK_SIGNALS as SIG, THIN_PANEL, manifest  # noqa: E402

MANIFEST = manifest()
EXCLUDE = {"DNP"}  # DNP.WA resolves to the DNP Select Income Fund on Yahoo: wrong security
H = [5, 21, 63, 126, 252]
MIN_HIST = 756  # full 3-year percentile window ("grade A" history)
ERAS = [("1962-1989", "1900", "1990"), ("1990-1999", "1990", "2000"), ("2000-2009", "2000", "2010"),
        ("2010-2019", "2010", "2020"), ("2020-2026", "2020", "2100")]
ERA_NAMES = [e[0] for e in ERAS] + ["ALL"]
SCORES = ["panic", "pressure", "exhaustion"]
DIMS = ["panic", "pressure", "exhaustion", "state", "phase", "direction", "all"]
NB = 16
NULL_SHIFTS = 40
BAD_MOVE = float(np.log(3.0))  # a one-day move of more than 3x up or down
CONTAM = 252
OUTCOMES = [f"r{h}" for h in H] + [f"x{h}" for h in H] + ["mae63", "vol21", "r_no21", "r_cc21", "x_cc21", "mae63_lt_15"]
COLS = (["date", "close", "hist_rows", "spike", "panic", "pressure", "exhaustion", "coverage", "state", "phase", "direction",
         "confirmations", "trend_z", "stretch_z", "rsi14", "f_return_5d", "f_return_20d", "mom_12_1", "f_rv_20d",
         "f_drawdown_252d", "f_distance_50d", "mae_21", "mae_63", "mfe_63", "fwd_vol21"]
        + [f"r_nc_{h}" for h in H] + [f"b_nc_{h}" for h in H] + ["r_no_21", "r_no_63", "r_cc_21", "r_cc_63", "b_cc_21", "b_cc_63"])
EVENT_COLS = ["date", "panic", "pressure", "exhaustion", "state", "f_drawdown_252d", "f_return_5d", "mae_63", "mfe_63", "fwd_vol21",
              *[f"r_nc_{h}" for h in H], *[f"x_nc_{h}" for h in H], "r_no_21", "r_cc_21"]


def era_index(dates: np.ndarray) -> np.ndarray:
    out = np.full(len(dates), -1, dtype=np.int64)
    for i, (_, lo, hi) in enumerate(ERAS):
        out[(dates >= lo) & (dates < hi)] = i
    return out


def ts_stats(score: np.ndarray, r: np.ndarray, h: int, rng: np.random.Generator, null: bool = True) -> dict:
    ok = np.isfinite(score) & np.isfinite(r)
    if ok.sum() < 252 + h:
        return {"ic": np.nan, "t": np.nan, "n": int(ok.sum()), "null_sd": np.nan, "null_p": np.nan}
    s = score[ok]
    y = r[ok]
    rs = su._rank(y)
    ss = su._rank(s)
    ic = float(np.corrcoef(ss, rs)[0, 1])
    z = (s - s.mean()) / (s.std() or 1.0)
    beta, se = su.nw_ollsafe(y, np.column_stack([np.ones(len(z)), z]), h)
    out = {"ic": ic, "t": beta[1] / se[1] if se[1] > 0 else np.nan, "slope": beta[1], "n": int(len(s))}
    if null:
        # circular-shift null: keeps both series' autocorrelation, breaks alignment
        n = len(s)
        shifts = rng.integers(252, max(253, n - 252), size=NULL_SHIFTS) if n > 600 else rng.integers(1, n, size=NULL_SHIFTS)
        nul = np.array([np.corrcoef(np.roll(ss, k), rs)[0, 1] for k in shifts])
        out["null_sd"] = float(np.nanstd(nul))
        out["null_p"] = float(np.mean(np.abs(nul) >= abs(ic)))
    return out


def main(limit: int = 0) -> int:
    res = RES if not limit else HERE / "results_smoke"
    res.mkdir(exist_ok=True)
    stocks = sorted((s, m) for s, m in MANIFEST.items() if m.get("kind") == "stock" and not m.get("error") and s not in EXCLUDE
                    and (SIG / m["file"]).exists())
    if limit:
        stocks = stocks[:limit]
    print(f"{len(stocks)} stock files", flush=True)
    acc = np.zeros((len(DIMS), len(ERA_NAMES), NB, len(OUTCOMES), 4))
    per_stock = []
    thin_writer = None
    ev_writer = None
    rng = np.random.default_rng(20261001)
    for k, (symbol, meta) in enumerate(stocks):
        df = pd.read_parquet(SIG / meta["file"], columns=COLS)
        n_all = len(df)
        cl = df["close"].to_numpy(float)
        lr1 = np.concatenate([[0.0], np.abs(np.diff(np.log(cl)))])
        jump = (lr1 > BAD_MOVE).astype(float)
        cs = np.concatenate([[0.0], np.cumsum(jump)])
        ii = np.arange(len(jump))
        contaminated = (cs[np.minimum(len(jump), ii + CONTAM + 1)] - cs[np.maximum(0, ii - CONTAM)]) > 0  # within +/-252 sessions of a >3x day
        spike = df["spike"].to_numpy(bool)
        bad = spike | np.concatenate([spike[1:], [False]]) | contaminated
        df = df[(df["hist_rows"].to_numpy() >= MIN_HIST) & ~bad].reset_index(drop=True)
        contaminated_rows = int(contaminated.sum())
        if len(df) < 300:
            per_stock.append({"symbol": symbol, "ticker": meta["ticker"], "usable_rows": len(df), "rows": n_all})
            continue
        dates = df["date"].to_numpy().astype(str)
        eidx = era_index(dates)
        for h in H:
            lr = np.log1p(df[f"r_nc_{h}"].clip(lower=-0.99))
            df[f"x_nc_{h}"] = lr - np.log1p(df[f"b_nc_{h}"].clip(lower=-0.99))  # log excess return vs benchmark
            df[f"r_nc_{h}"] = lr                                                  # log total return
        for c in ("r_no_21", "r_cc_21"):
            df[c] = np.log1p(df[c].clip(lower=-0.99))
        df["b_cc_21"] = np.log1p(df["b_cc_21"].clip(lower=-0.99))
        # ---- vectorized accumulators
        mae = df["mae_63"].to_numpy(float)
        outs = [df[f"r_nc_{h}"].to_numpy(float) for h in H] + [df[f"x_nc_{h}"].to_numpy(float) for h in H] + [
            mae, df["fwd_vol21"].to_numpy(float), df["r_no_21"].to_numpy(float), df["r_cc_21"].to_numpy(float),
            (df["r_cc_21"] - df["b_cc_21"]).to_numpy(float),
            np.where(np.isfinite(mae), (mae < -0.15).astype(float) - 0.5, np.nan),  # npos/n = P(MAE63 < -15%)
        ]
        buckets = {}
        for s in SCORES:
            v = df[s].to_numpy(float)
            buckets[s] = np.where(np.isfinite(v), np.clip(np.floor(v / 10.0), 0, 9), -1).astype(np.int64)
        for c in ("state", "phase", "direction"):
            buckets[c] = df[c].to_numpy(np.int64)
        buckets["all"] = np.zeros(len(df), dtype=np.int64)
        for di, dim in enumerate(DIMS):
            b = buckets[dim]
            for era_slot, emask in ((None, eidx >= 0), (len(ERA_NAMES) - 1, np.ones(len(df), bool))):
                key_era = eidx if era_slot is None else np.full(len(df), era_slot)
                valid_key = emask & (b >= 0) & (b < NB)
                key = key_era * NB + b
                for oi, v in enumerate(outs):
                    m = valid_key & np.isfinite(v)
                    if not m.any():
                        continue
                    kk = key[m]
                    vv = v[m]
                    size = len(ERA_NAMES) * NB
                    s1 = np.bincount(kk, weights=vv, minlength=size)
                    s2 = np.bincount(kk, weights=vv * vv, minlength=size)
                    cnt = np.bincount(kk, minlength=size)
                    pos = np.bincount(kk, weights=(vv > 0).astype(float), minlength=size)
                    acc[di, :, :, oi, 0] += s1.reshape(len(ERA_NAMES), NB)
                    acc[di, :, :, oi, 1] += s2.reshape(len(ERA_NAMES), NB)
                    acc[di, :, :, oi, 2] += cnt.reshape(len(ERA_NAMES), NB)
                    acc[di, :, :, oi, 3] += pos.reshape(len(ERA_NAMES), NB)
        # ---- per-stock time series predictive stats
        rec = {"symbol": symbol, "ticker": meta["ticker"], "benchmark": meta.get("benchmark"), "rows": n_all,
               "usable_rows": len(df), "first": dates[0], "last": dates[-1], "contaminated_rows": contaminated_rows}
        st = df["state"].to_numpy(int)
        for name, code in fear_vec.STATE_CODES.items():
            rec[f"days_{name}"] = int((st == code).sum())
        prev = np.concatenate([[0], st[:-1]])
        rec["entries_panic_or_worse"] = int(((st >= 2) & (prev < 2)).sum())
        rec["entries_candidate_or_worse"] = int(((st >= 3) & (prev < 3)).sum())
        for s in SCORES:
            for h in (21, 63, 252):
                for kind in ("r", "x"):
                    if s != "panic" and h == 252:
                        continue
                    res_ = ts_stats(df[s].to_numpy(float), df[f"{kind}_nc_{h}"].to_numpy(float), h, rng, null=True)
                    for key_, val in res_.items():
                        rec[f"{s}_{kind}{h}_{key_}"] = val
        pv = df["panic"].to_numpy(float)
        for h in (21, 63, 252):
            x = df[f"x_nc_{h}"].to_numpy(float)
            r = df[f"r_nc_{h}"].to_numpy(float)
            hi = pv >= 70
            lo = pv < 30
            rec[f"r{h}_all"] = float(np.nanmean(r))
            rec[f"x{h}_all"] = float(np.nanmean(x))
            rec[f"r{h}_panic70"] = float(np.nanmean(r[hi])) if np.isfinite(r[hi]).any() else np.nan
            rec[f"x{h}_panic70"] = float(np.nanmean(x[hi])) if np.isfinite(x[hi]).any() else np.nan
            rec[f"hit_x{h}_panic70"] = float(np.mean(x[hi & np.isfinite(x)] > 0)) if (hi & np.isfinite(x)).any() else np.nan
            rec[f"hit_x{h}_all"] = float(np.mean(x[np.isfinite(x)] > 0))
            rec[f"x{h}_panic_lt30"] = float(np.nanmean(x[lo])) if np.isfinite(x[lo]).any() else np.nan
        per_stock.append(rec)
        # ---- state entry events (streamed)
        ph = df["phase"].to_numpy(int)
        prevph = np.concatenate([[-1], ph[:-1]])
        frames = []
        for label, mask in {
            "stress_building": (st == 1) & (prev == 0),
            "panic_or_worse": (st >= 2) & (prev < 2),
            "candidate_or_worse": (st >= 3) & (prev < 3),
            "emerging_or_confirmed": (st >= 4) & (prev < 4),
            "confirmed_exhaustion": (st == 5) & (prev != 5),
            "phase_falling_knife": (ph == 4) & (prevph != 4),
            "phase_stabilizing": (ph == 3) & (prevph != 3),
        }.items():
            idx = np.flatnonzero(mask)
            if len(idx) == 0:
                continue
            ev = df.iloc[idx][EVENT_COLS].copy()
            ev.insert(0, "event", label)
            ev.insert(0, "symbol", symbol)
            frames.append(ev)
        if frames:
            evs = pd.concat(frames, ignore_index=True)
            for c in evs.columns:
                if evs[c].dtype == np.float64:
                    evs[c] = evs[c].astype("float32")
            evs["state"] = evs["state"].astype("int8")
            table = pa.Table.from_pandas(evs, preserve_index=False)
            if ev_writer is None:
                ev_writer = pq.ParquetWriter(EVENTS if not limit else res / "events.parquet", table.schema)
            ev_writer.write_table(table.cast(ev_writer.schema))
        # ---- thin panel for cross-section (streamed)
        thin = pd.DataFrame({
            "date": np.char.replace(dates.astype("U10"), "-", "").astype(np.int32), "sid": np.int16(k),
            "panic": df["panic"].astype("float32"), "pressure": df["pressure"].astype("float32"),
            "exhaustion": df["exhaustion"].astype("float32"), "state": df["state"].astype("int8"), "phase": df["phase"].astype("int8"),
            "ret5": df["f_return_5d"].astype("float32"), "ret20": df["f_return_20d"].astype("float32"), "mom": df["mom_12_1"].astype("float32"),
            "rv20": df["f_rv_20d"].astype("float32"), "dd252": df["f_drawdown_252d"].astype("float32"), "rsi14": df["rsi14"].astype("float32"),
            "x21": df["x_nc_21"].astype("float32"), "x63": df["x_nc_63"].astype("float32"), "x252": df["x_nc_252"].astype("float32"),
            "r21": df["r_nc_21"].astype("float32"), "r63": df["r_nc_63"].astype("float32"), "r5": df["r_nc_5"].astype("float32"),
            "x5": df["x_nc_5"].astype("float32"), "mae63": df["mae_63"].astype("float32"), "vol21": df["fwd_vol21"].astype("float32"),
            "us": np.bool_(meta.get("benchmark") == "SPY"),
        })
        table = pa.Table.from_pandas(thin, preserve_index=False)
        if thin_writer is None:
            thin_writer = pq.ParquetWriter(THIN_PANEL if not limit else res / "thin_panel.parquet", table.schema)
        thin_writer.write_table(table)
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/{len(stocks)}", flush=True)
    for w in (thin_writer, ev_writer):
        if w is not None:
            w.close()
    rows = []
    for di, dim in enumerate(DIMS):
        for ei, era in enumerate(ERA_NAMES):
            for b in range(NB):
                for oi, o in enumerate(OUTCOMES):
                    a = acc[di, ei, b, oi]
                    if a[2] > 0:
                        rows.append((dim, era, b, o, *a))
    pd.DataFrame(rows, columns=["dim", "era", "bucket", "outcome", "sum", "sumsq", "n", "npos"]).to_parquet(res / "bucket_acc.parquet", index=False)
    pd.DataFrame(per_stock).to_parquet(res / "per_stock.parquet", index=False)
    (res / "sids.json").write_text(json.dumps({k: s for k, (s, _) in enumerate(stocks)}))
    print("stage1 done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 0))
