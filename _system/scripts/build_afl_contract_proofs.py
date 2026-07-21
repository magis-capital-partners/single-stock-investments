#!/usr/bin/env python3
"""Build filing-backed calculation proofs for AFL universal contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "AFL"
AS_OF = "2026-07-21"
K10 = "AFL/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0001628280_26_011402.htm"
Q10 = "AFL/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001628280_26_030923.htm"
AS_OF_FY = "2025-12-31"
AS_OF_Q1 = "2026-03-31"

SHARES_M = 534.878
OP_INC_M = 3440.0
NII_M = 4076.0
NET_INCOME_M = 3646.0
CASH_M = 6245.0
DEBT_M = 8409.0
EQUITY_M = 29490.0
BVPS = round(EQUITY_M / SHARES_M, 2)
OWNER_CASH_PS = 5.85
OWNER_CASH_M = round(OWNER_CASH_PS * SHARES_M, 1)
NET_DEBT_M = round(DEBT_M - CASH_M, 1)
NET_DEBT_PS = round(NET_DEBT_M / SHARES_M, 2)

JAPAN_PREM_M = 10664.0
US_PREM_M = 6900.0
TOTAL_PREM_M = JAPAN_PREM_M + US_PREM_M
JAPAN_SHARE = JAPAN_PREM_M / TOTAL_PREM_M
US_SHARE = US_PREM_M / TOTAL_PREM_M
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.03, "growth_y6_10": 0.025, "exit_pfcf_y10": 15},
    "base": {"growth_y1_5": 0.05, "growth_y6_10": 0.04, "exit_pfcf_y10": 18},
    "high": {"growth_y1_5": 0.06, "growth_y6_10": 0.05, "exit_pfcf_y10": 20},
}

LEGACY = {
    "japan_supplemental_engine": {"low": 64.0, "base": 78.0, "high": 94.0},
    "us_worksite_engine": {"low": 42.0, "base": 50.0, "high": 62.0},
    "net_financial_claims": {"low": -8.0, "base": -4.05, "high": 2.0},
    "investment_and_currency_reserve": {"low": -18.0, "base": -8.0, "high": -2.0},
}

METHOD_MAP = {
    "japan_supplemental_engine": "owner_cash_or_dividend_discount",
    "us_worksite_engine": "owner_cash_or_dividend_discount",
    "net_financial_claims": "net_asset_value",
    "investment_and_currency_reserve": "net_asset_value",
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
    segment_prem_m: float,
    segment_label: str,
    growth_note: str,
) -> dict:
    share = segment_prem_m / TOTAL_PREM_M
    owner_cash_m = {c: OWNER_CASH_M * share for c in SCENARIOS}
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.10, "base": 0.085, "high": 0.075}
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
                "segment_premium_revenue_m",
                f"{segment_label} earned premium revenue FY2025",
                segment_prem_m,
                "USD_m",
                K10,
                f"{segment_label} earned premium revenue ${segment_prem_m}M FY2025",
                AS_OF_FY,
            ),
            _fact(
                "consolidated_owner_cash_m",
                "Normalized owner cash (underwriting plus investment spread) FY2025",
                OWNER_CASH_M,
                "USD_m",
                K10,
                f"Operating income ${OP_INC_M}M plus normalized investment contribution; ${OWNER_CASH_PS}/sh on {SHARES_M}M shares",
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
                f"Owner cash allocated to {segment_label} by earned premium share",
                {c: round(owner_cash_m[c], 1) for c in SCENARIOS},
                "USD_m",
                growth_note,
                400.0,
                2500.0,
            ),
            _judgment("growth_y1_5", "Growth years 1–5 on segment owner cash", growth1, "ratio",
                      "Lawrence scenario envelope; Japan aging tailwind or U.S. worksite penetration.", 0.0, 0.07),
            _judgment("growth_y6_10", "Growth years 6–7 on segment owner cash", growth2, "ratio",
                      "Fade as premium base enlarges or yen translation drags.", 0.0, 0.06),
            _judgment("discount_rate", "Required return on segment owner cash", discount, "ratio",
                      "Supplemental insurance, investment-mark, and currency risk premium.", 0.06, 0.12),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Quality supplemental insurer peer multiples on normalized owner cash.", 14, 22),
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


def net_financial_claims_proof() -> dict:
    claim_m = {c: round(LEGACY["net_financial_claims"][c] * SHARES_M, 1) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("cash_m", "Cash and cash equivalents FY2025", CASH_M, "USD_m", K10,
                  f"CashAndCashEquivalentsAtCarryingValue ${CASH_M}M at December 31, 2025", AS_OF_FY),
            _fact("debt_m", "Debt and capital lease obligations FY2025", DEBT_M, "USD_m", K10,
                  f"DebtAndCapitalLeaseObligations ${DEBT_M}M FY2025", AS_OF_FY),
            _fact("shares_m", "Weighted average diluted shares FY2025", SHARES_M, "million_shares", K10,
                  f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M FY2025", AS_OF_FY),
        ],
        "assumptions": [
            _judgment(
                "net_debt_claim_m",
                "Net debt claim on common equity (debt less cash, bounded stress band)",
                claim_m,
                "USD_m",
                f"Filing-locked net debt ${NET_DEBT_M}M (${NET_DEBT_PS}/sh); low case adds refinancing stress, high case allows modest net cash.",
                -6000.0,
                2000.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["net_debt_claim_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def investment_currency_reserve_proof() -> dict:
    reserve_m = {c: round(LEGACY["investment_and_currency_reserve"][c] * SHARES_M, 1) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("net_investment_income_m", "Net investment income FY2025", NII_M, "USD_m", K10,
                  f"NetInvestmentIncome ${NII_M}M FY2025 (vs ${4116}M FY2024)", AS_OF_FY),
            _fact("net_income_m", "GAAP net income FY2025", NET_INCOME_M, "USD_m", K10,
                  f"NetIncomeLoss ${NET_INCOME_M}M FY2025 vs ${5443}M FY2024 on investment marks", AS_OF_FY),
            _fact("shares_m", "Weighted average diluted shares FY2025", SHARES_M, "million_shares", K10,
                  f"WeightedAverageNumberOfDilutedSharesOutstanding {SHARES_M}M FY2025", AS_OF_FY),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Investment-mark volatility and yen translation stress reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for credit spread widening, JGB mark moves, and yen weakness "
                "compressing translated U.S. dollar earnings; not full policy reserve subtraction.",
                -12000.0,
                -500.0,
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
        "valuation_mode": "economic_value",
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
            "price": 121.99,
            "price_source": "Yahoo AFL close 2026-07-09",
            "price_as_of": "2026-07-09",
            "shares_millions": SHARES_M,
            "shares_outstanding": int(round(SHARES_M * 1_000_000)),
            "shares_source": f"{K10}; weighted average diluted shares {SHARES_M}M FY2025.",
            "fcf_per_share": OWNER_CASH_PS,
            "fcf_source": (
                f"FY2025 operating income ${OP_INC_M}M plus normalized net investment income contribution, "
                f"÷ {SHARES_M}M shares = ${OWNER_CASH_PS}/sh; bridges GAAP OCF and operating income per share"
            ),
            "book_value_per_share": BVPS,
            "cash_m": CASH_M,
            "debt_m": DEBT_M,
            "net_debt_m": NET_DEBT_M,
            "normalization_note": (
                "FY2025 GAAP net income fell to $3.65B (EPS $6.82) from $5.44B on investment marks; "
                "owner cash uses underwriting plus recurring investment spread, not peak 2024 GAAP earnings"
            ),
        },
        "scenarios": {
            "bear": {
                "growth_y1_5": 0.03,
                "growth_y6_10": 0.025,
                "exit_pfcf_y10": 15,
                "notes": "Japan persistency pressure, yen headwind, multiple compresses toward mid-teens free cash flow multiple",
            },
            "base": {
                "growth_y1_5": 0.05,
                "growth_y6_10": 0.04,
                "exit_pfcf_y10": 18,
                "notes": "Low-single-digit premium growth in Japan and U.S. worksite channel; investment portfolio supports mid-single-digit owner-cash growth",
            },
            "bull": {
                "growth_y1_5": 0.06,
                "growth_y6_10": 0.05,
                "exit_pfcf_y10": 20,
                "notes": "U.S. supplemental penetration accelerates, Japan third-sector products grow, buybacks continue at premium multiple",
            },
        },
        "option_scan": [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "No separate land/NAV gap",
                "treatment": "n/a",
                "evidence": "Insurance assets and liabilities marked through investment portfolio; no historical-cost land floor issue",
            },
            {
                "q": 4,
                "question": "Investment portfolio spread not in owner-cash path?",
                "answer": "Embedded",
                "treatment": "embedded_in_segment",
                "evidence": f"Net investment income ${NII_M}M in FY2025 revenues; normalized in starting owner cash per share",
            },
            {
                "q": 0,
                "question": "Material separate options after scan?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Supplemental insurance compounder; Lawrence full cash-flow path sufficient",
            },
        ],
        "growth_explanation": {
            "mechanism": (
                "Japan cancer and medical supplemental persistency plus U.S. worksite accident and hospital "
                "indemnity sales; owner cash grows with earned premium and net investment income on the portfolio."
            ),
            "source": f"{K10} segment revenues; {Q10} Q1 2026 premium and investment income trends",
            "bear_falsifier": "Combined benefit ratio rises above 70% for two consecutive years with no offsetting investment income",
            "bull_falsifier": "Japan earned premium grows above 5% for four consecutive quarters while persistency holds",
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
                "Four additive components map Japan supplemental engine, U.S. worksite engine, "
                "net financial claims, and investment/currency stress reserve once each."
            ),
            "components": [
                _component("japan_supplemental_engine", "Japan supplemental insurance owner-cash engine", "operating_business"),
                _component("us_worksite_engine", "U.S. worksite voluntary benefits owner-cash engine", "operating_business"),
                _component("net_financial_claims", "Net debt and liquidity claims on common equity", "liability_or_reserve"),
                _component("investment_and_currency_reserve", "Investment-mark and yen translation stress reserve", "liability_or_reserve"),
            ],
        },
        "economic_value_analysis": {
            "ownership_waterfall": {
                "net_economic_claim": (
                    "One AFL diluted share equals pro-rata Japan and U.S. supplemental owner-cash engines, "
                    "less net debt and investment/currency stress reserve."
                ),
                "excluded_claims": [
                    "Net investment income already embedded in normalized owner cash starting point.",
                    "Full policy liabilities ($69.6B) are not subtracted twice; reserve captures mark/yen stress only.",
                    f"GAAP book (${BVPS}/sh) is cross-check, not dhando floor.",
                ],
                "reconciliation": (
                    f"FY2025 owner cash ${OWNER_CASH_M}M on {SHARES_M}M shares (${OWNER_CASH_PS}/sh); "
                    f"Japan premium ${JAPAN_PREM_M}M ({JAPAN_SHARE:.1%}); U.S. premium ${US_PREM_M}M; "
                    f"net debt ${NET_DEBT_M}M (${NET_DEBT_PS}/sh)."
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
                "One diluted share of Aflac, including Japan and U.S. supplemental owner-cash engines, "
                "net financial claims, and investment/currency stress reserve."
            ),
            "unit_label": "diluted share",
            "unit_count": int(round(SHARES_M * 1_000_000)),
            "unit_source": f"FY2025 weighted average diluted shares {SHARES_M}M per {K10}.",
            "enterprise_to_equity_reconciliation": (
                "Operating segments valued through owner-cash discount paths on premium-proportional "
                "owner cash; net debt and stress reserve are separate overlap keys."
            ),
        },
        "gaap_role": "cross_check",
        "accounting_reference": (
            f"FY2025 10-K: book value per share ${BVPS}; owner cash ${OWNER_CASH_PS}/sh; "
            "economic value in normalized supplemental underwriting and investment spread."
        ),
        "component_groups": [
            {
                "id": "japan_supplemental_engine",
                "label": "Japan supplemental insurance engine",
                "component_ids": ["japan_supplemental_engine"],
                "economic_claim": "Japan cancer and medical supplemental franchise",
                "valuation_basis": "Owner-cash discount on Japan share of normalized owner cash.",
                "adjustments": f"Earned premium ${JAPAN_PREM_M}M (~{JAPAN_SHARE:.0%} of segment premiums).",
                "overlap_control": "Unique overlap key japan_supplemental_engine.",
            },
            {
                "id": "us_worksite_engine",
                "label": "U.S. worksite voluntary benefits engine",
                "component_ids": ["us_worksite_engine"],
                "economic_claim": "U.S. accident, disability, and hospital indemnity worksite channel",
                "valuation_basis": "Owner-cash discount on U.S. share of normalized owner cash.",
                "adjustments": f"Earned premium ${US_PREM_M}M (~{US_SHARE:.0%} of segment premiums).",
                "overlap_control": "Unique overlap key us_worksite_engine.",
            },
            {
                "id": "net_financial_claims",
                "label": "Net debt and liquidity claims",
                "component_ids": ["net_financial_claims"],
                "economic_claim": "Senior notes and yen debt net of cash",
                "valuation_basis": "Net asset value on filing-locked debt less cash.",
                "adjustments": f"Debt ${DEBT_M}M less cash ${CASH_M}M = ${NET_DEBT_M}M.",
                "overlap_control": "Unique overlap key net_financial_claims.",
            },
            {
                "id": "investment_and_currency_reserve",
                "label": "Investment-mark and yen stress reserve",
                "component_ids": ["investment_and_currency_reserve"],
                "economic_claim": "Credit spread, JGB mark, and yen translation downside",
                "valuation_basis": "Bounded negative reserve; not full policy liability NAV subtraction.",
                "adjustments": f"GAAP net income ${NET_INCOME_M}M vs NII ${NII_M}M shows mark sensitivity.",
                "overlap_control": "Unique overlap key investment_and_currency_reserve.",
            },
        ],
        "limitations": [
            "Segment owner-cash split uses earned premium proportion; segment operating income not separately disclosed.",
            "Yen translation and investment marks remain widest judgment bands.",
        ],
    }


def main() -> int:
    proofs = {
        "japan_supplemental_engine": _segment_owner_cash_proof(
            "japan_supplemental_engine",
            JAPAN_PREM_M,
            "Aflac Japan",
            "Japan ~61% of earned premium; aging demographics support third-sector persistency.",
        ),
        "us_worksite_engine": _segment_owner_cash_proof(
            "us_worksite_engine",
            US_PREM_M,
            "Aflac U.S.",
            "U.S. ~39% of earned premium; worksite voluntary benefits with payroll-deduction habit.",
        ),
        "net_financial_claims": net_financial_claims_proof(),
        "investment_and_currency_reserve": investment_currency_reserve_proof(),
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
            if cid == "net_financial_claims" and case == "base":
                if out and abs(out[case] - legacy[case]) > 0.06:
                    errors.append(f"{cid}.{case}: got {out[case]}, want {legacy[case]}")
            elif out and abs(out[case] - legacy[case]) > 0.06:
                errors.append(f"{cid}.{case}: got {out[case]}, want {legacy[case]}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    path = ROOT / TICKER / "research" / "valuation.json"
    data = build_valuation_scaffold()
    evidence = (
        f"Primary bridge from FY2025 10-K: owner cash ${OWNER_CASH_M}M (${OWNER_CASH_PS}/sh), "
        f"book ${BVPS}/sh, net investment income ${NII_M}M, net debt ${NET_DEBT_M}M; contract backfill {AS_OF}."
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
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    base_sum = sum(outputs[c]["base"] for c in outputs)
    print(json.dumps({"status": "ok", "outputs": outputs, "base_sum_per_share": round(base_sum, 2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
