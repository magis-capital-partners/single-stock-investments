"""TCI diagnostics using the existing Lawrence cash flows and contract math.

All return outputs are percent_per_year. Diagnostics do not confer proof,
change the authority chain, or infer missing underwriting assumptions.
"""
from __future__ import annotations

import math
from copy import deepcopy

from lawrence_horizon import LAWRENCE_HORIZON_YEARS

METHOD = "dated_forward_cashflow_schedule_per_share@1.0"
CASES = {"bear": "low", "base": "base", "bull": "high"}
COMPONENTS = ("organic_growth_pct", "reinvestment_rate_pct", "incremental_roic_pct",
              "dilution_pct", "buyback_accretion_pct")


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def incremental_roic(nopat_start, nopat_end, capital_start, capital_end):
    """Return percent, withholding nonpositive incremental capital."""
    values = [number(v) for v in (nopat_start, nopat_end, capital_start, capital_end)]
    if None in values or values[3] <= values[2]:
        return None
    return 100 * (values[1] - values[0]) / (values[3] - values[2])


def build_bridge(valuation: dict, *, price: float | None = None) -> dict:
    # Lazy import: marvin_valuation calls this module after defining its math.
    from marvin_valuation import cashflows_full, irr

    inputs = valuation.get("inputs") or {}
    price = number(inputs.get("price") if price is None else price)
    fcf = number(inputs.get("fcf_per_share"))
    result = {
        "schema_version": "1.0", "unit": "percent_per_year", "method": METHOD,
        "status": "gap", "research_only": True, "capital_actionable": False,
        "horizon_years": LAWRENCE_HORIZON_YEARS,
        "persona_horizon_note": "Hohn's 4-year lens scores business fit; the contract uses the existing 7-year cash-flow horizon, with a separate 10-year sensitivity.",
        "model_as_of": valuation.get("as_of"),
        "price": price, "price_as_of": inputs.get("price_as_of"),
        "sources": [{"ref": f"{valuation.get('ticker')}/research/valuation.json#inputs.{field}",
                     "locator": inputs.get(source), "as_of": valuation.get("as_of"),
                     "claim_type": "inference", "status": "assumption"}
                    for field, source in [("price", "price_source"), ("fcf_per_share", "fcf_source")]
                    if valuation.get("as_of") and inputs.get(source)],
        "normalization_note": inputs.get("normalization_note"),
        "claim_type": "inference", "scenarios": {}, "sensitivity_10yr": {},
        "forward_cashflow_schedule": {}, "gaps": [],
    }
    if valuation.get("method") == "owner_earnings_reinvestment_dcf":
        return owner_cash_bridge(valuation, result)
    if valuation.get("method") != "full":
        result["gaps"].append("GAP: method is not a per-share full cash-flow model; retain its approved NAV/issuer-specific method.")
        return result
    if price is None or price <= 0 or fcf is None or fcf <= 0:
        result["gaps"].append("GAP: positive price and normalized FCF/share are required.")
        return result
    if not inputs.get("fcf_source") or not valuation.get("as_of"):
        result["gaps"].append("GAP: dated owner-cash source is missing.")
        return result
    policy = (valuation.get("valuation_methodology") or {}).get("forward_return_policy") or {}
    expected_policy = {"distribution_basis": "modeled_fcf_is_distributable_after_reinvestment",
        "reinvestment_treatment": "embedded_in_modeled_fcf", "net_assets_timing": "embedded_in_terminal_equity_value"}
    if any(policy.get(key) != expected for key, expected in expected_policy.items()):
        result["gaps"].append("GAP: the full-model sensitivity distributes all modeled FCF and adds terminal equity value; explicitly reconcile reinvestment, buybacks and net-asset timing before publishing it as shareholder IRR.")
    result["distribution_assumption"] = "Sensitivity assumes all modeled FCF is distributable after reinvestment and cash/debt are already reflected in terminal equity proceeds. Not established without an explicit reconciled policy."
    for name, case in CASES.items():
        scenario = (valuation.get("scenarios") or {}).get(name) or {}
        g1 = number(scenario.get("growth_y1_5"))
        g2 = number(scenario.get("growth_y6_end", scenario.get("growth_y6_10")))
        multiple = number(scenario.get("exit_pfcf_end", scenario.get("exit_pfcf_y10")))
        if None in (g1, g2, multiple) or min(g1, g2) <= -1 or multiple <= 0:
            result["gaps"].append(f"GAP: {name} growth path or terminal multiple is missing/invalid.")
            continue
        for horizon, target in [(LAWRENCE_HORIZON_YEARS, result["scenarios"]), (10, result["sensitivity_10yr"])]:
            flows = cashflows_full(price, fcf, g1, g2, multiple, years=horizon)
            try:
                exact = irr(flows) * 100
            except (OverflowError, ZeroDivisionError):
                from universal_valuation_contract import _cashflow_irr
                exact = _cashflow_irr(price, [{"year": i, "amount_per_share": v}
                                              for i, v in enumerate(flows[1:], 1)])
            if exact is None or not math.isfinite(exact):
                result["gaps"].append(f"GAP: {name} IRR could not be resolved.")
                continue
            growth = 100 * ((1 + g1) ** (min(5, horizon) / horizon)
                            * (1 + g2) ** (max(0, horizon - 5) / horizon) - 1)
            yield_pct = 100 * fcf / price
            multiple_pct = 100 * ((multiple / (price / fcf)) ** (1 / horizon) - 1)
            simple = yield_pct + growth + multiple_pct
            drivers = deepcopy(scenario.get("tci_growth_components") or {})
            missing = [key for key in COMPONENTS if number(drivers.get(key)) is None]
            explained = None if missing else (drivers["organic_growth_pct"]
                + drivers["reinvestment_rate_pct"] * drivers["incremental_roic_pct"] / 100
                - drivers["dilution_pct"] + drivers["buyback_accretion_pct"])
            target[name] = {
                "fcf_yield_pct": yield_pct, "per_share_fcf_growth_pct": growth,
                "multiple_change_pct": multiple_pct, "approximate_return_pct": simple,
                "exact_irr_pct": exact, "reconciliation_gap_pp": exact - simple,
                "reconciliation_reason": "Compounding, growing interim cash distributions and terminal timing.",
                "growth_components": {key: drivers.get(key) for key in COMPONENTS},
                "growth_component_gap_pp": None if explained is None else growth - explained,
                "growth_components_status": "gap" if missing else "assumption",
                "mechanism": scenario.get("notes"), "claim_type": "inference",
                "legacy_reported_return_pct": ((valuation.get("results") or {}).get(name) or {}).get("return_pct"),
            }
            if horizon == LAWRENCE_HORIZON_YEARS:
                result["forward_cashflow_schedule"][case] = [
                    {"year": year, "amount_per_share": amount}
                    for year, amount in enumerate(flows[1:], 1)
                ]
        if not scenario.get("causal_drivers"):
            result["gaps"].append(f"GAP: {name} cited causal drivers require underwriting; scenario notes alone are insufficient.")
        if missing:
            result["gaps"].append(f"GAP: {name} growth attribution missing {', '.join(missing)}; do not add buybacks twice to per-share growth.")
    if len(result["scenarios"]) == 3:
        result["status"] = "diagnostic"
    return result


