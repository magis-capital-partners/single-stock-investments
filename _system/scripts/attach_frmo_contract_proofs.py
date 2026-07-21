#!/usr/bin/env python3
"""Attach filing-backed calculation proofs to FRMO universal valuation contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from calculation_proof import evaluate_calculation_proof

VAL_PATH = ROOT / "FRMO" / "research" / "valuation.json"
QTR = "FRMO/investor-documents/ir-frmo/2026-02-28_Quarterly_Report.pdf"
QTR_TEXT = "FRMO/research/evidence/_text/2026-02-28_Quarterly_Report.pdf.txt"
SHARES_M = 44.022781


def src(ref: str, locator: str, as_of: str) -> dict:
    return {"ref": ref, "locator": locator, "as_of": as_of}


def shares_input() -> dict:
    return {
        "id": "shares_m",
        "label": "Common shares outstanding",
        "kind": "fact",
        "value": SHARES_M,
        "unit": "million_shares",
        "locked": True,
        "source": src(QTR, "Outstanding shares 44,022,781 as of February 28, 2026", "2026-02-28"),
    }


def core_engine_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            shares_input(),
            {
                "id": "investment_a_m",
                "label": "Investment A filing fair value",
                "kind": "fact",
                "value": 308.984,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    QTR_TEXT,
                    "Concentration table; Investment A $308,984 thousand, 82.0% of FRMO-attributable equity",
                    "2026-02-28",
                ),
            },
        ],
        "assumptions": [
            {
                "id": "economic_realization_pct",
                "label": "Risked realization on look-through marks pending catalyst close",
                "kind": "judgment",
                "values": {"low": 0.593, "base": 0.764, "high": 0.973},
                "unit": "ratio",
                "rationale": "Base discounts OTC holdco friction and mark volatility; high assumes partial SOTP close on Investment A look-through.",
                "allowed_range": {"min": 0.4, "max": 1.1},
            }
        ],
        "calculations": [
            {
                "id": "risked_m",
                "label": "Risked Investment A economic value",
                "op": "multiply",
                "args": ["investment_a_m", "economic_realization_pct"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Look-through investment holdings per share",
                "op": "divide",
                "args": ["risked_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def reinvestment_or_assets_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "probability_weighted_catalyst_nav",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            shares_input(),
            {
                "id": "filed_bundle_m",
                "label": "Filed management-company and exchange bundle",
                "kind": "fact",
                "value": 57.831,
                "unit": "USD_m",
                "locked": True,
                "source": src(
                    QTR_TEXT,
                    "MIH $13,917 + CNSX $243 + HKHC equity $27,187 + royalty $10,200 + Winland $5,542 + CMSG $742 (thousands)",
                    "2026-02-28",
                ),
            },
        ],
        "assumptions": [
            {
                "id": "catalyst_realization_pct",
                "label": "Probability-weighted re-rate on exchange and affiliate stakes",
                "kind": "judgment",
                "values": {"low": 0.411, "base": 0.716, "high": 1.226},
                "unit": "ratio",
                "rationale": "Low reflects MIAX lockup and private-mark lag; high adds partial HKHC/MIH listing re-rate.",
                "allowed_range": {"min": 0.2, "max": 1.5},
            }
        ],
        "calculations": [
            {
                "id": "risked_m",
                "label": "Risked management and exchange NAV",
                "op": "multiply",
                "args": ["filed_bundle_m", "catalyst_realization_pct"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Management-company and exchange interests per share",
                "op": "divide",
                "args": ["risked_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def net_financial_claims_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [
            shares_input(),
            {
                "id": "cash_m",
                "label": "Cash and cash equivalents",
                "kind": "fact",
                "value": 45.59,
                "unit": "USD_m",
                "locked": True,
                "source": src(QTR_TEXT, "Balance sheet; Cash and cash equivalents $45,590 thousand", "2026-02-28"),
            },
            {
                "id": "digital_assets_m",
                "label": "Digital assets at fair value",
                "kind": "fact",
                "value": 10.911,
                "unit": "USD_m",
                "locked": True,
                "source": src(QTR_TEXT, "Balance sheet; Digital assets, at fair value $10,911 thousand", "2026-02-28"),
            },
        ],
        "assumptions": [
            {
                "id": "attributable_liquid_pct",
                "label": "FRMO-attributable excess liquid claims after consolidated subs",
                "kind": "judgment",
                "values": {"low": 0.0, "base": 0.265, "high": 0.522},
                "unit": "ratio",
                "rationale": "Most consolidated cash sits in operating subs; base counts corporate treasury plus digital sleeve only.",
                "allowed_range": {"min": 0.0, "max": 0.75},
            }
        ],
        "calculations": [
            {
                "id": "liquid_m",
                "label": "Consolidated liquid claims",
                "op": "add",
                "args": ["cash_m", "digital_assets_m"],
                "unit": "USD_m",
            },
            {
                "id": "attributable_m",
                "label": "Attributable liquid claims",
                "op": "multiply",
                "args": ["liquid_m", "attributable_liquid_pct"],
                "unit": "USD_m",
            },
            {
                "id": "value_per_share",
                "label": "Cash and net claims per share",
                "op": "divide",
                "args": ["attributable_m", "shares_m"],
                "unit": "USD_per_share",
            },
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


def downside_reserve_proof() -> dict:
    return {
        "schema_version": "1.0",
        "method_id": "net_asset_value",
        "method_version": "1.0",
        "output_unit": "USD_per_share",
        "inputs": [shares_input()],
        "assumptions": [
            {
                "id": "reserve_m",
                "label": "Holdco discount, deferred tax, and realization reserve",
                "kind": "judgment",
                "values": {"low": -59.0, "base": -26.414, "high": -3.08},
                "unit": "USD_m",
                "rationale": "Low case adds deferred tax ($122.6M consolidated) and OTC illiquidity haircut; high assumes near-par realization.",
                "allowed_range": {"min": -150.0, "max": 0.0},
            }
        ],
        "calculations": [
            {
                "id": "value_per_share",
                "label": "Realization reserve per share",
                "op": "divide",
                "args": ["reserve_m", "shares_m"],
                "unit": "USD_per_share",
            }
        ],
        "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"},
    }


PROOFS = {
    "core_engine": (core_engine_proof, "net_asset_value", "bounded_estimate"),
    "reinvestment_or_assets": (reinvestment_or_assets_proof, "probability_weighted_catalyst_nav", "bounded_estimate"),
    "net_financial_claims": (net_financial_claims_proof, "net_asset_value", "calculated"),
    "downside_reserve": (downside_reserve_proof, "net_asset_value", "bounded_estimate"),
}


def apply_proof(component: dict) -> dict:
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
        val[case] = round(result["outputs"][case], 2)
    val["basis"] = "per_share"
    val["evidence_tier"] = "mixed_primary_and_estimate"
    val["evidence"] = (
        f"Filing-backed proof from {QTR}; overlap_key={component.get('overlap_key')}. "
        "Legacy Lawrence SOTP path remains separate stance gate."
    )
    val["assumption_summary"] = f"Proof outputs {result['outputs']}; see calculation_proof graph."
    val["cross_check"] = "Non-overlapping component schedule reconciles to Q3 FY2026 quarterly report."
    val["falsifier"] = "Primary filing revises Investment A, affiliate marks, or share count >10% without matching proof update."
    return result


def main() -> int:
    data = json.loads(VAL_PATH.read_text(encoding="utf-8"))
    data["as_of"] = "2026-07-21"
    report = []
    for comp in (data.get("component_valuation") or {}).get("components") or []:
        if comp["id"] in PROOFS:
            result = apply_proof(comp)
            report.append({"component_id": comp["id"], "outputs": result["outputs"]})

    eva = data.setdefault("economic_value_analysis", {})
    eva["ownership_waterfall"] = {
        "net_economic_claim": (
            "One FRMO common share equals a pro-rata claim on Investment A look-through, "
            "direct exchange and HKHC stakes, corporate liquidity, and holdco realization reserves."
        ),
        "excluded_claims": [
            "Investment A underlying holdings are valued once in core_engine; HKHC/MIH/Winland/CMSG are in reinvestment_or_assets.",
            "Consolidated noncontrolling subsidiary equity ($418.5M) is not FRMO-attributable look-through.",
            "Deferred tax liability ($122.6M consolidated) is reserved in downside_reserve, not double-counted in asset marks.",
        ],
        "reconciliation": (
            "Investment A $308.984M (82% of $376.704M FRMO equity); affiliate bundle $57.831M; "
            "cash $45.590M + digital assets $10.911M at consolidated level."
        ),
        "evidence_ref": "FRMO/research/evidence_reconciliation_2026-07-21.md",
    }
    eva["primary_cash_or_nav_bridge"] = {
        "filed_book_equity_m": 376.704,
        "filed_book_per_share": 8.56,
        "investment_a_m": 308.984,
        "investment_a_pct_of_equity": 82.0,
        "affiliate_bundle_m": 57.831,
        "cash_and_digital_m": 56.501,
        "component_base_sum_per_share": 6.04,
        "overlap_control": "Four unique overlap keys; no additive component capitalizes the same filing line twice.",
        "evidence_ref": QTR,
    }

    VAL_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"patched": str(VAL_PATH), "proofs": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
