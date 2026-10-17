"""Gas sensitivity of regional electricity and explicitly assumed miner contracts."""
from __future__ import annotations

from energy_common import finite


def gas_burn_bcf_day(mw: float, utilization: float, heat_rate: float, heat_content=1037.0) -> float:
    return (finite(mw, 'MW', 0) * 24 * finite(utilization, 'utilization', 0, 1)
            * finite(heat_rate, 'heat rate', 0) / (1000 * finite(heat_content, 'heat content', 1)))


def regional_power_price(gas_usd_mmbtu: float, region: dict, reference_gas=3.28) -> dict:
    gas = finite(gas_usd_mmbtu, 'gas price', 0)
    heat_rate = finite(region['heat_rate_mmbtu_mwh'], 'heat rate', 0)
    basis = finite(region['gas_basis_usd_mmbtu'], 'gas basis')
    beta = finite(region['gas_pass_through'], 'pass through', 0, 1)
    baseline_fuel = (reference_gas + basis) * heat_rate
    fuel_delta = (gas - reference_gas) * heat_rate
    wholesale = baseline_fuel + beta * fuel_delta + region['nonfuel_usd_mwh'] + region['scarcity_usd_mwh']
    delivered = wholesale / 1000 + region['delivery_usd_kwh']
    return {'region': region['id'], 'label': region['label'], 'status': region['status'],
            'gas_usd_mmbtu': gas, 'gas_basis_usd_mmbtu': basis,
            'generator_fuel_delta_usd_mwh': fuel_delta,
            'wholesale_usd_mwh': wholesale, 'delivered_usd_kwh': delivered,
            'delta_usd_kwh': beta * fuel_delta / 1000,
            'source_url': region['source_url']}


def contract_cost(cohort: dict, power: dict, period: str, baseline_usd_kwh: float) -> dict:
    fixed = finite(cohort['fixed_share'], 'contract fixed share', 0, 1)
    expired = period > cohort['contract_end']
    if expired:
        fixed = 0.0
    # Baseline is an all-delivered tariff: do not add delivery twice. Regional
    # gas sensitivity changes its merchant portion; the regional absolute level
    # is displayed separately and does not masquerade as a disclosed contract.
    merchant = max(0, baseline_usd_kwh + power['delta_usd_kwh'])
    effective = fixed * cohort['fixed_usd_kwh'] + (1 - fixed) * merchant
    return {'fixed_share': fixed, 'contract_expired': expired,
            'merchant_usd_kwh': merchant, 'effective_usd_kwh': effective,
            'availability': finite(cohort['availability'], 'availability', 0, 1),
            'contract_status': cohort['status']}


def build_power_path(rows: list[dict], config: dict) -> list[dict]:
    reference_gas = config['reference']['henry_hub_usd_mmbtu']['2027']
    return [{'period': row['period'], 'regions': [regional_power_price(row['henry_hub_usd_mmbtu'], region, reference_gas)
                                               for region in config['power_regions']]} for row in rows]
