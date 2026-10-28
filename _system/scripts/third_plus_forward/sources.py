"""Bounded public-source adapters. No account credentials, trading SDK or paid data."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from .policy import ROOT, NY, closing, sessions, stamp


def receipt(raw, url, locator, at):
    return {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'locator': locator, 'retrieved_at': at.isoformat()}


def public_url(url):
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname not in {'data.sec.gov', 'query1.finance.yahoo.com'} or u.username or u.password or u.fragment:
        raise ValueError('Only approved public research HTTPS endpoints are allowed')
    if u.hostname == 'data.sec.gov' and not re.fullmatch(r'/api/xbrl/companyfacts/CIK\d{10}\.json', u.path):
        raise ValueError('Only public SEC companyfacts are requested')
    if u.hostname == 'query1.finance.yahoo.com' and not re.fullmatch(r'/v8/finance/chart/[A-Z0-9.%^=_-]{1,30}', u.path):
        raise ValueError('Only public market reference charts are requested')


class PublicSources:
    def __init__(self, work, now, maximum=30, network=True):
        from _system.scripts.reverse_splits.free_evidence import FreeClient
        from _system.scripts.reverse_splits.config import load_config
        self.now = now
        self.network = network
        self.client = FreeClient(Path(work)/'public_cache'/now.strftime('%Y%m%dT%H%M'),
                                 load_config().section('edgar')['user_agent'], maximum=maximum,
                                 validator=public_url)
        self.errors = []

    def get(self, url):
        if not self.network:
            return None
        raw = self.client.get(url)
        if raw is None:
            self.errors.append({'url': url, 'status': 'unavailable'})
        return raw

    def financials(self, cik):
        url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
        raw = self.get(url)
        if raw is None:
            return None, None
        doc = json.loads(raw)
        if int(doc.get('cik', -1)) != int(cik):
            raise ValueError('SEC companyfacts issuer mismatch')
        # Use precisely the financial extractor that supplied the historical signals.
        script = "const F=require('./_system/scripts/third_plus_signal/features.cjs');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{let x=JSON.parse(s);console.log(JSON.stringify(F.financialSnapshot(x.raw,x.at)))});"
        result = subprocess.run(['node', '-e', script], input=json.dumps({'raw': doc, 'at': self.now.isoformat()}),
                                cwd=ROOT, text=True, capture_output=True, check=True, timeout=30)
        return json.loads(result.stdout), receipt(raw, url, 'facts: shared point-in-time financialSnapshot', self.now)

    def prices(self, ticker):
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.^=_-]{0,19}', ticker):
            raise ValueError('Invalid public market symbol')
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + quote(ticker, safe='') + '?range=3mo&interval=1d&events=splits'
        raw = self.get(url)
        if raw is None:
            return [], None, []
        doc = json.loads(raw)
        results = doc.get('chart', {}).get('result') or []
        if not results:
            self.errors.append({'url': url, 'status': 'no_market_reference'})
            return [], None, []
        chart = results[0]
        if chart.get('meta', {}).get('symbol', '').upper() != ticker.upper():
            raise ValueError('Public chart symbol mismatch')
        q = (chart.get('indicators', {}).get('quote') or [{}])[0]
        rows = []
        for i, ts in enumerate(chart.get('timestamp', [])):
            day = datetime.fromtimestamp(ts, timezone.utc).astimezone(NY).date().isoformat()
            try:
                if day not in sessions(day, day) or closing(day) > self.now:
                    continue
                values = {k: float(q[k][i]) for k in ['open', 'high', 'low', 'close', 'volume']}
                from .journal import number
                if not all(number(values[k], .000001) for k in ['open', 'high', 'low', 'close']) or not number(values['volume']):
                    continue
                if values['low'] > min(values['open'], values['close']) or values['high'] < max(values['open'], values['close']):
                    continue
                rows.append(dict(values, day=day))
            except (TypeError, IndexError, KeyError, ValueError):
                continue
        actions = [{'day': datetime.fromtimestamp(x['date'], timezone.utc).astimezone(NY).date().isoformat(),
                    'new_shares_per_old': float(x['numerator'])/float(x['denominator'])}
                   for x in chart.get('events', {}).get('splits', {}).values()]
        return rows, receipt(raw, url, 'chart.result[0]; completed regular-session daily bars; vendor split-adjusted basis', self.now), actions


def discover(root, now, frozen_at):
    """Read the existing disclosure pipeline, retaining source identity and unknowns."""
    root = Path(root)
    path = root/'_system/data/reverse_splits/events.jsonl'
    if not path.exists():
        raise ValueError('The committed split-event input is missing')
    raw = path.read_bytes()
    events = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    by_issuer = defaultdict(dict)
    for e in events:
        if not e.get('cik') or not e.get('ex_date') or not e.get('ticker'):
            continue
        if float(e.get('split_from') or 0) <= float(e.get('split_to') or 1):
            continue
        by_issuer[str(int(e['cik']))][e['ex_date']] = e
    candidates = []
    cutoff = (stamp(frozen_at).astimezone(NY).date() - timedelta(days=1)).isoformat()
    for cik, days in by_issuer.items():
        for day, e in days.items():
            if day < cutoff or day > (now + timedelta(days=90)).date().isoformat():
                continue
            if e.get('accept_time') and stamp(e['accept_time']) > now:
                continue
            earlier = [d for d in days if d < day]
            # Future enrollment can use everything already captured in today's source snapshot.
            ordinal = max(len(earlier), int(e.get('prior_rs_count') or 0)) + 1
            if ordinal < 3:
                continue
            candidates.append({'event_id': 'third-plus/'+cik+'/'+day, 'issuer_id': 'cik/'+cik,
                               'cik': cik, 'ticker': e['ticker'], 'company': e.get('company') or e['ticker'],
                               'effective_day': day, 'documented_split_ordinal': ordinal,
                               'action_known_at': e.get('accept_time') or now.isoformat(),
                               'identity_status': 'ledger_CIK_ticker; broker contract unverified',
                               'source': receipt(raw, 'repo://_system/data/reverse_splits/events.jsonl', 'CIK='+cik+'; ex_date='+day, now)})
    leads = []
    announced = root/'_system/data/reverse_splits/announcements.jsonl'
    if announced.exists():
        for line in announced.read_text(encoding='utf-8').splitlines():
            e = json.loads(line)
            cik = str(int(e['cik'])) if e.get('cik') else None
            if e.get('announce_date', '') < cutoff or len(by_issuer.get(cik, {})) < 2:
                continue
            if e.get('announced_ex_date'):
                day = e['announced_ex_date']
                if not any(c['cik'] == cik and c['effective_day'] == day for c in candidates):
                    candidates.append({'event_id': 'third-plus/'+cik+'/'+day, 'issuer_id': 'cik/'+cik,
                                       'cik': cik, 'ticker': e['ticker'], 'company': e.get('company') or e['ticker'],
                                       'effective_day': day, 'documented_split_ordinal': len([d for d in by_issuer[cik] if d < day])+1,
                                       'action_known_at': e.get('accept_time') or now.isoformat(),
                                       'identity_status': 'announced schedule; completion unverified',
                                       'source': receipt(announced.read_bytes(), 'repo://_system/data/reverse_splits/announcements.jsonl', 'CIK='+cik+'; accession='+str(e.get('accession')), now)})
            else:
                leads.append({'ticker': e.get('ticker'), 'issuer_id': 'cik/'+cik,
                              'announced_at': e.get('accept_time'), 'accession': e.get('accession'),
                              'status': 'Effective split date unresolved; no entry scheduled'})
    return sorted(candidates, key=lambda x: x['event_id']), leads[-100:], {'events_sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(events)}


def input_snapshot(candidate, financials, bars, now):
    by_day = {r['day']: r for r in bars}
    effective = candidate['effective_day']
    prior_days = sessions((datetime.fromisoformat(effective)-timedelta(days=20)).date().isoformat(), effective)
    expected = prior_days[-6:]
    recent = [by_day.get(d) for d in expected]
    rally = 'unknown'
    if len(recent) == 6 and all(recent):
        rally = 'fail' if any(recent[i]['close']/recent[i-1]['close']-1 >= .5 for i in range(1, 6)) else 'pass'
    bar = by_day.get(effective)
    weak = 'unknown'
    if bar and bar['high'] > bar['low']:
        weak = 'pass' if bar['close'] < bar['open'] and (bar['close']-bar['low'])/(bar['high']-bar['low']) <= .25 else 'fail'
    cfo = financials.get('cfo') if financials else None
    burn = 'unknown' if cfo is None else 'pass' if cfo < 0 else 'fail'
    return {k: candidate[k] for k in ['event_id', 'issuer_id', 'ticker', 'company', 'effective_day', 'documented_split_ordinal', 'identity_status']} | {
        'known_at': now.isoformat(), 'signals': {'S7': rally, 'burn': burn, 'S5': weak},
        'action_known_at': candidate['action_known_at'],
        'financial_status': financials.get('status') if financials else 'missing_companyfacts',
        'financial_period': financials.get('period') if financials else None,
        'financial_currency': financials.get('currency') if financials else None,
        'financial_evidence': financials.get('cfo_evidence', []) if financials else [],
        'required_price_sessions': expected, 'completed_price_sessions': [r['day'] for r in recent if r],
        'borrow_assumption': 'Available for research; no approval inferred'}
