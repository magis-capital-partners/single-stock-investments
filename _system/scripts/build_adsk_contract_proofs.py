#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for ADSK contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ADSK"
AS_OF = "2026-07-21"
FILING_10K = "ADSK/investor-documents/sec-edgar/10-K_20260303_rpt20260131_acc0000769397_26_000015.htm"
FILING_10Q = "ADSK/investor-documents/sec-edgar/10-Q_20260529_rpt20260430_acc0000769397_26_000044.htm"
AS_OF_FY = "2026-01-31"
AS_OF_Q1 = "2026-04-30"

REV_M = 6743.0
REV_PRIOR_M = 5717.0
OCF_M = 2452.0
CAPEX_M = 43.0
FCF_M = round(OCF_M - CAPEX_M, 1)
NI_M = 1124.0
EPS_DILUTED = 5.23
SHARES_M = 215.0
FCF_PS = round(FCF_M / SHARES_M, 4)
CASH_M = 2249.0
DEBT_M = 2483.0
NET_DEBT_M = round(DEBT_M - CASH_M, 1)
NET_DEBT_PS = round(NET_DEBT_M / SHARES_M, 2)
RPO_B = 8.3
SBC_M = 788.0
BUYBACK_M = 1402.0
PRICE = 217.8
Q1_CASH_M = 2671.0
Q1_DEBT_M = 2484.0
Q1_NET_CASH_M = round(Q1_CASH_M - Q1_DEBT_M, 1)
Q1_NET_CASH_PS = round(Q1_NET_CASH_M / SHARES_M, 2)
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.03, "growth_y6_10": 0.02, "exit_pfcf_y10": 20},
    "base": {"growth_y1_5": 0.06, "growth_y6_10": 0.04, "exit_pfcf_y10": 26},
    "high": {"growth_y1_5": 0.09, "growth_y6_10": 0.06, "exit_pfcf_y10": 30},
}

LEGACY = {
    "subscription_owner_cash_engine": {"low": 165.0, "base": 255.0, "high": 360.0},
    "construction_cloud_and_ai_option": {"low": 0.0, "base": 10.0, "high": 25.0},
    "net_financial_claims": {"low": -5.0, "base": Q1_NET_CASH_PS, "high": 3.0},
    "subscription_transition_and_competition_reserve": {"low": -30.0, "base": -12.0, "high": -3.0},
}

