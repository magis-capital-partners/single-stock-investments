#!/usr/bin/env python3
"""Attach filing-backed calculation proofs to STHO component_valuation (2026-07-21)."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from calculation_proof import evaluate_calculation_proof

VAL_PATH = ROOT / "STHO" / "research" / "valuation.json"
FILING_10Q = "STHO/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001953366_26_000010.htm"
FILING_10K = "STHO/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001953366_26_000003.htm"
AS_OF = "2026-03-31"
SHARES_M = 12.081333


def src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def shares_input() -> dict:
    return {
        "id": "shares_m",
        "label": "Common shares outstanding",
        "kind": "fact",
        "value": SHARES_M,
        "unit": "million_shares",
        "locked": True,
        "source": src(FILING_10Q, "12,081,333 shares outstanding as of May 6, 2026 (cover page)", AS_OF),
    }


def safehold_equity_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "safe_shares_m",
                "label": "Implied SAFE shares (Q1 fair value / mark price)",
                "kind": "fact",
                "value": 13.525499,
                "unit": "million_shares",
                "locked": True,
                "source": src(
                    FILING_10Q,
                    "Note 7: ~13.5M SAFE shares; fair value $183.0M at $13.53 on 2026-03-31",
                    AS_OF,
                ),
            },
            shares_input(),
        ],
        "assumptions": [
            {
                "id": "safe_mark",
                "label": "SAFE equity mark per share",
                "kind": "judgment",
                "values": {"low": 12.0, "base": 16.93, "high": 25.0},
                "unit": "USD_per_share",
                "rationale": "Low forced-sale stress; base uses 2026-07-16 market; high rate-driven path toward March 2023 deal mark.",
                "allowed_range": {"min": 8.0, "max": 30.0},
            },
            {
                "id": "sale_friction",
                "label": "Governance, margin-loan, and transfer friction on gross stake",
                "kind": "judgment",
                "values": {"low": 0.966, "base": 0.976, "high": 1.0},
                "unit": "ratio",
                "rationale": "Safe Governance Agreement and first-priority margin pledge reduce realizable proceeds vs headline mark.",
                "allowed_range": {"min": 0.85, "max": 1.0},
            },
        ],
        "calculations": [
            {
                "id": "gross_stake_m",
                "label": "Gross SAFE stake value",
                "op": "multiply",
                "args": ["safe_shares_m", "safe_mark"],
                "unit": "USD_m",
            },
            {
                "id": "gross_ps",
                "label": "Gross SAFE stake per STHO share",
                "op": "divide",
                "args": ["gross_stake_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Net SAFE stake per STHO share",
                "op": "multiply",
                "args": ["gross_ps", "sale_friction"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def legacy_monetizing_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "carrying_m",
                "label": "MD&A monetizing portfolio carrying value",
                "kind": "fact",
                "value": 71.4,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    FILING_10Q,
                    "MD&A monetizing: loan $16.1M + AFS $38.2M + land $14.4M + two properties $2.7M = $71.4M",
                    AS_OF,
                ),
            },
            shares_input(),
        ],
        "assumptions": [
            {
                "id": "recovery_fraction",
                "label": "Recovery vs carrying on monetizing schedule only",
                "kind": "judgment",
                "values": {"low": 0.592, "base": 0.897, "high": 1.10},
                "unit": "ratio",
                "rationale": "Low distressed recovery; base on repayments and land-sale margins; high modest premium to carrying.",
                "allowed_range": {"min": 0.4, "max": 1.25},
            }
        ],
        "calculations": [
            {
                "id": "realizable_m",
                "label": "Risk-adjusted monetizing portfolio",
                "op": "multiply",
                "args": ["carrying_m", "recovery_fraction"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Monetizing portfolio per share",
                "op": "divide",
                "args": ["realizable_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def magnolia_asbury_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "residual_carrying_m",
                "label": "Magnolia/Asbury residual carrying after monetizing split",
                "kind": "fact",
                "value": 153.6,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    FILING_10Q,
                    "Q1 L&D $100.5M + RE $70.2M less MD&A monetizing land/other $17.1M = $153.6M residual",
                    AS_OF,
                ),
            },
            shares_input(),
        ],
        "assumptions": [
            {
                "id": "realization_fraction",
                "label": "Realization vs residual carrying",
                "kind": "judgment",
                "values": {"low": 0.315, "base": 0.590, "high": 1.024},
                "unit": "ratio",
                "rationale": "Lot sales above COS support base; low slow/distressed; high approaches carrying with partial entitlement uplift.",
                "allowed_range": {"min": 0.2, "max": 1.15},
            }
        ],
        "calculations": [
            {
                "id": "realizable_m",
                "label": "Risk-adjusted residual real estate",
                "op": "multiply",
                "args": ["residual_carrying_m", "realization_fraction"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Magnolia/Asbury residual per share",
                "op": "divide",
                "args": ["realizable_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def cash_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "cash_m",
                "label": "Cash plus restricted cash",
                "kind": "fact",
                "value": 62.059,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    FILING_10Q,
                    "Balance sheet / Note 8: cash $46.378M + restricted cash $15.681M = $62.059M",
                    AS_OF,
                ),
            },
            shares_input(),
        ],
        "assumptions": [
            {
                "id": "availability",
                "label": "Fraction of cash available to common equity",
                "kind": "judgment",
                "values": {"low": 0.805, "base": 0.992, "high": 0.993},
                "unit": "ratio",
                "rationale": "Low allows restricted-cash leakage or collateral lock; base/high near full availability.",
                "allowed_range": {"min": 0.7, "max": 1.0},
            }
        ],
        "calculations": [
            {
                "id": "available_m",
                "label": "Available cash to equity",
                "op": "multiply",
                "args": ["cash_m", "availability"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Cash per share",
                "op": "divide",
                "args": ["available_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def senior_debt_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "debt_m",
                "label": "Long-term debt obligations net",
                "kind": "fact",
                "value": 207.001,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    FILING_10Q,
                    "Note 9: Safe Credit $115.0M + Margin Loan $92.777M; total debt obligations net $207.001M",
                    AS_OF,
                ),
            },
            shares_input(),
        ],
        "assumptions": [
            {
                "id": "debt_scenario",
                "label": "Debt path multiplier (PIK/draw vs paydown)",
                "kind": "judgment",
                "values": {"low": 1.022, "base": 0.998, "high": 0.964},
                "unit": "ratio",
                "rationale": "Low PIK accretion or incremental draws; high modest paydown from asset sales.",
                "allowed_range": {"min": 0.9, "max": 1.1},
            }
        ],
        "calculations": [
            {
                "id": "scenario_debt_m",
                "label": "Scenario debt balance",
                "op": "multiply",
                "args": ["debt_m", "debt_scenario"],
                "unit": "USD_m",
            },
            {
                "id": "debt_ps",
                "label": "Debt per share before sign",
                "op": "divide",
                "args": ["scenario_debt_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Senior debt per share (negative)",
                "op": "negative",
                "args": ["debt_ps"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def fee_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "fee_path_m",
                "label": "Undiscounted management fee and friction path",
                "kind": "estimate",
                "value": 19.7,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    FILING_10Q,
                    "Note 1 fee schedule: $7.5M current term + 2% GBV ex-SAFE; illustrative wind-down sum ~$19.7M",
                    AS_OF,
                ),
            },
            shares_input(),
        ],
        "assumptions": [
            {
                "id": "fee_multiplier",
                "label": "Present-value and contestability adjustment on fee path",
                "kind": "judgment",
                "values": {"low": 1.533, "base": 0.86, "high": 0.245},
                "unit": "ratio",
                "rationale": "Low keeps termination overhang and high friction; base Safehold-managed wind-down; high post-2027-03-31 competitive management.",
                "allowed_range": {"min": 0.1, "max": 2.0},
            }
        ],
        "calculations": [
            {
                "id": "reserve_m",
                "label": "Fee and friction reserve",
                "op": "multiply",
                "args": ["fee_path_m", "fee_multiplier"],
                "unit": "USD_m",
            },
            {
                "id": "reserve_ps",
                "label": "Reserve per share before sign",
                "op": "divide",
                "args": ["reserve_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Fee reserve per share (negative)",
                "op": "negative",
                "args": ["reserve_ps"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def zero_carry_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [shares_input()],
        "assumptions": [
            {
                "id": "option_gross_m",
                "label": "Incremental zero-carry and entitlement surplus (enterprise dollars)",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 2.42, "high": 24.2},
                "unit": "USD_m",
                "rationale": "Failure value zero; base modest recovery beyond Magnolia/Asbury carrying; high entitlement surplus case.",
                "allowed_range": {"min": 0.0, "max": 40.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Zero-carry option per share",
                "op": "divide",
                "args": ["option_gross_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "safehold_equity_stake": safehold_equity_proof,
    "legacy_monetizing_portfolio": legacy_monetizing_proof,
    "magnolia_asbury_development_ops": magnolia_asbury_proof,
    "cash_and_restricted": cash_proof,
    "senior_debt": senior_debt_proof,
    "wind_down_fee_and_friction_reserve": fee_reserve_proof,
    "zero_carry_and_entitlement_option": zero_carry_proof,
}


def apply_proof(row: dict, proof: dict, ev: dict) -> None:
    row["calculation_proof"] = proof
    row["valuation_status"] = "bounded_estimate" if ev["status"] == "valid" else "unpriced"
    for case in ("low", "base", "high"):
        row[f"{case}_per_share"] = ev["outputs"][case]
    summary = f"Proof outputs {ev['outputs']}; see calculation_proof graph."
    row["assumption_summary"] = summary
    row["scenario_assumptions"] = summary


def main() -> int:
    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-21"
    report = []

    for component in data.get("component_valuation", {}).get("components") or []:
        cid = component.get("id")
        builder = PROOFS.get(cid)
        if not builder:
            continue
        proof = builder()
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemExit(f"{cid} proof invalid: {ev['checks']['errors']}")
        val = component.setdefault("valuation", {})
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        for case in ("low", "base", "high"):
            val[case] = ev["outputs"][case]
        val["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph via {proof['method_id']}@1.0."
        )
        report.append({"component_id": cid, "status": ev["status"], "outputs": ev["outputs"]})

    for row in (data.get("component_valuation_results") or {}).get("additive_components") or []:
        cid = row.get("id")
        builder = PROOFS.get(cid)
        if not builder:
            continue
        proof = deepcopy(PROOFS[cid]())
        ev = evaluate_calculation_proof(proof)
        apply_proof(row, proof, ev)

    eva = data.setdefault("economic_value_analysis", {})
    eva["validation_errors"] = []
    eva["safe_stake_reconciliation"] = {
        "safe_shares_implied": 13525499,
        "q1_fair_value_m": 183.0,
        "q1_mark_price": 13.53,
        "margin_loan_m": 92.777,
        "safe_credit_m": 115.0,
        "net_safe_after_margin_only_ps": 11.27,
        "remaining_uncertainty": [
            "Exact integer SAFE share count not disclosed.",
            "Numeric margin LTV trigger percentages not disclosed.",
        ],
        "evidence_ref": "STHO/research/evidence_reconciliation_2026-07-16.md § Gap 1",
    }
    eva["legacy_asset_schedule_reconciliation"] = {
        "monetizing_carrying_m": 71.4,
        "residual_magnolia_asbury_m": 153.6,
        "overlap_control": "Monetizing MD&A schedule excludes Magnolia/Asbury residual; zero-carry claims in separate option component.",
        "remaining_uncertainty": ["No asset-level third-party bids for Magnolia/Asbury residual."],
        "evidence_ref": "STHO/research/evidence_reconciliation_2026-07-16.md § Gap 2",
    }
    eva["fee_waterfall_reconciliation"] = {
        "current_term_fee_m": 7.5,
        "termination_overhang_m": 5.0,
        "illustrative_undiscounted_fee_path_m": 19.7,
        "cash_taxes_2025_m": 0.2,
        "remaining_uncertainty": [
            "Exact GBV definition for 2% post-2027 fee.",
            "Asset-level sale tax and transaction costs not scheduled.",
        ],
        "evidence_ref": "STHO/research/evidence_reconciliation_2026-07-16.md § Gap 3",
    }

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"proofs_attached": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
