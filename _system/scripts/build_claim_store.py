#!/usr/bin/env python3
"""Build the unified claim store at ``_system/data/claims.jsonl``.

Unifies three existing sources into one agent-retrieval layer where every row
carries type (fact / inference / opinion), status (approved / verified /
pending / assumption), and a cited source path:

  1. ``{TICKER}/research/valuation_fact_ledger.json`` facts (locked = approved)
  2. ``{TICKER}/research/thesis_card.json`` thesis, variant view, assumptions
  3. ``{TICKER}/research/evidence/ssi_verified_claims.json`` (severity >= 3,
     capped per ticker; the full set stays in the per-ticker file)

Usage:
  python _system/scripts/build_claim_store.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_schema import validate  # noqa: E402
from atomic_io import attach_envelope, write_json_if_changed  # noqa: E402

OUT_JSONL = ROOT / "_system" / "data" / "claims.jsonl"
OUT_SUMMARY = ROOT / "_system" / "data" / "claims_summary.json"
MAX_VERIFIED_PER_TICKER = 50
MIN_VERIFIED_SEVERITY = 3


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _claim_id(ticker: str, statement: str, source_path: str) -> str:
    digest = hashlib.sha256(f"{ticker}|{source_path}|{statement}".encode("utf-8")).hexdigest()
    return f"sha256:{digest[:24]}"


def _row(ticker: str, statement: str, claim_type: str, status: str, source_path: str, **extra: Any) -> dict[str, Any] | None:
    statement = " ".join(str(statement or "").split())[:1200]
    if not statement or not source_path:
        return None
    row: dict[str, Any] = {
        "claim_id": _claim_id(ticker, statement, source_path),
        "ticker": ticker,
        "statement": statement,
        "claim_type": claim_type,
        "status": status,
        "source_path": source_path,
        "source_locator": extra.get("source_locator"),
        "as_of": extra.get("as_of"),
        "confidence": extra.get("confidence"),
    }
    return {k: v for k, v in row.items() if v is not None}


def build_claims(*, root: Path = ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any] | None) -> None:
        if row and row["claim_id"] not in seen:
            seen.add(row["claim_id"])
            rows.append(row)

    for card_path in sorted(root.glob("*/research/thesis_card.json")):
        ticker = card_path.parent.parent.name
        card = _load(card_path)
        rel = card_path.relative_to(root).as_posix()
        as_of = (card.get("last_verified") or {}).get("valuation_as_of") or card.get("generated_at")
        add(_row(ticker, card.get("thesis") or "", "inference", "pending", rel, as_of=as_of))
        add(_row(ticker, card.get("why_market_wrong") or "", "inference", "pending", rel, as_of=as_of))
        for assumption in card.get("key_assumptions") or []:
            if isinstance(assumption, dict):
                add(_row(
                    ticker,
                    f"{assumption.get('input')}: {assumption.get('value')}",
                    "inference", "assumption", rel,
                    source_locator=str(assumption.get("source") or "") or None, as_of=as_of,
                ))

    for ledger_path in sorted(root.glob("*/research/valuation_fact_ledger.json")):
        ticker = ledger_path.parent.parent.name
        ledger = _load(ledger_path)
        rel = ledger_path.relative_to(root).as_posix()
        for fact in ledger.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            source = fact.get("source") or {}
            add(_row(
                ticker,
                f"{fact.get('field_id')} = {fact.get('value')} {fact.get('unit') or ''}".strip(),
                "fact", "approved" if fact.get("locked") else "verified",
                (source.get("ref") if isinstance(source, dict) else None) or rel,
                source_locator=(source.get("locator") if isinstance(source, dict) else None),
                as_of=(source.get("as_of") if isinstance(source, dict) else None) or ledger.get("as_of"),
                confidence=fact.get("confidence"),
            ))

    capped = 0
    for verified_path in sorted(root.glob("*/research/evidence/ssi_verified_claims.json")):
        ticker = verified_path.parent.parent.parent.name
        payload = _load(verified_path)
        claims = [c for c in (payload.get("verified_claims") or []) if isinstance(c, dict)]
        claims.sort(key=lambda c: float(c.get("severity") or 0), reverse=True)
        kept = 0
        for claim in claims:
            if kept >= MAX_VERIFIED_PER_TICKER:
                capped += 1
                continue
            if float(claim.get("severity") or 0) < MIN_VERIFIED_SEVERITY:
                continue
            ref = claim.get("evidence_ref") or {}
            source_path = ref.get("source_path") if isinstance(ref, dict) else None
            add(_row(
                ticker, claim.get("statement") or "", "fact", "verified",
                source_path or verified_path.relative_to(root).as_posix(),
                as_of=payload.get("as_of"), confidence=claim.get("confidence"),
            ))
            kept += 1

    rows.sort(key=lambda r: (str(r.get("ticker")), str(r.get("claim_type")), str(r.get("statement"))))
    for row in rows:
        errors = validate(row, "claim")
        if errors:
            raise ValueError(f"invalid claim row {row.get('claim_id')}: {errors}")
    return rows


def main(argv: list[str] | None = None) -> int:
    rows = build_claims()
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    from atomic_io import write_text_if_changed

    changed = write_text_if_changed(OUT_JSONL, text)
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_status[str(row["status"])] = by_status.get(str(row["status"]), 0) + 1
        by_type[str(row["claim_type"])] = by_type.get(str(row["claim_type"]), 0) + 1
    summary = attach_envelope(
        {
            "schema_version": "magis.claims_summary.v1",
            "description": "Unified claim store: fact-ledger facts, thesis inferences/assumptions, verified SSI claims (severity>=3, capped 50/ticker).",
            "claims_jsonl_path": "_system/data/claims.jsonl",
            "by_status": by_status,
            "by_type": by_type,
        },
        feed_id="agent-claims",
        row_count=len(rows),
    )
    write_json_if_changed(OUT_SUMMARY, summary)
    print(f"OK claim store: claims={len(rows)} by_status={by_status} written={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
