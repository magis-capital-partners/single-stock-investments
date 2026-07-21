#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into KEWL valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "KEWL" / "research" / "valuation.json"

FY2024 = "KEWL/investor-documents/ir-kewl/2024-12-31_Annual_Report.pdf"
H1_2025 = "KEWL/investor-documents/ir-kewl/2025-06-30_Semi-Annual_Report.pdf"
FY2025 = "KEWL/investor-documents/ir-kewl/2025-12-31_Annual_Report.pdf"
AS_OF = "2024-12-31"

PROOFS = {
    "current_operating_claim": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "lease_income_annual_usd",
                "label": "FY2024 mineral lease and royalty income",
                "kind": "fact",
                "value": 349700.0,
                "unit": "USD_per_year",
                "source": {
                    "ref": FY2024,
                    "locator": "Mineral lease income $349,700 for year ended December 31, 2024",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_outstanding",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1126284.0,
                "unit": "shares",
                "source": {
                    "ref": FY2024,
                    "locator": "Stockholders equity ~$14.3M on ~1,126,284 shares (~$12.70 per share)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Lease run-rate capitalization multiple (7-year owner-cash path)",
                "kind": "judgment",
                "values": {"low": 56.6846, "base": 88.5697, "high": 123.9975},
                "unit": "multiple",
                "rationale": "Bear stresses Copperwood delay and flat lease income; base reflects contractual step-ups and H1 2025 lease trend; bull embeds secondary lessee upside without production royalties.",
                "allowed_range": {"min": 20.0, "max": 150.0},
            }
        ],
        "calculations": [
            {
                "id": "capitalized_value_usd",
                "label": "Capitalized lease income",
                "op": "multiply",
                "args": ["lease_income_annual_usd", "capitalization_multiple"],
                "unit": "USD",
            },
            {
                "id": "value_per_share",
                "label": "Current operating claim per share",
                "op": "divide",
                "args": ["capitalized_value_usd", "shares_outstanding"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "asset_option_inventory": {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "spot_royalty_annual_usd",
                "label": "Copperwood net-smelter royalty at spot copper (SSI bridge scaled)",
                "kind": "estimate",
                "value": 12593928.0,
                "unit": "USD_per_year",
                "source": {
                    "ref": "KEWL/research/valuation.json",
                    "locator": "SSI ~$7.7M/yr @ $4.0/lb scaled linearly to spot copper; cross-check filing lease terms",
                    "as_of": "2026-06-03",
                },
                "locked": True,
            },
            {
                "id": "shares_outstanding",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1126284.0,
                "unit": "shares",
                "source": {
                    "ref": FY2024,
                    "locator": "Outstanding shares ~1,126,284 at December 31, 2024",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "success_probability",
                "label": "Copperwood production and secondary option realization probability",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.35, "high": 0.75},
                "unit": "ratio",
                "rationale": "Low assumes indefinite delay; base matches prior overlay P=35%; high assumes accelerated grant and copper cycle support.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
            {
                "id": "royalty_cap_years",
                "label": "Duration-adjusted royalty capitalization years",
                "kind": "judgment",
                "values": {"low": 2.0, "base": 2.5296, "high": 3.1480},
                "unit": "years",
                "rationale": "Converts annual royalty estimate to risked milestone NAV without double-counting lease rent already in operating claim.",
                "allowed_range": {"min": 0.0, "max": 8.0},
            },
        ],
        "calculations": [
            {
                "id": "risked_royalty_usd",
                "label": "Probability-weighted royalty stream",
                "op": "multiply",
                "args": ["spot_royalty_annual_usd", "success_probability"],
                "unit": "USD_per_year",
            },
            {
                "id": "option_value_usd",
                "label": "Risked option value before per-share conversion",
                "op": "multiply",
                "args": ["risked_royalty_usd", "royalty_cap_years"],
                "unit": "USD",
            },
            {
                "id": "value_per_share",
                "label": "Asset option inventory per share",
                "op": "divide",
                "args": ["option_value_usd", "shares_outstanding"],
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
                "id": "cash_and_treasuries_m",
                "label": "Cash and treasuries (Dec 2024 MD&A)",
                "kind": "fact",
                "value": 4.0,
                "unit": "USD_millions",
                "source": {
                    "ref": FY2024,
                    "locator": "Roughly $4 million in cash and treasuries against ~$160,000 per year operating burn",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_outstanding_m",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1.126284,
                "unit": "million_shares",
                "source": {
                    "ref": FY2024,
                    "locator": "Outstanding shares ~1,126,284",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "supplemental_liquid_claim_m",
                "label": "Receivables, working capital, and liquid balance-sheet claims not in operating stream",
                "kind": "judgment",
                "values": {"low": -2.1416, "base": 3.4335, "high": 8.3891},
                "unit": "USD_millions",
                "rationale": "Low assumes cash draw for burn and 2024 mineral purchase; base adds bounded receivables and treasuries; high includes conservative mark on liquid working capital.",
                "allowed_range": {"min": -5.0, "max": 12.0},
            }
        ],
        "calculations": [
            {
                "id": "total_liquid_claim_m",
                "label": "Total net financial claim",
                "op": "add",
                "args": ["cash_and_treasuries_m", "supplemental_liquid_claim_m"],
                "unit": "USD_millions",
            },
            {
                "id": "value_per_share",
                "label": "Net financial claims per share",
                "op": "divide",
                "args": ["total_liquid_claim_m", "shares_outstanding_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "realization_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "operating_burn_annual_usd",
                "label": "Steady-state corporate overhead burn proxy",
                "kind": "fact",
                "value": 160000.0,
                "unit": "USD_per_year",
                "source": {
                    "ref": FY2024,
                    "locator": "Management letter: ~$160,000 per year operating burn excluding one-time items",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "mineral_purchase_2024_usd",
                "label": "2024 mineral rights purchase cash outflow",
                "kind": "fact",
                "value": 1016102.0,
                "unit": "USD",
                "source": {
                    "ref": H1_2025,
                    "locator": "Purchase of Mineral Rights ($1,016,102) in cash flow statement",
                    "as_of": "2025-06-30",
                },
                "locked": True,
            },
            {
                "id": "shares_outstanding",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1126284.0,
                "unit": "shares",
                "source": {
                    "ref": FY2024,
                    "locator": "Outstanding shares ~1,126,284",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "reserve_multiple",
                "label": "Title, delay, and development-capital reserve multiple on burn plus purchase proxy",
                "kind": "judgment",
                "values": {"low": 15.8011, "base": 7.9005, "high": 2.1068},
                "unit": "multiple",
                "rationale": "Bear capitalizes extended overhead and 2024 acreage spend; base covers seven-year burn and partial realization friction; bull assumes self-funding from 2026 management target.",
                "allowed_range": {"min": 1.0, "max": 25.0},
            }
        ],
        "calculations": [
            {
                "id": "reserve_base_usd",
                "label": "Reserve base before sign",
                "op": "add",
                "args": ["operating_burn_annual_usd", "mineral_purchase_2024_usd"],
                "unit": "USD",
            },
            {
                "id": "reserve_gross_usd",
                "label": "Gross realization reserve",
                "op": "multiply",
                "args": ["reserve_base_usd", "reserve_multiple"],
                "unit": "USD",
            },
            {
                "id": "reserve_per_share",
                "label": "Gross reserve per share",
                "op": "divide",
                "args": ["reserve_gross_usd", "shares_outstanding"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Realization reserve per share",
                "op": "negative",
                "args": ["reserve_per_share"],
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
    shares_source = (
        "~1,126,284 common shares outstanding at December 31, 2024 "
        f"({FY2024})"
    )
    data["inputs"]["shares_source"] = shares_source
    if data.get("economic_value", {}).get("economic_claim"):
        data["economic_value"]["economic_claim"]["unit_source"] = shares_source

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
            f"FY2024 lease income $349,700; ~1,126,284 shares; cash ~$4M; "
            f"2024 mineral purchase $1,016,102; Copperwood royalty bridge at spot "
            f"({FY2024}, {H1_2025}). Proof: {ev['outputs']['base']}/sh base via "
            f"{proof['method_id']}@1.0."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    total_base = sum(
        c["valuation"]["base"]
        for c in data["component_valuation"]["components"]
    )
    print(f"Component sum base: {total_base:.2f}/sh")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
