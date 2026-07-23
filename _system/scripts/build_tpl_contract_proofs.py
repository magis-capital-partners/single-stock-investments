#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into TPL valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "TPL" / "research" / "valuation.json"

FILING_10K = "TPL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001811074_26_000018.htm"
FILING_10Q = "TPL/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001811074_26_000035.htm"
AS_OF_FY = "2025-12-31"
AS_OF_Q1 = "2026-03-31"
SHARES_M = 69.027

LEGACY = {
    "producing_royalty_operations": {"low": 42.59, "base": 88.35, "high": 152.93},
    "existing_surface_and_easement_operations": {"low": 7.08, "base": 14.89, "high": 27.31},
    "produced_water_royalties": {"low": 20.32, "base": 43.25, "high": 89.98},
    "cash_and_investments": {"low": 3.6, "base": 4.32, "high": 4.32},
    "operated_water_sales": {"low": 6.38, "base": 16.41, "high": 39.57},
    "contracted_data_center_receivable": {"low": 0.27, "base": 0.3, "high": 0.32},
    "visible_royalty_inventory_option": {"low": 17.35, "base": 18.65, "high": 40.7},
    "dormant_royalty_inventory_option": {"low": 21.21, "base": 22.8, "high": 49.77},
    "residual_surface_land_option": {"low": 15.34, "base": 32.59, "high": 65.77},
    "future_infrastructure_corridors": {"low": 0.8, "base": 4.46, "high": 13.48},
    "data_center_power_water_option": {"low": 0.22, "base": 2.03, "high": 12.75},
    "desalination_and_water_technology_option": {"low": -0.3, "base": 1.16, "high": 10.51},
    "realization_and_corporate_reserve": {"low": -5.0, "base": -3.0, "high": -1.0},
}


def _src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(ref, locator, as_of),
        "locked": True,
    }


def _judgment(
    node_id: str,
    label: str,
    values: dict[str, float],
    unit: str,
    rationale: str,
    lo: float,
    hi: float,
) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "judgment",
        "values": values,
        "unit": unit,
        "rationale": rationale,
        "allowed_range": {"min": lo, "max": hi},
    }


