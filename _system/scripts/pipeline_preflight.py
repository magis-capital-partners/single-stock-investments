#!/usr/bin/env python3
"""Cheap guard that keeps a late Data Pipeline news run from redoing work.

News runs on a 6-hour cadence, but GitHub's scheduler can start a scheduled
run hours late -- close enough to the next run that both ingest the same
window over every holding (up to 45 minutes each). The committed feed
(`dashboard/data/portfolio_news.json`) records `build_time`, so a run whose
predecessor built the feed less than half a cadence ago has almost nothing
new to find: the ingest deduplicates on `_system/data/news_seen.json`, and
anything published in the gap is caught by the next scheduled run at most
one cadence later.

Fail open in every direction: an unreadable feed, a missing or malformed
`build_time`, or a clock problem all mean "run the ingest". A preflight may
save a duplicate run; it may never silently swallow a scheduled one.

Usage:
  python _system/scripts/pipeline_preflight.py news \
      --feed dashboard/data/portfolio_news.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Half the 6-hour news cadence: fresher than this, a re-run is a duplicate.
MIN_FEED_AGE = timedelta(hours=3)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def feed_built_at(feed_path: Path) -> datetime | None:
    """When the committed news feed was built, or None when unknown."""
    try:
        payload = json.loads(Path(feed_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_time(payload.get("build_time") or payload.get("generated_at"))


def decide_news(built_at: datetime | None, *, now: datetime, min_age: timedelta = MIN_FEED_AGE) -> tuple[bool, str]:
    """(should_run, reason). Anything unknown runs the ingest."""
    if built_at is None:
        return True, "no readable feed build time; running the ingest"
    age = now - built_at
    if age < timedelta(0):
        return True, "feed build time is in the future; running the ingest"
    if age < min_age:
        return False, f"feed built {age} ago (< {min_age}); this run would duplicate the last ingest"
    return True, f"feed built {age} ago; running the ingest"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    news = sub.add_parser("news", help="skip a news ingest that would duplicate the last one")
    news.add_argument("--feed", type=Path, required=True)
    news.add_argument("--min-age-hours", type=float, default=MIN_FEED_AGE.total_seconds() / 3600)
    news.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args(argv)

    should_run, reason = decide_news(
        feed_built_at(args.feed),
        now=datetime.now(timezone.utc),
        min_age=timedelta(hours=args.min_age_hours),
    )
    values = {"changed": "true" if should_run else "false", "reason": reason}
    for key, value in values.items():
        print(f"{key}={value}")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
