"""Lab-only GA over covered-call knobs (Phase D). Never overwrites Marvin stance."""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backtest import benchmark_covered_call
from .config import DATA_DIR
from .covered_call import resolve_cc_cfg


def _random_cc_genome(rng: random.Random, base: dict) -> dict:
    return {
        "premium_yield_annual_pct": round(rng.uniform(4.0, 14.0), 2),
        "tenor_days": rng.choice([5, 7, 14, 21, 30]),
        "otm_pct": round(rng.uniform(1.0, 4.0), 2),
        "bid_ask_haircut": round(rng.uniform(0.05, 0.25), 2),
        "coverage_fraction": round(rng.uniform(0.1, 0.45), 2),
        "assignment_bps": rng.choice([0, 5, 10, 15]),
        "etf_proxy_ticker": base.get("etf_proxy_ticker") or "XYLD",
        "mode": "synthetic_lab",
        "label": "cc_knob_lab",
        "enabled": True,
    }


def run_cc_knob_lab(
    dates: list[str],
    returns_by_ticker: dict[str, list[float]],
    weights: dict[str, float],
    mandate_doc: dict,
    features_by_ticker: dict | None = None,
    iv_by_ticker: dict[str, float] | None = None,
    liquidity_by_ticker: dict[str, str] | None = None,
    regime: dict | None = None,
    n_trials: int = 12,
    seed: int = 42,
) -> dict[str, Any]:
    """Search CC knobs; write scenario JSON. Does not change production champion weights."""
    evo = mandate_doc.get("evolution") or {}
    if not evo.get("enable_cc_ga"):
        return {"enabled": False, "reason": "evolution.enable_cc_ga is false"}

    base = resolve_cc_cfg(mandate_doc, regime)
    rng = random.Random(seed)
    trials: list[dict] = []
    for i in range(max(3, n_trials)):
        genome = _random_cc_genome(rng, base) if i else {**base, "mode": "synthetic_lab", "label": "cc_baseline"}
        bt = benchmark_covered_call(
            dates,
            returns_by_ticker,
            weights,
            genome,
            (mandate_doc.get("mandate") or {}).get("rebalance_frequency", "semiannual"),
            track_series=False,
            features_by_ticker=features_by_ticker,
            iv_by_ticker=iv_by_ticker,
            liquidity_by_ticker=liquidity_by_ticker,
            regime=regime,
        )
        trials.append(
            {
                "genome": genome,
                "sharpe_annualized": bt.get("sharpe_annualized"),
                "cumulative_return": bt.get("cumulative_return"),
                "max_drawdown_pct": bt.get("max_drawdown_pct"),
                "error": bt.get("error"),
            }
        )
    ranked = sorted(
        [t for t in trials if not t.get("error")],
        key=lambda x: (x.get("sharpe_annualized") or -999),
        reverse=True,
    )
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lab": "cc_knob_ga",
        "disclaimer": "Lab only. Does not overwrite Marvin stance or production weights.",
        "n_trials": len(trials),
        "best": ranked[0] if ranked else None,
        "trials": ranked[:8],
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "darwin_cc_lab_scenarios.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    out["path"] = str(path)
    return out
