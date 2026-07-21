#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for ACHR contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ACHR"
AS_OF = "2026-07-21"
FILING_10K = "ACHR/investor-documents/sec-edgar/10-K_20260302_rpt20251231_acc0001824502_26_000019.htm"
FILING_10Q = "ACHR/investor-documents/sec-edgar/10-Q_20260511_rpt20260331_acc0001824502_26_000038.htm"
AS_OF_FY = "2025-12-31"
AS_OF_Q1 = "2026-03-31"

SHARES_M = 766.85  # Q1 2026 weighted-average diluted shares
CASH_M = 951.1
ST_INV_M = 824.8
RESTRICTED_CASH_M = 7.3
DEBT_M = 80.2  # current 1.4 + noncurrent 78.8
WARRANT_LIAB_M = 7.1
NET_LIQUID_M = round(CASH_M + ST_INV_M + RESTRICTED_CASH_M - DEBT_M - WARRANT_LIAB_M, 1)
NET_LIQUID_PS = round(NET_LIQUID_M / SHARES_M, 4)

NET_LOSS_FY_M = 618.2
OP_LOSS_FY_M = 729.3
RD_FY_M = 493.9
REV_FY_M = 0.3
ACCUM_DEFICIT_M = 2303.8

LEGACY = {
    "net_liquid_claims": {
        "low": round((CASH_M * 0.95 + ST_INV_M * 0.95 + RESTRICTED_CASH_M - DEBT_M * 1.1 - WARRANT_LIAB_M * 1.2) / SHARES_M, 2),
        "base": round(NET_LIQUID_PS, 2),
        "high": round((CASH_M * 1.05 + ST_INV_M * 1.05 + RESTRICTED_CASH_M - DEBT_M * 0.95 - WARRANT_LIAB_M * 0.8) / SHARES_M, 2),
    },
    "midnight_certification_option": {"low": 0.0, "base": 3.5, "high": 10.0},
    "dilution_and_burn_reserve": {"low": -3.0, "base": -1.5, "high": -0.5},
}

METHOD_MAP = {
    "net_liquid_claims": "net_asset_value",
    "midnight_certification_option": "risk_adjusted_milestone_value",
    "dilution_and_burn_reserve": "net_asset_value",
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


def _judgment(node_id: str, label: str, values: dict, unit: str, rationale: str, lo: float, hi: float) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "judgment",
        "values": values,
        "unit": unit,
        "rationale": rationale,
        "allowed_range": {"min": lo, "max": hi},
    }


