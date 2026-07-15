#!/usr/bin/env python3
"""Universal economic-value controls shared by valuation, pricing, and IC.

The framework standardizes the questions and validation gates while leaving the
component valuation method security-specific.  It deliberately does not blend
GAAP, comparable NAV, owner-cash value, and option value into one opaque score.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "reference" / "valuation_comparables.json"
VALUE_CASES = ("low", "base", "high")

ASSET_METHOD_TOKENS = (
    "nav", "acre", "land", "royalt", "transaction", "replacement", "liquidation",
    "sum_of_parts", "sotp", "book", "asset_value",
)
OPTION_METHOD_TOKENS = ("option", "milestone", "probability", "stage_gate")
CAPITAL_METHOD_TOKENS = ("infrastructure", "reinvestment", "ebitda", "network")


def _range(row: dict, prefix: str = "") -> dict[str, float] | None:
    keys = {case: f"{prefix}{case}" for case in VALUE_CASES}
    if any(row.get(key) is None for key in keys.values()):
        return None
    values = {case: round(float(row[key]), 2) for case, key in keys.items()}
    if not values["low"] <= values["base"] <= values["high"]:
        raise ValueError("economic value range must satisfy low <= base <= high")
    return values


def load_comparable_registry(path: Path = REGISTRY_PATH) -> dict:
    if not path.exists():
        return {"schema_version": "1.0", "comparables": []}
    return json.loads(path.read_text(encoding="utf-8"))


def economic_value_trigger(data: dict) -> dict:
    """Return deterministic reasons a full economic-value analysis is required."""
    reasons: list[str] = []
    schedule = data.get("component_valuation")
    methodology = data.get("valuation_methodology") or {}
    classification = data.get("classification_inputs") or {}
    archetype = str(classification.get("archetype") or "").lower()
    if isinstance(schedule, dict) and schedule.get("components"):
        reasons.append("explicit_component_schedule")
    if methodology.get("mode") == "separated_views":
        reasons.append("separated_valuation_views")
    if data.get("valuation_mode") == "optionality" or data.get("nav_overlay"):
        reasons.append("optionality_or_nav_overlay")
    if archetype in {
        "holding_company", "holdco", "bank", "insurer", "resource", "land_owner",
        "scarce_strategic_asset", "biotech", "pre_profit", "special_situation",
    }:
        reasons.append(f"economic_archetype:{archetype}")
    return {
        "required": bool(reasons),
        "reasons": reasons,
        "policy": "A complete economic-value analysis is required when any trigger fires; otherwise it is recommended.",
    }


def _default_falsifier(component: dict) -> str:
    category = component.get("category")
    method = str(component.get("method") or "").lower()
    if category == "real_option" or any(token in method for token in OPTION_METHOD_TOKENS):
        return "The next decision milestone fails, remaining capital rises materially, or the stated success probability no longer fits observable progress."
    if category == "infrastructure" or any(token in method for token in CAPITAL_METHOD_TOKENS):
        return "Utilization, incremental after-tax return on capital, or contract economics fall below the low-case assumptions."
    if category == "liability_or_reserve":
        return "The obligation, financing claim, tax, or realization friction is materially larger than the low-case reserve."
    if any(token in method for token in ASSET_METHOD_TOKENS):
        return "A directly comparable transaction or asset-specific impairment supports a value below the low-case unit mark after like-for-like adjustments."
    return "Owner cash, reinvestment economics, or competitive position remains below the low-case path for two reporting periods."


def _component_quantity(component: dict) -> dict:
    driver = component.get("driver_model") or {}
    if driver.get("units") is not None:
        return {"value": driver.get("units"), "unit": driver.get("unit_label", "economic units")}
    if driver.get("starting_revenue_m") is not None:
        return {"value": driver.get("starting_revenue_m"), "unit": "starting revenue, millions"}
    scenarios = driver.get("scenarios") or {}
    base = scenarios.get("base") or {}
    if base.get("success_value_m") is not None:
        return {"value": base.get("success_value_m"), "unit": "base success value, millions"}
    return {"value": 1, "unit": "per-share economic claim"}


def _group_map(groups: list[dict]) -> dict[str, dict]:
    mapped: dict[str, dict] = {}
    for group in groups:
        for component_id in group.get("component_ids") or []:
            if component_id in mapped:
                raise ValueError(f"economic value bridge double counts component: {component_id}")
            mapped[component_id] = group
    return mapped


def _validate_comparable_ids(groups: list[dict], registry: dict) -> list[str]:
    errors: list[str] = []
    records = {row.get("id"): row for row in registry.get("comparables") or []}
    for group in groups:
        for comparable_id in group.get("comparable_ids") or []:
            record = records.get(comparable_id)
            if not record:
                errors.append(f"unknown comparable_id {comparable_id}")
                continue
            required = ("economic_claim", "source_tier", "as_of", "source_ref", "adjustments_required")
            missing = [key for key in required if not record.get(key)]
            if missing:
                errors.append(f"comparable {comparable_id} missing {', '.join(missing)}")
    return errors


def build_economic_value_analysis(data: dict, config: dict | None = None, registry: dict | None = None) -> dict:
    """Build the common economic claim, bridge, proof table, and gate record."""
    trigger = economic_value_trigger(data)
    spec = config if isinstance(config, dict) else (data.get("economic_value") or {})
    component_results = data.get("component_valuation_results") or {}
    additive = component_results.get("additive_components") or []
    embedded = component_results.get("embedded_components") or []
    claim = spec.get("economic_claim") or {}
    groups = spec.get("component_groups") or []
    if not groups and additive:
        groups = [
            {
                "id": row["id"],
                "label": row["label"],
                "component_ids": [row["id"]],
                "economic_claim": row["label"],
                "valuation_basis": row.get("assumption_summary") or row.get("method"),
                "adjustments": row.get("cross_check") or "Risk and timing are reflected in the low/base/high range.",
                "overlap_control": f"Unique overlap key {row.get('overlap_key') or row['id']}.",
            }
            for row in additive
        ]
    mapped = _group_map(groups)
    additive_ids = {row.get("id") for row in additive}
    covered_ids = set(mapped)
    registry = registry or load_comparable_registry()

    errors: list[str] = []
    if trigger["required"] and spec.get("schema_version") != "1.0":
        errors.append("economic_value.schema_version 1.0 required")
    if trigger["required"] and component_results.get("status") != "complete":
        errors.append("complete component schedule required")
    if trigger["required"] and not claim.get("description"):
        errors.append("economic_claim.description required")
    if trigger["required"] and not claim.get("unit_label"):
        errors.append("economic_claim.unit_label required")
    if trigger["required"] and claim.get("unit_count") is None:
        errors.append("economic_claim.unit_count required")
    if trigger["required"] and not claim.get("enterprise_to_equity_reconciliation"):
        errors.append("economic_claim.enterprise_to_equity_reconciliation required")
    if trigger["required"] and not claim.get("unit_source"):
        errors.append("economic_claim.unit_source required")
    if trigger["required"] and not spec.get("gaap_role"):
        errors.append("gaap_role required")
    if spec.get("gaap_role") and spec.get("gaap_role") not in {"primary", "cross_check", "reference_only", "misleading_historical_cost"}:
        errors.append("gaap_role must use the controlled vocabulary")
    for group in groups:
        required_group_fields = ("id", "label", "component_ids", "economic_claim", "valuation_basis", "adjustments", "overlap_control")
        missing = [key for key in required_group_fields if not group.get(key)]
        if missing:
            errors.append(f"component group {group.get('id', '?')} missing {', '.join(missing)}")
    if trigger["required"] and (additive_ids - covered_ids or covered_ids - additive_ids):
        errors.append(
            "component groups must cover every additive component exactly once; "
            f"omitted={sorted(additive_ids-covered_ids)}, extra={sorted(covered_ids-additive_ids)}"
        )
    errors.extend(_validate_comparable_ids(groups, registry))

    proof: list[dict] = []
    for component in [*additive, *embedded]:
        group = mapped.get(component.get("id")) or mapped.get(component.get("included_in_component_id"), {})
        comparable_ids = group.get("comparable_ids") or []
        method = str(component.get("method") or "")
        comparable_required = (
            component.get("category") in {"real_option", "financial_asset"}
            or any(token in method.lower() for token in ASSET_METHOD_TOKENS)
        )
        comparable_role = "primary_or_cross_check" if comparable_ids else "not_applicable"
        driver = component.get("driver_model") or {}
        base_driver = (driver.get("scenarios") or {}).get("base") or {}
        risk_and_timing = None
        if component.get("category") == "real_option" or any(token in method.lower() for token in OPTION_METHOD_TOKENS):
            risk_and_timing = {
                "success_probability": base_driver.get("success_probability", base_driver.get("realization_probability")),
                "remaining_capital_m": base_driver.get("remaining_cost_m"),
                "timing_basis": group.get("risk_and_timing", {}).get("timing_basis") or driver.get("timing_basis"),
                "probability_basis": group.get("risk_and_timing", {}).get("probability_basis"),
                "remaining_capital_basis": group.get("risk_and_timing", {}).get("remaining_capital_basis"),
            }
            if not risk_and_timing.get("timing_basis") or (
                risk_and_timing.get("success_probability") is None and not risk_and_timing.get("probability_basis")
            ) or (
                risk_and_timing.get("remaining_capital_m") is None and not risk_and_timing.get("remaining_capital_basis")
            ):
                errors.append(f"option component {component.get('id')} requires probability, timing, and remaining-capital treatment")
        if comparable_required and not comparable_ids and not group.get("valuation_basis"):
            errors.append(f"component {component.get('id')} requires a comparable basis or registry reference")
        proof.append({
            "component_id": component.get("id"),
            "economic_claim": group.get("economic_claim") or component.get("label"),
            "quantity": _component_quantity(component),
            "method": method,
            "evidence_tier": component.get("evidence_tier"),
            "evidence": component.get("evidence"),
            "comparable_role": comparable_role,
            "comparable_ids": comparable_ids,
            "adjustment": group.get("adjustments") or component.get("cross_check") or component.get("assumption_summary"),
            "range_per_share": {
                case: component.get(f"{case}_per_share") for case in VALUE_CASES
            },
            "treatment": component.get("treatment"),
            "overlap_key": component.get("overlap_key") or component.get("id"),
            "overlap_control": group.get("overlap_control") or f"Unique overlap key {component.get('overlap_key') or component.get('id')}.",
            "falsifier": component.get("falsifier") or _default_falsifier(component),
            "risk_and_timing": risk_and_timing,
        })

    gross_nav = spec.get("gross_comparable_nav_per_share")
    if gross_nav:
        gross_nav = _range(gross_nav)
    risked_nav = component_results.get("total_equity_value_per_share") or {}
    price = (data.get("inputs") or {}).get("price")
    output = {
        "schema_version": "1.0",
        "status": "evidence_blocked" if errors else ("complete" if trigger["required"] else "recommended"),
        "trigger": trigger,
        "method": spec.get("method", "economic_claim_to_risked_present_value"),
        "economic_claim": claim,
        "gaap_role": spec.get("gaap_role"),
        "accounting_reference": spec.get("accounting_reference"),
        "comparable_hierarchy": spec.get("comparable_hierarchy") or [
            "issuer_arm_length_transaction", "same_asset_transaction", "public_peer",
            "replacement_cost", "approved_external_analysis",
        ],
        "gross_comparable_nav_per_share": gross_nav,
        "risked_present_value_per_share": risked_nav,
        "component_groups": [],
        "valuation_proof": proof,
        "wisdom_applied": spec.get("wisdom_applied") or [],
        "limitations": spec.get("limitations") or [],
        "complete_component_coverage": not (additive_ids - covered_ids or covered_ids - additive_ids),
        "validation_errors": sorted(set(errors)),
        "registry_version": registry.get("schema_version"),
    }
    by_id = {row.get("id"): row for row in additive}
    for group in groups:
        row = dict(group)
        component_ids = row.get("component_ids") or []
        row["risked_present_value_per_share"] = {
            case: round(sum(float(by_id[cid].get(f"{case}_per_share") or 0) for cid in component_ids if cid in by_id), 2)
            for case in VALUE_CASES
        }
        output["component_groups"].append(row)
    if gross_nav and price:
        output["gross_comparable_upside_downside_pct"] = {
            case: round((gross_nav[case] / float(price) - 1) * 100, 1) for case in VALUE_CASES
        }
        output["gross_to_risked_discount_pct"] = {
            case: round((1 - float(risked_nav[case]) / gross_nav[case]) * 100, 1)
            for case in VALUE_CASES if gross_nav[case]
        }
    convergence = spec.get("nav_convergence") or {}
    if gross_nav and convergence.get("enabled"):
        years = int(convergence.get("horizon_years") or data.get("lawrence_horizon_years") or 7)
        growth = convergence.get("annual_nav_growth") or {}
        realization = convergence.get("terminal_realization_pct") or {}
        hurdles = (0.10, 0.12, 0.15, 0.20)
        output["nav_convergence_entry_prices"] = {
            case: {
                f"{int(hurdle*100)}pct": round(
                    gross_nav[case] * (1 + float(growth.get(case, 0))) ** years
                    * float(realization.get(case, 1)) / (1 + hurdle) ** years, 2
                )
                for hurdle in hurdles
            }
            for case in VALUE_CASES
        }
        output["nav_convergence_contract"] = (
            f"{years}-year convergence to the stated share of comparable economic NAV with scenario-specific growth; "
            "interim distributions are excluded and owner-cash entry value remains separate."
        )
    data["economic_value_analysis"] = output
    return output


def strict_errors(data: dict) -> list[str]:
    analysis = data.get("economic_value_analysis") or build_economic_value_analysis(data)
    if not analysis.get("trigger", {}).get("required"):
        return []
    return list(analysis.get("validation_errors") or [])
