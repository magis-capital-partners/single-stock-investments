"""Stress simulation on allocation rules (Phase E)."""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone


def _portfolio_return(weights: dict[str, float], rets: dict[str, float]) -> float:
    return sum(weights.get(t, 0.0) * rets.get(t, 0.0) for t in weights)


def run_stress_simulation(
    panel: dict,
    policy_weights_fn,
    mandate: dict,
    n_paths: int = 200,
    seed: int = 42,
) -> dict:
    """Bootstrap monthly paths with regime shocks (complex adaptive stress)."""
    dates = panel.get("dates") or []
    matrix = panel.get("returns_by_ticker") or {}
    tickers = list(matrix.keys())
    if len(dates) < 12:
        return {"error": "insufficient_history", "months": len(dates)}

    rng = random.Random(seed)
    n_months = len(dates)
    base_w = policy_weights_fn(tickers, len(dates) - 1)

    path_cums: list[float] = []
    for _ in range(n_paths):
        # random block bootstrap of 6-month chunks
        log_eq = 0.0
        for _block in range(max(1, n_months // 6)):
            start = rng.randint(0, max(0, n_months - 7))
            shock = rng.choice([0.0, -0.02, -0.05, 0.03])
            for mi in range(start, min(start + 6, n_months)):
                rets = {t: matrix[t][mi] * (1.0 + shock) for t in tickers if mi < len(matrix[t])}
                pr = _portfolio_return(base_w, rets)
                log_eq += math.log1p(pr)
        path_cums.append(math.exp(log_eq) - 1.0)

    path_cums.sort()
    p10 = path_cums[int(0.1 * len(path_cums))]
    p50 = path_cums[len(path_cums) // 2]
    p90 = path_cums[int(0.9 * len(path_cums))]
    mean = sum(path_cums) / len(path_cums)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_paths": n_paths,
        "horizon_months": n_months,
        "mean_cumulative": round(mean, 4),
        "p10_cumulative": round(p10, 4),
        "p50_cumulative": round(p50, 4),
        "p90_cumulative": round(p90, 4),
        "policy_weights_sample": {t: round(base_w.get(t, 0), 4) for t in sorted(base_w, key=lambda x: -base_w.get(x, 0))[:8]},
        "note": "Block bootstrap with random macro shocks; exploratory stress layer not investment advice.",
    }
