"""Capture small public EIA/WGC physical ledgers; retain last good source on failure.

Raw publications live in the ignored object store. Only normalized factual tables
and provenance are published. No licensed terminal, broker or credentials are used.
"""
from __future__ import annotations

import argparse
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urljoin

from commodity_common import ROOT, digest, load, save
from commodity_observations import observation, pack, unpack

OUTPUT = ROOT/'_system/reference/market-data/commodities/resolution_inputs.json'
CACHE = ROOT/'_private/commodity/objects'
STEO_PAGE = 'https://www.eia.gov/outlooks/steo/outlook.php'
WGC_PAGE = 'https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2026'
ERCOT_PAGE = 'https://www.ercot.com/gridinfo/load/load_hist'


def parse_ercot(body, src):
    import openpyxl
    archive = zipfile.ZipFile(io.BytesIO(body))
    names = [n for n in archive.namelist() if n.endswith('.xlsx')]
    if len(names) != 1 or archive.getinfo(names[0]).file_size > 20_000_000:
        raise ValueError('Unexpected ERCOT load archive')
    book = openpyxl.load_workbook(io.BytesIO(archive.read(names[0])), read_only=True, data_only=True)
    values = iter(book.active.values)
    header = list(next(values))
    if header[0] != 'Hour Ending' or 'ERCOT' not in header:
        raise ValueError('ERCOT hourly schema changed')
    buckets = defaultdict(list)
    native = []
    occurrences = defaultdict(int)
    for row in values:
        label = str(row[0])
        if not re.match(r'\d{2}/\d{2}/20\d{2} ', label):
            continue
        day = datetime.strptime(label[:10], '%m/%d/%Y').replace(tzinfo=timezone.utc)
        hour = int(label[11:13])
        if not 0 <= hour <= 24:
            raise ValueError('Invalid ERCOT local hour ending')
        # Local clock labels and DST repeats are retained through source counts;
        # no fabricated UTC timestamp is assigned to the ERCOT settlement hour.
        kind = 'weekend' if day.weekday() >= 5 else 'weekday'
        period = f'{day:%Y-%m}|{kind}|HE{hour:02d}'
        value = row[header.index('ERCOT')]
        if isinstance(value, (int, float)) and value >= 0:
            label = f'{day:%Y-%m-%d}|HE{hour:02d}'
            occurrences[label] += 1
            native.append((f'{label}|{occurrences[label]}', value))
        for region in ('ERCOT', 'COAST', 'FWEST'):
            value = row[header.index(region)]
            if isinstance(value, (int, float)) and value >= 0:
                buckets[(period, region)].append(value)
    book.close()
    if len(buckets) < 500:
        raise ValueError('ERCOT load archive unexpectedly incomplete')
    profiles = [observation(value=sum(v)/len(v), source=src, period=period, metric='hourly_load',
                        commodity='power', unit='MW', frequency='hourly', basis='observed_profile',
                        region=region, product='native electric load', weight_hours=len(v),
                        transformation='Mean load by calendar month, local hour ending and weekday/weekend; count retains settlement hours',
                        extraction='Native Load Report; ERCOT/COAST/FWEST') for (period, region), v in sorted(buckets.items())]
    # Preserve every actual settlement hour for dispatch in the latest month.
    # Source occurrences distinguish repeated DST local hours; HE24 stays HE24.
    latest = max(period[:7] for period, _ in native)
    hours = [observation(value=value, source=src, period=period, metric='native_hourly_load',
                         commodity='power', unit='MW', frequency='hourly', basis='observed_revised',
                         region='ERCOT', product='native electric load', weight_hours=1,
                         transformation='Identity; local hour ending and repeated-hour occurrence retained',
                         extraction='Native Load Report; every ERCOT settlement hour in latest source month')
             for period, value in native if period.startswith(latest)]
    return profiles+hours


def source(key, url, body, published, today, days, next_release=None):
    sha = digest(body)
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE/sha
    if not path.exists():
        path.write_bytes(body)
    return {'id': key, 'url': url, 'sha256': sha, 'reviewed_sha256': sha,
            'published_at': published, 'retrieved_at': today.isoformat(),
            'reviewed_at': today.isoformat(), 'review_basis': 'validated_parser_and_accounting',
            'max_age_days': days, 'next_release': next_release, 'error': None}


