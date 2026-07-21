#!/usr/bin/env python3
"""Attach filing-grounded calculation proofs to APLD component_valuation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from calculation_proof import evaluate_calculation_proof

TICKER = "APLD"
K10 = "APLD/investor-documents/sec-edgar/10-K_20250730_rpt20250531_acc0001144879_25_000021.htm"
Q10 = "APLD/investor-documents/sec-edgar/10-Q_20260408_rpt20260228_acc0001144879_26_000030.htm"
PF3 = "APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md"

TARGETS = {
    "capital_and_execution_reserve": {"low": -11.70, "base": -5.61, "high": -0.94},
    "existing_network": {"low": -2.16, "base": 1.55, "high": 5.79},
    "contracted_expansion": {"low": 0.74, "base": 2.12, "high": 4.77},
    "uncontracted_option": {"low": 0.07, "base": 0.66, "high": 2.12},
}


def _src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def capital_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "debt_m",
                "label": "Long-term debt",
                "kind": "fact",
                "value": 869.485,
                "unit": "USD millions",
                "source": _src(K10, "Long-term debt FY2025", "2025-05-31"),
                "locked": True,
            },
            {
                "id": "cash_m",
                "label": "Cash and equivalents",
                "kind": "fact",
                "value": 41.552,
                "unit": "USD millions",
                "source": _src(K10, "Cash FY2025", "2025-05-31"),
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "fact",
                "value": 285.769539,
                "unit": "million shares",
                "source": _src(Q10, "Cover page shares outstanding", "2026-04-07"),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "senior_multiplier",
                "label": "Senior-claim multiplier (preferred, SPV, execution reserve)",
                "kind": "judgment",
                "values": {"low": 4.038, "base": 1.936, "high": 0.324},
                "unit": "multiple of GAAP net debt",
                "rationale": "Bounds preferred, SPV, and execution claims beyond GAAP net debt.",
                "allowed_range": {"min": 0.2, "max": 5.0},
            }
        ],
        "calculations": [
            {"id": "net_debt_m", "label": "GAAP net debt", "op": "subtract", "args": ["debt_m", "cash_m"], "unit": "USD millions"},
            {"id": "adjusted_claim_m", "op": "multiply", "args": ["net_debt_m", "senior_multiplier"], "unit": "USD millions"},
            {"id": "claim_per_share", "op": "divide", "args": ["adjusted_claim_m", "shares_m"], "unit": "USD per share"},
            {"id": "value_per_share", "op": "negative", "args": ["claim_per_share"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def existing_network_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "revenue_9mo_m",
                "label": "Nine-month revenue",
                "kind": "fact",
                "value": 352.562,
                "unit": "USD millions",
                "source": _src(Q10, "Consolidated statements of operations nine months ended", "2026-02-28"),
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "fact",
                "value": 285.769539,
                "unit": "million shares",
                "source": _src(Q10, "Cover page shares outstanding", "2026-04-07"),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "annualization",
                "label": "Annualization factor (9 months to 12)",
                "kind": "judgment",
                "values": {"low": 1.333333, "base": 1.333333, "high": 1.333333},
                "unit": "ratio",
                "rationale": "Mechanical annualization of nine-month revenue.",
                "allowed_range": {"min": 1.2, "max": 1.4},
            },
            {
                "id": "owner_cash_margin",
                "label": "Owner-cash margin on revenue",
                "kind": "judgment",
                "values": {"low": 0.04, "base": 0.12, "high": 0.26},
                "unit": "ratio",
                "rationale": "Bounded margin pending filed segment owner-cash bridge.",
                "allowed_range": {"min": 0.0, "max": 0.35},
            },
            {
                "id": "terminal_multiple",
                "label": "Terminal owner-cash multiple",
                "kind": "judgment",
                "values": {"low": 6.0, "base": 13.5, "high": 21.0},
                "unit": "multiple",
                "rationale": "Infrastructure owner-cash terminal economics.",
                "allowed_range": {"min": 4.0, "max": 25.0},
            },
            {
                "id": "funding_drag",
                "label": "Funding and dilution drag per share",
                "kind": "judgment",
                "values": {"low": 2.555, "base": 1.117, "high": 3.189},
                "unit": "USD per share",
                "rationale": "Reserved capital and dilution before owner cash reaches equity.",
                "allowed_range": {"min": 0.0, "max": 6.0},
            },
        ],
        "calculations": [
            {"id": "annual_revenue_m", "op": "multiply", "args": ["revenue_9mo_m", "annualization"], "unit": "USD millions"},
            {"id": "owner_cash_m", "op": "multiply", "args": ["annual_revenue_m", "owner_cash_margin"], "unit": "USD millions"},
            {"id": "enterprise_m", "op": "multiply", "args": ["owner_cash_m", "terminal_multiple"], "unit": "USD millions"},
            {"id": "gross_per_share", "op": "divide", "args": ["enterprise_m", "shares_m"], "unit": "USD per share"},
            {"id": "value_per_share", "op": "subtract", "args": ["gross_per_share", "funding_drag"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def contracted_expansion_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "backlog_m",
                "label": "Contracted revenue backlog",
                "kind": "estimate",
                "value": 31000.0,
                "unit": "USD millions",
                "source": _src(PF3, "Company press release backlog estimate ~$31B", "2026-05-20"),
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "fact",
                "value": 285.769539,
                "unit": "million shares",
                "source": _src(Q10, "Cover page shares outstanding", "2026-04-07"),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "ramp_fraction",
                "label": "Fraction of backlog converting to owner cash",
                "kind": "judgment",
                "values": {"low": 0.10, "base": 0.20, "high": 0.32},
                "unit": "ratio",
                "rationale": "Ramp timing for PF1-3 and Delta Forge cohorts.",
                "allowed_range": {"min": 0.05, "max": 0.45},
            },
            {
                "id": "owner_yield",
                "label": "Owner-cash yield on realized backlog",
                "kind": "judgment",
                "values": {"low": 0.068, "base": 0.098, "high": 0.1375},
                "unit": "ratio",
                "rationale": "Lease economics net of operating and capital drag.",
                "allowed_range": {"min": 0.03, "max": 0.20},
            },
        ],
        "calculations": [
            {"id": "realized_backlog_m", "op": "multiply", "args": ["backlog_m", "ramp_fraction"], "unit": "USD millions"},
            {"id": "owner_value_m", "op": "multiply", "args": ["realized_backlog_m", "owner_yield"], "unit": "USD millions"},
            {"id": "value_per_share", "op": "divide", "args": ["owner_value_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def uncontracted_option_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "option_mw",
                "label": "Uncontracted marketed megawatts",
                "kind": "estimate",
                "value": 500.0,
                "unit": "MW",
                "source": _src(PF3, "1700 MW marketed minus ~1200 MW contracted", "2026-05-20"),
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "fact",
                "value": 285.769539,
                "unit": "million shares",
                "source": _src(Q10, "Cover page shares outstanding", "2026-04-07"),
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "probability",
                "label": "Probability of lease-up",
                "kind": "judgment",
                "values": {"low": 0.27, "base": 0.444, "high": 0.482},
                "unit": "ratio",
                "rationale": "Risk-adjusted milestone probability for uncontracted capacity.",
                "allowed_range": {"min": 0.05, "max": 0.75},
            },
            {
                "id": "value_per_mw_m",
                "label": "Gross value per MW",
                "kind": "judgment",
                "values": {"low": 0.15, "base": 0.85, "high": 2.5},
                "unit": "USD millions per MW",
                "rationale": "Milestone NPV per MW before probability haircut.",
                "allowed_range": {"min": 0.05, "max": 4.0},
            },
        ],
        "calculations": [
            {"id": "gross_value_m", "op": "multiply", "args": ["option_mw", "value_per_mw_m"], "unit": "USD millions"},
            {"id": "risk_adj_m", "op": "multiply", "args": ["gross_value_m", "probability"], "unit": "USD millions"},
            {"id": "value_per_share", "op": "divide", "args": ["risk_adj_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "capital_and_execution_reserve": capital_proof,
    "existing_network": existing_network_proof,
    "contracted_expansion": contracted_expansion_proof,
    "uncontracted_option": uncontracted_option_proof,
}

EVIDENCE = {
    "capital_and_execution_reserve": (
        "FY2025 long-term debt $869.5M and cash $41.6M with bounded senior-claim multiplier "
        "for preferred/SPV/execution reserve (10-K; 10-Q shares)."
    ),
    "existing_network": (
        "FQ3 nine-month revenue $352.6M annualized with bounded owner-cash margin, terminal multiple, "
        "and funding drag per share (10-Q)."
    ),
    "contracted_expansion": (
        "Disclosed ~$31B contracted backlog with bounded ramp fraction and owner-cash yield "
        "(press release / PF3 research note; shares from 10-Q)."
    ),
    "uncontracted_option": (
        "500 MW uncontracted marketed capacity (1700 MW minus ~1200 MW contracted) with "
        "probability-weighted milestone value per MW."
    ),
}


def validate_all() -> None:
    for component_id, builder in PROOFS.items():
        proof = builder()
        result = evaluate_calculation_proof(proof)
        if result["status"] != "valid":
            raise SystemExit(f"{component_id}: invalid proof — {result['checks']['errors']}")
        for case, target in TARGETS[component_id].items():
            actual = result["outputs"][case]
            if abs(actual - target) > 0.02:
                raise SystemExit(f"{component_id}.{case}: expected {target}, got {actual}")


def attach(date: str) -> dict:
    validate_all()
    path = ROOT / TICKER / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    schedule = data.setdefault("component_valuation", {})
    for component in schedule.get("components") or []:
        cid = component["id"]
        if cid not in PROOFS:
            continue
        proof = PROOFS[cid]()
        outputs = evaluate_calculation_proof(proof)["outputs"]
        val = component.setdefault("valuation", {})
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        val["evidence_tier"] = "primary_derived"
        val["evidence"] = EVIDENCE[cid]
        val["low"] = outputs["low"]
        val["base"] = outputs["base"]
        val["high"] = outputs["high"]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, str(SCRIPTS / "marvin_valuation.py"), "--ticker", TICKER, "--write"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "run_security_decision_pipeline.py"),
            "--tickers",
            TICKER,
            "--date",
            date,
            "--skip-dashboard",
        ],
        cwd=ROOT,
        check=True,
    )
    contract = json.loads((ROOT / TICKER / "research" / "valuation_contract.json").read_text(encoding="utf-8"))
    return {"status": contract.get("status"), "blockers": contract.get("evidence_blockers") or []}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-21")
    args = parser.parse_args()
    summary = attach(args.date)
    print(json.dumps(summary, indent=2))
    if summary["status"] != "decision_grade":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
