#!/usr/bin/env python3
"""Retire warrant series whose contractual expiry has passed.

The registry is append-only and versioned: a series changes lifecycle only by
appending a superseding version. Nothing did that when a series simply ran out
of time, so an expired series stayed ``active`` forever and
``validate_registry`` reported "active security is past contractual expiry".
BKSY.W expired on 2026-09-09; from 2026-09-10 that one registry row failed the
warrant lane, intake-full, drive, world-model, technicals and the dashboard
deploy for thirteen days, until a human appended exactly the amendment this
script writes (version 3, recorded 2026-09-23T01:44:10Z).

An extension is recorded the same way, as a superseding version carrying the
new expiry. Only the latest version is read here, so a recorded extension is
honoured automatically; a series is retired only when its LATEST terms have
expired. The sweeper is the warrant lane's single writer of these amendments:
run it only from the warrant-discover job, never from a shared rebuild, so two
lanes can never append the same version number.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import warrant_common  # noqa: E402

SWEEPER = "sweep_warrant_expiry"
SWEEPABLE_LIFECYCLES = {"active", "candidate"}


def _as_of(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def expired_series(rows: list[dict], as_of: date) -> list[dict]:
    """Latest versions still marked live whose contractual expiry is past."""
    due = []
    for row in warrant_common.latest_registry(rows):
        if row.get("lifecycle") not in SWEEPABLE_LIFECYCLES:
            continue
        expiry = warrant_common.parse_date((row.get("terms") or {}).get("expiry"))
        if expiry is not None and expiry < as_of:
            due.append(row)
    return due


def expiry_amendment(row: dict, recorded_at: str) -> dict:
    """The superseding version: same contract, lifecycle ``expired``."""
    version = int(row.get("version") or 0)
    expiry = (row.get("terms") or {}).get("expiry")
    amendment = dict(row)
    amendment.update(
        {
            "version": version + 1,
            "recorded_at": recorded_at,
            "supersedes_version": version,
            "correction_reason": (
                f"Contractual expiry {expiry} in the recorded terms has passed. "
                "No extension is in the registry, so the series is no longer active."
            ),
            "lifecycle": "expired",
            "amended_by": SWEEPER,
            "next_action": "Retain for history. Do not treat the delayed mark as a live warrant.",
        }
    )
    return amendment


def sweep(*, as_of: date | None = None, dry_run: bool = False,
          registry_path: Path | None = None,
          amendments_path: Path | None = None) -> list[dict]:
    registry_path = registry_path or warrant_common.REGISTRY_PATH
    amendments_path = amendments_path or warrant_common.REGISTRY_AMENDMENTS_PATH
    rows = warrant_common.load_jsonl(registry_path) + warrant_common.load_jsonl(amendments_path)
    recorded_at = warrant_common.utc_now()
    amendments = [
        expiry_amendment(row, recorded_at)
        for row in expired_series(rows, as_of or date.today())
    ]
    if amendments and not dry_run:
        warrant_common.append_jsonl(amendments_path, amendments)
    return amendments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report without appending")
    parser.add_argument("--as-of", default=None, help="Evaluation date (YYYY-MM-DD); default today")
    args = parser.parse_args(argv)
    amendments = sweep(as_of=_as_of(args.as_of), dry_run=args.dry_run)
    verb = "would retire" if args.dry_run else "retired"
    for row in amendments:
        print(
            f"warrant expiry sweep: {verb} {row.get('warrant_ticker')} "
            f"(expiry {(row.get('terms') or {}).get('expiry')}; v{row['supersedes_version']} -> v{row['version']})"
        )
    print(f"warrant expiry sweep: {len(amendments)} series {verb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
