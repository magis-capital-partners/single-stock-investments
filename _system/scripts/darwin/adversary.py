"""Adversarial stress panel for evolutionary fitness (Workstream C)."""
from __future__ import annotations

import copy


def stress_returns(
    returns_by_ticker: dict[str, list[float]],
    shock_scale: float = 1.35,
    spike_months: int = 3,
) -> dict[str, list[float]]:
    """Inflate negative tails and add drawdown cluster."""
    out: dict[str, list[float]] = {}
    for t, series in returns_by_ticker.items():
        stressed = []
        for i, r in enumerate(series):
            if r < 0:
                stressed.append(r * shock_scale)
            elif i < spike_months and r > 0.02:
                stressed.append(r * 0.3)
            else:
                stressed.append(r * 0.95)
        out[t] = stressed
    return out


def adversarial_fitness(
    normal_score: float,
    stressed_score: float,
    blend: float = 0.45,
) -> float:
    """Min-blend: weak policies fail under stress."""
    return (1.0 - blend) * normal_score + blend * min(normal_score, stressed_score)
