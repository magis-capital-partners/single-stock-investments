#!/usr/bin/env python3
"""Build a compact cross-referenced research memory for the dashboard."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "research_memory.json"
INSIGHTS_PATH = DATA_DIR / "insights.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
BIOTECH_FUNDS_PATH = ROOT / "_system" / "reference" / "market-data" / "ownership" / "biotech_specialist_funds.json"

BIOTECH_TERMS = (
    "biotech",
    "biopharma",
    "pharma",
    "drug",
    "clinical",
    "fda",
    "pdufa",
    "phase 1",
    "phase 2",
    "phase 3",
    "therapy",
    "therapeutics",
    "diagnostic",
    "life sciences",
    "healthcare",
)

INFLECTION_TERMS = (
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
    "earnings",
    "free cash flow",
)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


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
    }.get(source, source)


def source_key(row: dict) -> str:
    return (
        row.get("evidence_url")
        or row.get("evidence_ref")
        or row.get("source_document")
        or row.get("source_file")
        or row.get("inventory_ref")
        or row.get("id")
        or "unknown"
    )


def source_record(row: dict) -> dict:
    key = source_key(row)
    return {
        "source_id": stable_id(key),
        "source_key": key,
        "title": short_text(row.get("source_name") or row.get("fund") or row.get("publisher") or row.get("title") or source_type(row), 140),
        "source_type": source_type(row),
        "date": row.get("observed_at") or row.get("as_of") or row.get("letter_date") or row.get("date"),
        "author": row.get("fund") or row.get("source_name") or row.get("publisher"),
        "url": row.get("evidence_url") or row.get("evidence_ref"),
        "label": row.get("evidence_label") or "source",
    }


def claim_type(row: dict) -> str:
    axis = row.get("impact_axis")
    event = row.get("event_type") or ""
    text = " ".join([row.get("title") or "", row.get("summary") or "", row.get("claim") or ""]).lower()
    if row.get("source") in {"superinvestor_letter", "sumzero_research", "third_party"}:
        return "thesis"
    if axis == "ownership" or "13f" in text or "insider" in text:
        return "ownership"
    if any(t in text for t in INFLECTION_TERMS) or event == "filing_metric":
        return "inflection"
    if axis == "risk" or row.get("direction") == "bearish":
        return "risk"
    if axis == "catalyst":
        return "catalyst"
    return axis or "context"


def evidence_effect(row: dict, ctype: str) -> str:
    direction = row.get("direction") or "neutral"
    if direction == "bearish" or ctype == "risk":
        return "disconfirms" if ctype != "risk" else "confirms"
    if direction == "bullish":
        return "confirms"
    if direction == "neutral":
        return "neutral"
    return "mixed"


def confidence_score(row: dict) -> int:
    score = int(row.get("score") or 0)
    source = row.get("source")
    bonus = {
        "filing": 20,
        "earnings": 18,
        "insider": 14,
        "superinvestor_letter": 12,
        "news": 8,
        "third_party": 7,
        "sumzero_research": 7,
    }.get(source, 4)
    return score + bonus


def all_insight_rows(insights: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for row in insights.get("events") or []:
        if row.get("ticker"):
            key = row.get("id") or stable_id(row.get("ticker"), row.get("title"), row.get("evidence_url"))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    for ticker, ticker_rows in (insights.get("by_ticker") or {}).items():
        for row in ticker_rows or []:
            if not row.get("ref") and not row.get("ticker"):
                row = {**row, "ref": ticker}
            key = row.get("id") or stable_id(row.get("ref") or ticker, row.get("claim"), row.get("evidence_url"))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def build_entity_map(registry: dict, classification: dict, insights: dict) -> dict:
    holdings = registry.get("holdings") or {}
    watchlist = registry.get("watchlist") or {}
    tickers = {}
    for ticker, meta in {**watchlist, **holdings}.items():
        cls = classification.get(ticker) or meta.get("classification") or {}
        tickers[ticker] = {
            "entity_id": f"ticker:{ticker}",
            "ticker": ticker,
            "company": meta.get("company", ticker),
            "market": meta.get("market"),
            "exchange": meta.get("exchange"),
            "aliases": sorted({ticker, meta.get("company", ticker), ticker.replace(".", " ")}),
            "portfolio_section": "holding" if ticker in holdings else "watchlist",
            "investment_sleeve": cls.get("investment_sleeve"),
            "archetype": cls.get("archetype"),
        }
    funds = {}
    for fund in insights.get("fund_registry") or []:
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        funds[fid] = {
            "entity_id": f"fund:{fid}",
            "fund_id": fid,
            "fund": fund.get("fund"),
            "manager": fund.get("manager"),
            "latest_quarter": fund.get("quarter"),
            "our_tickers": fund.get("our_tickers") or [],
        }
    biotech_funds_doc = load_json(BIOTECH_FUNDS_PATH, {"funds": []})
    for fund in biotech_funds_doc.get("funds") or []:
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        funds.setdefault(
            fid,
            {
                "entity_id": f"fund:{fid}",
                "fund_id": fid,
                "fund": fund.get("fund"),
                "manager": fund.get("manager"),
                "latest_quarter": None,
                "our_tickers": [],
            },
        )
        funds[fid].update(
            {
                "specialty": fund.get("specialty"),
                "signal_role": fund.get("signal_role"),
                "notes": fund.get("notes"),
            }
        )
    return {"tickers": tickers, "funds": funds}


def is_biotech_ticker(ticker: str, entity: dict, rows: list[dict]) -> bool:
    sleeve = str(entity.get("investment_sleeve") or "").lower()
    company = str(entity.get("company") or "").lower()
    if any(term in sleeve or term in company for term in BIOTECH_TERMS):
        return True
    text = " ".join(
        short_text((r.get("title") or "") + " " + (r.get("summary") or "") + " " + (r.get("claim") or ""), 500).lower()
        for r in rows[:50]
    )
    return any(term in text for term in BIOTECH_TERMS)


def build() -> dict:
    insights = load_json(INSIGHTS_PATH, {})
    registry = load_json(REGISTRY_PATH, {"holdings": {}, "watchlist": {}})
    classification = load_json(CLASS_PATH, {})
    entities = build_entity_map(registry, classification, insights)
    rows = all_insight_rows(insights)

    source_registry: dict[str, dict] = {}
    claim_ledger: list[dict] = []
    evidence_ledger: list[dict] = []
    by_ticker: dict[str, dict] = {}
    rows_by_ticker: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        ticker = (row.get("ticker") or row.get("ref") or "").upper()
        if not ticker or ticker not in entities["tickers"]:
            continue
        rows_by_ticker[ticker].append(row)
        src = source_record(row)
        existing = source_registry.get(src["source_id"])
        if existing:
            existing["tickers"] = sorted(set(existing.get("tickers") or []) | {ticker})
        else:
            src["tickers"] = [ticker]
            source_registry[src["source_id"]] = src

        text = short_text(row.get("summary") or row.get("claim") or row.get("title") or "", 320)
        if not text:
            continue
        ctype = claim_type(row)
        cid = stable_id(ticker, ctype, row.get("direction"), text.lower())
        claim = {
            "claim_id": cid,
            "ticker": ticker,
            "entity_id": f"ticker:{ticker}",
            "claim": text,
            "claim_type": ctype,
            "direction": row.get("direction") or "neutral",
            "confidence": row.get("confidence") or "med",
            "confidence_score": confidence_score(row),
            "date": row.get("observed_at") or row.get("as_of") or row.get("date"),
            "source_id": src["source_id"],
            "source_type": src["source_type"],
            "source_title": src["title"],
            "evidence_url": src["url"],
            "evidence_label": src["label"],
        }
        claim_ledger.append(claim)
        evidence_ledger.append(
            {
                "evidence_id": stable_id("evidence", cid, src["source_id"], row.get("id") or row.get("event_type")),
                "claim_id": cid,
                "ticker": ticker,
                "effect": evidence_effect(row, ctype),
                "date": claim["date"],
                "source_id": src["source_id"],
                "source_type": src["source_type"],
                "summary": text,
                "url": src["url"],
                "label": src["label"],
            }
        )

    deduped_claims: dict[str, dict] = {}
    for claim in sorted(claim_ledger, key=lambda c: (c.get("confidence_score") or 0, c.get("date") or ""), reverse=True):
        deduped_claims.setdefault(claim["claim_id"], claim)
    claim_ledger = list(deduped_claims.values())

    evidence_by_claim: dict[str, list[dict]] = defaultdict(list)
    for ev in evidence_ledger:
        evidence_by_claim[ev["claim_id"]].append(ev)

    for ticker, entity in entities["tickers"].items():
        ticker_claims = [c for c in claim_ledger if c["ticker"] == ticker]
        ticker_evidence = [e for e in evidence_ledger if e["ticker"] == ticker]
        effect_counts = Counter(e["effect"] for e in ticker_evidence)
        source_ids = {c["source_id"] for c in ticker_claims if c.get("source_id")}
        source_types = Counter(c["source_type"] for c in ticker_claims)
        top_claims = sorted(ticker_claims, key=lambda c: (c["confidence_score"], c.get("date") or ""), reverse=True)[:6]
        inflection = [c for c in ticker_claims if c["claim_type"] == "inflection"]
        ownership = [c for c in ticker_claims if c["claim_type"] == "ownership"]
        risks = [c for c in ticker_claims if c["claim_type"] == "risk" or c["direction"] == "bearish"]
        biotech = is_biotech_ticker(ticker, entity, rows_by_ticker.get(ticker, []))
        specialist_mentions = [
            c for c in ticker_claims
            if c["source_type"] == "letter" and any(term in (c.get("source_title") or "").lower() for term in ("baker", "perceptive", "ra capital", "orbimed", "ecor1", "redmile", "deerfield", "casdin", "venbio", "samsara"))
        ]
        by_ticker[ticker] = {
            "ticker": ticker,
            "company": entity.get("company"),
            "claim_count": len(ticker_claims),
            "evidence_count": len(ticker_evidence),
            "source_count": len(source_ids),
            "source_mix": sorted(source_types),
            "confirming_count": effect_counts.get("confirms", 0),
            "disconfirming_count": effect_counts.get("disconfirms", 0),
            "mixed_count": effect_counts.get("mixed", 0),
            "neutral_count": effect_counts.get("neutral", 0),
            "top_claims": top_claims,
            "inflection_claims": sorted(inflection, key=lambda c: c["confidence_score"], reverse=True)[:3],
            "risk_claims": sorted(risks, key=lambda c: c["confidence_score"], reverse=True)[:3],
            "ownership_claims": sorted(ownership, key=lambda c: c["confidence_score"], reverse=True)[:3],
            "biotech": {
                "is_biotech_related": biotech,
                "specialist_13f_ready": biotech,
                "specialist_mentions": specialist_mentions[:4],
                "tracked_specialist_fund_count": len(load_json(BIOTECH_FUNDS_PATH, {"funds": []}).get("funds") or []),
                "ownership_records": [],
            },
        }

    review_queue = []
    for ticker, mem in by_ticker.items():
        if mem["claim_count"] and not mem["source_count"]:
            review_queue.append({"ticker": ticker, "reason": "claims without source", "priority": "high"})
        if mem["disconfirming_count"] > 0:
            review_queue.append({"ticker": ticker, "reason": "disconfirming evidence present", "priority": "high"})
        if mem["claim_count"] == 0:
            review_queue.append({"ticker": ticker, "reason": "no claims in memory", "priority": "medium"})
        if mem["biotech"]["is_biotech_related"] and not mem["biotech"]["ownership_records"]:
            review_queue.append({"ticker": ticker, "reason": "biotech 13F ownership not loaded", "priority": "medium"})

    biotech_funds = load_json(BIOTECH_FUNDS_PATH, {"funds": []}).get("funds") or []
    return {
        "generated_at": now_iso(),
        "schema_version": 1,
        "summary": {
            "source_count": len(source_registry),
            "entity_count": len(entities["tickers"]) + len(entities["funds"]),
            "ticker_count": len(entities["tickers"]),
            "fund_count": len(entities["funds"]),
            "claim_count": len(claim_ledger),
            "evidence_count": len(evidence_ledger),
            "review_queue_count": len(review_queue),
            "biotech_specialist_count": len(biotech_funds),
            "biotech_related_ticker_count": sum(1 for v in by_ticker.values() if v["biotech"]["is_biotech_related"]),
        },
        "source_registry": sorted(source_registry.values(), key=lambda s: (s.get("date") or "", s.get("title") or ""), reverse=True),
        "entity_map": entities,
        "claim_ledger": sorted(claim_ledger, key=lambda c: (c.get("date") or "", c.get("confidence_score") or 0), reverse=True),
        "evidence_ledger": sorted(evidence_ledger, key=lambda e: e.get("date") or "", reverse=True),
        "by_ticker": by_ticker,
        "review_queue": review_queue,
        "biotech": {
            "specialist_funds": biotech_funds,
            "ownership_records": [],
            "notes": "13F parser target: populate ownership_records with fund_id, ticker, quarter, market_value, shares, change_type, and source_url.",
        },
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({payload['summary']['claim_count']} claims, {payload['summary']['source_count']} sources)"
    )


if __name__ == "__main__":
    main()
