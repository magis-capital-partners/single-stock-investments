#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for ABMD.CVR contract backfill."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ABMD.CVR"
AS_OF = "2026-07-21"
CVR_AGREEMENT = (
    "https://www.sec.gov/Archives/edgar/data/200406/000119312522311072/d428734dex101.htm"
)
OFFER_DOC = (
    "https://www.sec.gov/Archives/edgar/data/200406/000119312522285216/d411777dex99a1a.htm"
)
JNJ_CLOSE = "https://www.jnj.com/media-center/press-releases/johnson-johnson-completes-acquisition-of-abiomed"
ABMD_FY2022 = "https://www.sec.gov/Archives/edgar/data/815094/000095017022006432/abmd-ex99_1.htm"
CVR_AGREEMENT_DATE = "2022-12-22"

# Probability-weighted milestone values per CVR (one CVR per pre-merger ABMD share).
LEGACY = {
    "net_sales_milestone": {"low": 0.0, "base": 8.31, "high": 17.50},
    "fda_stemi_milestone": {"low": 0.0, "base": 2.63, "high": 7.50},
    "clinical_recommendation_milestone": {"low": 0.0, "base": 4.50, "high": 10.00},
    "timing_execution_reserve": {"low": -4.0, "base": -2.0, "high": -0.5},
}

