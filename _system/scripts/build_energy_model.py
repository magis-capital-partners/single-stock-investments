#!/usr/bin/env python3
"""Build auditable energy scenarios and an optional, separate BTC cost overlay."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from energy_common import ASSET_DIR, CONFIG, DATA_DIR, MODEL_VERSION, ROOT, atomic_json, digest, load_json, month_end, now_iso
from energy_balance import forecast, historical_validation, history_rows, summarize
from energy_btc_bridge import bridge_path, snapshot
from power_cost_model import build_power_path, gas_burn_bcf_day


def shift_month(period, delay):
    y, m = map(int, period.split('-'))
    value = y * 12 + m - 1 + delay
    return f'{value // 12:04d}-{value % 12 + 1:02d}'


def asset_comparison(rows, assets, scenario, config):
    trains = assets.get('lng', {}).get('trains', [])
    generators = assets.get('gas_generators', {}).get('generators', [])
    points = []
    for row in rows:
        period = row['period']
        lng = sum(t['baseload_bcf_day'] for t in trains if t['start_period'] and
                  shift_month(t['start_period'], scenario['project_delay_months'] if 'construction' in t['status'].lower() else 0) <= period)
        planned = [g for g in generators if g['inventory'] == 'Planned' and g['start_period'] and
                   shift_month(g['start_period'], scenario['project_delay_months']) <= period]
        mw = sum(g['nameplate_mw'] for g in planned)
        # A comparison, not an additive demand term: national power burn already
        # includes an assumed expansion. Existing retirements/dispatch are not solved.
        points.append({'period': period, 'reported_lng_baseload_bcf_day': lng if trains else None,
                       'lng_utilized_output_bcf_day': lng * scenario['project_utilization'] if trains else None,
                       'scenario_lng_exports_bcf_day': row['lng_exports'],
                       'planned_gas_generator_mw': mw if generators else None,
                       'illustrative_generator_burn_bcf_day': gas_burn_bcf_day(mw, 0.5, 7.5, config['gas_heat_content_btu_cf']) if generators else None})
    return {'rows': points, 'generator_utilization_assumption': 0.5, 'generator_heat_rate_assumption': 7.5,
            'included_in_national_balance': False,
            'note': 'Independent capacity cross-check. LNG baseload output differs from feedgas. Generator burn assumes 50% dispatch and 7.5 MMBtu/MWh; this is not incremental demand added to the national balance.'}


def compact_assets(assets):
    result = {'errors': assets.get('errors', {})}
    if assets.get('lng'):
        result['lng'] = assets['lng']
    source = assets.get('gas_generators', {})
    if source:
        rows = source['generators']
        result['gas_generators'] = {k: v for k, v in source.items() if k != 'generators'}
        result['gas_generators']['inventory_totals'] = source.get('inventory_totals') or [
            {'inventory': kind, 'count': len([g for g in rows if g['inventory'] == kind]),
             'nameplate_mw': sum(g['nameplate_mw'] for g in rows if g['inventory'] == kind)}
            for kind in sorted({g['inventory'] for g in rows})]
        result['gas_generators']['planned'] = sorted([g for g in rows if g['inventory'] == 'Planned'], key=lambda g: (g['start_period'] or '9999', g['id']))
    return result


def build(as_of=None, *, data_dir=DATA_DIR, asset_dir=ASSET_DIR, output_dir=None, config_path=CONFIG):
    as_of = as_of or date.today()
    output_dir = output_dir or ROOT / 'dashboard/data'
    config = load_json(config_path)
    if not config or config.get('in_base_irr') is not False:
        raise ValueError('Energy config must explicitly set in_base_irr=false')
    if config['reference']['published_at'] > as_of.isoformat():
        raise ValueError('Reference forecast was not available at requested as-of date')
    panel = load_json(data_dir / 'observations.json')
    if not panel:
        raise ValueError('Run fetch_energy_panel.py first')
    raw_assets = load_json(asset_dir / 'public_assets.json', {})
    assets = {k: v for k, v in raw_assets.items() if k == 'errors' or
              isinstance(v, dict) and v.get('published_at', '9999') <= as_of.isoformat()}
    history = history_rows(panel, as_of)
    if history[-1]['period'] >= config['forecast_end']:
        raise ValueError('Forecast horizon needs extension beyond latest history')
    sources = []
    warnings = []
    for series in panel['series'].values():
        source = {k: v for k, v in series.items() if k != 'observations'}
        source['age_days'] = (as_of - date.fromisoformat(source['published_at'])).days
        source['observation_age_days'] = (as_of - month_end(source['latest_period'])).days
        source['stale'] = max(source['age_days'], source['observation_age_days']) > config['max_source_age_days']
        if source['stale']:
            warnings.append(f"{source['label']} publication is {source['age_days']} days old.")
        sources.append(source)
    reference_age = (as_of - date.fromisoformat(config['reference']['published_at'])).days
    if reference_age > 60:
        warnings.append('Reviewed STEO reference is over 60 days old; refresh its versioned assumptions.')
    if panel.get('errors'):
        warnings.append('One or more source refreshes failed; retained observations are in use.')
    if not assets.get('lng') or not assets.get('gas_generators'):
        warnings.append('One or more public asset inventories are unavailable.')
    if raw_assets.get('errors'):
        warnings.append('Asset refresh had errors; inspect retained-source dates.')
    snap = snapshot(as_of, config)
    bridge_enabled = snap.get('available') and not any(s['stale'] for s in sources) and reference_age <= 120
    if not bridge_enabled:
        warnings.append(snap.get('reason') or 'Energy sources are too old for the BTC overlay.')
    scenarios = []
    bridge_scenarios = []
    for assumption in config['scenarios']:
        rows = forecast(history, config, assumption)
        power = build_power_path(rows, config)
        scenarios.append({'id': assumption['id'], 'label': assumption['label'], 'description': assumption['description'],
                          'status': assumption['status'], 'assumptions': assumption, 'rows': rows,
                          'summary': summarize(rows), 'power': power,
                          'asset_comparison': asset_comparison(rows, assets, assumption, config)})
        bridge_scenarios.append({'id': assumption['id'], 'rows': bridge_path(power, config, snap, dynamic=True) if bridge_enabled else []})
    weekly = panel.get('weekly_storage')
    if weekly and weekly['published_at'] > as_of.isoformat():
        weekly = None
    if weekly:
        weekly['stale'] = (as_of - date.fromisoformat(weekly['published_at'])).days > 14
    model_id = digest({'as_of': as_of.isoformat(), 'config': config, 'panel': [(s['id'], s['source_sha256']) for s in sources],
                       'weekly': weekly.get('source_sha256') if weekly else None,
                       'assets': [(k, digest({field: value for field, value in v.items() if field != 'retrieved_at'})) for k, v in assets.items() if isinstance(v, dict)], 'btc': snap})
    common = {'schema_version': '1.0', 'model_version': MODEL_VERSION, 'model_id': model_id,
              'generated_at': now_iso(), 'as_of': as_of.isoformat(), 'in_base_irr': False}
    bridge = {**common, 'available': bool(bridge_enabled), 'reason': None if bridge_enabled else warnings[-1],
              'snapshot': snap, 'scenarios': bridge_scenarios, 'parameters': config['btc'],
              'miner_cohorts': config['miner_cohorts'], 'verified_contract_coverage_pct': 0,
              'demand_model_changed': False, 'valuation_floor': False,
              'note': 'Conditional mining cost sensitivity. Constant BTC spot and fee assumptions; illustrative geography and contracts. Costs do not establish a BTC price floor. Future halving dates are estimates.'}
    model = {**common, 'status': 'research_scenarios', 'history': history, 'sources': sources,
             'weekly_storage': weekly,
             'latest_observation_period': history[-1]['period'], 'warnings': warnings,
             'reference': config['reference'], 'scenarios': scenarios, 'assets': compact_assets(assets),
             'storage_parameters': config['storage'], 'power_regions': config['power_regions'],
             'assumptions': config['assumptions'], 'validation': historical_validation(history),
             'falsification': [
                 {'condition': 'Supply exceeds the letter ceiling', 'metric': 'US dry production', 'threshold': 'Sustained production above 132 Bcf/day before end-2030', 'source_url': 'https://www.eia.gov/dnav/ng/hist/n9070us2m.htm'},
                 {'condition': 'LNG demand grows more slowly', 'metric': 'Actual exports and train dates', 'threshold': 'Exports below the scenario path for 6 months, or major trains delayed 12+ months', 'source_url': 'https://www.eia.gov/naturalgas/data.php'},
                 {'condition': 'Storage persistently exceeds normal', 'metric': 'Lower 48 working gas vs five-year average', 'threshold': 'At least 10% above average for 8 weekly reports', 'source_url': 'https://ir.eia.gov/ngs/ngs.html'},
                 {'condition': 'Generation needs less gas', 'metric': 'Gas power burn and reported project completions', 'threshold': 'Demand below the public-reference annual path across a full seasonal cycle', 'source_url': 'https://www.eia.gov/electricity/data/eia860m/'},
                 {'condition': 'Gas reaches fewer miners', 'metric': 'Verified geography, tariffs and renewals', 'threshold': 'Measured contract coverage materially lowers the assumed global pass-through', 'source_url': 'https://ccaf.io/cbnsi/cbeci/mining_map/methodology'}],
             'bridge': {'file': 'energy_btc_bridge.json', 'model_id': model_id, 'available': bool(bridge_enabled)},
             'limitations': ['US monthly balance; local transport and deliverability constraints are not solved.',
                             'Post-2027 supply is a scenario extension, not an independently verified well-by-well ceiling.',
                             'Gas price paths and regional pass-through are assumptions, not equilibrium price forecasts.',
                             'No predictive skill is claimed; observed history is the latest revised vintage.',
                             'Miner contracts and geographic shares are illustrative, with zero verified contract coverage.']}
    # Validate both fully before publishing. Matching content IDs prevent a
    # reader from combining artifacts from different runs during deployment.
    digest(model); digest(bridge)
    from validate_energy_model import validate
    validate(model, bridge)
    atomic_json(output_dir / 'energy_btc_bridge.json', bridge)
    atomic_json(output_dir / 'energy_model.json', model)
    from energy_exports import scenario_csv, write_csv
    for scenario in scenarios:
        write_csv(output_dir / 'energy_exports' / f"{scenario['id']}.csv", scenario_csv(model, bridge, scenario))
    atomic_json(output_dir / 'energy_exports' / 'full_model.json', {'energy_model': model, 'energy_btc_bridge': bridge}, compact=True)
    atomic_json(data_dir / 'snapshots' / f'{as_of}_{model_id}.json', {'energy_model': model, 'energy_btc_bridge': bridge}, compact=True)
    print(f"Energy model {model_id}: {len(history)} observed months; {len(scenarios)} scenarios; BTC overlay {'available' if bridge_enabled else 'unavailable'}")
    return model, bridge


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=date.fromisoformat)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    build(args.as_of, output_dir=args.output_dir, config_path=args.config)
