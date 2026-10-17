#!/usr/bin/env python3
"""Normalize public EIA LNG trains and gas generators; retain source provenance."""
from __future__ import annotations

import argparse
import hashlib
import io
import re
from datetime import date, datetime
from urllib.parse import urljoin

from energy_common import ASSET_DIR, atomic_json, load_json, now_iso
from fetch_energy_panel import get_bytes, plain

LNG_PAGE = 'https://www.eia.gov/naturalgas/data.php'
GEN_PAGE = 'https://www.eia.gov/electricity/data/eia860m/'


def workbook(body):
    import openpyxl
    if not body.startswith(b'PK'):
        raise ValueError('Expected an XLSX workbook, received a different response')
    return openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)


def number(value):
    return float(value) if isinstance(value, (int, float)) and value >= 0 else None


def timing(value):
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m'), 'reported_month'
    text = str(value or '').strip()
    year = re.search(r'(?<!\d)(20\d{2})(?!\d)', text)
    if not year:
        return None, 'unknown'
    # Conservative end-of-window date; retain the reported label alongside it.
    quarter = re.search(r'Q([1-4])|([1-4])Q', text, re.I)
    half = re.search(r'([1-2])H|H([1-2])', text, re.I)
    month = int(quarter.group(1) or quarter.group(2)) * 3 if quarter else int(half.group(1) or half.group(2)) * 6 if half else 12
    return f'{year.group(1)}-{month:02d}', 'reported_quarter_end' if quarter else 'reported_half_year_end' if half else 'reported_year_end'


