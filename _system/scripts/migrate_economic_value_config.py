#!/usr/bin/env python3
"""Promote legacy pricing bridges into the universal valuation specification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_REF = "_system/reviews/economic_value_comparable_audit_2026-07-15.md"
COMPARABLES = {
    "TPL": {
        "royalty_estate": ["tpl_royalty_acquisitions_2024_2025", "viper_sitio_2025"],
        "surface_estate": ["tpl_surface_sale_2025", "lb_reeves_800_2025", "lb_lea_3000_2025", "intrepid_south_ranch_2026"],
    },
    "LB": {
        "fee_engine": ["lb_q4_packages_2024", "lb_wolf_bone_2024"],
        "dormant_land": ["lb_reeves_800_2025", "lb_lea_3000_2025", "lb_1918_ranch_2025"],
        "other_options": ["lb_1918_ranch_2025", "intrepid_south_ranch_2026"],
    },
    "WBI": {"network": ["gravity_water_2025"]},
    "AZLCZ": {
        "renewable_leases": ["azlcz_groundbreaker_2026"],
        "surface_land": ["azlcz_groundbreaker_2026"],
        "minerals": ["azlcz_groundbreaker_2026"],
        "water": ["azlcz_groundbreaker_2026"],
        "railway_notes": ["azlcz_groundbreaker_2026"],
        "reserve": ["azlcz_groundbreaker_2026"],
    },
}


def normalize(ticker: str, valuation: dict, pricing: dict) -> dict:
    legacy = pricing.get("economic_value_bridge") or {}
    if not legacy:
        raise ValueError(f"{ticker}: pricing_model has no economic_value_bridge")
    inputs = valuation.get("inputs") or {}
    groups = []
    for raw in legacy.get("component_groups") or []:
        group = dict(raw)
        group["economic_claim"] = group.get("economic_claim") or group.get("label")
        group["adjustments"] = group.get("adjustments") or (
            f"Apply the production, contract, location, capital-intensity, ownership, timing, and realization adjustments described in {AUDIT_REF}."
        )
        group["comparable_ids"] = group.get("comparable_ids") or COMPARABLES.get(ticker, {}).get(group.get("id"), [])
        group["risk_and_timing"] = group.get("risk_and_timing") or {
            "probability_basis": "The component low/base/high range or milestone driver explicitly risks realization; uncertainty widens the range rather than creating a zero.",
            "timing_basis": "Discounting, realization friction, and the component assumptions reflect the time required to contract, develop, or monetize the claim.",
            "remaining_capital_basis": "Remaining owner-funded capital is deducted in the driver where disclosed; otherwise the range and realization reserve reflect the unresolved capital burden.",
        }
        groups.append(group)
    prior_gaap = str(legacy.get("gaap_role") or "")
    gaap_role = "misleading_historical_cost" if any(word in prior_gaap.lower() for word in ("zero", "book", "historical")) else "reference_only"
    economic_value = {
        "schema_version": "1.0",
        "method": legacy.get("method") or "economic_claim_to_risked_present_value",
        "economic_claim": {
            "description": pricing.get("economic_claim_note") or f"One {ticker} common economic unit.",
            "unit_label": "common economic unit",
            "unit_count": inputs.get("shares_outstanding"),
            "unit_source": "valuation.inputs.shares_outstanding",
            "enterprise_to_equity_reconciliation": "The complete additive component schedule includes operating assets, financial assets, debt or financing claims, minority interests where applicable, and realization reserves before division by the stated economic units.",
        },
        "gaap_role": gaap_role,
        "gaap_role_explanation": prior_gaap,
        "accounting_reference": legacy.get("accounting_reference"),
        "comparable_hierarchy": [
            "issuer_arm_length_transaction", "same_asset_transaction", "public_peer",
            "replacement_cost", "approved_external_analysis",
        ],
        "component_groups": groups,
        "wisdom_applied": legacy.get("wisdom_applied") or [],
        "limitations": legacy.get("limitations") or [],
    }
    if legacy.get("gross_comparable_nav_per_share") is not None:
        economic_value["gross_comparable_nav_per_share"] = legacy["gross_comparable_nav_per_share"]
    if legacy.get("nav_convergence") is not None:
        economic_value["nav_convergence"] = legacy["nav_convergence"]
    valuation["economic_value"] = economic_value
    return valuation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for raw in args.tickers:
        ticker = raw.upper()
        research = ROOT / ticker / "research"
        val_path = research / "valuation.json"
        pricing_path = research / "pricing_model.json"
        valuation = json.loads(val_path.read_text(encoding="utf-8"))
        pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
        normalize(ticker, valuation, pricing)
        if args.write:
            val_path.write_text(json.dumps(valuation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{ticker}: {'written' if args.write else 'ready'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
