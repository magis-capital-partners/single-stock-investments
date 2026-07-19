#!/usr/bin/env python3
"""Build the common, proof-first decision contract emitted by every valuation."""
from __future__ import annotations

from math import isfinite

from calculation_proof import CASES, PRICED_STATUSES, canonical_hash, component_proof, proof_completeness
from valuation_method_registry import approved_method
from valuation_method_router import route_valuation

PRIMARY_EVIDENCE = {"primary", "primary_verified", "primary_derived", "filing", "contract", "audited"}


def _annualized(value: float | None, price: float | None, years: int, distributions: float = 0) -> float | None:
    if value is None or price is None or price <= 0 or years <= 0 or value + distributions <= 0:
        return None
    result = ((float(value) + distributions) / float(price)) ** (1 / years) - 1
    return round(result * 100, 2) if isfinite(result) else None


def _input_kind(row: dict) -> str:
    proof = row.get("calculation_proof") or {}
    kinds = {item.get("kind") for item in [*(proof.get("inputs") or []), *(proof.get("assumptions") or [])]}
    if "judgment" in kinds:
        return "judgment"
    if "estimate" in kinds:
        return "estimate"
    if kinds == {"fact"}:
        return "fact"
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


def _sum_priced(rows: list[dict]) -> dict:
    result = {}
    for case in CASES:
        values = [row.get("range_per_share", {}).get(case) for row in rows if row.get("valuation_status") in PRICED_STATUSES]
        result[case] = round(sum(float(value) for value in values if value is not None), 4)
    return result


