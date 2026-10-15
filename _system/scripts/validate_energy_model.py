#!/usr/bin/env python3
"""Check the published energy/Bitcoin contract without touching external services."""
from __future__ import annotations

from energy_common import ROOT, load_json


def validate(model, bridge):
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(model['schema_version'] == bridge['schema_version'] == '1.0', 'Unsupported schema')
    require(model['in_base_irr'] is False and bridge['in_base_irr'] is False, 'Research cannot change base IRR')
    require(model['model_id'] == bridge['model_id'], 'Energy/BTC build IDs differ')
    require(bridge['demand_model_changed'] is False and bridge['valuation_floor'] is False, 'Bridge must remain a cost sensitivity')
    require(len({s['id'] for s in model['scenarios']}) == 4, 'Four distinct scenarios required')
    history = model['history']
    require(all(0 < r['working_storage'] < 5000 for r in history), 'Working storage plausibility failed; exclude base gas')
    for scenario in model['scenarios']:
        previous = history[-1]['working_storage']
        for row in scenario['rows']:
            require(row['operating_minimum_bcf'] <= row['working_storage'] <= row['capacity_bcf'] + 1e-6, 'Storage outside bounds')
            actual = row['working_storage'] - previous
            implied = row['balance_bcf_day'] * row['days'] + row['unmet_demand_bcf'] - row['excess_supply_bcf']
            require(abs(actual-implied) < 1e-5, f"Gas mass imbalance: {scenario['id']} {row['period']}")
            previous = row['working_storage']
        points = next(s['rows'] for s in bridge['scenarios'] if s['id'] == scenario['id'])
        for point in points:
            require(point['period'] >= bridge['as_of'][:7], 'BTC snapshot carried backward')
            require(abs(point['electricity_cost_usd_btc'] + point['other_cost_usd_btc'] - point['total_cost_usd_btc']) < 1e-6, 'Mining cost layers do not reconcile')
            revenue = point['issued_btc_per_day'] * point['btc_price_assumption_usd'] + point['fee_daily_usd']
            require(abs(revenue / (point['network_hash_eh'] * 1000) - point['hashprice_usd_ph_day']) < 1e-6, 'Hashprice unit mismatch')
    for source in model['sources']:
        require(source['published_at'] <= model['as_of'], 'Future source in as-of snapshot')
    return True


if __name__ == '__main__':
    directory = ROOT / 'dashboard/data'
    validate(load_json(directory/'energy_model.json'),load_json(directory/'energy_btc_bridge.json'))
    print('Energy model: conservation, bounds, units, provenance and BTC contract passed')
