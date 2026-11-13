"""Evidence-led resolution layer shared by commodity and energy dashboards."""
from __future__ import annotations

import calendar

from commodity_common import ROOT, digest, finite, load
from commodity_company_bridge import build_companies
from commodity_forecast_scores import score, shift
from commodity_observations import (
    available,
    meaningful_diff,
    observation,
    pack,
    publication,
    source_state,
    unpack,
    weighted_readiness,
)
from commodity_operating_cases import propagate
from commodity_operating_cases import run as run_operating_case
from commodity_physics import cost_curve, lng_feedgas, pv_silver

DATA = ROOT/'_system/reference/market-data/commodities'


def forecast_evidence(current_rows, as_of):
    history = {}
    directory = ROOT/'_private/commodity/resolution-vintages-v2'
    for path in sorted(directory.glob('*.json')):
        if path.name[:10] <= str(as_of):
            for row in unpack(load(path)):
                if row['frequency'] == 'monthly':
                    history[(row['id'], row['known_at'])] = row
    for row in current_rows:
        if row['frequency'] == 'monthly':
            history[(row['id'], row['known_at'])] = row
    forecasts = []
    for row in history.values():
        if row['basis'] == 'published_forecast':
            forecasts.append({**row, 'origin': row['known_at'][:7], 'target': row['period'], 'model': 'publisher_EIA'})
    return score(list(history.values()), forecasts)


def market_ledger(panel, as_of):
    """Retain publisher hashes; unavailable original release dates remain null."""
    sources, rows = [], []
    specs = {'wti_spot': 'crude', 'brent_spot': 'crude', 'copper_spot': 'copper',
             'gold_bullion': 'gold', 'silver_bullion': 'silver', 'real_yield': 'gold', 'broad_dollar': 'gold',
             'london_silver_stocks': 'silver'}
    for key, kind in specs.items():
        item = panel.get('series', {}).get(key, {})
        if not all(item.get(k) for k in ('source_url', 'sha256', 'fetched_at')):
            continue
        src = {'id': key, 'url': item['source_url'], 'sha256': item['sha256'],
               'published_at': None, 'publication_date_basis': 'Unknown; availability bounded by capture date',
               'retrieved_at': item['fetched_at'], 'reviewed_at': item['fetched_at'],
               'reviewed_sha256': item['sha256'], 'max_age_days': item.get('max_age_days') or 45,
               'latest_observation': item.get('last_observation'),
               'error': item.get('error') if item.get('status') == 'fetch_failed' else None}
        sources.append(src)
        for r in item.get('observations', []):
            period = r['date'][:7] if item['frequency'] == 'monthly' else r['date']
            rows.append(observation(value=r['value'], source=src, period=period,
                                    metric='gross_vault_holdings' if key == 'london_silver_stocks' else key,
                                    commodity=kind, unit=item['unit'], frequency=item['frequency'],
                                    basis='observed_revised', extraction=item.get('source_id', key),
                                    publication_date_basis=src['publication_date_basis']))
    item = panel.get('free_inputs', {}).get('copper_exchange_stocks', {})
    for r in item.get('rows', []):
        if not r.get('sha256') or not r.get('source_url'):
            continue
        sid = 'cochilco_'+r['period']
        src = {'id': sid, 'url': r['source_url'], 'sha256': r['sha256'],
               'published_at': None, 'publication_date_basis': 'Unknown; availability bounded by capture date',
               'retrieved_at': item['fetched_at'], 'reviewed_at': item['fetched_at'],
               'reviewed_sha256': r['sha256'], 'max_age_days': 21, 'error': None}
        src.update(latest_observation=r['period'], required=False)
        sources.append(src)
        for region, field in [('LME', 'lme_t'), ('COMEX', 'comex_t'), ('SHFE', 'shfe_t')]:
            if finite(r.get(field)):
                rows.append(observation(value=r[field], source=src, period=r['period'],
                                        metric='exchange_gross_stocks', commodity='copper', unit='tonnes',
                                        frequency='weekly', region=region, basis='observed_revised',
                                        extraction='Cochilco weekly exchange inventory table'))
    return [s for s in sources if s['retrieved_at'][:10] <= str(as_of)], available(rows, as_of)


