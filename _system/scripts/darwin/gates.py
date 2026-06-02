"""Human review gates (Workstream E)."""
from __future__ import annotations


def human_review_flags(
    rows: list[dict],
    weights: dict[str, float],
    prev: dict[str, float] | None,
    mandate: dict,
) -> list[dict]:
    m = mandate.get("mandate") or mandate
    max_core_delta = m.get("core_stance_max_delta_without_review_pct", 2.5) / 100.0
    stale_days = m.get("stale_dive_days_for_review", 120)
    stale_weight = m.get("stale_dive_weight_threshold", 0.08)
    flags: list[dict] = []

    for r in rows:
        t = r["ticker"]
        w = weights.get(t, 0.0)
        if w < 0.01:
            continue
        cl = r.get("classification") or {}
        stance = (cl.get("stance") or "watch").lower()
        prev_w = (prev or {}).get(t, 0.0)
        delta = abs(w - prev_w)

        if stance == "core" and delta > max_core_delta:
            flags.append(
                {
                    "ticker": t,
                    "severity": "review",
                    "reason": "core_stance_weight_delta",
                    "weight_pct": round(w * 100, 2),
                    "delta_pct": round(delta * 100, 2),
                }
            )
        if r.get("human_review_pending") and w >= 0.08:
            flags.append(
                {
                    "ticker": t,
                    "severity": "review",
                    "reason": "human_review_pending",
                    "weight_pct": round(w * 100, 2),
                }
            )
        days = r.get("days_since_deep_dive") or 0
        if days > stale_days and w >= stale_weight:
            flags.append(
                {
                    "ticker": t,
                    "severity": "warn",
                    "reason": "stale_deep_dive_high_weight",
                    "weight_pct": round(w * 100, 2),
                    "days_since_deep_dive": days,
                }
            )
        if w >= 0.08 and stance in ("watch", "trim", "exit"):
            flags.append(
                {
                    "ticker": t,
                    "severity": "review",
                    "reason": "high_weight_low_stance",
                    "weight_pct": round(w * 100, 2),
                    "stance": stance,
                }
            )
    return flags