def parse_steo(body, src):
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    dates = list(book['Dates'].values)
    beginning = int(dates[4][3])
    last_history = int(dates[6][3])
    rows = []
    specs = {
        '5atab': ('gas', 'bcf/day'), '3atab': ('crude', 'million bbl/day'),
        '3btab': ('crude', 'million bbl/day'), '3ctab': ('crude', 'million bbl/day'),
        '7atab': ('power', 'billion kWh'), '2tab': ('market', 'USD'),
    }
    allowed_prices = {'WTIPUUS': ('crude', 'USD/bbl'), 'BREPUUS': ('crude', 'USD/bbl'),
                      'NGHHUUS': ('gas', 'USD/MMBtu')}
    for sheet, (commodity, default_unit) in specs.items():
        for values in book[sheet].values:
            code, label = values[:2]
            if not isinstance(code, str) or not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9_$]+', code):
                continue
            if sheet == '2tab' and code not in allowed_prices:
                continue
            if sheet == '7atab' and not (code.startswith('ELWHU_') or code in {'ELSUTWH', 'TSEOTWH', 'EPEOTWH', 'INEOTWH', 'CMEOTWH', 'ELCOTWH'}):
                # This sheet also contains fuel tonnages and retail cents/kWh;
                # they must never inherit the generation table's TWh unit.
                continue
            kind, unit = allowed_prices.get(code, (commodity, default_unit))
            if code.startswith('NGWG'):
                unit = 'bcf'
            if code.startswith('pasc_'):
                unit = 'million bbl'
            if code.startswith('ELWHU_'):
                unit = 'USD/MWh'
            # 72 monthly columns from Jan 2022 through Dec 2027, then aggregates.
            for i, value in enumerate(values[2:74]):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                n = beginning//100*12 + beginning%100-1+i
                period = f'{n//12:04d}-{n%12+1:02d}'
                ym = (n//12)*100+n%12+1
                basis = 'observed_estimate' if ym <= last_history else 'published_forecast'
                region = code if sheet not in ('2tab',) else 'US' if code != 'BREPUUS' else 'global'
                rows.append(observation(value=value, source=src, period=period, metric=code,
                                        commodity=kind, unit=unit, frequency='monthly', basis=basis,
                                        region=region, product=label.strip(), extraction=f'{sheet}:{code}',
                                        transformation='publisher monthly value; no interpolation'))
    book.close()
    # Duplicate code appearances in EIA sections refer to the same series.
    unique = {r['id']: r for r in rows}
    if len(unique) < 2000:
        raise ValueError('STEO monthly schema changed')
    return list(unique.values())


def parse_wgc(body, src):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, 'html.parser')
    table = next((t for t in soup.find_all('table') if 'Net Producer Hedging' in t.get_text()), None)
    if table is None:
        raise ValueError('WGC supply/demand table missing')
    labels = [c.get_text(' ', strip=True) for c in table.find('tr').find_all(['td', 'th'])]
    quarters = []
    for label in labels:
        match = re.fullmatch(r"Q([1-4])['’](\d{2})", label)
        if match:
            quarters.append(f'20{match[2]}-Q{match[1]}')
    if len(quarters) < 4:
        raise ValueError('WGC quarterly labels changed')
    wanted = {'Mine Production': 'mine', 'Net Producer Hedging': 'hedging', 'Recycled Gold': 'recycling',
              'Total Supply': 'supply', 'Jewellery Fabrication': 'jewellery', 'Technology': 'technology',
              'Total Bar and Coin': 'bar_coin', 'ETFs and Similar Products': 'etf',
              'Central Bank and Other Institutions': 'central_bank', 'OTC and other': 'otc_other',
              'Total Demand': 'demand', 'LBMA Gold Price (US$/oz)': 'price'}
    rows = []
    for tr in table.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
        if len(cells) < 6 or cells[0] not in wanted:
            continue
        for period, value in zip(quarters, cells[1:1+len(quarters)]):
            number = float(value.replace(',', '').replace('−', '-'))
            metric = wanted[cells[0]]
            rows.append(observation(value=number, source=src, period=period, metric=metric,
                                    commodity='gold', unit='USD/troy oz' if metric == 'price' else 'tonnes',
                                    frequency='quarterly', basis='observed_estimate',
                                    extraction='Table 1; quarterly sector rows',
                                    estimate_note='WGC estimates; central-bank data include estimated unreported activity.'))
    latest = {r['metric']: r['value'] for r in rows if r['period'] == max(quarters)}
    if len(latest) != len(wanted) or abs(latest['mine']+latest['hedging']+latest['recycling']-latest['supply']) > .2:
        raise ValueError('WGC supply does not reconcile')
    if abs(sum(latest[k] for k in ('jewellery', 'technology', 'bar_coin', 'etf', 'central_bank', 'otc_other'))-latest['demand']) > .2:
        raise ValueError('WGC demand does not reconcile')
    return rows


