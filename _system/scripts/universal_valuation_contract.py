#!/usr/bin/env python3
"""Build the common decision contract emitted by every valuation."""
from __future__ import annotations

from math import isfinite

from valuation_method_router import route_valuation

CASES = ("low", "base", "high")
PRIMARY_EVIDENCE = {"primary", "primary_verified", "primary_derived", "filing", "contract", "audited"}


def _annualized(value: float | None, price: float | None, years: int, distributions: float = 0) -> float | None:
    if value is None or price is None or price <= 0 or years <= 0 or value + distributions <= 0:
        return None
    result = ((float(value) + distributions) / float(price)) ** (1 / years) - 1
    return round(result * 100, 2) if isfinite(result) else None


def _input_kind(row: dict) -> str:
    tier = str(row.get("evidence_tier") or "").lower()
    if tier in PRIMARY_EVIDENCE:
        return "fact"
    if row.get("driver_model") or tier in {"model_input", "vendor", "secondary_corroborated"}:
        return "estimate"
    return "judgment"


def _standard_evidence_level(row: dict) -> str:
    tier = str(row.get("evidence_tier") or "").lower()
    if tier in {"primary_derived", "calculated"}:
        return "primary_derived"
    if tier in PRIMARY_EVIDENCE or "filing" in tier or "contract" in tier:
        return "primary_verified"
    if tier in {"secondary", "secondary_corroborated", "golden_case"}:
        return "secondary_corroborated"
    if tier in {"vendor", "market_data"}:
        return "vendor_sourced"
    if tier in {"speculative", "illustrative_only", "unverified"}:
        return "speculative"
    return "analyst_estimated"


