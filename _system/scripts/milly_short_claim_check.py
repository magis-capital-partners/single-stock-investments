#!/usr/bin/env python3
"""Mechanical short-report claim cross-check against local filing extracts."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VERDICT_REFUTED = "refuted_by_filing"
VERDICT_PARTIAL = "partially_valid"
VERDICT_UNADDRESSED = "unaddressed"
VERDICT_STALE = "stale"
VERDICT_HUMAN = "needs_human"

NUMERIC_CLAIM_RE = re.compile(
    r"\b(\d[\d,.]*\s*(?:%|million|billion|bn|mm|m\b|bps|x))\b",
    re.I,
)


def _filing_text(ticker: str, limit: int = 120_000) -> str:
    evidence = ROOT / ticker / "research" / "evidence"
    if not evidence.is_dir():
        return ""
    chunks: list[str] = []
    for pattern in ("filing_digest_*.md", "_text/*.txt"):
        for path in sorted(evidence.glob(pattern), reverse=True):
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore")[: limit // 3])
            except OSError:
                continue
            if sum(len(c) for c in chunks) >= limit:
                break
        if chunks:
            break
    return "\n".join(chunks)[:limit]


def _claim_keywords(claim: str) -> list[str]:
    words = re.findall(r"[A-Za-z]{5,}", claim.lower())
    stop = {"their", "which", "would", "could", "should", "about", "company", "report"}
    return [w for w in words if w not in stop][:8]


def check_claim(claim: str, filing_text: str) -> dict:
    if not claim.strip():
        return {"claim": claim, "verdict": VERDICT_HUMAN, "cite": "", "note": "empty claim"}
    if not filing_text:
        return {"claim": claim, "verdict": VERDICT_UNADDRESSED, "cite": "", "note": "no local filing extract"}

    nums = NUMERIC_CLAIM_RE.findall(claim)
    keywords = _claim_keywords(claim)
    filing_lower = filing_text.lower()

    keyword_hits = sum(1 for k in keywords if k in filing_lower)
    num_hits = sum(1 for n in nums if n.lower().replace(",", "") in filing_lower.replace(",", ""))

    if nums and num_hits == 0 and keyword_hits >= 2:
        return {
            "claim": claim,
            "verdict": VERDICT_PARTIAL,
            "cite": "topic present; numeric claim not verified in extract",
            "note": f"keywords={keyword_hits} nums={len(nums)}",
        }
    if nums and num_hits >= max(1, len(nums) // 2):
        return {
            "claim": claim,
            "verdict": VERDICT_PARTIAL,
            "cite": "numeric/topic overlap in filing extract",
            "note": f"num_hits={num_hits}",
        }
    if keyword_hits >= 3:
        return {
            "claim": claim,
            "verdict": VERDICT_UNADDRESSED,
            "cite": "topic mentioned in filings; claim not directly tested",
            "note": f"keywords={keyword_hits}",
        }
    if nums and num_hits == 0:
        return {
            "claim": claim,
            "verdict": VERDICT_REFUTED,
            "cite": "numeric claim not found in latest filing extract",
            "note": "mechanical absence only",
        }
    return {"claim": claim, "verdict": VERDICT_HUMAN, "cite": "", "note": "insufficient signal"}


def check_short_claims(ticker: str, claims: list[str]) -> list[dict]:
    filing_text = _filing_text(ticker)
    return [check_claim(c, filing_text) for c in claims if c.strip()]
