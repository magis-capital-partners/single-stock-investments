"""Oracle test: vectorized replay vs production calculate_snapshot.

For random (ticker, date) pairs, feed production exactly what the nightly job
would have fetched on that date (5y calendar window of adjusted OHLCV + the
benchmark over the same window) and compare every published score.
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BARS, SCRIPTS, manifest  # noqa: E402

sys.path.insert(0, str(SCRIPTS))

import build_technical_signals as bts  # noqa: E402  production oracle
import fear_vec  # noqa: E402

MANIFEST = manifest()


def load(symbol: str) -> pd.DataFrame:
    raw = pd.read_parquet(BARS / MANIFEST[symbol]["file"])
    return fear_vec.production_rows(raw)


def as_rows(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for rec in frame.itertuples(index=False):
        rows.append({
            "date": rec.date,
            "open": None if not math.isfinite(rec.open) else rec.open,
            "high": None if not math.isfinite(rec.high) else rec.high,
            "low": None if not math.isfinite(rec.low) else rec.low,
            "close": rec.close,
            "volume": None if not math.isfinite(rec.volume) else rec.volume,
        })
    return rows


def main(n_tickers: int = 40, per_ticker: int = 8, seed: int = 7) -> int:
    rng = random.Random(seed)
    spy = load("SPY")
    bench = spy.set_index("date")["close"]
    stocks = [s for s, m in MANIFEST.items() if m.get("kind") == "stock" and m.get("benchmark") == "SPY" and not m.get("error")]
    picks = rng.sample(stocks, n_tickers)
    fields_1 = ["pressure", "panic", "exhaustion", "coverage"]
    fams = ["price_dislocation", "selling_climax", "volatility_stress", "relative_path_stress"]
    worst = {}
    mismatches = []
    checked = 0
    for symbol in picks:
        df = load(symbol)
        if len(df) < 400:
            continue
        vec = fear_vec.compute(df, bench)
        valid = [i for i in range(300, len(df)) if df["date"].iloc[i] >= "1994-06-01"]
        if not valid:
            continue
        for t in rng.sample(valid, min(per_ticker, len(valid))):
            end = df["date"].iloc[t]
            start = (date.fromisoformat(end) - timedelta(days=bts.LOOKBACK_DAYS)).isoformat()
            window = df[(df["date"] >= start) & (df["date"] <= end)]
            bwin = spy[(spy["date"] >= start) & (spy["date"] <= end)]
            if len(window) < 120:
                continue
            snap = bts.calculate_snapshot(symbol, as_rows(window), benchmark_rows=as_rows(bwin), benchmark="SPY", source="parity")
            cap = snap["capitulation"]
            row = vec.iloc[t]
            checked += 1

            def cmp(name, prod, mine, digits):
                if prod is None and (mine is None or not np.isfinite(mine)):
                    return
                if prod is None or mine is None or not np.isfinite(mine):
                    mismatches.append((symbol, end, name, prod, mine))
                    return
                d = abs(prod - round(float(mine), digits))
                worst[name] = max(worst.get(name, 0.0), d)
                if d > 1.5 * 10 ** (-digits):
                    mismatches.append((symbol, end, name, prod, round(float(mine), digits)))

            for k in fields_1:
                key = "confidence" if k == "coverage" else k
                cmp(k, cap["scores"][key], row[k], 1)
            for k in fams:
                cmp(k, cap["families"][k], row[f"fam_{k}"], 1)
            for k, v in cap["percentiles"].items():
                cmp("pct_" + k, v, row[f"pct_{k}"], 1)
            cmp("relative60_z", snap["scores"]["relative_strength_60d_z"], row["relative60_z"], 3)
            cmp("trend_z", snap["scores"]["trend_z"], row["trend_z"], 3)
            cmp("stretch_z", snap["scores"]["stretch_z"], row["stretch_z"], 3)
            if fear_vec.STATE_CODES[cap["state"]] != int(row["state"]):
                mismatches.append((symbol, end, "state", cap["state"], fear_vec.STATE_NAMES[int(row["state"])]))
            if fear_vec.PHASE_CODES[snap["setup"]["phase"]] != int(row["phase"]):
                mismatches.append((symbol, end, "phase", snap["setup"]["phase"], int(row["phase"])))
            if fear_vec.DIRECTION_CODES[snap["setup"]["direction"]] != int(row["direction"]):
                mismatches.append((symbol, end, "direction", snap["setup"]["direction"], int(row["direction"])))
            conf = cap["confirmation"]
            mine_conf = {"positive_session": row["conf_positive"], "closed_upper_half": row["conf_upper"],
                         "reclaimed_prior_high": row["conf_reclaimed"], "volume_cooled": row["conf_cooled"]}
            for k, v in conf.items():
                if bool(v) != bool(mine_conf[k]):
                    mismatches.append((symbol, end, k, v, mine_conf[k]))
    print(f"checked {checked} snapshots across {len(picks)} tickers")
    print("max abs diff by field:", json.dumps({k: round(v, 4) for k, v in sorted(worst.items())}))
    print(f"mismatches: {len(mismatches)}")
    for m in mismatches[:40]:
        print("  ", m)
    return 0 if not mismatches else 1


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    raise SystemExit(main(*args))
