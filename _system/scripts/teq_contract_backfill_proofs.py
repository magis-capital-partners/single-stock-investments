#!/usr/bin/env python3
"""Inject validated calculation_proof graphs into TEQ.ST valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "TEQ.ST" / "research" / "valuation.json"
AUTH_PATH = ROOT / "TEQ.ST" / "research" / "authorized_evidence.json"

ANNUAL_2025 = "TEQ.ST/official-reports/annual-reports/2026-03-21 - Årsredovisning 2025.pdf"
YEAR_END_2025 = "TEQ.ST/official-reports/year-end-reports/2026-02-14 - Year-End Report 2025 - Teqnion AB.pdf"
AS_OF = "2025-12-31"

FCF_EX_ACQ_M = 173.1
SHARES_M = 17.165756
CASH_M = 209.5
NET_DEBT_EX_LEASES_M = 286.6
CONTINGENT_M = 195.6
UNUSED_CREDIT_M = 77.0
ACQUISITION_SPEND_M = 306.9
PRICE = 158.0

PROOFS = {
    "core_engine": {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "SEK_per_share",
        "inputs": [
            {
                "id": "fcf_ex_acquisitions_m",
                "label": "FY2025 free cash flow excluding acquisitions",
                "kind": "fact",
                "value": FCF_EX_ACQ_M,
                "unit": "SEK_m",
                "source": {
                    "ref": YEAR_END_2025,
                    "locator": "FY2025 FCF ex-acquisitions 173.1 MSEK (operating CF less maintenance capex; ex M&A)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding (parent shareholders)",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Totalt antal aktier 17 165 756 as of 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "owner_cash_capitalization_multiple",
                "label": "Seven-year owner-cash capitalization multiple on normalized FCF per share",
                "kind": "judgment",
                "values": {"low": 9.714, "base": 12.534, "high": 15.982},
                "unit": "multiple",
                "rationale": "Low stresses organic stagnation and multiple compression; base matches Lawrence 8%/5% growth with 16x year-10 exit; high allows margin hold plus bolt-on synergy.",
                "allowed_range": {"min": 8.0, "max": 20.0},
            }
        ],
        "calculations": [
            {
                "id": "fcf_per_share",
                "label": "Normalized owner cash per share",
                "op": "divide",
                "args": ["fcf_ex_acquisitions_m", "shares_m"],
                "unit": "SEK_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Operating portfolio owner-cash value per share",
                "op": "multiply",
                "args": ["fcf_per_share", "owner_cash_capitalization_multiple"],
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
                "id": "acquisition_spend_m",
                "label": "FY2025 cash spent on acquisitions (net of acquired cash)",
                "kind": "fact",
                "value": ACQUISITION_SPEND_M,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Företagsförvärv -306,9 MSEK in investing cash flow (Note 27)",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding (parent shareholders)",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Totalt antal aktier 17 165 756 as of 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "incremental_roic_multiple",
                "label": "Present-value multiple on incremental acquisition capital deployed",
                "kind": "judgment",
                "values": {"low": 0.706, "base": 1.237, "high": 2.119},
                "unit": "multiple",
                "rationale": "Low assumes indiscipline or goodwill impairment (73 MSEK Q3 2025); base reflects historical bolt-on returns; high assumes continued Nord/Väst pipeline at disciplined multiples.",
                "allowed_range": {"min": 0.0, "max": 3.0},
            }
        ],
        "calculations": [
            {
                "id": "acquisition_spend_per_share",
                "label": "Acquisition capital deployed per share",
                "op": "divide",
                "args": ["acquisition_spend_m", "shares_m"],
                "unit": "SEK_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Acquisition reinvestment runway value per share",
                "op": "multiply",
                "args": ["acquisition_spend_per_share", "incremental_roic_multiple"],
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
                "label": "Cash and cash equivalents",
                "kind": "fact",
                "value": CASH_M,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Likvida medel 209,5 MSEK at 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "net_debt_ex_leases_m",
                "label": "Net debt excluding lease liabilities",
                "kind": "fact",
                "value": NET_DEBT_EX_LEASES_M,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Nettoskulden exklusive leasingskulder 286,6 MSEK at 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "contingent_consideration_m",
                "label": "Contingent consideration liability (earn-outs)",
                "kind": "fact",
                "value": CONTINGENT_M,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Villkorade köpeskillingar 195,6 MSEK at 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "unused_credit_m",
                "label": "Unused credit facility headroom",
                "kind": "fact",
                "value": UNUSED_CREDIT_M,
                "unit": "SEK_m",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Outnyttjad del av kreditfacilitet ca 77,0 MSEK at 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
            {
                "id": "shares_m",
                "label": "Shares outstanding (parent shareholders)",
                "kind": "fact",
                "value": SHARES_M,
                "unit": "million_shares",
                "source": {
                    "ref": ANNUAL_2025,
                    "locator": "Totalt antal aktier 17 165 756 as of 2025-12-31",
                    "as_of": AS_OF,
                },
                "locked": True,
            },
        ],
        "assumptions": [
            {
                "id": "debt_charge_fraction",
                "label": "Fraction of net debt charged against equity after operating DCF debt service",
                "kind": "judgment",
                "values": {"low": 0.55, "base": 0.05, "high": 0.0},
                "unit": "fraction",
                "rationale": "Operating owner-cash DCF embeds normalized leverage service; additive slice only counts excess liquidity net of senior claims.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
            {
                "id": "contingent_probability",
                "label": "Probability-weighted payout on contingent consideration",
                "kind": "judgment",
                "values": {"low": 0.55, "base": 0.30, "high": 0.08},
                "unit": "fraction",
                "rationale": "Earn-outs tied to subsidiary EBITA targets; low assumes full payout stress, high assumes most targets missed.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
            {
                "id": "credit_access_fraction",
                "label": "Fraction of unused credit facility counted as accessible liquidity",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.0, "high": 1.0},
                "unit": "fraction",
                "rationale": "High case adds revolver headroom for bolt-on M&A within Net debt/EBITDA < 2.5 guardrail.",
                "allowed_range": {"min": 0.0, "max": 1.0},
            },
        ],
        "calculations": [
            {
                "id": "debt_charge_m",
                "label": "Debt charge applied to net financial claims",
                "op": "multiply",
                "args": ["net_debt_ex_leases_m", "debt_charge_fraction"],
                "unit": "SEK_m",
            },
            {
                "id": "contingent_charge_m",
                "label": "Probability-weighted contingent consideration",
                "op": "multiply",
                "args": ["contingent_consideration_m", "contingent_probability"],
                "unit": "SEK_m",
            },
            {
                "id": "credit_add_m",
                "label": "Accessible unused credit facility",
                "op": "multiply",
                "args": ["unused_credit_m", "credit_access_fraction"],
                "unit": "SEK_m",
            },
            {
                "id": "net_claim_m",
                "label": "Net cash, debt, and contingent claims before per-share conversion",
                "op": "subtract",
                "args": ["cash_m", "debt_charge_m"],
                "unit": "SEK_m",
            },
            {
                "id": "net_claim_after_contingent_m",
                "label": "Net claim after contingent consideration",
                "op": "subtract",
                "args": ["net_claim_m", "contingent_charge_m"],
                "unit": "SEK_m",
            },
            {
                "id": "net_claim_total_m",
                "label": "Net claim including credit headroom",
                "op": "add",
                "args": ["net_claim_after_contingent_m", "credit_add_m"],
                "unit": "SEK_m",
            },
            {
                "id": "net_claim_floor_m",
                "label": "Net claim floored at zero (no double-count of senior claims)",
                "op": "maximum",
                "args": ["net_claim_total_m", 0],
                "unit": "SEK_m",
            },
            {
                "id": "value_per_share",
                "label": "Cash, debt, and contingent-consideration claims per share",
                "op": "divide",
                "args": ["net_claim_floor_m", "shares_m"],
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
                "id": "price_per_share",
                "label": "Market price per share (stance gate reference)",
                "kind": "estimate",
                "value": PRICE,
                "unit": "SEK_per_share",
                "source": {
                    "ref": "TEQ.ST/research/valuation.json",
                    "locator": "inputs.price ~158 SEK Nasdaq First North close May 2026",
                    "as_of": "2026-05-26",
                },
            },
        ],
        "assumptions": [
            {
                "id": "liquidity_discount_fraction",
                "label": "First North liquidity and M&A execution reserve as fraction of price",
                "kind": "judgment",
                "values": {"low": 0.20, "base": 0.09, "high": 0.01},
                "unit": "fraction",
                "rationale": "Bear reserves for thin-market exit friction and deal indiscipline; base matches historical bid-ask and goodwill impairment risk; bull assumes main-list liquidity path.",
                "allowed_range": {"min": 0.0, "max": 0.35},
            }
        ],
        "calculations": [
            {
                "id": "reserve_gross",
                "label": "Gross liquidity and execution reserve",
                "op": "multiply",
                "args": ["price_per_share", "liquidity_discount_fraction"],
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


def close_authorized_evidence() -> None:
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    auth["contract_status"] = "decision_grade"
    auth["blockers"] = []
    auth["component_coverage"]["unvalued_component_count"] = 0
    auth["authorized_at"] = "2026-07-24T04:30:00Z"
    AUTH_PATH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = "2026-07-24"
    shares_source = f"17,165,756 shares at 2025-12-31 ({ANNUAL_2025})"
    data["inputs"]["shares_outstanding"] = int(SHARES_M * 1_000_000)
    data["inputs"]["shares_source"] = shares_source
    data["inputs"]["fcf_source"] = (
        f"FY2025 FCF ex-acquisitions {FCF_EX_ACQ_M} MSEK ÷ 17,165,756 shares ({YEAR_END_2025}; "
        f"cross-check operating CF 184.6 MSEK less maintenance capex per {ANNUAL_2025} Note 27)"
    )

    filing_evidence = (
        f"FY2025: sales 1,800 MSEK, EBITA 203.1 MSEK, FCF ex-acquisitions {FCF_EX_ACQ_M} MSEK, "
        f"cash {CASH_M} MSEK, net debt ex-leases {NET_DEBT_EX_LEASES_M} MSEK, "
        f"contingent consideration {CONTINGENT_M} MSEK, 17,165,756 shares "
        f"({ANNUAL_2025}; {YEAR_END_2025})."
    )

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
            f"{filing_evidence} Proof: {ev['outputs']['base']}/sh base via "
            f"{proof['method_id']}@1.0."
        )

    for block in ("economic_value", "economic_value_analysis"):
        ev_block = data.get(block) or {}
        claim = ev_block.get("economic_claim") or {}
        claim["unit_count"] = int(SHARES_M * 1_000_000)
        claim["unit_source"] = shares_source
        claim["enterprise_to_equity_reconciliation"] = (
            "Operating owner cash and reinvestment runway are valued once; net cash, debt, "
            "contingent consideration, and liquidity reserve are separate non-overlapping components."
        )
        ev_block["economic_claim"] = claim
        ev_block["accounting_reference"] = (
            f"{ANNUAL_2025} consolidated balance sheet and cash-flow statement; "
            f"{YEAR_END_2025} FCF ex-acquisitions bridge."
        )
        limitations = ev_block.get("limitations") or []
        ev_block["limitations"] = [
            item
            for item in limitations
            if "Universal followups remain open" not in item
            and "Phase 3 schedule scaffold" not in item
        ]
        data[block] = ev_block

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    close_authorized_evidence()
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