def refresh(output=OUTPUT, today=None, download=None):
    from fetch_energy_panel import get_bytes
    download = download or get_bytes
    today = today or datetime.now(timezone.utc).date()
    previous = load(output, {'observations': [], 'sources': []})
    previous['observations'] = unpack(previous)
    observations, sources, errors = [], [], []
    for key in ('steo_monthly', 'wgc_quarterly', 'ercot_hourly'):
        try:
            if key == 'steo_monthly':
                from bs4 import BeautifulSoup
                page = download(STEO_PAGE)
                soup = BeautifulSoup(page, 'html.parser')
                candidates = []
                for tr in soup.find_all('tr'):
                    text = tr.get_text(' ', strip=True)
                    release = re.search(r'\b(\d{2}/\d{2}/20\d{2})\b', text)
                    link = tr.find('a', href=re.compile(r'_base\.xlsx$'))
                    if release and link:
                        published = datetime.strptime(release[1], '%m/%d/%Y').replace(tzinfo=timezone.utc).date()
                        if published <= today:
                            candidates.append((published, urljoin(STEO_PAGE, link['href'])))
                if not candidates:
                    raise ValueError('No published STEO workbook')
                published, url = max(candidates)
                body = download(url)
                src = source(key, url, body, published.isoformat(), today, 45)
                release = re.search(r'Next Release Date:\s*([A-Z][a-z]+ \d{1,2}, 20\d{2})', soup.get_text(' ', strip=True))
                if release:
                    src['next_release'] = datetime.strptime(release[1], '%B %d, %Y').replace(tzinfo=timezone.utc).date().isoformat()
                parsed = parse_steo(body, src)
            elif key == 'wgc_quarterly':
                from bs4 import BeautifulSoup
                landing = BeautifulSoup(download('https://www.gold.org/goldhub/research'), 'html.parser')
                links = [urljoin(WGC_PAGE, a['href']) for a in landing.select('a[href]') if re.search(r'/gold-demand-trends-q[1-4]-20\d{2}$', a['href'])]
                def quarter_key(url):
                    match = re.search(r'q([1-4])-(20\d{2})$', url)
                    return int(match[2]), int(match[1])
                url = max(links, key=quarter_key) if links else WGC_PAGE
                body = download(url)
                page = BeautifulSoup(body, 'html.parser')
                stamp = page.find('time')
                if not stamp:
                    raise ValueError('Goldhub publication date missing')
                published = datetime.strptime(stamp.get_text(' ', strip=True), '%d %B, %Y').replace(tzinfo=timezone.utc).date()
                src = source(key, url, body, published.isoformat(), today, 120)
                if src['published_at'] > today.isoformat():
                    raise ValueError('Future WGC source')
                parsed = parse_wgc(body, src)
            else:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(download(ERCOT_PAGE), 'html.parser')
                links = [a for a in soup.find_all('a', href=True) if re.fullmatch(r'20\d{2} ERCOT Hourly Load Data', a.get_text(' ', strip=True)) and int(a.get_text()[:4]) <= today.year]
                link = max(links, key=lambda a: a.get_text())
                text = link.parent.parent.get_text(' ', strip=True)
                stamp = re.search(r'([A-Z][a-z]{2} \d{1,2}, 20\d{2})', text)
                if not stamp:
                    raise ValueError('ERCOT load release date missing')
                published = datetime.strptime(stamp[1], '%b %d, %Y').replace(tzinfo=timezone.utc).date()
                if published > today:
                    raise ValueError('Future ERCOT release')
                url = urljoin(ERCOT_PAGE, link['href'])
                body = download(url)
                src = source(key, url, body, published.isoformat(), today, 45)
                parsed = parse_ercot(body, src)
            observations.extend(parsed)
            sources.append(src)
        except Exception as exc:  # noqa: BLE001 -- each failed adapter retains its prior dated source
            old = next((s for s in previous['sources'] if s['id'] == key), None)
            if old:
                sources.append({**old, 'error': type(exc).__name__, 'last_attempt': today.isoformat()})
                observations.extend(r for r in previous['observations'] if r['source_id'] == key)
            errors.append({'source': key, 'error': type(exc).__name__, 'detail': str(exc)[:200]})
    result = {'schema_version': 'commodity_observations.v2', 'as_of': today.isoformat(),
              'sources': sources, 'observations': observations, 'errors': errors}
    save(output, {k: v for k, v in result.items() if k != 'observations'} | {'datasets': pack(observations)})
    # New captures never overwrite prior vintages, including revisions within one day.
    save(ROOT/'_private/commodity/resolution-vintages-v2'/f'{today}-{digest(result)[:16]}.json',
         {k: v for k, v in result.items() if k != 'observations'} | {'datasets': pack(observations)}, compact=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = refresh()
    print(f"Captured {len(result['observations'])} physical observations; failures: {result['errors']}")
    if result['errors']:
        raise SystemExit(1)
