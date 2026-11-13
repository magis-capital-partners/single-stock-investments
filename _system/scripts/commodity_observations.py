"""Point-in-time identities, readiness and publication lineage for physical research.

Retrieval establishes availability for newly captured history. An observation's
economic date is never used as its publication or historical availability date.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from commodity_common import digest, finite

IDENTITY = ('commodity', 'product', 'quality', 'region', 'delivery', 'asset',
            'metric', 'unit', 'currency', 'basis', 'period', 'vintage')
FREQUENCIES = {'hourly', 'daily', 'weekly', 'monthly', 'quarterly', 'annual', 'milestone'}


def period_end(period):
    year = int(period[:4])
    if '-Q' in period:
        month = int(period[-1])*3
    elif len(period) >= 10 and period[7] == '-':
        return date.fromisoformat(period[:10])
    elif len(period) >= 7:
        month = int(period[5:7])
    else:
        month = 12
    return date(year, month, calendar.monthrange(year, month)[1])


def pack(rows):
    """Normalize repeated identity/provenance fields without losing ledger precision."""
    datasets = {}
    for row in rows:
        metadata = {k: v for k, v in row.items() if k not in ('id', 'value', 'period', 'basis')}
        key = digest(metadata)
        datasets.setdefault(key, {**metadata, 'values': []})['values'].append([row['period'], row['value'], row['basis']])
    return list(datasets.values())


def unpack(doc):
    if 'observations' in doc:
        return doc['observations']
    rows = []
    for dataset in doc.get('datasets', []):
        metadata = {k: v for k, v in dataset.items() if k != 'values'}
        for period, value, basis in dataset['values']:
            row = {**metadata, 'period': period, 'value': value, 'basis': basis}
            row['id'] = digest({k: row[k] for k in IDENTITY})[:24]
            rows.append(row)
    return rows


def observation(*, value, source, period, metric, commodity, unit, frequency,
                basis='observed_revised', region='global', product=None, quality='unspecified',
                delivery='unspecified', asset=None, currency=None, **extra):
    if not finite(value):
        raise ValueError('Observation must contain a finite value')
    if frequency not in FREQUENCIES:
        raise ValueError('Unknown observation frequency')
    if currency is None:
        currency = 'USD' if 'usd' in unit.lower() else 'AUD' if 'aud' in unit.lower() else None
    required = ('id', 'url', 'retrieved_at', 'sha256')
    if any(not source.get(k) for k in required):
        raise ValueError('Observation requires original-source provenance')
    known = max(source.get('published_at') or '', source['retrieved_at'], source.get('reviewed_at') or '')
    row = dict(commodity=commodity, product=product or commodity, quality=quality,
               region=region, delivery=delivery, asset=asset, metric=metric, unit=unit,
               currency=currency, basis=basis, period=period, vintage=source['sha256'],
               value=value, frequency=frequency, published_at=source.get('published_at'),
               retrieved_at=source['retrieved_at'], reviewed_at=source.get('reviewed_at'),
               known_at=known, source_id=source['id'], source_url=source['url'],
               source_sha256=source['sha256'], extraction=extra.pop('extraction', 'reviewed_table'),
               transformation=extra.pop('transformation', 'identity'), **extra)
    row['id'] = digest({k: row[k] for k in IDENTITY})[:24]
    return row


def available(rows, as_of, *, observed_only=False):
    cutoff = as_of.isoformat() if isinstance(as_of, date) else str(as_of)
    rows = [r for r in rows if r['known_at'][:10] <= cutoff[:10]
            and (not observed_only or r['basis'].startswith('observed'))]
    latest = {}
    for row in sorted(rows, key=lambda r: (r['known_at'], r['vintage'])):
        key = tuple(row[k] for k in IDENTITY if k != 'vintage')
        latest[key] = row
    return list(latest.values())


def source_state(source, as_of):
    """A missed expected release and a failed fetch are distinct from data age."""
    end = as_of if isinstance(as_of, date) else date.fromisoformat(as_of[:10])
    published = date.fromisoformat((source.get('published_at') or source['retrieved_at'])[:10])
    reviewed = source.get('reviewed_sha256')
    changed = bool(reviewed and reviewed != source.get('sha256'))
    due = source.get('next_release')
    stale = ((end - published).days > source['max_age_days'] or
             bool(due and due < end.isoformat()))
    observation_age = None
    if source.get('latest_observation'):
        period = source['latest_observation']
        observed = period_end(period)
        observation_age = (end-observed).days
        stale = stale or observation_age > source.get('max_observation_age_days', source['max_age_days'])
    state = ('retained_after_failure' if source.get('error') else
             'review_due' if changed else 'overdue' if stale else 'current')
    return {**source, 'age_days': (end - published).days, 'observation_age_days': observation_age, 'state': state,
            'changed_since_review': changed, 'usable': not (stale or changed or source.get('error'))}


def weighted_readiness(requirements, rows, sources, as_of):
    states = {s['id']: source_state(s, as_of) for s in sources}
    usable = available(rows, as_of)
    items = []
    for req in requirements:
        matches = [r for r in usable if all(r.get(k) == v for k, v in req['match'].items())]
        def fresh_observation(r):
            period = r['period']
            end = period_end(period)
            source = states.get(r['source_id'], {})
            return (as_of-end).days <= source.get('max_observation_age_days', source.get('max_age_days', 45))
        observed = [r for r in matches if r['basis'].startswith('observed') and
                    states.get(r['source_id'], {}).get('usable') and fresh_observation(r)]
        title = req.get('title') or req.get('id', req['match'].get('metric', 'Input')).replace('_', ' ')
        if matches:
            latest = max(matches, key=lambda r: r['period'])
            if latest['product'] != latest['commodity']:
                title = latest['product']
        items.append({**req, 'title': title, 'ready': bool(observed),
                      'latest_period': max((r['period'] for r in matches), default=None),
                      'reason': None if observed else req['missing_reason']})
    weight = sum(r['weight'] for r in items)
    return {'weighted_pct': round(100 * sum(r['weight'] for r in items if r['ready']) / weight, 1) if weight else 0,
            'core_ready': all(r['ready'] for r in items if r['core']), 'items': items,
            'basis': 'Decision importance weights; assumptions and stale or unreviewed evidence do not earn coverage.'}


def meaningful_diff(previous, current):
    key = lambda r: tuple(r[k] for k in IDENTITY if k != 'vintage')
    before = {key(r): r for r in previous}
    changes = []
    for row in current:
        old = before.get(key(row))
        if old is None or old['value'] != row['value']:
            changes.append({'id': row['id'], 'commodity': row['commodity'], 'metric': row['metric'],
                            'period': row['period'], 'region': row['region'], 'before': old['value'] if old else None,
                            'after': row['value'], 'change': row['value'] - old['value'] if old else None,
                            'unit': row['unit'], 'source_url': row['source_url'],
                            'kind': 'revision' if old else 'new_observation'})
    return changes


def publication(rows, inputs, as_of):
    model_id = digest({'observations': rows, 'inputs': inputs, 'as_of': str(as_of)})[:20]
    return {'model_id': model_id, 'built_at': datetime.now(timezone.utc).isoformat(),
            'as_of': str(as_of), 'valuation_authority': 'none', 'in_base_irr': False,
            'stages': ['original_publication', 'observations', 'reviewed_inputs', 'calculation',
                       'published_artifact', 'reader'],
            'reader_policy': 'Display served model ID and fetch time. Failed refresh retains prior model with a failure banner.',
            'next_review': (date.fromisoformat(str(as_of)[:10]) + timedelta(days=7)).isoformat()}
