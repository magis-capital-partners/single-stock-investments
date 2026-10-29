"""Recover catalogued official filing originals over HTTPS, with resumable receipts.

Only EDGAR and reviewed issuer filing hosts already in the private index are eligible.
This deliberately does not crawl third-party links or bypass access restrictions.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import threading
from urllib.parse import urlparse
from urllib.error import HTTPError

from company_sources import extract
from sec_client import SecClient

ISSUER_HOSTS = frozenset({'wcsecure.weblink.com.au','www.se.com','download.se.com',
                         'plc.rightmove.co.uk','consensusmining.com',
                         'investorrelations.sgx.com','assets-finance.hermes.com','www.otcmarkets.com'})


def fingerprint(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def eligible(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and (parsed.netloc in ISSUER_HOSTS or parsed.netloc == 'www.sec.gov' and parsed.path.startswith('/Archives/edgar/data/'))


def cached_filing(cache, url):
    path = cache / 'filings' / (fingerprint(url) + '.json')
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding='utf-8'))
    if doc.get('url') != url:
        return {}
    if doc.get('status') == 'indexed':
        try:
            original = base64.b64decode(doc['original_base64'], validate=True)
            if fingerprint(original) != doc['original_sha256'] or fingerprint(doc['text']) != doc['text_sha256']:
                return {}
        except (KeyError, ValueError):
            return {}
    return doc


def candidates(cache):
    manifest = json.loads((cache / 'index.json').read_text(encoding='utf-8'))
    urls = set()
    for part in manifest.get('record_parts', []):
        for record in json.loads((cache / part).read_text(encoding='utf-8')).values():
            if record.get('processing_status') == 'indexed' or record.get('availability') == 'removed_or_unavailable':
                continue
            for location in record.get('locations', []):
                url = location.get('url', '')
                if location.get('kind') == 'filing' and eligible(url):
                    urls.add(url)
    return sorted(urls)


def recover(cache, url, client):
    prior = cached_filing(cache, url)
    if prior.get('status') == 'indexed':
        return 'reused'
    if prior.get('status') == 'access_unavailable' and prior.get('fetched_at'):
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(prior['fetched_at'])).total_seconds()
        if age < 86400:
            return 'access_unavailable'
    doc = {'url': url, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'text': ''}
    try:
        raw = client.get_bytes(url, timeout=30)
        # Some upstream failures arrive as HTML with status 200. Never index them.
        if any(x in raw[:20000].lower() for x in (b'undeclared automated tool', b'request rate threshold exceeded', b'your request originates from an undeclared', b'permission to view this headline')):
            raise PermissionError('Publisher access policy response')
        suffix = '.pdf' if raw.startswith(b'%PDF') else Path(urlparse(url).path).suffix.lower()
        if suffix not in ('.pdf','.html','.htm','.txt','.xml') and b'<html' in raw[:2000].lower():
            suffix = '.html'
        if suffix == '.pdf':
            from backfill_company_sources import extract_complete
            text, status, detail = extract_complete(raw, suffix, ocr=True)
        else:
            text, status = extract(raw, suffix)
            detail = {'format': suffix}
        doc.update(text=text, status=status, extraction=detail, original_sha256=fingerprint(raw),
                   original_base64=base64.b64encode(raw).decode(), text_sha256=fingerprint(text))
    except Exception as exc:
        doc.update(status='access_unavailable' if isinstance(exc, PermissionError) or isinstance(exc, HTTPError) and exc.code in (401,403,404) else 'failed', error=str(exc)[:240])
    path = cache / 'filings' / (fingerprint(url) + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')
    temporary.replace(path)
    return doc['status']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path('_private/company-research/cache'))
    parser.add_argument('--seconds', type=int, default=1200)
    parser.add_argument('--workers', type=int, choices=(1,2,3), default=3)
    args = parser.parse_args()
    local = threading.local()
    def fetch(url):
        if not hasattr(local, 'client'):
            # At most three requests at once, below three per second in steady
            # state across the workers; each client uses SEC backoff rules.
            local.client = SecClient(min_interval=args.workers*.4, max_attempts=1)
        return url, recover(args.cache, url, local.client)
    end = time.monotonic() + args.seconds
    counts = {}
    urls = candidates(args.cache)
    blocked_hosts = set()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for start in range(0,len(urls),args.workers):
            if time.monotonic() >= end:
                break
            batch = [url for url in urls[start:start+args.workers] if urlparse(url).netloc not in blocked_hosts]
            for url,status in pool.map(fetch, batch):
                counts[status] = counts.get(status, 0) + 1
                if sum(counts.values()) % 50 == 0:
                    print(json.dumps({'processed':sum(counts.values()),'outcomes':counts}),flush=True)
                if status == 'access_unavailable':
                    doc = cached_filing(args.cache,url)
                    if '403' in doc.get('error','') or 'policy' in doc.get('error',''):
                        blocked_hosts.add(urlparse(url).netloc)
    print(json.dumps(counts), flush=True)


if __name__ == '__main__':
    main()
