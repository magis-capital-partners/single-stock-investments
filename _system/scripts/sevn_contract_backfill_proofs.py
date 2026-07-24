#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into SEVN valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "SEVN" / "research" / "valuation.json"

FILING_10Q = "SEVN/investor-documents/sec-edgar/10-Q_20260428_rpt20260331_acc0001452477_26_000021.htm"
FILING_10K = "SEVN/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001452477_26_000010.htm"
PRESENTATION = "SEVN/investor-documents/ir-sevn/SEVN-Q1-2026-Earnings-Presentation.pdf"
AS_OF = "2026-03-31"

PROOFS = {
    "tangible_loan_book_equity": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "adjusted_book_per_share",
                "label": "Adjusted book value per share (Q1 2026)",
                "kind": "fact",
                "value": 14.90,
                "unit": "USD_per_share",
                "source": {
                    "ref": PRESENTATION,
                    "locator": "Adjusted book value $14.90 per share as of 2026-03-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "mark_to_market_multiplier",
                "label": "Bounded mark-to-market adjustment on adjusted book",
                "kind": "judgment",
                "values": {"low": 0.8389, "base": 1.0, "high": 1.0745},
                "unit": "multiple",
                "rationale": "Low applies CRE stress marks below filing book; base uses adjusted book; high allows modest premium if redeployment lifts asset marks.",
                "allowed_range": {"min": 0.75, "max": 1.15},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Tangible loan-book equity per share",
                "op": "multiply",
                "args": ["adjusted_book_per_share", "mark_to_market_multiplier"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "external_manager_fee_drag": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "management_fees_m",
                "label": "FY2025 management fees (Tremont/RMR)",
                "kind": "fact",
                "value": 4.985,
                "unit": "USD_m",
                "source": {
                    "ref": FILING_10K,
                    "locator": "Management fees $4,985 thousand for year ended 2025-12-31",
                    "as_of": "2025-12-31",
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Common shares outstanding (Q1 2026)",
                "kind": "fact",
                "value": 22.596,
                "unit": "million_shares",
                "source": {
                    "ref": PRESENTATION,
                    "locator": "Shares outstanding ~22.596 million as of 2026-03-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "fee_capitalization_years",
                "label": "Capitalized years of external-manager fee drag",
                "kind": "judgment",
                "values": {"low": 11.33, "base": 6.80, "high": 3.63},
                "unit": "years",
                "rationale": "Bear capitalizes longer fee drag including incentive-fee upside; base reflects 1.5% base fee run-rate; bull assumes partial internalization or fee compression.",
                "allowed_range": {"min": 2.0, "max": 15.0},
            }
        ],
        "calculations": [
            {
                "id": "annual_fee_per_share",
                "label": "Annual management fee per share",
                "op": "divide",
                "args": ["management_fees_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "fee_drag_gross",
                "label": "Gross fee drag before sign",
                "op": "multiply",
                "args": ["annual_fee_per_share", "fee_capitalization_years"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "External manager fee drag per share",
                "op": "negative",
                "args": ["fee_drag_gross"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "cre_credit_and_redeployment_reserve": {
        "schema_version": "1.0",
        "method_id": "capital_structure_and_excess_return",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "total_commitments_m",
                "label": "Total loan commitments (Q1 2026)",
                "kind": "fact",
                "value": 776.0,
                "unit": "USD_m",
                "source": {
                    "ref": PRESENTATION,
                    "locator": "Total loan commitments $776.0 million as of 2026-03-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "acl_pct",
                "label": "Allowance for credit losses as percent of commitments",
                "kind": "fact",
                "value": 0.013,
                "unit": "ratio",
                "source": {
                    "ref": PRESENTATION,
                    "locator": "ACL 1.3% of total loan commitments",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Common shares outstanding (Q1 2026)",
                "kind": "fact",
                "value": 22.596,
                "unit": "million_shares",
                "source": {
                    "ref": PRESENTATION,
                    "locator": "Shares outstanding ~22.596 million as of 2026-03-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "stress_reserve_multiple",
                "label": "Stress reserve multiple on filing ACL per share",
                "kind": "judgment",
                "values": {"low": 6.72, "base": 3.36, "high": 1.12},
                "unit": "multiple",
                "rationale": "Low adds CRE cycle losses and redeployment lag beyond ACL; base matches judgment reserve; high assumes clean book and faster capital deployment.",
                "allowed_range": {"min": 1.0, "max": 8.0},
            }
        ],
        "calculations": [
            {
                "id": "acl_m",
                "label": "Allowance for credit losses (dollars)",
                "op": "multiply",
                "args": ["total_commitments_m", "acl_pct"],
                "unit": "USD_m",
            },
            {
                "id": "acl_per_share",
                "label": "Filing ACL per share",
                "op": "divide",
                "args": ["acl_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "reserve_gross",
                "label": "Gross credit and redeployment reserve",
                "op": "multiply",
                "args": ["acl_per_share", "stress_reserve_multiple"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "CRE credit and redeployment reserve per share",
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
    data["as_of"] = "2026-07-24"

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        if cid not in PROOFS:
            continue
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemError(f"{cid} proof invalid: {ev['checks']['errors']}")
        val = component["valuation"]
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        val["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            val[case] = ev["outputs"][case]
        val["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )
        val["evidence"] = (
            f"Q1 2026 adjusted book $14.90/sh; FY2025 management fees $4.985M; "
            f"loan commitments $776M at 1.3% ACL; 22.596M shares "
            f"({PRESENTATION}; {FILING_10K}; {FILING_10Q}). "
            f"Proof: {ev['outputs']['base']}/sh base via {proof['method_id']}@1.0."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
