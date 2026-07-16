#!/usr/bin/env python3
"""Small, auditable calculators for the generalized valuation power zones."""
from __future__ import annotations

CASES = ("low", "base", "high")


def _ordered(values: dict[str, float]) -> dict[str, float]:
    out = {case: round(float(values[case]), 2) for case in CASES}
    if not out["low"] <= out["base"] <= out["high"]:
        raise ValueError("valuation cases must satisfy low <= base <= high")
    return out


def scarce_asset_value(spec: dict) -> dict[str, float]:
    """Unit value adjusted for claim, realization, friction, time, and capital."""
    values = {}
    for case in CASES:
        row = spec["scenarios"][case]
        gross = float(spec["units"]) * float(row["value_per_unit"])
        claim = float(row.get("economic_claim_pct", 1))
        probability = float(row.get("realization_probability", 1))
        friction = float(row.get("friction_pct", 0))
        years = float(row.get("years_to_realization", 0))
        discount = float(row.get("discount_rate", 0))
        capital = float(row.get("remaining_capital", 0))
        values[case] = (gross * claim * probability * (1 - friction) - capital) / (1 + discount) ** years
    return _ordered(values)


def compounder_value(spec: dict) -> dict[str, float]:
    """Owner-earnings DCF where growth is charged through reinvestment economics."""
    values = {}
    for case in CASES:
        row = spec["scenarios"][case]
        cash = float(spec["owner_earnings"])
        years = int(row.get("years", 10))
        reinvest = float(row.get("reinvestment_rate", 0))
        roic = float(row.get("incremental_after_tax_roic", 0))
        discount = float(row["discount_rate"])
        multiple = float(row["terminal_owner_earnings_multiple"])
        pv = 0.0
        for year in range(1, years + 1):
            cash *= 1 + reinvest * roic
            distributable = cash * (1 - reinvest)
            pv += distributable / (1 + discount) ** year
        pv += cash * multiple / (1 + discount) ** years
        values[case] = pv
    return _ordered(values)


def capital_cycle_value(spec: dict) -> dict[str, float]:
    values = {}
    shares = float(spec["shares"])
    for case in CASES:
        row = spec["scenarios"][case]
        revenue = float(spec["capacity_units"]) * float(row["utilization"]) * float(row["revenue_per_unit"])
        owner_cash = (revenue * float(row["normalized_margin"]) - float(row.get("maintenance_capital", 0))) * (1 - float(row.get("tax_rate", 0)))
        equity = owner_cash * float(row["owner_cash_multiple"]) - float(row.get("net_debt", 0)) - float(row.get("downcycle_reserve", 0))
        values[case] = equity / shares
    return _ordered(values)


def credit_value(spec: dict) -> dict[str, float]:
    values = {}
    shares = float(spec["shares"])
    for case in CASES:
        row = spec["scenarios"][case]
        equity = float(spec["tangible_equity"])
        excess = max(0.0, float(row["normalized_roe"]) - float(row["cost_of_equity"])) * equity
        franchise = excess * float(row["excess_return_duration_years"])
        value = equity + franchise - float(row.get("stress_losses", 0)) - float(row.get("senior_claims", 0))
        values[case] = value / shares
    return _ordered(values)


def catalyst_value(spec: dict) -> dict[str, float]:
    """Value a finite mutually-exclusive event tree including delay and break cases."""
    values = {}
    for case in CASES:
        events = spec["scenarios"][case]
        probability = sum(float(event["probability"]) for event in events)
        if abs(probability - 1) > 1e-6:
            raise ValueError(f"{case} catalyst probabilities must sum to 1")
        values[case] = sum(
            float(event["probability"]) * (float(event["payoff"]) - float(event.get("remaining_cost", 0)))
            / (1 + float(event.get("discount_rate", 0))) ** float(event.get("years", 0))
            for event in events
        )
    return _ordered(values)


def binary_milestone_value(spec: dict) -> dict[str, float]:
    values = {}
    for case in CASES:
        row = spec["scenarios"][case]
        asset_value = sum(
            float(asset["success_probability"]) * float(asset["success_value"])
            / (1 + float(asset.get("discount_rate", 0))) ** float(asset.get("years", 0))
            - float(asset.get("remaining_cost", 0))
            for asset in row["assets"]
        )
        values[case] = (float(row.get("net_cash", 0)) + asset_value - float(row.get("future_dilution_value", 0))) / float(row.get("shares", 1))
    return _ordered(values)


def predictable_cash_value(spec: dict) -> dict[str, float]:
    values = {}
    for case in CASES:
        row = spec["scenarios"][case]
        distribution = float(spec["distribution_per_share"])
        growth = float(row["growth"])
        required = float(row["required_return"])
        if required <= growth:
            raise ValueError("required_return must exceed perpetual growth")
        values[case] = distribution * (1 + growth) / (required - growth) - float(row.get("dilution_or_funding_per_share", 0))
    return _ordered(values)


CALCULATORS = {
    "scarce_asset_optionality": scarce_asset_value,
    "quality_reinvestment": compounder_value,
    "capital_cycle": capital_cycle_value,
    "credit_and_normalized_returns": credit_value,
    "catalyst_asset_value": catalyst_value,
    "binary_milestone": binary_milestone_value,
    "predictable_cash_flow": predictable_cash_value,
}


def calculate(profile_id: str, spec: dict) -> dict[str, float]:
    if profile_id not in CALCULATORS:
        raise ValueError(f"unsupported valuation profile: {profile_id}")
    return CALCULATORS[profile_id](spec)
