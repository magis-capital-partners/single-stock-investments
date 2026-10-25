"""Source-scoped letter adjudications and current-return claim protection.

The ledger is reviewed evidence, not a second heuristic classifier. A source
reference is mandatory: a matching ticker/fund/quarter alone cannot override a
different document. Review candidates never change a published action.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORRECTIONS = ROOT / "_system/reference/letter_classification_corrections.json"
REVIEW_QUEUE = ROOT / "_system/reference/letter_classification_review_queue.json"


@lru_cache(maxsize=1)
def correction_rules() -> tuple[dict, ...]:
    return tuple(json.loads(CORRECTIONS.read_text(encoding="utf-8"))["rules"])


@lru_cache(maxsize=1)
def review_candidates() -> tuple[dict, ...]:
    return tuple(json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))["rows"])


@lru_cache(maxsize=1)
def correction_index() -> dict[str, dict]:
    return {r["id"]: r for r in correction_rules()}


@lru_cache(maxsize=1)
def review_index() -> dict[str, list[dict]]:
    out = {}
    for row in review_candidates():
        out.setdefault(":".join(row["id"].split(":")[:3]), []).append(row)
    return out


def source_key(ref: str) -> str:
    ref = str(ref or "").replace("\\", "/")
    ref = ref.split("superinvestor-letters/", 1)[-1].strip("/")
    return re.sub(r"\.(?:txt|pdf)$", "", ref, flags=re.I)


def matches_source(rule: dict, row: dict) -> bool:
    refs = [row.get(k) for k in ("source_file", "source_document", "evidence_ref") if row.get(k)]
    return any(source_key(s["ref"]) == source_key(ref) for s in rule["sources"] for ref in refs) or bool(
        row.get("evidence_url") and row["evidence_url"] in rule.get("document_urls", []))


def matches_content(rule: dict, row: dict) -> bool:
    content_hash = row.get("source_content_sha256")
    reviewed = {s["source_content_sha256"] for s in rule.get("sources", []) if s.get("source_content_sha256")}
    return not content_hash or not reviewed or content_hash in reviewed


def reconcile_letter(ticker: str, row: dict, *, context: dict | None = None) -> dict | None:
    """Return a copy, or None for a reviewed attribution to the wrong issuer."""
    context = context or {}
    fund = row.get("fund_id") or context.get("fund_id")
    quarter = row.get("quarter") or context.get("quarter")
    ref = (row.get("source_file") or row.get("source_document") or row.get("evidence_ref")
           or context.get("source_file") or context.get("source_document"))
    key = f"{ticker}:{fund}:{quarter}"
    rule = correction_index().get(key)
    if rule and not matches_source(rule, {**context, **row}):
        rule = None
    fixed = deepcopy(row)
    if rule and not matches_content(rule, {**context, **row}):
        fixed.update(action="unverified", reported_action=row.get("reported_action", row.get("action")), direction="neutral", relationship="unverified")
        fixed["classification_review"] = {"id": rule["id"], "status": "needs_review", "finding": "Source content changed",
            "reason": "The source bytes differ from the reviewed document; repeat the source review before applying the old correction.", "source_url": rule["source_url"]}
        return fixed
    if not rule:
        candidate = next((r for r in review_index().get(key, []) if r["status"] == "needs_review"
            and (source_key(r["source_ref"]) == source_key(ref)
                or bool(row.get("evidence_url") and row["evidence_url"] == r["source_url"]))), None)
        if candidate:
            fixed.setdefault("reported_action", fixed.get("action"))
            fixed["action"] = "unverified"
            fixed["direction"] = "neutral"
            fixed["relationship"] = "unverified"
            fixed["classification_review"] = {"id": candidate["id"], "status": "needs_review",
                "finding": candidate["finding"], "reason": candidate["reason"], "source_url": candidate["source_url"]}
            if "position_action" in fixed: fixed["position_action"] = "unverified"
            if "title" in fixed:
                fixed["title"] = f'{fixed.get("fund") or fixed.get("source_name") or fund} · action awaiting source review · {ticker} · {quarter}'
            fixed["impact_axis"] = "variant_view"
        return fixed
    if rule["disposition"] == "suppress":
        return None
    fixed["action"] = rule["action"]
    fixed["relationship"] = rule["relationship"]
    fixed["instrument"] = rule["instrument"]
    if "impact_axis" in fixed and rule["relationship"] != "position":
        fixed["impact_axis"] = "variant_view"
    fixed["direction"] = {"new": "bullish", "add": "bullish", "trim": "bearish",
                          "sell": "bearish", "exit": "bearish", "short": "bearish"}.get(rule["action"], "neutral")
    if "position_action" in fixed:
        fixed["position_action"] = rule["action"]
    fixed["classification_review"] = {"id": rule["id"], "status": "corrected",
        "reviewed_on": rule["reviewed_on"], "finding": rule["finding"],
        "reason": rule["reason"], "source_url": rule["source_url"]}
    if rule["source_url"]:
        fixed["evidence_url"] = rule["source_url"]
    # Derived claims/titles must be rebuilt from the corrected action. Source
    # commentary stays intact, including history and other companies' trades.
    if any(k in fixed for k in ("title", "summary", "claim")):
        from insight_format import format_letter_position
        title, summary = format_letter_position(ticker=ticker, fund=fixed.get("fund") or fixed.get("source_name") or context.get("fund") or fund,
            action=rule["action"], quarter=quarter, commentary=fixed.get("commentary") or fixed.get("thesis") or "")
        if "title" in fixed: fixed["title"] = title
        if "summary" in fixed: fixed["summary"] = summary
        if "claim" in fixed: fixed["claim"] = summary
    return fixed


def reconcile_positions(letter: dict) -> dict:
    fixed = deepcopy(letter)
    for field in ("positions", "mentions"):
        if field in fixed:
            fixed[field] = [r for pos in fixed[field]
                if (r := reconcile_letter(str(pos.get("ticker") or ""), pos, context=letter)) is not None]
    if "tickers" in fixed:
        suppressed = {r["ticker"] for r in correction_rules() if r["disposition"] == "suppress"
            and r["fund_id"] == letter.get("fund_id") and r["quarter"] == letter.get("quarter")
            and matches_source(r, letter) and matches_content(r, letter)}
        fixed["tickers"] = [t for t in fixed["tickers"] if t not in suppressed]
    return fixed


def classification_audit(ticker: str) -> dict:
    confirmed = [{k: r[k] for k in ("id", "fund_id", "quarter", "finding", "reason", "disposition", "action", "source_url")}
        for r in correction_rules() if r["ticker"] == ticker]
    pending = [{k: r[k] for k in ("id", "fund_id", "quarter", "finding", "reason", "source_url")}
        for r in review_candidates() if r["ticker"] == ticker and r["status"] == "needs_review"]
    return {"as_of": "2026-10-24", "confirmed": confirmed, "needs_review": pending,
        "confirmed_count": len(confirmed), "review_count": len(pending)}


# A prospective return claim must include both an IRR label and a numeric
# percent in its clause. Hurdles and historical performance are retained.
RETURN_CLAIM = re.compile(r"(?:\bIRRs?\b|\b(?:base|forward|expected|annualized)[ -]return\b)", re.I)
PERCENT = re.compile(r"[+\-~≈]?\d+(?:\.\d+)?\s*(?:%|percent)\b|[+\-~≈]?\d+(?:\.\d+)?\s*%", re.I)
HISTORICAL = re.compile(r"\b(?:historical|historically|since inception|realized)\b", re.I)
HURDLE_ONLY = re.compile(r"\b(?:require|required|hurdle|minimum|threshold)\b.{0,35}\bIRR\b|\bIRR\s+(?:hurdle|threshold|target)\b", re.I)


def gate_return_text(text: str, publishable: bool) -> str:
    if publishable or not text or not RETURN_CLAIM.search(text):
        return text
    # Splitting at semicolons/dashes preserves the investment case around an
    # unsupported return. Decimal points are deliberately not boundaries.
    clauses = re.split(r"(;|\s+[—–]\s+)", text)
    for i in range(0, len(clauses), 2):
        part = clauses[i]
        if RETURN_CLAIM.search(part) and PERCENT.search(part) and not HISTORICAL.search(part) and not HURDLE_ONLY.search(part):
            # Remove numbers only from clauses carrying a prospective claim;
            # retain the exact original separately for audit and source access.
            clauses[i] = " Forward IRR unavailable; dated cash flows and publication checks required."
    return "".join(clauses)


def gate_return_claims(row: dict) -> None:
    text = (row.get("return_claim_audit") or {}).get("original_thesis") or row.get("one_line_thesis") or ""
    safe = gate_return_text(text, bool((row.get("valuation_decision") or {}).get("return_publishable")))
    if safe != text:
        row.setdefault("return_claim_audit", {"status": "withheld", "original_thesis": text,
            "reason": "Current thesis conflicts with canonical forward-return eligibility; source text retained for audit."})
        row["one_line_thesis"] = safe.strip()
