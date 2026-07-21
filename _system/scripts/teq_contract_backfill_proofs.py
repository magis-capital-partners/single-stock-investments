#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into TEQ.ST valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "TEQ.ST" / "research" / "valuation.json"

ANNUAL = "TEQ.ST/official-reports/annual-reports/2026-03-21 - Årsredovisning 2025.pdf"
AS_OF = "2025-12-31"

SHARES_M = 17.165756

PROOFS = {
    "core_engine": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            {
                "id": "operating_cf_m",
                "label": "FY2025 cash flow from operating activities",
                "kind": "fact",
                "value": 184.6,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Kassaflöde från den löpande verksamheten 184,6 MSEK (Not 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "non_ma_investing_m",
                "label": "FY2025 investing cash outflow excluding business acquisitions",
                "kind": "fact",
                "value": 11.5,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Investeringar i anläggningstillgångar 14,4 MSEK exkl. företagsförvärv 306,9 MSEK (Not 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Totalt antal aktier 17 165 756",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "capitalization_multiple",
                "label": "Duration-adjusted owner-cash capitalization multiple",
                "kind": "judgment",
                "values": {"low": 9.71793, "base": 12.53968, "high": 15.98849},
                "unit": "multiple",
                "rationale": "Bear stresses organic stagnation and multiple compression; base seven-year owner-cash path; bull modest margin/M&A uplift without Q1 2026 peak run-rate.",
                "allowed_range": {"min": 4.0, "max": 25.0},
            }
        ],
        "calculations": [
            {
                "id": "fcf_ex_acquisitions_m",
                "label": "Free cash flow excluding acquisitions",
                "op": "subtract",
                "args": ["operating_cf_m", "non_ma_investing_m"],
                "unit": "SEK_m",
            },
            {
                "id": "fcf_per_share",
                "label": "FY2025 FCF ex-acquisitions per share",
                "op": "divide",
                "args": ["fcf_ex_acquisitions_m", "shares_m"],
                "unit": "SEK_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Operating portfolio owner cash per share",
                "op": "multiply",
                "args": ["fcf_per_share", "capitalization_multiple"],
                "unit": "SEK_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "reinvestment_or_assets": {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            {
                "id": "operating_cf_m",
                "label": "FY2025 cash flow from operating activities",
                "kind": "fact",
                "value": 184.6,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Kassaflöde från den löpande verksamheten 184,6 MSEK (Not 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "non_ma_investing_m",
                "label": "FY2025 investing cash outflow excluding business acquisitions",
                "kind": "fact",
                "value": 11.5,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Investeringar i anläggningstillgångar 14,4 MSEK exkl. företagsförvärv 306,9 MSEK (Not 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Totalt antal aktier 17 165 756",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "reinvestment_runway_multiple",
                "label": "Incremental reinvestment runway multiple on FCF ex-acquisitions per share",
                "kind": "judgment",
                "values": {"low": 1.25397, "base": 2.19424, "high": 3.7619},
                "unit": "multiple",
                "rationale": "Low assumes bolt-on pipeline stalls; base risk-adjusts nine FY2025 acquisitions; high assumes sustained UK/Nordic deal pace at disciplined multiples.",
                "allowed_range": {"min": 0.0, "max": 6.0},
            }
        ],
        "calculations": [
            {
                "id": "fcf_ex_acquisitions_m",
                "label": "Free cash flow excluding acquisitions",
                "op": "subtract",
                "args": ["operating_cf_m", "non_ma_investing_m"],
                "unit": "SEK_m",
            },
            {
                "id": "fcf_per_share",
                "label": "FY2025 FCF ex-acquisitions per share",
                "op": "divide",
                "args": ["fcf_ex_acquisitions_m", "shares_m"],
                "unit": "SEK_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Acquisition reinvestment runway per share",
                "op": "multiply",
                "args": ["fcf_per_share", "reinvestment_runway_multiple"],
                "unit": "SEK_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "net_financial_claims": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            {
                "id": "cash_m",
                "label": "Cash and bank balances",
                "kind": "fact",
                "value": 209.5,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Koncernens likvida medel 209,5 MSEK",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "contingent_consideration_m",
                "label": "Contingent consideration liabilities (earnouts)",
                "kind": "fact",
                "value": 195.6,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Finansiella skulder avseende villkorade köpeskillingar 195,6 MSEK (Not 14)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Totalt antal aktier 17 165 756",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "structural_liquidity_claim_m",
                "label": "Bounded parent liquidity and credit headroom not in operating DCF",
                "kind": "judgment",
                "values": {"low": -13.9, "base": 121.7, "high": 257.3},
                "unit": "SEK_m",
                "rationale": "Low nets cash against contingent consideration only; base adds undrawn credit headroom; high adds full undrawn check and credit facility slice.",
                "allowed_range": {"min": -100.0, "max": 400.0},
            }
        ],
        "calculations": [
            {
                "id": "gross_claim_m",
                "label": "Cash plus structural liquidity headroom",
                "op": "add",
                "args": ["cash_m", "structural_liquidity_claim_m"],
                "unit": "SEK_m",
            },
            {
                "id": "net_claim_m",
                "label": "Net financial claim before per-share conversion",
                "op": "subtract",
                "args": ["gross_claim_m", "contingent_consideration_m"],
                "unit": "SEK_m",
            },
            {
                "id": "value_per_share",
                "label": "Net financial claims per share",
                "op": "divide",
                "args": ["net_claim_m", "shares_m"],
                "unit": "SEK_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    },
    "downside_reserve": {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            {
                "id": "operating_cf_m",
                "label": "FY2025 cash flow from operating activities",
                "kind": "fact",
                "value": 184.6,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Kassaflöde från den löpande verksamheten 184,6 MSEK (Not 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "non_ma_investing_m",
                "label": "FY2025 investing cash outflow excluding business acquisitions",
                "kind": "fact",
                "value": 11.5,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Investeringar i anläggningstillgångar 14,4 MSEK exkl. företagsförvärv 306,9 MSEK (Not 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL,
                    "locator": "Totalt antal aktier 17 165 756",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "reserve_multiple",
                "label": "Small-cap liquidity and execution reserve multiple on FCF ex-acquisitions per share",
                "kind": "judgment",
                "values": {"low": 3.133, "base": 1.41, "high": 0.1567},
                "unit": "multiple",
                "rationale": "Reserve scales with owner-cash run-rate; bear assumes goodwill impairment repeat and First North liquidity; bull assumes tighter spreads.",
                "allowed_range": {"min": 0.0, "max": 5.0},
            }
        ],
        "calculations": [
            {
                "id": "fcf_ex_acquisitions_m",
                "label": "Free cash flow excluding acquisitions",
                "op": "subtract",
                "args": ["operating_cf_m", "non_ma_investing_m"],
                "unit": "SEK_m",
            },
            {
                "id": "fcf_per_share",
                "label": "FY2025 FCF ex-acquisitions per share",
                "op": "divide",
                "args": ["fcf_ex_acquisitions_m", "shares_m"],
                "unit": "SEK_per_share",
            },
            {
                "id": "reserve_gross",
                "label": "Gross reserve before sign",
                "op": "multiply",
                "args": ["fcf_per_share", "reserve_multiple"],
                "unit": "SEK_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Small-cap liquidity and execution reserve per share",
                "op": "negative",
                "args": ["reserve_gross"],
                "unit": "SEK_per_share",
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
    shares_source = f"17,165,756 shares at {AS_OF} ({ANNUAL})"
    data["inputs"]["shares_outstanding"] = int(SHARES_M * 1_000_000)
    data["inputs"]["shares_source"] = shares_source
    data["inputs"]["fcf_source"] = (
        "FY2025 FCF ex-acquisitions 173.1 MSEK = operating CF 184.6 MSEK "
        "minus non-acquisition investing 11.5 MSEK (Not 27); ÷ 17,165,756 shares"
    )
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
            f"FY2025 operating CF 184.6 MSEK; FCF ex-acquisitions 173.1 MSEK; "
            f"cash 209.5 MSEK; contingent consideration 195.6 MSEK; "
            f"17,165,756 shares ({ANNUAL}). "
            f"Proof base {ev['outputs']['base']}/sh via {proof['method_id']}@1.0."
        )

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