def owner_cash_bridge(valuation: dict, result: dict) -> dict:
    """Read undiscounted proof nodes, never annualize the proof's present value.

    The terminal owner-cash multiple is treated as equity proceeds. No separate
    cash or debt is added; this avoids counting financing claims a second time.
    This explicit settlement convention is a research scenario assumption.
    """
    from calculation_proof import evaluate_calculation_proof
    from universal_valuation_contract import _cashflow_irr

    components = (valuation.get("component_valuation_results") or {}).get("additive_components") or []
    if len(components) != 1 or number(result.get("price")) is None or result["price"] <= 0:
        result["gaps"].append("GAP: owner-cash bridge requires one reconciled operating component and a positive price.")
        return result
    proof = components[0].get("calculation_proof") or {}
    evaluated = evaluate_calculation_proof(proof)
    if evaluated.get("status") != "valid":
        result["gaps"].append("GAP: invalid owner-cash calculation proof.")
        return result
    result["distribution_assumption"] = "Use proof owner cash after reinvestment; terminal owner-cash multiple is equity proceeds; no additional cash/debt settlement."
    for name, case in CASES.items():
        nodes = {n["id"]: n["value"] for n in evaluated["traces"][case]}
        shares = number(nodes.get("shares_m"))
        cash = [number(nodes.get(f"owner_cash_y{y}")) for y in range(1, 8)]
        terminal = number(nodes.get("terminal_value"))
        if shares is None or shares <= 0 or terminal is None or any(v is None for v in cash):
            result["gaps"].append(f"GAP: {case} undiscounted owner-cash, terminal or diluted-share proof nodes unavailable.")
            continue
        flows = [{"year": y, "amount_per_share": v / shares} for y, v in enumerate(cash, 1)]
        flows[-1]["amount_per_share"] += terminal / shares
        exact = _cashflow_irr(result["price"], flows)
        if exact is None:
            result["gaps"].append(f"GAP: {case} shareholder cash-flow IRR unresolved.")
            continue
        result["forward_cashflow_schedule"][case] = flows
        result["scenarios"][name] = {"exact_irr_pct": exact, "claim_type": "inference",
            "mechanism": result["distribution_assumption"], "growth_components_status": "proof_derived"}
    if len(result["scenarios"]) == 3:
        result["status"] = "diagnostic"
    result["sources"] = evaluated.get("source_lineage") or []
    return result


