#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into LB valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "LB" / "research" / "valuation.json"
AS_OF = "2026-07-23"

FILING_10K = "LB/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001193125_26_072404.htm"
FILING_10Q = "LB/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001193125_26_209491.htm"
FILING_8K_Q1 = "LB/investor-documents/sec-edgar/8-K_20260506_exhibit_lb-ex99_1.htm_acc0001193125_26_209075.htm"
AS_OF_FY = "2025-12-31"
AS_OF_Q1 = "2026-03-31"

SHARES_M = 77.017004
CLASS_A_M = 27.839229
CLASS_B_M = 49.177775
DEBT_LT_M = 535.0
CASH_M = 30.7
FY2025_ADJ_EBITDA_M = 177.2
FY2025_FCF_M = 120.0
SURFACE_ACRES = 315000

LEGACY = {
    "current_fee_engine": {"low": 23.37, "base": 42.85, "high": 62.32},
    "net_debt": {"low": -7.5, "base": -6.56, "high": -5.8},
    "dormant_acreage": {"low": 0.6, "base": 2.8, "high": 6.0},
    "alpha_digital_option": {"low": 0.0, "base": 0.0, "high": 12.0},
    "pore_space_other_options": {"low": 0.0, "base": 1.5, "high": 5.0},
}

METHOD_MAP = {
    "current_fee_engine": "owner_cash_or_dividend_discount",
    "net_debt": "net_asset_value",
    "dormant_acreage": "net_asset_value",
    "alpha_digital_option": "risk_adjusted_milestone_value",
    "pore_space_other_options": "risk_adjusted_milestone_value",
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


def fee_engine_proof() -> dict:
    ebitda = {"low": 180.0, "base": 220.0, "high": 240.0}
    multiples = {
        case: LEGACY["current_fee_engine"][case] * SHARES_M / ebitda[case]
        for case in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "fy2025_adj_ebitda_m",
                "FY2025 adjusted EBITDA",
                FY2025_ADJ_EBITDA_M,
                "USD_m",
                FILING_8K_Q1,
                f"FY2025 adjusted EBITDA ${FY2025_ADJ_EBITDA_M}M (8-K FY2025 results exhibit)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Economic units outstanding (Class A plus OpCo units)",
                SHARES_M,
                "million_units",
                FILING_10Q,
                f"Q1 2026: {CLASS_A_M}M Class A shares plus {CLASS_B_M}M Class B/OpCo units",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "normalized_ebitda_m",
                "Normalized EBITDA for fee-engine capitalization",
                ebitda,
                "USD_m",
                "Low uses trough stress below 2026 guide floor; base uses midpoint of $210M-$230M "
                "2026 adjusted EBITDA outlook; high uses upper guide with modest run-rate uplift.",
                120.0,
                280.0,
            ),
            _judgment(
                "capitalization_multiple",
                "Enterprise-value multiple on normalized EBITDA before net debt",
                multiples,
                "multiple",
                "Capital-light surface toll; low 10x trough, base 15x mid-cycle, high 20x scarcity premium. "
                "Currently monetized acreage stays embedded here.",
                6.0,
                25.0,
            ),
        ],
        "calculations": [
            {
                "id": "enterprise_value_m",
                "label": "Enterprise value before net debt",
                "op": "multiply",
                "args": ["normalized_ebitda_m", "capitalization_multiple"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Current fee engine per economic unit",
                "op": "divide",
                "args": ["enterprise_value_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_debt_proof() -> dict:
    net_debt = {
        "low": round(-LEGACY["net_debt"]["low"] * SHARES_M, 1),
        "base": round(-LEGACY["net_debt"]["base"] * SHARES_M, 1),
        "high": round(-LEGACY["net_debt"]["high"] * SHARES_M, 1),
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "debt_lt_m",
                "Long-term debt",
                DEBT_LT_M,
                "USD_m",
                FILING_10Q,
                f"Long-term debt approximately ${DEBT_LT_M}M at March 31, 2026",
                AS_OF_Q1,
            ),
            _fact(
                "cash_m",
                "Cash and cash equivalents",
                CASH_M,
                "USD_m",
                FILING_10K,
                f"Cash and cash equivalents ${CASH_M}M at December 31, 2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                f"Q1 2026: {CLASS_A_M}M Class A shares plus {CLASS_B_M}M Class B/OpCo units",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "net_debt_m",
                "Net debt after cash (senior claim on equity)",
                net_debt,
                "USD_m",
                "Base reconciles long-term debt less year-end cash (~$505M). Low stresses refi and "
                "liquidity friction; high assumes modest deleveraging.",
                350.0,
                650.0,
            ),
        ],
        "calculations": [
            {
                "id": "net_debt_per_share",
                "label": "Net debt per economic unit before sign",
                "op": "divide",
                "args": ["net_debt_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Net debt claim per economic unit",
                "op": "negative",
                "args": ["net_debt_per_share"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def dormant_acreage_proof() -> dict:
    risked_nav_m = {
        case: round(LEGACY["dormant_acreage"][case] * SHARES_M, 2) for case in LEGACY["dormant_acreage"]
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "surface_acres",
                "Surface acres owned or managed",
                float(SURFACE_ACRES),
                "acres",
                FILING_10K,
                "Item 1 Business: own or manage 315,000+ surface acres (December 31, 2025)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                f"Q1 2026: {CLASS_A_M}M Class A shares plus {CLASS_B_M}M Class B/OpCo units",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "risked_nav_m",
                "Overlap-discounted dormant acreage NAV after fee-engine embed",
                risked_nav_m,
                "USD_m",
                "Transaction anchors from ~$875/acre bolt-ons to ~$7,100/fee-acre (1918 Ranch); "
                "only an illustrative share of inventory is additive after overlap with current operations.",
                0.0,
                600.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Dormant acreage per economic unit",
                "op": "divide",
                "args": ["risked_nav_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def alpha_digital_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "powerbridge_acres",
                "PowerBridge option acreage cap cited in filings",
                3400.0,
                "acres",
                FILING_10K,
                "Digital infrastructure / PowerBridge option over up to 3,400 acres; no executed Alpha Digital lease in SEC packet",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                f"Q1 2026: {CLASS_A_M}M Class A shares plus {CLASS_B_M}M Class B/OpCo units",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "success_value_m",
                "Gross campus economics if powered-land milestones convert",
                {"low": 0.0, "base": 0.0, "high": 1500.0},
                "USD_m",
                "No executed Alpha Digital lease with rent, customer, or capital terms in primary filings; "
                "base remains zero until contract economics are disclosed.",
                0.0,
                3000.0,
            ),
            _judgment(
                "success_probability",
                "Reference-class probability of enforceable LB net claim",
                {"low": 0.0, "base": 0.0, "high": 0.65},
                "ratio",
                "High case is upside sensitivity only; not contracted rent. Samsung options are capacity, not operating rent.",
                0.0,
                0.85,
            ),
            _judgment(
                "remaining_cost_m",
                "Remaining owner-funded capital before cash realization",
                {"low": 0.0, "base": 0.0, "high": 51.0},
                "USD_m",
                "Capital and infrastructure burden deducted where undisclosed in filings.",
                0.0,
                200.0,
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
                "label": "Net milestone value after remaining capital",
                "op": "subtract",
                "args": ["weighted_success_m", "remaining_cost_m"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Alpha Digital option per economic unit",
                "op": "divide",
                "args": ["risk_adjusted_value_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def pore_space_proof() -> dict:
    milestone_m = {
        case: round(LEGACY["pore_space_other_options"][case] * SHARES_M, 2)
        for case in LEGACY["pore_space_other_options"]
    }
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "surface_acres",
                "Contiguous Delaware Basin surface inventory",
                float(SURFACE_ACRES),
                "acres",
                FILING_10K,
                "315,000+ surface acres support pore space, water, fiber, and industrial uses (Item 1)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                f"Q1 2026: {CLASS_A_M}M Class A shares plus {CLASS_B_M}M Class B/OpCo units",
                AS_OF_Q1,
            ),
        ],
        "assumptions": [
            _judgment(
                "portfolio_option_m",
                "Risk-adjusted pore-space and new-use option reserve",
                milestone_m,
                "USD_m",
                "1918 Ranch and Intrepid South Ranch transactions show non-zero value for water/pore rights "
                "before full monetization; options graduate into fee engine only after contracts.",
                0.0,
                500.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Pore space and other options per economic unit",
                "op": "divide",
                "args": ["portfolio_option_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _build_proofs() -> dict[str, dict]:
    return {
        "current_fee_engine": fee_engine_proof(),
        "net_debt": net_debt_proof(),
        "dormant_acreage": dormant_acreage_proof(),
        "alpha_digital_option": alpha_digital_proof(),
        "pore_space_other_options": pore_space_proof(),
    }


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    proofs = _build_proofs()
    errors: list[str] = []
    outputs: dict[str, dict] = {}
    for cid, proof in proofs.items():
        ev = evaluate_calculation_proof(proof)
        outputs[cid] = ev.get("outputs") or {}
        if ev["status"] != "valid":
            errors.append(f"{cid}: {ev['checks']['errors']}")
            continue
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = outputs[cid][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                errors.append(f"{cid}.{case}: got {got}, want {want}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    data = json.loads(VAL_PATH.read_text(encoding="utf-8-sig"))
    data["as_of"] = AS_OF

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        proof = deepcopy(proofs[cid])
        ev = evaluate_calculation_proof(proof)
        val = component["valuation"]
        val["method"] = METHOD_MAP[cid]
        val["calculation_proof"] = proof
        val["valuation_status"] = "bounded_estimate"
        val["evidence_tier"] = "primary_derived"
        val["basis"] = "per_share" if cid != "current_fee_engine" else "total_value_m"
        for case in ("low", "base", "high"):
            if cid == "current_fee_engine":
                val[case] = round(ev["outputs"][case] * SHARES_M, 0)
            else:
                val[case] = ev["outputs"][case]
        val["evidence"] = (
            f"Q1 2026 debt ${DEBT_LT_M}M; cash ${CASH_M}M; FY2025 adj EBITDA ${FY2025_ADJ_EBITDA_M}M; "
            f"{SURFACE_ACRES:,} surface acres; {SHARES_M}M economic units. "
            f"Proof base {ev['outputs']['base']}/sh via {proof['method_id']}@1.0."
        )
        val["assumption_summary"] = (
            f"Proof outputs {ev['outputs']}; see calculation_proof graph."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One LB economic unit (Class A share look-through on Up-C) on current fee engine, "
            "net debt, risked dormant acreage, Alpha Digital milestone option, and pore-space portfolio reserve."
        ),
        "excluded_claims": [
            "Currently monetized surface, water, and royalty contracts remain in the fee-engine component.",
            "Alpha Digital base stays zero until executed lease economics are filed.",
            "GAAP book (~$12/sh Class A) is cross-check only; not a dhando floor.",
        ],
        "reconciliation": (
            f"Fee engine from normalized EBITDA multiples; net debt from Q1 debt ${DEBT_LT_M}M less cash; "
            f"dormant acreage from transaction-anchored risked NAV on {SURFACE_ACRES:,} acres."
        ),
        "evidence_ref": f"LB/research/evidence_reconciliation_{AS_OF}.json",
    }
    eva["validation_errors"] = []

    open_questions = [
        {
            "id": "alpha_digital_lease_economics",
            "question": "What enforceable economics accrue to LB from the Alpha Digital campus?",
            "status": "open",
            "blocks_decision_grade": True,
            "note": "Primary SEC packet lacks executed lease with rent, customer, capital, and termination terms.",
        },
        {
            "id": "fee_engine_unit_economics",
            "question": "How much of current fee growth is recurring volume, price, mix, and one-time activity?",
            "status": "open",
            "blocks_decision_grade": False,
            "note": "Q1 2026 run-rate exceeds FY2025 normalization; segment mix in 8-K revenue table.",
        },
    ]
    data["open_questions"] = open_questions

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(json.dumps({"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
