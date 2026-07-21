#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into HNFSA valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "HNFSA" / "research" / "valuation.json"

FILING_10K = "HNFSA/investor-documents/sec-edgar/10-K_20040830_rpt20040531_acc000095011604002631.htm"
FILING_SC13E3 = "HNFSA/investor-documents/sec-edgar/proxy_SC13E3_odd_lot_tender_20041206.htm"
AS_OF = "2004-05-30"

PROOFS = {
    "operating_food_business": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "class_a_shares",
                "label": "Class A common shares outstanding",
                "kind": "fact",
                "value": 287996,
                "unit": "shares",
                "source": {
                    "ref": FILING_10K,
                    "locator": "287,996 shares of Class A Common Stock outstanding as of August 11, 2004",
                    "as_of": "2004-08-11",
                },
                "locked": True,
            },
            {
                "id": "odd_lot_tender_price",
                "label": "December 2004 odd-lot tender price",
                "kind": "fact",
                "value": 131.0,
                "unit": "USD_per_share",
                "source": {
                    "ref": FILING_SC13E3,
                    "locator": "Odd-lot tender offer price of $131.00 per share for eligible Class A shares",
                    "as_of": "2004-12-06",
                },
                "locked": True,
            },
            {
                "id": "gaap_book_per_share",
                "label": "Stated GAAP book per Class A share (aggregator cross-check)",
                "kind": "estimate",
                "value": 87.62,
                "unit": "USD_per_share",
                "source": {
                    "ref": "HNFSA/research/valuation.json",
                    "locator": "Aggregator book value ~$87.62/sh; last filed GAAP equity is FY2004 Exhibit 13 — stale",
                    "as_of": "2026-06-10",
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "seven_year_payoff_to_book_ratio",
                "label": "Seven-year owner-cash payoff as a fraction of stated book",
                "kind": "judgment",
                "values": {"low": 0.575, "base": 0.822, "high": 1.15},
                "unit": "ratio",
                "rationale": "Bear assumes book erosion without facility monetization; base matches partial re-rate to $72/sh; bull approaches stated book if catalysts emerge.",
                "allowed_range": {"min": 0.4, "max": 1.3},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Operating food business per share",
                "op": "multiply",
                "args": ["gaap_book_per_share", "seven_year_payoff_to_book_ratio"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "illiquidity_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            {
                "id": "class_a_shares",
                "label": "Class A common shares outstanding",
                "kind": "fact",
                "value": 287996,
                "unit": "shares",
                "source": {
                    "ref": FILING_SC13E3,
                    "locator": "287,996 shares of Class A Common Stock issued and outstanding as of November 22, 2004",
                    "as_of": "2004-11-22",
                },
                "locked": True,
            },
            {
                "id": "gaap_book_per_share",
                "label": "Stated GAAP book per Class A share (aggregator cross-check)",
                "kind": "estimate",
                "value": 87.62,
                "unit": "USD_per_share",
                "source": {
                    "ref": "HNFSA/research/valuation.json",
                    "locator": "Aggregator book value ~$87.62/sh; last filed GAAP equity is FY2004 Exhibit 13 — stale",
                    "as_of": "2026-06-10",
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "otc_control_discount_ratio",
                "label": "OTC Pink and family-control realization discount on stated book",
                "kind": "judgment",
                "values": {"low": 0.205, "base": 0.123, "high": 0.041},
                "unit": "ratio",
                "rationale": "Thin OTC market, Class B control, and stale disclosure widen the gap between economic realization and stated book; low case assumes deeper friction.",
                "allowed_range": {"min": 0.0, "max": 0.35},
            }
        ],
        "calculations": [
            {
                "id": "reserve_gross",
                "label": "Gross illiquidity reserve before sign",
                "op": "multiply",
                "args": ["gaap_book_per_share", "otc_control_discount_ratio"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "OTC / control illiquidity reserve per share",
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
        "287,996 Class A shares outstanding at August 11, 2004 "
        f"({FILING_10K}); aggregator ~1.21M for book math remains [Assumption]"
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
        component["valuation"]["evidence_tier"] = "mixed_primary_and_estimate"
        for case in ("low", "base", "high"):
            component["valuation"][case] = round(ev["outputs"][case], 2)
        if cid == "operating_food_business":
            component["valuation"]["evidence"] = (
                "287,996 Class A shares; December 2004 odd-lot tender at $131/sh; "
                f"stated book ~$87.62/sh [Assumption]. Proof base {ev['outputs']['base']}/sh "
                f"via owner_cash_or_dividend_discount@1.0."
            )
        else:
            component["valuation"]["evidence"] = (
                "287,996 Class A shares; OTC Pink and Warehime Class B control from FY2004 10-K. "
                f"Proof base {ev['outputs']['base']}/sh via net_asset_value@1.0."
            )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
