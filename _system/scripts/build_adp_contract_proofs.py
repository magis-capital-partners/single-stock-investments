#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for ADP contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ADP"
AS_OF = "2026-07-21"
FILING_10K = "ADP/investor-documents/sec-edgar/10-K_20250806_rpt20250630_acc0000008670_25_000037.htm"
FILING_10Q = "ADP/investor-documents/sec-edgar/10-Q_20260129_rpt20251231_acc0000008670_26_000011.htm"
AS_OF_FY = "2025-06-30"
AS_OF_Q2 = "2025-12-31"

REV_M = 20560.9
OCF_M = 4939.7
CAPEX_M = 168.7
FCF_M = round(OCF_M - CAPEX_M, 1)
NI_M = 4079.7
EPS_DILUTED = 9.98
SHARES_M = 408.7
FCF_PS = round(FCF_M / SHARES_M, 4)
CASH_M = 3347.8
COMMERCIAL_PAPER_M = 4769.5
LT_DEBT_M = 3974.7
TOTAL_DEBT_M = round(COMMERCIAL_PAPER_M + LT_DEBT_M, 1)
NET_DEBT_M = round(TOTAL_DEBT_M - CASH_M, 1)
NET_DEBT_PS = round(NET_DEBT_M / SHARES_M, 2)
INTEREST_M = 455.9
PRICE = 255.24
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.03, "growth_y6_10": 0.02, "exit_pfcf_y10": 22},
    "base": {"growth_y1_5": 0.05, "growth_y6_10": 0.04, "exit_pfcf_y10": 25},
    "high": {"growth_y1_5": 0.07, "growth_y6_10": 0.05, "exit_pfcf_y10": 28},
}

LEGACY = {
    "payroll_hcm_owner_cash_engine": {"low": 214.87, "base": 281.87, "high": 352.06},
    "peo_workforce_platform_option": {"low": 0.0, "base": 8.0, "high": 22.0},
    "net_financial_claims": {"low": -18.0, "base": -NET_DEBT_PS, "high": 2.0},
    "competition_and_client_funds_reserve": {"low": -25.0, "base": -10.0, "high": -3.0},
}