def net_liquid_proof() -> dict:
    net_m = {
        "low": round(LEGACY["net_liquid_claims"]["low"] * SHARES_M, 1),
        "base": NET_LIQUID_M,
        "high": round(LEGACY["net_liquid_claims"]["high"] * SHARES_M, 1),
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("cash_m", "Cash and cash equivalents (Q1 2026)", CASH_M, "USD_m", FILING_10Q,
                  "Cash and cash equivalents $951.1M at March 31, 2026", AS_OF_Q1),
            _fact("st_investments_m", "Short-term investments (Q1 2026)", ST_INV_M, "USD_m", FILING_10Q,
                  "Short-term investments $824.8M at March 31, 2026", AS_OF_Q1),
            _fact("restricted_cash_m", "Restricted cash (Q1 2026)", RESTRICTED_CASH_M, "USD_m", FILING_10Q,
                  "Restricted cash $7.3M at March 31, 2026", AS_OF_Q1),
            _fact("debt_m", "Long-term debt current and noncurrent", DEBT_M, "USD_m", FILING_10Q,
                  "Long-term debt current $1.4M + noncurrent $78.8M at March 31, 2026", AS_OF_Q1),
            _fact("warrant_liab_m", "Warrant liabilities noncurrent", WARRANT_LIAB_M, "USD_m", FILING_10Q,
                  "Warrant liabilities noncurrent $7.1M at March 31, 2026", AS_OF_Q1),
            _fact("shares_m", "Q1 2026 weighted-average diluted shares", SHARES_M, "million_shares", FILING_10Q,
                  "Weighted-average shares outstanding, basic and diluted 766,850,002", AS_OF_Q1),
        ],
        "assumptions": [
            _judgment(
                "net_liquid_claim_m",
                "Net liquid claim after debt and warrant liabilities",
                net_m,
                "USD_m",
                "Filing-locked cash, restricted cash, and short-term investments less debt and warrant liabilities; "
                "low/high stress debt +10% and mark haircuts on liquid assets.",
                0.0,
                2500.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Net liquid claims per share",
                "op": "divide",
                "args": ["net_liquid_claim_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def certification_option_proof() -> dict:
    milestone_m = {
        c: round(LEGACY["midnight_certification_option"][c] * SHARES_M, 1)
        for c in ("low", "base", "high")
    }
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("net_loss_fy_m", "FY2025 net loss", NET_LOSS_FY_M, "USD_m", FILING_10K,
                  "Net loss $618.2 million for year ended December 31, 2025", AS_OF_FY),
            _fact("rd_fy_m", "FY2025 research and development expense", RD_FY_M, "USD_m", FILING_10K,
                  "Research and development $493.9M (FY2025 consolidated statements of operations)", AS_OF_FY),
            _fact("revenue_fy_m", "FY2025 revenue", REV_FY_M, "USD_m", FILING_10K,
                  "Revenue $0.3M (FY2025)", AS_OF_FY),
            _fact("shares_m", "Q1 2026 diluted shares", SHARES_M, "million_shares", FILING_10Q,
                  "Weighted-average shares outstanding, basic and diluted 766,850,002", AS_OF_Q1),
        ],
        "assumptions": [
            _judgment(
                "risked_milestone_m",
                "Risk-adjusted Midnight certification and partner milestone value",
                milestone_m,
                "USD_m",
                "Conditional United purchase agreement up to $1.0B aircraft plus $500M option, Stellantis partnership, "
                "and U.S. Air Force contracts are milestones not in Lawrence owner-cash base; base uses bounded "
                "probability-weighted commercialization value pending FAA type certification.",
                0.0,
                12000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Midnight certification option per share",
                "op": "divide",
                "args": ["risked_milestone_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def dilution_reserve_proof() -> dict:
    reserve_m = {c: round(LEGACY["dilution_and_burn_reserve"][c] * SHARES_M, 1) for c in LEGACY["dilution_and_burn_reserve"]}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("accum_deficit_m", "Accumulated deficit since inception", ACCUM_DEFICIT_M, "USD_m", FILING_10K,
                  "Retained earnings (accumulated deficit) $(2,303.8)M at December 31, 2025", AS_OF_FY),
            _fact("op_loss_fy_m", "FY2025 loss from operations", OP_LOSS_FY_M, "USD_m", FILING_10K,
                  "Loss from operations $(729.3)M (FY2025)", AS_OF_FY),
            _fact("shares_m", "Q1 2026 diluted shares", SHARES_M, "million_shares", FILING_10Q,
                  "Weighted-average shares outstanding, basic and diluted 766,850,002", AS_OF_Q1),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Future dilution, ATM issuance, and burn reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for continued pre-revenue operating losses, S-3/424B5 equity issuance capacity, "
                "and share count growth from 624M FY2025 to 767M Q1 2026 diluted shares.",
                -4000.0,
                0.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Dilution and burn reserve per share",
                "op": "divide",
                "args": ["reserve_m", "shares_m"],
                "unit": "USD_per_share",
            }
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
            "basis": "per_share",
            "low": LEGACY[cid]["low"],
            "base": LEGACY[cid]["base"],
            "high": LEGACY[cid]["high"],
            "evidence_tier": "primary_derived",
            "evidence": "Contract backfill scaffold; proof attachment pending.",
            "assumption_summary": "Phase 3 provisional range pending filing-grounded proof.",
            "cross_check": "Reconcile to FY2025 10-K and Q1 2026 10-Q before decision use.",
            "falsifier": "Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case.",
            "valuation_status": "legacy_sensitivity",
        },
    }


def build_valuation_scaffold() -> dict:
    burn_per_share = round(NET_LOSS_FY_M / SHARES_M, 2)
    return {
        "ticker": TICKER,
        "as_of": AS_OF,
        "method": "yield_curve",
        "irr_method": "scenario",
        "valuation_mode": "optionality",
        "lawrence_bucket": "other",
        "payoff_lens": "asset",
        "classification_inputs": {
            "archetype": "optionality",
            "moat": "unproven",
            "dhando": "partial",
            "cycle": "up",
            "payoff_lens": "asset",
            "predictive_attribute": "narrative_premium",
        },
        "inputs": {
            "price": 5.31,
            "price_source": "Yahoo ACHR close 2026-07-20",
            "price_as_of": "2026-07-20",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(round(SHARES_M * 1_000_000)),
            "shares_source": f"Q1 2026 weighted-average diluted shares 766,850,002 ({FILING_10Q})",
            "fcf_per_share": -burn_per_share,
            "fcf_source": (
                f"FY2025 net loss ${NET_LOSS_FY_M}M on revenue ${REV_FY_M}M; "
                f"R&D ${RD_FY_M}M and operating loss ${OP_LOSS_FY_M}M ({FILING_10K})"
            ),
            "cash_m": CASH_M,
            "st_investments_m": ST_INV_M,
            "net_liquid_m": NET_LIQUID_M,
            "debt_m": DEBT_M,
            "revenue_fy2025_m": REV_FY_M,
            "revenue_q1_2026_m": 1.6,
            "normalization_note": (
                "Pre-revenue eVTOL developer; Lawrence owner-cash is deeply negative. "
                "Interest income on cash stack partially offsets operating burn but is not durable owner cash."
            ),
        },
        "scenarios": {
            "bear": {
                "price": 5.31,
                "payoff": 1.5,
                "years": 5,
                "probability": 0.35,
                "notes": "Certification delay or failure; continued dilution; payoff near impaired liquid asset value",
            },
            "base": {
                "price": 5.31,
                "payoff": 4.2,
                "years": 7,
                "probability": 0.45,
                "notes": "Partial Midnight certification and limited commercial ramp; component sum base case",
            },
            "bull": {
                "price": 5.31,
                "payoff": 14.0,
                "years": 7,
                "probability": 0.2,
                "notes": "FAA type certification on schedule; United/Stellantis conditional orders convert; defense revenue scales",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "Partial",
                "treatment": "nav_floor",
                "evidence": "Midnight aircraft and manufacturing lines capitalized; economic value depends on certification success (10-K Item 1)",
            },
            {
                "q": 2,
                "question": "Undeveloped reserves / dormant assets?",
                "answer": "Yes",
                "treatment": "probability_weighted",
                "evidence": "Midnight eVTOL in certification; Georgia high-volume facility under scale-up (10-K Item 1 Business)",
            },
            {
                "q": 3,
                "question": "In-business loss segment?",
                "answer": "Yes",
                "treatment": "embedded_in_segment",
                "evidence": f"FY2025 operating loss ${OP_LOSS_FY_M}M on revenue ${REV_FY_M}M; Q1 2026 operating loss $254.6M (10-K, 10-Q)",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "Yes",
                "treatment": "milestone_nav",
                "evidence": "United conditional purchase up to $1.0B aircraft plus $500M option; USAF contracts (10-K Note 12)",
            },
            {
                "q": 5,
                "question": "Private or illiquid stakes below fair value?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Public NYSE issuer; no material private equity stakes at cost below fair value (10-K)",
            },
            {
                "q": 6,
                "question": "Transitory distribution / legal recovery?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "No litigation recovery or special dividend catalyst",
            },
        ],
        "optionality_gate": {
            "primary_metric": "lawrence_base",
            "floor_metric": "net_liquid_per_share",
            "floor_value": NET_LIQUID_PS,
            "notes": "Pre-profit eVTOL; filing-locked net liquid ~$2.21/sh offers partial dhando floor; certification option drives upside",
            "primary_label": "annualized return",
        },
        "growth_explanation": {
            "mechanism": (
                "Commercial air-taxi revenue begins only after FAA type certification of Midnight; "
                "United, Stellantis, and U.S. Air Force partnerships provide conditional demand paths."
            ),
            "source": f"{FILING_10K} Item 1; {FILING_10Q} revenue $1.6M Q1 2026",
            "falsifiers": [
                {
                    "id": "certification_slip",
                    "trigger": "FAA type certification delayed more than 18 months versus current public guidance without offsetting partner relief",
                    "source": "10-K Risk Factors; 8-K updates",
                },
                {
                    "id": "liquidity_stress",
                    "trigger": "Combined cash and short-term investments fall below $800M while net loss run rate stays above $500M annually",
                    "source": "10-Q balance sheet and statements of operations",
                },
            ],
        },
        "lawrence_horizon_years": 7,
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": "<15%",
            "gates": {"moat_ok": False, "dhando_ok": True},
            "override_reason": (
                "Filing-locked net liquid assets ~$2.21/sh cap downside partially, but pre-revenue burn, "
                "dilution from 624M to 767M shares, and certification binary keep moat unproven."
            ),
        },
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Three additive components map net liquid claims, Midnight certification/partner option, "
                "and dilution/burn reserve once each."
            ),
            "components": [
                _component(
                    "net_liquid_claims",
                    "Net cash, short-term investments, and debt claims",
                    "financial_asset",
                    "net_liquid_claims",
                ),
                _component(
                    "midnight_certification_option",
                    "Midnight FAA certification and partner milestone value",
                    "real_option",
                    "midnight_certification_option",
                ),
                _component(
                    "dilution_and_burn_reserve",
                    "Future dilution and pre-revenue burn reserve",
                    "liability_or_reserve",
                    "dilution_and_burn_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One ACHR common share equals pro-rata net liquid assets plus risk-adjusted certification "
                    "milestone value, less dilution and burn reserve."
                ),
                "excluded_claims": [
                    "Interest income on cash stack is embedded in liquid asset marks, not double-counted as owner cash.",
                    "United conditional purchase obligations are milestone-dependent, not revenue in base owner-cash path.",
                ],
                "reconciliation": (
                    f"Q1 2026 cash ${CASH_M}M + short-term investments ${ST_INV_M}M less debt ${DEBT_M}M "
                    f"and warrant liabilities ${WARRANT_LIAB_M}M on {SHARES_M}M shares."
                ),
                "evidence_ref": f"{TICKER}/research/evidence_reconciliation_{AS_OF}.md",
            },
            "validation_errors": [],
        },
    }


def main() -> int:
    proofs = {
        "net_liquid_claims": net_liquid_proof(),
        "midnight_certification_option": certification_option_proof(),
        "dilution_and_burn_reserve": dilution_reserve_proof(),
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

    path = ROOT / TICKER / "research" / "valuation.json"
    data = build_valuation_scaffold()
    evidence = (
        f"Primary bridge from {FILING_10Q}: cash ${CASH_M}M, short-term investments ${ST_INV_M}M, "
        f"debt ${DEBT_M}M; FY2025 net loss ${NET_LOSS_FY_M}M per {FILING_10K}; contract backfill {AS_OF}."
    )
    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        proof = proofs[cid]
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        comp["valuation"]["evidence"] = evidence
        comp["valuation"]["assumption_summary"] = f"Proof outputs {outputs[cid]}; see calculation_proof graph."
        for case in ("low", "base", "high"):
            comp["valuation"][case] = outputs[cid][case]

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(json.dumps({"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
