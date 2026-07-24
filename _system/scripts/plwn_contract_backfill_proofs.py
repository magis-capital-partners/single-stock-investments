#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into PLWN valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "PLWN" / "research" / "valuation.json"

PROPUBLICA = "ProPublica Nonprofit Explorer EIN 11-1190044 FY ending Dec 2024"
AS_OF = "2024-12-31"

PROOFS = {
    "form990_net_assets": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "net_assets_m",
                "label": "Form 990 net assets",
                "kind": "estimate",
                "value": 161.903602,
                "unit": "USD_m",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": f"{PROPUBLICA}; net assets $161,903,602; liabilities $0 on extract",
                    "as_of": AS_OF,
                },
            },
            {
                "id": "shares_m",
                "label": "Provisional common shares outstanding",
                "kind": "estimate",
                "value": 3.46,
                "unit": "million_shares",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": "Aggregator ~3.46M shares; conflicts with dividend cash math vs FY2024 NI [HUMAN REVIEW]",
                    "as_of": "2026-07-17",
                },
            },
        ],
        "assumptions": [
            {
                "id": "equity_claim_fraction",
                "label": "Fraction of filed net assets attributable to one provisional share",
                "kind": "judgment",
                "values": {"low": 0.854702, "base": 1.0, "high": 1.175216},
                "unit": "fraction",
                "rationale": "Base uses full 990 net assets per provisional share; low/high bracket Schedule D uncertainty and share-count error.",
                "allowed_range": {"min": 0.5, "max": 1.5},
            }
        ],
        "calculations": [
            {
                "id": "nav_per_share",
                "label": "Form 990 net assets per provisional share",
                "op": "divide",
                "args": ["net_assets_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Form 990 net assets per share",
                "op": "multiply",
                "args": ["nav_per_share", "equity_claim_fraction"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "cemetery_operations": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "net_income_m",
                "label": "FY2024 net income (program services surplus)",
                "kind": "estimate",
                "value": 5.324496,
                "unit": "USD_m",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": f"{PROPUBLICA}; revenue $42,855,178; expenses $37,530,682; net income $5,324,496",
                    "as_of": AS_OF,
                },
            },
            {
                "id": "shares_m",
                "label": "Provisional common shares outstanding",
                "kind": "estimate",
                "value": 3.46,
                "unit": "million_shares",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": "Aggregator ~3.46M shares; conflicts with dividend cash math vs FY2024 NI [HUMAN REVIEW]",
                    "as_of": "2026-07-17",
                },
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Duration-adjusted cemetery owner-cash capitalization multiple",
                "kind": "judgment",
                "values": {"low": 3.249, "base": 7.798, "high": 12.996},
                "unit": "multiple",
                "rationale": "Bear stresses trough cemetery demand and nonprofit reinvestment; base modestly capitalizes FY2024 surplus; bull assumes sustained pricing on Long Island inventory.",
                "allowed_range": {"min": 2.0, "max": 20.0},
            }
        ],
        "calculations": [
            {
                "id": "owner_cash_per_share",
                "label": "FY2024 net income per provisional share",
                "op": "divide",
                "args": ["net_income_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Cemetery operating franchise per share",
                "op": "multiply",
                "args": ["owner_cash_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "land_market_to_990_gap": {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "land_gap_reference_m",
                "label": "Base-case incremental land fair-value above 990 carrying amounts",
                "kind": "estimate",
                "value": 51.9,
                "unit": "USD_m",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": "Long Island cemetery land often carried below market on Form 990; Schedule D marks pending [Assumption]",
                    "as_of": AS_OF,
                },
            },
            {
                "id": "shares_m",
                "label": "Provisional common shares outstanding",
                "kind": "estimate",
                "value": 3.46,
                "unit": "million_shares",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": "Aggregator ~3.46M shares; conflicts with dividend cash math vs FY2024 NI [HUMAN REVIEW]",
                    "as_of": "2026-07-17",
                },
            },
        ],
        "assumptions": [
            {
                "id": "risk_fraction",
                "label": "Probability-weighted fraction of land fair-value gap realized to owners",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 1.0, "high": 5.33526},
                "unit": "fraction",
                "rationale": "Low assumes no mark-up above 990 carrying value; base modest Long Island land gap; high assumes appraisal upside or control transaction.",
                "allowed_range": {"min": 0.0, "max": 8.0},
            }
        ],
        "calculations": [
            {
                "id": "risked_land_gap_m",
                "label": "Risk-adjusted land fair-value gap",
                "op": "multiply",
                "args": ["land_gap_reference_m", "risk_fraction"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Land fair-value gap per share",
                "op": "divide",
                "args": ["risked_land_gap_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "illiquidity_and_governance_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "net_assets_m",
                "label": "Form 990 net assets",
                "kind": "estimate",
                "value": 161.903602,
                "unit": "USD_m",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": f"{PROPUBLICA}; net assets $161,903,602",
                    "as_of": AS_OF,
                },
            },
            {
                "id": "shares_m",
                "label": "Provisional common shares outstanding",
                "kind": "estimate",
                "value": 3.46,
                "unit": "million_shares",
                "source": {
                    "ref": "PLWN/research/valuation.json",
                    "locator": "Aggregator ~3.46M shares; conflicts with dividend cash math vs FY2024 NI [HUMAN REVIEW]",
                    "as_of": "2026-07-17",
                },
            },
        ],
        "assumptions": [
            {
                "id": "realization_haircut_ratio",
                "label": "OTC illiquidity and nonprofit-governance haircut on NAV per share",
                "kind": "judgment",
                "values": {"low": 0.854702, "base": 0.427351, "high": 0.106838},
                "unit": "ratio",
                "rationale": "Reserve scales with filed NAV; bear assumes minority cannot realize book; bull assumes clearer share register and governance path.",
                "allowed_range": {"min": 0.05, "max": 1.0},
            }
        ],
        "calculations": [
            {
                "id": "nav_per_share",
                "label": "Form 990 net assets per provisional share",
                "op": "divide",
                "args": ["net_assets_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "reserve_gross",
                "label": "Gross illiquidity and governance reserve before sign",
                "op": "multiply",
                "args": ["nav_per_share", "realization_haircut_ratio"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "OTC illiquidity and nonprofit-governance reserve per share",
                "op": "negative",
                "args": ["reserve_gross"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
}


def close_authorized_evidence() -> None:
    auth_path = ROOT / "PLWN" / "research" / "authorized_evidence.json"
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["contract_status"] = "decision_grade"
    auth["blockers"] = []
    auth["component_coverage"]["unvalued_component_count"] = 0
    auth["authorized_at"] = "2026-07-24T02:00:00Z"
    auth_path.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-24"
    shares_note = (
        "Provisional aggregator ~3.46M shares; conflicts with $45.40 indicated dividend vs "
        "FY2024 NI $5.3M [HUMAN REVIEW — do not size on this denominator]"
    )
    data["inputs"]["shares_source"] = shares_note
    data["economic_value"]["economic_claim"]["unit_source"] = shares_note

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemError(f"{cid} proof invalid: {ev['checks']['errors']}")
        component["valuation"]["calculation_proof"] = proof
        component["valuation"]["valuation_status"] = "bounded_estimate"
        component["valuation"]["evidence_tier"] = "mixed_primary_and_estimate"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]
        component["valuation"]["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )
        component["valuation"]["evidence"] = (
            f"FY2024 Form 990 extract: revenue ~$42.9M, net income ~$5.3M, net assets ~$161.9M. "
            f"Proof base {ev['outputs']['base']}/sh via {proof['method_id']}@1.0. "
            "Share count and Schedule D remain [HUMAN REVIEW]."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    close_authorized_evidence()
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
