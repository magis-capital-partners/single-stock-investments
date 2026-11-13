"""Publication contract for detailed commodity evidence and cash sensitivities."""
from commodity_common import finite
from commodity_observations import IDENTITY, unpack


def validate(doc, as_of):
    errors = []
    if doc.get('schema_version') != 'commodity_resolution.v1':
        errors.append('resolution: unknown schema')
    if doc.get('in_base_irr') is not False or doc.get('valuation_authority') != 'none':
        errors.append('resolution: valuation boundary')
    source_ids = {s['id'] for s in doc.get('sources', [])}
    ids = set()
    for r in unpack(doc):
        if not all(k in r for k in IDENTITY) or not finite(r['value']):
            errors.append('resolution: invalid observation identity/value')
        if r['id'] in ids:
            errors.append('resolution: duplicate observation')
        ids.add(r['id'])
        if r['known_at'][:10] > as_of or (r.get('published_at') or '')[:10] > as_of:
            errors.append('resolution: future availability leakage')
        if r['source_id'] not in source_ids or not r['source_url'].startswith('https://'):
            errors.append('resolution: missing original source')
    for name, readiness in doc.get('readiness', {}).items():
        weight = sum(i['weight'] for i in readiness['items'])
        actual = 100*sum(i['weight'] for i in readiness['items'] if i['ready'])/weight
        if abs(actual-readiness['weighted_pct']) > .051:
            errors.append(f'resolution: {name} weighted coverage')
        if readiness['core_ready'] != all(i['ready'] for i in readiness['items'] if i['core']):
            errors.append(f'resolution: {name} core readiness')
    for c in doc.get('companies', []):
        if c['in_base_irr'] is not False or c['valuation_authority'] != 'none':
            errors.append('resolution: company valuation boundary')
        if any(abs(v) > 1 for v in c['reconciliation_usd'].values()):
            errors.append('resolution: company disclosure reconciliation')
        if c['revenue_sensitivity_coverage_pct'] < 90:
            errors.append('resolution: pilot revenue coverage below 90%')
    for s in doc.get('solar', {}).get('scenarios', []):
        for r in s['rows']:
            if abs(r['supply_moz']-r['demand_moz']-r['etp_moz']-r['balance_less_etp_moz']) > .001:
                errors.append('resolution: silver physical balance')
    return sorted(set(errors))
