#!/usr/bin/env python3
"""Shared helpers for short_reports/*.md activist entries."""
from __future__ import annotations

from pathlib import Path

from activist_common import ROOT, firm_name
from activist_date_parse import normalize_partial_date

CHANGE_ACTIONS = {
    "new": "new",
    "added": "add",
    "add": "add",
    "increased": "add",
    "buy": "add",
    "trimmed": "trim",
    "trim": "trim",
    "reduced": "trim",
    "sold": "exit",
    "exit": "exit",
    "closed": "exit",
    "hold": "hold",
    "unchanged": "hold",
    "short": "short",
}


def short_md_report_entry(md: Path, *, ticker: str | None = None) -> dict:
    """Build an activist index report dict from a short_reports markdown file."""
    rel = str(md.relative_to(ROOT)).replace("\\", "/")
    firm_id = md.stem.split("_")[0] if "_" in md.stem else md.stem
    raw_date = md.stem.split("_")[-1] if "_" in md.stem else ""
    iso, precision, source = normalize_partial_date(raw_date)
    return {
        "firm_id": firm_id,
        "firm_name": firm_name(firm_id),
        "side": "short",
        "report_date": iso or raw_date or None,
        "date_precision": precision if iso else "unknown",
        "date_source": source or "filename",
        "title": md.stem.replace("_", " "),
        "source": "short_reports_md",
        "local_file": rel,
        "status": "cached",
        "tier": "context",
        "include_in_feed": True,
        "filing_class": "short_markdown",
        "ticker_hint": ticker,
    }


def collect_short_markdown_reports(ticker: str) -> list[dict]:
    sr_dir = ROOT / ticker / "third-party-analyses" / "short_reports"
    if not sr_dir.is_dir():
        return []
    out: list[dict] = []
    for md in sorted(sr_dir.glob("*.md")):
        entry = short_md_report_entry(md, ticker=ticker)
        out.append({"ticker": ticker, **entry})
    return out
