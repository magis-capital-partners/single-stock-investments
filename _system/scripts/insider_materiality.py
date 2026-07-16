"""Deterministic materiality scoring for Form 4 / insider insight events.

Mirrors activist_materiality.py: multiplicative components → 1–100 score with
signal / context / noise tiers. Insider Conviction Score (ICS) is one component
only — never auto-inflates Lawrence base IRR.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SIGNAL_THRESHOLD = 55
NOISE_THRESHOLD = 25
FRESHNESS_HALF_LIFE_DAYS = 120

# Absolute USD size bands → size factor
SIZE_BANDS = (
    (5_000_000, 1.15),
    (1_000_000, 1.08),
    (250_000, 1.0),
    (100_000, 0.9),
    (25_000, 0.75),
    (0, 0.55),
)


def type_factor(row: dict) -> float:
    """Open-market purchase > award acquire > sale; planned sales crushed elsewhere."""
    action = (row.get("action") or row.get("transaction_action") or "").lower()
    code = (row.get("transaction_code") or "").upper()
    acquired = (row.get("acquired_disposed") or "").upper()
    is_buy = action == "purchase" or code == "P" or acquired == "A"
    is_sale = action == "sale" or code == "S" or acquired == "D"
    if is_buy and code in {"", "P"} and acquired in {"", "A"}:
        # Prefer open-market P over generic A when code known
        if code == "P":
            return 1.0
        if code in {"A", "M", "G"} or row.get("is_award"):
            return 0.55
        return 0.92
    if is_sale:
        return 0.62
    return 0.5


def role_factor(row: dict) -> float:
    title = " ".join(
        str(x or "") for x in (row.get("role"), row.get("title"), row.get("relationship"))
    ).lower()
    if row.get("is_ceo") or "ceo" in title or "chief executive" in title:
        return 1.1
    if row.get("is_cfo") or "cfo" in title or "chief financial" in title:
        return 0.95 if _is_buy(row) else 0.7
    if row.get("is_director") or "director" in title or "chair" in title:
        return 1.05 if "chair" in title else 1.0
    if row.get("is_officer") or "officer" in title:
        return 0.9 if _is_buy(row) else 0.55
    if row.get("is_ten_pct") or "10%" in title or "ten percent" in title:
        return 1.15
    return 0.8


def _is_buy(row: dict) -> bool:
    action = (row.get("action") or "").lower()
    code = (row.get("transaction_code") or "").upper()
    acquired = (row.get("acquired_disposed") or "").upper()
    return action == "purchase" or code == "P" or acquired == "A"


def size_factor(value_usd: float | None) -> float:
    if value_usd is None:
        return 0.7
    v = max(0.0, float(value_usd))
    for threshold, factor in SIZE_BANDS:
        if v >= threshold:
            return factor
    return 0.55


def cluster_factor(cluster_size: int | None, distinct_insiders: int | None = None) -> float:
    size = max(1, int(cluster_size or 1))
    insiders = max(1, int(distinct_insiders or 1))
    boost = 1.0
    if insiders >= 2:
        boost += 0.08
    if size >= 3:
        boost += 0.06
    return min(1.2, boost)


def freshness_factor(report_date: str | None, *, now: datetime | None = None) -> float:
    if not report_date:
        return 0.5
    try:
        dt = datetime.strptime(str(report_date)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.5
    now = now or datetime.now(timezone.utc)
    days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return max(0.25, math.pow(0.5, days / FRESHNESS_HALF_LIFE_DAYS))


def book_factor(*, in_holdings: bool, in_watchlist: bool) -> float:
    if in_holdings:
        return 1.0
    if in_watchlist:
        return 0.72
    return 0.45


def ics_factor(ics: float | None) -> float:
    """Map ICS 0–10 → ~0.7–1.15."""
    if ics is None:
        return 1.0
    try:
        v = max(0.0, min(10.0, float(ics)))
    except (TypeError, ValueError):
        return 1.0
    return 0.7 + 0.045 * v


def plan_factor(row: dict) -> float:
    """Planned / 10b5-1 / tax withholding sales → noise."""
    if row.get("is_10b5_1") or row.get("planned_sale"):
        return 0.35
    footnotes = str(row.get("footnotes") or row.get("note") or "").lower()
    if "10b5-1" in footnotes or "rule 10b5" in footnotes:
        return 0.35
    if "tax" in footnotes and "withhold" in footnotes:
        return 0.4
    code = (row.get("transaction_code") or "").upper()
    if code == "F":  # tax withholding
        return 0.35
    return 1.0


def materiality_score(
    row: dict,
    *,
    in_holdings: bool = True,
    in_watchlist: bool = False,
    ics: float | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    value = row.get("value_usd")
    if value is None:
        value = row.get("value")
    components = {
        "type": type_factor(row),
        "role": role_factor(row),
        "size": size_factor(value if value is not None else None),
        "cluster": cluster_factor(row.get("cluster_size"), row.get("distinct_insiders")),
        "freshness": freshness_factor(
            row.get("report_date") or row.get("as_of") or row.get("filing_date") or row.get("date"),
            now=now,
        ),
        "book": book_factor(in_holdings=in_holdings, in_watchlist=in_watchlist),
        "ics": ics_factor(ics if ics is not None else row.get("ics")),
        "plan": plan_factor(row),
    }
    raw = 100.0
    for value_f in components.values():
        raw *= float(value_f)
    score = max(1, min(100, round(raw)))
    return score, components


def materiality_tier(score: int, row: dict | None = None) -> str:
    row = row or {}
    if plan_factor(row) < 0.5 and not _is_buy(row):
        # Planned sales stay noise unless score somehow clears signal (unlikely)
        if score < SIGNAL_THRESHOLD:
            return "noise"
    if score >= SIGNAL_THRESHOLD:
        return "signal"
    if score < NOISE_THRESHOLD:
        return "noise"
    return "context"


def score_form4_event(
    row: dict,
    *,
    in_holdings: bool = True,
    in_watchlist: bool = False,
    ics: float | None = None,
    now: datetime | None = None,
) -> dict:
    """Attach materiality fields to an insight-like dict (returns new fields only)."""
    score, components = materiality_score(
        row,
        in_holdings=in_holdings,
        in_watchlist=in_watchlist,
        ics=ics,
        now=now,
    )
    tier = materiality_tier(score, row)
    return {
        "materiality": score,
        "materiality_components": {k: round(v, 4) for k, v in components.items()},
        "tier": tier,
        "ics": ics if ics is not None else row.get("ics"),
    }