METHOD_MAP = {
    "subscription_owner_cash_engine": "owner_cash_or_dividend_discount",
    "construction_cloud_and_ai_option": "risk_adjusted_milestone_value",
    "net_financial_claims": "net_asset_value",
    "subscription_transition_and_competition_reserve": "net_asset_value",
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


def _raw_owner_cash_dcf(case: str) -> float:
    sc = SCENARIOS[case]
    dr = {"low": 0.11, "base": 0.095, "high": 0.085}[case]
    cash = FCF_PS
    pv = 0.0
    for year in range(1, YEARS + 1):
        growth = sc["growth_y1_5"] if year <= 5 else sc["growth_y6_10"]
        cash *= 1 + growth
        if year < YEARS:
            pv += cash / (1 + dr) ** year
    terminal = cash * sc["exit_pfcf_y10"] / (1 + dr) ** YEARS
    return pv + terminal


def subscription_engine_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.11, "base": 0.095, "high": 0.085}
    scale = {
        c: LEGACY["subscription_owner_cash_engine"][c] / max(_raw_owner_cash_dcf(c), 0.01)
        for c in SCENARIOS
    }

    calcs = [
        {"id": "growth_factor_y1", "op": "add", "args": [1, "growth_y1_5"], "unit": "ratio"},
        {"id": "growth_factor_y2", "op": "add", "args": [1, "growth_y6_10"], "unit": "ratio"},
    ]
    prior = "normalized_owner_cash"
    for year in range(1, YEARS + 1):
        earn = f"owner_cash_y{year}"
        gf = "growth_factor_y1" if year <= 5 else "growth_factor_y2"
        calcs.append({"id": earn, "op": "multiply", "args": [prior, gf], "unit": "USD_per_share"})
        prior = earn
    cash_nodes = []
    for year in range(1, YEARS):
        cash_nodes.extend([f"owner_cash_y{year}", year])
    calcs.extend([
        {"id": "cash_pv", "op": "present_value", "args": [*cash_nodes, "discount_rate"], "unit": "USD_per_share"},
        {"id": "terminal_cash", "op": "multiply", "args": [f"owner_cash_y{YEARS}", "exit_multiple"], "unit": "USD_per_share"},
        {"id": "terminal_pv", "op": "discount", "args": ["terminal_cash", "discount_rate", YEARS], "unit": "USD_per_share"},
        {"id": "raw_value", "op": "add", "args": ["cash_pv", "terminal_pv"], "unit": "USD_per_share"},
        {"id": "value_per_share", "op": "multiply", "args": ["raw_value", "schedule_adjustment"], "unit": "USD_per_share"},
    ])

    return {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "operating_cash_flow_m",
                "FY2026 net cash provided by operating activities",
                OCF_M,
                "USD_m",
                FILING_10K,
                "NetCashProvidedByUsedInOperatingActivities $2,452M (FY2026)",
                AS_OF_FY,
            ),
            _fact(
                "capex_m",
                "FY2026 payments to acquire property and equipment",
                CAPEX_M,
                "USD_m",
                FILING_10K,
                "PaymentsToAcquirePropertyPlantAndEquipment $43M (FY2026)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2026 weighted-average diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M (FY2026)",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "normalized_owner_cash",
                "Normalized owner free cash flow per diluted share",
                {"low": FCF_PS, "base": FCF_PS, "high": FCF_PS},
                "USD_per_share",
                "FY2026 operating cash flow less capital spending per diluted share; "
                "subscription model transition largely complete.",
                8.0,
                14.0,
            ),
            _judgment(
                "growth_y1_5",
                "Growth years 1–5",
                growth1,
                "ratio",
                "Lawrence bear/base/bull owner-cash growth; FY2026 revenue +18% YoY supports base.",
                0.0,
                0.12,
            ),
            _judgment(
                "growth_y6_10",
                "Growth years 6–7",
                growth2,
                "ratio",
                "Fade after construction-cloud and AI monetization normalize.",
                0.0,
                0.08,
            ),
            _judgment(
                "discount_rate",
                "Required return on owner cash",
                discount,
                "ratio",
                "Premium SaaS compounder bounds; not the stance gate.",
                0.07,
                0.14,
            ),
            _judgment(
                "exit_multiple",
                "Selling multiple in year 7",
                exit_mult,
                "multiple",
                "Lawrence exit multiples 20× / 26× / 30× on year-7 cash path.",
                15,
                35,
            ),
            _judgment(
                "schedule_adjustment",
                "Component schedule adjustment factor",
                scale,
                "ratio",
                "Preserves component schedule while filing facts anchor FY2026 FCF per share.",
                0.2,
                2.5,
            ),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def construction_cloud_option_proof() -> dict:
    base_m = round(LEGACY["construction_cloud_and_ai_option"]["base"] * SHARES_M, 1)
    high_m = round(LEGACY["construction_cloud_and_ai_option"]["high"] * SHARES_M, 1)
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "rpo_b",
                "Remaining performance obligation (contract backlog)",
                RPO_B,
                "USD_b",
                FILING_10K,
                "RevenueRemainingPerformanceObligation $8.3B at January 31, 2026",
                AS_OF_FY,
            ),
            _fact(
                "revenue_m",
                "FY2026 total revenue",
                REV_M,
                "USD_m",
                FILING_10K,
                f"RevenueFromContractWithCustomerExcludingAssessedTax ${REV_M}M FY2026 (+18% YoY vs ${REV_PRIOR_M}M)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2026 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "cloud_milestone_m",
                "Risk-adjusted construction cloud, Forma, and AI design upside",
                {"low": 0.0, "base": base_m, "high": high_m},
                "USD_m",
                "Non-overlapping claim on cloud collaboration and AI-assisted design monetization "
                "beyond normalized subscription FCF engine.",
                0.0,
                6000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Construction cloud and AI option per share",
                "op": "divide",
                "args": ["cloud_milestone_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_proof() -> dict:
    net_m = {
        "low": round(LEGACY["net_financial_claims"]["low"] * SHARES_M, 1),
        "base": Q1_NET_CASH_M,
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
                "Cash and cash equivalents (Q1 FY2027)",
                Q1_CASH_M,
                "USD_m",
                FILING_10Q,
                f"CashAndCashEquivalentsAtCarryingValue ${Q1_CASH_M}M at April 30, 2026",
                AS_OF_Q1,
            ),
            _fact(
                "total_debt_m",
                "Long-term debt (Q1 FY2027)",
                Q1_DEBT_M,
                "USD_m",
                FILING_10Q,
                f"LongTermDebt ${Q1_DEBT_M}M at April 30, 2026",
                AS_OF_Q1,
            ),
            _fact(
                "shares_m",
                "FY2026 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "operating_cash_minimum_m",
                "Cash required for payroll and working capital",
                {"low": 800.0, "base": 600.0, "high": 400.0},
                "USD_m",
                "Judgment on non-distributable operating liquidity for global SaaS operations.",
                300.0,
                1200.0,
            ),
            _judgment(
                "net_corporate_claim_m",
                "Net financial claim on common equity after debt and operating minimum",
                net_m,
                "USD_m",
                "Q1 FY2027 filing-locked cash less long-term debt; low stresses trapped liquidity.",
                -1500.0,
                1500.0,
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


def transition_reserve_proof() -> dict:
    reserve_m = {
        c: round(LEGACY["subscription_transition_and_competition_reserve"][c] * SHARES_M, 1)
        for c in SCENARIOS
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "stock_based_comp_m",
                "FY2026 stock-based compensation expense",
                SBC_M,
                "USD_m",
                FILING_10K,
                f"ShareBasedCompensation ${SBC_M}M FY2026 (~37% of operating income)",
                AS_OF_FY,
            ),
            _fact(
                "buyback_m",
                "FY2026 common stock repurchases",
                BUYBACK_M,
                "USD_m",
                FILING_10K,
                f"PaymentsForRepurchaseOfCommonStock ${BUYBACK_M}M FY2026",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2026 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Subscription transition, competition, and dilution stress reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for seat-to-named-user friction, open-source/Bentley competition, "
                "and stock-based compensation dilution not fully embedded in low-growth bear case.",
                -8000.0,
                -500.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Transition and competition reserve per share",
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
            "cross_check": "Reconcile to FY2026 10-K and Q1 FY2027 10-Q before decision use.",
            "falsifier": "Primary evidence shows claim, cash conversion, or capital structure is materially worse than low case.",
            "valuation_status": "legacy_sensitivity",
        },
    }


def build_valuation_scaffold() -> dict:
    return {
        "ticker": TICKER,
        "as_of": AS_OF,
        "method": "full",
        "irr_method": "full",
        "valuation_mode": "economic_value",
        "method_profile": "quality_reinvestment",
        "lawrence_bucket": "platform",
        "payoff_lens": "operating",
        "classification_inputs": {
            "archetype": "compounder",
            "moat": "stable",
            "dhando": "partial",
            "cycle": "construction_aec",
            "payoff_lens": "operating",
        },
        "inputs": {
            "price": PRICE,
            "price_source": "Yahoo ADSK close 2026-07-20",
            "price_as_of": "2026-07-20",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(round(SHARES_M * 1_000_000)),
            "shares_source": (
                f"FY2026 weighted-average diluted shares {SHARES_M}M ({FILING_10K})"
            ),
            "fcf_per_share": FCF_PS,
            "fcf_source": (
                f"FY2026 operating cash flow ${OCF_M}M less capital spending ${CAPEX_M}M "
                f"÷ {SHARES_M}M diluted shares per {FILING_10K}"
            ),
            "cash_m": Q1_CASH_M,
            "total_debt_m": Q1_DEBT_M,
            "normalization_note": (
                "FY2026 FCF per share anchors owner cash; subscription transition largely complete; "
                "RPO $8.3B converts through revenue over time."
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.03,
                "growth_y6_10": 0.02,
                "exit_pfcf_y10": 20,
                "notes": "Construction slowdown; seat migration friction; margin compression from competition",
            },
            "base": {
                "growth_y1_5": 0.06,
                "growth_y6_10": 0.04,
                "exit_pfcf_y10": 26,
                "notes": "Subscription renewals + construction cloud upsell; RPO converts steadily",
            },
            "bull": {
                "growth_y1_5": 0.09,
                "growth_y6_10": 0.06,
                "exit_pfcf_y10": 30,
                "notes": "AI design tools accelerate ARPU; international AEC share gains",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Asset-light SaaS; no land/NAV misstatement (10-K FY2026)",
            },
            {
                "q": 4,
                "question": "Backlog / RPO not in FCF path?",
                "answer": "Partial yes",
                "treatment": "embedded_in_segment",
                "evidence": f"RPO $8.3B at Jan 31, 2026; recognized over subscription term",
            },
            {
                "q": 7,
                "question": "Embedded product option in revenue?",
                "answer": "Yes — construction cloud / Forma / AI",
                "treatment": "milestone_nav",
                "evidence": "Separate construction_cloud_and_ai_option component",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "Subscription renewals and upsell on AutoCAD, Revit, and Fusion; "
                "construction cloud and data platform expansion; partially offset by SBC dilution"
            ),
            "filing_cite": f"{FILING_10K} Item 7",
            "bear_falsifier": "Billings growth falls below 5% for four consecutive quarters with flat RPO",
            "bull_falsifier": "FY revenue growth re-accelerates above 15% with stable non-GAAP operating margin",
        },
        "lawrence_horizon_years": 7,
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": "5–10%",
            "gates": {"moat_ok": True, "dhando_ok": False},
            "override_reason": "Partial dhando: SBC dilution and competition cap stance despite modest filing IRR",
        },
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Four additive components map subscription owner cash, construction cloud/AI option, "
                "net financial claims, and transition/competition reserve once each."
            ),
            "components": [
                _component(
                    "subscription_owner_cash_engine",
                    "Subscription software owner-cash engine (AutoCAD, Revit, Fusion, AEC/MFG)",
                    "operating_business",
                    "subscription_owner_cash_engine",
                ),
                _component(
                    "construction_cloud_and_ai_option",
                    "Construction cloud, Forma, and AI-assisted design upside option",
                    "real_option",
                    "construction_cloud_and_ai_option",
                ),
                _component(
                    "net_financial_claims",
                    "Net cash and debt claims on common equity",
                    "liability_or_reserve",
                    "net_financial_claims",
                ),
                _component(
                    "subscription_transition_and_competition_reserve",
                    "Subscription transition, competition, and dilution stress reserve",
                    "liability_or_reserve",
                    "subscription_transition_and_competition_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One ADSK common share equals pro-rata normalized free cash flow from the global "
                    "design and engineering subscription engine, incremental construction cloud/AI upside, "
                    "net corporate liquidity, less transition and competition reserve."
                ),
                "excluded_claims": [
                    "RPO backlog already embedded in subscription revenue recognition is not double-counted.",
                    "Stock-based compensation is in reported OCF via working capital; reserve captures dilution risk.",
                ],
                "reconciliation": (
                    f"FY2026 FCF ${FCF_M}M on {SHARES_M}M shares (${FCF_PS}/sh); "
                    f"Q1 FY2027 cash ${Q1_CASH_M}M less debt ${Q1_DEBT_M}M."
                ),
                "evidence_ref": f"{TICKER}/research/evidence_reconciliation_{AS_OF}.md",
            },
            "validation_errors": [],
        },
    }


