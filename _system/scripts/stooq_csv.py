"""Validate Stooq CSV responses before anything parses or stores them.

Stooq answers scripted requests with HTML and HTTP 200: a JavaScript
proof-of-work bot check on /q/d/l/ (``fetch("/__verify" ...)``), a "page does
not exist" page on /q/l/, and earlier a plain-text "Get your apikey" notice.
None of those raise, so a caller that only checks the status code writes the
page to disk or parses zero rows and calls it "no data". Every Stooq fetch goes
through ``check_stooq_csv`` so the failure is named at the boundary.
"""
from __future__ import annotations

# /q/d/l/ daily history: Date,Open,High,Low,Close,Volume
DAILY_HEADER = ("Date", "Open", "High", "Low", "Close")
# /q/l/?f=sd2t2ohlcv&h quote: Symbol,Date,Time,Open,High,Low,Close,Volume
QUOTE_HEADER = ("Symbol", "Date", "Time", "Open", "High", "Low", "Close")


class StooqNotCsvError(ValueError):
    """Stooq returned something other than the expected CSV."""


def _describe(text: str) -> str:
    lowered = text.lower()
    if "__verify" in lowered or "requires javascript to verify" in lowered:
        return "Stooq bot-check page (JavaScript proof-of-work), not CSV"
    if "apikey" in lowered:
        return "Stooq 'Get your apikey' page, not CSV"
    if lowered.lstrip().startswith("<"):
        return "Stooq returned HTML, not CSV"
    head = text.strip().splitlines()[0][:60] if text.strip() else ""
    return f"Stooq returned non-CSV body (first line: {head!r})"


def check_stooq_csv(raw: bytes | str, header: tuple[str, ...] = DAILY_HEADER) -> str:
    """Return the decoded body if it starts with ``header``; raise otherwise."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = text.lstrip("﻿")
    first = text.lstrip().split("\n", 1)[0].strip()
    columns = tuple(col.strip() for col in first.split(","))
    if columns[: len(header)] != header:
        raise StooqNotCsvError(_describe(text))
    return text