def requirement(commodity, metric, weight, reason, *, core=True, region=None):
    match = {'commodity': commodity, 'metric': metric}
    if region:
        match['region'] = region
    return {'id': metric, 'match': match, 'weight': weight, 'core': core, 'missing_reason': reason}


REQUIREMENTS = {
    'crude': [requirement('crude', 'papr_world', 3, 'Monthly world production unavailable'),
              requirement('crude', 'patc_world', 3, 'Monthly world consumption unavailable'),
              requirement('crude', 'pasc_oecd_t3', 3, 'Dated commercial inventory unavailable'),
              requirement('crude', 'BREPUUS', 2, 'Dated benchmark unavailable'),
              requirement('crude', 'refinery_products', 2, 'Matched regional refinery/product balance missing'),
              requirement('crude', 'quality_spread', 1, 'Quality differentials need a licensed or issuer feed', core=False)],
    'copper': [requirement('copper', 'refined_monthly', 3, 'Matched monthly refined production/use needs ICSG or validated public tables'),
               requirement('copper', 'smelter_intake', 3, 'Smelter intake must match concentrate geography and period'),
               requirement('copper', 'sxew', 2, 'Matched SX-EW split missing'),
               requirement('copper', 'warranted_stocks', 2, 'Location/warrant/ownership-specific feed not connected'),
               requirement('copper', 'mine_operating_inputs', 2, 'Verified throughput/grade/recovery project inputs missing'),
               requirement('copper', 'exchange_gross_stocks', 1, 'Dated exchange gross inventory unavailable', core=False)],
    'gold': [requirement('gold', 'mine', 2, 'Mine production unavailable'),
             requirement('gold', 'recycling', 2, 'Recycling unavailable'),
             requirement('gold', 'central_bank', 3, 'Central-bank estimates unavailable'),
             requirement('gold', 'etf', 3, 'ETF quarterly flows unavailable'),
             requirement('gold', 'jewellery', 2, 'Jewellery fabrication unavailable'),
             requirement('gold', 'regional_premium', 1, 'Regional physical premiums not connected', core=False)],
    'silver': [requirement('silver', 'pv_technology_intensity', 3, 'PV technology production and net intensity remain scenario assumptions'),
               requirement('silver', 'available_stocks', 3, 'Gross vault totals do not establish free float'),
               requirement('silver', 'byproduct_production', 2, 'Matched byproduct mine feed missing'),
               requirement('silver', 'etf', 2, 'Dated silver ETF flow feed not connected')],
    'gas': [requirement('gas', 'NGPRPUS', 3, 'National dry gas production unavailable'),
            requirement('gas', 'NGMPPM', 2, 'Permian marketed supply unavailable'),
            requirement('gas', 'NGMPAP', 2, 'Appalachian marketed supply unavailable'),
            requirement('gas', 'NGWG_SC', 3, 'Regional working storage unavailable'),
            requirement('gas', 'weather_normalized_demand', 2, 'Weather coefficients require aligned HDD/CDD evidence'),
            requirement('gas', 'pipeline_capacity', 2, 'Dated maintenance/capacity and regional flows not matched')],
    'power': [requirement('power', 'ELWHU_TX', 2, 'ERCOT hub monthly prices unavailable'),
              requirement('power', 'ELWHU_PJ', 2, 'PJM hub monthly prices unavailable'),
              requirement('power', 'hourly_load', 3, 'Hourly load and renewable traces not connected'),
              requirement('power', 'contract_coverage', 3, 'Verified firm/merchant contract coverage missing')],
}