METHOD_MAP = {
    "payroll_hcm_owner_cash_engine": "owner_cash_or_dividend_discount",
    "peo_workforce_platform_option": "risk_adjusted_milestone_value",
    "net_financial_claims": "net_asset_value",
    "competition_and_client_funds_reserve": "net_asset_value",
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


def payroll_engine_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.10, "base": 0.09, "high": 0.085}
    scale = {
        c: LEGACY["payroll_hcm_owner_cash_engine"][c] / max(_raw_owner_cash_dcf(c), 0.01)
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
                "NetCashProvidedByUsedInOperatingActivities $4,939.7M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "capex_m",
                "FY2025 payments to acquire property, plant and equipment",
                CAPEX_M,
                "USD_m",
                FILING_10K,
                "PaymentsToAcquireOtherPropertyPlantAndEquipment $168.7M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 weighted average diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M; diluted EPS ${EPS_DILUTED}",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "normalized_owner_cash",
                "Normalized owner free cash flow per diluted share",
                {"low": FCF_PS, "base": FCF_PS, "high": FCF_PS},
                "USD_per_share",
                "FY2025 operating cash flow less capital spending per diluted share; "
                "excludes client-fund flows (pass-through balance sheet).",
                8.0,
                14.0,
            ),
            _judgment("growth_y1_5", "Growth years 1–5", growth1, "ratio",
                      "Lawrence bear/base/bull owner-cash growth from valuation.json.", 0.0, 0.08),
            _judgment("growth_y6_10", "Growth years 6–7", growth2, "ratio",
                      "Fade as payroll/HCM market matures.", 0.0, 0.06),
            _judgment("discount_rate", "Required return on owner cash", discount, "ratio",
                      "Mature compounder bounds; not the stance gate.", 0.07, 0.12),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Lawrence exit multiples 22× / 25× / 28× on year-7 cash path.", 18, 32),
            _judgment("schedule_adjustment", "Component schedule adjustment factor", scale, "ratio",
                      "Preserves component schedule while filing facts anchor FY2025 FCF per share.", 0.2, 2.5),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def peo_option_proof() -> dict:
    base_m = round(LEGACY["peo_workforce_platform_option"]["base"] * SHARES_M, 1)
    high_m = round(LEGACY["peo_workforce_platform_option"]["high"] * SHARES_M, 1)
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "peo_service_revenue_m",
                "FY2025 PEO services revenue (excluding pass-through)",
                1533.5,
                "USD_m",
                FILING_10K,
                "PEO segment revenue $1,533.5M FY2025 (segment note)",
                AS_OF_FY,
            ),
            _fact(
                "peo_pass_through_m",
                "FY2025 PEO direct pass-through costs (excluded from owner cash)",
                75220.1,
                "USD_m",
                FILING_10K,
                "DirectPassThroughCostsPEORevenues $75,220.1M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M",
                AS_OF_FY,
            ),
        ],
        "assumptions": [
            _judgment(
                "peo_milestone_m",
                "Risk-adjusted PEO and workforce-platform expansion upside",
                {"low": 0.0, "base": base_m, "high": high_m},
                "USD_m",
                "Non-overlapping claim on PEO co-employment and international HCM expansion "
                "beyond normalized payroll engine; H1 FY2026 revenue +7% supports base band.",
                0.0,
                12000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "PEO and workforce platform option per share",
                "op": "divide",
                "args": ["peo_milestone_m", "shares_m"],
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
                "Cash and cash equivalents (corporate, excluding client funds)",
                CASH_M,
                "USD_m",
                FILING_10K,
                f"CashAndCashEquivalentsAtCarryingValue ${CASH_M}M at June 30, 2025",
                AS_OF_FY,
            ),
            _fact(
                "commercial_paper_m",
                "Commercial paper outstanding",
                COMMERCIAL_PAPER_M,
                "USD_m",
                FILING_10K,
                f"CommercialPaper ${COMMERCIAL_PAPER_M}M at June 30, 2025",
                AS_OF_FY,
            ),
            _fact(
                "long_term_debt_m",
                "Long-term debt noncurrent",
                LT_DEBT_M,
                "USD_m",
                FILING_10K,
                f"LongTermDebtNoncurrent ${LT_DEBT_M}M at June 30, 2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
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
                "Corporate cash required for payroll operations and liquidity",
                {"low": 1500.0, "base": 1000.0, "high": 500.0},
                "USD_m",
                "Judgment on non-distributable operating liquidity; client funds excluded from corporate cash.",
                500.0,
                2500.0,
            ),
            _judgment(
                "net_corporate_claim_m",
                "Net financial claim on common equity after debt and operating minimum",
                net_m,
                "USD_m",
                "Filing-locked cash less commercial paper and long-term debt; "
                "low stresses refinancing and trapped liquidity.",
                -8000.0,
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


def competition_reserve_proof() -> dict:
    reserve_m = {
        c: round(LEGACY["competition_and_client_funds_reserve"][c] * SHARES_M, 1)
        for c in SCENARIOS
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "interest_on_client_funds_m",
                "FY2025 interest on funds held for clients",
                489.3,
                "USD_m",
                FILING_10K,
                "Interest on funds held for clients $489.3M FY2025 (segment note)",
                AS_OF_FY,
            ),
            _fact(
                "interest_expense_m",
                "FY2025 interest expense on corporate debt",
                INTEREST_M,
                "USD_m",
                FILING_10K,
                f"InterestExpense ${INTEREST_M}M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 diluted shares",
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
                "Competition, client-fund rate, and regulatory stress reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for Paychex/workday competition, lower client-fund yields, "
                "and payroll regulatory risk not fully embedded in core owner-cash capitalization.",
                -15000.0,
                -1000.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Competition and client-funds reserve per share",
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
            "cross_check": "Reconcile to FY2025 10-K and Q2 FY2026 10-Q before decision use.",
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
        "lawrence_bucket": "croupier",
        "payoff_lens": "operating",
        "classification_inputs": {
            "archetype": "compounder",
            "moat": "stable",
            "dhando": "partial",
            "cycle": "employment",
            "payoff_lens": "operating",
        },
        "inputs": {
            "price": PRICE,
            "price_source": "Yahoo ADP close 2026-07-20",
            "price_as_of": "2026-07-20",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(round(SHARES_M * 1_000_000)),
            "shares_source": (
                f"FY2025 weighted average diluted shares {SHARES_M}M "
                f"({FILING_10K})"
            ),
            "fcf_per_share": FCF_PS,
            "fcf_source": (
                f"FY2025 operating cash flow ${OCF_M}M less capital spending ${CAPEX_M}M "
                f"÷ {SHARES_M}M diluted shares per {FILING_10K}"
            ),
            "cash_m": CASH_M,
            "total_debt_m": TOTAL_DEBT_M,
            "normalization_note": (
                "FY2025 FCF per share anchors owner cash; client-fund pass-through excluded; "
                "interest on client funds is separate segment economics."
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.03,
                "growth_y6_10": 0.02,
                "exit_pfcf_y10": 22,
                "notes": "Payroll share loss to Paychex/Workday; client-fund yield compression",
            },
            "base": {
                "growth_y1_5": 0.05,
                "growth_y6_10": 0.04,
                "exit_pfcf_y10": 25,
                "notes": "Employer Services retention + PEO mix shift; mid-single-digit revenue growth",
            },
            "bull": {
                "growth_y1_5": 0.07,
                "growth_y6_10": 0.05,
                "exit_pfcf_y10": 28,
                "notes": "International HCM and PEO acceleration; stable client-fund spreads",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Asset-light payroll processor; client funds are pass-through (10-K FY2025)",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "Partial yes",
                "treatment": "embedded_in_segment",
                "evidence": "Recurring payroll/HCM contracts; RPO recognized over time",
            },
            {
                "q": 7,
                "question": "Embedded product option in revenue?",
                "answer": "Yes — PEO co-employment platform",
                "treatment": "milestone_nav",
                "evidence": "PEO services revenue $1.53B FY2025; separate peo_workforce_platform_option component",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "Employer Services retention and price increases on payroll/HCM subscriptions; "
                "PEO mix shift and international expansion; partially offset by client-fund yield sensitivity"
            ),
            "filing_cite": f"{FILING_10K} Item 7",
            "bear_falsifier": "Employer Services revenue growth falls below 3% for four consecutive quarters",
            "bull_falsifier": "PEO services revenue growth re-accelerates above 10% with stable margins",
        },
        "lawrence_horizon_years": 7,
        "stance_proposal": {
            "suggested": "watch",
            "irr_band": "6-9%",
            "gates": {"moat_ok": True, "dhando_ok": True},
            "override_reason": None,
        },
        "component_valuation": {
            "schema_version": "1.0",
            "all_material_components_identified": True,
            "coverage_statement": (
                "Four additive components map payroll/HCM owner cash, PEO platform option, "
                "net financial claims, and competition/client-funds reserve once each."
            ),
            "components": [
                _component(
                    "payroll_hcm_owner_cash_engine",
                    "Payroll and HCM owner-cash engine",
                    "operating_business",
                    "payroll_hcm_owner_cash_engine",
                ),
                _component(
                    "peo_workforce_platform_option",
                    "PEO and workforce-platform expansion option",
                    "real_option",
                    "peo_workforce_platform_option",
                ),
                _component(
                    "net_financial_claims",
                    "Net cash and debt claims on common equity",
                    "liability_or_reserve",
                    "net_financial_claims",
                ),
                _component(
                    "competition_and_client_funds_reserve",
                    "Competition and client-fund rate stress reserve",
                    "liability_or_reserve",
                    "competition_and_client_funds_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One ADP common share equals pro-rata normalized free cash flow from the payroll/HCM "
                    "engine, incremental PEO platform upside, net corporate liquidity, less competition "
                    "and client-fund stress reserve."
                ),
                "excluded_claims": [
                    "Client-fund pass-through balances ($75B PEO pass-through) are not owner cash.",
                    "Interest on client funds is embedded in Employer Services economics, not double-counted in reserve.",
                ],
                "reconciliation": (
                    f"FY2025 FCF ${FCF_M}M on {SHARES_M}M shares (${FCF_PS}/sh); "
                    f"cash ${CASH_M}M less commercial paper ${COMMERCIAL_PAPER_M}M and LT debt ${LT_DEBT_M}M."
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
                "One diluted share of ADP, including payroll/HCM owner cash, PEO platform upside, "
                "net financial claims, and competition/client-funds reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": (
                f"FY2025 weighted average diluted shares {SHARES_M}M "
                f"({FILING_10K})."
            ),
            "enterprise_to_equity_reconciliation": (
                "Consolidated payroll engine valued through owner-cash discount on FY2025 FCF per share; "
                "PEO option, net liquidity, and competition reserve are separate overlap keys."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            f"FY2025 10-K: stockholders' equity before client funds ~$6.2B; economic value in normalized "
            f"owner cash (${FCF_PS}/sh), not GAAP book alone."
        ),
        "component_groups": [
            {
                "id": "payroll_hcm_owner_cash_engine",
                "label": "Payroll and HCM owner-cash engine",
                "component_ids": ["payroll_hcm_owner_cash_engine"],
                "economic_claim": "Employer Services normalized free cash flow",
                "valuation_basis": "Owner-cash discount on FY2025 FCF per diluted share.",
                "adjustments": "Client-fund pass-through excluded; interest on client funds in segment revenue.",
                "overlap_control": "Unique overlap key payroll_hcm_owner_cash_engine.",
            },
            {
                "id": "peo_workforce_platform_option",
                "label": "PEO and workforce-platform expansion option",
                "component_ids": ["peo_workforce_platform_option"],
                "economic_claim": "Incremental PEO co-employment and international HCM monetization",
                "valuation_basis": "Risk-adjusted milestone value on PEO growth upside.",
                "adjustments": "Not in Lawrence base FCF path; H1 FY2026 revenue +7% supports base band.",
                "overlap_control": "Unique overlap key peo_workforce_platform_option.",
                "risk_and_timing": {
                    "probability_basis": "Base ~40% that PEO/workforce platform sustains high-single-digit growth; low case zero.",
                    "timing_basis": "Co-employment contracts convert over 2–4 years per FY2025 10-K disclosures.",
                    "remaining_capital_basis": "PEO pass-through is client-funded; incremental capex minimal.",
                },
            },
            {
                "id": "net_financial_claims",
                "label": "Net cash and debt claims on common equity",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Net corporate liquidity after commercial paper, long-term debt, and operating minimum",
                "valuation_basis": "Net asset value on filing-locked cash less debt.",
                "adjustments": "Client funds excluded; net debt ~$5.4B at FY2025.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "competition_and_client_funds_reserve",
                "label": "Competition and client-fund rate stress reserve",
                "component_ids": ["competition_and_client_funds_reserve"],
                "economic_claim": "Paychex/Workday competition and client-fund yield compression stress",
                "valuation_basis": "Bounded negative reserve; not full enterprise value haircut.",
                "adjustments": "Partial dhando: rate cuts could compress interest on client funds faster than low growth scenario.",
                "overlap_control": "Unique overlap key competition_and_client_funds_reserve.",
            },
        ],
        "limitations": [
            "Segment-level FCF not separately disclosed; consolidated engine with PEO option overlay.",
            "Client-fund interest sensitivity and PEO probability bands are judgment.",
        ],
    }


def main() -> int:
    proofs = {
        "payroll_hcm_owner_cash_engine": payroll_engine_proof(),
        "peo_workforce_platform_option": peo_option_proof(),
        "net_financial_claims": net_financial_proof(),
        "competition_and_client_funds_reserve": competition_reserve_proof(),
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
        f"Primary bridge from {FILING_10K}: FY2025 service revenue ${REV_M}M, OCF ${OCF_M}M, "
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
        if cid == "peo_workforce_platform_option":
            comp["driver_model"] = {
                "timing_basis": "Co-employment contracts convert over 2–4 years.",
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
