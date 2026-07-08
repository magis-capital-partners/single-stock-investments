#!/usr/bin/env python3
"""Deterministic materiality scoring for insights event queue rows."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from filing_review import FILING_SKIP_FLAGS

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "_system" / "data" / "event_triage_rules.json"

SOURCE_BASE = {
    "kpi_trend": 0.95,
    "filing": 0.96,
    "earnings": 0.94,
    "insider": 0.86,
    "superinvestor_letter": 0.8,
    "sumzero_research": 0.64,
    "news": 0.72,
    "third_party": 0.58,
    "macro": 0.62,
    "theme": 0.58,
}

SOURCE_QUALITY = {
    "kpi_trend": 0.92,
    "filing": 1.0,
    "earnings": 0.96,
    "insider": 0.9,
    "superinvestor_letter": 0.82,
    "sumzero_research": 0.68,
    "news": 0.7,
    "third_party": 0.58,
    "macro": 0.54,
    "theme": 0.5,
}

BALANCE_SHEET_METRICS = frozenset({"cash", "stockholders_equity", "long_term_debt"})
PL_METRICS = frozenset({"revenues", "revenue", "operating_income", "net_income", "eps_basic", "eps_diluted", "cfo"})


def load_rules() -> dict:
    if RULES_PATH.exists():
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return {}


def confidence_factor(confidence: str | None) -> float:
    return {"high": 1.0, "med": 0.75, "medium": 0.75, "low": 0.45}.get(str(confidence or "").lower(), 0.6)


def freshness_factor(days: int | None) -> float:
    if days is None:
        return 0.5
    if days < 0:
        return 0.85
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.84
    if days <= 90:
        return 0.62
    if days <= 365:
        return 0.38
    return 0.2


def book_factor(in_our_book: bool, portfolio_relevance: float | None) -> float:
    if in_our_book:
        return 1.0
    rel = float(portfolio_relevance or 0)
    if rel >= 0.7:
        return 0.72
    return 0.45


def magnitude_factor(event: dict, rules: dict) -> float:
    thresholds = rules.get("thresholds") or {}
    metric = event.get("metric_name") or ""
    prior = _to_float(event.get("prior_value"))
    current = _to_float(event.get("current_value"))
    change_pct = _to_float(event.get("change_pct"))
    if event.get("source") != "filing" or change_pct is None:
        if event.get("event_type") in {"inflection", "regime_shift", "leadership_risk"}:
            if event.get("trend_signal_tier") == "confirmed":
                return 1.1
            return 0.95
        if event.get("event_type") == "letter_position" and event.get("position_action") in {
            "add",
            "trim",
            "new",
            "exit",
            "short",
            "buy",
        }:
            return 1.05
        return 1.0

    prior_abs = abs(prior or 0)
    tiny = float(thresholds.get("small_base_tiny_prior_usd_k") or 100)
    floor = float(thresholds.get("small_base_prior_usd_k") or 5000)
    pct_cap = float(thresholds.get("small_base_pct_cap") or 100)

    if metric in BALANCE_SHEET_METRICS:
        if prior_abs < floor:
            scale = max(0.25, min(1.0, prior_abs / floor))
            if abs(change_pct or 0) > pct_cap:
                scale *= 0.6
            return scale
        abs_delta = abs((current or 0) - prior_abs)
        min_delta = float(thresholds.get("balance_abs_delta_usd_k_min") or 5000)
        if abs_delta < min_delta:
            return 0.55

    if prior_abs < tiny and abs(change_pct or 0) > 50:
        return 0.25

    if abs(change_pct or 0) > 200:
        return 0.7
    if abs(change_pct or 0) > 100:
        return 0.85
    return 1.0


def verification_factor(event: dict) -> float:
    factor = 1.0
    v = event.get("verification") or {}
    flags = set(v.get("parser_flags") or [])
    if flags & FILING_SKIP_FLAGS:
        factor *= 0.35
    if event.get("needs_review"):
        factor *= 0.55
    conf = str(v.get("parser_confidence") or event.get("confidence") or "med").lower()
    if event.get("source") == "filing" and conf == "low":
        factor *= 0.5
    return factor


def stance_factor(event: dict) -> float:
    if event.get("in_base_irr") and event.get("direction") in {"bullish", "bearish"}:
        return 0.82
    return 1.0


def base_weight(event: dict) -> float:
    source = event.get("source") or ""
    base = SOURCE_BASE.get(source, 0.55)
    event_type = event.get("event_type") or ""
    if event_type == "inflection":
        base = min(1.0, base + 0.08)
    elif event_type == "regime_shift":
        base = min(1.0, base + 0.1)
    elif event_type == "leadership_risk":
        base = min(1.0, base + 0.06)
    elif event_type in {"filing_metric", "reported_earnings"}:
        base = min(1.0, base + 0.05)
    elif event_type == "filing_refresh":
        base = 0.35
    elif event_type == "letter_position":
        base = min(1.0, base + 0.04)
    if event.get("impact_axis") in {"governance", "risk"}:
        base = min(1.0, base + 0.03)
    return base


def materiality_score(event: dict, *, rules: dict | None = None) -> tuple[int, dict]:
    rules = rules or load_rules()
    quality = SOURCE_QUALITY.get(event.get("source") or "", 0.55)
    components = {
        "base": base_weight(event),
        "quality": quality,
        "magnitude": magnitude_factor(event, rules),
        "confidence": confidence_factor(event.get("confidence")),
        "freshness": freshness_factor(event.get("freshness_days")),
        "book": book_factor(bool(event.get("in_our_book")), event.get("portfolio_relevance")),
        "verification": verification_factor(event),
        "stance": stance_factor(event),
    }
    if event.get("superseded_penalty"):
        components["superseded"] = 0.4
    raw = 100.0
    for value in components.values():
        raw *= float(value)
    score = max(1, min(100, round(raw)))
    floor = event.get("materiality_floor")
    if floor is not None:
        score = max(score, int(floor))
    return score, components


def materiality_tier(score: int, *, rules: dict | None = None) -> str:
    rules = rules or load_rules()
    signal = int(rules.get("signal_threshold") or 55)
    noise = int(rules.get("noise_threshold") or 25)
    if score >= signal:
        return "signal"
    if score >= noise:
        return "context"
    return "noise"


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
