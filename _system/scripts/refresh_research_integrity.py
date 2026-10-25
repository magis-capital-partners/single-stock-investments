#!/usr/bin/env python3
"""Repair published research projections without rebuilding a stale source vault.

Only classifications covered by source-scoped adjudications/review records are
touched. Non-letter feeds, source dates, quotes, valuations and model authority
are preserved. Running twice produces the same bytes.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from atomic_io import write_text_if_changed
from research_integrity import (ROOT, correction_rules, matches_source,
    reconcile_letter, reconcile_positions, review_candidates, source_key, classification_audit)


def reconcile_rows(ticker: str, rows: list[dict], *, letters_only=False) -> list[dict]:
    return [fixed for row in rows if (fixed := row if letters_only and row.get("source") != "superinvestor_letter"
        else reconcile_letter(ticker, row)) is not None]


def reconcile_index(row: dict) -> dict:
    """Repair the letter index's compact action lists with exact source scope."""
    row = dict(row)
    candidates = [(r["ticker"], r) for r in correction_rules()
        if r["fund_id"] == row.get("fund_id") and r["quarter"] == row.get("quarter") and matches_source(r, row)]
    for candidate in review_candidates():
        if candidate["fund_id"] == row.get("fund_id") and candidate["quarter"] == row.get("quarter") and (
                source_key(candidate["source_ref"]) in {source_key(row.get(k)) for k in ("source_file", "source_document", "evidence_ref")}):
            candidates.append((candidate["ticker"], {"disposition": "review", "action": "unverified"}))
    for ticker, rule in candidates:
        for field in ("adds", "trims", "exits", "shorts"):
            if field in row:
                row[field] = [t for t in row[field] if t != ticker]
        if rule["disposition"] == "suppress":
            for field in ("tickers", "our_overlap", "our_tickers"):
                if field in row: row[field] = [t for t in row[field] if t != ticker]
        else:
            field = {"add": "adds", "new": "adds", "trim": "trims", "sell": "trims", "exit": "exits", "short": "shorts"}.get(rule["action"])
            if field in row and ticker not in row[field]: row[field] = [*row[field], ticker]
    if "our_ticker_count" in row:
        row["our_ticker_count"] = len(row.get("our_tickers") or [])
    return row


def reconcile_insight_payload(doc: dict) -> dict:
    """Works on monoliths and section shards; never discards unrelated feeds."""
    for field in ("ticker_discussants", "by_ticker", "events_by_ticker"):
        for ticker, rows in (doc.get(field) or {}).items():
            doc[field][ticker] = reconcile_rows(ticker, rows, letters_only=field != "ticker_discussants")
    if "events" in doc:
        doc["events"] = [fixed for row in doc["events"] if (fixed := reconcile_letter(
            row.get("ticker") or row.get("ref") or "", row) if row.get("source") == "superinvestor_letter" else row) is not None]
    if "letter_index" in doc:
        doc["letter_index"] = [reconcile_index(row) for row in doc["letter_index"]]
    if "fund_registry" in doc:
        doc["fund_registry"] = [reconcile_index(row) for row in doc["fund_registry"]]
    for fund_id, profile in (doc.get("fund_profiles") or {}).items():
        old_tickers = {p.get("ticker") for letter in profile.get("letters") or [] for p in letter.get("positions") or []}
        for i, letter in enumerate(profile.get("letters") or []):
            fixed = reconcile_positions({"fund_id": fund_id, **letter})
            fixed.pop("fund_id", None)
            profile["letters"][i] = fixed
        new_tickers = {p.get("ticker") for letter in profile.get("letters") or [] for p in letter.get("positions") or []}
        # Only remove issuers demonstrably removed from these same letters;
        # a truncated profile is not authority to rebuild its whole universe.
        profile["our_tickers"] = [t for t in profile.get("our_tickers") or [] if t not in old_tickers - new_tickers]
    consensus = doc.get("consensus") or {}
    changed = set()
    for ticker, rows in (consensus.get("by_ticker") or {}).items():
        fixed_rows = []
        for row in rows:
            fixed = reconcile_letter(ticker, row)
            if fixed is None or fixed.get("action") != row.get("action"):
                changed.add((ticker, row.get("quarter")))
            if fixed is not None: fixed_rows.append(fixed)
        consensus["by_ticker"][ticker] = fixed_rows
    # Published consensus retains only 8 source rows per issuer; rebuilding
    # full-history vote counts from that truncated projection would fabricate
    # aggregates. Withhold affected rankings until a full-source rebuild, and
    # keep the original rows explicitly archived here for audit.
    affected = {t for t, _q in changed}
    if changed:
        archive = consensus.setdefault("classification_withheld_aggregates", [])
        for quarter, section in (consensus.get("by_quarter") or {}).items():
            for field in ("most_discussed", "biggest_changes", "activity", "qoq_shifts"):
                kept = []
                for row in section.get(field) or []:
                    if row.get("ticker") in affected and (quarter == "all" or (row["ticker"], quarter) in changed or field == "qoq_shifts"):
                        archive.append({"quarter": quarter, "section": field, "status": "withheld_pending_full_source_rebuild", "original": row})
                    else: kept.append(row)
                if field in section: section[field] = kept
        for quarter, section in (consensus.get("qoq_by_quarter") or {}).items():
            section["shifts"] = [r for r in section.get("shifts") or [] if r.get("ticker") not in affected]
        consensus["classification_integrity"] = {"status": "affected_aggregates_withheld", "as_of": "2026-10-24",
            "reason": "Corrected source actions; truncated published source rows cannot reconstruct full historical vote counts.",
            "affected_tickers": sorted(set((consensus.get("classification_integrity") or {}).get("affected_tickers") or []) | affected)}
    return doc


