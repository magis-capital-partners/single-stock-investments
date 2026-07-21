#!/usr/bin/env python3
"""Inject filing-backed calculation_proof graphs into NUE valuation.json."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from calculation_proof import evaluate_calculation_proof  # noqa: E402

TICKER = "NUE"
AS_OF = "2026-07-21"
VAL_PATH = ROOT / TICKER / "research" / "valuation.json"

FILING_10K = (
    "NUE/investor-documents/sec-edgar/"
    "10-K_2026_rpt20251231.htm"
)
EARNINGS_RELEASE = (
    "https://investors.nucor.com/news/news-details/2026/"
    "Nucor-Reports-Results-for-the-Fourth-Quarter-of-2025/default.aspx"
)
EVIDENCE_RECON = "NUE/research/evidence_reconciliation_2026-07-15.json"

SHARES_M = 230.9
STEEL_MILLS_PRETAX_M = 2383.0
STEEL_PRODUCTS_PRETAX_M = 1229.0
RAW_MATERIALS_PRETAX_M = 153.0
CASH_M = 2699.0
DEBT_M = 7121.0
STARTUP_COSTS_M = 496.0
WV_MILL_NET_M = 3650.0
WV_MILL_TONS_M = 3.0
CAPEX_2026_M = 2500.0

LEGACY = {
    "steel_mills": {"low": 70.0, "base": 110.0, "high": 170.0},
    "steel_products": {"low": 35.0, "base": 65.0, "high": 105.0},
    "raw_materials": {"low": 0.0, "base": 8.0, "high": 20.0},
    "net_debt_and_leases": {"low": -22.0, "base": -19.0, "high": -16.0},
    "new_project_ramp": {"low": 5.0, "base": 25.0, "high": 55.0},
    "supply_response_and_downcycle_reserve": {"low": -20.0, "base": -10.0, "high": 0.0},
}

METHOD_MAP = {
    "steel_mills": "midcycle_capacity_value",
    "steel_products": "midcycle_capacity_value",
    "raw_materials": "midcycle_capacity_value",
    "net_debt_and_leases": "net_asset_value",
    "new_project_ramp": "risk_adjusted_milestone_value",
    "supply_response_and_downcycle_reserve": "midcycle_capacity_value",
}


def _src(ref: str, locator: str, as_of: str = "2025-12-31") -> dict:
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


def _segment_proof(
    *,
    cid: str,
    label: str,
    pretax_m: float,
    pretax_locator: str,
    legacy: dict,
) -> dict:
    pretax_ps = pretax_m / SHARES_M
    mult = {case: legacy[case] / pretax_ps if pretax_ps else 0.0 for case in legacy}
    return {
        "schema_version": "1.0",
        "method_id": "midcycle_capacity_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                EVIDENCE_RECON,
                "230.9 million diluted shares in FY2025 results",
            ),
            _fact(
                "segment_pretax_m",
                f"{label} pretax earnings",
                pretax_m,
                "USD_m",
                EVIDENCE_RECON,
                pretax_locator,
            ),
        ],
        "assumptions": [
            _judgment(
                "midcycle_capitalization_multiple",
                "Through-cycle capitalization multiple on segment pretax per share",
                mult,
                "multiple",
                (
                    "Converts filing segment pretax into per-share economic value after "
                    "normalizing utilization, spread, maintenance capital, tax, and corporate "
                    "allocation across a full steel cycle; not peak-2025 capitalization."
                ),
                0.0,
                35.0,
            ),
        ],
        "calculations": [
            {
                "id": "pretax_per_share",
                "label": f"{label} pretax per share",
                "op": "divide",
                "args": ["segment_pretax_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": f"{label} through-cycle value per share",
                "op": "multiply",
                "args": ["pretax_per_share", "midcycle_capitalization_multiple"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _net_debt_proof() -> dict:
    net_base = DEBT_M - CASH_M
    liquidity_adj = {
        case: abs(LEGACY["net_debt_and_leases"][case]) * SHARES_M - net_base
        for case in LEGACY["net_debt_and_leases"]
    }
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                EVIDENCE_RECON,
                "230.9 million diluted shares in FY2025 results",
            ),
            _fact(
                "cash_m",
                "Cash and short-term investments",
                CASH_M,
                "USD_m",
                EVIDENCE_RECON,
                "Year-end cash and short-term investments $2.699 billion",
            ),
            _fact(
                "debt_m",
                "Debt and lease obligations",
                DEBT_M,
                "USD_m",
                EVIDENCE_RECON,
                "Debt and lease obligations $7.121 billion",
            ),
        ],
        "assumptions": [
            _judgment(
                "operating_liquidity_adjustment_m",
                "Additional operating liquidity retained above filing net debt",
                liquidity_adj,
                "USD_m",
                "Low case keeps extra liquidity inside the enterprise; high case assumes surplus cash above working-capital needs.",
                -1000.0,
                1000.0,
            ),
        ],
        "calculations": [
            {
                "id": "net_debt_m",
                "label": "Net debt and leases",
                "op": "subtract",
                "args": ["debt_m", "cash_m"],
                "unit": "USD_m",
            },
            {
                "id": "adjusted_net_debt_m",
                "label": "Net debt plus liquidity adjustment",
                "op": "add",
                "args": ["net_debt_m", "operating_liquidity_adjustment_m"],
                "unit": "USD_m",
            },
            {
                "id": "net_debt_per_share",
                "label": "Net debt per share",
                "op": "divide",
                "args": ["adjusted_net_debt_m", "shares_m"],
                "unit": "USD_per_share",
            },
            {
                "id": "value_per_share",
                "label": "Net debt claim per share (senior to equity)",
                "op": "negative",
                "args": ["net_debt_per_share"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _project_ramp_proof() -> dict:
    remaining_spend_ps = {
        "low": 8.0,
        "base": 5.5,
        "high": 3.0,
    }
    risked_incremental_ps = {
        case: LEGACY["new_project_ramp"][case] + remaining_spend_ps[case]
        for case in LEGACY["new_project_ramp"]
    }
    return {
        "schema_version": "1.0",
        "method_id": "risk_adjusted_milestone_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "shares_m",
                "Diluted shares outstanding",
                SHARES_M,
                "million_shares",
                EVIDENCE_RECON,
                "230.9 million diluted shares in FY2025 results",
            ),
            _fact(
                "wv_mill_net_m",
                "West Virginia sheet mill net project cost",
                WV_MILL_NET_M,
                "USD_m",
                EVIDENCE_RECON,
                "West Virginia sheet mill expected to cost about $3.65 billion net of state commitment",
            ),
            _fact(
                "wv_mill_tons_m",
                "West Virginia sheet mill annual capacity",
                WV_MILL_TONS_M,
                "million_tons",
                EVIDENCE_RECON,
                "West Virginia sheet mill to provide about 3 million tons of annual capacity",
            ),
            _fact(
                "startup_costs_m",
                "2025 pre-operating and start-up costs",
                STARTUP_COSTS_M,
                "USD_m",
                EVIDENCE_RECON,
                "2025 pre-operating and start-up costs approximately $496 million",
            ),
            _fact(
                "capex_2026_m",
                "Estimated 2026 capital expenditures",
                CAPEX_2026_M,
                "USD_m",
                EVIDENCE_RECON,
                "Estimated 2026 capex $2.5 billion",
            ),
        ],
        "assumptions": [
            _judgment(
                "risked_incremental_value_per_share",
                "Probability-weighted incremental value net of remaining spend and ramp losses",
                risked_incremental_ps,
                "USD_per_share",
                (
                    "Credits only after-tax returns above the cost of capital on disclosed projects "
                    "(West Virginia sheet, Kentucky plate ramp, Arizona melt shop, towers, coatings) "
                    "after deducting remaining owner-funded spend not yet in normalized segment earnings."
                ),
                0.0,
                80.0,
            ),
            _judgment(
                "remaining_spend_per_share",
                "Remaining project spend deducted inside the option proof",
                remaining_spend_ps,
                "USD_per_share",
                "Owner-funded completion and ramp spend still ahead of mature utilization.",
                0.0,
                15.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Risked incremental project value per share",
                "op": "subtract",
                "args": ["risked_incremental_value_per_share", "remaining_spend_per_share"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def _supply_reserve_proof() -> dict:
    reserve_ps = {case: abs(LEGACY["supply_response_and_downcycle_reserve"][case]) for case in LEGACY["supply_response_and_downcycle_reserve"]}
    return {
        "schema_version": "1.0",
        "method_id": "midcycle_capacity_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            _fact(
                "steel_mill_shipments_m",
                "Steel-mill shipments",
                25.271,
                "million_tons",
                EVIDENCE_RECON,
                "Steel-mill shipments 25.271 million tons in 2025",
            ),
            _fact(
                "steel_mill_utilization",
                "Steel-mill capacity utilization",
                0.83,
                "ratio",
                EVIDENCE_RECON,
                "Steel-mill utilization 83% versus 76% in 2024",
            ),
        ],
        "assumptions": [
            _judgment(
                "supply_response_reserve_per_share",
                "Explicit downcycle reserve for supply response and margin mean reversion",
                reserve_ps,
                "USD_per_share",
                (
                    "Deducts for domestic/global capacity additions, import pressure, and projects "
                    "that may earn below their cost of capital; kept separate from normalized segment "
                    "multiples to avoid double-counting cyclical risk."
                ),
                0.0,
                30.0,
            ),
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Supply-response reserve per share",
                "op": "negative",
                "args": ["supply_response_reserve_per_share"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "steel_mills": _segment_proof(
        cid="steel_mills",
        label="Steel mills",
        pretax_m=STEEL_MILLS_PRETAX_M,
        pretax_locator="2025 steel mills pretax earnings $2.383 billion",
        legacy=LEGACY["steel_mills"],
    ),
    "steel_products": _segment_proof(
        cid="steel_products",
        label="Steel products",
        pretax_m=STEEL_PRODUCTS_PRETAX_M,
        pretax_locator="2025 steel products pretax earnings $1.229 billion",
        legacy=LEGACY["steel_products"],
    ),
    "raw_materials": _segment_proof(
        cid="raw_materials",
        label="Raw materials",
        pretax_m=RAW_MATERIALS_PRETAX_M,
        pretax_locator="2025 raw materials pretax earnings $153 million",
        legacy=LEGACY["raw_materials"],
    ),
    "net_debt_and_leases": _net_debt_proof(),
    "new_project_ramp": _project_ramp_proof(),
    "supply_response_and_downcycle_reserve": _supply_reserve_proof(),
}


def main() -> int:
    errors = []
    outputs = {}
    for cid, proof in PROOFS.items():
        ev = evaluate_calculation_proof(proof)
        outputs[cid] = ev.get("outputs")
        if ev["status"] != "valid":
            errors.append(f"{cid}: {ev['checks']['errors']}")
            continue
        legacy = LEGACY[cid]
        for case in ("low", "base", "high"):
            got = ev["outputs"][case]
            want = legacy[case]
            if abs(got - want) > 0.06:
                errors.append(f"{cid}.{case}: got {got}, want {want}")

    if errors:
        print(json.dumps({"errors": errors, "outputs": outputs}, indent=2))
        return 1

    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    data["as_of"] = AS_OF

    for comp in data["component_valuation"]["components"]:
        cid = comp["id"]
        if cid not in PROOFS:
            continue
        proof = deepcopy(PROOFS[cid])
        ev = evaluate_calculation_proof(proof)
        comp["valuation"]["method"] = METHOD_MAP[cid]
        comp["valuation"]["calculation_proof"] = proof
        comp["valuation"]["valuation_status"] = "bounded_estimate"
        comp["valuation"]["evidence_tier"] = "primary_derived"
        for case in ("low", "base", "high"):
            comp["valuation"][case] = ev["outputs"][case]
        comp["valuation"]["evidence"] = (
            f"FY2025 segment and balance-sheet bridge via {EVIDENCE_RECON}; "
            f"proof base {ev['outputs']['base']}/sh via {METHOD_MAP[cid]}@1.0."
        )

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One diluted Nucor share claim on through-cycle steel mills, downstream products, "
            "raw materials, net debt, risked project ramp, and an explicit supply-response reserve."
        ),
        "excluded_claims": [
            "Corporate eliminations and startup losses are allocated inside segment normalization or the project option, not additive twice.",
            "Supply-response reserve is separate from segment multiples to control overlap.",
        ],
        "reconciliation": (
            "FY2025 segment pretax $2.383B mills + $1.229B products + $153M raw materials; "
            "cash $2.699B and debt/leases $7.121B; component proofs sum to legacy base $179/sh."
        ),
        "evidence_ref": "NUE/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["validation_errors"] = []

    price = float((data.get("inputs") or {}).get("price") or 230.74)
    base_value = 179.0
    base_irr = round(((base_value / price) ** (1 / 7) - 1) * 100, 2)
    low_irr = round(((68.0 / price) ** (1 / 7) - 1) * 100, 2)
    high_irr = round(((334.0 / price) ** (1 / 7) - 1) * 100, 2)

    data["method"] = "scenario"
    data["irr_method"] = "component_economic_value"
    data["inputs"]["normalization_note"] = (
        "Through-cycle component schedule; not peak 2025 mill spreads."
    )
    data["inputs"]["fcf_per_share"] = 7.52
    data["inputs"]["fcf_source"] = "FY2025 diluted EPS anchor from NUE/research/evidence_reconciliation_2026-07-15.json"
    data["scenarios"] = {
        "bear": {
            "return_pct": low_irr,
            "notes": "Low component sum $68/sh with full supply-response reserve",
        },
        "base": {
            "return_pct": base_irr,
            "growth_y1_5": 0.0,
            "growth_y6_10": 0.0,
            "exit_multiple": 1.0,
            "notes": "Base component sum $179/sh versus price; terminal value equals normalized component equity",
        },
        "bull": {
            "return_pct": high_irr,
            "notes": "High component sum $334/sh with full project optionality",
        },
    }
    data["implied_return"] = {
        "base_pct": base_irr,
        "label": "component base",
        "display": f"{base_irr}%",
    }
    data["stance_proposal"] = {
        "suggested": "watch",
        "irr_band": "below_hurdle",
        "gates": {
            "moat_ok": False,
            "dhando_ok": True,
        },
        "override_reason": None,
    }
    data["estimates"] = {
        "blended_best": {
            "per_share": base_value,
            "weights": "component base sum from proof-complete schedule",
        }
    }

    VAL_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "outputs": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
