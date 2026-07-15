#!/usr/bin/env python3
"""Record a verified, dividend-aware committee outcome and refresh calibration."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from build_total_return_panel import compute_period_total_return
from committee_calibration import summarize

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "_system" / "research" / "committee_outcomes.jsonl"
CALIBRATION = ROOT / "_system" / "research" / "committee_calibration.json"


def latest_committee(ticker: str, committee_date: str | None = None) -> tuple[Path, dict]:
    research = ROOT / ticker / "research"
    paths = [research / f"committee_{committee_date}.json"] if committee_date else sorted(research.glob("committee_????-??-??.json"))
    paths = [path for path in paths if path.exists()]
    if not paths:
        raise FileNotFoundError(f"{ticker}: no committee record")
    path = paths[-1]
    return path, json.loads(path.read_text(encoding="utf-8"))


def upsert(rows: list[dict], record: dict) -> list[dict]:
    key = (record["ticker"], record["decision_date"], record["measurement_date"])
    kept = [row for row in rows if (row.get("ticker"), row.get("decision_date"), row.get("measurement_date")) != key]
    kept.append(record)
    return sorted(kept, key=lambda row: (row["measurement_date"], row["ticker"], row["decision_date"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--committee-date")
    parser.add_argument("--measurement-date", default=date.today().isoformat())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    committee_path, committee = latest_committee(ticker, args.committee_date)
    decision_date = (committee.get("review") or {}).get("as_of")
    if not decision_date:
        raise ValueError("committee review.as_of is required")
    outcome = compute_period_total_return(ticker, decision_date, args.measurement_date)
    valuation = json.loads((ROOT / ticker / "research" / "valuation.json").read_text(encoding="utf-8"))
    component = valuation.get("component_valuation_results") or {}
    record = {
        **outcome,
        "ticker": ticker,
        "decision_date": decision_date,
        "measurement_date": args.measurement_date,
        "committee_ref": str(committee_path.relative_to(ROOT)).replace("\\", "/"),
        "decision_price": (valuation.get("inputs") or {}).get("price"),
        "decision_value_range_per_share": component.get("total_equity_value_per_share"),
        "economic_value_status": (valuation.get("economic_value_analysis") or {}).get("status"),
        "votes": (committee.get("round_two") or {}).get("votes") or [],
        "error_attribution": [],
    }
    print(json.dumps(record, indent=2))
    if not args.write:
        return 0
    existing = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()] if LEDGER.exists() else []
    rows = upsert(existing, record)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    CALIBRATION.write_text(json.dumps(summarize(rows), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {LEDGER} and {CALIBRATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
