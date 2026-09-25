#!/usr/bin/env python3
"""Fail loudly when the activist feed stops moving.

Between 2026-08-02 and 2026-08-26 the activist scan did not commit once. Every
scheduled run was *cancelled* while pending in a shared concurrency group, which
GitHub reports as "cancelled", not "failed", so no red X appeared anywhere and
the lane receipt kept recording the pipeline's other jobs as successful.

Per-job receipts would not have caught it either: a job that runs and collects
nothing looks identical to one that never ran. Asserting on the artifact's own
age catches eviction, a silent crash, an upstream outage and a no-op run with a
single check, and it cannot be satisfied by a job that merely started.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEED_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"
DISCOVERY_PATH = ROOT / "_system" / "data" / "activist_filer_discovery.json"
# Written by scan_activist_sources.py --phase ...: which holdings the rotating
# SEC phase has reached, and when. A feed that is rebuilt every day can still
# be built from a scan that never gets through the book; this is that check.
STATE_PATH = ROOT / "_system" / "data" / "activist_scan_state.json"
DEFAULT_MAX_SCAN_AGE_DAYS = 7

# Weekday scan, so a Friday run is still fresh on Monday. Three days tolerates a
# weekend plus one bad day before it complains.
DEFAULT_MAX_AGE_DAYS = 3
# A scan that runs but returns nothing is the failure mode a "did it run?" check
# cannot see, so assert on content too.
DEFAULT_MIN_ROWS = 100


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None


def scan_coverage_problems(
    state: dict,
    tickers: list[str],
    *,
    now: datetime,
    max_scan_age_days: int = DEFAULT_MAX_SCAN_AGE_DAYS,
) -> list[str]:
    """Holdings the rotating SEC phase has not reached within the window.

    Quiet until the state itself is older than the window, so the first
    rotation after the phases ship is not reported as a failure.
    """
    if not state or not tickers:
        return []
    created = _parse_iso(state.get("created_at"))
    window = timedelta(days=max_scan_age_days)
    if created is None or now - created < window:
        return []
    last = (state.get("sec") or {}).get("last_scanned") or {}
    stale = []
    for ticker in tickers:
        stamp = _parse_iso(last.get(ticker))
        if stamp is None or now - stamp > window:
            stale.append(ticker)
    if not stale:
        return []
    return [
        f"{len(stale)} of {len(tickers)} holdings have had no SEC activist scan in "
        f"{max_scan_age_days} days (e.g. {', '.join(stale[:5])}) -- the rotating SEC "
        "phase is not getting through the book; raise its --budget-min"
    ]


def check(
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    min_rows: int = DEFAULT_MIN_ROWS,
    now: datetime | None = None,
    feed_path: Path | None = None,
    state_path: Path | None = None,
    tickers: list[str] | None = None,
    max_scan_age_days: int = DEFAULT_MAX_SCAN_AGE_DAYS,
) -> tuple[bool, list[str]]:
    now = now or datetime.now(timezone.utc)
    path = feed_path or FEED_PATH
    problems: list[str] = []
    if state_path is not None and state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        problems.extend(
            scan_coverage_problems(
                state if isinstance(state, dict) else {},
                tickers or [],
                now=now,
                max_scan_age_days=max_scan_age_days,
            )
        )

    if not path.is_file():
        return False, [f"{path.name} does not exist -- the activist feed has never been built"]

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"{path.name} is not valid JSON: {exc}"]

    generated = _parse_iso(doc.get("generated_at"))
    if generated is None:
        problems.append(f"{path.name} has no parseable generated_at")
    else:
        age = now - generated
        if age > timedelta(days=max_age_days):
            problems.append(
                f"activist feed is {age.days} days old "
                f"(generated {doc.get('generated_at')}, limit {max_age_days}d). "
                "Check whether the 06:00 UTC data-pipeline activist job ran, "
                "and whether it was cancelled rather than failed."
            )

    rows = doc.get("feed") or []
    if len(rows) < min_rows:
        problems.append(
            f"activist feed has {len(rows)} rows, below the floor of {min_rows} -- "
            "a scan that runs and collects nothing looks healthy by every other measure"
        )

    summary = doc.get("summary") or {}
    if summary.get("activist_row_count") == 0 and rows:
        problems.append(
            "no row in the feed is attributed to a registry activist -- "
            "filer attribution or the firm registry has broken"
        )

    return (not problems), problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--min-rows", type=int, default=DEFAULT_MIN_ROWS)
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Report problems without a non-zero exit (for the first days after a rebuild)",
    )
    parser.add_argument("--max-scan-age-days", type=int, default=DEFAULT_MAX_SCAN_AGE_DAYS)
    args = parser.parse_args()

    from activist_common import portfolio_tickers

    ok, problems = check(
        max_age_days=args.max_age_days,
        min_rows=args.min_rows,
        state_path=STATE_PATH,
        tickers=portfolio_tickers(),
        max_scan_age_days=args.max_scan_age_days,
    )
    if ok:
        print("OK: activist feed is fresh and populated")
        return 0
    for problem in problems:
        # GitHub renders this as an annotation on the run.
        print(f"::error::{problem}" if not args.warn_only else f"::warning::{problem}")
    print(f"activist freshness check found {len(problems)} problem(s)", file=sys.stderr)
    return 0 if args.warn_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
