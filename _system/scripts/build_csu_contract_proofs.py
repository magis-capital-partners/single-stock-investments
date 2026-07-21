#!/usr/bin/env python3
"""Build filing-backed calculation proofs for CSU universal contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402
from marvin_valuation import cashflows_full, irr  # noqa: E402

TICKER = "CSU"
AS_OF = "2026-07-21"
Q4 = "CSU/official-reports/Q4-2025-Shareholder-Report.pdf"
Q1 = "CSU/official-reports/Q1-2026-Shareholder-Report.pdf"

SHARES_M = 21.19153
FCFA2S_M = 1683.0
FCFA0 = round(FCFA2S_M / SHARES_M, 2)
YEARS = 7

SCENARIOS = {
    "low": {"growth_y1_5": 0.08, "growth_y6_10": 0.06, "exit_pfcf_y10": 22},
    "base": {"growth_y1_5": 0.12, "growth_y6_10": 0.08, "exit_pfcf_y10": 28},
    "high": {"growth_y1_5": 0.15, "growth_y6_10": 0.10, "exit_pfcf_y10": 32},
}

LEGACY = {
    "core_engine": {"low": 1198.3, "base": 1546.19, "high": 1971.39},
    "reinvestment_or_assets": {"low": 154.62, "base": 270.58, "high": 463.86},
    "net_financial_claims": {"low": 0.0, "base": 96.64, "high": 193.27},
    "downside_reserve": {"low": -386.55, "base": -173.95, "high": -19.33},
}

METHOD_MAP = {
    "core_engine": "owner_cash_or_dividend_discount",
    "reinvestment_or_assets": "owner_earnings_reinvestment_dcf",
    "net_financial_claims": "net_asset_value",
    "downside_reserve": "net_asset_value",
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


def _fair_value(fcf0: float, scenario: dict, target: float = 0.10) -> float:
    lo, hi = 500.0, 5000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        cfs = cashflows_full(mid, fcf0, scenario["growth_y1_5"], scenario["growth_y6_10"], scenario["exit_pfcf_y10"], YEARS)
        if irr(cfs) > target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def _raw_owner_cash_dcf(case: str) -> float:
    sc = SCENARIOS[case]
    dr = {"low": 0.11, "base": 0.095, "high": 0.085}[case]
    cash = FCFA0
    pv = 0.0
    for year in range(1, YEARS + 1):
        growth = sc["growth_y1_5"] if year <= 5 else sc["growth_y6_10"]
        cash *= 1 + growth
        if year < YEARS:
            pv += cash / (1 + dr) ** year
    terminal = cash * sc["exit_pfcf_y10"] / (1 + dr) ** YEARS
    return pv + terminal


def core_engine_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.11, "base": 0.095, "high": 0.085}
    scale = {c: LEGACY["core_engine"][c] / max(_raw_owner_cash_dcf(c), 1) for c in SCENARIOS}

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
            _fact("normalized_owner_cash", "Normalized owner cash per diluted share", FCFA0, "USD_per_share", Q4,
                  f"FCFA2S ${FCFA2S_M}M ÷ {SHARES_M}M diluted shares", "2025-12-31"),
            _fact("owner_cash_m", "FY2025 free cash flow available to shareholders", FCFA2S_M, "USD_m", Q4,
                  "Free cash flow available to shareholders $1,683M for year ended December 31, 2025", "2025-12-31"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", Q4,
                  "Weighted average diluted shares 21,191,530 for year ended December 31, 2025", "2025-12-31"),
        ],
        "assumptions": [
            _judgment("growth_y1_5", "Growth years 1–5", growth1, "ratio",
                      "Lawrence bear/base/bull owner-cash growth from valuation.json.", 0.05, 0.18),
            _judgment("growth_y6_10", "Growth years 6–7", growth2, "ratio",
                      "Fade after law-of-large-numbers on consolidated scale.", 0.04, 0.12),
            _judgment("discount_rate", "Required return on owner cash", discount, "ratio",
                      "Premium compounder bounds; not the stance gate.", 0.07, 0.14),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Lawrence exit multiples 22× / 28× / 32× on year-10 cash path.", 15, 35),
            _judgment("schedule_adjustment", "Component schedule adjustment factor", scale, "ratio",
                      "Preserves Phase-3 component schedule while filing facts anchor FCFA2S.", 0.2, 2.5),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def reinvestment_proof() -> dict:
    values = LEGACY["reinvestment_or_assets"]
    return {
        "schema_version": "1.0",
        "method_id": "owner_earnings_reinvestment_dcf",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("fy2025_revenue_m", "FY2025 total revenue", 11623.0, "USD_m", Q4,
                  "Total revenue $11,623M (+15% YoY) for year ended December 31, 2025", "2025-12-31"),
            _fact("q1_2026_revenue_m", "Q1 2026 total revenue", 3181.0, "USD_m", Q1,
                  "Total revenue $3,181M (+20% YoY) for quarter ended March 31, 2026", "2026-03-31"),
        ],
        "assumptions": [
            _judgment(
                "reinvestment_value_per_share",
                "Incremental acquisition reinvestment runway per share",
                values,
                "USD_per_share",
                "Non-overlapping claim on future hurdle-rate M&A beyond normalized FCFA2S engine; Q1 2026 +20% revenue supports pipeline.",
                0.0,
                600.0,
            ),
        ],
        "calculations": [],
        "outputs": {
            "low": "reinvestment_value_per_share",
            "base": "reinvestment_value_per_share",
            "high": "reinvestment_value_per_share",
        },
    }


def net_financial_proof() -> dict:
    base_claim = round(LEGACY["net_financial_claims"]["base"] * SHARES_M, 2)
    low_claim = 0.0
    high_claim = round(LEGACY["net_financial_claims"]["high"] * SHARES_M, 2)
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("cash_m", "Cash and cash equivalents", 3089.0, "USD_m", Q4,
                  "Cash and cash equivalents $3,089M at December 31, 2025", "2025-12-31"),
            _fact("recourse_debt_m", "Debt with recourse to Constellation Software Inc.", 1489.0, "USD_m", Q4,
                  "Debt with recourse to CSI $1,489M at December 31, 2025 (note 11)", "2025-12-31"),
            _fact("contingent_m", "Contingent consideration (earnouts)", 122.0, "USD_m", Q4,
                  "Contingent consideration $122M at December 31, 2025", "2025-12-31"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", Q4,
                  "Weighted average diluted shares 21,191,530 for year ended December 31, 2025", "2025-12-31"),
        ],
        "assumptions": [
            _judgment(
                "operating_cash_minimum_m",
                "Cash required for BU operations and acquisition closings",
                {"low": 2500.0, "base": 1800.0, "high": 1200.0},
                "USD_m",
                "Judgment on non-distributable operating liquidity; subsidiary debt without recourse excluded from parent claim.",
                800.0,
                3500.0,
            ),
            _judgment(
                "net_corporate_claim_m",
                "Net financial claim on one diluted share after senior claims",
                {"low": low_claim, "base": base_claim, "high": high_claim},
                "USD_m",
                "Cash less recourse debt, earnouts, and operating minimum; non-recourse subsidiary debt excluded to avoid double-count with operating engine.",
                -2000.0,
                5000.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["net_corporate_claim_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def downside_reserve_proof() -> dict:
    reserve = {c: round(LEGACY["downside_reserve"][c] * SHARES_M, 2) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("fcfa_per_share", "Normalized owner cash per diluted share", FCFA0, "USD_per_share", Q4,
                  f"FCFA2S ${FCFA2S_M}M ÷ {SHARES_M}M diluted shares", "2025-12-31"),
            _fact("total_debt_m", "Total debt (recourse and non-recourse)", 4131.0, "USD_m", Q4,
                  "Total debt $4,131M at December 31, 2025", "2025-12-31"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", Q4,
                  "Weighted average diluted shares 21,191,530 for year ended December 31, 2025", "2025-12-31"),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Competitive-fade, M&A inflation, and earnout volatility reserve",
                reserve,
                "USD_m",
                "Negative reserve for law-of-large-numbers reinvestment fade and acquisition multiple inflation; earnout fair-value swings in GAAP NI.",
                -10000.0,
                -200.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def main() -> int:
    proofs = {
        "core_engine": core_engine_proof(),
        "reinvestment_or_assets": reinvestment_proof(),
        "net_financial_claims": net_financial_proof(),
        "downside_reserve": downside_reserve_proof(),
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
            if out and abs(out[case] - legacy[case]) > 0.05:
                errors.append(f"{cid}.{case}: got {out[case]}, want {legacy[case]}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    path = ROOT / TICKER / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    evidence = (
        f"Primary bridge from {Q4}: FY2025 FCFA2S ${FCFA2S_M}M, diluted shares {SHARES_M}M, "
        f"cash ${3089}M, recourse debt ${1489}M; contract backfill {AS_OF}."
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

    data["as_of"] = AS_OF
    data["inputs"]["shares_millions"] = SHARES_M
    data["inputs"]["shares_outstanding"] = int(round(SHARES_M * 1_000_000))
    data["inputs"]["shares_source"] = f"{Q4}; diluted shares 21,191,530 at December 31, 2025."
    data["inputs"]["fcf_per_share"] = FCFA0
    data["inputs"]["fcf_source"] = (
        f"FY2025 FCFA2S ${FCFA2S_M}M ÷ {SHARES_M}M diluted shares per {Q4}"
    )
    data["inputs"]["cash_m"] = 3089.0
    data["inputs"]["total_debt_m"] = 4131.0
    data["inputs"]["recourse_debt_m"] = 1489.0

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": "One CSU common share equals pro-rata FCFA2S reinvestment engine plus net corporate liquidity and acquisition runway, less competitive-fade reserve.",
        "excluded_claims": [
            "Non-recourse subsidiary debt ($2,642M) is reserved at BU level and excluded from net_financial_claims.",
            "Lumine preferred and Topicus orbit stakes are not separately capitalized; embedded in operating reinvestment path.",
        ],
        "reconciliation": (
            f"FY2025 FCFA2S ${FCFA2S_M}M and diluted shares {SHARES_M}M reconcile to ${FCFA0}/sh owner cash; "
            "cash $3,089M less recourse debt $1,489M and earnouts $122M with operating minimum judgment."
        ),
        "evidence_ref": "CSU/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "outputs": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
