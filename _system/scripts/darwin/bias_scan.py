"""Bias scan across holdings (Phase D)."""
from __future__ import annotations

from datetime import datetime, timezone


def run_bias_scan(rows: list[dict], weights: dict[str, float] | None = None) -> dict:
    weights = weights or {}
    flags: list[dict] = []

    for r in rows:
        t = r["ticker"]
        w = weights.get(t, 0.0)
        irr = r.get("irr_base_pct")
        stance = ((r.get("classification") or {}).get("stance") or "watch").lower()
        moat = ((r.get("classification") or {}).get("moat") or "").lower()

        if r.get("human_review_pending") and w > 0.05:
            flags.append({"ticker": t, "bias": "human_review_with_weight", "severity": "review", "weight_pct": round(w * 100, 2)})

        if (r.get("days_since_deep_dive") or 0) > 180 and w > 0.06:
            flags.append({"ticker": t, "bias": "stale_research_high_weight", "severity": "warn", "days": r.get("days_since_deep_dive")})

        if irr is not None and irr < 0 and stance in ("hold", "core", "accumulate") and w > 0.03:
            flags.append({"ticker": t, "bias": "negative_irr_core_stance", "severity": "review", "irr": irr})

        if irr is not None and irr > 12 and stance == "watch" and w > 0.08:
            flags.append({"ticker": t, "bias": "high_irr_watch_capped", "severity": "info", "irr": irr})

        if moat == "eroding" and w > 0.1:
            flags.append({"ticker": t, "bias": "eroding_moat_large_weight", "severity": "warn"})

        if (r.get("falsifier_count") or 0) > 0 and w > 0.08:
            flags.append({"ticker": t, "bias": "falsifier_with_weight", "severity": "review", "count": r.get("falsifier_count")})

    by_severity = {"review": 0, "warn": 0, "info": 0}
    for f in flags:
        by_severity[f.get("severity", "info")] = by_severity.get(f.get("severity", "info"), 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flag_count": len(flags),
        "by_severity": by_severity,
        "flags": flags,
        "pass": not any(f["severity"] == "review" for f in flags),
    }