def monthly_oil(rows, old_model, as_of):
    metrics = {key: {r['period']: r['value'] for r in rows if r['metric'] == key}
               for key in ('papr_world', 'patc_world', 'pasc_oecd_t3', 'BREPUUS', 'WTIPUUS')}
    common = sorted(set.intersection(*(set(x) for x in metrics.values())))
    actual = []
    for period in common:
        v = {k: metrics[k][period] for k in metrics}
        y, m = map(int, period.split('-'))
        balance = v['papr_world']-v['patc_world']
        actual.append({'period': period, 'production_mbd': v['papr_world'], 'consumption_mbd': v['patc_world'],
                       'balance_mbd': balance, 'world_stock_change_mb': balance*calendar.monthrange(y, m)[1],
                       'oecd_stock_mb': v['pasc_oecd_t3'], 'brent': v['BREPUUS'], 'wti': v['WTIPUUS'],
                       'spread': v['BREPUUS']-v['WTIPUUS'],
                       'basis': next(r['basis'] for r in rows if r['period'] == period and r['metric'] == 'papr_world')})
    stresses = []
    for s in old_model['scenarios']:
        path, lagged = [], []
        # Published monthly baseline: shocks are applied once to production/use.
        for row in [r for r in actual if r['period'] >= str(as_of)[:7]]:
            lag = int(s['shale_lag_quarters'])*3
            price_gap = max(0, (lagged[-lag] if lag and len(lagged) >= lag else 0)-old_model['cost_floor']['value'])
            # Assumed bounded response, rather than a step after four high quarters.
            response = s['shale_response_mbd']*min(1, price_gap/max(1, old_model['cost_floor']['value']))
            production = row['production_mbd']+s['supply_shock_mbd']+response
            use = row['consumption_mbd']+s['demand_shock_mbd']
            disruption = s['disruption_premium'] if s['id'] != 'steo' else 0
            brent = row['brent']+disruption
            lagged.append(max(.01, brent-row['spread']))
            path.append({**row, 'production_mbd': production, 'consumption_mbd': use,
                         'balance_mbd': production-use, 'brent': brent,
                         'wti': lagged[-1], 'lagged_supply_response_mbd': response,
                         'basis': 'published_forecast' if s['id'] == 'steo' else 'named_stress',
                         'price_status': 'published_forecast' if s['id'] == 'steo' else 'assumed_premium',
                         # Absolute world inventory and stress OECD allocation are unknown.
                         'oecd_stock_mb': row['oecd_stock_mb'] if s['id'] == 'steo' else None,
                         'world_stock_change_mb': (production-use)*calendar.monthrange(int(row['period'][:4]), int(row['period'][5:]))[1]})
        stresses.append({'id': s['id'], 'label': s['label'], 'rows': path})
    return {'rows': actual, 'scenarios': stresses,
            'supply_response_basis': 'Lagged incentive-cost response is an analyst sensitivity, not calibrated elasticity.',
            'world_inventory_level': None, 'refinery_product_balance': None,
            'note': 'Native EIA monthly observations/forecasts and dynamic published Brent-WTI spread. No annual values relabeled as monthly observations. Long-run quarterly extensions remain in the original scenario cards.'}


def solar_paths(silver):
    # The 2026 survey anchor determines the baseline net intensity; not a measured
    # engineering observation. Alternative technologies are explicit assumptions.
    anchor = next(r for r in silver['reference']['annual'] if r['year'] == 2026)['pv_moz']
    base_gw = 800
    baseline_intensity = anchor*31.1034768/base_gw
    paths = []
    for s in silver['scenarios']:
        rows = []
        for r in s['rows']:
            step = int(r['period'])-2026
            production = base_gw*(1.05**step)
            intensity = baseline_intensity*((1+s['pv_growth_pct']/100)/1.05)**step
            tech = [{'name': 'silicon_net_equivalent', 'share': 1, 'mg_per_watt': intensity}]
            physics = pv_silver(production, tech)
            # Replace old compounded PV term once, preserving the other physical terms.
            demand = r['demand_moz']-r['pv_moz']+physics['pv_moz']
            rows.append({'period': r['period'], **physics, 'technologies': tech,
                         'non_pv_demand_moz': r['demand_moz']-r['pv_moz'], 'demand_moz': demand,
                         'supply_moz': r['supply_moz'], 'balance_moz': r['supply_moz']-demand,
                         'etp_moz': r['etp_moz'], 'balance_less_etp_moz': r['supply_moz']-demand-r['etp_moz'],
                         'basis': 'anchor_equivalent_assumptions'})
        paths.append({'id': s['id'], 'label': s['label'], 'rows': rows})
    return {'baseline_production_gw': base_gw, 'baseline_mg_per_watt': baseline_intensity,
            'scenarios': paths, 'measured_technology_coverage_pct': 0,
            'production_vs_installation': 'Cell production, not installed solar capacity. Installation lag does not create silver demand twice.',
            'note': '800 GW and 5% annual production growth are explicit assumptions. Net equivalent intensity is inferred from the survey demand anchor; no TOPCon/HJT mix is asserted as measured. Technology mix, thrifting, recovered process scrap and substitution can be evaluated in the calculator.'}