def contract_schedule_patch(bridge: dict) -> dict | None:
    """Proposal payload only. Existing component proof and ownership gates stay."""
    if len(bridge.get("forward_cashflow_schedule") or {}) != 3:
        return None
    return {"output_basis": "forward_cashflow_schedule",
            "primary_method": METHOD.split("@")[0], "method_version": "1.0",
            "schedule_generator": "tci_return_bridge@1.0",
            "horizon_years": LAWRENCE_HORIZON_YEARS,
            "forward_cashflow_schedule": deepcopy(bridge["forward_cashflow_schedule"])}


def irr_attribution(before: dict, after: dict) -> dict:
    """Ordered counterfactuals; contributions telescope exactly to the IRR move."""
    working = deepcopy(before)
    old = (build_bridge(working).get("scenarios") or {}).get("base", {}).get("exact_irr_pct")
    if old is None:
        return {"status": "gap", "reason": "Previous full cash-flow model is missing."}
    contributions = {}
    previous = old
    for group, fields in [("price", ["price"]), ("fcf", ["fcf_per_share"]),
                          ("growth", ["growth_y1_5", "growth_y6_end", "growth_y6_10"]),
                          ("multiple", ["exit_pfcf_end", "exit_pfcf_y10"])]:
        source = after.get("inputs") or {} if group in {"price", "fcf"} else (after.get("scenarios") or {}).get("base") or {}
        dest = working.setdefault("inputs", {}) if group in {"price", "fcf"} else working.setdefault("scenarios", {}).setdefault("base", {})
        for field in fields:
            if field in source:
                dest[field] = source[field]
            else:
                dest.pop(field, None)
        current = (build_bridge(working).get("scenarios") or {}).get("base", {}).get("exact_irr_pct")
        if current is None:
            return {"status": "gap", "reason": f"Missing comparable {group} inputs."}
        contributions[group + "_pp"] = current - previous
        previous = current
    return {"status": "available", "method": "price_then_fcf_then_growth_then_multiple",
            "unit": "percentage_points_per_year", "total_delta_pp": previous - old,
            **contributions, "residual_pp": previous - old - sum(contributions.values())}
