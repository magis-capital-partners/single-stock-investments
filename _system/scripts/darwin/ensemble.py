"""Ensemble top policies by deflated fitness (Workstream C)."""
from __future__ import annotations

import math


def deflated_sharpe(sharpe: float, n_trials: int) -> float:
    """Simple haircut when many policies were tried."""
    if n_trials <= 1:
        return sharpe
    penalty = math.sqrt(math.log(max(n_trials, 2)) / max(n_trials, 2))
    return sharpe * max(0.5, 1.0 - 0.15 * penalty)


def blend_weights(
    candidates: list[tuple[str, dict[str, float], float]],
    top_k: int = 3,
) -> tuple[dict[str, float], list[dict]]:
    """Weighted average of top policies by score."""
    ranked = sorted(candidates, key=lambda x: -x[2])[:top_k]
    if not ranked:
        return {}, []
    total_score = sum(max(s, 1e-6) for _, _, s in ranked) or 1.0
    blended: dict[str, float] = {}
    detail = []
    for name, weights, score in ranked:
        w_share = max(score, 1e-6) / total_score
        detail.append({"policy": name, "weight_in_ensemble": round(w_share, 3), "score": round(score, 4)})
        for t, w in weights.items():
            blended[t] = blended.get(t, 0.0) + w * w_share
    s = sum(blended.values()) or 1.0
    blended = {t: blended[t] / s for t in blended}
    return blended, detail
