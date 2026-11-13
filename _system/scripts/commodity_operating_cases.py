"""Executable detailed cases and dependent shocks, with no inferred probabilities.

Every case must declare its evidence and assumptions. Optional inputs remain
absent until supplied; a missing physical input is never silently set to zero.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from commodity_common import load, save
from commodity_company_bridge import asset_cashflow
from commodity_physics import (
    concentrate_balance,
    cost_curve,
    hourly_dispatch,
    mine_output,
    positive,
    pv_silver,
    regional_gas_step,
    warehouse,
)


def refinery_products(case):
    """Regional volumetric product balances, with explicit refinery volume gain."""
    throughput = positive(case['throughput_mbd'], 'refinery throughput')
    days = positive(case['days'], 'days', False)
    products = case['products']
    if abs(sum(p['yield_fraction'] for p in products)-(1+case['processing_gain_fraction'])) > 1e-6:
        raise ValueError('Product yields must reconcile to throughput plus processing gain')
    rows = []
    for p in products:
        production = throughput*positive(p['yield_fraction'], 'product yield')
        change = (production+p['imports_mbd']-p['exports_mbd']-p['use_mbd'])*days
        end = p['opening_inventory_mb']+change
        rows.append({'product': p['product'], 'region': case['region'], 'production_mbd': production,
                     'inventory_change_mb': change, 'inventory_mb': max(0, end),
                     'unmet_product_demand_mb': max(0, -end),
                     'feasible': end >= 0, 'crack_spread_usd_bbl': p.get('crack_spread_usd_bbl'),
                     'price_response': 'No inferred price without a calibrated product model'})
    return rows


def weather_demand(case):
    """Named weather sensitivity; coefficients must identify their evidence/fit."""
    coefficients = case['coefficients']
    if not coefficients.get('basis'):
        raise ValueError('Weather coefficients require an evidence or assumption label')
    rows = []
    for r in case['rows']:
        weather = coefficients['bcf_day_per_hdd']*r['hdd']+coefficients['bcf_day_per_cdd']*r['cdd']
        normal = coefficients['bcf_day_per_hdd']*r['normal_hdd']+coefficients['bcf_day_per_cdd']*r['normal_cdd']
        rows.append({**r, 'weather_effect_bcf_day': weather-normal,
                     'normalized_demand_bcf_day': r['observed_demand_bcf_day']-weather+normal,
                     'basis': coefficients['basis']})
    return rows


def data_center_load(projects, as_of):
    stages = {'proposed', 'funded', 'grid_connected', 'operating'}
    result = []
    for p in projects:
        if p['stage'] not in stages:
            raise ValueError('Unknown data-center milestone')
        known = p['known_at'][:10] <= str(as_of)
        operating = p['stage'] == 'operating' and known and p.get('operating_from', '9999') <= str(as_of)
        result.append({**p, 'eligible_operating_mw': p['mw'] if operating else 0,
                       'incremental_national_demand_mw': None,
                       'note': 'Operating MW is a cross-check. A reconciled national baseline must be replaced before adding incremental load.'})
    return result


def copper_month(case):
    refined = case.get('refined_primary_kt')
    secondary = case.get('refined_secondary_kt')
    use = case.get('refined_use_kt')
    concentrate = concentrate_balance(*(case.get(k) for k in
        ('mine_kt', 'sxew_kt', 'concentrate_imports_kt', 'concentrate_exports_kt', 'smelter_intake_kt')))
    refined_balance = None if any(v is None for v in (refined, secondary, use)) else refined+secondary-use
    return {'concentrate': concentrate, 'refined_balance_kt': refined_balance,
            'projects': [{**p, 'output': mine_output(p, case['period'])} for p in case.get('projects', [])],
            'project_inclusion': 'Register is a cross-check unless a baseline explicitly replaces an asset contribution.',
            'tc_rc': case.get('tc_rc'), 'unreported_stock_bounds_kt': case.get('unreported_stock_bounds_kt'),
            'end_use': case.get('end_use', []), 'regional_stocks': case.get('regional_stocks', []),
            'price': None, 'price_basis': 'No validated balance-to-price calibration supplied'}


def gold_flow(case):
    required = ('mine_t', 'hedging_t', 'recycling_t', 'jewellery_t', 'technology_t', 'bar_coin_t', 'etf_t', 'central_bank_t')
    if any(case.get(k) is None for k in required):
        return {'status': 'missing_matched_flow_inputs', 'balance_t': None}
    supply = case['mine_t']+case['hedging_t']+case['recycling_t']
    absorbed = sum(case[k] for k in ('jewellery_t', 'technology_t', 'bar_coin_t', 'etf_t', 'central_bank_t'))
    return {'status': 'conditional_balance', 'supply_t': supply, 'identified_absorption_t': absorbed,
            'otc_and_unidentified_residual_t': supply-absorbed,
            'above_ground_stock_addition_t': case['mine_t'],
            'price': None, 'price_basis': 'Physical residual is not a causal monetary price premium.'}


def propagate(base, shocks):
    """Canonical-driver graph. Duplicate shocks fail rather than being summed twice."""
    seen, effects, lineage = set(), {}, []
    for shock in shocks:
        identity = shock['driver']
        if identity in seen:
            raise ValueError(f'Duplicate underlying shock: {identity}')
        seen.add(identity)
        if identity == 'global_demand':
            fraction = shock['fraction']
            mapping = {'oil_use_mbd': base.get('oil_use_mbd'), 'copper_use_kt': base.get('copper_use_kt'),
                       'silver_non_pv_use_moz': base.get('silver_non_pv_use_moz')}
            deltas = {key: value*fraction for key, value in mapping.items() if value is not None}
        elif identity == 'copper_mine_disruption':
            loss = positive(shock['loss_kt'], 'copper production loss')
            deltas = {'copper_refined_kt': -loss}
            coefficient = shock.get('silver_byproduct_moz_per_kt')
            if coefficient is not None:
                deltas['silver_byproduct_moz'] = -loss*coefficient
        elif identity == 'gas_price':
            # One gas price input reaches company realization and power fuel cost.
            # Neither is another physical gas-demand increment.
            change = shock['usd_mmbtu_change']
            deltas = {'gas_price_usd_mmbtu': change}
            if shock.get('power_heat_rate') is not None:
                deltas['power_fuel_usd_mwh'] = change*shock['power_heat_rate']
        else:
            raise ValueError(f'Unsupported canonical shock: {identity}')
        for key, value in deltas.items():
            effects[key] = effects.get(key, 0)+value
        lineage.append({'driver': identity, 'effects': deltas, 'evidence': shock.get('evidence', 'analyst_assumption')})
    return {'base': base, 'effects': effects, 'result': {k: v+effects.get(k, 0) for k, v in base.items()},
            'lineage': lineage, 'probability': None, 'basis': 'named_dependent_stress',
            'physical_price_response': 'withheld until calibrated', 'in_base_irr': False}


def run(case, as_of):
    if case.get('in_base_irr') is not False or not case.get('name'):
        raise ValueError('Named context-only case required')
    if not case.get('evidence') or not case.get('assumptions'):
        raise ValueError('Evidence and assumptions must be declared separately')
    if any(s['known_at'][:10] > str(as_of) for s in case['evidence']):
        raise ValueError('Future operating evidence')
    result = {'name': case['name'], 'evidence': case['evidence'], 'assumptions': case['assumptions'],
              'as_of': str(as_of), 'in_base_irr': False, 'valuation_authority': 'none'}
    if 'gas' in case:
        c = case['gas']
        result['gas'] = regional_gas_step(c['nodes'], c['pipelines'], c['days'])
    if 'refinery_products' in case:
        result['refinery_products'] = refinery_products(case['refinery_products'])
    if 'weather' in case:
        result['weather'] = weather_demand(case['weather'])
    if 'data_centers' in case:
        result['data_centers'] = data_center_load(case['data_centers'], as_of)
    if 'power' in case:
        c = case['power']
        result['power'] = hourly_dispatch(c['hours'], c['fleet'], c['gas_price'], c.get('carbon_price', 0), c.get('contract'))
    if 'copper' in case:
        result['copper'] = copper_month(case['copper'])
    if 'gold' in case:
        result['gold'] = gold_flow(case['gold'])
    if 'solar' in case:
        c = case['solar']
        result['solar'] = pv_silver(c['production_gw'], c['technologies'], c.get('net_yield', 1))
    if 'warehouse' in case:
        result['warehouse'] = warehouse(**case['warehouse'])
    if 'costs' in case:
        result['costs'] = cost_curve(case['costs'])
    if 'company_assets' in case:
        result['company_assets'] = [asset_cashflow(a['contract'], a['benchmark'], fx=a.get('fx', 1)) for a in case['company_assets']]
    if 'joint_stress' in case:
        c = case['joint_stress']
        result['joint_stress'] = propagate(c['base'], c['shocks'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    save(args.output, run(load(args.case), args.as_of))
