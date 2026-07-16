#!/usr/bin/env python3
"""Build a repository-wide schedule of IC reviews and due outcome checks."""
from __future__ import annotations

import argparse
import calendar
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def add_months(value: str, months: int) -> str:
    source = date.fromisoformat(value[:10])
    index = source.month - 1 + months
    year, month = source.year + index // 12, index % 12 + 1
    return date(year, month, min(source.day, calendar.monthrange(year, month)[1])).isoformat()


def build(as_of: str) -> dict:
    rows = []
    for path in ROOT.glob("*/research/committee_????-??-??.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        decision = record.get("human_decision") or {}
        if decision.get("status") != "complete":
            continue
        decision_date = str(decision.get("decided_at") or (record.get("review") or {}).get("as_of"))[:10]
        for months in (record.get("monitoring_plan") or {}).get("outcome_horizons_months") or [6, 12, 24]:
            due = add_months(decision_date, int(months))
            rows.append({
                "ticker": record.get("ticker"), "decision_date": decision_date, "horizon_months": months,
                "due_date": due, "status": "due" if due <= as_of else "scheduled",
                "committee_ref": path.relative_to(ROOT).as_posix(),
            })
    return {"schema_version": "1.0", "as_of": as_of, "items": sorted(rows, key=lambda row: (row["due_date"], row["ticker"]))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--out", type=Path, default=ROOT / "_system" / "research" / "committee_monitoring.json")
    args = parser.parse_args()
    payload = build(args.date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
