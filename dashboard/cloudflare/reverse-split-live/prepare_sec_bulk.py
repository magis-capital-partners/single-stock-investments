"""Read public SEC bulk data into a bounded stream. Never receives broker credentials."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

AGENT = 'MagisCapitalResearch/1.0 (financial preparation; drewgoldman01@gmail.com)'
TICKERS = 'https://www.sec.gov/files/company_tickers_exchange.json'
FACTS = 'https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip'

def emit(value):
    print(json.dumps(value, separators=(',', ':'), ensure_ascii=True), flush=True)

def fetch(url):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept': 'application/json, application/zip'}), timeout=120)
        except urllib.error.HTTPError as error:
            if error.code not in (403, 429) or attempt == 3:
                raise
            time.sleep(min(300, max(60, int(error.headers.get('Retry-After', '60')))))

def compact(raw, aliases, cutoff):
    facts = {}
    for namespace in ('us-gaap', 'ifrs-full', 'dei'):
        selected = {}
        for tag in aliases:
            concept = raw.get('facts', {}).get(namespace, {}).get(tag)
            if not concept:
                continue
            units = {}
            for unit, rows in concept.get('units', {}).items():
                if len(unit) != 3 or not unit.isalpha() or not unit.isupper():
                    continue
                latest = set(sorted({r.get('end', '') for r in rows})[-3:])
                chosen = [{k: r[k] for k in ('start', 'end', 'val', 'accn', 'fy', 'fp', 'form', 'filed', 'frame') if k in r}
                          for r in rows if r.get('end', '') >= cutoff or r.get('end', '') in latest]
                if chosen:
                    units[unit] = chosen
            if units:
                selected[tag] = {'units': units}
        if selected:
            facts[namespace] = selected
    return {'cik': raw['cik'], 'entityName': raw.get('entityName'), 'facts': facts}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--aliases', required=True)
    parser.add_argument('--maximum-archive-gb', type=int, default=8)
    args = parser.parse_args()
    aliases = set(json.loads(Path(args.aliases).read_text(encoding='utf-8')))
    with fetch(TICKERS) as response:
        body = response.read(8_000_001)
    if len(body) > 8_000_000:
        raise ValueError('SEC ticker list exceeds limit')
    data = json.loads(body)
    universe = {}
    for values in data['data']:
        row = dict(zip(data['fields'], values))
        if not row.get('exchange') or not row.get('ticker'):
            continue
        cik = str(int(row['cik']))
        record = universe.setdefault(cik, {'cik': cik, 'company': row.get('name'), 'tickers': [], 'exchanges': [], 'security_type': 'requires_common_share_verification'})
        if row['ticker'] not in record['tickers']:
            record['tickers'].append(row['ticker'])
        if row['exchange'] not in record['exchanges']:
            record['exchanges'].append(row['exchange'])
    if len(universe) < 1000:
        raise ValueError('SEC listed universe unexpectedly small; preserve previous snapshot')
    limit = args.maximum_archive_gb * 1024**3
    with tempfile.TemporaryFile(suffix='.zip') as archive:
        checksum = hashlib.sha256()
        size = 0
        with fetch(FACTS) as response:
            expected = int(response.headers.get('Content-Length', '0'))
            if expected > limit or shutil.disk_usage(tempfile.gettempdir()).free < max(expected, 2*1024**3) + 512*1024**2:
                raise ValueError('Insufficient bounded workspace for SEC bulk archive')
            while True:
                chunk = response.read(1024*1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError('SEC bulk archive size limit')
                checksum.update(chunk)
                archive.write(chunk)
        archive.seek(0)
        emit({'kind': 'source', 'url': FACTS, 'sha256': checksum.hexdigest(), 'bytes': size, 'universe': list(universe.values()), 'universe_url': TICKERS, 'universe_sha256': hashlib.sha256(body).hexdigest()})
        seen = set()
        cutoff = (date.today()-timedelta(days=4*366)).isoformat()
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                name = Path(member.filename).name
                if not name.startswith('CIK') or not name.endswith('.json') or not name[3:-5].isdigit():
                    continue
                cik = str(int(name[3:-5]))
                if cik not in universe:
                    continue
                seen.add(cik)
                if member.file_size > 128*1024**2:
                    emit({'kind': 'company', 'issuer': universe[cik], 'error': 'Company Facts member exceeds bounded reader'})
                    continue
                try:
                    raw_bytes = zipped.read(member)
                    raw = json.loads(raw_bytes)
                    if str(int(raw['cik'])) != cik:
                        raise ValueError('SEC bulk member identity mismatch')
                    emit({'kind': 'company', 'issuer': universe[cik], 'raw': compact(raw, aliases, cutoff), 'member_sha256': hashlib.sha256(raw_bytes).hexdigest()})
                except (ValueError, KeyError, TypeError) as error:
                    emit({'kind': 'company', 'issuer': universe[cik], 'error': str(error)})
        for cik in sorted(set(universe)-seen, key=int):
            emit({'kind': 'company', 'issuer': universe[cik], 'error': 'No SEC Company Facts member for listed issuer'})
        emit({'kind': 'complete', 'issuers': len(universe), 'members_found': len(seen)})

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'event': 'SEC_bulk_preparation_failed', 'error': str(error)}), file=sys.stderr, flush=True)
        raise SystemExit(1)
