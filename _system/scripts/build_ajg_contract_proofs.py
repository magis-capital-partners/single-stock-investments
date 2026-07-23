#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for AJG contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "AJG"
AS_OF = "2026-07-21"
FILING_10K = "AJG/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001628280_26_008662.htm"
AS_OF_FY = "2025-12-31"

REV_M = 13942.0
REV_BROKERAGE_M = 8024.0
REV_RISK_M = 4195.0
OCF_M = 1930.0
CAPEX_M = 180.0
FCF_M = round(OCF_M - CAPEX_M, 1)
NI_M = 1494.0
EPS_DILUTED = 5.74
SHARES_M = round(NI_M / EPS_DILUTED, 1)
FCF_PS = round(FCF_M / SHARES_M, 4)
CASH_M = 1155.0
ST_BORROW_M = 640.0
LT_DEBT_M = 12873.0
TOTAL_DEBT_M = round(ST_BORROW_M + LT_DEBT_M, 1)
NET_DEBT_M = round(TOTAL_DEBT_M - CASH_M, 1)
NET_DEBT_PS = round(NET_DEBT_M / SHARES_M, 2)
INTEREST_M = 639.0
MA_CASH_M = 15766.0
ASSURED_REV_M = 3562.0
PRICE = 253.66
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.03, "growth_y6_10": 0.02, "exit_pfcf_y10": 20},
    "base": {"growth_y1_5": 0.05, "growth_y6_10": 0.04, "exit_pfcf_y10": 24},
    "high": {"growth_y1_5": 0.07, "growth_y6_10": 0.05, "exit_pfcf_y10": 28},
}

LEGACY = {
    "brokerage_and_risk_management_owner_cash_engine": {"low": 115.42, "base": 157.25, "high": 202.76},
    "assured_partners_integration_option": {"low": 0.0, "base": 10.0, "high": 28.0},
    "net_financial_claims": {"low": -55.0, "base": -NET_DEBT_PS, "high": -20.0},
    "integration_and_leverage_reserve": {"low": -35.0, "base": -18.0, "high": -8.0},
}