def fetch_lng():
    html = get_bytes(LNG_PAGE).decode(errors='replace')
    links = re.findall(r'href=["\']([^"\']+U\.S\.liquefactioncapacity_(\d{4})_Q([1-4])\.xlsx)["\']', html, re.I)
    eligible = [(url, int(y), int(q)) for url, y, q in links if (int(y), int(q)) <= (date.today().year, (date.today().month - 1) // 3 + 1)]
    if not eligible:
        raise ValueError('No dated EIA LNG capacity workbook found')
    url, _, _ = max(eligible, key=lambda v: (v[1], v[2]))
    url = urljoin(LNG_PAGE, url)
    body = get_bytes(url)
    book = workbook(body)
    published = None
    for row in book['Contents'].iter_rows(values_only=True):
        if any(str(v or '').strip() == 'Release Date:' for v in row):
            published = next((v.date().isoformat() for v in row if isinstance(v, datetime)), None)
    if not published or published > date.today().isoformat():
        raise ValueError('Missing or future LNG workbook publication date')
    trains = []
    project = ''
    for row in book['Existing & Under Construction'].iter_rows(min_row=4, values_only=True):
        capacity = number(row[2])
        if capacity is None or capacity == 0:
            continue
        project = str(row[0] or project).strip()
        start, precision = timing(row[8] or row[7])
        trains.append({'id': f'{project} / {row[1]}', 'project': project, 'train': str(row[1] or ''),
                       'baseload_bcf_day': capacity, 'peak_bcf_day': number(row[4]),
                       'status': str(row[6] or ''), 'start_period': start, 'date_precision': precision,
                       'reported_start': str(row[8] or row[7] or ''), 'state': str(row[9] or ''),
                       'operator': str(row[20] or ''), 'evidence_status': 'reported_asset'})
    approved = []
    for row in book['Approved'].iter_rows(min_row=4, values_only=True):
        capacity = number(row[5])
        if not row[0] or capacity is None or not capacity:
            continue
        approved.append({'project': str(row[0]), 'operator': str(row[1] or ''),
                         'baseload_bcf_day': capacity, 'status': str(row[7] or ''),
                         'state': str(row[8] or ''), 'start_period': None, 'included_in_capacity_path': False})
    book.close()
    if len(trains) < 15 or len({r['id'] for r in trains}) != len(trains):
        raise ValueError('LNG train inventory incomplete or duplicated')
    return {'source_url': url, 'source_title': 'EIA US liquefaction capacity', 'published_at': published,
            'retrieved_at': now_iso(), 'source_sha256': hashlib.sha256(body).hexdigest(),
            'trains': trains, 'approved_only': approved,
            'note': 'Dates are reported estimates. Undated approvals are excluded from the capacity path. Baseload capacity is not feedgas demand.'}


def fetch_generators():
    html = get_bytes(GEN_PAGE).decode(errors='replace')
    # Download lists can contain unpublished future files. Select the latest
    # inventory month strictly before the page's actual release month.
    release = re.search(r'(?<!Next )Release Date:\s*([A-Za-z]+ \d{1,2}, 20\d{2})', plain(html))
    if not release:
        raise ValueError('EIA-860M release date not found')
    published = datetime.strptime(release.group(1), '%B %d, %Y').date()
    candidates = re.findall(r'href=["\']([^"\']*/([a-z]+)_generator(20\d{2})\.xlsx)["\']', html, re.I)
    eligible = []
    for href, month_name, year in candidates:
        try:
            dt = datetime.strptime(month_name + ' ' + year, '%B %Y').date()
        except ValueError:
            continue
        if dt < published.replace(day=1):
            eligible.append((dt, href))
    if not eligible or published > date.today():
        raise ValueError('No published generator inventory found')
    vintage, href = max(eligible)
    if vintage > date.today():
        raise ValueError('Future generator inventory rejected')
    url = urljoin(GEN_PAGE, href)
    body = get_bytes(url)
    book = workbook(body)
    generators = []
    for sheet in ('Operating', 'Planned', 'Retired', 'Canceled or Postponed'):
        rows = book[sheet].iter_rows(values_only=True)
        next(rows); next(rows)
        headers = [str(v or '').strip() for v in next(rows)]
        for values in rows:
            r = dict(zip(headers, values))
            if r.get('Energy Source Code') != 'NG' or not number(r.get('Nameplate Capacity (MW)')):
                continue
            month_key, year_key = ('Planned Operation Month', 'Planned Operation Year') if sheet == 'Planned' else ('Operating Month', 'Operating Year')
            yr, mo = number(r.get(year_key)), number(r.get(month_key))
            period = f'{int(yr):04d}-{int(mo):02d}' if yr and mo and 1 <= mo <= 12 else None
            ba = str(r.get('Balancing Authority Code') or '')
            generators.append({'id': f"{r['Plant ID']}:{r['Generator ID']}", 'plant': str(r['Plant Name']),
                               'generator': str(r['Generator ID']), 'entity': str(r['Entity Name']),
                               'state': str(r['Plant State']), 'balancing_authority': ba,
                               'region': 'ercot' if ba == 'ERCO' else 'pjm' if ba == 'PJM' else 'other_us',
                               'nameplate_mw': number(r['Nameplate Capacity (MW)']),
                               'summer_mw': number(r.get('Net Summer Capacity (MW)')),
                               'technology': str(r['Technology']), 'inventory': sheet,
                               'status': str(r.get('Status') or sheet), 'start_period': period,
                               'evidence_status': 'reported_asset'})
    book.close()
    if len(generators) < 1000:
        raise ValueError('EIA gas generator inventory unexpectedly small')
    # Retrieval is the conservative availability date if no machine-readable release is present.
    totals = [
        {'inventory': kind, 'count': sum(g['inventory'] == kind for g in generators),
         'nameplate_mw': sum(g['nameplate_mw'] for g in generators if g['inventory'] == kind)}
        for kind in sorted({g['inventory'] for g in generators})
    ]
    return {'source_url': url, 'source_title': 'EIA-860M gas generator inventory',
            'inventory_period': vintage.strftime('%Y-%m'), 'published_at': published.isoformat(),
            'publication_date_basis': 'EIA-860M release page',
            'retrieved_at': now_iso(), 'source_sha256': hashlib.sha256(body).hexdigest(),
            'inventory_totals': totals,
            'inventory_scope': 'planned_units_with_all_inventory_totals',
            'generators': [g for g in generators if g['inventory'] == 'Planned'],
            'note': 'Planned MW is not dispatch or incremental gas demand. The compact registry retains planned units and totals for every inventory; original detail is in the linked EIA workbook.'}


def refresh(offline=False, force=False):
    path = ASSET_DIR / 'public_assets.json'
    result = load_json(path, {'schema_version': '1.0'})
    for train in result.get('lng', {}).get('trains', []):
        if not train.get('start_period'):
            train['start_period'], train['date_precision'] = timing(train.get('reported_start'))
    if offline:
        return result
    errors = dict(result.get('errors', {}))
    for key, fn in (('lng', fetch_lng), ('gas_generators', fetch_generators)):
        old = result.get(key)
        if old and not force and key not in errors and old.get('retrieved_at', '')[:10] == date.today().isoformat():
            continue
        try:
            new = fn()
            if old and old['source_sha256'] != new['source_sha256']:
                atomic_json(ASSET_DIR / 'vintages' / f"{key}_{old['published_at']}_{old['source_sha256'][:10]}.json", old)
            result[key] = new
            errors.pop(key, None)
            print(f'{key}: public inventory normalized', flush=True)
        except Exception as exc:
            errors[key] = str(exc)
            print(f'{key}: {exc}; preserving cache', flush=True)
    result['errors'] = errors
    atomic_json(path, result)
    if not result.get('lng') and not result.get('gas_generators'):
        raise RuntimeError('No public asset inventory is available')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    refresh(args.offline, args.force)
