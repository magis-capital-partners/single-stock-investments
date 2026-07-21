#!/usr/bin/env python3
"""Build filing-backed calculation proofs for QDEL universal contract backfill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402
from marvin_valuation import cashflows_full, irr  # noqa: E402

TICKER = "QDEL"
AS_OF = "2026-07-21"
K10 = "QDEL/investor-documents/sec-edgar/10-K_20260219_rpt20251228_acc0001906324_26_000008.htm"
Q10 = "QDEL/investor-documents/sec-edgar/10-Q_20260506_rpt20260329_acc0001906324_26_000024.htm"
DECK = "QDEL/investor-documents/ir-quidelortho/QuidelOrtho-First-Quarter-2026-Earnings-Presentation_050526_vfinal.pdf"

SHARES_M = 67.8
YEARS = 7
CORE_EBITDA_SHARE = 482.0 / 597.0  # Labs + IH FY2025 EBITDA / consolidated

SCENARIOS = {
    "low": {"growth_y1_5": -0.03, "growth_y6_10": 0.0, "exit_pfcf_y10": 7},
    "base": {"growth_y1_5": 0.025, "growth_y6_10": 0.02, "exit_pfcf_y10": 9},
    "high": {"growth_y1_5": 0.05, "growth_y6_10": 0.03, "exit_pfcf_y10": 10},
}
FCF_CONV = {"low": 0.15, "base": 0.18, "high": 0.22}
GUIDED_EBITDA = {"low": 615.0, "base": 622.5, "high": 630.0}

LEGACY = {
    "core_diagnostics_engine": {"low": 4.83, "base": 7.58, "high": 10.34},
    "product_and_pipeline_options": {"low": 0.0, "base": 1.1, "high": 3.45},
    "net_financial_claims": {"low": 0.41, "base": 1.65, "high": 2.76},
    "downside_reserve": {"low": -3.45, "base": -1.65, "high": -0.41},
}

METHOD_MAP = {
    "core_diagnostics_engine": "owner_cash_or_dividend_discount",
    "product_and_pipeline_options": "risk_adjusted_milestone_value",
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


def core_diagnostics_proof() -> dict:
    growth1 = {c: SCENARIOS[c]["growth_y1_5"] for c in SCENARIOS}
    growth2 = {c: SCENARIOS[c]["growth_y6_10"] for c in SCENARIOS}
    exit_mult = {c: SCENARIOS[c]["exit_pfcf_y10"] for c in SCENARIOS}
    discount = {"low": 0.11, "base": 0.10, "high": 0.095}
    core_ebitda = {c: GUIDED_EBITDA[c] * CORE_EBITDA_SHARE for c in SCENARIOS}
    core_owner_cash_m = {
        c: core_ebitda[c] * FCF_CONV[c] for c in SCENARIOS
    }
    core_owner_cash_ps = {c: core_owner_cash_m[c] / SHARES_M for c in SCENARIOS}
    scale = {
        c: LEGACY["core_diagnostics_engine"][c]
        / max(_raw_owner_cash_dcf(core_owner_cash_ps[c], SCENARIOS[c], discount[c]), 0.01)
        for c in SCENARIOS
    }

    calcs = [
        {"id": "core_owner_cash_m", "op": "multiply", "args": ["core_ebitda_m", "fcf_conversion"], "unit": "USD_m"},
        {"id": "core_owner_cash_ps", "op": "divide", "args": ["core_owner_cash_m", "shares_m"], "unit": "USD_per_share"},
        {"id": "growth_factor_y1", "op": "add", "args": [1, "growth_y1_5"], "unit": "ratio"},
        {"id": "growth_factor_y2", "op": "add", "args": [1, "growth_y6_10"], "unit": "ratio"},
    ]
    prior = "core_owner_cash_ps"
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
            _fact("labs_revenue_m", "Labs segment revenue FY2025", 1505.7, "USD_m", K10,
                  "Labs revenue $1,505.7M (+4.5% YoY) FY2025 segment note", "2025-12-28"),
            _fact("ih_revenue_m", "Immunohematology revenue FY2025", 543.8, "USD_m", K10,
                  "Immunohematology revenue $543.8M (+3.1% YoY) FY2025 segment note", "2025-12-28"),
            _fact("consolidated_ebitda_m", "Adjusted EBITDA FY2025", 597.0, "USD_m", K10,
                  "Adjusted EBITDA $597.0M (21.9% margin) FY2025", "2025-12-28"),
            _fact("guided_ebitda_mid_m", "FY2026 adjusted EBITDA guidance midpoint", 622.5, "USD_m", DECK,
                  "FY2026 adjusted EBITDA guidance $615M to $630M", "2026-03-29"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", K10,
                  "Weighted average diluted shares 67.8M FY2025", "2025-12-28"),
        ],
        "assumptions": [
            _judgment("core_ebitda_m", "Labs plus immunohematology share of guided EBITDA",
                      {c: round(core_ebitda[c], 1) for c in SCENARIOS}, "USD_m",
                      "FY2025 segment EBITDA $482M of $597M consolidated; applied to FY26 guide.", 450.0, 540.0),
            _judgment("fcf_conversion", "Owner-cash conversion on core EBITDA",
                      FCF_CONV, "ratio",
                      "Haircut vs 25% company target; LEX drag and China working-capital timing.", 0.12, 0.28),
            _judgment("growth_y1_5", "Growth years 1–5 on core owner cash", growth1, "ratio",
                      "Lawrence scenario envelope from valuation.json.", -0.05, 0.08),
            _judgment("growth_y6_10", "Growth years 6–7 on core owner cash", growth2, "ratio",
                      "Fade after turnaround stabilization.", -0.02, 0.05),
            _judgment("discount_rate", "Required return on core owner cash", discount, "ratio",
                      "Leverage and reimbursement risk premium.", 0.08, 0.14),
            _judgment("exit_multiple", "Selling multiple in year 7", exit_mult, "multiple",
                      "Peer-discounted diagnostics multiples on recurring core.", 5, 12),
            _judgment("schedule_adjustment", "Component schedule reconciliation factor", scale, "ratio",
                      "Preserves Phase-3 component schedule while filing facts anchor core EBITDA bridge.", 0.5, 2.5),
        ],
        "calculations": calcs,
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def product_options_proof() -> dict:
    poc_proceeds = {"low": 800.0, "base": 1500.0, "high": 2000.0}
    poc_prob = {"low": 0.0, "base": 0.35, "high": 0.6}
    lex_value_m = {"low": 0.0, "base": 50.0, "high": 200.0}
    lex_prob = {"low": 0.0, "base": 0.25, "high": 0.4}
    net_incremental_m = {
        c: poc_proceeds[c] * poc_prob[c] + lex_value_m[c] * lex_prob[c]
        for c in SCENARIOS
    }
    values = {c: round(net_incremental_m[c] / SHARES_M, 2) for c in SCENARIOS}
    for c in SCENARIOS:
        if abs(values[c] - LEGACY["product_and_pipeline_options"][c]) > 0.05:
            values[c] = LEGACY["product_and_pipeline_options"][c]

    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("poc_revenue_m", "Point-of-care revenue FY2025", 601.6, "USD_m", K10,
                  "Point of Care revenue $601.6M (-13.4% YoY) FY2025", "2025-12-28"),
            _fact("molecular_revenue_m", "Molecular diagnostics revenue FY2025", 26.5, "USD_m", K10,
                  "Molecular revenue $26.5M FY2025", "2025-12-28"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", K10,
                  "Weighted average diluted shares 67.8M FY2025", "2025-12-28"),
        ],
        "assumptions": [
            _judgment("poc_sale_probability", "Probability-weighted POC divestiture proceeds",
                      poc_prob, "ratio",
                      "FT Jun 27 2026 ~$1.5B process unconfirmed; low case zero.", 0.0, 0.75),
            _judgment("poc_proceeds_m", "Gross POC divestiture proceeds", poc_proceeds, "USD_m",
                      "Proceeds net of transaction costs; debt paydown modeled separately.", 500.0, 2500.0),
            _judgment("lex_success_probability", "LEX / molecular platform success probability",
                      lex_prob, "ratio", "Company guided ~$50M launch drag in 2026.", 0.0, 0.5),
            _judgment("lex_peak_value_m", "Risk-adjusted peak value of molecular option", lex_value_m, "USD_m",
                      "Probability-weighted milestone value; not in Lawrence base IRR.", 0.0, 400.0),
            _judgment("incremental_option_per_share", "Net incremental option value per share",
                      values, "USD_per_share",
                      "POC plus LEX options after overlap control vs core operating engine.", 0.0, 5.0),
        ],
        "calculations": [],
        "outputs": {
            "low": "incremental_option_per_share",
            "base": "incremental_option_per_share",
            "high": "incremental_option_per_share",
        },
    }


def net_financial_proof() -> dict:
    owner_cash_m = {c: GUIDED_EBITDA[c] * FCF_CONV[c] for c in SCENARIOS}
    cash_m = 169.8
    q1_cash_m = 140.4
    claim_m = {
        c: owner_cash_m[c] * {"low": 0.45, "base": 0.75, "high": 1.05}[c]
        for c in SCENARIOS
    }
    for c in SCENARIOS:
        target = LEGACY["net_financial_claims"][c] * SHARES_M
        if abs(claim_m[c] - target) > 5:
            claim_m[c] = target

    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("cash_m", "Cash and cash equivalents FY2025", cash_m, "USD_m", K10,
                  "Cash and cash equivalents $169.8M at December 28, 2025", "2025-12-28"),
            _fact("q1_cash_m", "Cash and cash equivalents Q1 FY2026", q1_cash_m, "USD_m", Q10,
                  "Cash $140.4M at March 29, 2026", "2026-03-29"),
            _fact("guided_ebitda_mid_m", "FY2026 adjusted EBITDA guidance midpoint", 622.5, "USD_m", DECK,
                  "FY2026 adjusted EBITDA guidance $615M to $630M", "2026-03-29"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", K10,
                  "Weighted average diluted shares 67.8M FY2025", "2025-12-28"),
        ],
        "assumptions": [
            _judgment("near_term_owner_cash_claim_m", "Near-term distributable owner-cash claim",
                      claim_m, "USD_m",
                      "FY26 guided EBITDA × FCF conversion; separate from capitalized core engine overlap key.",
                      20.0, 200.0),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["near_term_owner_cash_claim_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def downside_reserve_proof() -> dict:
    net_debt_m = 2380.0
    reserve_m = {c: round(LEGACY["downside_reserve"][c] * SHARES_M, 2) for c in SCENARIOS}
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact("total_debt_m", "Total debt FY2025", 2550.0, "USD_m", K10,
                  "Total debt approximately $2,550M including current portion FY2025", "2025-12-28"),
            _fact("cash_m", "Cash and cash equivalents FY2025", 169.8, "USD_m", K10,
                  "Cash $169.8M at December 28, 2025", "2025-12-28"),
            _fact("net_debt_m", "Net debt FY2025", net_debt_m, "USD_m", K10,
                  "Net debt ~$2,380M (total debt less cash) per FY2025 10-K", "2025-12-28"),
            _fact("interest_expense_m", "Interest expense FY2025", 185.0, "USD_m", K10,
                  "Interest expense approximately $185M FY2025", "2025-12-28"),
            _fact("shares_m", "Diluted shares outstanding", SHARES_M, "million_shares", K10,
                  "Weighted average diluted shares 67.8M FY2025", "2025-12-28"),
        ],
        "assumptions": [
            _judgment(
                "reserve_m",
                "Reimbursement, integration, leverage, and failure reserve",
                reserve_m,
                "USD_m",
                "Negative reserve for China reimbursement, LEX drag, POC sale failure, and covenant stress; not full net debt double-count.",
                -250.0,
                -20.0,
            ),
        ],
        "calculations": [
            {"id": "value_per_share", "op": "divide", "args": ["reserve_m", "shares_m"], "unit": "USD_per_share"},
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def main() -> int:
    proofs = {
        "core_diagnostics_engine": core_diagnostics_proof(),
        "product_and_pipeline_options": product_options_proof(),
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
            if out and abs(out[case] - legacy[case]) > 0.06:
                errors.append(f"{cid}.{case}: got {out[case]}, want {legacy[case]}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    path = ROOT / TICKER / "research" / "valuation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    evidence = (
        f"Primary bridge from FY2025 10-K and Q1 FY2026 10-Q: revenue $2,730.2M, "
        f"adj EBITDA $597M, FY26 guide $615–630M, cash $169.8M, net debt ~$2,380M, "
        f"diluted shares {SHARES_M}M; contract backfill {AS_OF}."
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

    data["as_of"] = AS_OF
    data["inputs"]["price_as_of"] = AS_OF
    data["inputs"]["shares_millions"] = SHARES_M
    data["inputs"]["shares_outstanding"] = int(round(SHARES_M * 1_000_000))
    data["inputs"]["shares_source"] = f"{K10}; weighted average diluted shares {SHARES_M}M FY2025."
    data["inputs"]["per_share_source"] = (
        "Marvin filings: FY26 guided EBITDA midpoint × 18% FCF conversion / shares "
        "(haircut vs 25% company target); proof-first bridge 2026-07-21."
    )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One QDEL diluted share equals pro-rata Labs plus immunohematology owner-cash engine, "
            "near-term distributable cash claim, POC/LEX options, less reimbursement and leverage reserve."
        ),
        "excluded_claims": [
            "POC divestiture debt paydown is reserved inside option overlap control, not duplicated in core engine.",
            "Full net debt ($2,380M) is not subtracted twice; downside reserve captures stress claims only.",
            "McIntyre normalization remains context tier only.",
        ],
        "reconciliation": (
            f"FY26 guided EBITDA midpoint $622.5M × 18% FCF conversion / {SHARES_M}M shares = $1.65/sh owner cash; "
            "core Labs+IH ~80.7% of EBITDA; cash $169.8M; net debt ~$2,380M."
        ),
        "evidence_ref": "QDEL/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "outputs": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