def coverage_audit():
    registry = load(ROOT/'_system/portfolio/registry.json', {}).get('holdings', {})
    candidates = {'iron_ore_pellets': ['MSB', 'DRR.AX'], 'metallurgical_coal': ['ECOR.L'],
                  'timber_lumber': ['KEWL', 'RYN', 'PCH', 'WY'], 'uranium': ['CCJ', 'UEC', 'UROY', 'DNN']}
    return [{'commodity': k, 'registered_issuers': [t for t in tickers if t in registry],
             'model_status': 'not_modeled', 'position_weight': None,
             'priority_basis': 'Registry research coverage only; registry membership is not a funded holding.',
             'required_evidence': 'Reconcile current Flex positions and issuer asset revenue before assigning capital-weighted priority. No Gateway access.'}
            for k, tickers in candidates.items()]


def build(doc, as_of, previous=None, inputs_path=None, panel=None):
    inputs = load(inputs_path or DATA/'resolution_inputs.json', {'sources': [], 'observations': []})
    all_rows = unpack(inputs)
    rows = available(all_rows, as_of)
    sources = [s for s in inputs['sources'] if s['published_at'] <= str(as_of)]
    market_sources, market_rows = market_ledger(panel if panel is not None else {}, as_of)
    sources += market_sources
    rows += market_rows
    models = {m['id']: m for m in doc['models']}
    copper_source = next(s for s in models['copper']['sources'] if s['id'] == 'icsg_monthly')
    captured = panel.get('sources', {}).get('icsg_monthly', {}) if panel else {}
    if captured.get('sha256') == copper_source['sha256']:
        src = {'id': 'icsg_monthly', 'url': captured.get('resolved_url', copper_source['url']),
               'sha256': copper_source['sha256'], 'reviewed_sha256': copper_source['sha256'],
               'published_at': copper_source['published_at'], 'retrieved_at': captured['fetched_at'],
               'reviewed_at': copper_source['reviewed_at'], 'max_age_days': 45,
               'max_observation_age_days': 120, 'error': None if captured['status'] == 'fetched' else 'fetch_failed'}
        sources.append(src)
        for r in models['copper']['reference'].get('monthly_balances', []):
            if abs(r['refined_kt']-r['use_kt']-r['balance_kt']) > 1.01:
                raise ValueError('ICSG preliminary monthly balance does not reconcile')
            for field, metric in [('refined_kt', 'refined_production'), ('use_kt', 'refined_use'), ('balance_kt', 'refined_monthly')]:
                rows.append(observation(value=r[field], source=src, period=r['period'], metric=metric,
                                        commodity='copper', unit='kt', frequency='monthly', basis='observed_preliminary',
                                        extraction='Reviewed ICSG preliminary world refined production/use/balance table'))
        rows = available(rows, as_of)
    readiness = {k: weighted_readiness(v, rows, sources, as_of) for k, v in REQUIREMENTS.items()}
    gold_quarters = []
    for period in sorted({r['period'] for r in rows if r['commodity'] == 'gold'}):
        values = {r['metric']: r['value'] for r in rows if r['commodity'] == 'gold' and r['period'] == period}
        gold_quarters.append({'period': period, **values, 'basis': 'observed_estimate'})
    cost_assets = []
    for r in models['gold'].get('reference', {}).get('producer_costs', {}).get('rows', []):
        # Costs without matched production do not receive an invented weight.
        if r.get('production_oz') and r.get('aisc'):
            cost_assets.append({'id': r['company'], 'production': r['production_oz'], 'sustaining': r['aisc'],
                                'unit': 'USD/oz', 'currency': 'USD', 'period': r.get('period', 'unspecified'),
                                'byproduct_basis': r.get('byproduct_basis', 'issuer_reported')})
    for r in models['gold'].get('free_evidence', {}).get('gold_regional_cost_curve', {}).get('rows', []):
        if r.get('production_oz') and r.get('aisc_aud_oz'):
            cost_assets.append({'id': r['period'], 'production': r['production_oz'], 'sustaining': r['aisc_aud_oz'],
                                'unit': 'AUD/oz', 'currency': 'AUD', 'period': '2026-Q2', 'byproduct_basis': 'issuer_reported'})
    companies = build_companies(load(DATA/'company_bridges.json', {'companies': []}), as_of)
    old_rows = unpack(previous or {})
    changes = meaningful_diff(old_rows, rows)
    # The downloadable ledger retains every point; the change feed summarizes
    # the latest affected period per series and distinguishes first capture.
    latest_changes = {}
    for change in sorted(changes, key=lambda r: r['period']):
        latest_changes[(change['commodity'], change['metric'], change['region'])] = change
    result = {'schema_version': 'commodity_resolution.v1', 'publication': publication(rows, inputs, as_of),
              'sources': [source_state(s, as_of) for s in sources], 'readiness': readiness,
              'datasets': pack(rows), 'changes': list(latest_changes.values()), 'changed_observation_count': len(changes),
              'oil_monthly': monthly_oil([r for r in rows if r['commodity'] == 'crude'], models['crude'], as_of),
              'gold_quarters': gold_quarters, 'solar': solar_paths(models['silver']),
              'companies': companies, 'cost_curves': cost_curve(cost_assets), 'coverage_audit': coverage_audit(),
              'forecast_validation': forecast_evidence(rows, as_of),
              'driver_wiring': {
                  'crude': {'production': 'world physical balance', 'demand': 'world physical balance', 'spare_capacity': 'context until matched outage/production data', 'price': 'published monthly forecast or explicit stress premium'},
                  'copper': {'price': 'assumed price causes scrap response; balance does not independently predict price', 'concentrate': 'requires matched mine/SXEW/trade/intake', 'stocks': 'geography and warrant status required for deliverability'},
                  'gold': {'ETF': 'physical absorption only', 'central_bank': 'physical absorption and assumed reduced-form price sensitivity', 'real_yield_USD': 'assumed price sensitivities; diagnostic has no proven forecasting skill', 'producer_cost': 'operating economics; not a monetary price floor'},
                  'silver': {'PV': 'production × technology mix × intensity / net yield', 'ETP': 'deducted once after fabrication balance', 'price': 'gold / assumed ratio comparator; no calibrated physical tightness price forecast'}},
              'unknowns': ['Regional gas pipeline/maintenance and weather coefficients need verified input series.',
                           'Hourly power traces, congestion and customer contracts are not inferred from monthly hub prices.',
                           'ICSG detailed monthly balance, smelter intake, TC/RC and available inventory need validated public data or a separately approved license.',
                           'No calibrated forecast intervals or statistically supported structural price targets.',
                           'Company sensitivities cover revenue; contract-by-contract future cash flow remains incomplete.'],
              'entitlements': [{'dataset': 'ICSG detailed monthly bulletin', 'status': 'not_licensed'},
                               {'dataset': 'CME historical settlement curves', 'status': 'not_licensed'},
                               {'dataset': 'Regional/nodal power and physical metal free float', 'status': 'not_connected'}],
              'in_base_irr': False, 'valuation_authority': 'none'}
    mine = next(r for r in models['copper']['reference']['annual'] if r['year'] == 2026)
    silver_base = models['silver']['scenarios'][0]['rows'][0]
    result['joint_stresses'] = [
        {'name': 'Copper disruption and silver coproduct sensitivity',
         'period_basis': '2026 copper annual baseline; first silver scenario year. Cross-commodity sensitivity, not a matched monthly forecast.',
         **propagate({'copper_refined_kt': mine['refined_kt'], 'silver_byproduct_moz': silver_base['byproduct_moz']},
                     [{'driver': 'copper_mine_disruption', 'loss_kt': 400,
                       'silver_byproduct_moz_per_kt': models['silver']['reference']['copper_byproduct_2025_moz']/mine['mine_kt'],
                       'evidence': 'Assumed 400 kt disruption and proportional coproduct link; replaces other disruption shocks.'}])},
        {'name': 'Gas price and power fuel-cost sensitivity',
         **propagate({'gas_price_usd_mmbtu': 3, 'power_fuel_usd_mwh': 22.5},
                     [{'driver': 'gas_price', 'usd_mmbtu_change': 1, 'power_heat_rate': 7.5,
                       'evidence': 'Assumed 3 USD/MMBtu baseline and 7.5 MMBtu/MWh heat rate; no added gas demand.'}])}
    ]
    result['operating_cases'] = [run_operating_case(c, as_of) for c in load(DATA/'operating_cases.json', {}).get('cases', [])]
    energy = load(ROOT/'dashboard/data/energy_model.json', {})
    if energy.get('as_of', '9999') <= str(as_of):
        result['energy'] = energy.get('resolution', {})
    result['publication']['status'] = 'partial_inputs' if not all(v['core_ready'] for v in readiness.values()) else 'current'
    if not changes and previous:
        result['changes'] = previous.get('changes', [])
        result['changed_observation_count'] = previous.get('changed_observation_count', 0)
    # Served ID covers calculated outputs and company terms, not only source bytes.
    result['publication']['model_id'] = digest({'as_of': str(as_of), 'result': {k: v for k, v in result.items() if k != 'publication'}})[:20]
    for m in doc['models']:
        m['resolution_readiness'] = readiness[m['id']]
        m['valuation_authority'] = 'none'
    return result


