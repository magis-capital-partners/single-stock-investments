#!/usr/bin/env python3
"""Record a verified, dividend-aware committee outcome and refresh calibration."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from build_total_return_panel import compute_period_total_return
from build_valuation_workbench import write as write_valuation_workbench
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
    def key(row: dict) -> tuple:
        measurement_key = ("horizon", row.get("horizon_months")) if row.get("horizon_months") else ("date", row.get("measurement_date"))
        return row.get("ticker"), row.get("decision_date"), measurement_key

    record_key = key(record)
    kept = [row for row in rows if key(row) != record_key]
    kept.append(record)
    return sorted(kept, key=lambda row: (row["measurement_date"], row["ticker"], row["decision_date"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--committee-date")
    parser.add_argument("--measurement-date", default=date.today().isoformat())
    parser.add_argument("--horizon-months", type=int, choices=(6, 12, 24))
    parser.add_argument("--error-attribution", action="append", choices=("economic_claim", "cash_flow", "capital_intensity", "comparable", "option_probability", "timing", "leverage", "governance", "other"), default=[])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    committee_path, committee = latest_committee(ticker, args.committee_date)
    human_decision = committee.get("human_decision") or {}
    if human_decision.get("status") != "complete" or not human_decision.get("decision"):
        raise ValueError("committee owner decision must be complete before measuring an outcome")
    decision_date = human_decision.get("decided_at") or (committee.get("review") or {}).get("as_of")
    if not decision_date:
        raise ValueError("committee review.as_of is required")
    outcome = compute_period_total_return(ticker, decision_date, args.measurement_date)
    valuation = json.loads((ROOT / ticker / "research" / "valuation.json").read_text(encoding="utf-8"))
    component = valuation.get("component_valuation_results") or {}
    contract = valuation.get("universal_valuation_contract") or {}
    power_zone = (contract.get("method_route") or valuation.get("valuation_method_route") or {}).get("profile_id")
    expected_ranges = [v.get("expected_return_range_pct") for v in (committee.get("round_two") or {}).get("votes") or [] if isinstance(v.get("expected_return_range_pct"), list)]
    expected_midpoint = None
    if expected_ranges:
        expected_midpoint = round(sum((float(r[0]) + float(r[1])) / 2 for r in expected_ranges) / len(expected_ranges), 2)
    record = {
        **outcome,
        "ticker": ticker,
        "decision_date": decision_date,
        "measurement_date": args.measurement_date,
        "horizon_months": args.horizon_months,
        "committee_ref": str(committee_path.relative_to(ROOT)).replace("\\", "/"),
        "owner_decision": human_decision.get("decision"),
        "owner_sizing": human_decision.get("sizing"),
        "decision_price": (valuation.get("inputs") or {}).get("price"),
        "decision_value_range_per_share": component.get("total_equity_value_per_share"),
        "economic_value_status": (valuation.get("economic_value_analysis") or {}).get("status"),
        "universal_contract_status": contract.get("status"),
        "power_zone": power_zone,
        "expected_return_midpoint_pct": expected_midpoint,
        "forecast_midpoint_error_pct": round(float(outcome["total_return_pct"]) - expected_midpoint, 2) if outcome.get("total_return_pct") is not None and expected_midpoint is not None else None,
        "component_forecast_snapshot": component.get("additive_components") or [],
        "votes": (committee.get("round_two") or {}).get("votes") or [],
        "error_attribution": sorted(set(args.error_attribution)),
    }
    print(json.dumps(record, indent=2))
    if not args.write:
        return 0
    existing = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()] if LEDGER.exists() else []
    rows = upsert(existing, record)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    CALIBRATION.write_text(json.dumps(summarize(rows), indent=2) + "\n", encoding="utf-8")
    write_valuation_workbench(ticker, args.measurement_date)
    print(f"Wrote {LEDGER} and {CALIBRATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
