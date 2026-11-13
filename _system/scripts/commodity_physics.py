"""Unit-explicit physical calculations. Inputs retain observed/assumed status."""
from __future__ import annotations

import calendar
import math

from commodity_common import finite

GRAMS_PER_TROY_OZ = 31.1034768


def positive(value, name, allow_zero=True):
    if not finite(value) or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f'{name} must be finite and positive')
    return value


def share(value, name):
    positive(value, name)
    if value > 1:
        raise ValueError(f'{name} must be a fraction between zero and one')
    return value


def pv_silver(production_gw, technologies, yield_fraction=1):
    """Cell production GW × mix × mg/W ÷ grams/oz -> million ounces.

    yield_fraction is net silver utilization after recovered process scrap;
    counting gross process loss as final demand would overstate consumption.
    """
    positive(production_gw, 'cell production')
    share(yield_fraction, 'net material yield')
    if yield_fraction == 0 or abs(sum(t['share'] for t in technologies) - 1) > 1e-8:
        raise ValueError('Technology shares must sum to one and yield must exceed zero')
    intensity = 0
    for t in technologies:
        share(t['share'], 'technology share')
        positive(t['mg_per_watt'], 'silver intensity')
        intensity += t['share'] * t['mg_per_watt']
    return {'pv_moz': production_gw * intensity / GRAMS_PER_TROY_OZ / yield_fraction,
            'weighted_mg_per_watt': intensity, 'production_gw': production_gw,
            'yield_fraction': yield_fraction}


def mine_output(project, period):
    """Contained payable copper kt; no output before dated operation milestone."""
    start = project.get('start_period')
    if not start or period < start:
        return {'gross_kt': 0, 'attributable_kt': 0, 'status': 'not_operating'}
    required = ('ore_mt_per_year', 'copper_grade_pct', 'recovery', 'ownership', 'availability', 'ramp_months')
    if any(project.get(k) is None for k in required):
        return {'gross_kt': None, 'attributable_kt': None, 'status': 'missing_operating_inputs'}
    for key in ('recovery', 'ownership', 'availability'):
        share(project[key], key)
    positive(project['ore_mt_per_year'], 'throughput')
    positive(project['copper_grade_pct'], 'grade')
    if project['copper_grade_pct'] > 100:
        raise ValueError('Copper grade cannot exceed 100%')
    positive(project['ramp_months'], 'ramp months', False)
    year, month = map(int, period.split('-'))
    sy, sm = map(int, start.split('-'))
    elapsed = (year-sy)*12 + month-sm + 1
    if project.get('end_period') and period > project['end_period']:
        return {'gross_kt': 0, 'attributable_kt': 0, 'status': 'mine_life_ended'}
    ramp = min(1, elapsed/project['ramp_months'])
    annual = project['ore_mt_per_year'] * project['copper_grade_pct'] * 10 * project['recovery'] * project['availability']
    days = calendar.monthrange(year, month)[1]
    gross = annual * days / (366 if calendar.isleap(year) else 365) * ramp
    return {'gross_kt': gross, 'attributable_kt': gross*project['ownership'], 'ramp': ramp,
            'status': project.get('basis', 'analyst_assumption')}


def concentrate_balance(mine_kt, sxew_kt, imports_kt, exports_kt, smelter_intake_kt):
    values = [mine_kt, sxew_kt, imports_kt, exports_kt, smelter_intake_kt]
    if any(v is None for v in values):
        return {'balance_kt': None, 'status': 'matched_concentrate_inputs_missing'}
    for value in values:
        positive(value, 'contained copper')
    if sxew_kt > mine_kt:
        raise ValueError('SX-EW cannot exceed total mine production')
    supply = mine_kt - sxew_kt + imports_kt - exports_kt
    return {'supply_kt': supply, 'intake_kt': smelter_intake_kt,
            'balance_kt': supply - smelter_intake_kt, 'status': 'calculated'}


def warehouse(gross, etf_owned=None, warranted=None, available=None):
    positive(gross, 'gross warehouse metal')
    for name, value in [('ETF-owned', etf_owned), ('warranted', warranted), ('available', available)]:
        if value is not None and not 0 <= value <= gross:
            raise ValueError(f'{name} must lie within gross holdings')
    return {'gross': gross, 'etf_owned': etf_owned, 'warranted': warranted, 'available': available,
            'outside_etfs': gross-etf_owned if etf_owned is not None else None,
            'note': 'Outside-ETF, warranted, deliverable and freely available metal are different concepts; categories overlap.'}


def regional_gas_step(nodes, edges, days):
    """Explicit directed pipeline dispatch followed by inventory-dependent storage.

    This is a bounded physical scenario, not an optimization or a gas-price solve.
    Interregional flows cancel exactly in the national aggregation.
    """
    from energy_balance import storage_step
    positive(days, 'days', False)
    balances = {}
    for n in nodes:
        if n['id'] in balances:
            raise ValueError('Duplicate gas region')
        balances[n['id']] = n['production'] + n.get('imports', 0) - n['demand'] - n.get('exports', 0)
    flows = []
    for e in edges:
        if e['from'] not in balances or e['to'] not in balances or e['from'] == e['to']:
            raise ValueError('Pipeline endpoints must name distinct regions')
        positive(e['capacity'], 'pipeline capacity')
        outage = share(e.get('outage_fraction', 0), 'pipeline outage')
        flow = min(positive(e['scheduled_flow'], 'pipeline flow'), e['capacity']*(1-outage))
        balances[e['from']] -= flow
        balances[e['to']] += flow
        flows.append({**e, 'flow': flow, 'curtailed': e['scheduled_flow']-flow})
    rows = []
    for n in nodes:
        fraction = max(0, min(1, (n['storage']-n['minimum']) / (n['capacity']-n['minimum']))) if n['capacity'] > n['minimum'] else 0
        withdrawal = n['max_withdrawal'] * math.sqrt(fraction)
        injection = n['max_injection'] * math.sqrt(1-fraction)
        result = storage_step(n['storage'], balances[n['id']], days, n['capacity'], n['minimum'], injection, withdrawal)
        rows.append({'region': n['id'], 'balance_bcf_day': balances[n['id']],
                     'withdrawal_limit_bcf_day': withdrawal, 'injection_limit_bcf_day': injection, **result})
    return {'regions': rows, 'pipelines': flows,
            'national_balance_bcf_day': sum(balances.values()), 'included_in_national_balance': False}


