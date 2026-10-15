"""Monthly gas conservation and explicitly conditional physical scenarios."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean

from energy_common import available_records, finite, interpolate, month_days, months, next_month

REQUIRED = ('dry_production', 'pipeline_imports', 'lng_imports', 'pipeline_exports', 'lng_exports',
            'consumption', 'residential', 'commercial', 'industrial', 'power_burn', 'working_storage')
COMPONENTS = ('residential', 'commercial', 'industrial', 'power_burn', 'other_consumption')


def history_rows(panel: dict, as_of: date) -> list[dict]:
    series = panel['series']
    missing = [key for key in REQUIRED if key not in series]
    if missing:
        raise ValueError(f'Missing required gas histories: {missing}')
    maps = {key: {r['period']: r['value'] for r in available_records(series[key], as_of)} for key in REQUIRED}
    periods = sorted(set.intersection(*(set(values) for values in maps.values())))
    rows = []
    for period in periods:
        row = {'period': period, 'status': 'observed_revised', 'days': month_days(period),
               **{key: values[period] for key, values in maps.items()}}
        row['other_consumption'] = row['consumption'] - sum(row[key] for key in COMPONENTS[:-1])
        row['supply_bcf_day'] = row['dry_production'] + row['pipeline_imports'] + row['lng_imports']
        row['demand_bcf_day'] = row['consumption'] + row['pipeline_exports'] + row['lng_exports']
        row['balance_bcf_day'] = row['supply_bcf_day'] - row['demand_bcf_day']
        row['statistical_difference_bcf'] = None
        if rows and period == next_month(rows[-1]['period']):
            row['statistical_difference_bcf'] = row['working_storage'] - rows[-1]['working_storage'] - row['balance_bcf_day'] * row['days']
        rows.append(row)
    if len(rows) < 24:
        raise ValueError('At least 24 overlapping monthly source observations are required')
    return rows


def seasonal_factors(history: list[dict], key: str, years=5) -> dict[int, float]:
    """Day-weighted seasonal ratios of daily rates, using only prior history."""
    cutoff = int(history[-1]['period'][:4]) - years
    sample = [r for r in history if int(r['period'][:4]) >= cutoff]
    average = sum(r[key] * r['days'] for r in sample) / sum(r['days'] for r in sample)
    groups = defaultdict(list)
    for row in sample:
        groups[int(row['period'][5:7])].append(row[key])
    if average <= 0:
        return {m: 1.0 for m in range(1, 13)}
    values = {m: mean(groups[m]) / average if groups[m] else 1.0 for m in range(1, 13)}
    normalizer = sum(values[m] * month_days(f'2025-{m:02d}') for m in range(1, 13)) / 365
    return {m: v / normalizer for m, v in values.items()}


def storage_step(start: float, balance: float, days: int, capacity: float, minimum: float,
                 injection_limit: float, withdrawal_limit: float) -> dict:
    """Conserve mass. Shortfall/spill remain explicit after operational limits."""
    start = finite(start, 'starting storage', 0)
    capacity = finite(capacity, 'capacity', 0)
    minimum = finite(minimum, 'minimum storage', 0, capacity)
    if start > capacity or start < minimum:
        raise ValueError('Starting working gas must lie within the configured operating bounds; check source identity and units')
    injection_limit = finite(injection_limit, 'injection limit', 0)
    withdrawal_limit = finite(withdrawal_limit, 'withdrawal limit', 0)
    balance = finite(balance, 'balance')
    if days <= 0:
        raise ValueError('days must be positive')
    desired = balance * days
    if desired >= 0:
        change = min(desired, injection_limit * days, max(capacity - start, 0))
        spill, shortfall = desired - change, 0.0
    else:
        available = max(start - minimum, 0)
        change = -min(-desired, withdrawal_limit * days, available)
        spill, shortfall = 0.0, -desired + change
    end = start + change
    return {'working_storage': end, 'storage_change_bcf': change,
            'unmet_demand_bcf': shortfall, 'excess_supply_bcf': spill,
            'unconstrained_storage': start + desired,
            'conservation_error_bcf': end - start - desired - shortfall + spill}


def forecast(history: list[dict], config: dict, scenario: dict) -> list[dict]:
    reference = config['reference']
    baseline = reference['annual_2027']
    factors = {key: seasonal_factors(history, key) for key in (*COMPONENTS, 'pipeline_imports', 'pipeline_exports', 'lng_exports')}
    storage = history[-1]['working_storage']
    limits = config['storage']
    result = []
    for period in months(next_month(history[-1]['period']), config['forecast_end']):
        year, month = map(int, period.split('-'))
        days = month_days(period)
        quarter = f'{year}-Q{(month - 1) // 3 + 1}'
        published = reference['quarterly'].get(quarter)
        row = {'period': period, 'days': days, 'status': 'scenario', 'reference_status': 'published_forecast' if published else 'analyst_extension'}
        if published:
            qmonths = range(((month - 1) // 3) * 3 + 1, ((month - 1) // 3) * 3 + 4)
            for key, value in published.items():
                if key in factors:
                    qmean = sum(factors[key][m] * month_days(f'{year}-{m:02d}') for m in qmonths) / sum(month_days(f'{year}-{m:02d}') for m in qmonths)
                    row[key] = value * factors[key][month] / qmean
                else:
                    row[key] = value
        else:
            progress = max(0, min(1, ((year - 2027) * 12 + month - 12) / 36))
            after = max(0, year - 2030 + (month - 12) / 12)
            for key, value in baseline.items():
                target = scenario['terminal_2030'].get(key, value)
                # Production and LNG are December exit rates. Other sector
                # anchors are annualized rates with a seasonal profile.
                if key == 'lng_exports':
                    target /= factors[key][12]
                start = reference['quarterly']['2027-Q4'][key] if key == 'dry_production' else value
                rate = start + (target - start) * progress
                growth = scenario['post2030_production_growth'] if key == 'dry_production' else scenario['post2030_demand_growth']
                if key in ('supplemental_supply', 'lng_imports', 'pipeline_imports'):
                    growth = 0
                rate *= (1 + growth) ** after
                row[key] = rate * factors[key][month] if key in factors else rate
        if month in (12, 1, 2):
            for key in ('residential', 'commercial'):
                row[key] *= 1 + scenario['winter_demand_pct'] / 100
            row['dry_production'] *= 1 - scenario['supply_disruption_pct'] / 100
        if month in (6, 7, 8):
            row['power_burn'] *= 1 + scenario['summer_power_pct'] / 100
        row['consumption'] = sum(row[key] for key in COMPONENTS)
        row['supply_bcf_day'] = row['dry_production'] + row['pipeline_imports'] + row['lng_imports'] + row['supplemental_supply']
        row['demand_bcf_day'] = row['consumption'] + row['pipeline_exports'] + row['lng_exports']
        row['balance_bcf_day'] = row['supply_bcf_day'] - row['demand_bcf_day']
        # No fitted reconciliation term is carried into the forecast.
        row['statistical_difference_bcf'] = 0.0
        row['capacity_bcf'] = interpolate({'2026': limits['working_capacity_bcf'], '2030': limits['capacity_2030_bcf']}, year + (month - 1) / 12)
        row['operating_minimum_bcf'] = limits['operating_minimum_bcf']
        row.update(storage_step(storage, row['balance_bcf_day'], days, row['capacity_bcf'], limits['operating_minimum_bcf'], limits['max_injection_bcf_day'], limits['max_withdrawal_bcf_day']))
        storage = row['working_storage']
        row['henry_hub_usd_mmbtu'] = interpolate(scenario['gas_price'], year + (month - 6.5) / 12)
        result.append({k: round(v, 8) if isinstance(v, float) else v for k, v in row.items()})
    return result


def summarize(rows: list[dict]) -> dict:
    shortfalls = [r for r in rows if r['unmet_demand_bcf'] > 0.01]
    annual = []
    for year in sorted({r['period'][:4] for r in rows}):
        sample = [r for r in rows if r['period'].startswith(year)]
        days = sum(r['days'] for r in sample)
        annual.append({'year': int(year), 'months': len(sample), 'partial_year': len(sample) != 12,
                       'dry_production_bcf_day': sum(r['dry_production'] * r['days'] for r in sample) / days,
                       'lng_exports_bcf_day': sum(r['lng_exports'] * r['days'] for r in sample) / days,
                       'power_burn_bcf_day': sum(r['power_burn'] * r['days'] for r in sample) / days,
                       'balance_bcf_day': sum(r['balance_bcf_day'] * r['days'] for r in sample) / days,
                       'ending_storage_bcf': sample[-1]['working_storage'],
                       'unmet_demand_bcf': sum(r['unmet_demand_bcf'] for r in sample),
                       'excess_supply_bcf': sum(r['excess_supply_bcf'] for r in sample)})
    return {'first_shortfall': shortfalls[0]['period'] if shortfalls else None,
            'minimum_storage_bcf': min(r['working_storage'] for r in rows),
            'unmet_demand_bcf': sum(r['unmet_demand_bcf'] for r in rows),
            'annual': annual}


def historical_validation(history: list[dict]) -> dict:
    residuals = [r['statistical_difference_bcf'] for r in history if r['statistical_difference_bcf'] is not None]
    # Baseline-only rolling test: predict next-year same-month storage. It is a
    # yardstick, not evidence that the structural forecast has predictive skill.
    lookup = {r['period']: r for r in history}
    errors = []
    for row in history:
        prior = f"{int(row['period'][:4]) - 1}{row['period'][4:]}"
        if prior in lookup:
            errors.append(abs(row['working_storage'] - lookup[prior]['working_storage']))
    return {'history_basis': 'retrospective_revised_history', 'n_months': len(history),
            'statistical_difference_mae_bcf': mean(abs(v) for v in residuals),
            'statistical_difference_max_abs_bcf': max(abs(v) for v in residuals),
            'seasonal_naive_storage_mae_bcf': mean(errors) if errors else None,
            'forecast_skill_status': 'unvalidated',
            'note': 'Statistical differences are published explicitly, not fitted away. Seasonal error is a benchmark only. True vintage holdout evaluation starts with retained snapshots.'}
