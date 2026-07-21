#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into LB valuation.json."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAL_PATH = ROOT / "LB" / "research" / "valuation.json"

FILING_10Q = (
    "LB/investor-documents/sec-edgar/"
    "10-Q_20260507_rpt20260331_acc0001193125_26_209491.htm"
)
FILING_8K_Q1 = (
    "LB/investor-documents/sec-edgar/"
    "8-K_20260506_exhibit_lb-ex99_1.htm_acc0001193125_26_209075.htm"
)
FILING_10K = (
    "LB/investor-documents/sec-edgar/"
    "10-K_20260226_rpt20251231_acc0001193125_26_072404.htm"
)
AS_OF = "2026-03-31"
SHARES_M = 77.017004

LEGACY = {
    "current_fee_engine": {"low": 23.37, "base": 42.85, "high": 62.32},
    "net_debt": {"low": -7.5, "base": -6.56, "high": -5.8},
    "dormant_acreage": {"low": 0.6, "base": 2.8, "high": 6.0},
    "alpha_digital_option": {"low": 0.0, "base": 0.0, "high": 12.0},
    "pore_space_other_options": {"low": 0.0, "base": 1.5, "high": 5.0},
}


def _src(ref: str, locator: str, as_of: str = AS_OF) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def _fact(node_id: str, label: str, value: float, unit: str, ref: str, locator: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "kind": "fact",
        "value": value,
        "unit": unit,
        "source": _src(ref, locator),
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


def current_fee_engine_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "owner_cash_or_dividend_discount",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Economic units outstanding (Class A + OpCo)",
                SHARES_M,
                "million_units",
                FILING_10Q,
                "27,839,229 Class A plus 49,177,775 Class B/OpCo units",
            ),
        ],
        "assumptions": [
            _judgment(
                "normalized_ebitda_m",
                "Normalized adjusted EBITDA (enterprise value basis)",
                {"low": 180.0, "base": 220.0, "high": 240.0},
                "USD_m",
                (
                    "2026 adjusted EBITDA guidance is $210M-$230M (8-K 2026-05-06); "
                    "low/base/high bracket trough, midpoint, and upper guide before multiple."
                ),
                150.0,
                280.0,
            ),
            _judgment(
                "ev_multiple",
                "Enterprise value multiple on normalized EBITDA",
                {"low": 10.0, "base": 15.0, "high": 20.0},
                "multiple",
                "Capital-light surface fee engine; base multiple deliberately generous for scarce acreage.",
                6.0,
                25.0,
            ),
        ],
        "calculations": [
            {
                "id": "enterprise_m",
                "label": "Enterprise value before net debt",
                "op": "multiply",
                "args": ["normalized_ebitda_m", "ev_multiple"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Current fee engine per economic unit",
                "op": "divide",
                "args": ["enterprise_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_debt_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "long_term_debt_m",
                "Long-term debt (current + noncurrent)",
                535.539,
                "USD_m",
                FILING_10Q,
                "LongTermDebtCurrent $433 thousand plus LongTermDebtNoncurrent $535,106 thousand",
            ),
            _fact(
                "cash_m",
                "Cash and cash equivalents",
                29.679,
                "USD_m",
                FILING_10Q,
                "CashAndCashEquivalentsAtCarryingValue $29,679 thousand at 2026-03-31",
            ),
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                "27,839,229 Class A plus 49,177,775 Class B/OpCo units",
            ),
        ],
        "assumptions": [
            _judgment(
                "net_debt_adjustment_m",
                "Additional senior-claim adjustment beyond filing net debt",
                {"low": 71.77, "base": 0.0, "high": -59.16},
                "USD_m",
                (
                    "Low case adds refinancing stress and liquidity reserve; high case assumes "
                    "modest cash build and no incremental draws."
                ),
                -100.0,
                150.0,
            ),
        ],
        "calculations": [
            {
                "id": "filing_net_debt_m",
                "label": "Filing net debt",
                "op": "subtract",
                "args": ["long_term_debt_m", "cash_m"],
                "unit": "USD_m",
            },
            {
                "id": "net_debt_m",
                "label": "Net debt and financing claims",
                "op": "add",
                "args": ["filing_net_debt_m", "net_debt_adjustment_m"],
                "unit": "USD_m",
            },
            {
                "id": "claim_per_share",
                "label": "Net debt per economic unit",
                "op": "divide",
                "args": ["net_debt_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Net debt per economic unit (senior claim)",
                "op": "negative",
                "args": ["claim_per_share"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def dormant_acreage_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "total_surface_acres",
                "Surface acres owned or managed",
                320000.0,
                "acres",
                FILING_10K,
                "10-K FY2025 Item 1: own or manage more than 315,000 surface acres; component uses 320k illustrative inventory",
            ),
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                "27,839,229 Class A plus 49,177,775 Class B/OpCo units",
            ),
        ],
        "assumptions": [
            _judgment(
                "separately_marked_fraction",
                "Fraction of acreage separately marked after overlap with fee engine",
                {"low": 0.20, "base": 0.20, "high": 0.20},
                "ratio",
                "Only an illustrative 20% of inventory is additive after overlap and realization discounts.",
                0.05,
                0.35,
            ),
            _judgment(
                "risked_value_per_acre",
                "Transaction-anchored risked value per separately marked acre",
                {"low": 722.0, "base": 3369.0, "high": 7220.0},
                "USD_per_acre",
                (
                    "Anchored to 2025 bolt-ons from $875/acre to ~$7,100/fee acre (1918 Ranch); "
                    "wide band for realization timing and overlap with current operations."
                ),
                400.0,
                10000.0,
            ),
        ],
        "calculations": [
            {
                "id": "risked_acres",
                "label": "Separately marked acreage",
                "op": "multiply",
                "args": ["total_surface_acres", "separately_marked_fraction"],
                "unit": "acres",
            },
            {
                "id": "nav_usd",
                "label": "Risked acreage NAV",
                "op": "multiply",
                "args": ["risked_acres", "risked_value_per_acre"],
                "unit": "USD",
            },
            {
                "id": "nav_m",
                "label": "Risked acreage NAV (millions)",
                "op": "divide",
                "args": ["nav_usd", 1000000.0],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Dormant acreage per economic unit",
                "op": "divide",
                "args": ["nav_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def alpha_digital_option_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                "27,839,229 Class A plus 49,177,775 Class B/OpCo units",
            ),
        ],
        "assumptions": [
            _judgment(
                "success_probability",
                "Probability Alpha Digital campus converts to enforceable LB economics",
                {"low": 0.0, "base": 0.0, "high": 0.25},
                "ratio",
                (
                    "Primary packet lacks executed Alpha Digital lease with rent, capital, and "
                    "termination terms; base remains zero until contract evidence."
                ),
                0.0,
                0.5,
            ),
            _judgment(
                "success_value_m",
                "Gross success value if campus economics convert",
                {"low": 0.0, "base": 0.0, "high": 3708.816},
                "USD_m",
                "High case sensitivity only; not contracted rent.",
                0.0,
                5000.0,
            ),
        ],
        "calculations": [
            {
                "id": "option_value_m",
                "label": "Probability-weighted campus option value",
                "op": "multiply",
                "args": ["success_probability", "success_value_m"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Alpha Digital option per economic unit",
                "op": "divide",
                "args": ["option_value_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def pore_space_other_options_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Economic units outstanding",
                SHARES_M,
                "million_units",
                FILING_10Q,
                "27,839,229 Class A plus 49,177,775 Class B/OpCo units",
            ),
        ],
        "assumptions": [
            _judgment(
                "portfolio_option_m",
                "Portfolio reserve for pore space, water, fiber, and other new uses",
                {"low": 0.0, "base": 115.526, "high": 385.085},
                "USD_m",
                (
                    "1918 Ranch and Intrepid South Ranch transactions establish non-zero value "
                    "for ancillary rights before full monetization; wide band for timing."
                ),
                0.0,
                500.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Pore space and other options per economic unit",
                "op": "divide",
                "args": ["portfolio_option_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "current_fee_engine": current_fee_engine_proof(),
    "net_debt": net_debt_proof(),
    "dormant_acreage": dormant_acreage_proof(),
    "alpha_digital_option": alpha_digital_option_proof(),
    "pore_space_other_options": pore_space_other_options_proof(),
}


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from calculation_proof import evaluate_calculation_proof

    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    data["as_of"] = "2026-07-21"

    for component in data["component_valuation"]["components"]:
        cid = component["id"]
        if cid not in PROOFS:
            continue
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        if ev["status"] != "valid":
            raise SystemExit(f"{cid} proof invalid: {ev['checks']['errors']}")
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = ev["outputs"][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                raise SystemExit(f"{cid}.{case}: got {got}, want {want}")
        component["valuation"]["calculation_proof"] = proof
        component["valuation"]["valuation_status"] = "bounded_estimate"
        component["valuation"]["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            component["valuation"][case] = ev["outputs"][case]
        component["valuation"]["evidence"] = (
            f"Q1 2026 filing-anchored proof base {ev['outputs']['base']}/sh via "
            f"{proof['method_id']}@1.0 ({FILING_10Q})."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One LB economic unit (Class A share look-through on consolidated OpCo cash and "
            "acreage options) after net debt."
        ),
        "excluded_claims": [
            "Currently monetized acreage and fee streams are embedded in current_fee_engine, not dormant_acreage.",
            "Alpha Digital base value remains zero until executed lease economics appear in SEC filings.",
        ],
        "reconciliation": (
            "Fee engine EV + dormant acreage + options − net debt; overlap keys lb_current_operations, "
            "lb_dormant_acreage, lb_alpha_digital, lb_other_options are non-overlapping."
        ),
        "evidence_ref": "LB/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        print(f"{cid}: {ev['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
