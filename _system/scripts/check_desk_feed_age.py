#!/usr/bin/env python3
"""Flag desk feeds whose build stamp or newest row is more than N business days old.

The Special Situations desk reads portfolio news, warrants, the activist feed,
the document catalog, the special-situations book, and separations. Activism
can call the same check for ``activist_feed`` instead of keeping a second copy.
There was no open pull request for that check when this landed (Activism cloud
agent bc-9a567f44 had not pushed a branch).

A feed is stale when the business-day gap from its stamp to ``--as-of`` is
greater than ``--max-business-days`` (default 2). The stamp is
``_envelope.generated_at`` when the file has one, otherwise ``generated_at``,
``build_time``, or ``generated``. The newest row date is checked the same way
when the feed has a row list. NYSE sessions, including full-day holidays, come
from ``build_capitulation_daily.is_nyse_session``.

Warrant rows and events with a missing, null, or blank ``terms_status`` are
flagged on their own. ``unparsed`` is a status, not a missing one.

    python _system/scripts/check_desk_feed_age.py --desk special_situations
    python _system/scripts/check_desk_feed_age.py --feed activist_feed
    python _system/scripts/check_desk_feed_age.py --desk special_situations --warn-only

Exit 1 when any feed is flagged. ``--warn-only`` prints the same lines and
exits 0, for the nightly rebuild, which does not own these artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_capitulation_daily import is_nyse_session  # noqa: E402

FILE_STAMP_FIELDS = ("generated_at", "build_time", "generated")


@dataclass(frozen=True)
class FeedSpec:
    feed_id: str
    path: str
    row_lists: tuple[tuple[str, str], ...] = ()
    fallback_path: str | None = None
    check_terms_status: bool = False
    terms_lists: tuple[str, ...] = field(default_factory=tuple)


FEEDS: dict[str, FeedSpec] = {
    "portfolio_news": FeedSpec(
        "portfolio_news",
        "dashboard/data/portfolio_news.json",
        row_lists=(("items", "published_utc"),),
    ),
    "warrants": FeedSpec(
        "warrants",
        "dashboard/data/warrants.json",
        row_lists=(("events", "filed_at"),),
        check_terms_status=True,
        terms_lists=("rows", "events"),
    ),
    "activist_feed": FeedSpec(
        "activist_feed",
        "dashboard/data/activist_feed.json",
        row_lists=(("feed", "report_date"),),
    ),
    "document_catalog": FeedSpec(
        "document_catalog",
        "dashboard/data/document_catalog.json",
        fallback_path="dashboard/data/document_catalog_summary.json",
    ),
    "special_situations": FeedSpec(
        "special_situations",
        "dashboard/data/special_situations.json",
        row_lists=(("rows", "as_of"),),
    ),
    "separations": FeedSpec(
        "separations",
        "dashboard/data/separations.json",
        row_lists=(("discovery_events", "filed"),),
    ),
}

DESK_FEEDS: dict[str, tuple[str, ...]] = {
    "special_situations": (
        "portfolio_news",
        "warrants",
        "activist_feed",
        "document_catalog",
        "special_situations",
        "separations",
    ),
    # Activism's stale check is this feed. Call --feed activist_feed or --desk activism.
    "activism": ("activist_feed",),
}


def parse_stamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    if len(text) == 10:
        text = text + "T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def business_days_since(stamp: date, today: date) -> int:
    """NYSE sessions after ``stamp`` through ``today``. Same-day is 0."""
    if stamp >= today:
        return 0
    count = 0
    day = stamp
    while day < today:
        day += timedelta(days=1)
        if is_nyse_session(day):
            count += 1
    return count


def _dig(doc: dict, dotted: str) -> object:
    current: object = doc
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def file_stamp(doc: dict) -> tuple[str | None, str | None]:
    """Return (iso stamp, field name). Envelope wins, then the file's own field."""
    envelope = _dig(doc, "_envelope.generated_at")
    if parse_stamp(envelope):
        return str(envelope), "_envelope.generated_at"
    for name in FILE_STAMP_FIELDS:
        value = doc.get(name)
        if parse_stamp(value):
            return str(value), name
    return None, None