def build_universal_valuation_contract(data: dict, explicit_profile: str | None = None) -> dict:
    result = data.get("component_valuation_results") or {}
    economic = data.get("economic_value_analysis") or {}
    inputs = data.get("inputs") or {}
    route = route_valuation(data, explicit_profile)
    additive = result.get("additive_components") or []
    embedded = result.get("embedded_components") or []
    components = [*additive, *embedded]
    total = result.get("total_equity_value_per_share") or {}
    price = inputs.get("price")
    shares = inputs.get("shares_outstanding")
    years = int((data.get("valuation_methodology") or {}).get("horizon_years") or data.get("lawrence_horizon_years") or 7)
    distributions = float((data.get("valuation_methodology") or {}).get("expected_distributions_per_share") or 0)
    explicit_complete = result.get("status") == "complete" and bool(result.get("all_material_components_identified"))
    unvalued_count = 0 if explicit_complete else 1
    validation_errors = list(economic.get("validation_errors") or [])
    evidence_blockers = []
    records = []
    buckets = {"facts": [], "estimates": [], "judgments": []}
    proof = {str(row.get("component_id")): row for row in economic.get("valuation_proof") or []}
    for row in components:
        component_id = str(row.get("id"))
        kind = _input_kind(row)
        item = {
            "component_id": component_id,
            "label": row.get("label"),
            "kind": kind,
            "evidence_tier": row.get("evidence_tier"),
            "evidence": row.get("evidence"),
            "method": row.get("method"),
        }
        buckets[kind + "s"].append(item)
        tier = str(row.get("evidence_tier") or "").lower()
        materiality = abs(float(row.get("base_per_share") or 0)) / max(abs(float(total.get("base") or 0)), .01)
        if materiality >= .10 and tier in {"speculative", "illustrative_only", "unverified"}:
            evidence_blockers.append(f"{component_id}: material value relies on {tier} evidence")
        records.append({
            "component_id": component_id,
            "label": row.get("label"),
            "category": row.get("category"),
            "treatment": row.get("treatment"),
            "included_in_component_id": row.get("included_in_component_id"),
            "ownership_claim": (proof.get(component_id) or {}).get("economic_claim") or row.get("label"),
            "ownership_percentage": ((row.get("driver_model") or {}).get("scenarios") or {}).get("base", {}).get("ownership_pct", 1.0),
            "quantity": (proof.get(component_id) or {}).get("quantity"),
            "current_operating_contribution": {
                "starting_revenue_m": (row.get("driver_model") or {}).get("starting_revenue_m"),
                "base_value_per_share": row.get("base_per_share"),
            },
            "growth_driver": row.get("scenario_assumptions") or row.get("assumption_summary"),
            "required_reinvestment": {
                "model_type": row.get("driver_model_type"),
                "base_incremental_after_tax_roic": ((row.get("driver_model") or {}).get("scenarios") or {}).get("base", {}).get("incremental_after_tax_roic"),
                "base_remaining_cost_m": ((row.get("driver_model") or {}).get("scenarios") or {}).get("base", {}).get("remaining_cost_m"),
                "treatment": "explicit in driver model or included in the stated owner-cash conversion and component range",
            },
            "method": row.get("method"),
            "comparable_ids": (proof.get(component_id) or {}).get("comparable_ids") or [],
            "range_per_share": {case: row.get(f"{case}_per_share") for case in CASES},
            "evidence_tier": row.get("evidence_tier"),
            "evidence_level": _standard_evidence_level(row),
            "evidence": row.get("evidence"),
            "probability_and_timing": (proof.get(component_id) or {}).get("risk_and_timing"),
            "tax_and_realization_adjustments": (proof.get(component_id) or {}).get("adjustment") or row.get("cross_check"),
            "falsifier": (proof.get(component_id) or {}).get("falsifier") or row.get("falsifier"),
            "overlap_key": row.get("overlap_key") or component_id,
            "assumption_type": kind,
        })
    if unvalued_count:
        evidence_blockers.append("A complete, explicit ownership/component schedule has not been supplied.")
    evidence_blockers.extend(validation_errors)
    market_cap = float(price) * float(shares) / 1_000_000 if price is not None and shares else None
    debt = inputs.get("total_debt_m", inputs.get("debt_m"))
    cash = inputs.get("cash_m")
    enterprise_value = market_cap + float(debt or 0) - float(cash or 0) if market_cap is not None and (debt is not None or cash is not None) else None
    returns = {case: _annualized(total.get(case), price, years, distributions) for case in CASES}
    top_drivers = sorted(
        ({
            "component_id": row.get("id"),
            "label": row.get("label"),
            "base_per_share": row.get("base_per_share"),
            "range_width_per_share": round(float(row.get("high_per_share") or 0) - float(row.get("low_per_share") or 0), 2),
            "scenario_assumptions": row.get("scenario_assumptions"),
        } for row in additive),
        key=lambda row: abs(row["range_width_per_share"]), reverse=True,
    )
    contract = {
        "schema_version": "1.0",
        "status": "decision_grade" if not evidence_blockers else "evidence_blocked",
        "ticker": data.get("ticker"),
        "as_of": data.get("as_of"),
        "economic_ownership_map": records,
        "component_coverage": {
            "all_material_components_identified": explicit_complete,
            "material_component_count": len(components),
            "additive_component_count": len(additive),
            "embedded_component_count": len(embedded),
            "unvalued_component_count": unvalued_count,
            "double_counting_flags": [],
        },
        "input_classification": buckets,
        "method_route": route,
        "market": {
            "price_per_share": price,
            "fully_diluted_shares": shares,
            "market_cap_m": round(market_cap, 2) if market_cap is not None else None,
            "enterprise_value_m": round(enterprise_value, 2) if enterprise_value is not None else None,
        },
        "valuation": {
            "value_per_share": {case: total.get(case) for case in CASES},
            "probability_weighted_value_per_share": total.get("base"),
            "expected_distributions_per_share": distributions,
            "annualized_return_at_price_pct": returns,
            "downside_to_low_pct": round((float(total["low"]) / float(price) - 1) * 100, 2) if price and total.get("low") is not None else None,
            "horizon_years": years,
        },
        "scenario_contract": {
            "rule": "Cases must change causal operating, capital, probability, timing, or financing drivers—not only the terminal multiple.",
            "top_value_drivers": top_drivers[:5],
            "reverse_expectations": (data.get("valuation_views") or {}).get("reverse_expectations") or data.get("reverse_expectations"),
        },
        "evidence": {
            "unresolved_count": len(set(evidence_blockers)),
            "blockers": sorted(set(evidence_blockers)),
            "validation_errors": validation_errors,
        },
        "monitoring": {
            "falsifiers": [row["falsifier"] for row in records if row.get("falsifier")],
            "required_refresh_triggers": ["new filing or material operating update", "capital-structure change", "material price move", "component milestone or falsifier"],
        },
        "decision_rule": "No security is decision-grade until every material economic claim is valued exactly once and every material evidence blocker is resolved.",
    }
    data["universal_valuation_contract"] = contract
    return contract


def strict_contract_errors(data: dict) -> list[str]:
    contract = data.get("universal_valuation_contract") or build_universal_valuation_contract(data)
    errors = list((contract.get("evidence") or {}).get("validation_errors") or [])
    if (contract.get("component_coverage") or {}).get("unvalued_component_count"):
        errors.append("unvalued_component_count must equal zero")
    if (contract.get("component_coverage") or {}).get("double_counting_flags"):
        errors.append("double-counting flags remain open")
    return sorted(set(errors))
