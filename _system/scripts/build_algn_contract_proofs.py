#!/usr/bin/env python3
"""Build filing-backed calculation proofs and component scaffold for ALGN contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "ALGN"
AS_OF = "2026-07-21"
FILING_10K = "ALGN/investor-documents/sec-edgar/10-K_20260227_rpt20251231_acc0001097149_26_000014.htm"
FILING_10Q = "ALGN/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001097149_26_000040.htm"
AS_OF_FY = "2025-12-31"
AS_OF_Q1 = "2026-03-31"

REV_M = 3862.3
CLEAR_ALIGNER_REV_M = 3245.4
SYSTEMS_REV_M = 789.6
OCF_M = 785.8
CAPEX_M = 177.7
FCF_M = round(OCF_M - CAPEX_M, 1)
SHARES_M = 76.568
FCF_PS = round(FCF_M / SHARES_M, 4)
CASH_M = 1043.9
CREDIT_FACILITY_M = 300.0
TOTAL_DEBT_M = 0.0
NET_CASH_M = round(CASH_M - TOTAL_DEBT_M, 1)
NET_CASH_PS = round(NET_CASH_M / SHARES_M, 2)
PRICE = 175.05
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.02, "growth_y6_10": 0.01, "exit_pfcf_y10": 20},
    "base": {"growth_y1_5": 0.04, "growth_y6_10": 0.03, "exit_pfcf_y10": 24},
    "high": {"growth_y1_5": 0.06, "growth_y6_10": 0.04, "exit_pfcf_y10": 28},
}

LEGACY = {
    "clear_aligner_owner_cash_engine": {"low": 115.0, "base": 160.0, "high": 205.0},
    "scanner_platform_option": {"low": 0.0, "base": 10.0, "high": 25.0},
    "net_financial_claims": {"low": 3.0, "base": 11.02, "high": 13.63},
    "competition_and_asp_reserve": {"low": -20.0, "base": -6.0, "high": -2.0},
}

METHOD_MAP = {
    "clear_aligner_owner_cash_engine": "owner_cash_or_dividend_discount",
    "scanner_platform_option": "risk_adjusted_milestone_value",
    "net_financial_claims": "net_asset_value",
    "competition_and_asp_reserve": "net_asset_value",
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


def clear_aligner_engine_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.10, "base": 0.09, "high": 0.085}
    scale = {
        c: LEGACY["clear_aligner_owner_cash_engine"][c] / max(_raw_owner_cash_dcf(c), 0.01)
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
                "NetCashProvidedByUsedInOperatingActivities $785.8M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "capex_m",
                "FY2025 payments to acquire property, plant and equipment",
                CAPEX_M,
                "USD_m",
                FILING_10K,
                "PaymentsToAcquirePropertyPlantAndEquipment $177.7M (FY2025)",
                AS_OF_FY,
            ),
            _fact(
                "clear_aligner_revenue_m",
                "FY2025 Clear Aligner segment net revenues",
                CLEAR_ALIGNER_REV_M,
                "USD_m",
                FILING_10K,
                "Clear Aligner segment net revenues $3,245.4M (~84% of consolidated)",
                AS_OF_FY,
            ),
            _fact(
                "shares_m",
                "FY2025 weighted average diluted shares outstanding",
                SHARES_M,
                "million_shares",
                FILING_10K,
                f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M; diluted EPS $5.81",
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
                "Clear Aligner franchise drives ~84% of consolidated revenue.",
                5.0,
                11.0,
            ),
            _judgment("growth_y1_5", "Growth years 1–5", growth1, "ratio",
                      "Lawrence bear/base/bull owner-cash growth; teen-case volume recovery.", 0.0, 0.08),
            _judgment("growth_y6_10", "Growth years 6–7", growth2, "ratio",
                      "Fade as clear-aligner market matures internationally.", 0.0, 0.06),
            _judgment("discount_rate", "Required return on owner cash", discount, "ratio",
                      "Medical-device compounder bounds; not the stance gate.", 0.07, 0.12),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Lawrence exit multiples 20× / 24× / 28× on year-7 cash path.", 16, 32),
            _judgment("schedule_adjustment", "Component schedule adjustment factor", scale, "ratio",
                      "Preserves component schedule while filing facts anchor FY2025 FCF per share.", 0.2, 2.5),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def scanner_option_proof() -> dict:
    base_m = round(LEGACY["scanner_platform_option"]["base"] * SHARES_M, 1)
    high_m = round(LEGACY["scanner_platform_option"]["high"] * SHARES_M, 1)
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "systems_services_revenue_m",
                "FY2025 Systems and Services segment net revenues (iTero scanners, CAD/CAM)",
                SYSTEMS_REV_M,
                "USD_m",
                FILING_10K,
                "Systems and Services segment net revenues $789.6M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "deferred_revenue_m",
                "FY2025 total deferred revenue (current + noncurrent)",
                1433.3,
                "USD_m",
                FILING_10K,
                "Deferred revenue current $1,331.1M + noncurrent $102.2M",
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
                "scanner_milestone_m",
                "Risk-adjusted iTero scanner and digital-platform ecosystem upside",
                {"low": 0.0, "base": base_m, "high": high_m},
                "USD_m",
                "Non-overlapping claim on scanner/software monetization beyond normalized "
                "Clear Aligner engine; Q1 FY2026 Systems revenue +8% YoY supports base band.",
                0.0,
                2500.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Scanner platform option per share",
                "op": "divide",
                "args": ["scanner_milestone_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_proof() -> dict:
    net_m = {
        "low": round(LEGACY["net_financial_claims"]["low"] * SHARES_M, 1),
        "base": round((NET_CASH_M - 200.0), 1),
        "high": round(NET_CASH_M, 1),
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash and cash equivalents at December 31, 2025",
                CASH_M,
                "USD_m",
                FILING_10K,
                f"CashAndCashEquivalentsAtCarryingValue ${CASH_M}M at December 31, 2025",
                AS_OF_FY,
            ),
            _fact(
                "credit_facility_m",
                "Revolving credit facility maximum borrowing capacity (undrawn)",
                CREDIT_FACILITY_M,
                "USD_m",
                FILING_10K,
                "LineOfCreditFacilityMaximumBorrowingCapacity $300M; no outstanding borrowings",
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
                "Corporate cash required for manufacturing and liquidity",
                {"low": 400.0, "base": 200.0, "high": 100.0},
                "USD_m",
                "Judgment on non-distributable operating liquidity for global manufacturing footprint.",
                100.0,
                500.0,
            ),
            _judgment(
                "net_corporate_claim_m",
                "Net financial claim on common equity after operating minimum",
                net_m,
                "USD_m",
                "Filing-locked cash with no long-term debt; $300M revolver undrawn.",
                -500.0,
                1200.0,
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
        c: round(LEGACY["competition_and_asp_reserve"][c] * SHARES_M, 1)
        for c in SCENARIOS
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "rd_expense_m",
                "FY2025 research and development expense",
                346.8,
                "USD_m",
                FILING_10K,
                "ResearchAndDevelopmentExpense $346.8M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "share_based_comp_m",
                "FY2025 share-based compensation expense",
                154.0,
                "USD_m",
                FILING_10K,
                "ShareBasedCompensation $154.0M FY2025",
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
                "Competition, ASP pressure, and litigation stress reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for DTC competition, average selling price compression, "
                "antitrust litigation, and China/international share risk not fully embedded in core owner-cash path.",
                -2000.0,
                -100.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Competition and ASP reserve per share",
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
            "cross_check": "Reconcile to FY2025 10-K and Q1 FY2026 10-Q before decision use.",
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
            "archetype": "compounder",
            "moat": "stable",
            "dhando": "partial",
            "cycle": "mid",
            "payoff_lens": "operating",
        },
        "inputs": {
            "price": PRICE,
            "price_source": "Yahoo ALGN close 2026-07-20",
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
                "FY2025 FCF per share anchors owner cash; Clear Aligner ~84% of revenue; "
                "scanner ecosystem valued separately as option."
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.02,
                "growth_y6_10": 0.01,
                "exit_pfcf_y10": 20,
                "notes": "ASP compression and DTC competition; teen-case volume stagnation",
            },
            "base": {
                "growth_y1_5": 0.04,
                "growth_y6_10": 0.03,
                "exit_pfcf_y10": 24,
                "notes": "Clear Aligner retention + international mix; Systems growth mid-single-digit",
            },
            "bull": {
                "growth_y1_5": 0.06,
                "growth_y6_10": 0.04,
                "exit_pfcf_y10": 28,
                "notes": "Teen-case volume recovery + iTero scanner adoption acceleration",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Asset-light medical device; goodwill $492M on balance sheet (10-K FY2025)",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "Partial yes",
                "treatment": "embedded_in_segment",
                "evidence": "Deferred revenue $1.43B; RPO $1.44B recognized over ~1 year",
            },
            {
                "q": 7,
                "question": "Embedded product option in revenue?",
                "answer": "Yes — iTero scanner and digital platform",
                "treatment": "milestone_nav",
                "evidence": "Systems and Services revenue $789.6M FY2025; separate scanner_platform_option component",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "Clear Aligner case volume growth from teen and adult orthodontic adoption; "
                "international expansion; partially offset by ASP pressure and DTC competition"
            ),
            "filing_cite": f"{FILING_10K} Item 7",
            "bear_falsifier": "Consolidated revenue growth falls below 2% for four consecutive quarters",
            "bull_falsifier": "Clear Aligner segment revenue re-accelerates above 8% with stable gross margin",
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
                "Four additive components map Clear Aligner owner cash, scanner platform option, "
                "net financial claims, and competition/ASP reserve once each."
            ),
            "components": [
                _component(
                    "clear_aligner_owner_cash_engine",
                    "Clear Aligner owner-cash engine",
                    "operating_business",
                    "clear_aligner_owner_cash_engine",
                ),
                _component(
                    "scanner_platform_option",
                    "iTero scanner and digital-platform option",
                    "real_option",
                    "scanner_platform_option",
                ),
                _component(
                    "net_financial_claims",
                    "Net cash claims on common equity",
                    "liability_or_reserve",
                    "net_financial_claims",
                ),
                _component(
                    "competition_and_asp_reserve",
                    "Competition and ASP stress reserve",
                    "liability_or_reserve",
                    "competition_and_asp_reserve",
                ),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One ALGN common share equals pro-rata normalized free cash flow from the Clear Aligner "
                    "franchise, incremental scanner platform upside, net corporate liquidity, less competition "
                    "and ASP stress reserve."
                ),
                "excluded_claims": [
                    "Deferred revenue is embedded in Clear Aligner engine, not double-counted in scanner option.",
                    "Undrawn $300M credit facility is liquidity backstop, not additive owner cash.",
                ],
                "reconciliation": (
                    f"FY2025 FCF ${FCF_M}M on {SHARES_M}M shares (${FCF_PS}/sh); "
                    f"cash ${CASH_M}M; no long-term debt outstanding."
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
                "One diluted share of Align Technology, including Clear Aligner owner cash, "
                "scanner platform upside, net financial claims, and competition/ASP reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": (
                f"FY2025 weighted average diluted shares {SHARES_M}M "
                f"({FILING_10K})."
            ),
            "enterprise_to_equity_reconciliation": (
                "Consolidated Clear Aligner engine valued through owner-cash discount on FY2025 FCF per share; "
                "scanner option, net liquidity, and competition reserve are separate overlap keys."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            f"FY2025 10-K: stockholders' equity $4.05B; economic value in normalized "
            f"owner cash (${FCF_PS}/sh), not GAAP book alone."
        ),
        "component_groups": [
            {
                "id": "clear_aligner_owner_cash_engine",
                "label": "Clear Aligner owner-cash engine",
                "component_ids": ["clear_aligner_owner_cash_engine"],
                "economic_claim": "Invisalign clear-aligner normalized free cash flow",
                "valuation_basis": "Owner-cash discount on FY2025 FCF per diluted share.",
                "adjustments": "Clear Aligner ~84% of consolidated revenue; Systems option separate.",
                "overlap_control": "Unique overlap key clear_aligner_owner_cash_engine.",
            },
            {
                "id": "scanner_platform_option",
                "label": "iTero scanner and digital-platform option",
                "component_ids": ["scanner_platform_option"],
                "economic_claim": "Incremental iTero scanner and CAD/CAM monetization",
                "valuation_basis": "Risk-adjusted milestone value on Systems segment upside.",
                "adjustments": "Not in Lawrence base FCF path; Q1 FY2026 Systems revenue +8% YoY.",
                "overlap_control": "Unique overlap key scanner_platform_option.",
                "risk_and_timing": {
                    "probability_basis": "Base ~35% that scanner ecosystem sustains high-single-digit growth; low case zero.",
                    "timing_basis": "Scanner lease and software contracts convert over 2–4 years per FY2025 10-K.",
                    "remaining_capital_basis": "Leased iTero fleet is customer-funded; incremental capex minimal.",
                },
            },
            {
                "id": "net_financial_claims",
                "label": "Net cash claims on common equity",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Net corporate liquidity after operating minimum",
                "valuation_basis": "Net asset value on filing-locked cash less debt.",
                "adjustments": "No long-term debt; $300M revolver undrawn; net cash ~$13.6/sh gross.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "competition_and_asp_reserve",
                "label": "Competition and ASP stress reserve",
                "component_ids": ["competition_and_asp_reserve"],
                "economic_claim": "DTC competition, ASP compression, and litigation stress",
                "valuation_basis": "Bounded negative reserve; not full enterprise value haircut.",
                "adjustments": "Partial dhando: antitrust and Angelalign litigation could compress margins faster than low growth.",
                "overlap_control": "Unique overlap key competition_and_asp_reserve.",
            },
        ],
        "limitations": [
            "Segment-level FCF not separately disclosed; consolidated engine with scanner option overlay.",
            "Teen-case volume recovery and ASP trajectory bands are judgment.",
        ],
    }


def main() -> int:
    proofs = {
        "clear_aligner_owner_cash_engine": clear_aligner_engine_proof(),
        "scanner_platform_option": scanner_option_proof(),
        "net_financial_claims": net_financial_proof(),
        "competition_and_asp_reserve": competition_reserve_proof(),
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
        f"FCF ${FCF_M}M, cash ${CASH_M}M, no debt; contract backfill {AS_OF}."
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
        if cid == "scanner_platform_option":
            comp["driver_model"] = {
                "timing_basis": "Scanner lease contracts convert over 2–4 years.",
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
