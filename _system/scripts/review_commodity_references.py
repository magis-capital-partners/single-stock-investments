"""Promote validated publisher tables into the existing reviewed scenario anchors.

Explicit command, separate from collection: a fetch never silently overwrites a
scenario coefficient or approved valuation. Monthly rates are day-weighted;
quarter-end stocks are not averaged.
"""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone

from commodity_common import CONFIG_DIR, ROOT, load, save
from commodity_observations import available, unpack
from commodity_resolution import DATA


def promote(as_of=None):
    as_of = as_of or datetime.now(timezone.utc).date()
    inputs = load(DATA/'resolution_inputs.json')
    rows = available(unpack(inputs), as_of)
    sources = {s['id']: s for s in inputs['sources']}
    eia = sources['steo_monthly']
    if eia.get('error'):
        raise ValueError('Cannot review a failed source refresh')
    values = {(r['metric'], r['period']): r['value'] for r in rows if r['source_id'] == eia['id']}
    def quarter(code, year, q, stock=False):
        periods = [f'{year}-{m:02d}' for m in range(q*3-2, q*3+1)]
        if stock:
            return values[code, periods[-1]]
        days = [calendar.monthrange(year, int(p[5:]))[1] for p in periods]
        return sum(values[code, p]*d for p, d in zip(periods, days))/sum(days)
    crude = load(CONFIG_DIR/'crude.json')
    mapping = {'production_mbd': 'papr_world', 'consumption_mbd': 'patc_world',
               'opec_mbd': 'papr_opec', 'oecd_consumption_mbd': 'patc_oecd',
               'oecd_stock_mb': 'pasc_oecd_t3', 'brent': 'BREPUUS', 'wti': 'WTIPUUS'}
    for r in crude['reference']['quarterly']:
        y, q = int(r['period'][:4]), int(r['period'][-1])
        if (mapping['production_mbd'], f'{y}-{q*3:02d}') not in values:
            continue
        for key, code in mapping.items():
            r[key] = round(quarter(code, y, q, key == 'oecd_stock_mb'), 2 if key in ('brent', 'wti') else 4)
        r['world_draw_mbd'] = round(r['consumption_mbd']-r['production_mbd'], 4)
    # The forecast beginning stays Q4 for compatibility; inventory starts at Q3 end.
    crude['reference']['starting_oecd_stock_mb'] = quarter('pasc_oecd_t3', 2026, 3, True)
    for src in crude['sources']:
        if src['id'].startswith('eia_oil_'):
            src.update(url=eia['url'], published_at=eia['published_at'], sha256=eia['sha256'],
                       reviewed_at=str(as_of), label=f"EIA STEO {eia['published_at']} · validated monthly workbook")
    save(CONFIG_DIR/'crude.json', crude)
    energy_path = ROOT/'_system/scripts/energy_model_config.json'
    energy = load(energy_path)
    ref = energy['reference']
    gas = {'dry_production': 'NGPRPUS', 'lng_exports': 'NGEXPUS_LNG',
           'lng_imports': 'NGIMPUS_LNG', 'pipeline_imports': 'NGIMPUS_PIPE',
           'pipeline_exports': 'NGEXPUS_PIPE', 'supplemental_supply': 'NGSFPUS',
           'residential': 'NGRCPUS', 'commercial': 'NGCCPUS', 'industrial': 'NGINX', 'power_burn': 'NGEPCON'}
    for period in ref['quarterly']:
        y, q = int(period[:4]), int(period[-1])
        ref['quarterly'][period] = {k: quarter(code, y, q) for k, code in gas.items()}
        ref['quarterly'][period]['other_consumption'] = sum(quarter(code, y, q) for code in ('NGLPPUS', 'NGACPUS', 'NGVHPUS'))
    weights = [sum(calendar.monthrange(2027, m)[1] for m in range(q*3-2, q*3+1)) for q in range(1, 5)]
    for key in ref['annual_2027']:
        ref['annual_2027'][key] = sum(ref['quarterly'][f'2027-Q{q}'][key]*weights[q-1] for q in range(1, 5))/365
    ref.update(published_at=eia['published_at'], source_url=eia['url'], price_source_url=eia['url'],
               label=f"EIA STEO {eia['published_at']}", reviewed_at=str(as_of),
               supply_source_sha256=eia['sha256'], prices_source_sha256=eia['sha256'])
    ref['henry_hub_usd_mmbtu'] = {str(y): sum(quarter('NGHHUUS', y, q)*sum(calendar.monthrange(y, m)[1] for m in range(q*3-2, q*3+1)) for q in range(1, 5))/(366 if calendar.isleap(y) else 365) for y in (2026, 2027)}
    save(energy_path, energy)
    gold = load(CONFIG_DIR/'gold.json')
    wgc = sources['wgc_quarterly']
    gold['sources'] = [s for s in gold['sources'] if s['id'] not in ('wgc_q3', 'wgc_latest')]
    latest = max(r['period'] for r in rows if r['source_id'] == wgc['id'])
    gold['sources'].append({'id': 'wgc_latest', 'label': f'WGC Gold Demand Trends {latest}',
                            'url': wgc['url'], 'published_at': wgc['published_at'], 'max_age_days': 120,
                            'required': True, 'capture_kind': 'publisher_bytes', 'sha256': wgc['sha256'], 'reviewed_at': str(as_of)})
    latest_values = {r['metric']: r['value'] for r in rows if r['source_id'] == wgc['id'] and r['period'] == latest}
    gold['reference'].update(latest_quarter={'period': latest, **latest_values}, price_usd_oz=latest_values['price'], price_period=latest)
    if not any(r['period'] == latest for r in gold['reference']['history']):
        gold['reference']['history'].append({'period': latest, 'price': latest_values['price'], 'basis': 'published_history'})
    from bs4 import BeautifulSoup
    panel = load(ROOT/'_private/commodity/observations.json', {})
    if panel:
        panel.setdefault('sources', {})['wgc_latest'] = {'url': wgc['url'], 'resolved_url': wgc['url'],
            'sha256': wgc['sha256'], 'fetched_at': wgc['retrieved_at'], 'status': 'fetched'}
        save(ROOT/'_private/commodity/observations.json', panel)
    captured_stock = panel.get('sources', {}).get('wgc_stock')
    if captured_stock and captured_stock['status'] == 'fetched':
        body = (ROOT/'_private/commodity/objects'/captured_stock['sha256']).read_bytes()
        soup = BeautifulSoup(body, 'html.parser')
        text = soup.get_text(' ', strip=True)
        total = re.search(r'Total above-ground stock \(end-Q([1-4]) (20\d{2})\): ([\d,]+) tonnes', text)
        if not total:
            raise ValueError('WGC above-ground stock anchor changed format')
        labels = {'jewellery': 'Jewellery', 'central_banks': 'Central banks', 'bars_coins': 'Bars and coins:',
                  'etf': 'Gold ETFs:', 'otc': 'OTC:', 'other': 'Other:'}
        categories = {}
        for key, label in labels.items():
            match = re.search(re.escape(label)+r'\s*~([\d,]+)t', text)
            if not match:
                raise ValueError(f'Missing WGC stock category: {key}')
            categories[key] = float(match[1].replace(',', ''))
        stock = float(total[3].replace(',', ''))
        if abs(sum(categories.values())-stock) > 100:
            raise ValueError('WGC rounded above-ground categories do not reconcile')
        y, month = int(total[2]), int(total[1])*3
        gold['reference'].update(above_ground_t=stock, stock_date=f'{y}-{month:02d}-{calendar.monthrange(y,month)[1]}', stock_categories_t=categories)
        published = datetime.strptime(soup.find('time').get_text(' ', strip=True), '%d %B, %Y').replace(tzinfo=timezone.utc).date().isoformat()
        for src in gold['sources']:
            if src['id'] == 'wgc_stock':
                src.update(sha256=captured_stock['sha256'], published_at=published, reviewed_at=str(as_of))
            if src['id'] == 'wgc_q2':
                src['required'] = False
    save(CONFIG_DIR/'gold.json', gold)
    print('Reviewed monthly EIA oil/gas anchors and Q3 gold composition; scenario coefficients unchanged')


if __name__ == '__main__':
    promote()