def reconcile_ticker(row: dict) -> dict:
    from build_dashboard_data import build_essential_insights
    ticker = row["ticker"]
    audit = classification_audit(ticker)
    row["classification_audit"] = audit
    changed = any(r.get("classification_review") for field in ("letter_discussants", "insights", "insight_events") for r in row.get(field) or [])
    for field in ("letter_discussants", "insights", "insight_events"):
        if field not in row: continue
        fixed = reconcile_rows(ticker, row[field] or [], letters_only=field != "letter_discussants")
        changed = changed or fixed != row[field]
        row[field] = fixed
    if changed:
        old = row.get("essential_insights") or {}
        essential = build_essential_insights(ticker, row.get("insight_events") or [], row.get("insights") or [], row.get("letter_discussants") or [])
        # Coverage annotations are maintained by separate research processes.
        for key in ("needs_work", "needs_work_reasons", "coverage_gaps", "insider_materiality", "insider_tier", "insider_ics"):
            if key in old: essential[key] = old[key]
        row["essential_insights"] = essential
    return row


def refresh(data_dir: Path, *, check=False) -> dict:
    from build_dashboard_shards import _slim_essential_insights
    changes = Counter()
    core_path = data_dir / "core.json"
    core = json.loads(core_path.read_text(encoding="utf-8"))
    core_rows = {row["ticker"]: row for row in core["tickers"]}

    def save(path, before, after, kind):
        if before != after:
            changes[kind] += 1
            if not check:
                write_text_if_changed(path, json.dumps(after, ensure_ascii=False, separators=(",", ":")))

    for path in sorted((data_dir / "tickers").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        before = json.loads(text)
        after = reconcile_ticker(json.loads(text))
        if before != after and after["ticker"] in core_rows:
            core_rows[after["ticker"]]["essential_insights"] = _slim_essential_insights(after["essential_insights"])
        save(path, before, after, "ticker_shards")
    save(core_path, json.loads(core_path.read_text(encoding="utf-8")), core, "core")
    for path in sorted((data_dir / "insights").glob("*.json")):
        if path.name == "manifest.json": continue
        text = path.read_text(encoding="utf-8")
        save(path, json.loads(text), reconcile_insight_payload(json.loads(text)), "insight_shards")
    return dict(changes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changes = refresh(ROOT / "dashboard/data", check=args.check)
    print(json.dumps({"pending_changes" if args.check else "updated": changes}, sort_keys=True))
    return int(args.check and bool(changes))


if __name__ == "__main__":
    raise SystemExit(main())