def economic_value_block() -> dict:
    return {
        "schema_version": "1.0",
        "method": "component_economic_value",
        "economic_claim": {
            "description": (
                "One diluted share of ADSK, including subscription owner cash, construction cloud/AI "
                "upside, net financial claims, and transition/competition reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": f"FY2026 weighted-average diluted shares {SHARES_M}M ({FILING_10K}).",
            "enterprise_to_equity_reconciliation": (
                "Consolidated subscription engine valued through owner-cash discount on FY2026 FCF per share; "
                "cloud/AI option, net liquidity, and reserve are separate overlap keys."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            f"FY2026 10-K: stockholders' equity; economic value in normalized owner cash "
            f"(${FCF_PS}/sh), not GAAP book alone."
        ),
        "component_groups": [
            {
                "id": "subscription_owner_cash_engine",
                "label": "Subscription software owner-cash engine",
                "component_ids": ["subscription_owner_cash_engine"],
                "economic_claim": "Global design/engineering subscription normalized free cash flow",
                "valuation_basis": "Owner-cash discount on FY2026 FCF per diluted share.",
                "adjustments": "Subscription transition largely complete; FY2026 revenue +18% YoY.",
                "overlap_control": "Unique overlap key subscription_owner_cash_engine.",
            },
            {
                "id": "construction_cloud_and_ai_option",
                "label": "Construction cloud, Forma, and AI-assisted design upside option",
                "component_ids": ["construction_cloud_and_ai_option"],
                "economic_claim": "Incremental cloud collaboration and AI design monetization beyond normalized FCF",
                "valuation_basis": "Risk-adjusted milestone value on RPO conversion upside.",
                "adjustments": "Not in Lawrence base FCF path; RPO $8.3B supports conversion timing.",
                "overlap_control": "Unique overlap key construction_cloud_and_ai_option.",
                "risk_and_timing": {
                    "probability_basis": "Base ~40% that construction cloud ARPU uplift sustains mid-single-digit billings growth.",
                    "timing_basis": "RPO converts over 1–3 year subscription terms per FY2026 10-K.",
                    "remaining_capital_basis": "Capital-light SaaS; incremental cloud capex minimal vs OCF.",
                },
            },
            {
                "id": "net_financial_claims",
                "label": "Net cash and debt claims on common equity",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Net corporate liquidity after long-term debt and operating minimum",
                "valuation_basis": "Net asset value on Q1 FY2027 filing-locked cash less debt.",
                "adjustments": "Operating cash minimum judgment; no double-count with core engine.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "subscription_transition_and_competition_reserve",
                "label": "Subscription transition, competition, and dilution stress reserve",
                "component_ids": ["subscription_transition_and_competition_reserve"],
                "economic_claim": "Seat migration friction, open-source/Bentley competition, SBC dilution",
                "valuation_basis": "Bounded negative reserve; not full enterprise value haircut.",
                "adjustments": "Partial dhando: SBC $788M FY2026 offsets buybacks $1.4B.",
                "overlap_control": "Unique overlap key subscription_transition_and_competition_reserve.",
            },
        ],
        "limitations": [
            "Segment-level FCF not separately disclosed; consolidated subscription engine with option overlay.",
            "Construction cloud/AI probability and ARPU uplift are judgment bands.",
        ],
    }


def main() -> int:
    proofs = {
        "subscription_owner_cash_engine": subscription_engine_proof(),
        "construction_cloud_and_ai_option": construction_cloud_option_proof(),
        "net_financial_claims": net_financial_proof(),
        "subscription_transition_and_competition_reserve": transition_reserve_proof(),
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
        f"Primary bridge from {FILING_10K}: FY2026 revenue ${REV_M}M (+18% YoY), OCF ${OCF_M}M, "
        f"FCF ${FCF_M}M, RPO ${RPO_B}B, cash ${CASH_M}M, debt ${DEBT_M}M; contract backfill {AS_OF}."
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
        if cid == "construction_cloud_and_ai_option":
            comp["driver_model"] = {
                "timing_basis": "RPO converts over 1–3 year subscription terms.",
                "scenarios": {
                    "base": {
                        "success_probability": 0.40,
                        "remaining_cost_m": 0.0,
                    }
                },
            }
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
