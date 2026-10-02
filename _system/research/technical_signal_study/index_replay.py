"""Point-in-time replay of the risk page's daily capitulation ladder.

Calls the PRODUCTION code (criticality.flow_stress.calculate_flow_snapshot,
apply_state_hysteresis, build_capitulation_daily.drawdown_context /
exhaustion_meaning) once per session over the full history, advancing the
hysteresis memory one trading date at a time -- exactly what the nightly lane
would have published had it run every session.

Also replays the "US market fear" macro read (the per-stock fear model run on
SPY with no benchmark), via the parity-tested vectorized model.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BARS, INDEX_SIGNALS, SCRIPTS, manifest  # noqa: E402

sys.path.insert(0, str(SCRIPTS))

import build_capitulation_daily as bcd  # noqa: E402
from criticality import flow_stress  # noqa: E402
import fear_vec  # noqa: E402

OUT = INDEX_SIGNALS
OUT.mkdir(parents=True, exist_ok=True)
MANIFEST = manifest()
WINDOW = 100  # flow_stress reads <= 61 bars; parity-checked against the full 2y window
SYMBOLS = list(bcd.UNIVERSE) + ["^GSPC", "^NDX", "^RUT", "^DJI", "^IXIC"]
START = {"^GSPC": "1962-01-02", "^IXIC": "1984-10-11"}  # first real high/low
CONF_KEYS = ["positive_interval", "closed_upper_half", "volatility_decelerating", "selling_decelerating", "volume_cooling"]


def load(symbol: str) -> pd.DataFrame:
    raw = pd.read_parquet(BARS / MANIFEST[symbol]["file"])
    df = fear_vec.production_rows(raw)
    if symbol in START:
        df = df[df["date"] >= START[symbol]].reset_index(drop=True)
    return df


def bars_of(df: pd.DataFrame) -> list[dict]:
    out = []
    for r in df.itertuples(index=False):
        out.append({
            "date": r.date,
            "open": None if not np.isfinite(r.open) else float(r.open),
            "high": None if not np.isfinite(r.high) else float(r.high),
            "low": None if not np.isfinite(r.low) else float(r.low),
            "close": float(r.close),
            "volume": None if not np.isfinite(r.volume) else float(r.volume),
        })
    return out


def replay(symbol: str) -> pd.DataFrame:
    df = load(symbol)
    bars = bars_of(df)
    scope = "sector" if symbol in bcd.SECTORS else "market"
    memory: dict | None = None
    rows = []
    for t in range(len(bars)):
        if t + 1 < bcd.MIN_BARS:  # production refuses < 120 bars
            continue
        window = bars[max(0, t + 1 - WINDOW): t + 1]
        snap = flow_stress.calculate_flow_snapshot(symbol, window, scope=scope, source=bcd.SOURCE, entitlement_mode="eod")
        raw_state = snap["raw_state"]
        state, memory = flow_stress.apply_state_hysteresis(raw_state, memory)
        dd = bcd.drawdown_context(bars[max(0, t + 1 - bcd.DRAWDOWN_WINDOW): t + 1])
        meaningful, _ = bcd.exhaustion_meaning(raw_state, snap["scores"]["panic"], dd["drawdown_pct"], dd["in_drawdown"])
        conf = snap["confirmation"]
        rows.append({
            "date": bars[t]["date"],
            "pressure": snap["scores"]["pressure"],
            "panic": snap["scores"]["panic"],
            "exhaustion": snap["scores"]["exhaustion"],
            "raw_state": flow_stress.STATE_RANK[raw_state],
            "state": flow_stress.STATE_RANK[state],
            "confirmation_count": sum(bool(conf[k]) for k in CONF_KEYS),
            **{f"c_{k}": bool(conf[k]) for k in CONF_KEYS},
            "drawdown_pct": dd["drawdown_pct"],
            "days_since_high": dd["days_since_high"],
            "in_drawdown": dd["in_drawdown"],
            "exhaustion_meaningful": meaningful,
            "return_5d_pct": snap["features"]["return_5m_pct"],
            "volatility_acceleration": snap["features"]["volatility_acceleration"],
            "volume_z": snap["features"]["volume_z"],
            "range_z": snap["features"]["range_z"],
        })
    out = pd.DataFrame(rows)
    return out


def parity(symbol: str = "SPY", samples: int = 60, seed: int = 3) -> int:
    """WINDOW-bar replay must equal production's full 2-year call."""
    rng = np.random.default_rng(seed)
    df = load(symbol)
    bars = bars_of(df)
    bad = 0
    for t in sorted(rng.choice(np.arange(600, len(bars)), size=samples, replace=False)):
        full = bars[max(0, t + 1 - 520): t + 1]
        short = bars[max(0, t + 1 - WINDOW): t + 1]
        a = flow_stress.calculate_flow_snapshot(symbol, full, entitlement_mode="eod")
        b = flow_stress.calculate_flow_snapshot(symbol, short, entitlement_mode="eod")
        if a["scores"] != b["scores"] or a["raw_state"] != b["raw_state"] or a["confirmation"] != b["confirmation"]:
            bad += 1
    print(f"window parity {symbol}: {samples - bad}/{samples} identical")
    return bad


def main() -> int:
    parity("SPY")
    parity("XLK")
    for symbol in SYMBOLS:
        if symbol not in MANIFEST or MANIFEST[symbol].get("error"):
            print("skip", symbol)
            continue
        t0 = time.time()
        out = replay(symbol)
        out.to_parquet(OUT / f"{MANIFEST[symbol]['file']}", index=False)
        print(f"{symbol}: {len(out)} sessions {out['date'].iloc[0]}..{out['date'].iloc[-1]} in {time.time() - t0:.1f}s", flush=True)
    # US market fear (per-stock model on SPY, benchmark None) -- the holdings-page Macro lane
    spy = load("SPY")
    macro = fear_vec.compute(spy, None)
    macro.to_parquet(OUT / "SPY_macro_fear.parquet", index=False)
    gspc = load("^GSPC")
    fear_vec.compute(gspc, None).to_parquet(OUT / "GSPC_macro_fear.parquet", index=False)
    print("macro fear replay written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
