#!/usr/bin/env python3
"""Shared helpers for research memory claim building."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BIOTECH_SLEEVE = {"healthcare_pharma", "biotech_pharma", "life_sciences"}
BIOTECH_EXCLUDE_SLEEVES = {
    "exchanges_markets",
    "financials_banks",
    "financials_insurance",
    "real_assets_land",
    "royalties_streams",
    "holdco_conglomerate",
}
BIOTECH_EXCLUDE_TICKERS = {
    "AMZN",
    "AMD",
    "CHTR",
    "CPRT",
    "CSGP",
    "ENPH",
    "GOOG",
    "GOOGL",
    "ICE",
    "META",
    "MSTR",
    "NDAQ",
    "CME",
    "GS",
    "JPM",
    "NVDA",
    "TSLA",
    "XYZ",
    "0388.HK",
}

BIOTECH_ISSUER_TERMS = (
    "biotech",
    "biopharm",
    "therapeutic",
    "pharma",
    "bioscience",
    "genomic",
    "genetics",
    "oncology",
    "immuno",
    "diagnostic",
    "lifesci",
    "life sci",
    "medical",
    "vaccine",
    "biosciences",
)

NON_BIOTECH_ISSUER_TERMS = (
    "alphabet",
    "google",
    "amazon",
    "meta platform",
    "facebook",
    "nvidia",
    "microsoft",
    "apple",
    "tesla",
    "advanced micro",
    "microstrategy",
    "enphase",
    "copart",
    "costar",
    "exchange",
    "financial",
    "insurance",
    "bank",
)

SPECIALIST_FUND_TERMS = (
    "baker",
    "perceptive",
    "ra capital",
    "orbimed",
    "ecor1",
    "redmile",
    "deerfield",
    "casdin",
    "venbio",
    "samsara",
    "rtw",
    "avoro",
    "deep track",
    "cormorant",
    "ikarian",
)

LOW_VALUE_CLAIM_PATTERNS = (
    r"^\s*\w+\s+earnings event tracked\.?\s*$",
    r"^\s*earnings event tracked\.?\s*$",
    r"^\s*no material update\.?\s*$",
)

SKIP_EVENT_TYPES = {"earnings_calendar_stub", "placeholder"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def short_text(value: str | None, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def slug(value: str | None, limit: int = 80) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return text[:limit].strip("-") or "unknown"


def stable_id(*parts: object, size: int = 16) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:size]


def is_low_value_claim(text: str, row: dict) -> bool:
    if row.get("event_type") in SKIP_EVENT_TYPES:
        return True
    if len(text.strip()) < 24:
        return True
    for pattern in LOW_VALUE_CLAIM_PATTERNS:
        if re.match(pattern, text, flags=re.I):
            return True
    return False


def is_biotech_ticker(
    ticker: str,
    entity: dict,
    registry_meta: dict | None,
    *,
    biotech_watchlist: set[str],
) -> bool:
    if ticker in biotech_watchlist:
        return True
    if ticker in BIOTECH_EXCLUDE_TICKERS:
        return False
    sleeve = str(entity.get("investment_sleeve") or "").lower()
    if sleeve in BIOTECH_EXCLUDE_SLEEVES:
        return False
    if sleeve in BIOTECH_SLEEVE:
        return True
    if registry_meta and registry_meta.get("biotech_watchlist"):
        return True
    company = str(entity.get("company") or "").lower()
    if any(term in company for term in ("biotech", "biopharma", "therapeutics", "pharma", "diagnostics")):
        if sleeve not in BIOTECH_EXCLUDE_SLEEVES:
            return True
    return False


def normalize_issuer(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def issuer_is_biotech(issuer: str | None) -> bool:
    text = normalize_issuer(issuer)
    if not text:
        return False
    if any(term in text for term in NON_BIOTECH_ISSUER_TERMS):
        return False
    return any(term in text for term in BIOTECH_ISSUER_TERMS)


def is_biotech_quant_universe_ticker(
    ticker: str,
    entity: dict,
    registry_meta: dict | None,
    *,
    biotech_watchlist: set[str],
    ownership_records: list[dict] | None = None,
) -> bool:
    """Ticker is in the 13F biotech quant universe (specialist holdings + biotech classification)."""
    records = ownership_records or []
    if not records:
        return False
    if ticker in BIOTECH_EXCLUDE_TICKERS:
        return False
    if is_biotech_ticker(ticker, entity, registry_meta, biotech_watchlist=biotech_watchlist):
        return True
    return any(issuer_is_biotech(rec.get("issuer")) for rec in records)


def claim_type(row: dict) -> str:
    axis = row.get("impact_axis")
    event = row.get("event_type") or ""
    source = row.get("source") or ""
    text = " ".join([row.get("title") or "", row.get("summary") or "", row.get("claim") or ""]).lower()
    if source in {"deep_dive", "adversarial_review", "proposed_belief", "approved_belief"}:
        return row.get("claim_type") or "thesis"
    if source == "specialist_13f":
        return "ownership"
    if source in {"superinvestor_letter", "sumzero_research", "third_party"}:
        return "thesis"
    if axis == "ownership" or "13f" in text or "insider" in text:
        return "ownership"
    if axis in {"management", "governance", "capital_allocation", "variant_view", "macro", "fundamentals"}:
        return axis
    if event == "filing_metric" or any(
        term in text
        for term in (
            "accelerat",
            "inflect",
            "improv",
            "recover",
            "less bad",
            "decline",
            "growth",
            "margin",
            "revision",
            "revenue",
            "free cash flow",
        )
    ):
        return "inflection"
    if axis == "risk" or row.get("direction") == "bearish":
        return "risk"
    if axis == "catalyst":
        return "catalyst"
    return axis or "context"


def evidence_effect(row: dict, ctype: str) -> str:
    direction = row.get("direction") or "neutral"
    if ctype == "risk":
        return "disconfirms"
    if direction == "bearish":
        return "disconfirms"
    if direction == "bullish":
        return "confirms"
    if direction == "neutral":
        return "neutral"
    return "mixed"


def confidence_score(row: dict) -> int:
    score = int(row.get("score") or 0)
    source = row.get("source")
    bonus = {
        "approved_belief": 28,
        "deep_dive": 24,
        "adversarial_review": 22,
        "filing": 20,
        "specialist_13f": 20,
        "earnings": 18,
        "insider": 14,
        "superinvestor_letter": 12,
        "news": 8,
        "third_party": 7,
        "sumzero_research": 7,
        "proposed_belief": 5,
    }.get(source, 4)
    final = score + bonus
    date = row.get("observed_at") or row.get("as_of") or row.get("date") or ""
    if date[:4].isdigit():
        year = int(date[:4])
        if year <= datetime.now(timezone.utc).year - 5:
            final -= 8
    return max(final, 0)


def source_type(row: dict) -> str:
    source = row.get("source") or "source"
    return {
        "superinvestor_letter": "letter",
        "third_party": "third_party_research",
        "sumzero_research": "third_party_research",
        "news": "news",
        "filing": "filing",
        "earnings": "earnings",
        "insider": "insider",
        "specialist_13f": "ownership_13f",
        "deep_dive": "deep_dive",
        "adversarial_review": "adversarial",
        "proposed_belief": "proposed_memory",
        "approved_belief": "approved_memory",
    }.get(source, source)


def dedupe_review_queue(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    for item in items:
        ticker = item.get("ticker") or ""
        existing = merged.get(ticker)
        if not existing:
            merged[ticker] = {**item, "reasons": [item.get("reason") or ""]}
            continue
        existing["reasons"].append(item.get("reason") or "")
        if priority_rank.get(item.get("priority") or "medium", 9) < priority_rank.get(
            existing.get("priority") or "medium", 9
        ):
            existing["priority"] = item.get("priority")
    out = []
    for ticker, item in sorted(merged.items()):
        reasons = [r for r in dict.fromkeys(item.get("reasons") or []) if r]
        out.append(
            {
                "ticker": ticker,
                "priority": item.get("priority") or "medium",
                "reason": "; ".join(reasons),
                "reasons": reasons,
            }
        )
    out.sort(key=lambda r: (priority_rank.get(r.get("priority") or "medium", 9), r.get("ticker") or ""))
    return out