def build_universal_valuation_contract(data: dict, explicit_profile: str | None = None) -> dict:
    result = data.get("component_valuation_results") or {}
    economic = data.get("economic_value_analysis") or {}
    inputs = data.get("inputs") or {}
    route = route_valuation(data, explicit_profile)
    raw_components = [*(result.get("additive_components") or []), *(result.get("embedded_components") or [])]
    additive = [row for row in raw_components if row.get("treatment") == "additive"]
    embedded = [row for row in raw_components if row.get("treatment") != "additive"]
    components = [*additive, *embedded]
    price = inputs.get("price")
    shares = inputs.get("shares_outstanding")
    years = int((data.get("valuation_methodology") or {}).get("horizon_years") or data.get("lawrence_horizon_years") or 7)
    distributions = float((data.get("valuation_methodology") or {}).get("expected_distributions_per_share") or 0)
    validation_errors = list(economic.get("validation_errors") or [])
    evidence_blockers: list[str] = []
    records, evaluated_rows = [], []
    buckets = {"facts": [], "estimates": [], "judgments": []}
    old_proof = {str(row.get("component_id")): row for row in economic.get("valuation_proof") or []}

    overlap_seen: dict[str, str] = {}
    double_counting_flags = []
    for row in components:
        component_id = str(row.get("id"))
        proof_result = component_proof(row)
        evaluation = proof_result.get("evaluation")
        status = proof_result["valuation_status"]
        provenance = approved_method(
            evaluation.get("method_id") if evaluation else None,
            evaluation.get("method_version") if evaluation else None,
        )
        if evaluation and not provenance:
            status = "unpriced"
            evidence_blockers.append(
                f"{component_id}: method {evaluation.get('method_id')}@{evaluation.get('method_version')} is not approved"
            )
        calculated_range = evaluation.get("outputs") if evaluation and evaluation.get("status") == "valid" else {}
        kind = _input_kind(row)
        item = {
            "component_id": component_id, "label": row.get("label"), "kind": kind,
            "evidence_tier": row.get("evidence_tier"), "evidence": row.get("evidence"),
            "method": row.get("method"), "valuation_status": status,
        }
        buckets[kind + "s"].append(item)
        overlap_key = row.get("overlap_key") or component_id
        if row.get("treatment") == "additive" and overlap_key in overlap_seen:
            double_counting_flags.append(f"{component_id} overlaps additive component {overlap_seen[overlap_key]} via {overlap_key}")
        elif row.get("treatment") == "additive":
            overlap_seen[overlap_key] = component_id
        if row.get("treatment") == "additive" and status not in PRICED_STATUSES:
            evidence_blockers.append(f"{component_id}: material component is {status}; a valid calculation proof is required")
        if evaluation and evaluation.get("status") != "valid":
            evidence_blockers.extend(f"{component_id}: {message}" for message in evaluation.get("checks", {}).get("errors") or [])

        legacy_proof = old_proof.get(component_id) or {}
        record = {
            "component_id": component_id,
            "label": row.get("label"),
            "category": row.get("category"),
            "treatment": row.get("treatment"),
            "included_in_component_id": row.get("included_in_component_id"),
            "ownership_claim": legacy_proof.get("economic_claim") or row.get("label"),
            "ownership_percentage": ((row.get("driver_model") or {}).get("scenarios") or {}).get("base", {}).get("ownership_pct", 1.0),
            "quantity": legacy_proof.get("quantity"),
            "method": row.get("method"),
            "method_version": (row.get("calculation_proof") or {}).get("method_version"),
            "method_provenance": ({
                "method_id": provenance.get("method_id"),
                "version": provenance.get("version"),
                "label": provenance.get("label"),
                "power_zones": provenance.get("power_zones"),
                "equation": provenance.get("equation"),
                "sources": provenance.get("sources"),
            } if provenance else None),
            "comparable_ids": legacy_proof.get("comparable_ids") or [],
            "range_per_share": {case: calculated_range.get(case) for case in CASES},
            "legacy_range_per_share": proof_result.get("legacy_range_per_share"),
            "valuation_status": status,
            "calculation_proof": evaluation,
            "evidence_tier": row.get("evidence_tier"),
            "evidence_level": _standard_evidence_level(row),
            "evidence": row.get("evidence"),
            "scenario_assumptions": row.get("scenario_assumptions") or row.get("assumption_summary"),
            "probability_and_timing": legacy_proof.get("risk_and_timing"),
            "tax_and_realization_adjustments": legacy_proof.get("adjustment") or row.get("cross_check"),
            "falsifier": legacy_proof.get("falsifier") or row.get("falsifier"),
            "overlap_key": overlap_key,
            "assumption_type": kind,
        }
        records.append(record)
        evaluated_rows.append(record)

    proof_summary = proof_completeness(evaluated_rows)
    unvalued_count = sum(
        1 for row in evaluated_rows
        if row.get("treatment") == "additive" and row.get("valuation_status") not in PRICED_STATUSES
    )
    if not components:
        unvalued_count = 1
        evidence_blockers.append("A complete economic ownership map has not been supplied.")
    evidence_blockers.extend(validation_errors)
    evidence_blockers.extend(double_counting_flags)

    priced = _sum_priced([row for row in evaluated_rows if row.get("treatment") == "additive"])
    total = priced if unvalued_count == 0 else {case: None for case in CASES}
    legacy_total = (
        (data.get("legacy_component_valuation_snapshot") or {}).get("value_per_share")
        or ((result.get("total_equity_value_per_share") or {}) if result else {})
    )
    market_cap = float(price) * float(shares) / 1_000_000 if price is not None and shares else None
    debt = inputs.get("total_debt_m", inputs.get("debt_m"))
    cash = inputs.get("cash_m")
    enterprise_value = market_cap + float(debt or 0) - float(cash or 0) if market_cap is not None and (debt is not None or cash is not None) else None
    returns = {case: _annualized(total.get(case), price, years, distributions) for case in CASES}
    top_drivers = sorted(({
        "component_id": row.get("component_id"), "label": row.get("label"),
        "valuation_status": row.get("valuation_status"),
        "base_per_share": row.get("range_per_share", {}).get("base"),
        "legacy_base_per_share": (row.get("legacy_range_per_share") or {}).get("base"),
        "range_width_per_share": (
            round(float(row["range_per_share"]["high"]) - float(row["range_per_share"]["low"]), 4)
            if row.get("range_per_share", {}).get("high") is not None and row.get("range_per_share", {}).get("low") is not None else None
        ),
        "scenario_assumptions": row.get("scenario_assumptions"),
    } for row in evaluated_rows if row.get("treatment") == "additive"), key=lambda x: abs(float(x.get("range_width_per_share") or 0)), reverse=True)
    source_lineage = []
    for row in records:
        for source in ((row.get("calculation_proof") or {}).get("source_lineage") or []):
            source_lineage.append({"component_id": row["component_id"], **source})

    contract = {
        "schema_version": "2.0",
        "status": "decision_grade" if not evidence_blockers and unvalued_count == 0 else "evidence_blocked",
        "ticker": data.get("ticker"),
        "as_of": data.get("as_of"),
        "economic_ownership_map": records,
        "component_coverage": {
            "all_material_components_identified": bool(result.get("all_material_components_identified")),
            "material_component_count": len(components),
            "additive_component_count": len(additive),
            "embedded_component_count": len(embedded),
            "unvalued_component_count": unvalued_count,
            "double_counting_flags": double_counting_flags,
        },
        "input_classification": buckets,
        "method_route": route,
        "market": {
            "price_per_share": price, "fully_diluted_shares": shares,
            "market_cap_m": round(market_cap, 2) if market_cap is not None else None,
            "enterprise_value_m": round(enterprise_value, 2) if enterprise_value is not None else None,
        },
        "valuation": {
            "value_per_share": total,
            "priced_components_per_share": priced,
            "legacy_value_per_share": legacy_total or None,
            "probability_weighted_value_per_share": total.get("base"),
            "expected_distributions_per_share": distributions,
            "annualized_return_at_price_pct": returns,
            "downside_to_low_pct": round((float(total["low"]) / float(price) - 1) * 100, 2) if price and total.get("low") is not None else None,
            "horizon_years": years,
            "interpretation": "value_per_share is withheld while any material additive component is unpriced; priced_components_per_share is not a complete security value.",
        },
        "scenario_contract": {
            "rule": "Cases must change cited causal operating, capital, probability, timing, or financing drivers—not only a terminal multiple.",
            "top_value_drivers": top_drivers[:5],
            "reverse_expectations": (data.get("valuation_views") or {}).get("reverse_expectations") or data.get("reverse_expectations"),
        },
        "calculation_proof_summary": proof_summary,
        "source_lineage": source_lineage,
        "model_checks": {
            "calculation_graphs_valid": not proof_summary.get("calculation_errors"),
            "component_sum_reconciles": unvalued_count == 0,
            "no_double_counting": not double_counting_flags,
            "all_material_components_priced": unvalued_count == 0,
            "low_base_high_ordered": all(
                row.get("range_per_share", {}).get("low") is None
                or row["range_per_share"]["low"] <= row["range_per_share"]["base"] <= row["range_per_share"]["high"]
                for row in records
            ),
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
        "change_control": {
            "model_hash": None,
            "method_versions": sorted({f"{row.get('method')}@{row.get('method_version')}" for row in records if row.get("method_version")}),
            "change_log": data.get("valuation_change_log") or [],
            "rule": "A source fact is locked. Every assumption change requires a reason, author, timestamp, and before/after value.",
        },
        "decision_rule": "No security is decision-grade until every material claim is valued exactly once by a valid calculation proof and every material evidence blocker is resolved.",
    }
    contract["change_control"]["model_hash"] = canonical_hash({k: v for k, v in contract.items() if k != "change_control"})
    data["universal_valuation_contract"] = contract
    return contract


def strict_contract_errors(data: dict) -> list[str]:
    contract = data.get("universal_valuation_contract") or build_universal_valuation_contract(data)
    errors = list((contract.get("evidence") or {}).get("validation_errors") or [])
    errors.extend((contract.get("calculation_proof_summary") or {}).get("calculation_errors") or [])
    if (contract.get("component_coverage") or {}).get("unvalued_component_count"):
        errors.append("unvalued_component_count must equal zero")
    if (contract.get("component_coverage") or {}).get("double_counting_flags"):
        errors.append("double-counting flags remain open")
    if not (contract.get("model_checks") or {}).get("component_sum_reconciles"):
        errors.append("component sum does not reconcile to a complete security value")
    return sorted(set(errors))
