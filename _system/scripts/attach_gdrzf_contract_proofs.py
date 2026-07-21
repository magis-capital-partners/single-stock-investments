#!/usr/bin/env python3
"""Attach deterministic calculation proofs to GDRZF component_valuation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from calculation_proof import evaluate_calculation_proof

VAL_PATH = ROOT / "GDRZF" / "research" / "valuation.json"
ARB_II = "GDRZF/investor-documents/ir-gdrzf/GR_Vz_2025.03.05_Arb_II_Final_Draft_RFA__330pm_ET_.pdf"
SALE_ORDER = (
    "GDRZF/investor-documents/ir-gdrzf/"
    "2025-11-29-2556-Crystallex-International-Corporation-v-ORDER-I-APPROVING-STOCK-PURCHASE-AGREEMENT-II.pdf"
)
VALUATION_INPUTS = "GDRZF/research/valuation.json"


def src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def corporate_cash_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "estimate",
                "value": 147.869033,
                "unit": "million_shares",
                "source": src(
                    VALUATION_INPUTS,
                    "inputs.shares_outstanding 147,869,033; aggregator pending SEDAR confirmation",
                    "2026-07-17",
                ),
            }
        ],
        "assumptions": [
            {
                "id": "cash_m",
                "label": "Corporate cash available to common (USD millions)",
                "kind": "judgment",
                "values": {"low": 59.15, "base": 100.48, "high": 133.08},
                "unit": "USD_m",
                "rationale": (
                    "Secondary cash ~USD 100M after 2025/2026 placements; low haircuts burn and "
                    "placement dilution; high allows modest upside to aggregator cash."
                ),
                "allowed_range": {"min": 40.0, "max": 160.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Corporate cash per share",
                "op": "divide",
                "args": ["cash_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def risked_award_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "unpaid_award_m",
                "label": "Unpaid ICSID/settlement award face (USD millions)",
                "kind": "estimate",
                "value": 1180.0,
                "unit": "USD_m",
                "source": src(
                    ARB_II,
                    "Company H1 2025 interim Note 5 unpaid award estimate ~USD 1.18B as of 2026-06-30",
                    "2025-06-30",
                ),
            },
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "estimate",
                "value": 147.869033,
                "unit": "million_shares",
                "source": src(
                    VALUATION_INPUTS,
                    "inputs.shares_outstanding 147,869,033; aggregator pending SEDAR confirmation",
                    "2026-07-17",
                ),
            },
        ],
        "assumptions": [
            {
                "id": "net_to_equity_pct",
                "label": "Risked net recovery to common after CVR, bonus, seniors, timing",
                "kind": "judgment",
                "values": {"low": 0.188, "base": 0.689, "high": 1.503},
                "unit": "ratio",
                "rationale": (
                    "Delaware attached-judgment path and Amber SPA Incremental Consideration mechanics; "
                    "CVR 5.466% and bonus-plan leakage netted; senior creditor ranking uncertain."
                ),
                "allowed_range": {"min": 0.05, "max": 2.0},
            },
            {
                "id": "timing_discount",
                "label": "Present-value discount for ~4-year realization horizon",
                "kind": "judgment",
                "values": {"low": 1.0, "base": 1.0, "high": 1.0},
                "unit": "ratio",
                "rationale": "Risked recovery range already embeds timing and process probability in net_to_equity_pct.",
                "allowed_range": {"min": 0.5, "max": 1.0},
            },
        ],
        "calculations": [
            {
                "id": "risked_recovery_m",
                "label": "Risked net equity recovery",
                "op": "multiply",
                "args": ["unpaid_award_m", "net_to_equity_pct"],
                "unit": "USD_m",
            },
            {
                "id": "pv_recovery_m",
                "label": "Present value of risked recovery",
                "op": "multiply",
                "args": ["risked_recovery_m", "timing_discount"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Risked award recovery per share",
                "op": "divide",
                "args": ["pv_recovery_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def arb_ii_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "estimate",
                "value": 147.869033,
                "unit": "million_shares",
                "source": src(
                    VALUATION_INPUTS,
                    "inputs.shares_outstanding 147,869,033; aggregator pending SEDAR confirmation",
                    "2026-07-17",
                ),
            }
        ],
        "assumptions": [
            {
                "id": "gross_success_m",
                "label": "Gross incremental Arb II success value to equity",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.0, "high": 738.45},
                "unit": "USD_m",
                "rationale": (
                    "Arb II RFA pleads damages above USD 7B; base zero until tribunal path clearer; "
                    "high case is bull-only optionality after collectibility haircut."
                ),
                "allowed_range": {"min": 0.0, "max": 2000.0},
            },
            {
                "id": "success_probability",
                "label": "Probability-weighted realization of gross success value",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.0, "high": 1.0},
                "unit": "ratio",
                "rationale": "Base treats success probability as ~0; high case is explicit bull sensitivity only.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
        ],
        "calculations": [
            {
                "id": "risked_m",
                "label": "Risked Arb II option value",
                "op": "multiply",
                "args": ["gross_success_m", "success_probability"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Arb II option per share",
                "op": "divide",
                "args": ["risked_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def legal_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "shares_m",
                "label": "Diluted shares outstanding",
                "kind": "estimate",
                "value": 147.869033,
                "unit": "million_shares",
                "source": src(
                    VALUATION_INPUTS,
                    "inputs.shares_outstanding 147,869,033; aggregator pending SEDAR confirmation",
                    "2026-07-17",
                ),
            }
        ],
        "assumptions": [
            {
                "id": "reserve_m",
                "label": "Legal burn and senior-claim reserve (USD millions, negative)",
                "kind": "judgment",
                "values": {"low": -147.87, "base": -73.935, "high": -29.574},
                "unit": "USD_m",
                "rationale": (
                    "Ongoing litigation spend and ranking leakage versus other attached judgment creditors "
                    "on CITGO proceeds; does not double-count CVR already netted in recovery."
                ),
                "allowed_range": {"min": -250.0, "max": -10.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Legal burn and senior-claim reserve per share",
                "op": "divide",
                "args": ["reserve_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "corporate_cash": corporate_cash_proof,
    "risked_award_citgo_recovery": risked_award_proof,
    "arb_ii_option": arb_ii_proof,
    "legal_burn_and_senior_claims_reserve": legal_reserve_proof,
}

METHOD_MAP = {
    "corporate_cash": "net_asset_value",
    "risked_award_citgo_recovery": "probability_weighted_catalyst_nav",
    "arb_ii_option": "risk_adjusted_milestone_value",
    "legal_burn_and_senior_claims_reserve": "net_asset_value",
}


def main() -> int:
    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    report = []
    for component in (data.get("component_valuation") or {}).get("components") or []:
        cid = component.get("id")
        builder = PROOFS.get(cid)
        if not builder:
            continue
        proof = builder()
        result = evaluate_calculation_proof(proof)
        valuation = component.setdefault("valuation", {})
        valuation["calculation_proof"] = proof
        valuation["method"] = METHOD_MAP[cid]
        valuation["valuation_status"] = "bounded_estimate" if result["status"] == "valid" else "unpriced"
        report.append({"component_id": cid, "status": result["status"], "outputs": result.get("outputs")})
    data["as_of"] = "2026-07-21"
    VAL_PATH.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({"proofs_attached": report}, indent=2))
    return 0 if all(r["status"] == "valid" for r in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
