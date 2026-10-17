#!/usr/bin/env python3
"""Fetch public EIA histories; no API key, broker, or market-data seat required.

The first retained vintage is a revised-history snapshot, never a point-in-time
backtest. Each successful source response is hashed and revisions are archived.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from html import unescape
from pathlib import Path

from energy_common import DATA_DIR, atomic_json, load_json, month_days, now_iso

SUMMARY_URL = 'https://www.eia.gov/dnav/ng/ng_sum_lsum_dcu_nus_m.htm'
SOURCES = {
    'dry_production': ('n9070us2m', 'US dry gas production', 'bcf_per_day'),
    'pipeline_imports': ('n9102us2m', 'US pipeline gas imports', 'bcf_per_day'),
    'lng_imports': ('n9103us2m', 'US LNG imports', 'bcf_per_day'),
    'pipeline_exports': ('n9132us2m', 'US pipeline gas exports', 'bcf_per_day'),
    'lng_exports': ('n9133us2m', 'US LNG exports', 'bcf_per_day'),
    'consumption': ('n9140us2m', 'US total gas consumption', 'bcf_per_day'),
    'residential': ('n3010us2m', 'US residential gas consumption', 'bcf_per_day'),
    'commercial': ('n3020us2m', 'US commercial gas consumption', 'bcf_per_day'),
    'industrial': ('n3035us2m', 'US industrial gas consumption', 'bcf_per_day'),
    'power_burn': ('n3045us2m', 'US electric power gas consumption', 'bcf_per_day'),
    'working_storage': ('n5020us2m', 'US working gas in storage', 'bcf'),
    'henry_hub_spot': ('rngwhhdm', 'Henry Hub monthly spot price', 'usd_per_mmbtu'),
}


def get_bytes(url: str) -> bytes:
    for attempt in range(2):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'SSI-EnergyResearch/1.0 (public EIA data)'})
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
        except Exception:
            if attempt:
                raise
            time.sleep(1)
    raise RuntimeError('unreachable')


def plain(html: str) -> str:
    return unescape(re.sub(r'<[^>]+>', '', html)).strip()


def parse_eia_history(html: str, unit: str, start='2010-01') -> tuple[str, list[dict]]:
    release = re.search(r'(?<!Next )Release Date:\s*(\d{1,2}/\d{1,2}/\d{4})', html)
    if not release:
        raise ValueError('EIA history missing release date')
    published = datetime.strptime(release.group(1), '%m/%d/%Y').date().isoformat()
    records = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, flags=re.I | re.S):
        cells = [plain(x) for x in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', row, flags=re.I | re.S)]
        if len(cells) != 13 or not re.fullmatch(r'\d{4}', cells[0]):
            continue
        for month, raw in enumerate(cells[1:], 1):
            period = f'{int(cells[0]):04d}-{month:02d}'
            raw = raw.replace(',', '')
            if period < start or not re.fullmatch(r'-?\d+(?:\.\d+)?', raw):
                continue
            value = float(raw)
            if unit == 'bcf_per_day':
                value /= 1000 * month_days(period)
            elif unit == 'bcf':
                value /= 1000
            records.append({'period': period, 'value': round(value, 8), 'published_at': published})
    if len(records) < 12:
        raise ValueError(f'EIA history has only {len(records)} valid observations')
    periods = [r['period'] for r in records]
    if len(periods) != len(set(periods)):
        raise ValueError('duplicate EIA periods')
    return published, sorted(records, key=lambda r: r['period'])


def fetch_one(key, spec) -> dict:
    series_id, label, unit = spec
    url = f'https://www.eia.gov/dnav/ng/hist/{series_id}.htm'
    body = get_bytes(url)
    html = body.decode('utf-8', errors='replace')
    # Unit validation is separate from a stable filename, to catch source drift.
    expected = 'Dollars per Million Btu' if unit == 'usd_per_mmbtu' else 'Million Cubic Feet'
    if expected.lower() not in plain(html).lower():
        raise ValueError(f'{key}: unexpected source unit; expected {expected}')
    published, observations = parse_eia_history(html, unit)
    title = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
    if not title:
        raise ValueError('missing source title')
    if key == 'working_storage' and 'working gas' not in plain(title.group(1)).lower():
        raise ValueError('Working storage source must exclude base/cushion gas')
    return {'id': key, 'label': label, 'unit': unit, 'geography': 'US', 'frequency': 'monthly',
            'status': 'observed_revised', 'source_id': f'EIA:{series_id}', 'source_url': url,
            'source_title': plain(title.group(1)), 'published_at': published,
            'retrieved_at': now_iso(), 'source_sha256': hashlib.sha256(body).hexdigest(),
            'latest_period': observations[-1]['period'], 'observations': observations}


def fetch_weekly_storage():
    url = 'https://ir.eia.gov/ngs/wngsr.json'
    body = get_bytes(url)
    report = json.loads(body.decode('utf-8-sig'))
    published = datetime.strptime(report['release_date'][:11], '%Y-%b-%d').date().isoformat()
    if published > date.today().isoformat():
        raise ValueError('Weekly report has a future release date')
    rows = []
    for source in report['series']:
        if source.get('unitsshort') != 'bcf':
            raise ValueError('Unexpected weekly storage units')
        period, value = source['data'][0]
        rows.append({'series_id': source['series_id'], 'region': source['name'], 'period': period,
                     'working_storage_bcf': float(value), 'change_bcf': source['calculated']['net_change'],
                     'five_year_average_bcf': source['calculated']['5yr-avg'],
                     'vs_five_year_pct': source['calculated']['pct-chg_5yr-avg']})
    total = next(r for r in rows if r['series_id'] == 'png.nw2_epg0_swo_r48_bcf.w')
    return {'source_url': url, 'source_title': report['release_name'], 'published_at': published,
            'retrieved_at': now_iso(), 'source_sha256': hashlib.sha256(body).hexdigest(),
            'geography': 'Lower 48', 'unit': 'bcf', 'total': total, 'regions': rows,
            'note': 'Weekly Lower 48 context is not spliced into the monthly US balance.'}


def refresh(data_dir: Path = DATA_DIR, *, offline=False, force=False) -> dict:
    existing = load_json(data_dir / 'observations.json', {'schema_version': '1.0', 'series': {}})
    if offline:
        if not existing['series']:
            raise ValueError('No energy observations cache; run fetch_energy_panel.py online first')
        return existing
    errors = dict(existing.get('errors', {}))
    pending = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for key, spec in SOURCES.items():
            old = existing['series'].get(key, {})
            retrieved = str(old.get('retrieved_at', ''))[:10]
            if not force and key not in errors and retrieved == date.today().isoformat() and old.get('source_id') == f'EIA:{spec[0]}':
                continue
            pending[pool.submit(fetch_one, key, spec)] = key
        for future in as_completed(pending):
            key = pending[future]
            try:
                record = future.result()
                old = existing['series'].get(key)
                if old and old.get('source_sha256') != record['source_sha256']:
                    archive = data_dir / 'vintages' / f"{key}_{old['published_at']}_{old['source_sha256'][:10]}.json"
                    if not archive.exists():
                        atomic_json(archive, old)
                existing['series'][key] = record
                errors.pop(key, None)
                print(f"{key}: {len(record['observations'])} months, through {record['latest_period']}", flush=True)
            except Exception as exc:
                errors[key] = f'{type(exc).__name__}: {exc}'
                print(f'{key}: source unavailable; preserving cache', flush=True)
    try:
        old = existing.get('weekly_storage')
        if force or not old or old.get('retrieved_at', '')[:10] != date.today().isoformat() or 'weekly_storage' in errors:
            weekly = fetch_weekly_storage()
            if old and old['source_sha256'] != weekly['source_sha256']:
                atomic_json(data_dir / 'vintages' / f"weekly_storage_{old['published_at']}_{old['source_sha256'][:10]}.json", old)
            existing['weekly_storage'] = weekly
            errors.pop('weekly_storage', None)
    except Exception as exc:
        errors['weekly_storage'] = str(exc)
    existing.update({'schema_version': '1.0', 'retrieved_at': now_iso(), 'errors': errors,
                     'history_basis': 'Revised EIA histories. Publication vintages retained from first acquisition; not a historical information-set backtest.'})
    if not existing['series']:
        raise RuntimeError(f'No public source returned usable data: {errors}')
    atomic_json(data_dir / 'observations.json', existing)
    return existing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    result = refresh(args.data_dir, offline=args.offline, force=args.force)
    print(f"Energy sources: {len(result['series'])}; failed refreshes: {len(result.get('errors', {}))}")


if __name__ == '__main__':
    main()
