"""Apply mandate constraints to raw weights."""
from __future__ import annotations

import math


def enforce_max_weight_sum(weights: dict[str, float], max_w: float) -> dict[str, float]:
    """Cap each name at max_w then renormalize (iterative)."""
    w = {t: max(v, 0.0) for t, v in weights.items() if v > 1e-9}
    if not w:
        return weights
    for _ in range(24):
        over = [t for t in w if w[t] > max_w + 1e-9]
        if not over:
            break
        extra = sum(w[t] - max_w for t in over)
        for t in over:
            w[t] = max_w
        under = [t for t in w if w[t] < max_w - 1e-9]
        if not under:
            break
        add = extra / len(under)
        for t in under:
            w[t] += add
    s = sum(w.values()) or 1.0
    return {t: w[t] / s for t in w}


def apply_constraints(
    tickers: list[str],
    raw: dict[str, float],
    prev: dict[str, float] | None,
    mandate: dict,
    falsifier_counts: dict[str, int] | None = None,
) -> tuple[dict[str, float], dict]:
    m = mandate.get("mandate") or mandate
    max_w = m.get("max_weight_pct", 18.0) / 100.0
    min_w = m.get("min_weight_pct", 2.0) / 100.0
    max_names = m.get("max_names", 15)
    min_names = m.get("min_names", 8)
    max_delta = m.get("max_abs_weight_change_pct_per_rebalance", 3.0) / 100.0
    max_turn = m.get("max_one_way_turnover_pct_per_rebalance", 15.0) / 100.0

    falsifier_counts = falsifier_counts or {}
    scores = {}
    for t in tickers:
        w = max(raw.get(t, 0.0), 0.0)
        if falsifier_counts.get(t, 0) > 0 and m.get("falsifier_exit"):
            w *= 0.25
        scores[t] = w

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    keep = [t for t, s in ranked if s > 1e-9][:max_names]
    if len(keep) < min_names:
        keep = [t for t, _ in ranked[: min(min_names, len(tickers))]]

    total = sum(scores.get(t, 0.0) for t in keep) or 1.0
    out = {t: scores.get(t, 0.0) / total for t in keep}
    out = enforce_max_weight_sum(out, max_w)

    for t in list(out):
        if out[t] < min_w and len(out) > min_names:
            del out[t]
    s = sum(out.values()) or 1.0
    out = {t: out[t] / s for t in out}

    notes: dict = {"trimmed_names": len(tickers) - len(out)}
    if prev:
        for t in list(out):
            p = prev.get(t, 0.0)
            lo, hi = p - max_delta, p + max_delta
            if p > 0:
                out[t] = min(max(out[t], lo), hi)
        s = sum(out.values()) or 1.0
        out = {t: out[t] / s for t in out}
        turnover = 0.5 * sum(abs(out.get(t, 0.0) - prev.get(t, 0.0)) for t in set(out) | set(prev))
        notes["turnover_one_way"] = round(turnover, 4)
        if turnover > max_turn:
            alpha = max_turn / turnover
            blended = {}
            for t in out:
                blended[t] = prev.get(t, 0.0) * (1 - alpha) + out[t] * alpha
            s = sum(blended.values()) or 1.0
            out = {t: blended[t] / s for t in blended}
            notes["turnover_capped"] = True
            # Re-apply cap after blend
            ranked2 = sorted(out.items(), key=lambda x: -x[1])
            out = dict(ranked2[:max_names])
            s = sum(out.values()) or 1.0
            out = {t: out[t] / s for t in out}

    n = len(out)
    if n > 0 and n * max_w < 1.0 - 1e-6:
        max_w = min(max_w, 1.0 / n)
    out = enforce_max_weight_sum(out, max_w)
    out = {t: v for t, v in out.items() if v > 1e-4}
    s = sum(out.values()) or 1.0
    out = {t: out[t] / s for t in out}
    return out, notes


def apply_ira_stance_caps(
    weights: dict[str, float],
    features_by_ticker: dict[str, dict],
    mandate: dict,
) -> dict[str, float]:
    """Cap watch/trim names; boost redistribution to hold+."""
    m = mandate.get("mandate") or mandate
    max_watch = m.get("max_weight_pct_watch", 5.0) / 100.0
    allow_watch = set(m.get("allow_watch_stances") or [])
    if not max_watch:
        return weights
    excess = 0.0
    out = dict(weights)
    receivers = []
    for t, w in list(out.items()):
        f = features_by_ticker.get(t, {})
        stance = ((f.get("classification") or {}).get("stance") or "watch").lower()
        if stance in ("watch", "trim") and stance not in allow_watch and w > max_watch:
            excess += w - max_watch
            out[t] = max_watch
        elif stance in ("core", "accumulate", "hold"):
            receivers.append(t)
    if excess > 0 and receivers:
        add = excess / len(receivers)
        for t in receivers:
            out[t] = out.get(t, 0.0) + add
    s = sum(out.values()) or 1.0
    out = {t: out[t] / s for t in out}
    max_w = m.get("max_weight_pct", 15.0) / 100.0
    out = enforce_max_weight_sum(out, max_w)
    return {t: v for t, v in out.items() if v > 1e-4}


def weights_to_list(
    weights: dict[str, float],
    features_by_ticker: dict[str, dict],
    prev: dict[str, float] | None,
) -> list[dict]:
    prev = prev or {}
    rows = []
    for t, w in sorted(weights.items(), key=lambda x: -x[1]):
        f = features_by_ticker.get(t, {})
        cl = f.get("classification") or {}
        rows.append(
            {
                "ticker": t,
                "company": f.get("company", t),
                "weight": round(w, 4),
                "weight_pct": round(w * 100, 2),
                "delta": round(w - prev.get(t, 0.0), 4),
                "stance": cl.get("stance"),
                "irr_base_pct": f.get("irr_base_pct"),
                "falsifier_count": f.get("falsifier_count", 0),
                "trade_suggested": abs(w - prev.get(t, 0.0)) >= 0.005,
            }
        )
    return rows
