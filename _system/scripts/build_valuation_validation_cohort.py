#!/usr/bin/env python3
"""Run truthful cross-power-zone readiness and regression validation."""
from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path

from marvin_valuation import compute_valuation
from universal_valuation_contract import build_universal_valuation_contract
from valuation_method_router import PROFILES, route_valuation

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "_system" / "reference" / "valuation_validation_cohort.json"
FOLLOWUPS = ROOT / "_system" / "reference" / "valuation_followups.json"
OUT = ROOT / "_system" / "research" / "valuation_validation_cohort.json"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def starter_packet(row: dict) -> dict:
    profile = PROFILES[row["profile"]]
    synthetic = {"ticker": row["ticker"], "classification_inputs": {"archetype": row.get("archetype")}}
    route = route_valuation(synthetic, row["profile"])
    return {
        "schema_version": "1.0",
        "ticker": row["ticker"],
        "status": "evidence_blocked_model_required",
        "purpose": row["purpose"],
        "method_route": route,
        "required_component_map": profile["required_evidence"],
        "required_outputs": [
            "fully diluted price and share count", "complete non-overlapping component schedule", "low/base/high causal scenarios",
            "annualized return at price", "downside", "reverse expectations", "evidence proof", "falsifiers",
        ],
        "primary_sources": row.get("primary_sources") or [],
        "unvalued_component_count": 1,
        "next_action": "Build and primary-source the complete component schedule; do not infer decision-grade value from this scaffold.",
    }


def run_security(row: dict, as_of: str, write_ticker: bool) -> dict:
    ticker = row["ticker"]
    valuation_path = ROOT / ticker / "research" / "valuation.json"
    if not valuation_path.exists():
        packet = starter_packet(row)
        packet["as_of"] = as_of
        if write_ticker:
            path = ROOT / ticker / "research" / "valuation_model_scaffold.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        return packet
    original = read(valuation_path)
    try:
        calculated = compute_valuation(copy.deepcopy(original))
        contract = calculated.get("universal_valuation_contract") or build_universal_valuation_contract(calculated, row["profile"])
        contract["method_route"] = route_valuation(calculated, row["profile"])
        contract["cohort_purpose"] = row["purpose"]
        contract["cohort_expected_profile"] = row["profile"]
        routed = (contract.get("method_route") or {}).get("profile_id")
        contract["profile_match"] = routed == row["profile"]
        if not contract["profile_match"]:
            contract.setdefault("evidence", {}).setdefault("blockers", []).append(f"Expected cohort profile {row['profile']} but deterministic router selected {routed}.")
            contract["status"] = "evidence_blocked"
        followups = ((read(FOLLOWUPS).get("tickers") or {}).get(ticker) or {}).get("evidence_gaps") or []
        open_followups = [gap for gap in followups if gap.get("status") not in {"resolved", "not_applicable"}]
        if open_followups:
            contract.setdefault("evidence", {}).setdefault("blockers", []).extend(
                f"{gap.get('id')}: {gap.get('question')}" for gap in open_followups
            )
            contract["evidence"]["unresolved_count"] = len(set(contract["evidence"]["blockers"]))
            contract["status"] = "evidence_blocked"
        if write_ticker:
            path = ROOT / ticker / "research" / "valuation_contract.json"
            path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        return contract
    except (KeyError, TypeError, ValueError) as exc:
        packet = starter_packet(row)
        packet.update({"as_of": as_of, "status": "evidence_blocked_invalid_or_legacy_model", "validation_error": str(exc)})
        if write_ticker:
            path = ROOT / ticker / "research" / "valuation_model_scaffold.json"
            path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        return packet


def build(as_of: str, write_tickers: bool = False) -> dict:
    rows = [run_security(row, as_of, write_tickers) for row in read(CONFIG)["securities"]]
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": "1.0", "as_of": as_of, "security_count": len(rows), "status_counts": counts,
        "securities": rows,
        "acceptance_rule": "A cohort case passes only with zero unvalued material components, no double counting, a matching deterministic route, and no material evidence blockers.",
    }


def markdown(payload: dict) -> str:
    lines = ["# Generalized valuation validation cohort", "", f"**As of:** {payload['as_of']}", "", "| Ticker | Status | Power zone | Unvalued | Next action |", "|---|---|---|---:|---|"]
    for row in payload["securities"]:
        route = row.get("method_route") or {}
        coverage = row.get("component_coverage") or {}
        lines.append(f"| {row.get('ticker')} | {row.get('status')} | {route.get('profile_id', 'pending')} | {coverage.get('unvalued_component_count', row.get('unvalued_component_count', 0))} | {row.get('next_action', 'Close listed evidence blockers.')} |")
    lines.extend(["", payload["acceptance_rule"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--write-tickers", action="store_true")
    args = parser.parse_args()
    payload = build(args.date, args.write_tickers)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUT.with_suffix(".md").write_text(markdown(payload), encoding="utf-8")
    print(json.dumps(payload["status_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
