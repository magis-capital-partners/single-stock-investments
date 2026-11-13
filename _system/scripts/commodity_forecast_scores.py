"""Rolling-origin evaluation with availability checks and explicit benchmarks."""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

from commodity_observations import available


def shift(period, months):
    year, month = map(int, period[:7].split('-'))
    n = year * 12 + month - 1 + months
    return f'{n // 12:04d}-{n % 12 + 1:02d}'


def score(rows, forecasts=(), horizons=(1, 3, 6, 12)):
    """Only score genuinely archived forecasts, never fit today's assumptions backward.

    Actuals use latest revised values; this choice is exposed in the result.
    Seasonal baseline repeats the last known value for the target calendar month.
    """
    observations = [r for r in rows if r['frequency'] == 'monthly' and r['basis'].startswith('observed')]
    groups = defaultdict(list)
    for r in observations:
        groups[(r['commodity'], r['metric'], r['region'], r['unit'])].append(r)
    samples = []
    for identity, history in groups.items():
        actual = {r['period'][:7]: r for r in sorted(history, key=lambda r: r['known_at'])}
        # Availability months, rather than economic observation months, are origins.
        origins = sorted({r['known_at'][:7] for r in history})
        for origin in origins:
            known = sorted(available(history, origin + '-28', observed_only=True), key=lambda r: r['period'])
            if not known:
                continue
            for horizon in horizons:
                target = shift(origin, horizon)
                if target not in actual:
                    continue
                predictions = {'no_change': known[-1]['value']}
                seasonal = [r for r in known if r['period'][5:7] == target[5:7] and r['period'][:7] <= origin]
                if seasonal:
                    predictions['seasonal'] = seasonal[-1]['value']
                for f in forecasts:
                    if (tuple(f[k] for k in ('commodity', 'metric', 'region', 'unit')) == identity and
                            f['target'] == target and f['origin'] == origin and
                            f['known_at'][:7] <= origin):
                        predictions[f['model']] = f['value']
                for model, value in predictions.items():
                    samples.append({'commodity': identity[0], 'metric': identity[1], 'region': identity[2],
                                    'unit': identity[3], 'origin': origin, 'target': target, 'horizon': horizon,
                                    'model': model, 'error': value - actual[target]['value'],
                                    'regime': '2020_pandemic' if target.startswith('2020') else
                                              '2022_energy_shock' if target.startswith('2022') else 'other'})
    buckets = defaultdict(list)
    for row in samples:
        buckets[tuple(row[k] for k in ('commodity', 'metric', 'region', 'unit', 'horizon', 'model', 'regime'))].append(row['error'])
    summary = [dict(zip(('commodity', 'metric', 'region', 'unit', 'horizon', 'model', 'regime'), k),
                    n=len(v), mae=mean(abs(x) for x in v), rmse=math.sqrt(mean(x*x for x in v)), bias=mean(v))
               for k, v in sorted(buckets.items())]
    return {'status': 'scored' if summary else 'awaiting_archived_origins', 'summary': summary,
            'futures_baseline': 'Requires dated licensed settlement captures; not substituted with current curves.',
            'intervals': 'Named stresses only; probabilities withheld until rolling-origin coverage is measured.',
            'actuals_basis': 'Latest revised realized observations. Overlapping horizons are not independent.',
            'structural_skill': 'unvalidated', 'samples': samples}
