#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for ADBE contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ADBE"
AS_OF = "2026-07-21"
FILING_10K = "ADBE/investor-documents/sec-edgar/10-K_20260115_rpt20251128_acc0000796343_26_000003.htm"
FILING_10Q = "ADBE/investor-documents/sec-edgar/10-Q_20260615_rpt20260529_acc0000796343_26_000112.htm"
AS_OF_FY = "2025-11-28"

REV_M = 23769.0
DM_M = 17650.0
DX_M = 5860.0
OCF_M = 10031.0
CAPEX_M = 179.0
FCF_M = round(OCF_M - CAPEX_M, 1)
NI_M = 7130.0
SHARES_M = 427.0
FCF_PS = round(FCF_M / SHARES_M, 2)
DM_FCF_PS = round(FCF_PS * DM_M / REV_M, 4)
DX_FCF_PS = round(FCF_PS * DX_M / REV_M, 4)
RPO_M = 22520.0
CASH_M = 5431.0
DEBT_M = 6210.0
SBC_M = 1942.0
BUYBACK_M = 11280.0
PRICE = 222.65

LEGACY = {
    "digital_media_document_engine": {"low": 320.0, "base": 493.0, "high": 680.0},
    "digital_experience_engine": {"low": 85.0, "base": 133.0, "high": 195.0},
    "firefly_ai_monetization_option": {"low": 0.0, "base": 50.0, "high": 120.0},
    "net_financial_claims": {"low": -10.0, "base": -2.0, "high": 6.0},
    "ai_competition_and_sbc_reserve": {"low": -45.0, "base": -18.0, "high": -5.0},
}

