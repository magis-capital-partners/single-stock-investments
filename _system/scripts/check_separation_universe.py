#!/usr/bin/env python3
"""Structural and health checks for the separations register and dashboard feed.

Exit non-zero on structural errors; with --strict also on an unhealthy feed.
With --warn-only always exit zero (the nightly intake lane; the Monday
discovery lane runs strict).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from separation_common import (  # noqa: E402
    AMENDMENTS_PATH,
    DASHBOARD_PATH,
    DISCOVERY_STATE_PATH,
    EVENTS_PATH,
    EVENT_STATUSES,
    FLOWS_PATH,
    REGISTRY_PATH,
    SIDES,
    gate_state,
    latest_registry,
    load_jsonl,
    parse_date,
    read_json,
    validate_registry,
)

UNHEALTHY_FAILURE_STREAK = 3
STALE_FEED_HOURS = 100


def structural_errors() -> list[str]:
    errors = validate_registry()
    for index, row in enumerate(load_jsonl(EVENTS_PATH)):
        if row.get("status") not in EVENT_STATUSES:
            errors.append(f"events[{index}]: status must be one of {sorted(EVENT_STATUSES)}")
        if not row.get("accession") and not row.get("url"):
            errors.append(f"events[{index}]: accession or url required")
    ids = {r["separation_id"] for r in latest_registry()}
    for index, row in enumerate(load_jsonl(FLOWS_PATH)):
        if row.get("side") not in SIDES:
            errors.append(f"flows[{index}]: side must be parent or spinco")
        if row.get("separation_id") not in ids:
            errors.append(f"flows[{index}]: unknown separation_id {row.get('separation_id')}")
        if row.get("authority") != "none" or row.get("in_base_irr") is not False:
            errors.append(f"flows[{index}]: flow rows must carry authority none and in_base_irr false")
        for leg in row.get("legs") or []:
            if leg.get("confidence") == "n_a" and leg.get("shares_base") is not None:
                errors.append(f"flows[{index}]: n_a leg {leg.get('leg')} carries a share count")
    # A ranked row in the register must pass gates, and gates must agree with lifecycle.
    for row in latest_registry():
        gates = gate_state(row)
        if row.get("lifecycle") == "active" and not gates["identity"]["pass"]:
            errors.append(f"{row['separation_id']}: active but identity gate fails ({gates['identity']['missing']})")
    return errors


def health(today: date | None = None) -> dict:
    today = today or date.today()
    state = read_json(DISCOVERY_STATE_PATH, {}) or {}
    streak = int(state.get("consecutive_failures") or 0)
    problems: list[str] = []
    status = "healthy"
    if streak >= UNHEALTHY_FAILURE_STREAK:
        status = "unhealthy"
        problems.append(f"EDGAR discovery failed {streak} runs in a row")
    feed = read_json(DASHBOARD_PATH, {}) or {}
    stamp = feed.get("generated_at")
    if stamp:
        try:
            generated = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - generated).total_seconds() / 3600.0
            if age_h > STALE_FEED_HOURS:
                problems.append(f"separations.json is {age_h:.0f}h old")
                status = "unhealthy" if status == "healthy" else status
        except ValueError:
            problems.append("separations.json generated_at unparseable")
            status = "unhealthy"
    # Open offers past expiration with no final count for more than 10 days: stale terms.
    stale_terms = []
    for row in latest_registry():
        if row.get("kind") != "split_off" or row.get("lifecycle") != "active":
            continue
        exp = parse_date((row.get("dates") or {}).get("expiration"))
        exchange = (row.get("terms") or {}).get("exchange") or {}
        if exp and (today - exp).days > 10 and exchange.get("parent_shares_accepted") is None:
            stale_terms.append(row["separation_id"])
    if stale_terms:
        problems.append("expired offers without filed final results: " + ", ".join(stale_terms))
    return {
        "status": status,
        "structural_errors": structural_errors(),
        "problems": problems,
        "stale_terms": stale_terms,
        "discovery_consecutive_failures": streak,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail on an unhealthy feed as well")
    parser.add_argument("--warn-only", action="store_true", help="never fail")
    args = parser.parse_args()
    report = health()
    for err in report["structural_errors"]:
        print(f"ERROR {err}")
    for problem in report["problems"]:
        print(f"WARN  {problem}")
    print(
        f"separations: status={report['status']} structural_errors={len(report['structural_errors'])} "
        f"registry={len(latest_registry())} amendments={len(load_jsonl(AMENDMENTS_PATH))} "
        f"registry_path={REGISTRY_PATH.relative_to(REGISTRY_PATH.parents[3])}"
    )
    if args.warn_only:
        return 0
    if report["structural_errors"]:
        return 1
    if args.strict and report["status"] != "healthy":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
