#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into KEWL valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "KEWL" / "research" / "valuation.json"

FY2025_ANNUAL = "KEWL/investor-documents/ir-kewl/2025-12-31_Annual_Report.pdf"
FY2024_ANNUAL = "KEWL/investor-documents/ir-kewl/2024-12-31_Annual_Report.pdf"
H1_2025_SEMI = "KEWL/investor-documents/ir-kewl/2025-06-30_Semi-Annual_Report.pdf"
AS_OF = "2025-12-31"

PROOFS = {
    "current_operating_claim": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "lease_income_annual",
                "label": "Mineral lease income run-rate",
                "kind": "estimate",
                "value": 365000,
                "unit": "USD",
                "source": {
                    "ref": H1_2025_SEMI,
                    "locator": "H1 2025 mineral lease income $189,101 vs $149,310 prior year; annualized ~$365K",
                    "as_of": "2025-06-30",
                },
            },
            {
                "id": "shares",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1126284,
                "unit": "shares",
                "source": {
                    "ref": FY2025_ANNUAL,
                    "locator": "1,126,284 shares outstanding as of 12/31/2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Duration-adjusted lease-income capitalization multiple",
                "kind": "judgment",
                "values": {"low": 54.3085, "base": 84.857, "high": 118.7998},
                "unit": "multiple",
                "rationale": "Bear stresses Copperwood delay and flat lease income; base capitalizes normalized lease run-rate with modest growth optionality; bull assumes secondary lessee uplift.",
                "allowed_range": {"min": 20.0, "max": 150.0},
            }
        ],
        "calculations": [
            {
                "id": "lease_income_per_share",
                "label": "Annual lease income per share",
                "op": "divide",
                "args": ["lease_income_annual", "shares"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Existing lease and mineral-rights cash flows per share",
                "op": "multiply",
                "args": ["lease_income_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "asset_option_inventory": {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "shares_m",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1.126284,
                "unit": "million_shares",
                "source": {
                    "ref": FY2025_ANNUAL,
                    "locator": "1,126,284 shares outstanding as of 12/31/2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "ssi_royalty_ref_m",
                "label": "Copperwood royalty reference at $4/lb copper",
                "kind": "estimate",
                "value": 7.7,
                "unit": "USD_m",
                "source": {
                    "ref": "KEWL/third-party-analyses/references.md",
                    "locator": "SSI May 2024 mineral-floor framing; ~$7.7M/yr at $4/lb copper [Assumption pending production]",
                    "as_of": "2024-05-01",
                },
            },
        ],
        "assumptions": [
            {
                "id": "copper_price_scale",
                "label": "Copper price scale vs SSI $4/lb reference",
                "kind": "judgment",
                "values": {"low": 0.5, "base": 1.635575, "high": 2.0},
                "unit": "ratio",
                "rationale": "Base uses spot copper ~$6.54/lb vs SSI $4/lb reference; bear uses trough copper; bull uses sustained higher copper.",
                "allowed_range": {"min": 0.0, "max": 3.0},
            },
            {
                "id": "success_probability",
                "label": "Probability Copperwood reaches production royalty",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.35, "high": 0.65},
                "unit": "fraction",
                "rationale": "Low assumes project delay or failure; base matches Lawrence overlay P=35%; high assumes grant/acceleration path.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
            {
                "id": "acreage_option_m",
                "label": "Secondary acreage and water-development option value",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 6.742337, "high": 19.72},
                "unit": "USD_m",
                "rationale": "667K-acre expansion and non-Copperwood leases; low zeroes undeveloped option; high assumes secondary lessee.",
                "allowed_range": {"min": 0.0, "max": 30.0},
            },
        ],
        "calculations": [
            {
                "id": "spot_royalty_m",
                "label": "Scaled Copperwood royalty at copper price",
                "op": "multiply",
                "args": ["ssi_royalty_ref_m", "copper_price_scale"],
                "unit": "USD_m",
            },
            {
                "id": "risked_royalty_m",
                "label": "Probability-weighted production royalty",
                "op": "multiply",
                "args": ["spot_royalty_m", "success_probability"],
                "unit": "USD_m",
            },
            {
                "id": "total_option_m",
                "label": "Total copper, land, and water option value",
                "op": "add",
                "args": ["risked_royalty_m", "acreage_option_m"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Copper, land, and water options per share",
                "op": "divide",
                "args": ["total_option_m", "shares_m"],
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
                "id": "shareholders_equity_m",
                "label": "Shareholders equity",
                "kind": "estimate",
                "value": 14.3,
                "unit": "USD_m",
                "source": {
                    "ref": FY2024_ANNUAL,
                    "locator": "Book value ~$14.3 million (~$12.70 per share) at December 2024",
                    "as_of": "2024-12-31",
                },
            },
            {
                "id": "shares_m",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1.126284,
                "unit": "million_shares",
                "source": {
                    "ref": FY2025_ANNUAL,
                    "locator": "1,126,284 shares outstanding as of 12/31/2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "equity_claim_fraction",
                "label": "Fraction of GAAP equity attributable to net financial claims (cash, treasuries, non-operating)",
                "kind": "judgment",
                "values": {"low": 0.1299558, "base": 0.5198234, "high": 0.8663723},
                "unit": "fraction",
                "rationale": "Operating and option components own mineral cash flows and Copperwood upside; this slice captures cash/treasury and non-operating book without double-counting.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            }
        ],
        "calculations": [
            {
                "id": "equity_per_share",
                "label": "GAAP equity per share",
                "op": "divide",
                "args": ["shareholders_equity_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Cash and other net claims per share",
                "op": "multiply",
                "args": ["equity_per_share", "equity_claim_fraction"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "realization_reserve": {
        "schema_version": "1.0",
        "method_id": "realization_reserve",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "operating_burn_annual",
                "label": "Annual corporate operating burn excluding one-offs",
                "kind": "estimate",
                "value": 160000,
                "unit": "USD",
                "source": {
                    "ref": FY2024_ANNUAL,
                    "locator": "FY2024 MD&A; ~$160K/yr operating burn ex one-time items",
                    "as_of": "2024-12-31",
                },
            },
            {
                "id": "shares",
                "label": "Common shares outstanding",
                "kind": "fact",
                "value": 1126284,
                "unit": "shares",
                "source": {
                    "ref": FY2025_ANNUAL,
                    "locator": "1,126,284 shares outstanding as of 12/31/2025",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "reserve_multiple",
                "label": "Title, realization, and development-capital reserve multiple on burn proxy",
                "kind": "judgment",
                "values": {"low": 116.148, "base": 58.074, "high": 15.4864},
                "unit": "multiple",
                "rationale": "Bear assumes prolonged overhead, title friction, and dilution; base reserves seven-year realization drag; bull assumes self-sustaining ops from 2026.",
                "allowed_range": {"min": 5.0, "max": 150.0},
            }
        ],
        "calculations": [
            {
                "id": "burn_per_share",
                "label": "Annual operating burn per share",
                "op": "divide",
                "args": ["operating_burn_annual", "shares"],
                "unit": "USD_per_share",
            },
            {
                "id": "reserve_gross",
                "label": "Gross realization reserve before sign",
                "op": "multiply",
                "args": ["burn_per_share", "reserve_multiple"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Title, realization, and development-capital reserve per share",
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
    data["as_of"] = "2026-07-23"
    shares_source = f"1,126,284 shares outstanding as of 12/31/2025 ({FY2025_ANNUAL})"
    data["inputs"]["shares_source"] = shares_source
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
        component["valuation"]["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )
        component["valuation"]["evidence"] = (
            f"FY2025 annual: 1,126,284 shares; >1.3M mineral acres; 36,705 leased acres. "
            f"FY2024: book ~$14.3M (~$12.70/sh); mineral lease income ~$349.7K; "
            f"~$160K/yr operating burn. H1 2025 lease income $189K vs $149K prior year. "
            f"Proof: {ev['outputs']['base']}/sh base via {proof['method_id']}@1.0."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
