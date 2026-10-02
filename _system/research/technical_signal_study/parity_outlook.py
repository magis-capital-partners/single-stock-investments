"""Oracle test for v3: production calculate_snapshot()["_model_inputs"] must equal
the study panel the outlook models were trained on, stock-day by stock-day.

Feeds production exactly what the nightly job would have fetched on each
sampled date (5-year window of adjusted OHLCV + the SPY window).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BARS, DATA, SCRIPTS, manifest  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
import build_technical_signals as bts  # noqa: E402  production
import fear_vec  # noqa: E402
from parity_test import as_rows  # noqa: E402

PANEL = DATA / "phase5_panel.parquet"
FEATURES = ["panic", "pressure", "exhaustion", "fam_price_dislocation", "fam_selling_climax", "fam_volatility_stress",
            "fam_relative_path_stress", "pct_return_1d_fear", "pct_return_5d_fear", "pct_return_20d_fear",
            "pct_drawdown_fear", "pct_distance_50d_fear", "pct_volume_climax", "pct_range_climax", "pct_gap_fear",
            "pct_volatility_fear", "pct_vol_acceleration", "pct_vcr", "pct_trend_shape", "pct_negative_consistency",
            "pct_downside_share", "f_return_5d", "f_return_20d", "idio5", "idio20", "sys5", "sys20", "mom_12_1",
            "f_rv_20d", "f_drawdown_252d", "f_distance_50d", "f_volume_log_20d", "f_close_location", "rsi14", "beta",
            "spread", "dvol"]


def main(samples: int = 120, seed: int = 5) -> int:
    rng = np.random.default_rng(seed)
    man = manifest()
    spy = fear_vec.production_rows(pd.read_parquet(BARS / man["SPY"]["file"]))
    dset = ds.dataset(PANEL)
    syms = dset.to_table(columns=["sym"], filter=ds.field("us") & ds.field("dash") & (ds.field("date") >= 19980101)).to_pandas()["sym"].unique()
    picks = rng.choice(syms, size=min(40, len(syms)), replace=False)
    worst: dict[str, float] = {}
    bad = []
    checked = 0
    for sym in picks:
        panel = dset.to_table(columns=["sym", "date"] + FEATURES,
                              filter=(ds.field("sym") == sym) & (ds.field("date") >= 19980101)).to_pandas()
        if panel.empty:
            continue
        df = fear_vec.production_rows(pd.read_parquet(BARS / man[sym]["file"]))
        for _, prow in panel.sample(n=min(samples // 40 + 1, len(panel)), random_state=int(rng.integers(1e9))).iterrows():
            d = str(prow["date"])
            end = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            start = (date.fromisoformat(end) - timedelta(days=bts.LOOKBACK_DAYS)).isoformat()
            window = df[(df["date"] >= start) & (df["date"] <= end)]
            bwin = spy[(spy["date"] >= start) & (spy["date"] <= end)]
            snap = bts.calculate_snapshot(sym, as_rows(window), benchmark_rows=as_rows(bwin), benchmark="SPY", source="parity")
            x = snap["_model_inputs"]
            checked += 1
            for f in FEATURES:
                a, b = x.get(f), prow[f]
                if (a is None or (isinstance(a, float) and not math.isfinite(a))) and not np.isfinite(b):
                    continue
                if a is None or not np.isfinite(b):
                    bad.append((sym, end, f, a, float(b)))
                    continue
                err = abs(a - float(b)) / max(1.0, abs(float(b)))
                worst[f] = max(worst.get(f, 0.0), err)
                if err > 2e-4:
                    bad.append((sym, end, f, a, float(b)))
    print(f"checked {checked} stock-days across {len(picks)} stocks")
    print("worst relative error:", json.dumps({k: float(f"{v:.2e}") for k, v in sorted(worst.items(), key=lambda kv: -kv[1])[:12]}))
    print("mismatches:", len(bad))
    for m in bad[:25]:
        print("  ", m)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(*(int(a) for a in sys.argv[1:])))
