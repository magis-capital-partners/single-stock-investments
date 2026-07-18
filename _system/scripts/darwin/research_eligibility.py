"""Deterministic research eligibility for the production IRA book.

This module intentionally does not infer a return for an unresearched company.
Stance remains useful research context, but is not an allocation input.
"""
from __future__ import annotations


def adjusted_irr(row: dict) -> float | None:
    """Return the published falsifier-adjusted IRR; never substitute a proxy."""
    value = row.get("irr_falsifier_pct")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def research_status(row: dict, mandate: dict | None = None) -> str:
    """Classify a row using fixed, explainable research-policy states."""
    m = mandate or {}
    if row.get("authority_level") and not row.get("decision_actionable"):
        return "owner_decision_required"
    if not row.get("deep_dive_date"):
        return "research_missing"
    if adjusted_irr(row) is None:
        return "valuation_incomplete"
    days = row.get("days_since_deep_dive")
    if days is None:
        return "valuation_incomplete"
    if float(days) > float(m.get("stale_deep_dive_days", 180)):
        return "research_stale"
    if adjusted_irr(row) < float(m.get("min_irr_pct_for_weight", 6.0)):
        return "irr_below_minimum"
    if float(days) > float(m.get("current_deep_dive_days", 120)):
        return "aging"
    return "current"


def is_allocatable(row: dict, mandate: dict | None = None) -> bool:
    return research_status(row, mandate) in ("current", "aging")


def allocation_cap(row: dict, mandate: dict | None = None) -> float | None:
    """Maximum position fraction by research freshness; None means no allocation."""
    m = mandate or {}
    status = research_status(row, m)
    if status == "current":
        return float(m.get("max_weight_pct", 15.0)) / 100.0
    if status == "aging":
        return float(m.get("aging_max_weight_pct", 7.5)) / 100.0
    return None


def research_queue(rows: list[dict], mandate: dict | None = None, limit: int = 50) -> list[dict]:
    """Queue research work without estimating returns for incomplete names."""
    m = mandate or {}
    priority = {"owner_decision_required": 0, "research_stale": 1, "valuation_incomplete": 2, "research_missing": 3, "irr_below_minimum": 4}
    queued = []
    for row in rows:
        status = research_status(row, m)
        if status in ("current", "aging"):
            continue
        queued.append({
            "ticker": row.get("ticker"),
            "reason": status,
            "days_since_deep_dive": row.get("days_since_deep_dive"),
            "has_falsifier_adjusted_irr": adjusted_irr(row) is not None,
            "priority": priority[status],
        })
    return sorted(queued, key=lambda x: (x["priority"], -(x["days_since_deep_dive"] or -1), x["ticker"] or ""))[:limit]
