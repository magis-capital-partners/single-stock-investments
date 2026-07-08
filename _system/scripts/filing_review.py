#!/usr/bin/env python3
"""Shared filing metric review logic for build_insights and auto_resolve."""
from __future__ import annotations


def pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    try:
        current_f = float(current)
        prior_f = float(prior)
    except (TypeError, ValueError):
        return None
    if prior_f == 0:
        return None
    return (current_f - prior_f) / abs(prior_f) * 100.0


FILING_SKIP_FLAGS = {
    "segment_zero_revenue",
    "footnote_pairing",
    "immaterial_prior",
    "segment_context",
    "magnitude_mismatch",
    "legacy_pairing",
    "non_statement_debt",
}


def filing_metric_needs_review(metric: dict, change: float | None = None) -> bool:
    flags = set(metric.get("parser_flags") or [])
    parser_conf = str(metric.get("parser_confidence") or "low").lower()
    if parser_conf == "low" and flags & FILING_SKIP_FLAGS:
        return True
    if parser_conf == "low" and change is not None and abs(change) > 200:
        return True
    return False


PL_METRICS = frozenset({"revenues", "revenue", "operating_income", "net_income", "eps_basic", "eps_diluted", "cfo"})
BALANCE_METRICS = frozenset({"cash", "stockholders_equity", "long_term_debt"})


def filing_metric_passes_magnitude(name: str, metric: dict, change: float | None) -> bool:
    """Stricter magnitude gates aligned with event_triage_rules.json."""
    if change is None:
        return True
    try:
        prior_abs = abs(float(metric.get("prior") or 0))
        current = float(metric.get("current") or 0)
        abs_delta = abs(current - prior_abs)
    except (TypeError, ValueError):
        prior_abs = 0.0
        abs_delta = 0.0
    if name in PL_METRICS:
        return abs(change) >= 10
    if name in BALANCE_METRICS:
        if prior_abs < 5000:
            return abs_delta >= 5000
        return abs(change) >= 25 and abs_delta >= 5000
    return abs(change) >= 20


def filing_metric_passes_sanity(name: str, metric: dict, change: float | None) -> bool:
    flags = set(metric.get("parser_flags") or [])
    parser_conf = str(metric.get("parser_confidence") or "low").lower()
    if parser_conf == "low":
        return False
    if flags & FILING_SKIP_FLAGS:
        return False
    if change is None:
        return False
    if abs(change) > 500:
        return False
    if name in {"revenues", "revenue"}:
        current = metric.get("current")
        try:
            if current is not None and float(current) == 0:
                return False
        except (TypeError, ValueError):
            pass
    return True


def auto_resolve_verdict(name: str, metric: dict, change: float | None) -> tuple[str, str]:
    """Return (verdict, reason) — auto_ok | needs_human."""
    if filing_metric_passes_sanity(name, metric, change):
        return "auto_ok", "high_confidence_sanity_pass"
    if filing_metric_needs_review(metric, change):
        return "needs_human", "low_confidence_or_skip_flags"
    return "auto_ok", "default_accept"
