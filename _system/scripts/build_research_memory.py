#!/usr/bin/env python3
"""Build a compact cross-referenced research memory for the dashboard."""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "magis-capital-partners/single-stock-investments")

from document_store import best_document_label, best_document_url, document_id_for_ref  # noqa: E402
from memory_claim_sources import (  # noqa: E402
    from_biotech_methodology,
    load_biotech_factor_spec,
    supplemental_claim_rows,
)
from memory_common import (  # noqa: E402
    SPECIALIST_FUND_TERMS,
    claim_type,
    confidence_score,
    dedupe_review_queue,
    evidence_effect,
    is_biotech_ticker,
    is_biotech_quant_universe_ticker,
    is_low_value_claim,
    now_iso,
    short_text,
    slug,
    source_type,
    stable_id,
)
from ownership_common import (  # noqa: E402
    FUNDS_PATH,
    RECORDS_DIR,
    SIGNALS_PATH,
    load_json,
    save_json,
)

DATA_DIR = ROOT / "dashboard" / "data"
OUTPUT = DATA_DIR / "research_memory.json"
EVIDENCE_OUTPUT = DATA_DIR / "research_memory_evidence.json"
INSIGHTS_PATH = DATA_DIR / "insights.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"

MAX_CLAIMS = 12000
MAX_SOURCES = 4000
MAX_EVIDENCE = 20000


def source_key(row: dict) -> str:
    return (
        row.get("evidence_ref")
        or row.get("source_document")
        or row.get("source_file")
        or row.get("inventory_ref")
        or row.get("evidence_url")
        or row.get("id")
        or "unknown"
    )


def resolve_evidence_url(row: dict) -> str | None:
    raw = row.get("evidence_url") or row.get("evidence_ref") or source_key(row)
    if not raw or raw == "unknown":
        return None
    text = str(raw)
    if text.startswith(("http://", "https://")):
        return text
    return best_document_url(text, GITHUB_REPO)


def resolve_evidence_label(row: dict, url: str | None = None) -> str:
    if row.get("evidence_label"):
        return str(row["evidence_label"])
    ref = row.get("evidence_ref") or row.get("evidence_url") or source_key(row)
    return best_document_label(ref) if ref and ref != "unknown" else "source"


def source_record(row: dict) -> dict:
    key = source_key(row)
    url = resolve_evidence_url(row)
    return {
        "source_id": stable_id(key),
        "source_key": key,
        "title": short_text(
            row.get("source_name") or row.get("fund") or row.get("publisher") or row.get("title") or source_type(row),
            140,
        ),
        "source_type": source_type(row),
        "date": row.get("observed_at") or row.get("as_of") or row.get("letter_date") or row.get("date"),
        "author": row.get("fund") or row.get("source_name") or row.get("publisher"),
        "url": url,
        "label": resolve_evidence_label(row, url),
        "document_id": row.get("evidence_document_id") or document_id_for_ref(key),
    }


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


def load_ownership_records() -> tuple[list[dict], dict]:
    latest = load_json(RECORDS_DIR / "latest.json", {"records": []})
    records = latest.get("records") or []
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        by_ticker[row.get("ticker") or ""].append(row)
    return records, dict(by_ticker)


def load_biotech_watchlist(registry: dict) -> set[str]:
    out: set[str] = set()
    for bucket in ("holdings", "watchlist"):
        for ticker, meta in (registry.get(bucket) or {}).items():
            if meta.get("biotech_watchlist"):
                out.add(ticker.upper())
    return out


def build_entity_map(registry: dict, classification: dict, insights: dict, biotech_funds: list[dict]) -> dict:
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
            "portfolio_section": "holding" if ticker in holdings else "watchlist",
            "investment_sleeve": cls.get("investment_sleeve"),
            "archetype": cls.get("archetype"),
            "biotech_watchlist": bool(meta.get("biotech_watchlist")),
        }

    funds: dict[str, dict] = {}
    for fund in biotech_funds:
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        funds[fid] = {
            "entity_id": f"fund:{fid}",
            "fund_id": fid,
            "fund": fund.get("fund"),
            "specialty": fund.get("specialty"),
            "signal_role": fund.get("signal_role"),
            "priority": fund.get("priority"),
            "our_tickers": [],
        }

    for fund in insights.get("fund_registry") or []:
        our = fund.get("our_tickers") or []
        if not our:
            continue
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        if fid in funds:
            funds[fid]["our_tickers"] = sorted(set(funds[fid].get("our_tickers") or []) | set(our))
            continue
        funds[fid] = {
            "entity_id": f"fund:{fid}",
            "fund_id": fid,
            "fund": fund.get("fund"),
            "manager": fund.get("manager"),
            "latest_quarter": fund.get("quarter"),
            "our_tickers": our,
        }
    return {"tickers": tickers, "funds": funds}


