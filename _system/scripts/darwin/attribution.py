"""Factor attribution from encoder + policy scores (Phase 3)."""
from __future__ import annotations

import numpy as np

from .policies import _score_row


def factor_attribution(
    rows: list[dict],
    latent: dict[str, list[float]],
    weights: dict[str, float],
    factor_labels: list[str],
) -> list[dict]:
    """Correlation-weighted factor importance at portfolio level."""
    if not rows or not latent:
        return []

    tickers = [r["ticker"] for r in rows]
    k = len(factor_labels)
    Z = np.array([latent.get(t, [0.0] * k)[:k] for t in tickers], dtype=float)
    w = np.array([weights.get(t, 0.0) for t in tickers], dtype=float)
    if w.sum() < 1e-9:
        w = np.ones(len(tickers)) / len(tickers)
    else:
        w = w / w.sum()

    contrib = (w.reshape(-1, 1) * Z).sum(axis=0)
    scores = np.array([_score_row(r) for r in rows])
    # map Marvin themes
    themes = {
        "owner_cash_irr": float(np.corrcoef(Z[:, 0] if k > 0 else scores, scores)[0, 1])
        if k > 0 and len(scores) > 1
        else 0.0,
        "moat_quality": float(
            np.mean(
                [
                    1.0
                    if (r.get("classification") or {}).get("moat") in ("widening", "stable")
                    else 0.0
                    for r in rows
                ]
            )
        ),
        "research_staleness": float(
            np.mean([(r.get("days_since_deep_dive") or 180) / 365.0 for r in rows])
        ),
        "falsifier_pressure": float(np.mean([r.get("falsifier_count", 0) for r in rows])),
    }

    out = []
    for i, label in enumerate(factor_labels):
        out.append(
            {
                "factor": label,
                "shap": round(float(contrib[i]), 4),
                "portfolio_weighted": True,
            }
        )
    for name, val in themes.items():
        out.append({"factor": name, "shap": round(val, 4), "portfolio_weighted": False})
    out.sort(key=lambda x: -abs(x["shap"]))
    return out[:10]