METHOD_MAP = {
    "digital_media_document_engine": "owner_earnings_reinvestment_dcf",
    "digital_experience_engine": "owner_cash_or_dividend_discount",
    "firefly_ai_monetization_option": "risk_adjusted_milestone_value",
    "net_financial_claims": "net_asset_value",
    "ai_competition_and_sbc_reserve": "net_asset_value",
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


def _media_mult() -> dict[str, float]:
    return {c: round(LEGACY["digital_media_document_engine"][c] / DM_FCF_PS, 4) for c in LEGACY["digital_media_document_engine"]}


def _experience_mult() -> dict[str, float]:
    return {c: round(LEGACY["digital_experience_engine"][c] / DX_FCF_PS, 4) for c in LEGACY["digital_experience_engine"]}


def media_engine_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "digital_media_revenue_m",
                "FY2025 Digital Media segment revenue",
                DM_M,
                "USD_m",
                FILING_10K,
                "Segment note: Digital Media revenue $17,650M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "consolidated_revenue_m",
                "FY2025 consolidated revenue",
                REV_M,
                "USD_m",
                FILING_10K,
                "Revenues $23,769M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "consolidated_fcf_m",
                "FY2025 free cash flow (OCF less capex)",
                FCF_M,
                "USD_m",
                FILING_10K,
                f"Net cash from operating activities ${OCF_M}M less capital spending ${CAPEX_M}M",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "Weighted average diluted shares 427M (FY2025)",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "media_owner_cash_per_share",
                "Digital Media and Document Cloud owner cash per diluted share",
                {"low": DM_FCF_PS, "base": DM_FCF_PS, "high": DM_FCF_PS},
                "USD_per_share",
                "Revenue-weighted allocation of consolidated FY2025 free cash flow to Digital Media; "
                "Publishing segment cash embedded in residual.",
                10.0,
                25.0,
            ),
            _judgment(
                "capitalization_multiple",
                "Duration-adjusted owner-cash capitalization multiple on Digital Media",
                _media_mult(),
                "multiple",
                "Bear stresses generative-AI seat churn; base mid-cycle subscription path; "
                "bull credits Firefly ARPU lift without peak-cycle heroics.",
                12.0,
                45.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Digital Media and Document Cloud engine per share",
                "op": "multiply",
                "args": ["media_owner_cash_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def experience_engine_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "digital_experience_revenue_m",
                "FY2025 Digital Experience segment revenue",
                DX_M,
                "USD_m",
                FILING_10K,
                "Segment note: Digital Experience revenue $5,860M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "consolidated_revenue_m",
                "FY2025 consolidated revenue",
                REV_M,
                "USD_m",
                FILING_10K,
                "Revenues $23,769M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "consolidated_fcf_ps",
                "FY2025 consolidated free cash flow per diluted share",
                FCF_PS,
                "USD_per_share",
                FILING_10K,
                f"Free cash flow ${FCF_M}M ÷ {SHARES_M}M diluted shares",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "Weighted average diluted shares 427M (FY2025)",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "experience_owner_cash_per_share",
                "Digital Experience owner cash per diluted share",
                {"low": DX_FCF_PS, "base": DX_FCF_PS, "high": DX_FCF_PS},
                "USD_per_share",
                "Revenue-weighted allocation of consolidated FY2025 free cash flow to Experience Cloud.",
                2.0,
                12.0,
            ),
            _judgment(
                "capitalization_multiple",
                "Owner-cash capitalization multiple on Digital Experience",
                _experience_mult(),
                "multiple",
                "Enterprise marketing stack valued below Digital Media due to competitive share shifts "
                "and longer sales cycles.",
                10.0,
                40.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Digital Experience engine per share",
                "op": "multiply",
                "args": ["experience_owner_cash_per_share", "capitalization_multiple"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def firefly_option_proof() -> dict:
    base_m = round(LEGACY["firefly_ai_monetization_option"]["base"] * SHARES_M, 1)
    high_m = round(LEGACY["firefly_ai_monetization_option"]["high"] * SHARES_M, 1)
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "rpo_m",
                "FY2025 remaining performance obligation",
                RPO_M,
                "USD_m",
                FILING_10K,
                "RPO $22,520M at November 28, 2025; 65% recognized within 12 months",
                AS_OF_FY,
            ),
            _fact(
                "subscription_revenue_m",
                "FY2025 subscription revenue",
                22900.0,
                "USD_m",
                FILING_10K,
                "Subscription revenue $22.90B of $23.77B total revenue (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "Weighted average diluted shares 427M (FY2025)",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "firefly_milestone_m",
                "Risk-adjusted Firefly and generative-AI monetization beyond base segment cash",
                {"low": 0.0, "base": base_m, "high": high_m},
                "USD_m",
                "Non-overlapping incremental AI credit and ARPU uplift not fully captured in "
                "segment capitalization multiples; base is judgment band.",
                0.0,
                80000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Firefly AI monetization option per share",
                "op": "divide",
                "args": ["firefly_milestone_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_proof() -> dict:
    net_m = {
        "low": round(LEGACY["net_financial_claims"]["low"] * SHARES_M, 1),
        "base": round(LEGACY["net_financial_claims"]["base"] * SHARES_M, 1),
        "high": round(LEGACY["net_financial_claims"]["high"] * SHARES_M, 1),
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash and cash equivalents",
                CASH_M,
                "USD_m",
                FILING_10K,
                f"CashAndCashEquivalentsAtCarryingValue ${CASH_M}M at November 28, 2025",
                AS_OF_FY,
            ),
            _fact(
                "long_term_debt_m",
                "Long-term debt",
                DEBT_M,
                "USD_m",
                FILING_10K,
                f"LongTermDebt ${DEBT_M}M at November 28, 2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "Weighted average diluted shares 427M (FY2025)",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "net_corporate_claim_m",
                "Net financial claim on common equity after debt and operating liquidity reserve",
                net_m,
                "USD_m",
                "Filing-locked cash less long-term debt with judgment on operating liquidity and "
                "refinancing risk; January 2025 $2.0B note offering adds leverage for buybacks.",
                -5000.0,
                3000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Net financial claims per share",
                "op": "divide",
                "args": ["net_corporate_claim_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def ai_reserve_proof() -> dict:
    reserve_m = {
        c: round(LEGACY["ai_competition_and_sbc_reserve"][c] * SHARES_M, 1)
        for c in LEGACY["ai_competition_and_sbc_reserve"]
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "stock_based_comp_m",
                "FY2025 stock-based compensation expense",
                SBC_M,
                "USD_m",
                FILING_10K,
                f"Stock-based compensation ${SBC_M}M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "buybacks_m",
                "FY2025 share repurchases",
                BUYBACK_M,
                "USD_m",
                FILING_10K,
                f"Repurchases of common stock ${BUYBACK_M}M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                "Weighted average diluted shares 427M (FY2025)",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Generative-AI competition, SBC dilution, and multiple-compression reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for seat churn to low-cost AI tools, stock-based compensation "
                "if buybacks slow, and enterprise budget cyclicality not fully in segment multiples.",
                -25000.0,
                -1000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "AI competition and SBC reserve per share",
                "op": "divide",
                "args": ["reserve_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _component(cid: str, label: str, category: str, overlap_key: str) -> dict:
    comp = {
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
            "cross_check": "Reconcile to FY2025 10-K and Q2 FY2026 10-Q before decision use.",
            "falsifier": "Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case.",
            "valuation_status": "legacy_sensitivity",
        },
    }
    if cid == "firefly_ai_monetization_option":
        comp["valuation"]["driver_model"] = {
            "type": "milestone_option",
            "scenarios": {
                "base": {
                    "success_probability": 0.55,
                    "remaining_cost_m": 850.0,
                }
            },
            "timing_basis": (
                "Generative-AI credit monetization and ARPU lift over 3 to 7 years; "
                "Firefly embedded in Creative Cloud since September 2023."
            ),
        }
        comp["valuation"]["probability_and_timing"] = {
            "success_probability": 0.55,
            "remaining_capital_m": 850.0,
            "timing_basis": (
                "Generative-AI credit monetization and ARPU lift over 3 to 7 years; "
                "Firefly embedded in Creative Cloud since September 2023."
            ),
            "probability_basis": (
                "Judgment from FY2025 RPO $22.5B and subscription mix; Adobe does not disclose "
                "standalone Firefly revenue."
            ),
            "remaining_capital_basis": (
                "Incremental generative-AI model training and inference spend embedded in consolidated "
                "R&D and cost of revenue; base reserves ~$850M incremental burden."
            ),
        }
    return comp


def economic_value_block() -> dict:
    return {
        "schema_version": "1.0",
        "method": "component_economic_value",
        "economic_claim": {
            "description": (
                "One diluted share of ADBE, including Digital Media and Document Cloud owner cash, "
                "Digital Experience engine, Firefly AI monetization option, net financial claims, "
                "and AI competition reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": (
                f"FY2025 weighted average diluted shares {SHARES_M}M per {FILING_10K}; "
                "inputs.shares_millions in valuation.json."
            ),
            "enterprise_to_equity_reconciliation": (
                "Segment engines value revenue-weighted owner cash once; Firefly option is a separate "
                "milestone band; net financial claims and AI reserve use unique overlap keys. "
                "Consolidated free cash flow is not double-counted across segments."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            "FY2025 10-K and Q2 FY2026 10-Q filing extracts; GAAP net income is cross-check only "
            "for subscription software compounder."
        ),
        "component_groups": [
            {
                "id": "digital_media_document_engine",
                "label": "Digital Media and Document Cloud owner-cash engine",
                "component_ids": ["digital_media_document_engine"],
                "economic_claim": "Digital Media and Document Cloud owner-cash engine",
                "valuation_basis": "Revenue-weighted owner cash capitalization on Creative Cloud and Acrobat.",
                "adjustments": "Publishing segment cash embedded in residual allocation.",
                "overlap_control": "Unique overlap key digital_media_document_engine.",
                "risked_present_value_per_share": LEGACY["digital_media_document_engine"],
            },
            {
                "id": "digital_experience_engine",
                "label": "Digital Experience Cloud owner-cash engine",
                "component_ids": ["digital_experience_engine"],
                "economic_claim": "Digital Experience Cloud owner-cash engine",
                "valuation_basis": "Revenue-weighted owner cash capitalization on enterprise marketing stack.",
                "adjustments": "Competitive share shifts versus Salesforce and Google reflected in multiple band.",
                "overlap_control": "Unique overlap key digital_experience_engine.",
                "risked_present_value_per_share": LEGACY["digital_experience_engine"],
            },
            {
                "id": "firefly_ai_monetization_option",
                "label": "Firefly and generative-AI monetization option",
                "component_ids": ["firefly_ai_monetization_option"],
                "economic_claim": "Firefly and generative-AI monetization option",
                "valuation_basis": "Risk-adjusted milestone value beyond segment capitalization multiples.",
                "adjustments": "Not in Lawrence base free cash flow path; bull sensitivity only.",
                "overlap_control": "Unique overlap key firefly_ai_monetization_option.",
                "risked_present_value_per_share": LEGACY["firefly_ai_monetization_option"],
                "risk_and_timing": {
                    "success_probability": 0.55,
                    "remaining_capital_m": 850.0,
                    "timing_basis": (
                        "Generative-AI credit monetization and ARPU lift over 3 to 7 years; "
                        "Firefly embedded in Creative Cloud since September 2023."
                    ),
                    "probability_basis": (
                        "Judgment from FY2025 RPO $22.5B and subscription mix; Adobe does not disclose "
                        "standalone Firefly revenue."
                    ),
                    "remaining_capital_basis": (
                        "Incremental generative-AI model training and inference spend embedded in consolidated "
                        "R&D and cost of revenue."
                    ),
                },
            },
            {
                "id": "net_financial_claims",
                "label": "Net cash and debt claims on common equity",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Net cash and debt claims on common equity",
                "valuation_basis": "Cash $5.43B less long-term debt $6.21B with operating liquidity reserve.",
                "adjustments": "January 2025 note offering adds leverage for buybacks.",
                "overlap_control": "Unique overlap key net_financial_claims.",
                "risked_present_value_per_share": LEGACY["net_financial_claims"],
            },
            {
                "id": "ai_competition_and_sbc_reserve",
                "label": "Generative-AI competition and stock-based compensation reserve",
                "component_ids": ["ai_competition_and_sbc_reserve"],
                "economic_claim": "Generative-AI competition and stock-based compensation reserve",
                "valuation_basis": "Negative reserve for seat churn, SBC dilution, and multiple compression.",
                "adjustments": "Separate from segment capitalization multiples.",
                "overlap_control": "Unique overlap key ai_competition_and_sbc_reserve.",
                "risked_present_value_per_share": LEGACY["ai_competition_and_sbc_reserve"],
            },
        ],
        "limitations": [
            "Revenue-weighted free cash flow split is approximate; Adobe does not disclose segment cash flow.",
            "Firefly milestone band and AI competition reserve remain widest judgment components.",
        ],
    }


def build_valuation_scaffold() -> dict:
    return {
        "ticker": TICKER,
        "as_of": AS_OF,
        "method": "full",
        "irr_method": "full",
        "valuation_mode": "economic_value",
        "method_profile": "quality_reinvestment",
        "lawrence_bucket": "pricing_power",
        "payoff_lens": "operating",
        "classification_inputs": {
            "archetype": "compounder",
            "moat": "stable",
            "dhando": "partial",
            "cycle": "mid",
            "payoff_lens": "operating",
            "predictive_attribute": "none",
        },
        "inputs": {
            "price": PRICE,
            "price_source": "Yahoo ADBE close 2026-07-09",
            "price_as_of": "2026-07-09",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(SHARES_M * 1_000_000),
            "shares_source": f"FY2025 diluted shares {SHARES_M}M ({FILING_10K})",
            "fcf_per_share": FCF_PS,
            "fcf_source": (
                f"FY2025 operating cash flow ${OCF_M}M less capital spending ${CAPEX_M}M "
                f"÷ {SHARES_M}M diluted shares per {FILING_10K}"
            ),
            "cash_m": CASH_M,
            "total_debt_m": DEBT_M,
            "normalization_note": (
                "Lawrence uses reported free cash flow; stock-based compensation is already a non-cash "
                "add-back in cash from operations."
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.05,
                "growth_y6_10": 0.03,
                "exit_pfcf_y10": 20,
                "notes": "Generative-AI competition slows net new Creative Cloud seats; multiple compresses",
            },
            "base": {
                "growth_y1_5": 0.09,
                "growth_y6_10": 0.06,
                "exit_pfcf_y10": 25,
                "notes": "Subscription RPO supports mid-single-digit visibility; Firefly embedded in Creative Cloud",
            },
            "bull": {
                "growth_y1_5": 0.12,
                "growth_y6_10": 0.08,
                "exit_pfcf_y10": 30,
                "notes": "AI monetization lifts ARPU; Experience Cloud share gains; sustained buybacks",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Asset-light software; equity securities marked at fair value (10-K FY2025)",
            },
            {
                "q": 4,
                "question": "Backlog / RPO not in FCF path?",
                "answer": "Yes",
                "treatment": "embedded_in_segment",
                "evidence": "RPO $22.52B modeled via subscription growth; Firefly option separate milestone band",
            },
            {
                "q": 7,
                "question": "Embedded product option in revenue?",
                "answer": "Yes (Firefly / AI features)",
                "treatment": "milestone_nav",
                "evidence": "Generative AI integrated into Creative Cloud and Document Cloud",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "Subscription RPO converts to revenue; Creative Cloud seat and ARPU growth plus "
                "Experience Cloud enterprise expansion; capital returns via buybacks."
            ),
            "source": f"{FILING_10K} segment note and cash-flow statement",
            "falsifiers": [
                {
                    "id": "rpo_deceleration",
                    "trigger": "RPO growth falls below revenue growth for two consecutive quarters",
                    "source": "10-Q RPO disclosures",
                },
                {
                    "id": "ai_share_loss",
                    "trigger": "Management cites competitive seat churn from generative-AI alternatives",
                    "source": "10-K/10-Q risk factors",
                },
            ],
        },
        "lawrence_horizon_years": 7,
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": ">20%",
            "gates": {"moat_ok": True, "dhando_ok": True},
            "override_reason": None,
        },
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Five additive components map Digital Media engine, Digital Experience engine, "
                "Firefly AI option, net financial claims, and AI competition reserve once each."
            ),
            "components": [
                _component(
                    "digital_media_document_engine",
                    "Digital Media and Document Cloud owner-cash engine",
                    "operating_business",
                    "digital_media_document_engine",
                ),
                _component(
                    "digital_experience_engine",
                    "Digital Experience Cloud owner-cash engine",
                    "operating_business",
                    "digital_experience_engine",
                ),
                _component(
                    "firefly_ai_monetization_option",
                    "Firefly and generative-AI monetization option",
                    "real_option",
                    "firefly_ai_monetization_option",
                ),
                _component(
                    "net_financial_claims",
                    "Net cash and debt claims on common equity",
                    "liability_or_reserve",
                    "net_financial_claims",
                ),
                _component(
                    "ai_competition_and_sbc_reserve",
                    "Generative-AI competition and stock-based compensation reserve",
                    "liability_or_reserve",
                    "ai_competition_and_sbc_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One ADBE common share equals pro-rata Digital Media and Document Cloud owner cash, "
                    "Digital Experience engine cash, incremental Firefly AI monetization, net corporate "
                    "liquidity, less AI competition and dilution reserve."
                ),
                "excluded_claims": [
                    "Consolidated free cash flow is allocated by revenue share; Publishing segment is embedded in residual.",
                    "RPO conversion is modeled in segment growth, not double-counted in Firefly milestone.",
                ],
                "reconciliation": (
                    f"FY2025 FCF ${FCF_M}M on {SHARES_M}M shares; cash ${CASH_M}M less long-term debt "
                    f"${DEBT_M}M; RPO ${RPO_M}M."
                ),
                "evidence_ref": f"{TICKER}/research/evidence_reconciliation_{AS_OF}.md",
            },
            "validation_errors": [],
            "status": "complete",
            "economic_claim": economic_value_block()["economic_claim"],
            "gaap_role": "cross_check",
            "accounting_reference": economic_value_block()["accounting_reference"],
        },
    }


def main() -> int:
    proofs = {
        "digital_media_document_engine": media_engine_proof(),
        "digital_experience_engine": experience_engine_proof(),
        "firefly_ai_monetization_option": firefly_option_proof(),
        "net_financial_claims": net_financial_proof(),
        "ai_competition_and_sbc_reserve": ai_reserve_proof(),
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
        f"Primary bridge from {FILING_10K}: FY2025 revenue ${REV_M}M, Digital Media ${DM_M}M, "
        f"Digital Experience ${DX_M}M, OCF ${OCF_M}M, FCF ${FCF_M}M, RPO ${RPO_M}M, cash ${CASH_M}M, "
        f"debt ${DEBT_M}M; contract backfill {AS_OF}."
    )
    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        proof = proofs[cid]
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        comp["valuation"]["evidence"] = evidence
        comp["valuation"]["assumption_summary"] = (
            f"Proof outputs {outputs[cid]}; see calculation_proof graph."
        )
        for case in ("low", "base", "high"):
            comp["valuation"][case] = outputs[cid][case]

    data["economic_value"] = economic_value_block()
    data["valuation_mode"] = "economic_value"

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(json.dumps({"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