def ownership_claim_rows(records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for rec in records:
        change = rec.get("change_type") or "unchanged"
        if change == "unchanged":
            continue
        direction = "bullish" if change in {"new", "add"} else "bearish" if change in {"trim", "exit"} else "neutral"
        fund = rec.get("fund") or rec.get("fund_id")
        ticker = rec.get("ticker")
        summary = f"{fund} {change} {ticker} ({rec.get('quarter')})"
        if rec.get("change_shares_pct") is not None:
            summary += f"; {rec['change_shares_pct']:+.1f}% shares"
        rows.append(
            {
                "ticker": ticker,
                "source": "specialist_13f",
                "claim_type": "ownership",
                "direction": direction,
                "title": f"Specialist 13F {change}",
                "summary": summary,
                "observed_at": rec.get("filing_date"),
                "impact_axis": "ownership",
                "evidence_url": rec.get("source_url"),
                "evidence_label": "13F",
                "score": 12 if rec.get("fund_id") in {"baker-bros", "ra-capital", "orbimed", "perceptive-advisors"} else 8,
            }
        )
    return rows


def build() -> tuple[dict, dict]:
    insights = load_json(INSIGHTS_PATH, {})
    registry = load_json(REGISTRY_PATH, {"holdings": {}, "watchlist": {}})
    classification = load_json(CLASS_PATH, {})
    biotech_funds = load_json(FUNDS_PATH, {"funds": []}).get("funds") or []
    signals_doc = load_json(SIGNALS_PATH, {})
    ownership_records, ownership_by_ticker = load_ownership_records()
    biotech_watchlist = load_biotech_watchlist(registry)
    entities = build_entity_map(registry, classification, insights, biotech_funds)

    rows = all_insight_rows(insights)
    rows.extend(ownership_claim_rows(ownership_records))
    methodology_rows = from_biotech_methodology()
    factor_spec = load_biotech_factor_spec()

    for ticker in entities["tickers"]:
        ticker_dir = ROOT / ticker
        if ticker_dir.is_dir():
            rows.extend(supplemental_claim_rows(ticker, ticker_dir))

    source_registry: dict[str, dict] = {}
    claim_ledger: list[dict] = []
    evidence_ledger: list[dict] = []
    rows_by_ticker: dict[str, list[dict]] = defaultdict(list)
    methodology_claims: list[dict] = []

    for row in methodology_rows:
        text = short_text(row.get("summary") or row.get("title") or "", 320)
        if not text:
            continue
        src = source_record(row)
        existing = source_registry.get(src["source_id"])
        if not existing:
            src["tickers"] = []
            source_registry[src["source_id"]] = src
        methodology_claims.append(
            {
                "claim_id": stable_id("methodology", text.lower(), src["source_id"]),
                "ticker": None,
                "claim": text,
                "claim_type": "methodology",
                "direction": "neutral",
                "confidence": "med",
                "confidence_score": confidence_score(row),
                "date": row.get("observed_at"),
                "source_id": src["source_id"],
                "source_type": src["source_type"],
                "source_title": src["title"],
                "evidence_url": src["url"],
                "evidence_label": src["label"],
            }
        )

    for row in rows:
        ticker = (row.get("ticker") or row.get("ref") or "").upper()
        if not ticker or ticker not in entities["tickers"]:
            continue
        text = short_text(row.get("summary") or row.get("claim") or row.get("title") or "", 320)
        if not text or is_low_value_claim(text, row):
            continue
        rows_by_ticker[ticker].append(row)
        src = source_record(row)
        existing = source_registry.get(src["source_id"])
        if existing:
            existing["tickers"] = sorted(set(existing.get("tickers") or []) | {ticker})
        else:
            src["tickers"] = [ticker]
            source_registry[src["source_id"]] = src

        ctype = claim_type(row)
        cid = stable_id(ticker, ctype, row.get("direction"), text.lower(), row.get("source"), src["source_id"])
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
            "evidence_document_id": src.get("document_id"),
            "quarter": row.get("quarter"),
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
                "document_id": src.get("document_id"),
            }
        )

    deduped_claims: dict[str, dict] = {}
    for claim in sorted(claim_ledger, key=lambda c: (c.get("confidence_score") or 0, c.get("date") or ""), reverse=True):
        deduped_claims.setdefault(claim["claim_id"], claim)
    claim_ledger = list(deduped_claims.values())
    claim_ledger.sort(key=lambda c: (c.get("date") or "", c.get("confidence_score") or 0), reverse=True)
    if len(claim_ledger) > MAX_CLAIMS:
        claim_ledger = claim_ledger[:MAX_CLAIMS]

    claim_ids = {c["claim_id"] for c in claim_ledger}
    evidence_ledger = [e for e in evidence_ledger if e["claim_id"] in claim_ids]
    if len(evidence_ledger) > MAX_EVIDENCE:
        evidence_ledger = evidence_ledger[:MAX_EVIDENCE]

    source_registry_list = sorted(
        source_registry.values(), key=lambda s: (s.get("date") or "", s.get("title") or ""), reverse=True
    )
    if len(source_registry_list) > MAX_SOURCES:
        source_registry_list = source_registry_list[:MAX_SOURCES]

    by_ticker: dict[str, dict] = {}
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
        meta = (registry.get("holdings") or {}).get(ticker) or (registry.get("watchlist") or {}).get(ticker) or {}
        biotech = is_biotech_ticker(ticker, entity, meta, biotech_watchlist=biotech_watchlist)
        specialist_mentions = [
            c
            for c in ticker_claims
            if c["source_type"] == "letter"
            and any(term in (c.get("source_title") or "").lower() for term in SPECIALIST_FUND_TERMS)
        ]
        ticker_ownership = ownership_by_ticker.get(ticker, [])
        signal = (signals_doc.get("by_ticker") or {}).get(ticker) or {}
        in_quant = bool(signal.get("in_biotech_quant_universe")) or is_biotech_quant_universe_ticker(
            ticker,
            entity,
            meta,
            biotech_watchlist=biotech_watchlist,
            ownership_records=ticker_ownership,
        )
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
                "in_biotech_quant_universe": in_quant,
                "awaiting_13f_ingest": in_quant and not ticker_ownership,
                "specialist_mentions": specialist_mentions[:4],
                "tracked_specialist_fund_count": len(biotech_funds),
                "ownership_records": ticker_ownership[:20],
                "signals": {
                    "consensus_score": signal.get("consensus_score"),
                    "consensus_quintile": signal.get("consensus_quintile"),
                    "core_fund_holder_count": signal.get("core_fund_holder_count"),
                    "specialist_holder_count": signal.get("specialist_holder_count"),
                    "spend_value_quintile": signal.get("spend_value_quintile"),
                    "insider_score": signal.get("insider_score"),
                    "composite_score": signal.get("composite_score"),
                    "convergence_flag": signal.get("convergence_flag"),
                    "initiation_signal": signal.get("initiation_signal"),
                    "exit_signal": signal.get("exit_signal"),
                    "size_bucket": signal.get("size_bucket"),
                },
            },
        }

    review_queue: list[dict] = []
    holdings = set((registry.get("holdings") or {}).keys())
    watchlist = set((registry.get("watchlist") or {}).keys())
    book = holdings | watchlist
    for ticker, mem in by_ticker.items():
        if mem["claim_count"] and not mem["source_count"]:
            review_queue.append({"ticker": ticker, "reason": "claims without source", "priority": "high"})
        if mem["disconfirming_count"] > 0:
            review_queue.append({"ticker": ticker, "reason": "disconfirming evidence present", "priority": "high"})
        if mem["claim_count"] == 0 and ticker in book:
            review_queue.append({"ticker": ticker, "reason": "no claims in memory", "priority": "medium"})
        if mem["biotech"]["in_biotech_quant_universe"] and not mem["biotech"]["ownership_records"]:
            review_queue.append({"ticker": ticker, "reason": "biotech 13F ownership not loaded", "priority": "medium"})
    review_queue = dedupe_review_queue(review_queue)

    summary = {
        "source_count": len(source_registry_list),
        "entity_count": len(entities["tickers"]) + len(entities["funds"]),
        "ticker_count": len(entities["tickers"]),
        "fund_count": len(entities["funds"]),
        "claim_count": len(claim_ledger),
        "evidence_count": len(evidence_ledger),
        "review_queue_count": len(review_queue),
        "biotech_specialist_count": len(biotech_funds),
        "biotech_related_ticker_count": sum(1 for v in by_ticker.values() if v["biotech"]["is_biotech_related"]),
        "biotech_quant_universe_count": sum(1 for v in by_ticker.values() if v["biotech"]["in_biotech_quant_universe"]),
        "ownership_record_count": len(ownership_records),
        "methodology_claim_count": len(methodology_claims),
    }

    quant_signals = {
        k: v
        for k, v in (signals_doc.get("by_ticker") or {}).items()
        if v.get("in_biotech_quant_universe")
    }
    quant_tickers = set(quant_signals) | {
        t for t, mem in by_ticker.items() if mem["biotech"].get("in_biotech_quant_universe")
    }
    quant_ownership = [r for r in ownership_records if r.get("ticker") in quant_tickers]

    live_factors = []
    for factor in factor_spec.get("factors") or []:
        keys = factor.get("signal_keys") or []
        present = False
        if keys and quant_signals:
            present = any(
                row.get(k) is not None
                for row in quant_signals.values()
                for k in keys
            )
        status = factor.get("status") or "planned"
        fid = factor.get("id")
        if fid == "specialist_consensus" and quant_signals:
            present = True
        if fid == "spend_value" and any(row.get("spend_value") is not None for row in quant_signals.values()):
            present = True
        if fid == "insider_non_ceo" and any(row.get("insider_score") is not None for row in quant_signals.values()):
            present = True
        if fid == "short_interest" and any((row.get("short_candidate_score") or 0) > 0 for row in quant_signals.values()):
            present = True
        live_factors.append(
            {
                "id": fid,
                "label": factor.get("label") or fid,
                "status": status,
                "present": present,
                "weight_long": factor.get("weight_long"),
                "weight_short": factor.get("weight_short"),
            }
        )

    memory_doc = {
        "generated_at": now_iso(),
        "schema_version": 2,
        "summary": summary,
        "source_registry": source_registry_list,
        "entity_map": entities,
        "claim_ledger": claim_ledger,
        "methodology_claims": methodology_claims,
        "by_ticker": by_ticker,
        "review_queue": review_queue,
        "biotech": {
            "specialist_funds": biotech_funds,
            "ownership_records": quant_ownership,
            "signals": {
                **signals_doc,
                "by_ticker": quant_signals,
                "ticker_count": len(quant_signals),
            },
            "factor_spec": factor_spec,
            "factor_scoreboard": live_factors,
            "library_catalog": factor_spec.get("library_catalog") or [],
            "methodology_claims": methodology_claims,
            "notes": "13F records stored in _system/reference/market-data/ownership/records/",
        },
    }
    evidence_doc = {
        "generated_at": now_iso(),
        "schema_version": 1,
        "evidence_ledger": sorted(evidence_ledger, key=lambda e: e.get("date") or "", reverse=True),
        "evidence_by_claim": {},
    }
    by_claim: dict[str, list[dict]] = defaultdict(list)
    for ev in evidence_doc["evidence_ledger"]:
        by_claim[ev["claim_id"]].append(ev)
    evidence_doc["evidence_by_claim"] = {k: v[:6] for k, v in by_claim.items()}
    return memory_doc, evidence_doc


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    memory_doc, evidence_doc = build()
    save_json(OUTPUT, memory_doc)
    save_json(EVIDENCE_OUTPUT, evidence_doc)
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({memory_doc['summary']['claim_count']} claims, {memory_doc['summary']['source_count']} sources, "
        f"{memory_doc['summary']['ownership_record_count']} 13F records)"
    )


if __name__ == "__main__":
    main()
