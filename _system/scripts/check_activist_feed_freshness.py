#!/usr/bin/env python3
"""Warn when the activist feed's newest row is more than two business days old.

Uses ``feed_row_staleness.check_feed_row_staleness``. That function takes a
feed path and a maximum business-day age so another desk can call it on its
own file. This script only points it at ``dashboard/data/activist_feed.json``.

It reports health. It does not rewrite the feed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from feed_row_staleness import check_feed_row_staleness  # noqa: E402

FEED_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"
MAX_BUSINESS_DAYS = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--feed", type=Path, default=FEED_PATH)
    parser.add_argument("--max-business-days", type=int, default=MAX_BUSINESS_DAYS)
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print warnings and still exit 0",
    )
    args = parser.parse_args(argv)
    result = check_feed_row_staleness(args.feed, args.max_business_days)
    for warning in result["warnings"]:
        print(f"::warning::{warning}")
    print(
        json.dumps(
            {
                "health": result["health"],
                "newest_row_date": result["newest_row_date"],
                "clock_date": result["clock_date"],
                "business_days_vs_clock": result["business_days_vs_clock"],
                "business_days_vs_today": result["business_days_vs_today"],
                "max_business_days": result["max_business_days"],
            },
            indent=2,
        )
    )
    if result["health"] == "healthy" or args.warn_only:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
