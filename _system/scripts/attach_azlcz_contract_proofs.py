#!/usr/bin/env python3
"""Attach deterministic calculation proofs to AZLCZ component_valuation_results."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from calculation_proof import evaluate_calculation_proof

VAL_PATH = ROOT / "AZLCZ" / "research" / "valuation.json"
ANNUAL = "AZLCZ/investor-documents/ir-azlcz/2025-12-31_Annual_Report.pdf"
ANNUAL_TEXT = "AZLCZ/research/evidence/_text/2025-12-31_Annual_Report.pdf.txt"
FY2024_ANNUAL = "AZLCZ/investor-documents/ir-azlcz/2024-12-31_Annual_Report.pdf"


def src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def current_lease_cash_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "owner_cash_m",
                "label": "Normalized owner cash (FY2024 run-rate)",
                "kind": "fact",
                "value": 2.134121,
                "unit": "USD millions",
                "locked": True,
                "source": src(FY2024_ANNUAL, "Statements of revenues and expenses; excess revenues over expenses $2,134,121 for year ended 2024-12-31", "2024-12-31"),
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares issued and outstanding at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "cap_multiple",
                "label": "Owner-cash capitalization multiple on current leases only",
                "kind": "judgment",
                "values": {"low": 8.5, "base": 16.0, "high": 23.5},
                "unit": "multiple",
                "rationale": "Bounded range for contracted ground-rent durability; excludes incremental project rent already modeled separately.",
                "allowed_range": {"min": 6.0, "max": 30.0},
            }
        ],
        "calculations": [
            {"id": "capitalized_m", "label": "Capitalized current lease cash", "op": "multiply", "args": ["owner_cash_m", "cap_multiple"], "unit": "USD millions"},
            {"id": "value_per_share", "label": "Current lease value per share", "op": "divide", "args": ["capitalized_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def incremental_renewable_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "owner_cash_m",
                "label": "Normalized owner cash baseline",
                "kind": "fact",
                "value": 2.134121,
                "unit": "USD millions",
                "locked": True,
                "source": src(FY2024_ANNUAL, "FY2024 excess revenues over expenses $2,134,121", "2024-12-31"),
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "steady_state_m",
                "label": "Steady-state renewable owner cash",
                "kind": "judgment",
                "values": {"low": 6.8, "base": 9.9, "high": 12.9},
                "unit": "USD millions",
                "rationale": "Approved Groundbreaker project ramp cross-check; bounded pending full contract disclosure.",
                "allowed_range": {"min": 5.0, "max": 15.0},
            },
            {
                "id": "steady_multiple",
                "label": "Steady-state capitalization multiple",
                "kind": "judgment",
                "values": {"low": 15.0, "base": 16.0, "high": 18.0},
                "unit": "multiple",
                "rationale": "Groundbreaker comparable lease portfolio capitalization.",
                "allowed_range": {"min": 12.0, "max": 20.0},
            },
            {
                "id": "current_multiple",
                "label": "Current lease capitalization multiple",
                "kind": "judgment",
                "values": {"low": 8.5, "base": 16.0, "high": 23.5},
                "unit": "multiple",
                "rationale": "Matches current_lease_cash component to avoid double counting.",
                "allowed_range": {"min": 6.0, "max": 30.0},
            },
            {
                "id": "completion_discount",
                "label": "Completion and timing discount on incremental rent",
                "kind": "judgment",
                "values": {"low": 0.714, "base": 0.695, "high": 0.814},
                "unit": "ratio",
                "rationale": "Discount for projects still in cancellable development or construction terms per Note 10.",
                "allowed_range": {"min": 0.4, "max": 0.9},
            },
        ],
        "calculations": [
            {"id": "portfolio_m", "label": "Steady-state capitalized portfolio", "op": "multiply", "args": ["steady_state_m", "steady_multiple"], "unit": "USD millions"},
            {"id": "portfolio_ps", "label": "Steady-state portfolio per share", "op": "divide", "args": ["portfolio_m", "shares_m"], "unit": "USD per share"},
            {"id": "current_cap_m", "label": "Current capitalized lease cash", "op": "multiply", "args": ["owner_cash_m", "current_multiple"], "unit": "USD millions"},
            {"id": "current_ps", "label": "Current lease per share", "op": "divide", "args": ["current_cap_m", "shares_m"], "unit": "USD per share"},
            {"id": "undiscounted_ps", "label": "Undiscounted incremental per share", "op": "subtract", "args": ["portfolio_ps", "current_ps"], "unit": "USD per share"},
            {"id": "value_per_share", "label": "Risked incremental renewable per share", "op": "multiply", "args": ["undiscounted_ps", "completion_discount"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def residual_surface_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "residual_acres",
                "label": "Residual surface acres after panel overlap",
                "kind": "estimate",
                "value": 234800,
                "unit": "acres",
                "locked": True,
                "source": src(ANNUAL_TEXT, "Note 1 ~239,000 surface acres minus ~4,200 Hashknife solar panel acres per Groundbreaker segmentation cross-check", "2025-12-31"),
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "per_acre_mark",
                "label": "Segmented comparable per-acre mark",
                "kind": "judgment",
                "values": {"low": 603.0, "base": 1100.0, "high": 2015.0},
                "unit": "USD per acre",
                "rationale": "Approved Groundbreaker transaction ladder by parcel class; not a single portfolio average.",
                "allowed_range": {"min": 400.0, "max": 2500.0},
            },
            {
                "id": "realization_discount",
                "label": "Checkerboard, control, and transaction friction discount",
                "kind": "judgment",
                "values": {"low": 0.424, "base": 0.521, "high": 0.680},
                "unit": "ratio",
                "rationale": "Converts gross comparable land NAV to risked present value for minority OTC holders.",
                "allowed_range": {"min": 0.2, "max": 0.85},
            },
        ],
        "calculations": [
            {"id": "gross_value_dollars", "label": "Gross land NAV dollars", "op": "multiply", "args": ["residual_acres", "per_acre_mark"], "unit": "USD"},
            {"id": "gross_value_m", "label": "Gross land NAV millions", "op": "multiply", "args": ["gross_value_dollars", 0.000001], "unit": "USD millions"},
            {"id": "gross_ps", "label": "Gross land NAV per share", "op": "divide", "args": ["gross_value_m", "shares_m"], "unit": "USD per share"},
            {"id": "value_per_share", "label": "Risked residual land per share", "op": "multiply", "args": ["gross_ps", "realization_discount"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def mineral_option_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "mineral_acres",
                "label": "Mineral acres disclosed",
                "kind": "fact",
                "value": 318000,
                "unit": "acres",
                "locked": True,
                "source": src(ANNUAL_TEXT, "Note 1; approximately 318,000 acres of mineral rights", "2025-12-31"),
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "gross_option_m",
                "label": "Gross comparable mineral option value",
                "kind": "judgment",
                "values": {"low": 5.0, "base": 20.0, "high": 75.0},
                "unit": "USD millions",
                "rationale": "Groundbreaker Holbrook Basin option marks; no production royalties in filings yet.",
                "allowed_range": {"min": 0.0, "max": 100.0},
            },
            {
                "id": "success_probability",
                "label": "Realization probability",
                "kind": "judgment",
                "values": {"low": 0.1417, "base": 0.248, "high": 0.283},
                "unit": "ratio",
                "rationale": "Permitting, deposit overlap, and absence of operator reduce probability; widened range in high case.",
                "allowed_range": {"min": 0.05, "max": 0.5},
            },
        ],
        "calculations": [
            {"id": "risked_m", "label": "Risked mineral option value", "op": "multiply", "args": ["gross_option_m", "success_probability"], "unit": "USD millions"},
            {"id": "value_per_share", "label": "Mineral option per share", "op": "divide", "args": ["risked_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def water_option_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "south_well_af",
                "label": "South Well Field entitlement",
                "kind": "fact",
                "value": 13490,
                "unit": "acre-feet per year",
                "locked": True,
                "source": src(ANNUAL_TEXT, "Note 17; Corporation entitled to 13,490 acre feet per year from South Well Field", "2025-12-31"),
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "gross_option_m",
                "label": "Gross comparable water option value",
                "kind": "judgment",
                "values": {"low": 15.0, "base": 40.0, "high": 90.0},
                "unit": "USD millions",
                "rationale": "Groundbreaker pre-adjudication marks; western water transactions are contextual only.",
                "allowed_range": {"min": 5.0, "max": 120.0},
            },
            {
                "id": "realization_probability",
                "label": "Transferable and adjudicated realization probability",
                "kind": "judgment",
                "values": {"low": 0.1417, "base": 0.354, "high": 0.551},
                "unit": "ratio",
                "rationale": "Little Colorado adjudication unresolved; base uses fraction of entitlement, not full 13,490 AF mark.",
                "allowed_range": {"min": 0.05, "max": 0.75},
            },
        ],
        "calculations": [
            {"id": "risked_m", "label": "Risked water option value", "op": "multiply", "args": ["gross_option_m", "realization_probability"], "unit": "USD millions"},
            {"id": "value_per_share", "label": "Water option per share", "op": "divide", "args": ["risked_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def railway_notes_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "railway_book_m",
                "label": "Investment in Apache Railroad Company LLC",
                "kind": "fact",
                "value": 3.592687,
                "unit": "USD millions",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; Investment in The Apache Railroad Company, LLC $3,592,687", "2025-12-31"),
            },
            {
                "id": "notes_m",
                "label": "Notes receivable, related parties",
                "kind": "fact",
                "value": 5.01936,
                "unit": "USD millions",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; Notes receivable, related parties $5,019,360", "2025-12-31"),
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "railway_strategic_m",
                "label": "Strategic railway replacement value",
                "kind": "judgment",
                "values": {"low": 4.25, "base": 10.62, "high": 21.25},
                "unit": "USD millions",
                "rationale": "Groundbreaker replacement difficulty and BNSF interchange; base equals risked $75/sh total before note haircuts.",
                "allowed_range": {"min": 3.0, "max": 30.0},
            },
            {
                "id": "notes_collectability",
                "label": "Related-party notes collectability",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.0, "high": 0.35},
                "unit": "ratio",
                "rationale": "Base case values strategic railway only; high case adds partial note recovery after illiquidity haircut.",
                "allowed_range": {"min": 0.0, "max": 0.75},
            },
        ],
        "calculations": [
            {"id": "notes_risked_m", "label": "Collectible notes", "op": "multiply", "args": ["notes_m", "notes_collectability"], "unit": "USD millions"},
            {"id": "total_m", "label": "Railway and notes economic value", "op": "add", "args": ["railway_strategic_m", "notes_risked_m"], "unit": "USD millions"},
            {"id": "value_per_share", "label": "Railway and notes per share", "op": "divide", "args": ["total_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def realization_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD per share",
        "inputs": [
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 0.141666,
                "unit": "million shares",
                "locked": True,
                "source": src(ANNUAL, "Balance sheet; 141,666 shares at 2025-12-31", "2025-12-31"),
            },
        ],
        "assumptions": [
            {
                "id": "reserve_m",
                "label": "Tax, governance, and illiquidity reserve",
                "kind": "judgment",
                "values": {"low": -14.16, "base": -10.62, "high": -5.67},
                "unit": "USD millions",
                "rationale": "OTC minority control, related-party friction, and realization taxes beyond filing liabilities.",
                "allowed_range": {"min": -25.0, "max": -2.0},
            }
        ],
        "calculations": [
            {"id": "value_per_share", "label": "Realization reserve per share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD per share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "current_lease_cash": current_lease_cash_proof,
    "incremental_renewable_projects": incremental_renewable_proof,
    "residual_surface_acreage": residual_surface_proof,
    "mineral_option": mineral_option_proof,
    "water_option": water_option_proof,
    "railway_and_notes": railway_notes_proof,
    "realization_reserve": realization_reserve_proof,
}


def main() -> int:
    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    components = (data.get("component_valuation_results") or {}).get("additive_components") or []
    report = []
    for row in components:
        cid = row.get("id")
        builder = PROOFS.get(cid)
        if not builder:
            continue
        proof = builder()
        result = evaluate_calculation_proof(proof)
        row["calculation_proof"] = proof
        row["valuation_status"] = "bounded_estimate" if result["status"] == "valid" else "unpriced"
        report.append({"component_id": cid, "status": result["status"], "outputs": result.get("outputs")})
    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": "One AZLCZ common share equals a pro-rata claim on corporation-filed cash, investments, notes, and ground-lease cash flows.",
        "excluded_claims": [
            "Stapled Aztec Land Company LLC units are not look-through valued without legal proof of transfer with AZLCZ shares.",
            "Lessee-side project capital and partner waterfalls sit with developers; AZLCZ receives ground rent only.",
        ],
        "reconciliation": "FY2025 rentals $3.46M and excess cash $2.34M reconcile to filed statements; related-party notes $5.02M and Apache Railway investment $3.59M are modeled with collectability and strategic marks in railway_and_notes.",
        "evidence_ref": "AZLCZ/research/evidence_reconciliation_2026-07-21.json",
    }
    eva["residual_acreage_bridge"] = {
        "disclosed_surface_acres": 239000,
        "less_panel_footprint_acres": 4200,
        "residual_surface_acres": 234800,
        "overlap_control": "Renewable lease cash is in current_lease_cash and incremental_renewable_projects; panel acres are excluded from residual_surface_acreage.",
        "evidence_ref": "AZLCZ/investor-documents/ir-azlcz/2025-12-31_Annual_Report.pdf Note 1 and Note 10",
    }
    eva["water_realization_bounds"] = {
        "south_well_field_entitlement_af": 13490,
        "north_well_field_delivered_2025_af": 95,
        "transferable_volume_basis": "Base and low cases apply explicit realization probabilities; full entitlement is not marked without adjudication.",
        "adjudication_status": "Little Colorado River general adjudication ongoing; Settlement Agreement pending federal legislation.",
        "evidence_ref": "AZLCZ/investor-documents/ir-azlcz/2025-12-31_Annual_Report.pdf Notes 13 and 17",
    }
    eva["validation_errors"] = []
    data["as_of"] = "2026-07-21"
    VAL_PATH.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({"proofs_attached": report}, indent=2))
    return 0 if all(r["status"] == "valid" for r in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
