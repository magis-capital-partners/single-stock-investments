#!/usr/bin/env python3
"""Repair issuer/owner identity from public SEC ownership submissions in the feed.

Only --fetch permits HTTPS reads. Ordinary builds consume the resulting local
cache and never download. No ThetaData or broker connections are involved.
"""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse
import urllib.request

from atomic_io import write_json_if_changed
from insider_signal_common import parse_form4_submission, SEC_UA

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / '_system/reference/market-data/insider/ownership_cache.json'


def repair(events, *, cache=None, fetch=False):
    cache = dict(cache or {'schema_version': 1, 'filings': {}})
    cache['filings'] = dict(cache.get('filings') or {})
    errors = []
    for event in events:
        if event.get('event_type') != 'form4_transaction':
            continue
        url = event.get('evidence_ref') or ''
        parsed = urlparse(url)
        match = re.search(r'/(\d{10}-\d{2}-\d{6})\.txt$', parsed.path)
        if parsed.scheme != 'https' or parsed.hostname != 'www.sec.gov' or not parsed.path.startswith('/Archives/edgar/data/') or not match:
            continue
        accession = match[1]
        if accession in cache['filings'] or not fetch:
            continue
        try:
            request = urllib.request.Request(url, headers={'User-Agent': SEC_UA})
            with urllib.request.urlopen(request, timeout=10) as response:
                text = response.read().decode('utf-8', errors='replace')
            rows = parse_form4_submission(text, {'accession': accession, 'source_path': url,
                'filing_date': event.get('published_at') or event.get('observed_at')})
            if not rows or not all(row.get('issuer_cik') for row in rows):
                raise ValueError('No verified issuer in SEC XML')
            cache['filings'][accession] = {'source_url': url, 'transactions': rows}
        except Exception as exc:
            errors.append({'accession': accession, 'error': str(exc)})
        time.sleep(0.15)
    return cache, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    events = json.loads((ROOT / 'dashboard/data/insights/events.json').read_text(encoding='utf-8'))['events']
    cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else None
    cache, errors = repair(events, cache=cache, fetch=args.fetch)
    write_json_if_changed(CACHE, cache)
    print(json.dumps({'cached_filings': len(cache['filings']), 'errors': errors}, indent=2))


if __name__ == '__main__':
    main()