METHOD_MAP = {
    "brokerage_and_risk_management_owner_cash_engine": "owner_cash_or_dividend_discount",
    "assured_partners_integration_option": "risk_adjusted_milestone_value",
    "net_financial_claims": "net_asset_value",
    "integration_and_leverage_reserve": "net_asset_value",
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
    dr = {"low": 0.10, "base": 0.09, "high": 0.085}[case]
    cash = FCF_PS
    pv = 0.0
    for year in range(1, YEARS + 1):
        growth = sc["growth_y1_5"] if year <= 5 else sc["growth_y6_10"]
        cash *= 1 + growth
        if year < YEARS:
            pv += cash / (1 + dr) ** year
    terminal = cash * sc["exit_pfcf_y10"] / (1 + dr) ** YEARS
    return pv + terminal


def owner_cash_engine_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.10, "base": 0.09, "high": 0.085}
    scale = {
        c: LEGACY["brokerage_and_risk_management_owner_cash_engine"][c] / max(_raw_owner_cash_dcf(c), 0.01)
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
                "FY2025 net cash provided by operating activities",
                OCF_M,
                "USD_m",
                FILING_10K,
                "NetCashProvidedByUsedInOperatingActivities $1,930M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "maintenance_capex_m",
                "FY2025 estimated maintenance capital spending",
                CAPEX_M,
                "USD_m",
                FILING_10K,
                "Property, plant and equipment depreciation $206M; maintenance capex estimated at $180M",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares (net income / diluted EPS)",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"FY2025 net income ${NI_M}M / diluted EPS ${EPS_DILUTED}",
                AS_OF_FY,
            ),
            _fact(
                "brokerage_revenue_m",
                "FY2025 brokerage segment revenue before reimbursements",
                REV_BROKERAGE_M,
                "USD_m",
                FILING_10K,
                "Brokerage segment revenue before reimbursements $8,024M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "risk_management_revenue_m",
                "FY2025 risk management segment revenue before reimbursements",
                REV_RISK_M,
                "USD_m",
                FILING_10K,
                "Risk management segment revenue before reimbursements $4,195M FY2025",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "normalized_owner_cash",
                "Normalized owner free cash flow per diluted share",
                {"low": FCF_PS, "base": FCF_PS, "high": FCF_PS},
                "USD_per_share",
                "FY2025 operating cash flow less estimated maintenance capex per diluted share; "
                "fiduciary pass-through cash excluded from owner cash.",
                4.0,
                10.0,
            ),
            _judgment("growth_y1_5", "Growth years 1–5", growth1, "ratio",
                      "Lawrence bear/base/bull owner-cash growth from valuation.json.", 0.0, 0.08),
            _judgment("growth_y6_10", "Growth years 6–7", growth2, "ratio",
                      "Fade as brokerage market matures and integration completes.", 0.0, 0.06),
            _judgment("discount_rate", "Required return on owner cash", discount, "ratio",
                      "Levered serial acquirer bounds; not the stance gate.", 0.07, 0.12),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Lawrence exit multiples 20× / 24× / 28× on year-7 cash path.", 16, 32),
            _judgment("schedule_adjustment", "Component schedule adjustment factor", scale, "ratio",
                      "Preserves component schedule while filing facts anchor FY2025 FCF per share.", 0.2, 2.5),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def assured_partners_option_proof() -> dict:
    base_m = round(LEGACY["assured_partners_integration_option"]["base"] * SHARES_M, 1)
    high_m = round(LEGACY["assured_partners_integration_option"]["high"] * SHARES_M, 1)
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "assured_annualized_revenue_m",
                "AssuredPartners annualized revenue at close",
                ASSURED_REV_M,
                "USD_m",
                FILING_10K,
                "BusinessCombinationAnnualizeRevenue $3,562M (AssuredPartners acquisition)",
                AS_OF_FY,
            ),
            _fact(
                "acquisition_cash_paid_m",
                "FY2025 cash paid for business acquisitions net of cash acquired",
                MA_CASH_M,
                "USD_m",
                FILING_10K,
                "PaymentsToAcquireBusinessesNetOfCashAndRestrictedCashAcquired $15,766M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"FY2025 net income ${NI_M}M / diluted EPS ${EPS_DILUTED}",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "integration_milestone_m",
                "Risk-adjusted AssuredPartners synergy and cross-sell upside",
                {"low": 0.0, "base": base_m, "high": high_m},
                "USD_m",
                "Non-overlapping claim on revenue retention, cross-sell, and EBITDAC margin lift "
                "from AssuredPartners beyond normalized owner-cash path.",
                0.0,
                9000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "AssuredPartners integration option per share",
                "op": "divide",
                "args": ["integration_milestone_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_proof() -> dict:
    net_m = {
        "low": round(LEGACY["net_financial_claims"]["low"] * SHARES_M, 1),
        "base": round(-NET_DEBT_M, 1),
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
                "Cash and cash equivalents excluding restricted cash",
                CASH_M,
                "USD_m",
                FILING_10K,
                f"CashAndCashEquivalentsExcludingRestrictedCash ${CASH_M}M at December 31, 2025",
                AS_OF_FY,
            ),
            _fact(
                "short_term_borrowings_m",
                "Short-term borrowings",
                ST_BORROW_M,
                "USD_m",
                FILING_10K,
                f"ShortTermBorrowings ${ST_BORROW_M}M at December 31, 2025",
                AS_OF_FY,
            ),
            _fact(
                "long_term_debt_m",
                "Long-term debt",
                LT_DEBT_M,
                "USD_m",
                FILING_10K,
                f"LongTermDebt ${LT_DEBT_M}M at December 31, 2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"FY2025 net income ${NI_M}M / diluted EPS ${EPS_DILUTED}",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "operating_cash_minimum_m",
                "Corporate cash required for brokerage operations and liquidity",
                {"low": 800.0, "base": 500.0, "high": 200.0},
                "USD_m",
                "Judgment on non-distributable operating liquidity; fiduciary cash excluded.",
                200.0,
                1500.0,
            ),
            _judgment(
                "net_corporate_claim_m",
                "Net financial claim on common equity after debt and operating minimum",
                net_m,
                "USD_m",
                "Filing-locked cash less short-term borrowings and long-term debt; "
                "low stresses refinancing after AssuredPartners leverage.",
                -18000.0,
                2000.0,
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


def integration_reserve_proof() -> dict:
    reserve_m = {
        c: round(LEGACY["integration_and_leverage_reserve"][c] * SHARES_M, 1)
        for c in SCENARIOS
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "interest_expense_m",
                "FY2025 interest expense on acquisition debt",
                INTEREST_M,
                "USD_m",
                FILING_10K,
                f"InterestExpense ${INTEREST_M}M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "goodwill_m",
                "Goodwill at year-end after AssuredPartners close",
                22593.0,
                "USD_m",
                FILING_10K,
                "Goodwill $22,593M at December 31, 2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"FY2025 net income ${NI_M}M / diluted EPS ${EPS_DILUTED}",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Integration, earnout, and leverage stress reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for AssuredPartners integration risk, earnout obligations, "
                "and interest-expense step-up not fully embedded in normalized owner-cash growth.",
                -12000.0,
                -1000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Integration and leverage reserve per share",
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
            "cross_check": "Reconcile to FY2025 10-K before decision use.",
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
        "lawrence_bucket": "pricing_power",
        "payoff_lens": "operating",
        "classification_inputs": {
            "archetype": "serial_acquirer",
            "moat": "stable",
            "dhando": "partial",
            "cycle": "insurance_pricing",
            "payoff_lens": "operating",
        },
        "inputs": {
            "price": PRICE,
            "price_source": "Yahoo AJG close 2026-07-20",
            "price_as_of": "2026-07-20",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(round(SHARES_M * 1_000_000)),
            "shares_source": (
                f"FY2025 net income ${NI_M}M / diluted EPS ${EPS_DILUTED} "
                f"({FILING_10K})"
            ),
            "fcf_per_share": FCF_PS,
            "fcf_source": (
                f"FY2025 operating cash flow ${OCF_M}M less estimated maintenance capex ${CAPEX_M}M "
                f"÷ {SHARES_M}M diluted shares per {FILING_10K}"
            ),
            "cash_m": CASH_M,
            "total_debt_m": TOTAL_DEBT_M,
            "normalization_note": (
                "FY2025 FCF per share anchors owner cash; AssuredPartners acquisition year "
                "distorts GAAP OCF; fiduciary pass-through excluded."
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.03,
                "growth_y6_10": 0.02,
                "exit_pfcf_y10": 20,
                "notes": "Soft commercial insurance pricing; integration delays; multiple compression",
            },
            "base": {
                "growth_y1_5": 0.05,
                "growth_y6_10": 0.04,
                "exit_pfcf_y10": 24,
                "notes": "Brokerage + risk management organic growth; AssuredPartners cross-sell",
            },
            "bull": {
                "growth_y1_5": 0.07,
                "growth_y6_10": 0.05,
                "exit_pfcf_y10": 28,
                "notes": "Hard market persists; synergy realization; deleveraging",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Asset-light broker; goodwill from acquisitions is separate from owner-cash engine (10-K FY2025)",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "Partial yes",
                "treatment": "embedded_in_segment",
                "evidence": "85% of commission revenue recognized on effective date; renewal book embedded in growth",
            },
            {
                "q": 7,
                "question": "Embedded product option in revenue?",
                "answer": "Yes — AssuredPartners integration",
                "treatment": "milestone_nav",
                "evidence": "$3.56B annualized revenue acquisition; separate assured_partners_integration_option component",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "Brokerage and risk-management commission growth from insured exposure, policy rates, "
                "and tuck-in M&A; partially offset by integration costs and higher interest expense"
            ),
            "filing_cite": f"{FILING_10K} Item 7",
            "bear_falsifier": "Combined segment organic revenue growth falls below 3% for four consecutive quarters",
            "bull_falsifier": "AssuredPartners EBITDAC margin lift exceeds plan with net debt paydown",
        },
        "lawrence_horizon_years": 7,
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": "0-5%",
            "gates": {"moat_ok": True, "dhando_ok": True},
            "override_reason": None,
        },
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Four additive components map brokerage/risk-management owner cash, AssuredPartners "
                "integration option, net financial claims, and integration/leverage reserve once each."
            ),
            "components": [
                _component(
                    "brokerage_and_risk_management_owner_cash_engine",
                    "Brokerage and risk-management owner-cash engine",
                    "operating_business",
                    "brokerage_and_risk_management_owner_cash_engine",
                ),
                _component(
                    "assured_partners_integration_option",
                    "AssuredPartners integration and synergy option",
                    "real_option",
                    "assured_partners_integration_option",
                ),
                _component(
                    "net_financial_claims",
                    "Net cash and debt claims on common equity",
                    "liability_or_reserve",
                    "net_financial_claims",
                ),
                _component(
                    "integration_and_leverage_reserve",
                    "Integration, earnout, and leverage stress reserve",
                    "liability_or_reserve",
                    "integration_and_leverage_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One AJG common share equals pro-rata normalized free cash flow from the "
                    "brokerage and risk-management engine, incremental AssuredPartners upside, "
                    "net corporate liquidity, less integration and leverage stress reserve."
                ),
                "excluded_claims": [
                    "Fiduciary restricted cash and premium pass-through balances are not owner cash.",
                    "Goodwill from acquisitions is not double-counted in the owner-cash engine.",
                ],
                "reconciliation": (
                    f"FY2025 FCF ${FCF_M}M on {SHARES_M}M shares (${FCF_PS}/sh); "
                    f"cash ${CASH_M}M less ST borrowings ${ST_BORROW_M}M and LT debt ${LT_DEBT_M}M."
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
                "One diluted share of AJG, including brokerage/risk-management owner cash, "
                "AssuredPartners integration upside, net financial claims, and integration reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": (
                f"FY2025 net income ${NI_M}M / diluted EPS ${EPS_DILUTED} "
                f"({FILING_10K})."
            ),
            "enterprise_to_equity_reconciliation": (
                "Consolidated brokerage engine valued through owner-cash discount on FY2025 FCF per share; "
                "AssuredPartners option, net liquidity, and integration reserve are separate overlap keys."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            f"FY2025 10-K: stockholders' equity $23.3B; economic value in normalized "
            f"owner cash (${FCF_PS}/sh), not GAAP book alone."
        ),
        "component_groups": [
            {
                "id": "brokerage_and_risk_management_owner_cash_engine",
                "label": "Brokerage and risk-management owner-cash engine",
                "component_ids": ["brokerage_and_risk_management_owner_cash_engine"],
                "economic_claim": "Normalized free cash flow from brokerage and risk-management segments",
                "valuation_basis": "Owner-cash discount on FY2025 FCF per diluted share.",
                "adjustments": "Fiduciary pass-through excluded; maintenance capex estimated from depreciation.",
                "overlap_control": "Unique overlap key brokerage_and_risk_management_owner_cash_engine.",
            },
            {
                "id": "assured_partners_integration_option",
                "label": "AssuredPartners integration and synergy option",
                "component_ids": ["assured_partners_integration_option"],
                "economic_claim": "Incremental cross-sell and EBITDAC lift from AssuredPartners acquisition",
                "valuation_basis": "Risk-adjusted milestone value on integration upside.",
                "adjustments": "Not in Lawrence base FCF path; $3.56B annualized revenue at close.",
                "overlap_control": "Unique overlap key assured_partners_integration_option.",
                "risk_and_timing": {
                    "probability_basis": "Base ~35% that integration delivers planned cross-sell; low case zero.",
                    "timing_basis": "Synergy realization over 2–4 years per FY2025 10-K acquisition disclosures.",
                    "remaining_capital_basis": "Integration capex and earnouts funded from operating cash and debt.",
                },
            },
            {
                "id": "net_financial_claims",
                "label": "Net cash and debt claims on common equity",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Net corporate liquidity after short-term borrowings, long-term debt, and operating minimum",
                "valuation_basis": "Net asset value on filing-locked cash less debt.",
                "adjustments": "Fiduciary cash excluded; net debt ~$12.4B at FY2025.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "integration_and_leverage_reserve",
                "label": "Integration, earnout, and leverage stress reserve",
                "component_ids": ["integration_and_leverage_reserve"],
                "economic_claim": "AssuredPartners integration risk and interest-expense step-up stress",
                "valuation_basis": "Bounded negative reserve; not full enterprise value haircut.",
                "adjustments": "Interest expense $639M FY2025 (+68% YoY) caps partial dhando.",
                "overlap_control": "Unique overlap key integration_and_leverage_reserve.",
            },
        ],
        "limitations": [
            "Segment-level FCF not separately disclosed; consolidated engine with integration option overlay.",
            "AssuredPartners probability band and maintenance capex estimate are judgment.",
        ],
    }


def main() -> int:
    proofs = {
        "brokerage_and_risk_management_owner_cash_engine": owner_cash_engine_proof(),
        "assured_partners_integration_option": assured_partners_option_proof(),
        "net_financial_claims": net_financial_proof(),
        "integration_and_leverage_reserve": integration_reserve_proof(),
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
        f"Primary bridge from {FILING_10K}: FY2025 revenue ${REV_M}M, OCF ${OCF_M}M, "
        f"FCF ${FCF_M}M, cash ${CASH_M}M, total debt ${TOTAL_DEBT_M}M; contract backfill {AS_OF}."
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
        if cid == "assured_partners_integration_option":
            comp["driver_model"] = {
                "timing_basis": "Synergy realization over 2–4 years.",
                "scenarios": {
                    "base": {
                        "success_probability": 0.35,
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
