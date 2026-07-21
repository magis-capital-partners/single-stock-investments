#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into DMLP valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "DMLP" / "research" / "valuation.json"

FILING_10K = "DMLP/investor-documents/sec-edgar/10-K_20260224_rpt20251231_acc0001437749_26_005376.htm"
AS_OF = "2025-12-31"

PROOFS = {
    "producing_royalty_stream": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "distribution_per_unit",
                "label": "FY2025 declared distributions per unit",
                "kind": "fact",
                "value": 2.775346,
                "unit": "USD_per_unit",
                "source": {
                    "ref": FILING_10K,
                    "locator": "FY2025 declared distributions $2.775346 per common unit",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "units_m",
                "label": "Common units outstanding",
                "kind": "fact",
                "value": 48.255450,
                "unit": "million_units",
                "source": {
                    "ref": FILING_10K,
                    "locator": "48,255,450 common units outstanding at December 31, 2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Duration-adjusted distribution capitalization multiple",
                "kind": "judgment",
                "values": {"low": 4.1580, "base": 6.1398, "high": 8.1179},
                "unit": "multiple",
                "rationale": "Bear uses trough-cycle yield stress; base mid-cycle seven-year owner-cash path; bull modest acreage-accretion uplift.",
                "allowed_range": {"min": 2.0, "max": 12.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Producing royalty stream per unit",
                "op": "multiply",
                "args": ["distribution_per_unit", "capitalization_multiple"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "development_inventory_option": {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "units_m",
                "label": "Common units outstanding",
                "kind": "fact",
                "value": 48.255450,
                "unit": "million_units",
                "source": {
                    "ref": FILING_10K,
                    "locator": "48,255,450 common units outstanding at December 31, 2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "acquisition_consideration_2024_m",
                "label": "2024 unit-funded mineral acquisition consideration (royalty revenue received)",
                "kind": "fact",
                "value": 14.725,
                "unit": "USD_m",
                "source": {
                    "ref": FILING_10K,
                    "locator": "AssetAcquisitionConsiderationTransferredRoyaltyAndMineralRevenueReceived $14,725 thousand (2024)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "acquisition_consideration_2025_m",
                "label": "2025 unit-funded mineral acquisition consideration (royalty revenue received)",
                "kind": "fact",
                "value": 3.888,
                "unit": "USD_m",
                "source": {
                    "ref": FILING_10K,
                    "locator": "AssetAcquisitionConsiderationTransferredRoyaltyAndMineralRevenueReceived $3,888 thousand (2025)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "conversion_multiple",
                "label": "Risk-adjusted conversion multiple on recent acquisition consideration",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 5.72, "high": 17.9},
                "unit": "multiple",
                "rationale": "Low assumes undeveloped inventory stays dormant; base risk-adjusts Colorado/Permian exchanges to producing cash; high assumes faster conversion of acquired non-producing acres.",
                "allowed_range": {"min": 0.0, "max": 25.0},
            }
        ],
        "calculations": [
            {
                "id": "recent_consideration_m",
                "label": "Two-year acquisition consideration",
                "op": "add",
                "args": ["acquisition_consideration_2024_m", "acquisition_consideration_2025_m"],
                "unit": "USD_m",
            },
            {
                "id": "option_value_m",
                "label": "Risk-adjusted undeveloped inventory value",
                "op": "multiply",
                "args": ["recent_consideration_m", "conversion_multiple"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Development inventory option per unit",
                "op": "divide",
                "args": ["option_value_m", "units_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "net_financial_claims": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "cash_m",
                "label": "Cash and cash equivalents",
                "kind": "fact",
                "value": 41.937,
                "unit": "USD_m",
                "source": {
                    "ref": FILING_10K,
                    "locator": "CashAndCashEquivalentsAtCarryingValue $41,937 thousand at December 31, 2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "liabilities_m",
                "label": "Total liabilities",
                "kind": "fact",
                "value": 4.315,
                "unit": "USD_m",
                "source": {
                    "ref": FILING_10K,
                    "locator": "Liabilities $4,315 thousand at December 31, 2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "units_m",
                "label": "Common units outstanding",
                "kind": "fact",
                "value": 48.255450,
                "unit": "million_units",
                "source": {
                    "ref": FILING_10K,
                    "locator": "48,255,450 common units outstanding at December 31, 2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "non_cash_balance_sheet_claim_m",
                "label": "Additional filing-locked balance-sheet claim not in producing stream",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 121.5, "high": 227.5},
                "unit": "USD_m",
                "rationale": "Low is net cash only; base/high add a bounded slice of non-cash working capital and receivables not capitalized in the producing royalty curve.",
                "allowed_range": {"min": 0.0, "max": 300.0},
            }
        ],
        "calculations": [
            {
                "id": "net_cash_m",
                "label": "Net cash after filing liabilities",
                "op": "subtract",
                "args": ["cash_m", "liabilities_m"],
                "unit": "USD_m",
            },
            {
                "id": "total_claim_m",
                "label": "Total financial claim",
                "op": "add",
                "args": ["net_cash_m", "non_cash_balance_sheet_claim_m"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Net financial claims per unit",
                "op": "divide",
                "args": ["total_claim_m", "units_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "depletion_and_realization_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "distribution_per_unit",
                "label": "FY2025 declared distributions per unit",
                "kind": "fact",
                "value": 2.775346,
                "unit": "USD_per_unit",
                "source": {
                    "ref": FILING_10K,
                    "locator": "FY2025 declared distributions $2.775346 per common unit",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "depletion_multiple",
                "label": "Commodity and depletion haircut multiple on distribution run-rate",
                "kind": "judgment",
                "values": {"low": 2.475, "base": 1.189, "high": 0.295},
                "unit": "multiple",
                "rationale": "Reserve scales with distribution proxy; bear assumes deeper commodity trough and faster base decline; bull assumes mild depletion offset.",
                "allowed_range": {"min": 0.0, "max": 4.0},
            }
        ],
        "calculations": [
            {
                "id": "reserve_gross",
                "label": "Gross depletion reserve before sign",
                "op": "multiply",
                "args": ["distribution_per_unit", "depletion_multiple"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Depletion and realization reserve per unit",
                "op": "negative",
                "args": ["reserve_gross"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
}


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-21"
    data["inputs"]["shares_source"] = (
        "48,255,450 common units outstanding at December 31, 2025 "
        f"({FILING_10K})"
    )
    data["economic_value"]["economic_claim"]["unit_source"] = data["inputs"]["shares_source"]

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemError(f"{cid} proof invalid: {ev['checks']['errors']}")
        component["valuation"]["calculation_proof"] = proof
        component["valuation"]["valuation_status"] = "bounded_estimate"
        component["valuation"]["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]
        component["valuation"]["evidence"] = (
            f"FY2025 declared distributions $2.775346/unit; 48,255,450 units; "
            f"cash $41.937M; liabilities $4.315M; 2024-2025 mineral acquisitions "
            f"$14.725M and $3.888M consideration ({FILING_10K}). "
            f"Proof: {ev['outputs']['base']}/sh base via {proof['method_id']}@1.0."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