def lng_feedgas(train, period, utilization, outage_fraction=0, ramp_months=6, fuel_fraction=.08):
    share(utilization, 'LNG utilization')
    share(outage_fraction, 'LNG outage')
    share(fuel_fraction, 'liquefaction fuel')
    positive(ramp_months, 'ramp months', False)
    if fuel_fraction == 1:
        raise ValueError('Liquefaction fuel must be below 100%')
    start = train.get('start_period')
    if not start or period < start:
        return {'output_bcf_day': 0, 'feedgas_bcf_day': 0, 'status': 'not_operating_or_undated'}
    y, m = map(int, period.split('-'))
    sy, sm = map(int, start.split('-'))
    ramp = min(1, ((y-sy)*12+m-sm+1)/ramp_months)
    output = positive(train['baseload_bcf_day'], 'baseload') * ramp * utilization * (1-outage_fraction)
    return {'output_bcf_day': output, 'feedgas_bcf_day': output/(1-fuel_fraction),
            'ramp': ramp, 'status': 'reported_capacity_assumed_operations'}


def hourly_dispatch(hours, fleet, gas_price, carbon_price=0, contract=None):
    """Representative-hour merit order, including scarcity and contract exposure.

    Hour weights must be provided by the caller. Load/profile and congestion
    provenance are preserved; this does not infer a nodal LMP from annual totals.
    """
    if not hours:
        return {'status': 'hourly_load_unavailable', 'rows': []}
    result = []
    for hour in hours:
        load = positive(hour['load_mw'], 'load')
        renewables = positive(hour.get('renewable_mw', 0), 'renewable generation')
        remaining = max(0, load-renewables)
        units = []
        for unit in fleet:
            marginal = (gas_price * unit.get('heat_rate', 0) + unit['variable_cost'] +
                        carbon_price*unit.get('co2_t_mwh', 0))
            capacity = unit['capacity_mw']*share(unit['availability'], 'generation availability')
            units.append((marginal, capacity, unit))
        dispatch, fuel, clearing = {}, 0, 0
        for cost, capacity, unit in sorted(units, key=lambda v: v[0]):
            mw = min(remaining, capacity)
            dispatch[unit['id']] = mw
            if mw:
                clearing = cost
            remaining -= mw
            fuel += mw*unit.get('heat_rate', 0)
        if remaining > 0:
            clearing = hour.get('scarcity_price', 5000)
        merchant = clearing+hour.get('congestion_usd_mwh', 0)
        tariff = merchant
        if contract:
            fraction = share(contract['fixed_fraction'], 'fixed contract fraction')
            tariff = fraction*contract['fixed_usd_mwh']+(1-fraction)*merchant+contract.get('delivery_usd_mwh', 0)
        result.append({**hour, 'dispatch_mw': dispatch, 'unserved_mw': remaining,
                       'curtailed_renewable_mw': max(0, renewables-load),
                       'gas_mmbtu': fuel, 'merchant_usd_mwh': merchant, 'delivered_usd_mwh': tariff,
                       'residual_mw': load-min(load, renewables)-sum(dispatch.values())-remaining})
    weight = sum(positive(h['weight_hours'], 'hour weight', False) for h in result)
    return {'status': 'conditional_dispatch', 'rows': result,
            'weighted_delivered_usd_mwh': sum(r['delivered_usd_mwh']*r['weight_hours'] for r in result)/weight,
            'unserved_mwh': sum(r['unserved_mw']*r['weight_hours'] for r in result),
            'gas_mmbtu': sum(r['gas_mmbtu']*r['weight_hours'] for r in result)}


def cost_curve(assets, total_production=None):
    """Comparable production-weighted costs; a sample never becomes a world curve."""
    groups = {}
    for asset in assets:
        for kind in ('cash', 'sustaining', 'new_project', 'required_return'):
            cost = asset.get(kind)
            if cost is None:
                continue
            # Byproduct credits can make a reported cash cost negative.
            if not finite(cost):
                raise ValueError('Cost must be finite')
            weight = positive(asset['production'], 'production', False)
            key = (kind, asset['unit'], asset['currency'], asset['period'], asset['byproduct_basis'])
            groups.setdefault(key, []).append((cost, weight, asset['id']))
    output = []
    for key, values in groups.items():
        weight = sum(v[1] for v in values)
        quantiles = {}
        for q in (.1, .5, .9):
            acc = 0
            for value, w, _ in sorted(values):
                acc += w
                if acc >= q*weight:
                    quantiles[f'p{int(q*100)}'] = value
                    break
        denominator = (total_production or {}).get('|'.join(key[1:]))
        output.append(dict(zip(('kind', 'unit', 'currency', 'period', 'byproduct_basis'), key),
                           sample_production=weight, sample_assets=len(values),
                           weighted_average=sum(c*w for c, w, _ in values)/weight,
                           sample_quantiles=quantiles,
                           coverage_pct=100*weight/denominator if denominator else None,
                           universe='disclosed_sample', global_percentiles=False))
    return output