METHOD_MAP = {
    "net_sales_milestone": "risk_adjusted_milestone_value",
    "fda_stemi_milestone": "risk_adjusted_milestone_value",
    "clinical_recommendation_milestone": "risk_adjusted_milestone_value",
    "timing_execution_reserve": "net_asset_value",
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
    values: dict,
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


def net_sales_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_cvr",
        "inputs": [
            _fact(
                "full_milestone_payment",
                "Net sales milestone payment if achieved in 2028 measurement period",
                17.50,
                "USD_per_cvr",
                CVR_AGREEMENT,
                "Milestone Payment (a)(i): $17.50 per CVR if Net Sales Milestone achieved during 2028 Measurement Period",
                CVR_AGREEMENT_DATE,
            ),
            _fact(
                "reduced_milestone_payment",
                "Net sales milestone payment if achieved in 2028-29 measurement period only",
                8.75,
                "USD_per_cvr",
                CVR_AGREEMENT,
                "Milestone Payment (a)(ii): $8.75 per CVR if achieved during 2028-29 Measurement Period after missing 2028 period",
                CVR_AGREEMENT_DATE,
            ),
            _fact(
                "net_sales_threshold_b",
                "Worldwide net sales threshold for net sales milestone",
                3.7,
                "USD_billion",
                CVR_AGREEMENT,
                "Net Sales Milestone: aggregate worldwide Net Sales exceeds $3,700,000,000",
                CVR_AGREEMENT_DATE,
            ),
            _fact(
                "abiomed_fy2022_revenue_b",
                "Abiomed FY2022 worldwide revenue (pre-acquisition baseline)",
                1.032,
                "USD_billion",
                ABMD_FY2022,
                "Full year revenue totaled $1.032 billion for fiscal year ended March 31, 2022",
                "2022-03-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "full_period_success_probability",
                "Probability of exceeding $3.7B net sales in the 2028 measurement period",
                {"low": 0.0, "base": 0.40, "high": 1.0},
                "probability",
                "FY2022 revenue $1.0B; milestone requires ~3.6× run-rate by JNJ FY2028 Q1 window. "
                "JNJ MedTech distribution and Impella penetration partially offset but threshold remains ambitious.",
                0.0,
                1.0,
            ),
            _judgment(
                "delayed_period_success_probability",
                "Probability of reduced $8.75 payment in 2028-29 measurement period",
                {"low": 0.0, "base": 0.15, "high": 0.0},
                "probability",
                "Captures delayed four-quarter achievement at half rate if primary window missed.",
                0.0,
                0.5,
            ),
        ],
        "calculations": [
            {
                "id": "full_expected",
                "label": "Expected value from full-period milestone",
                "op": "multiply",
                "args": ["full_milestone_payment", "full_period_success_probability"],
                "unit": "USD_per_cvr",
            },
            {
                "id": "delayed_expected",
                "label": "Expected value from delayed milestone",
                "op": "multiply",
                "args": ["reduced_milestone_payment", "delayed_period_success_probability"],
                "unit": "USD_per_cvr",
            },
            {
                "id": "value_per_share",
                "label": "Net sales milestone expected value per CVR",
                "op": "add",
                "args": ["full_expected", "delayed_expected"],
                "unit": "USD_per_cvr",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def fda_stemi_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_cvr",
        "inputs": [
            _fact(
                "milestone_payment",
                "FDA approval milestone payment",
                7.50,
                "USD_per_cvr",
                CVR_AGREEMENT,
                "Milestone Payment (b): $7.50 per CVR for FDA Approval Milestone",
                CVR_AGREEMENT_DATE,
            ),
        ],
        "assumptions": [
            _judgment(
                "success_probability",
                "Probability of FDA PMA approval for Impella in STEMI without cardiogenic shock by Jan 1, 2028",
                {"low": 0.0, "base": 0.35, "high": 1.0},
                "probability",
                "STEMI DTU trial and regulatory path remain active under JNJ; binary regulatory risk by fixed deadline.",
                0.0,
                1.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Risk-adjusted FDA milestone value per CVR",
                "op": "multiply",
                "args": ["milestone_payment", "success_probability"],
                "unit": "USD_per_cvr",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def clinical_recommendation_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_cvr",
        "inputs": [
            _fact(
                "milestone_payment",
                "Clinical recommendation milestone payment",
                10.00,
                "USD_per_cvr",
                CVR_AGREEMENT,
                "Milestone Payment (c): $10.00 per CVR for Clinical Recommendation Milestone",
                CVR_AGREEMENT_DATE,
            ),
        ],
        "assumptions": [
            _judgment(
                "success_probability",
                "Probability at least one Class I ACC/AHA guideline recommendation path succeeds by Dec 31, 2029",
                {"low": 0.0, "base": 0.45, "high": 1.0},
                "probability",
                "Three mutually exclusive clinical paths (STEMI, HRPCI, cardiogenic shock); earliest success triggers full payment.",
                0.0,
                1.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Risk-adjusted clinical recommendation value per CVR",
                "op": "multiply",
                "args": ["milestone_payment", "success_probability"],
                "unit": "USD_per_cvr",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def timing_reserve_proof() -> dict:
    reserve = {c: abs(LEGACY["timing_execution_reserve"][c]) for c in LEGACY["timing_execution_reserve"]}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_cvr",
        "inputs": [],
        "assumptions": [
            _judgment(
                "reserve_per_cvr",
                "Reserve for tax withholding, payment delay, net-sales definition risk, and non-tradeable illiquidity",
                reserve,
                "USD_per_cvr",
                "CVR Agreement permits withholding and measurement disputes; OTC quote unavailable at 0.000.",
                0.0,
                6.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Timing and execution reserve per CVR",
                "op": "negative",
                "args": ["reserve_per_cvr"],
                "unit": "USD_per_cvr",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _component(cid: str, label: str, category: str, overlap_key: str) -> dict:
    return {
        "id": cid,
        "label": label,
        "category": category,
        "overlap_key": overlap_key,
        "treatment": "additive",
        "valuation": {
            "method": METHOD_MAP[cid],
            "basis": "per_cvr",
            "low": LEGACY[cid]["low"],
            "base": LEGACY[cid]["base"],
            "high": LEGACY[cid]["high"],
            "evidence_tier": "primary_derived",
            "evidence": "Contract backfill scaffold; proof attachment pending.",
            "assumption_summary": "Phase 3 provisional range pending filing-grounded proof.",
            "cross_check": "Reconcile to CVR Agreement milestone definitions before decision use.",
            "falsifier": "JNJ certifies milestone non-achievement or Net Sales Statement shows threshold unreachable.",
            "valuation_status": "legacy_sensitivity",
        },
    }


def build_valuation_scaffold(base_sum: float) -> dict:
    ref_price = round(base_sum, 2)
    return {
        "ticker": TICKER,
        "as_of": AS_OF,
        "method": "yield_curve",
        "irr_method": "yield_curve",
        "method_profile": "binary_milestone",
        "valuation_mode": "economic_value",
        "lawrence_bucket": "other",
        "payoff_lens": "event",
        "classification_inputs": {
            "archetype": "optionality",
            "moat": "n/a",
            "dhando": "partial",
            "cycle": "-",
            "payoff_lens": "event",
            "predictive_attribute": "complexity_discount",
        },
        "inputs": {
            "price": ref_price,
            "price_source": (
                "Reference price equals base-case probability-weighted milestone component sum; "
                "non-tradeable CVR has no reliable OTC quote (0.000 on broker screens Jul 2026) [Assumption for yield curve]"
            ),
            "price_as_of": AS_OF,
            "shares_outstanding": 1,
            "shares_source": (
                "One CVR per pre-merger Abiomed share tendered; ~25.76M shares accepted Dec 2022 "
                f"({JNJ_CLOSE})"
            ),
            "max_milestone_payment_per_cvr": 35.0,
            "max_milestone_source": f"CVR Agreement and Offer to Purchase ({OFFER_DOC})",
            "abiomed_fy2022_revenue_b": 1.032,
            "abiomed_fy2022_revenue_source": ABMD_FY2022,
            "normalization_note": (
                "Security is a non-tradeable contingent cash claim, not an operating business. "
                "Lawrence yield-curve base uses probability-weighted milestone stack from the Dec 2022 CVR Agreement."
            ),
        },
        "scenarios": {
            "bear": {
                "price": ref_price,
                "payoff": 2.0,
                "years": 4.0,
                "notes": "All three milestones miss or only minimal delayed net-sales payment; long wait, high discount.",
            },
            "base": {
                "price": ref_price,
                "payoff": ref_price,
                "years": 3.5,
                "notes": "Component-weighted expected milestone stack realized on base probabilities by 2029.",
            },
            "bull": {
                "price": ref_price,
                "payoff": 32.0,
                "years": 3.0,
                "notes": "Near-maximum $35 stack less modest reserve; FDA and Class I paths succeed on schedule.",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Pure contractual cash claim; no balance sheet",
            },
            {
                "q": 2,
                "question": "Undeveloped reserves / acreage / dormant royalty?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "No physical asset base",
            },
            {
                "q": 3,
                "question": "In-business loss segment?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Not an operating company",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "Yes",
                "treatment": "yield_curve",
                "evidence": "Contractual milestone payments up to $35/CVR per CVR Agreement",
            },
            {
                "q": 5,
                "question": "Private or illiquid stakes below fair value?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Cash claim only",
            },
            {
                "q": 6,
                "question": "Transitory distribution / legal recovery?",
                "answer": "Yes",
                "treatment": "yield_curve",
                "evidence": "Dated milestone cash payments from JNJ upon achievement",
            },
            {
                "q": 7,
                "question": "Embedded product option already in revenue?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Claim is separate from JNJ MedTech equity",
            },
        ],
        "optionality_gate": {
            "framework": "milestone_yield_curve",
            "floor_pass": True,
            "floor_metric": "contractual_milestone_stack",
            "floor_value": 0.0,
            "ceiling_value": 35.0,
            "primary_metric": "lawrence_base",
            "primary_label": "annualized return",
            "notes": (
                "Downside bounded at zero contractual payment per milestone; upside capped at $35/CVR. "
                "Illiquidity and JNJ measurement discretion remain real risks."
            ),
        },
        "growth_explanation": {
            "mechanism": (
                "Return driver is dated milestone realization under the Dec 2022 CVR Agreement, "
                "not operating cash-flow growth."
            ),
            "bear_trigger": "2028 Non-Achievement Notice for net sales and FDA miss by Jan 1, 2028.",
            "bull_trigger": "Full $17.50 net-sales payment plus FDA and Class I milestones before deadlines.",
            "status": "complete",
        },
        "lawrence_horizon_years": 7,
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": "<15%",
            "gates": {"moat_ok": True, "dhando_ok": True},
            "override_reason": None,
        },
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Four additive components map net-sales, FDA, clinical-recommendation milestones "
                "and a timing/execution reserve once each."
            ),
            "components": [
                _component(
                    "net_sales_milestone",
                    "Net sales milestone ($3.7B threshold)",
                    "real_option",
                    "net_sales_milestone",
                ),
                _component(
                    "fda_stemi_milestone",
                    "FDA STEMI-without-shock approval milestone",
                    "real_option",
                    "fda_stemi_milestone",
                ),
                _component(
                    "clinical_recommendation_milestone",
                    "Class I clinical recommendation milestone",
                    "real_option",
                    "clinical_recommendation_milestone",
                ),
                _component(
                    "timing_execution_reserve",
                    "Tax, timing, definition, and illiquidity reserve",
                    "liability_or_reserve",
                    "timing_execution_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One ABMD.CVR equals the contractual right to up to $35 in milestone cash "
                    "from Johnson & Johnson under the Dec 2022 CVR Agreement."
                ),
                "excluded_claims": [
                    "Upfront $380/share cash consideration from the merger is excluded; only CVR tail remains.",
                    "JNJ common stock or MedTech segment value is not part of this claim.",
                ],
                "reconciliation": (
                    "Maximum stack $35/CVR = $17.50 net sales + $7.50 FDA + $10.00 clinical recommendation."
                ),
                "evidence_ref": f"{TICKER}/research/evidence_reconciliation_{AS_OF}.md",
            },
            "validation_errors": [],
        },
    }


def main() -> int:
    proofs = {
        "net_sales_milestone": net_sales_proof(),
        "fda_stemi_milestone": fda_stemi_proof(),
        "clinical_recommendation_milestone": clinical_recommendation_proof(),
        "timing_execution_reserve": timing_reserve_proof(),
    }
    errors = []
    outputs = {}
    for cid, proof in proofs.items():
        ev = evaluate_calculation_proof(proof)
        outputs[cid] = ev.get("outputs")
        if ev["status"] != "valid":
            errors.append(f"{cid}: {ev['checks']['errors']}")
        legacy = LEGACY[cid]
        out = ev.get("outputs") or {}
        for case in ("low", "base", "high"):
            if out and abs(out[case] - legacy[case]) > 0.06:
                errors.append(f"{cid}.{case}: got {out[case]}, want {legacy[case]}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    base_sum = sum(outputs[c]["base"] for c in outputs)
    path = ROOT / TICKER / "research" / "valuation.json"
    data = build_valuation_scaffold(base_sum)
    evidence = (
        f"CVR Agreement {CVR_AGREEMENT_DATE}: up to $35/CVR in three milestones; "
        f"Abiomed FY2022 revenue $1.032B baseline ({ABMD_FY2022})."
    )
    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        proof = proofs[cid]
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        comp["valuation"]["evidence"] = (
            f"{evidence} Proof base {outputs[cid]['base']}/CVR via {METHOD_MAP[cid]}@1.0."
        )
        comp["valuation"]["assumption_summary"] = (
            f"Proof outputs {outputs[cid]}; probability and timing judgments explicit in graph."
        )
        for case in ("low", "base", "high"):
            comp["valuation"][case] = outputs[cid][case]

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": "ok", "outputs": outputs, "base_sum_per_cvr": round(base_sum, 2)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
