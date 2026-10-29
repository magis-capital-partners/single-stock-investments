#!/usr/bin/env python3
"""Load and project special-situations situation rows.

The append-only ledger is ``_system/data/special_situations/situations.jsonl``.
The latest ``version`` for each ``situation_id`` is the current row. A weekly
review appends a new line. It does not edit an earlier one.

``attach_to_book`` copies the latest rows onto the special-situations dashboard
payload so the Ideas view and the other desks can read them without opening
the ledger. Rows this module adds carry ``source_feed: situation_register``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "_system" / "data" / "special_situations" / "situations.jsonl"
DASHBOARD_LANES = (
    "spinoffs",
    "split_offs",
    "mergers",
    "warrants",
    "restructurings",
    "forced_sellers",
    "buyback_events",
)
SOURCE_FEED = "situation_register"
TYPE_LANE = {
    "spinoff_orphan": "spinoffs",
    "cvr_merger_security": "mergers",
    "tender_odd_lot": "split_offs",
    "no_vote_deal": "mergers",
    "topping_bid": "mergers",
    "warrant_terms": "warrants",
    "capital_structure_shock": "restructurings",
    "post_reorg": "restructurings",
    "rights_offering": "warrants",
    "recap_stub": "restructurings",
    "merger": "mergers",
}


def load_lines(path: Path = LEDGER) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_no}: invalid JSON ({exc})") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_no}: row is not an object")
        row["_line"] = line_no
        rows.append(row)
    return rows


def latest_by_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Highest version per situation_id. Equal versions keep the later line."""
    chosen: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("situation_id") or "")
        current = chosen.get(key)
        if current is None or (int(row.get("version") or 0), int(row.get("_line") or 0)) >= (
            int(current.get("version") or 0),
            int(current.get("_line") or 0),
        ):
            chosen[key] = row
    return sorted(chosen.values(), key=lambda row: str(row.get("situation_id")))


def lane_for(row: dict[str, Any]) -> str:
    explicit = row.get("lane")
    if explicit in DASHBOARD_LANES:
        return str(explicit)
    for screen in row.get("screens_hit") or []:
        if screen in DASHBOARD_LANES:
            return str(screen)
    return TYPE_LANE.get(str(row.get("situation_type")), "restructurings")


def book_for(row: dict[str, Any]) -> str:
    if row.get("status") in {"closed", "passed", "wrong"}:
        return "history"
    return "ranked"


def project_dashboard_row(row: dict[str, Any]) -> dict[str, Any]:
    """Shape the Ideas table already reads. Research only. No spread."""
    filing = row.get("primary_filing") or {}
    catalyst = row.get("catalyst") or {}
    one = (row.get("one_number") or {}).get("text") or ""
    tickers = row.get("tickers") or []
    ticker = tickers[0] if tickers else ""
    lane = lane_for(row)
    ends = catalyst.get("date")
    what = catalyst.get("what_ends_it") or ""
    return {
        "id": row.get("situation_id"),
        "lane": lane,
        "lanes": [lane],
        "book": book_for(row),
        "ticker": ticker,
        "company": row.get("company"),
        "what": what,
        "ends": ends,
        "ends_label": ends or "End date not stated",
        "annualized_spread": None,
        "evidence_url": filing.get("url"),
        "evidence_label": f"{filing.get('form') or 'filing'} {filing.get('accession') or ''}".strip(),
        "evidence_kind": "filing",
        "source_feed": SOURCE_FEED,
        "as_of": (row.get("recorded_at") or "")[:10] or None,
        "desk": "special_situations",
        "status": "ended" if book_for(row) == "history" else "open",
        "situation_status": row.get("status"),
        "next": (row.get("pass_if") or {}).get("text"),
        "one_number": one,
        "inbox": book_for(row) == "ranked",
        "situation_id": row.get("situation_id"),
        "situation_type": row.get("situation_type"),
        "field_tags": row.get("field_tags"),
        "drew_verdict": row.get("drew_verdict"),
        "outcome": row.get("outcome"),
        "cross_desk_tags": row.get("cross_desk_tags") or [],
        "research_only": True,
        "in_base_irr": False,
        "authority": "none",
    }


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    """Ledger row without the loader's line number."""
    return {key: value for key, value in row.items() if key != "_line"}


def attach_to_book(payload: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Replace any prior register projection and add the latest rows.

    Closed, passed, and wrong rows go to history. Open rows stay ranked and
    set ``inbox`` so the Ideas inbox lists them. ``situation_rows`` is the
    full latest ledger record for desks that need the tags and the accession.
    """
    latest = latest_by_id(rows if rows is not None else load_lines())
    projected = [project_dashboard_row(row) for row in latest]
    for key, book in (("rows", "ranked"), ("discovery", "discovery"), ("history", "history")):
        kept = [item for item in payload.get(key) or [] if item.get("source_feed") != SOURCE_FEED]
        kept.extend(item for item in projected if item["book"] == book)
        payload[key] = kept
        counts = payload.setdefault("counts", {}).setdefault(book, {})
        if isinstance(counts, dict):
            for lane in DASHBOARD_LANES:
                counts[lane] = sum(
                    1
                    for item in kept
                    if lane in (item.get("lanes") or [item.get("lane")])
                )
    payload["situation_rows"] = [public_row(row) for row in latest]
    return payload
