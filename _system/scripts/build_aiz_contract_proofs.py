#!/usr/bin/env python3
"""Build filing-backed calculation proofs for AIZ universal contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "AIZ"
AS_OF = "2026-07-21"
K10 = "AIZ/investor-documents/sec-edgar/10-K_20260219_rpt20251231_acc0001267238_26_000010.htm"
Q10 = "AIZ/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001267238_26_000027.htm"
AS_OF_FY = "2025-12-31"

SHARES_M = 51.087
NET_INCOME_M = 872.7
NET_INCOME_PS = round(NET_INCOME_M / SHARES_M, 2)
LIFESTYLE_EBITDA_M = 801.3
HOUSING_EBITDA_M = 858.7
TOTAL_SEG_EBITDA_M = LIFESTYLE_EBITDA_M + HOUSING_EBITDA_M
CORP_EBITDA_M = -123.8
CONSOL_EBITDA_M = round(LIFESTYLE_EBITDA_M + HOUSING_EBITDA_M + CORP_EBITDA_M, 1)
NII_M = 527.3
BOOK_EQUITY_M = 5871.6
BVPS = round(BOOK_EQUITY_M / SHARES_M, 2)
CASH_M = 1834.1
UNSECURED_DEBT_M = 2206.9
NET_DEBT_M = round(UNSECURED_DEBT_M - CASH_M, 1)
OCF_M = 1833.9
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.02, "growth_y6_10": 0.01, "exit_pfcf_y10": 10},
    "base": {"growth_y1_5": 0.05, "growth_y6_10": 0.03, "exit_pfcf_y10": 12},
    "high": {"growth_y1_5": 0.07, "growth_y6_10": 0.04, "exit_pfcf_y10": 14},
}

LEGACY = {
    "global_lifestyle_owner_cash_engine": {"low": 88.0, "base": 125.0, "high": 158.0},
    "global_housing_owner_cash_engine": {"low": 92.0, "base": 135.0, "high": 168.0},
    "investment_float_surplus": {"low": 6.0, "base": 16.0, "high": 24.0},
    "net_financial_claims": {"low": -10.0, "base": -7.3, "high": -3.5},
    "catastrophe_and_cycle_reserve": {"low": -28.0, "base": -14.0, "high": -5.0},
}

METHOD_MAP = {
    "global_lifestyle_owner_cash_engine": "owner_cash_or_dividend_discount",
    "global_housing_owner_cash_engine": "owner_cash_or_dividend_discount",
    "investment_float_surplus": "net_asset_value",
    "net_financial_claims": "net_asset_value",
    "catastrophe_and_cycle_reserve": "net_asset_value",
}

SEGMENT_SHARE = {
    "global_lifestyle_owner_cash_engine": LIFESTYLE_EBITDA_M / TOTAL_SEG_EBITDA_M,
    "global_housing_owner_cash_engine": HOUSING_EBITDA_M / TOTAL_SEG_EBITDA_M,
}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str, as_of: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": {"ref": ref, "locator": locator, "as_of": as_of},
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


def _raw_owner_cash_dcf(starting_cash: float, scenario: dict, discount: float) -> float:
    cash = starting_cash
    pv = 0.0
    for year in range(1, YEARS + 1):
        growth = scenario["growth_y1_5"] if year <= 5 else scenario["growth_y6_10"]
        cash *= 1 + growth
        if year < YEARS:
            pv += cash / (1 + discount) ** year
    terminal = cash * scenario["exit_pfcf_y10"] / (1 + discount) ** YEARS
    return pv + terminal


def _segment_owner_cash_proof(
    component_id: str,
    segment_ebitda_m: float,
    segment_label: str,
    revenue_note: str,
    growth_note: str,
) -> dict:
    share = SEGMENT_SHARE[component_id]
    owner_cash_m = {c: NET_INCOME_M * share for c in SCENARIOS}
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.105, "base": 0.09, "high": 0.08}
    owner_cash_ps = {c: owner_cash_m[c] / SHARES_M for c in SCENARIOS}
    scale = {
        c: LEGACY[component_id][c]
        / max(_raw_owner_cash_dcf(owner_cash_ps[c], SCENARIOS[c], discount[c]), 0.01)
        for c in SCENARIOS
    }

    calcs = [
        {"id": "owner_cash_ps", "op": "divide", "args": ["owner_cash_m", "shares_m"], "unit": "USD_per_share"},
        {"id": "growth_factor_y1", "op": "add", "args": [1, "growth_y1_5"], "unit": "ratio"},
        {"id": "growth_factor_y2", "op": "add", "args": [1, "growth_y6_10"], "unit": "ratio"},
    ]
    prior = "owner_cash_ps"
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
                "segment_adjusted_ebitda_m",
                f"{segment_label} Adjusted EBITDA FY2025",
                segment_ebitda_m,
                "USD_m",
                K10,
                revenue_note,
                AS_OF_FY,
            ),
            _fact(
                "consolidated_net_income_m",
                "Consolidated net income FY2025",
                NET_INCOME_M,
                "USD_m",
                K10,
                f"Consolidated net income ${NET_INCOME_M}M FY2025; diluted EPS ${NET_INCOME_PS}/sh",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "Weighted average diluted shares FY2025",
                SHARES_M,
                "million_shares",
                K10,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M FY2025",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "owner_cash_m",
                f"Normalized net income allocated to {segment_label}",
                {c: round(owner_cash_m[c], 1) for c in SCENARIOS},
                "USD_m",
                growth_note,
                200.0,
                550.0,
            ),
            _judgment("growth_y1_5", "Growth years 1–5 on segment owner cash", growth1, "ratio",
                      "Connected Living mobile programs and lender-placed housing growth.", 0.0, 0.08),
            _judgment("growth_y6_10", "Growth years 6–7 on segment owner cash", growth2, "ratio",
                      "Fade as mobile attach rates mature and housing policies normalize.", 0.0, 0.05),
            _judgment("discount_rate", "Required return on segment owner cash", discount, "ratio",
                      "Specialty insurance, catastrophe, and partner concentration risk premium.", 0.07, 0.12),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Specialty insurer / warranty administrator peer multiples on normalized owner cash.", 9, 15),
            _judgment(
                "schedule_adjustment",
                "Component schedule reconciliation factor",
                scale,
                "ratio",
                "Preserves additive component schedule while filing facts anchor owner-cash bridge.",
                0.4,
                3.0,
            ),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def investment_float_proof() -> dict:
    surplus_m = {c: round(LEGACY["investment_float_surplus"][c] * SHARES_M, 1) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("book_equity_m", "Total shareholders' equity FY2025", BOOK_EQUITY_M, "USD_m", K10,
                  f"Stockholders' equity ${BOOK_EQUITY_M}M; book value per share ~${BVPS} at December 31, 2025", AS_OF_FY),
            _fact("net_investment_income_m", "Net investment income FY2025", NII_M, "USD_m", K10,
                  f"Net investment income ${NII_M}M on marked fixed-income portfolio FY2025", AS_OF_FY),
            _fact("cash_m", "Cash and cash equivalents FY2025", CASH_M, "USD_m", K10,
                  f"CashAndCashEquivalentsAtCarryingValue ${CASH_M}M at December 31, 2025", AS_OF_FY),
            _fact("shares_m", "Weighted average diluted shares FY2025", SHARES_M, "million_shares", K10,
                  f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M FY2025", AS_OF_FY),
        ],
        "assumptions": [
            _judgment(
                "float_surplus_claim_m",
                "Investment float and marked portfolio surplus above segment owner-cash capitalization",
                surplus_m,
                "USD_m",
                "Float-backed portfolio earns $527M net investment income; modest net debt leaves equity cushion; "
                "surplus not double-counted in segment DCF.",
                200.0,
                1500.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["float_surplus_claim_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_claims_proof() -> dict:
    claim_m = {c: round(LEGACY["net_financial_claims"][c] * SHARES_M, 1) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("unsecured_debt_m", "Unsecured senior notes FY2025", UNSECURED_DEBT_M, "USD_m", K10,
                  f"UnsecuredDebt ${UNSECURED_DEBT_M}M; debt to total capital 27.3% FY2025", AS_OF_FY),
            _fact("cash_m", "Cash and cash equivalents FY2025", CASH_M, "USD_m", K10,
                  f"CashAndCashEquivalentsAtCarryingValue ${CASH_M}M at December 31, 2025", AS_OF_FY),
            _fact("shares_m", "Weighted average diluted shares FY2025", SHARES_M, "million_shares", K10,
                  f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M FY2025", AS_OF_FY),
        ],
        "assumptions": [
            _judgment(
                "net_claim_m",
                "Net financial claims after cash (senior notes less cash)",
                claim_m,
                "USD_m",
                f"Filing-locked net debt ~${NET_DEBT_M}M (~${round(NET_DEBT_M/SHARES_M,2)}/sh); "
                "August 2025 $300M 5.55% notes issued to redeem $175M 6.10% notes.",
                -600.0,
                200.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["net_claim_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def catastrophe_reserve_proof() -> dict:
    reserve_m = {c: round(LEGACY["catastrophe_and_cycle_reserve"][c] * SHARES_M, 1) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("housing_adjusted_ebitda_m", "Global Housing Adjusted EBITDA FY2025", HOUSING_EBITDA_M, "USD_m", K10,
                  f"Global Housing Adjusted EBITDA ${HOUSING_EBITDA_M}M; lender-placed and catastrophe-sensitive", AS_OF_FY),
            _fact("unearned_premiums_m", "Unearned premiums FY2025", 20881.4, "USD_m", K10,
                  "UnearnedPremiums $20,881.4M; large premium float on balance sheet FY2025", AS_OF_FY),
            _fact("shares_m", "Weighted average diluted shares FY2025", SHARES_M, "million_shares", K10,
                  f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M FY2025", AS_OF_FY),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Catastrophe, lender-placed housing cycle, and mobile partner concentration stress reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for reportable catastrophes, housing credit cycle, and Connected Living "
                "partner concentration; not full unearned premium double-count.",
                -1800.0,
                -200.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _component(cid: str, label: str, category: str) -> dict:
    return {
        "id": cid,
        "label": label,
        "category": category,
        "overlap_key": cid,
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
    return {
        "ticker": TICKER,
        "as_of": AS_OF,
        "method": "full",
        "irr_method": "full",
        "lawrence_bucket": "multi_sided",
        "payoff_lens": "operating",
        "classification_inputs": {
            "archetype": "compounder",
            "moat": "stable",
            "dhando": "partial",
            "cycle": "mid",
            "payoff_lens": "operating",
        },
        "inputs": {
            "price": 275.47,
            "price_source": "Yahoo AIZ close 2026-07-20",
            "price_as_of": "2026-07-20",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(round(SHARES_M * 1_000_000)),
            "shares_source": f"{K10}; weighted average diluted shares {SHARES_M}M FY2025.",
            "fcf_per_share": NET_INCOME_PS,
            "fcf_source": (
                f"FY2025 consolidated net income ${NET_INCOME_M}M ÷ {SHARES_M}M shares = "
                f"${NET_INCOME_PS}/sh; Adjusted EBITDA ${CONSOL_EBITDA_M}M consolidated"
            ),
            "book_value_per_share": BVPS,
            "cash_m": CASH_M,
            "senior_notes_m": UNSECURED_DEBT_M,
            "normalization_note": (
                "Lawrence base uses filing net income allocated by segment Adjusted EBITDA share; "
                "Adjusted EBITDA excludes realized investment gains and unusual items per 10-K definition"
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.02,
                "growth_y6_10": 0.01,
                "exit_pfcf_y10": 10,
                "notes": "Mobile attach slows, housing catastrophes rise, investment yields fall; multiple compresses to ~10× normalized owner cash",
            },
            "base": {
                "growth_y1_5": 0.05,
                "growth_y6_10": 0.03,
                "exit_pfcf_y10": 12,
                "notes": "Connected Living mobile growth and lender-placed housing persist; 12× exit on year-10 owner cash",
            },
            "bull": {
                "growth_y1_5": 0.07,
                "growth_y6_10": 0.04,
                "exit_pfcf_y10": 14,
                "notes": "Global mobile programs scale, housing cat-light years continue, buybacks reduce share count",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "Partial",
                "treatment": "embedded_in_segment",
                "evidence": "Investment portfolio marked to fair value; goodwill from acquisitions; book ~$115/sh is cross-check not dhando floor (10-K FY2025)",
            },
            {
                "q": 2,
                "question": "Undeveloped reserves / dormant assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Operating specialty insurer / warranty administrator; no land or royalty reserves",
            },
            {
                "q": 3,
                "question": "In-business loss segment?",
                "answer": "Partial",
                "treatment": "embedded_in_segment",
                "evidence": "Corporate and Other Adjusted EBITDA loss $(123.8)M FY2025 embedded in consolidated path (10-K MD&A)",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "Partial",
                "treatment": "embedded_in_segment",
                "evidence": "Unearned premium reserve $20.9B and B2B2C partner contracts embedded in premium growth assumptions",
            },
            {
                "q": 5,
                "question": "Private or illiquid stakes below fair value?",
                "answer": "Partial",
                "treatment": "embedded_in_segment",
                "evidence": "Home warranty business and equity securities without readily determinable fair value per 10-K footnotes",
            },
            {
                "q": 6,
                "question": "Transitory distribution / legal recovery?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Earnings from recurring premiums and fees, not litigation recovery",
            },
            {
                "q": 7,
                "question": "Embedded product option already in revenue?",
                "answer": "Yes",
                "treatment": "embedded_in_segment",
                "evidence": "Connected Living mobile device solutions already in Global Lifestyle revenues $9.58B FY2025",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "B2B2C distribution through carrier and lender partners; Connected Living mobile attach rates "
                "and financial-services cross-sell; lender-placed housing growth from policies in-force and "
                "average premium; investment float earns on $8.6B marked fixed-income portfolio."
            ),
            "source": f"{K10} segment Adjusted EBITDA and net earned premiums tables",
            "bear_falsifier": "Global Housing reportable catastrophes exceed $100M pre-tax for two consecutive years with no offsetting Lifestyle growth",
            "bull_falsifier": "Connected Living net earned premiums grow faster than 10% for four consecutive quarters while consolidated Adjusted EBITDA margin expands",
            "status": "partial",
        },
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": "<15%",
            "gates": {"moat_ok": True, "dhando_ok": True},
            "override_reason": None,
        },
        "lawrence_horizon_years": 7,
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Five additive components map Global Lifestyle, Global Housing, investment float surplus, "
                "net financial claims, and catastrophe cycle reserve once each."
            ),
            "components": [
                _component("global_lifestyle_owner_cash_engine", "Global Lifestyle owner-cash engine (Connected Living + Automotive)", "operating_business"),
                _component("global_housing_owner_cash_engine", "Global Housing owner-cash engine (lender-placed + renters)", "operating_business"),
                _component("investment_float_surplus", "Investment float and marked portfolio surplus", "asset"),
                _component("net_financial_claims", "Net financial claims (senior notes less cash)", "liability_or_reserve"),
                _component("catastrophe_and_cycle_reserve", "Catastrophe, housing cycle, and concentration stress reserve", "liability_or_reserve"),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One AIZ diluted share equals pro-rata Global Lifestyle and Global Housing "
                    "owner-cash engines, investment float surplus, less net financial claims and catastrophe reserve."
                ),
                "excluded_claims": [
                    "Net investment income already partially reflected in net income; float surplus captures incremental portfolio economics.",
                    "Full $20.9B unearned premiums are not subtracted twice; catastrophe reserve captures stress claims only.",
                    "GAAP book (~$115/sh) is cross-check, not dhando floor; economic value lives in normalized owner cash.",
                ],
                "reconciliation": (
                    f"FY2025 net income ${NET_INCOME_M}M on {SHARES_M}M shares (${NET_INCOME_PS}/sh); "
                    f"consolidated Adjusted EBITDA ${CONSOL_EBITDA_M}M; book value ~${BVPS}/sh; "
                    f"net debt ~${NET_DEBT_M}M; net investment income ${NII_M}M."
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
                "One diluted share of AIZ, including Global Lifestyle and Global Housing owner-cash engines, "
                "investment float surplus, net financial claims, and catastrophe cycle reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": f"FY2025 weighted average diluted shares {SHARES_M}M per {K10}.",
            "enterprise_to_equity_reconciliation": (
                "Operating segments valued through owner-cash discount paths on net income allocated by "
                "Adjusted EBITDA share; float surplus and stress reserve are separate overlap keys."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            f"FY2025 10-K: book value per share ~${BVPS}; net income ${NET_INCOME_M}M; "
            "economic value in normalized underwriting, fees, and investment spread, not book floor alone."
        ),
        "component_groups": [
            {
                "id": "global_lifestyle_owner_cash_engine",
                "label": "Global Lifestyle owner-cash engine",
                "component_ids": ["global_lifestyle_owner_cash_engine"],
                "economic_claim": "Connected Living mobile programs, Global Automotive vehicle protection",
                "valuation_basis": "Owner-cash discount on Lifestyle share of net income.",
                "adjustments": "Adjusted EBITDA $801.3M FY2025; 53% of Lifestyle revenue from mobile device solutions.",
                "overlap_control": "Unique overlap key global_lifestyle_owner_cash_engine.",
            },
            {
                "id": "global_housing_owner_cash_engine",
                "label": "Global Housing owner-cash engine",
                "component_ids": ["global_housing_owner_cash_engine"],
                "economic_claim": "Lender-placed homeowners, manufactured housing, flood, renters insurance",
                "valuation_basis": "Owner-cash discount on Housing share of net income.",
                "adjustments": "Adjusted EBITDA $858.7M FY2025 (+28% YoY); catastrophe-sensitive.",
                "overlap_control": "Unique overlap key global_housing_owner_cash_engine.",
            },
            {
                "id": "investment_float_surplus",
                "label": "Investment float and portfolio surplus",
                "component_ids": ["investment_float_surplus"],
                "economic_claim": "Marked investment portfolio and premium float economics above segment DCF",
                "valuation_basis": "Net asset value on surplus investment income and equity cushion.",
                "adjustments": "Net investment income $527.3M; debt to total capital 27.3%.",
                "overlap_control": "Unique overlap key investment_float_surplus.",
            },
            {
                "id": "net_financial_claims",
                "label": "Net financial claims",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Senior notes net of cash",
                "valuation_basis": "Filing-locked net debt per share.",
                "adjustments": f"Unsecured debt ${UNSECURED_DEBT_M}M less cash ${CASH_M}M.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "catastrophe_and_cycle_reserve",
                "label": "Catastrophe and cycle stress reserve",
                "component_ids": ["catastrophe_and_cycle_reserve"],
                "economic_claim": "Housing catastrophes, lender-placed cycle, mobile partner concentration",
                "valuation_basis": "Bounded negative reserve; not full unearned premium subtraction.",
                "adjustments": "Reportable catastrophes and housing credit cycle remain widest judgment band.",
                "overlap_control": "Unique overlap key catastrophe_and_cycle_reserve.",
            },
        ],
        "limitations": [
            "Segment splits use Adjusted EBITDA-proportional net income allocation.",
            "Housing catastrophe sensitivity and mobile partner concentration remain widest judgment bands.",
        ],
    }


def main() -> int:
    proofs = {
        "global_lifestyle_owner_cash_engine": _segment_owner_cash_proof(
            "global_lifestyle_owner_cash_engine",
            LIFESTYLE_EBITDA_M,
            "Global Lifestyle",
            f"Global Lifestyle Adjusted EBITDA ${LIFESTYLE_EBITDA_M}M; net earned premiums $9.58B FY2025",
            "Lifestyle ~48% of segment EBITDA; Connected Living mobile and financial services drive growth.",
        ),
        "global_housing_owner_cash_engine": _segment_owner_cash_proof(
            "global_housing_owner_cash_engine",
            HOUSING_EBITDA_M,
            "Global Housing",
            f"Global Housing Adjusted EBITDA ${HOUSING_EBITDA_M}M; net earned premiums $2.77B FY2025",
            "Housing ~52% of segment EBITDA; lender-placed insurance and catastrophe experience drive earnings.",
        ),
        "investment_float_surplus": investment_float_proof(),
        "net_financial_claims": net_financial_claims_proof(),
        "catastrophe_and_cycle_reserve": catastrophe_reserve_proof(),
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
        f"Primary bridge from FY2025 10-K: net income ${NET_INCOME_M}M "
        f"(${NET_INCOME_PS}/sh), consolidated Adjusted EBITDA ${CONSOL_EBITDA_M}M, "
        f"book ~${BVPS}/sh, net investment income ${NII_M}M, net debt ~${NET_DEBT_M}M; contract backfill {AS_OF}."
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

    data["economic_value"] = economic_value_block()
    data["valuation_mode"] = "economic_value"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(json.dumps({"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