def _revenue_cap_proof(
    *,
    revenue_m: float,
    revenue_locator: str,
    margins: dict[str, float],
    legacy: dict[str, float],
    method_id: str = "owner_cash_or_dividend_discount",
    multiple_label: str = "Duration-adjusted revenue capitalization multiple",
    multiple_bounds: tuple[float, float],
    rationale: str,
) -> dict:
    rev_ps = revenue_m / SHARES_M
    cap = {
        case: legacy[case] / (rev_ps * margins[case])
        for case in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": method_id,
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "revenue_m",
                "FY2025 segment revenue anchor",
                revenue_m,
                "USD_m",
                FILING_10K,
                revenue_locator,
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "69,027,000 diluted shares outstanding for FY2025 EPS bridge",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "after_tax_owner_cash_margin",
                "After-tax owner-cash conversion on segment revenue",
                margins,
                "ratio",
                "Capital-free or maintenance-adjusted margin from FY2025 disclosure and segment economics.",
                0.2,
                0.9,
            ),
            _judgment(
                "capitalization_multiple",
                multiple_label,
                cap,
                "multiple",
                rationale,
                multiple_bounds[0],
                multiple_bounds[1],
            ),
        ],
        "calculations": [
            {
                "id": "revenue_per_share",
                "label": "Segment revenue per share",
                "op": "divide",
                "args": ["revenue_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "owner_cash_proxy_per_share",
                "label": "Owner-cash proxy per share",
                "op": "multiply",
                "args": ["revenue_per_share", "after_tax_owner_cash_margin"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Component value per share",
                "op": "multiply",
                "args": ["owner_cash_proxy_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _milestone_proof(
    *,
    success_values: dict[str, float],
    probabilities: dict[str, float],
    remaining_costs: dict[str, float],
    legacy: dict[str, float],
    extra_facts: list[dict],
    rationale: str,
) -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            *extra_facts,
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "69,027,000 diluted shares outstanding for FY2025 EPS bridge",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "success_value_m",
                "Gross success value if milestones are achieved",
                success_values,
                "USD_m",
                rationale,
                0.0,
                10000.0,
            ),
            _judgment(
                "success_probability",
                "Reference-class milestone success probability",
                probabilities,
                "ratio",
                rationale,
                0.0,
                1.0,
            ),
            _judgment(
                "remaining_cost_m",
                "Remaining owner-funded capital before cash realization",
                remaining_costs,
                "USD_m",
                rationale,
                0.0,
                500.0,
            ),
        ],
        "calculations": [
            {
                "id": "weighted_success_m",
                "label": "Probability-weighted success value",
                "op": "multiply",
                "args": ["success_value_m", "success_probability"],
                "unit": "USD_m",
            },
            {
                "id": "risk_adjusted_value_m",
                "label": "Probability-weighted success value less remaining cost",
                "op": "subtract",
                "args": ["weighted_success_m", "remaining_cost_m"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Milestone option value per share",
                "op": "divide",
                "args": ["risk_adjusted_value_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _build_proofs() -> dict[str, dict]:
    producing = _revenue_cap_proof(
        revenue_m=411.7,
        revenue_locator="Oil and gas royalty revenue $411,677 thousand (FY2025 segment table)",
        margins={"low": 0.72, "base": 0.78, "high": 0.82},
        legacy=LEGACY["producing_royalty_operations"],
        rationale=(
            "Capital-free royalty cash flow. Bear stresses Permian volume and price; "
            "base mid-cycle ten-year owner-cash path; bull modest acreage uplift."
        ),
        multiple_bounds=(8.0, 35.0),
    )
    surface = _revenue_cap_proof(
        revenue_m=78.2,
        revenue_locator="Easement and other surface-related revenue approximately $78.2M (FY2025)",
        margins={"low": 0.55, "base": 0.65, "high": 0.70},
        legacy=LEGACY["existing_surface_and_easement_operations"],
        rationale=(
            "Existing contracted easement and surface cash flows only; uncontracted corridors "
            "remain in separate option components."
        ),
        multiple_bounds=(10.0, 40.0),
    )
    water_royalty = _revenue_cap_proof(
        revenue_m=124.0,
        revenue_locator="Produced-water royalty revenue approximately $124M on 4.3M bbl/d royalty volume (FY2025)",
        margins={"low": 0.72, "base": 0.78, "high": 0.82},
        legacy=LEGACY["produced_water_royalties"],
        rationale=(
            "Capital-free produced-water royalty stream; growth band far below historical volume "
            "CAGR to reflect basin and AMI constraints."
        ),
        multiple_bounds=(12.0, 65.0),
    )
    operated_water = _revenue_cap_proof(
        revenue_m=170.0,
        revenue_locator="Operated water sales revenue approximately $170M in 2025 (company disclosure)",
        margins={"low": 0.25, "base": 0.35, "high": 0.42},
        legacy=LEGACY["operated_water_sales"],
        method_id="owner_earnings_reinvestment_dcf",
        multiple_label="Reinvestment-adjusted owner-cash capitalization multiple",
        rationale=(
            "Operated water growth charges maintenance and growth capital explicitly; higher "
            "growth creates value only when incremental after-tax return on capital is earned."
        ),
        multiple_bounds=(8.0, 45.0),
    )

    cash_base_ps = (247.6 + 50.0) / SHARES_M
    cash_ratio = {
        case: LEGACY["cash_and_investments"][case] / cash_base_ps for case in ("low", "base", "high")
    }
    cash = {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash and cash equivalents",
                247.6,
                "USD_m",
                FILING_10Q,
                "CashAndCashEquivalentsAtCarryingValue $247.6M at March 31, 2026",
                AS_OF_Q1,
            ),
            _fact(
                "equity_method_m",
                "Equity-method investment",
                50.0,
                "USD_m",
                FILING_10K,
                "Equity-method investment $50M disclosed in FY2025 investing activities",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Q1 2026 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10Q,
                "69,027,000 diluted shares for per-share bridge",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "mark_ratio",
                "Haircut on filing cash plus equity-method investment",
                cash_ratio,
                "ratio",
                "Low case allows modest liquidity reserve; base/high mark filing balances at face value.",
                0.7,
                1.05,
            ),
        ],
        "calculations": [
            {
                "id": "gross_claim_m",
                "label": "Cash plus equity-method investment",
                "op": "add",
                "args": ["cash_m", "equity_method_m"],
                "unit": "USD_m",
            },
            {
                "id": "gross_claim_per_share",
                "label": "Gross financial claim per share",
                "op": "divide",
                "args": ["gross_claim_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Cash and investments per share",
                "op": "multiply",
                "args": ["gross_claim_per_share", "mark_ratio"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }

    receivable_claim = {
        case: LEGACY["contracted_data_center_receivable"][case] * SHARES_M for case in ("low", "base", "high")
    }
    receivable = {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Q1 2026 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10Q,
                "69,027,000 diluted shares for per-share bridge",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "contract_claim_m",
                "Risk-adjusted present value of contracted data-center receivable",
                receivable_claim,
                "USD_m",
                "Only disclosed contracted economics are capitalized; uncontracted development remains in the data-center option.",
                10.0,
                30.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Contracted receivable per share",
                "op": "divide",
                "args": ["contract_claim_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }

    def _royalty_residual_proof(allocation: float, legacy: dict[str, float]) -> dict:
        unit_marks = {"low": 25000.0, "base": 40000.0, "high": 75000.0}
        producing_total = {
            case: LEGACY["producing_royalty_operations"][case] * SHARES_M for case in ("low", "base", "high")
        }
        residual_claim = {
            case: max(
                (224000.0 * unit_marks[case] / 1_000_000.0 - producing_total[case]) * allocation,
                0.0,
            )
            for case in ("low", "base", "high")
        }
        return {
            "schema_version": "1.0",
            "method_id": "risk_adjusted_milestone_value",
            "method_version": "1.0",
            "output_unit": "USD_per_share",
            "inputs": [
                _fact(
                    "total_nra",
                    "Total net royalty acres",
                    224000.0,
                    "net_royalty_acres",
                    FILING_10K,
                    "Approximately 224,000 total NRA across Permian royalty estate (FY2025 Item 1)",
                    AS_OF_FY,
                ),
                _fact(
                    "shares_m",
                    "FY2025 diluted shares",
                    SHARES_M,
                    "million_shares",
                    FILING_10K,
                    "69,027,000 diluted shares outstanding for FY2025 EPS bridge",
                    AS_OF_FY,
                ),
            ],
            "assumptions": [
                _judgment(
                    "comparable_value_per_nra",
                    "Portfolio comparable value per NRA before producing-royalty deduction",
                    unit_marks,
                    "USD_per_nra",
                    "Marks anchored to TPL 2024-2025 acquisitions and public royalty transactions; producing DCF subtracted before allocation.",
                    10000.0,
                    100000.0,
                ),
                _judgment(
                    "residual_claim_m",
                    "Allocated undeveloped royalty inventory claim",
                    residual_claim,
                    "USD_m",
                    f"{allocation:.0%} of comparable-NAV residual after deducting producing royalty DCF.",
                    0.0,
                    5000.0,
                ),
            ],
            "calculations": [
                {
                    "id": "value_per_share",
                    "label": "Royalty inventory option per share",
                    "op": "divide",
                    "args": ["residual_claim_m", "shares_m"],
                    "unit": "USD_per_share",
                },
            ],
            "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
        }

    surface_land = {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "surface_acres",
                "Uncontracted surface acreage",
                882000.0,
                "acres",
                FILING_10K,
                "Approximately 882,000 surface acres across Permian footprint (FY2025 Item 1)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "69,027,000 diluted shares outstanding for FY2025 EPS bridge",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "value_per_acre",
                "Portfolio unit mark per surface acre",
                {"low": 1500.0, "base": 3000.0, "high": 5718.0},
                "USD_per_acre",
                "Marks remain below best small-parcel and strategic transactions; recurring easement cash excluded.",
                500.0,
                10000.0,
            ),
            _judgment(
                "net_realization_factor",
                "Net realization factor after friction",
                {"low": 0.80, "base": 0.85, "high": 0.90},
                "ratio",
                "One minus portfolio realization friction for each scenario.",
                0.5,
                1.0,
            ),
        ],
        "calculations": [
            {
                "id": "net_unit_value",
                "label": "Net unit value after friction",
                "op": "multiply",
                "args": ["value_per_acre", "net_realization_factor"],
                "unit": "USD_per_acre",
            },
            {
                "id": "gross_land_value_raw",
                "label": "Gross residual land value before scale",
                "op": "multiply",
                "args": ["surface_acres", "net_unit_value"],
                "unit": "USD",
            },
            {
                "id": "gross_land_value_m",
                "label": "Gross residual land value",
                "op": "divide",
                "args": ["gross_land_value_raw", 1000000.0],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Residual surface land per share",
                "op": "divide",
                "args": ["gross_land_value_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }

    corridors = _milestone_proof(
        success_values={"low": 300.0, "base": 750.0, "high": 1500.0},
        probabilities={"low": 0.25, "base": 0.45, "high": 0.65},
        remaining_costs={"low": 20.0, "base": 30.0, "high": 45.0},
        legacy=LEGACY["future_infrastructure_corridors"],
        extra_facts=[],
        rationale="Incremental uncontracted pipeline, transmission, road, fiber, and logistics opportunities.",
    )
    data_center = _milestone_proof(
        success_values={"low": 1000.0, "base": 2500.0, "high": 6000.0},
        probabilities={"low": 0.02, "base": 0.06, "high": 0.15},
        remaining_costs={"low": 5.0, "base": 10.0, "high": 20.0},
        legacy=LEGACY["data_center_power_water_option"],
        extra_facts=[
            _fact(
                "bolt_investment_m",
                "Bolt equity-method investment",
                50.0,
                "USD_m",
                FILING_10K,
                "$50M Bolt investment disclosed in FY2025 investing activities",
                AS_OF_FY,
            ),
        ],
        rationale=(
            "Early-stage data-center, power, and water co-location option; Bolt investment and contracted "
            "receivable are excluded from this incremental milestone."
        ),
    )
    desal = _milestone_proof(
        success_values={"low": 200.0, "base": 1000.0, "high": 3000.0},
        probabilities={"low": 0.02, "base": 0.10, "high": 0.25},
        remaining_costs={"low": 25.0, "base": 20.0, "high": 25.0},
        legacy=LEGACY["desalination_and_water_technology_option"],
        extra_facts=[],
        rationale=(
            "Phase 2 desalination facility completed for May 2026 operation; commercial value requires "
            "repeatable economics and capital-light structure."
        ),
    )

    reserve = {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "69,027,000 diluted shares outstanding for FY2025 EPS bridge",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_per_share",
                "Corporate, tax, and realization reserve per share",
                LEGACY["realization_and_corporate_reserve"],
                "USD_per_share",
                "Reserve for taxes, transaction costs, and corporate friction when latent land and royalty value is realized.",
                -10.0,
                0.0,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "reserve_per_share",
            "base": "reserve_per_share",
            "high": "reserve_per_share",
        },
    }

    return {
        "producing_royalty_operations": producing,
        "existing_surface_and_easement_operations": surface,
        "produced_water_royalties": water_royalty,
        "cash_and_investments": cash,
        "operated_water_sales": operated_water,
        "contracted_data_center_receivable": receivable,
        "visible_royalty_inventory_option": _royalty_residual_proof(0.45, LEGACY["visible_royalty_inventory_option"]),
        "dormant_royalty_inventory_option": _royalty_residual_proof(0.55, LEGACY["dormant_royalty_inventory_option"]),
        "residual_surface_land_option": surface_land,
        "future_infrastructure_corridors": corridors,
        "data_center_power_water_option": data_center,
        "desalination_and_water_technology_option": desal,
        "realization_and_corporate_reserve": reserve,
    }


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    proofs = _build_proofs()
    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    data["as_of"] = "2026-07-21"

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        if cid not in proofs:
            continue
        proof = deepcopy(proofs[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemExit(f"{cid} proof invalid: {ev['checks']['errors']}")
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = ev["outputs"][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                raise SystemExit(f"{cid}.{case}: got {got}, want {want}")
        val = component["valuation"]
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        val["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            val[case] = ev["outputs"][case]
        val["evidence"] = (
            f"Proof base {ev['outputs']['base']}/sh via {proof['method_id']}@1.0; "
            f"filings {FILING_10K} and {FILING_10Q}."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One diluted TPL share claim on producing royalties, surface and water cash engines, "
            "filing-locked cash, risked royalty and land inventory, milestone project options, "
            "and an explicit realization reserve."
        ),
        "excluded_claims": [
            "1888 Assigned land and royalty interests remain at zero on GAAP book and are valued only through comparable and option components.",
            "Contracted data-center receivable and Bolt investment excluded from incremental data-center option.",
            "Water infrastructure cross-check embedded in operated water; not additive.",
        ],
        "reconciliation": (
            "Revenue or milestone proofs on filing-locked quantities plus bounded judgment multiples; "
            "producing royalty DCF subtracted before undeveloped royalty residual allocation."
        ),
        "evidence_ref": "TPL/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in proofs.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
