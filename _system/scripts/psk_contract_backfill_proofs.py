#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into PSK.TO valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "PSK.TO" / "research" / "valuation.json"

FY2025_MDA = "PSK.TO/official-reports/PSK-2025-YE-MDA.pdf"
Q1_2026_MDA = "PSK.TO/official-reports/2026-Q1-MDA-FINAL.pdf"
Q1_2026_FS = "PSK.TO/official-reports/2026-Q1-Financial-Statements-FINAL.pdf"
AS_OF = "2026-03-31"

PROOFS = {
    "producing_royalty_stream": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "CAD_per_share",
        "inputs": [
            {
                "id": "ffo_per_share",
                "label": "FY2025 funds from operations per share",
                "kind": "fact",
                "value": 1.5,
                "unit": "CAD_per_share",
                "source": {
                    "ref": FY2025_MDA,
                    "locator": "FY2025 funds from operations $353.0M ($1.50 per share)",
                    "as_of": "2025-12-31",
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 232.4,
                "unit": "million_shares",
                "source": {
                    "ref": Q1_2026_MDA,
                    "locator": "232.4 million shares outstanding Q1 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Duration-adjusted FFO capitalization multiple",
                "kind": "judgment",
                "values": {"low": 9.6467, "base": 14.2467, "high": 18.84},
                "unit": "multiple",
                "rationale": "Bear uses trough-cycle yield stress on FY2025 FFO; base mid-cycle seven-year owner-cash path; bull modest play-level volume uplift without Q1 2026 peak run-rate.",
                "allowed_range": {"min": 4.0, "max": 25.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Producing royalty stream per share",
                "op": "multiply",
                "args": ["ffo_per_share", "capitalization_multiple"],
                "unit": "CAD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "development_inventory_option": {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "CAD_per_share",
        "inputs": [
            {
                "id": "ee_assets_m",
                "label": "Exploration and evaluation assets",
                "kind": "fact",
                "value": 1468.0,
                "unit": "CAD_m",
                "source": {
                    "ref": Q1_2026_FS,
                    "locator": "Exploration and evaluation assets $1,468M March 31, 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 232.4,
                "unit": "million_shares",
                "source": {
                    "ref": Q1_2026_MDA,
                    "locator": "232.4 million shares outstanding Q1 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "q1_lease_bonus_m",
                "label": "Q1 2026 lease issuance bonus consideration",
                "kind": "fact",
                "value": 12.3,
                "unit": "CAD_m",
                "source": {
                    "ref": Q1_2026_MDA,
                    "locator": "Lease bonus consideration $12.3M (48 new leases) Q1 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "risk_fraction",
                "label": "Risk-adjusted fraction of E&E book for undeveloped fee-land option",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.436921, "high": 1.365},
                "unit": "fraction",
                "rationale": "Low assumes dormant inventory; base risk-adjusts filed E&E to milestone option value; high assumes faster Clearwater/Duvernay/Mannville conversion.",
                "allowed_range": {"min": 0.0, "max": 2.0},
            }
        ],
        "calculations": [
            {
                "id": "option_value_m",
                "label": "Risk-adjusted undeveloped inventory value",
                "op": "multiply",
                "args": ["ee_assets_m", "risk_fraction"],
                "unit": "CAD_m",
            },
            {
                "id": "value_per_share",
                "label": "Development inventory option per share",
                "op": "divide",
                "args": ["option_value_m", "shares_m"],
                "unit": "CAD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "net_financial_claims": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "CAD_per_share",
        "inputs": [
            {
                "id": "shareholders_equity_m",
                "label": "Shareholders equity",
                "kind": "fact",
                "value": 2528.0,
                "unit": "CAD_m",
                "source": {
                    "ref": Q1_2026_FS,
                    "locator": "Shareholders equity $2,528M March 31, 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "net_debt_m",
                "label": "Net debt",
                "kind": "fact",
                "value": 257.7,
                "unit": "CAD_m",
                "source": {
                    "ref": Q1_2026_MDA,
                    "locator": "Net debt $257.7M Q1 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": 232.4,
                "unit": "million_shares",
                "source": {
                    "ref": Q1_2026_MDA,
                    "locator": "232.4 million shares outstanding Q1 2026",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "equity_claim_fraction",
                "label": "Fraction of net equity counted as additive financial claim",
                "kind": "judgment",
                "values": {"low": 0.105, "base": 0.424, "high": 0.705},
                "unit": "fraction",
                "rationale": "Operating royalty stream owns producing cash; this component captures bounded balance-sheet cushion after net debt without double-counting E&E option.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            }
        ],
        "calculations": [
            {
                "id": "net_equity_m",
                "label": "Shareholders equity less net debt",
                "op": "subtract",
                "args": ["shareholders_equity_m", "net_debt_m"],
                "unit": "CAD_m",
            },
            {
                "id": "net_equity_per_share",
                "label": "Net equity per share before fraction",
                "op": "divide",
                "args": ["net_equity_m", "shares_m"],
                "unit": "CAD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Net financial claims per share",
                "op": "multiply",
                "args": ["net_equity_per_share", "equity_claim_fraction"],
                "unit": "CAD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "depletion_and_realization_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "CAD_per_share",
        "inputs": [
            {
                "id": "ffo_per_share",
                "label": "FY2025 funds from operations per share",
                "kind": "fact",
                "value": 1.5,
                "unit": "CAD_per_share",
                "source": {
                    "ref": FY2025_MDA,
                    "locator": "FY2025 funds from operations $353.0M ($1.50 per share)",
                    "as_of": "2025-12-31",
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "depletion_multiple",
                "label": "Commodity, depletion, and realization haircut multiple on FFO run-rate",
                "kind": "judgment",
                "values": {"low": 5.7467, "base": 2.76, "high": 0.6867},
                "unit": "multiple",
                "rationale": "Reserve scales with owner-cash proxy; bear assumes deeper commodity trough and faster base decline; bull assumes mild depletion offset.",
                "allowed_range": {"min": 0.0, "max": 8.0},
            }
        ],
        "calculations": [
            {
                "id": "reserve_gross",
                "label": "Gross depletion reserve before sign",
                "op": "multiply",
                "args": ["ffo_per_share", "depletion_multiple"],
                "unit": "CAD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Depletion and realization reserve per share",
                "op": "negative",
                "args": ["reserve_gross"],
                "unit": "CAD_per_share",
            }
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
        "232.4 million shares outstanding Q1 2026 "
        f"({Q1_2026_MDA})"
    )
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
        component["valuation"]["evidence"] = (
            f"FY2025 FFO $1.50/sh; Q1 2026 net debt $257.7M; shareholders equity $2,528M; "
            f"E&E assets $1,468M; Q1 2026 lease bonus $12.3M; 232.4M shares "
            f"({FY2025_MDA}; {Q1_2026_MDA}; {Q1_2026_FS}). "
            f"Proof: {ev['outputs']['base']}/sh base via {proof['method_id']}@1.0."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