def energy_detail(model, assets, as_of):
    inputs = load(DATA/'resolution_inputs.json', {})
    rows = [r for r in available(unpack(inputs), as_of) if r['commodity'] in ('gas', 'power')]
    sources = [s for s in inputs.get('sources', []) if s['published_at'] <= str(as_of)]
    lng = []
    for scenario in model['scenarios']:
        path = []
        for r in scenario['rows']:
            trains = [{**t, 'start_period': shift(t['start_period'], scenario['assumptions']['project_delay_months']) if t.get('start_period') and 'construction' in t.get('status', '').lower() else t.get('start_period')} for t in assets.get('lng', {}).get('trains', [])]
            flows = [lng_feedgas(t, r['period'], scenario['assumptions']['project_utilization']) for t in trains]
            path.append({'period': r['period'], 'output_bcf_day': sum(f['output_bcf_day'] for f in flows),
                         'feedgas_bcf_day': sum(f['feedgas_bcf_day'] for f in flows), 'basis': 'capacity_assumed_operations'})
        lng.append({'id': scenario['id'], 'rows': path})
    return {'datasets': pack(rows), 'readiness': {k: weighted_readiness(REQUIREMENTS[k], rows, sources, as_of) for k in ('gas', 'power')},
            'lng': lng, 'included_in_national_balance': False,
            'regional_storage_basis': 'EIA working gas by storage region; marketed production by basin is a different geography and processing basis.',
            'hourly_dispatch': {'status': 'hourly_evidence_required', 'rows': []},
            'data_center_stages': ['proposed', 'funded', 'grid_connected', 'operating'],
            'data_center_registry': [], 'data_center_incremental_demand_mw': None,
            'national_accounting': 'Asset paths and regional reports are cross-checks. National LNG and power demand are not increased a second time.'}
