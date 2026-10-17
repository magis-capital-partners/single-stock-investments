"""Optional gas-to-mining sensitivity; never changes BTC demand or valuation."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from energy_common import ROOT, finite, month_end
from power_cost_model import contract_cost

CRYPTO = ROOT / '_system/reference/market-data/crypto'


def latest_csv(path: Path, as_of: date):
    if not path.exists():
        return None
    with path.open(encoding='utf-8-sig') as stream:
        records = [(r['date'], float(r['value'])) for r in csv.DictReader(stream)
                   if r.get('date', '9999') <= as_of.isoformat() and r.get('value')]
    records = sorted((d, v) for d, v in records if v > 0)
    return records[-1] if records else None


def subsidy_at(day: date) -> float:
    # Future dates are estimates; policy is consensus subsidy by block height.
    events = [(date(2012, 11, 28), 25), (date(2016, 7, 9), 12.5),
              (date(2020, 5, 11), 6.25), (date(2024, 4, 20), 3.125),
              (date(2028, 4, 15), 1.5625), (date(2032, 4, 20), 0.78125)]
    value = 50.0
    for when, amount in events:
        if day >= when:
            value = amount
    return value


def month_issuance(period: str) -> float:
    end = month_end(period)
    return sum(144 * subsidy_at(date(end.year, end.month, d)) for d in range(1, end.day + 1)) / end.day


def electricity_kwh_day(hash_eh: float, effective_j_th: float) -> float:
    """EH/s -> TH/s -> W -> kWh/day. Efficiency includes PUE exactly once."""
    return finite(hash_eh, 'active hashrate', 0) * finite(effective_j_th, 'effective J/TH', 0) * 24000


def cost_layers(electricity_daily: float, other_daily: float, issuance_daily: float,
                btc_price: float, fee_daily: float, opex_share=0.5) -> dict:
    if issuance_daily <= 0:
        raise ValueError('issuance must be positive')
    total = electricity_daily + other_daily
    operating = electricity_daily + other_daily * opex_share
    revenue = issuance_daily * btc_price + fee_daily
    return {'electricity_cost_usd_btc': electricity_daily / issuance_daily,
            'other_cost_usd_btc': other_daily / issuance_daily,
            'operating_cost_usd_btc': operating / issuance_daily,
            'total_cost_usd_btc': total / issuance_daily,
            'cash_margin_daily_usd': revenue - operating,
            'economic_margin_daily_usd': revenue - total,
            'revenue_breakeven_btc_usd': max(0, total - fee_daily) / issuance_daily}


def snapshot(as_of: date, config: dict, crypto_dir=CRYPTO) -> dict:
    names = {'btc_usd': 'btc_spot_usd', 'hash_eh': 'btc_hash_rate_eh', 'fleet_jth': 'btc_fleet_jth',
             'legacy_all_in': 'btc_all_in_cost_usd', 'fee_per_block_usd': 'btc_avg_fee_per_block_usd'}
    values = {key: latest_csv(crypto_dir / f'{name}.csv', as_of) for key, name in names.items()}
    required = [key for key in names if key != 'fee_per_block_usd']
    missing = [key for key in required if values[key] is None]
    if missing:
        return {'available': False, 'reason': f'Missing BTC inputs: {", ".join(missing)}'}
    age = max((as_of - date.fromisoformat(values[key][0])).days for key in required)
    if age > config['btc']['max_crypto_age_days']:
        return {'available': False, 'reason': f'BTC inputs are {age} days old; energy comparison requires a refreshed snapshot.', 'age_days': age}
    # All series are independently dated, not assigned a fabricated common date.
    data = {key: value[1] if value else 0 for key, value in values.items()}
    data.update({'available': True, 'dates': {key: value[0] if value else None for key, value in values.items()},
                 'as_of': as_of.isoformat(), 'age_days': age,
                 'fees_status': 'observed' if values['fee_per_block_usd'] else 'assumed_zero_missing'})
    power_daily = electricity_kwh_day(data['hash_eh'], data['fleet_jth']) * config['btc']['baseline_usd_kwh']
    total_daily = data['legacy_all_in'] * 144 * subsidy_at(as_of)
    if total_daily < power_daily:
        return {'available': False, 'reason': 'BTC inputs disagree: legacy total cost is below reconstructed electricity cost.'}
    data['other_daily_usd'] = total_daily - power_daily
    data['power_daily_usd'] = power_daily
    data['other_cost_basis'] = 'Daily residual calibrated from legacy HK total; operating/capital split is assumed.'
    return data


def bridge_path(power_path: list[dict], config: dict, snap: dict, *, dynamic=False) -> list[dict]:
    if not snap.get('available'):
        return []
    cohorts = config['miner_cohorts']
    if abs(sum(c['hash_share'] for c in cohorts) - 1) > 1e-8:
        raise ValueError('miner cohort hashrate shares must sum to one')
    params = config['btc']
    as_of = date.fromisoformat(snap['as_of'])
    baseline = params['baseline_usd_kwh']
    # Normalize relative efficiency so weighted baseline exactly matches the
    # observed aggregate, rather than quietly changing watts when adding cohorts.
    efficiency_normalizer = sum(c['hash_share'] * c['efficiency_factor'] for c in cohorts)
    rows = []
    for point in power_path:
        period = point['period']
        if period < as_of.isoformat()[:7]:
            continue
        day = month_end(period)
        years = max(0, (day - as_of).days / 365.25)
        network_hash = snap['hash_eh'] * (1 + params['annual_hash_growth']) ** years
        fleet_jth = snap['fleet_jth'] * (1 - params['annual_efficiency_improvement']) ** years
        issuance = month_issuance(period)
        other_daily = snap['other_daily_usd'] * (1 + params['annual_nonpower_inflation']) ** years
        fees = 144 * snap['fee_per_block_usd']
        region_lookup = {r['region']: r for r in point['regions']}
        details = []
        for cohort in cohorts:
            contract = contract_cost(cohort, region_lookup[cohort['region']], period, baseline)
            effective_jth = fleet_jth * cohort['efficiency_factor'] / efficiency_normalizer
            active_hash = network_hash * cohort['hash_share']
            # Observed hashrate is already realized. Availability is displayed
            # and used for installed-capacity inference only, not multiplied twice.
            energy = electricity_kwh_day(active_hash, effective_jth)
            details.append({'id': cohort['id'], 'label': cohort['label'], 'region': cohort['region'],
                            'status': cohort['status'], 'hash_share': cohort['hash_share'],
                            'active_hash_eh': active_hash, 'effective_j_th': effective_jth,
                            'kwh_day': energy, 'electricity_daily_usd': energy * contract['effective_usd_kwh'],
                            **contract})
        energy_total = sum(c['kwh_day'] for c in details)
        power_daily = sum(c['electricity_daily_usd'] for c in details)
        linked = cost_layers(power_daily, other_daily, issuance, snap['btc_usd'], fees, params['nonpower_opex_share'])
        base = cost_layers(energy_total * baseline, other_daily, issuance, snap['btc_usd'], fees, params['nonpower_opex_share'])
        row = {'period': period, 'status': 'conditional_sensitivity', 'network_hash_eh': network_hash,
               'fleet_jth_including_pue': fleet_jth, 'issued_btc_per_day': issuance,
               'btc_price_assumption_usd': snap['btc_usd'], 'fee_daily_usd': fees,
               'effective_power_usd_kwh': power_daily / energy_total,
               'baseline_total_cost_usd_btc': base['total_cost_usd_btc'],
               'legacy_fixed_share_cost_usd_btc': power_daily / params['baseline_power_share'] / issuance,
               'cost_delta_usd_btc': linked['total_cost_usd_btc'] - base['total_cost_usd_btc'],
               'cost_delta_pct': 100 * (linked['total_cost_usd_btc'] / base['total_cost_usd_btc'] - 1),
               'hashprice_usd_ph_day': (issuance * snap['btc_usd'] + fees) / (network_hash * 1000),
               'cohorts': details, **linked}
        if dynamic:
            row['network_response'] = network_response(details, network_hash, issuance, snap['btc_usd'], fees,
                                                        other_daily * params['nonpower_opex_share'])
        rows.append(row)
    return rows


def network_response(cohorts: list[dict], reference_hash: float, issuance: float,
                     btc_price: float, fee_daily: float, other_opex_daily: float) -> dict:
    """Illustrative immediate shutdown and post-retarget survivor economics.

    This two-state experiment does not claim to predict the path or timing of
    difficulty. All open cohorts face the same network revenue per hash.
    """
    reference_revenue = issuance * btc_price + fee_daily
    active = []
    for cohort in cohorts:
        revenue = reference_revenue * cohort['hash_share']
        avoidable_cost = cohort['electricity_daily_usd'] + other_opex_daily * cohort['hash_share']
        if revenue >= avoidable_cost:
            active.append(cohort)
    surviving_hash = sum(c['active_hash_eh'] for c in active)
    share = surviving_hash / reference_hash if reference_hash else 0
    return {'status': 'illustrative_shutdown_sensitivity', 'active_hash_share': share,
            'curtailed_hash_share': 1 - share,
            'immediate_blocks_per_day': 144 * share,
            'immediate_issued_btc_per_day': issuance * share,
            'after_retarget_blocks_per_day': 144 if share > 0 else 0,
            'survivor_revenue_multiplier_after_retarget': 1 / share if share > 0 else None,
            'surviving_cohorts': [c['id'] for c in active],
            'note': 'Conditional two-state experiment, no re-entry or migration forecast. Retarget timing and partial curtailment require finer data.'}
