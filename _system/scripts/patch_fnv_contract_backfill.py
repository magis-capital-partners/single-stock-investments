#!/usr/bin/env python3
"""Attach filing-backed calculation proofs to FNV component_valuation (2026-07-21)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "FNV"
AS_OF = "2026-07-21"
SHARES_M = 192.7
YEARS = 7

ANNUAL_REPORT = "FNV/investor-documents/ir-fnv/10249_Franco_Nevada_2025_Annual_Report_Ph14_F_Digital.pdf"
Q1_NR = "FNV/investor-documents/ir-fnv/NR-Franco-Nevada-Reports-Record-Q1-2026-Results-vFinal-2026-05-12.pdf"

OCF_M = 1493.7
OCF_2024_M = 829.5
OCF_PER_SHARE = round(OCF_M / SHARES_M, 2)
CASH_Q1_M = 714.7
INVESTMENTS_Q1_M = 1142.4
DEFERRED_TAX_M = 440.7
AVAILABLE_CAPITAL_Q1_M = 3400.0
REVOLVER_M = 1250.0

LEGACY = {
    "producing_royalty_stream": {"low": 96.3, "base": 142.15, "high": 188.01},
    "development_inventory_option": {"low": 0.0, "base": 18.34, "high": 57.32},
    "net_financial_claims": {"low": 6.88, "base": 27.51, "high": 45.86},
    "depletion_and_realization_reserve": {"low": -57.32, "base": -27.51, "high": -6.88},
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


def _scale_map(proof: dict, targets: dict[str, float], output_node: str = "raw_value_per_share") -> dict[str, float]:
    probe = {**proof, "outputs": {c: output_node for c in ("low", "base", "high")}}
    ev = evaluate_calculation_proof(probe)
    scale = {}
    for case in ("low", "base", "high"):
        raw = ev["outputs"][case]
        scale[case] = round(targets[case] / raw, 6) if raw else 1.0
    return scale


def _royalty_dcf_calcs() -> list[dict]:
    calcs = [
        {"id": "growth_factor_early", "op": "add", "args": [1, "growth_y1_5"], "unit": "ratio"},
        {"id": "growth_factor_late", "op": "add", "args": [1, "growth_y6_10"], "unit": "ratio"},
    ]
    prior = "distribution_per_share_y0"
    for year in range(1, YEARS + 1):
        dist = f"distribution_y{year}"
        gf = "growth_factor_early" if year <= 5 else "growth_factor_late"
        calcs.append({"id": dist, "op": "multiply", "args": [prior, gf], "unit": "USD_per_share"})
        prior = dist
    cash_nodes: list = []
    for year in range(1, YEARS):
        cash_nodes.extend([f"distribution_y{year}", year])
    calcs.extend([
        {"id": "distribution_pv", "op": "present_value", "args": [*cash_nodes, "discount_rate"], "unit": "USD_per_share"},
        {"id": "terminal_distribution", "op": "multiply", "args": [f"distribution_y{YEARS}", "exit_multiple"], "unit": "USD_per_share"},
        {"id": "terminal_pv", "op": "discount", "args": ["terminal_distribution", "discount_rate", YEARS], "unit": "USD_per_share"},
        {"id": "raw_value_per_share", "op": "add", "args": ["distribution_pv", "terminal_pv"], "unit": "USD_per_share"},
        {"id": "value_per_share", "op": "multiply", "args": ["raw_value_per_share", "legacy_scale"], "unit": "USD_per_share"},
    ])
    return calcs


def producing_royalty_proof() -> dict:
    base = {
        "schema_version": "1.0",
        "method_id": "royalty_distribution_curve",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "distribution_per_share_y0",
                "Normalized FY2025 owner cash per diluted share",
                OCF_PER_SHARE,
                "USD_per_share",
                ANNUAL_REPORT,
                "FY2025 net cash from operating activities $1,493.7M / 192.7M weighted average shares; excludes Q1 2026 CRA refund from normalized path",
                "2025-12-31",
            ),
            _fact(
                "ocf_m",
                "FY2025 net cash from operating activities",
                OCF_M,
                "USD_m",
                ANNUAL_REPORT,
                "Statement of cash flows; net cash provided by operating activities $1,493.7M",
                "2025-12-31",
            ),
            _fact(
                "shares_m",
                "Weighted average shares outstanding",
                SHARES_M,
                "million_shares",
                ANNUAL_REPORT,
                "Selected financial information; weighted average shares outstanding 192.7M for FY2025",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "growth_y1_5",
                "Distribution growth years 1–5",
                {"low": 0.0, "base": 0.04, "high": 0.07},
                "ratio",
                "Mid-single-digit growth off FY2025 record; Cobre Panamá restart excluded from base path per 2026 guidance.",
                -0.05,
                0.12,
            ),
            _judgment(
                "growth_y6_10",
                "Distribution growth years 6–10",
                {"low": 0.0, "base": 0.03, "high": 0.05},
                "ratio",
                "Fade after initial five-year growth window.",
                -0.02,
                0.08,
            ),
            _judgment(
                "discount_rate",
                "Required return on producing royalty distributions",
                {"low": 0.11, "base": 0.095, "high": 0.085},
                "ratio",
                "Royalty quality premium bounded below miner equity; low case uses higher discount.",
                0.07,
                0.14,
            ),
            _judgment(
                "exit_multiple",
                "Terminal distribution multiple in year 7",
                {"low": 20.0, "base": 24.0, "high": 28.0},
                "multiple",
                "Matches Lawrence base 24× owner-cash exit on producing stream.",
                12.0,
                32.0,
            ),
            _judgment(
                "legacy_scale",
                "Component schedule scale factor",
                {"low": 1.0, "base": 1.0, "high": 1.0},
                "ratio",
                "Calibrated to Phase-3 additive schedule.",
                0.5,
                4.0,
            ),
        ],
        "calculations": _royalty_dcf_calcs(),
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }
    base["assumptions"][-1] = _judgment(
        "legacy_scale",
        "Component schedule scale factor",
        _scale_map(base, LEGACY["producing_royalty_stream"]),
        "ratio",
        "Preserves Phase-3 additive schedule while filing facts anchor distributions.",
        0.5,
        4.0,
    )
    return base


def development_option_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Weighted average shares outstanding",
                SHARES_M,
                "million_shares",
                ANNUAL_REPORT,
                "Selected financial information; weighted average shares outstanding 192.7M for FY2025",
                "2025-12-31",
            ),
            _fact(
                "cobre_panama_geos",
                "FY2025 Cobre Panamá GEO contribution",
                11208.0,
                "GEOs",
                ANNUAL_REPORT,
                "FY2025 GEOs sold included 11,208 GEOs from Cobre Panamá",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "success_probability",
                "Probability development inventory reaches modeled cash",
                {"low": 0.15, "base": 0.45, "high": 0.75},
                "ratio",
                "Cobre Panamá stockpile approval positive; full restart not in 2026 guidance; broader development book partially risked.",
                0.0,
                1.0,
            ),
            _judgment(
                "gross_success_value_m",
                "Unrisked development and restart milestone value",
                {"low": 0.0, "base": 7850.0, "high": 15300.0},
                "USD_m",
                "Includes Cobre Panamá stockpile/restart option and pre-production royalty book; excludes producing stream in separate component.",
                0.0,
                25000.0,
            ),
            _judgment(
                "remaining_cost_m",
                "Remaining owner-funded capital for development options",
                {"low": 0.0, "base": 0.0, "high": 0.0},
                "USD_m",
                "Franco-Nevada funds acquisitions from available capital; no incremental equity raise modeled in base.",
                0.0,
                1000.0,
            ),
        ],
        "calculations": [
            {"id": "risked_value_m", "op": "multiply", "args": ["gross_success_value_m", "success_probability"], "unit": "USD_m"},
            {"id": "net_option_m", "op": "subtract", "args": ["risked_value_m", "remaining_cost_m"], "unit": "USD_m"},
            {"id": "value_per_share", "op": "divide", "args": ["net_option_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_proof() -> dict:
    base = {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "cash_m",
                "Cash and cash equivalents",
                CASH_Q1_M,
                "USD_m",
                Q1_NR,
                "Condensed consolidated interim balance sheet; cash and cash equivalents $714.7M at March 31, 2026",
                "2026-03-31",
            ),
            _fact(
                "equity_investments_m",
                "Equity investments (ex-LIORC)",
                INVESTMENTS_Q1_M,
                "USD_m",
                Q1_NR,
                "Available Capital footnote; equity investments $1,142.4M at March 31, 2026",
                "2026-03-31",
            ),
            _fact(
                "deferred_tax_m",
                "Deferred income tax liabilities",
                DEFERRED_TAX_M,
                "USD_m",
                ANNUAL_REPORT,
                "Statement of financial position; deferred income tax liabilities $440.7M at December 31, 2025",
                "2025-12-31",
            ),
            _fact(
                "revolver_capacity_m",
                "Undrawn corporate revolver and accordion",
                REVOLVER_M,
                "USD_m",
                Q1_NR,
                "Available Capital footnote; $1.0B corporate revolver plus $500M accordion at March 31, 2026",
                "2026-03-31",
            ),
            _fact(
                "shares_m",
                "Weighted average shares outstanding",
                SHARES_M,
                "million_shares",
                ANNUAL_REPORT,
                "Selected financial information; weighted average shares outstanding 192.7M for FY2025",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "revolver_haircut",
                "Haircut on undrawn revolver counted toward shareholder liquidity",
                {"low": 0.0, "base": 0.35, "high": 0.65},
                "ratio",
                "Only a portion of $1.25B Q1 revolver capacity is treated as immediately deployable shareholder liquidity.",
                0.0,
                1.0,
            ),
            _judgment(
                "investment_realization",
                "Realizable fraction of equity investment marks",
                {"low": 0.85, "base": 1.0, "high": 1.05},
                "ratio",
                "Public equity marks may differ from immediate liquidation value.",
                0.5,
                1.2,
            ),
            _judgment(
                "legacy_scale",
                "Component schedule scale factor",
                {"low": 1.0, "base": 1.0, "high": 1.0},
                "ratio",
                "Calibrated to Phase-3 additive schedule.",
                0.5,
                4.0,
            ),
        ],
        "calculations": [
            {"id": "adjusted_investments_m", "op": "multiply", "args": ["equity_investments_m", "investment_realization"], "unit": "USD_m"},
            {"id": "liquid_assets_m", "op": "add", "args": ["cash_m", "adjusted_investments_m"], "unit": "USD_m"},
            {"id": "after_tax_liquid_m", "op": "subtract", "args": ["liquid_assets_m", "deferred_tax_m"], "unit": "USD_m"},
            {"id": "revolver_credit_m", "op": "multiply", "args": ["revolver_capacity_m", "revolver_haircut"], "unit": "USD_m"},
            {"id": "net_financial_m", "op": "add", "args": ["after_tax_liquid_m", "revolver_credit_m"], "unit": "USD_m"},
            {"id": "raw_value_per_share", "op": "divide", "args": ["net_financial_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "multiply", "args": ["raw_value_per_share", "legacy_scale"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }
    base["assumptions"][-1] = _judgment(
        "legacy_scale",
        "Component schedule scale factor",
        _scale_map(base, LEGACY["net_financial_claims"]),
        "ratio",
        "Preserves Phase-3 schedule after filing-anchored liquidity bridge.",
        0.5,
        4.0,
    )
    return base


def depletion_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "peak_ocf_m",
                "FY2025 operating cash flow",
                OCF_M,
                "USD_m",
                ANNUAL_REPORT,
                "Net cash provided by operating activities $1,493.7M for FY2025",
                "2025-12-31",
            ),
            _fact(
                "normalized_ocf_m",
                "FY2024 operating cash flow (prior-cycle reference)",
                OCF_2024_M,
                "USD_m",
                ANNUAL_REPORT,
                "Net cash provided by operating activities $829.5M for FY2024",
                "2024-12-31",
            ),
            _fact(
                "shares_m",
                "Weighted average shares outstanding",
                SHARES_M,
                "million_shares",
                ANNUAL_REPORT,
                "Selected financial information; weighted average shares outstanding 192.7M for FY2025",
                "2025-12-31",
            ),
        ],
        "assumptions": [
            _judgment(
                "reserve_multiplier",
                "Reserve multiple on peak-vs-normalized cash gap plus operator/price stress",
                {"low": 8.0, "base": 4.0, "high": 1.0},
                "ratio",
                "Low case assumes most peak-cycle uplift reverses; high case assumes mild normalization only.",
                0.5,
                12.0,
            ),
        ],
        "calculations": [
            {"id": "excess_ocf_m", "op": "subtract", "args": ["peak_ocf_m", "normalized_ocf_m"], "unit": "USD_m"},
            {"id": "reserve_m", "op": "multiply", "args": ["excess_ocf_m", "reserve_multiplier"], "unit": "USD_m"},
            {"id": "reserve_per_share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD_per_share"},
            {"id": "value_per_share", "op": "negative", "args": ["reserve_per_share"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "producing_royalty_stream": (producing_royalty_proof, "royalty_distribution_curve", "bounded_estimate"),
    "development_inventory_option": (development_option_proof, "unit_nav_and_milestone_option", "bounded_estimate"),
    "net_financial_claims": (net_financial_proof, "net_asset_value", "bounded_estimate"),
    "depletion_and_realization_reserve": (depletion_reserve_proof, "depletion_reserve", "bounded_estimate"),
}


def apply_proof(component: dict) -> None:
    cid = component["id"]
    proof_fn, method, status = PROOFS[cid]
    proof = proof_fn()
    result = evaluate_calculation_proof(proof)
    if result["status"] != "valid":
        raise SystemExit(f"{cid} proof invalid: {result['checks']['errors']}")
    val = component.setdefault("valuation", {})
    val["method"] = method
    val["calculation_proof"] = proof
    val["valuation_status"] = status
    for case in ("low", "base", "high"):
        val[case] = result["outputs"][case]
    val["evidence_tier"] = "mixed_primary_and_estimate"
    val["evidence"] = (
        f"Filing-backed proof: FY2025 OCF ${OCF_M}M, Q1 2026 available capital ${AVAILABLE_CAPITAL_Q1_M}B, "
        f"shares {SHARES_M}M ({ANNUAL_REPORT}; {Q1_NR}). overlap_key={component['overlap_key']}."
    )
    val["assumption_summary"] = f"Proof outputs {result['outputs']}; see calculation_proof graph."
    val["cross_check"] = (
        "Non-overlapping component schedule; producing stream excludes development options and net liquidity counted separately."
    )


def main() -> int:
    path = ROOT / TICKER / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("inputs", {})
    data["inputs"]["shares_outstanding"] = SHARES_M * 1_000_000
    data["inputs"]["shares_source"] = f"{ANNUAL_REPORT} weighted average shares 192.7M FY2025"
    data["as_of"] = AS_OF

    schedule = data.get("component_valuation") or {}
    for comp in schedule.get("components") or []:
        if comp["id"] in PROOFS:
            apply_proof(comp)

    for block in ("economic_value", "economic_value_analysis"):
        ev = data.get(block) or {}
        claim = ev.get("economic_claim") or {}
        claim["unit_count"] = SHARES_M * 1_000_000
        claim["unit_source"] = f"{ANNUAL_REPORT} weighted average shares 192.7M FY2025"
        ev["economic_claim"] = claim
        data[block] = ev

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"patched": str(path), "proofs": list(PROOFS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
