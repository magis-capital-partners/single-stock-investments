#!/usr/bin/env python3
"""Row-age check for a dashboard feed.

Reusable on purpose. The activism desk calls it for
``dashboard/data/activist_feed.json``. The special-situations desk is building
the same idea (newest row more than a few business days behind the build
clock) on ``grok/special-situations/2026-10-29-situation-rows``. Keep this
function small so the two can become one later: pass a feed path and a maximum
business-day age.

Business days are Monday through Friday. This does not apply a holiday calendar.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def business_days_between(earlier: date, later: date) -> int:
    """Weekdays after ``earlier`` through ``later``. The same day is zero."""
    if later <= earlier:
        return 0
    count = 0
    cursor = earlier
    step = timedelta(days=1)
    while cursor < later:
        cursor += step
        if cursor.weekday() < 5:
            count += 1
    return count


def _newest_row_date(rows: Any, date_key: str) -> date | None:
    if not isinstance(rows, list):
        return None
    found: list[date] = []
    for row in rows:
        if isinstance(row, dict):
            parsed = parse_iso_date(row.get(date_key))
            if parsed is not None:
                found.append(parsed)
    return max(found) if found else None


def check_feed_row_staleness(
    feed_path: str | Path,
    max_business_days: int,
    *,
    today: date | None = None,
    rows_key: str = "feed",
    date_key: str = "report_date",
) -> dict[str, Any]:
    """Warn when the newest row is more than ``max_business_days`` behind.

    The build clock is ``_envelope.generated_at`` when that field is present,
    otherwise the top-level ``generated_at``. The row is also compared with
    ``today``. Health is ``stale`` when either gap is over the limit.
    """
    path = Path(feed_path)
    today = today or date.today()
    result: dict[str, Any] = {
        "health": "unknown",
        "warnings": [],
        "feed_path": str(path),
        "newest_row_date": None,
        "generated_at": None,
        "envelope_generated_at": None,
        "clock_date": None,
        "business_days_vs_clock": None,
        "business_days_vs_today": None,
        "max_business_days": max_business_days,
    }
    if max_business_days < 0:
        raise ValueError("max_business_days must be >= 0")
    if not path.is_file():
        result["warnings"].append(f"{path.name} does not exist")
        return result
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result["warnings"].append(f"{path.name} is not valid JSON: {exc}")
        return result
    if not isinstance(document, dict):
        result["warnings"].append(f"{path.name} is not a JSON object")
        return result

    envelope = document.get("_envelope") if isinstance(document.get("_envelope"), dict) else {}
    envelope_generated = envelope.get("generated_at")
    top_generated = document.get("generated_at")
    result["generated_at"] = top_generated
    result["envelope_generated_at"] = envelope_generated
    clock_raw = envelope_generated or top_generated
    clock = parse_iso_date(clock_raw)
    result["clock_date"] = clock.isoformat() if clock else None
    if clock is None:
        result["warnings"].append(f"{path.name} has no parseable _envelope.generated_at or generated_at")

    newest = _newest_row_date(document.get(rows_key), date_key)
    result["newest_row_date"] = newest.isoformat() if newest else None
    if newest is None:
        result["warnings"].append(f"{path.name} has no parseable {date_key} on {rows_key}")
        return result

    warnings: list[str] = list(result["warnings"])
    stale = False
    if clock is not None:
        behind_clock = business_days_between(newest, clock)
        result["business_days_vs_clock"] = behind_clock
        if behind_clock > max_business_days:
            stale = True
            warnings.append(
                f"newest row {newest.isoformat()} is {behind_clock} business days older than "
                f"build clock {clock.isoformat()} (limit {max_business_days})"
            )
    behind_today = business_days_between(newest, today)
    result["business_days_vs_today"] = behind_today
    if behind_today > max_business_days:
        stale = True
        warnings.append(
            f"newest row {newest.isoformat()} is {behind_today} business days older than "
            f"today {today.isoformat()} (limit {max_business_days})"
        )
    result["warnings"] = warnings
    result["health"] = "stale" if stale else "healthy"
    return result