def newest_row_stamp(doc: dict, spec: FeedSpec) -> str | None:
    newest: datetime | None = None
    raw: str | None = None
    for list_name, field_name in spec.row_lists:
        rows = doc.get(list_name)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            stamp = parse_stamp(row.get(field_name))
            if stamp is not None and (newest is None or stamp > newest):
                newest = stamp
                raw = str(row.get(field_name))
    return raw


def missing_terms(doc: dict, spec: FeedSpec) -> list[str]:
    if not spec.check_terms_status:
        return []
    missing: list[str] = []
    for list_name in spec.terms_lists:
        rows = doc.get(list_name)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            status = row.get("terms_status") if "terms_status" in row else None
            if "terms_status" not in row or status is None or (isinstance(status, str) and not status.strip()):
                label = row.get("warrant_id") or row.get("event_id") or row.get("issuer") or index
                missing.append(f"{list_name}[{index}] ({label})")
    return missing


def _load(path: Path) -> dict | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) else None


def check_feed(
    spec: FeedSpec,
    *,
    root: Path = ROOT,
    today: date | None = None,
    max_business_days: int = 2,
) -> list[str]:
    today = today or datetime.now(timezone.utc).date()
    flags: list[str] = []
    path = root / spec.path
    doc = _load(path)
    used = spec.path
    if spec.fallback_path and (doc is None or file_stamp(doc)[0] is None):
        flags.append(f"{spec.feed_id}: {spec.path} has no readable stamp; using {spec.fallback_path}")
        used = spec.fallback_path
        fallback = _load(root / spec.fallback_path)
        if fallback is not None:
            doc = fallback
    if doc is None:
        flags.append(f"{spec.feed_id}: {used} is missing or not a JSON object")
        return flags
    stamp, field_name = file_stamp(doc)
    parsed = parse_stamp(stamp)
    if parsed is None:
        flags.append(f"{spec.feed_id}: {used} has no _envelope.generated_at or file stamp")
    else:
        age = business_days_since(parsed.date(), today)
        if age > max_business_days:
            flags.append(
                f"{spec.feed_id}: {field_name} {stamp} is {age} business days before {today.isoformat()} "
                f"(more than {max_business_days})"
            )
    row_stamp = newest_row_stamp(doc, spec)
    row_parsed = parse_stamp(row_stamp)
    if spec.row_lists and row_parsed is None:
        flags.append(f"{spec.feed_id}: {used} has no newest-row date")
    elif row_parsed is not None:
        age = business_days_since(row_parsed.date(), today)
        if age > max_business_days:
            flags.append(
                f"{spec.feed_id}: newest row {row_stamp} is {age} business days before {today.isoformat()} "
                f"(more than {max_business_days})"
            )
    for item in missing_terms(doc, spec):
        flags.append(f"{spec.feed_id}: missing terms_status on {item}")
    return flags


def feeds_for(desk: str | None, feed_ids: list[str] | None) -> list[FeedSpec]:
    ids: list[str] = list(feed_ids or [])
    if desk:
        if desk not in DESK_FEEDS:
            known = ", ".join(sorted(DESK_FEEDS))
            raise SystemExit(f"unknown desk {desk!r} (known: {known})")
        ids.extend(DESK_FEEDS[desk])
    if not ids:
        ids.extend(DESK_FEEDS["special_situations"])
    missing = [item for item in ids if item not in FEEDS]
    if missing:
        raise SystemExit(f"unknown feed(s): {', '.join(missing)}")
    # Preserve order, drop duplicates.
    seen: list[str] = []
    for item in ids:
        if item not in seen:
            seen.append(item)
    return [FEEDS[item] for item in seen]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--desk", choices=sorted(DESK_FEEDS), default=None)
    parser.add_argument("--feed", action="append", default=None, help="Feed id. Repeatable. Activism can pass activist_feed.")
    parser.add_argument("--max-business-days", type=int, default=2)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD. Default is today in UTC.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc).date()
    flags: list[str] = []
    for spec in feeds_for(args.desk, args.feed):
        flags.extend(
            check_feed(spec, root=args.root, today=today, max_business_days=args.max_business_days)
        )
    for flag in flags:
        print(f"FLAG {flag}")
    if not flags:
        print(f"desk feeds are within {args.max_business_days} business days of {today.isoformat()}")
    if flags and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
