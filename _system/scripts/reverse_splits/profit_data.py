"""Source-addressable short-alpha event data. No broker or market-data access.

Future outcomes are kept in a separate analysis object, never event features.
Cached SEC text supplies discovery evidence, not analyst-approved deal terms.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
RUN = '20261013T224003582762Z'
VERSION = 'short_profit_events.v1'
FUTURE_FIELDS = {'financing_60d_after', 'next_reverse_split_2y', 'stopped_trading',
                 'out180', 'out360', 'regain_date', 'delist_date', 'last_bar', 'merged'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError): return None


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def next_day_clock(day):
    return (datetime.fromisoformat(day[:10]).replace(tzinfo=NY) + timedelta(days=1)).isoformat()


def issuer(cik):
    return 'cik/' + str(int(cik))


def key(family, cik, identity):
    return family + '/' + str(int(cik)) + '/' + hashlib.sha256(identity.encode()).hexdigest()[:20]


def sec_filing_url(cik,accession):
    compact=accession.replace('-','')
    if not re.fullmatch(r'\d{18}',compact):raise ValueError('Invalid SEC accession')
    dashed=compact[:10]+'-'+compact[10:12]+'-'+compact[12:]
    return f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/{dashed}.txt'


def distribution(values):
    import numpy as np
    a = np.array([x for x in values if x is not None and math.isfinite(x)], dtype=float)
    if not len(a): return {'n': 0, 'mean': None, 'median': None}
    return {'n': len(a), 'mean': float(a.mean()), 'median': float(np.median(a)),
            'p05': float(np.quantile(a, .05)), 'p95': float(np.quantile(a, .95)),
            'min': float(a.min()), 'max': float(a.max()), 'sd': float(a.std()),
            'stock_positive_fraction': float((a > 0).mean())}


def import_studies(source):
    """Public event metadata; supplied market returns appear only in aggregates."""
    source = Path(source)
    split_file = source / 'research-data_reverse-splits.csv'
    notice_file = source / 'research-data_nasdaq-deficiency-notices.csv'
    splits, notices = rows(split_file), rows(notice_file)
    events, statistics = [], {'split': {}, 'deficiency': {}, 'prior_financing': []}
    seen = set()
    for r in splits:
        identity = key('split', r['cik'], r['effective_date'] + '/' + r['ratio'])
        if identity in seen: raise ValueError('Duplicate split identity')
        seen.add(identity)
        events.append({'id': identity, 'issuer': issuer(r['cik']), 'cik': str(int(r['cik'])),
            'ticker': r['symbol'], 'name': r['company_current_edgar_name'], 'family': 'split',
            'event_date': r['effective_date'], 'known_at': next_day_clock(r['split_8k_filed']) if r['split_8k_filed'] else None,
            'clock_basis': 'filing_date_plus_one_ET_day', 'exchange': r['exchange'],
            'source_url': r['split_8k_url'], 'source_locator': 'split_8k_url; effective_date; ratio',
            'source_dataset': 'microcapledger_reverse_splits', 'review_status': 'provider_record_unverified',
            'features': {'ratio': number(r['ratio']), 'prior_financing_flag': r['financing_60d_before'] == 'True',
                         'prior_financing_verified': False},
            'identity_status': 'provider_symbol_current_name_not_PIT_security_master',
            'event_status': 'provider_effective_action', 'episode_start': True})
    for r in notices:
        identity = key('deficiency', r['cik'], r['adsh'] + '/' + r['type'])
        if identity in seen: raise ValueError('Duplicate notice identity')
        seen.add(identity)
        events.append({'id': identity, 'issuer': issuer(r['cik']), 'cik': str(int(r['cik'])),
            'ticker': r['ticker'], 'name': r['name'], 'family': 'deficiency',
            'event_date': r['file_date'], 'known_at': next_day_clock(r['file_date']),
            'clock_basis': 'filing_date_plus_one_ET_day', 'exchange': r['exchange'],
            'source_url': r['filing_url'], 'source_locator': 'filing_url; file_date; type',
            'source_dataset': 'microcapledger_deficiency_notices', 'accession': r['adsh'],
            'review_status': 'provider_record_unverified', 'features': {'deficiency_type': r['type']},
            'identity_status': 'provider_symbol_not_PIT_security_master',
            'event_status': 'provider_disclosure', 'episode_start': r['episode_start'] == 'True'})
    for h in (0, 1, 5, 20, 60, 120, 250):
        vals = [number(r['ret_' + str(h)]) for r in splits if r['status_' + str(h)] == 'trading']
        statistics['split'][str(h)] = {**distribution(vals), 'statuses': dict(Counter(r['status_' + str(h)] for r in splits))}
        statistics['prior_financing'].append({'horizon': h, **{flag: distribution([
            number(r['ret_' + str(h)]) for r in splits if r['status_' + str(h)] == 'trading'
            and (r['financing_60d_before'] == 'True') == (flag == 'yes')]) for flag in ['yes', 'no']}})
    for h in (1, 20, 60, 250):
        statistics['deficiency'][str(h)] = {kind: distribution([number(r['r' + str(h)]) for r in notices
            if r['type'] == kind or kind == 'all']) for kind in ['all', 'bid', 'equity', 'mvls', 'late', 'governance']}
    statistics['method'] = 'Provider raw stock returns, pre-split-close or provider filing window; not short P&L. Changing horizon denominators and terminal-price treatment retained.'
    return events, statistics, [{'file': f.name, 'sha256': digest(f), 'rows': len(v)} for f, v in [(split_file, splits), (notice_file, notices)]]


def plain_text(raw):
    # Keep the primary SEC report plus exhibits, but never parse binary attachments.
    docs = re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>', raw, re.S | re.I)
    if docs:
        chosen = []
        for doc in docs:
            kind = re.search(r'<TYPE>\s*([^\r\n<]+)', doc, re.I)
            if kind and re.match(r'(?:8-K|6-K|424B\d|S-[13]|F-[13]|EX-(?:4|10|99))', kind[1], re.I): chosen.append(doc)
        raw = '\n'.join(chosen)
    raw = re.sub(r'<(?:script|style|ix:header)\b.*?</(?:script|style|ix:header)>', ' ', raw, flags=re.S | re.I)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    return re.sub(r'\s+', ' ', html.unescape(raw)).strip()


FINANCING = {
    'registered_direct': r'registered direct offering',
    'public_offering': r'(?:pricing|priced|closing|closed|completed).{0,90}(?:public offering|underwritten offering)',
    'private_placement': r'(?:entered|closed|completed|closing).{0,100}(?:securities purchase|private placement)',
    'atm': r'at.the.market.{0,80}(?:offering|sales|agreement)|equity distribution agreement',
    'equity_line': r'equity (?:line|purchase facility)|committed equity (?:facility|financing)',
    'convertible': r'(?:issued|issuance|entered|purchase).{0,90}convertible (?:notes?|preferred|debentures)',
    'warrant_inducement': r'warrant (?:inducement|exercise inducement)|inducement.{0,80}exercise',
}
ANCHORS = {
    'registered_direct': ('registered direct offering',),
    'public_offering': ('public offering','underwritten offering'),
    'private_placement': ('securities purchase','private placement'),
    'atm': ('at-the-market','at the market','equity distribution agreement'),
    'equity_line': ('equity line','equity purchase facility','committed equity facility','committed equity financing'),
    'convertible': ('convertible note','convertible preferred','convertible debenture'),
    'warrant_inducement': ('inducement',),
}
RESET = r'alternat(?:e|ive) cashless|(?:exercise|conversion) price.{0,130}(?:reset|reduc|adjust)|variable conversion|(?:reset|ratchet).{0,80}(?:price|warrant|convert)'
EXECUTED = r'(?:closed|completed|consummated|issued and sold).{0,100}(?:offering|placement|shares|notes)|(?:pricing|priced).{0,100}(?:offering|placement)|entered into.{0,70}securities purchase agreement'
CAPACITY = r'(?:sales|distribution|purchase) agreement|shelf registration|registration statement|may.{0,60}(?:sell|issue)'


def classify_financing(text, filed_at=None):
    """Conservative lead extraction; history/boilerplate never becomes verified issuance."""
    findings = []
    lower=text.lower()
    for label, pattern in FINANCING.items():
        candidates=[]
        for anchor in ANCHORS[label]:
            cursor=0
            for _ in range(12):
                at=lower.find(anchor,cursor)
                if at<0:break
                start,end=max(0,at-200),min(len(text),at+700)
                match=re.search(pattern,text[start:end],re.I)
                if match:
                    offset=start+match.start()
                    candidates.append((offset,max(0,offset-200),min(len(text),start+match.end()+500)))
                cursor=at+len(anchor)
        for offset,start,end in sorted(set(candidates))[:2]:
            findings.append({'type':label,'excerpt':text[start:end],
                             'locator':f'normalized_text[{start}:{end}]','offset':offset})
    if not findings: return None
    # A disclosure is one discovery, not one trade per keyword or exhibit.
    findings.sort(key=lambda r: r['offset'])
    context = ' '.join(r['excerpt'] for r in findings)
    state = 'terms_disclosed' if re.search(EXECUTED, context, re.I) else 'capacity_or_context'
    date_pattern=r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2}'
    origins=[]
    for match in re.finditer(r'\bon\s+('+date_pattern+r').{0,150}?(?:entered into|executed|closed|completed).{0,100}?(?:purchase agreement|offering|placement|financing)',context,re.I):
        value=re.sub(r'\s+',' ',match[1].replace(',','')).title()
        try:origins.append(datetime.strptime(value,'%B %d %Y').date().isoformat())
        except ValueError:pass
    origin=min(origins,default=None)
    if re.search(r'(?:entered into|executed|effective).{0,160}(?:amendment|amended).{0,100}(?:purchase|financing|warrant|conversion|preferred)',context,re.I):
        state='amendment_terms_disclosed'
    elif origin and filed_at and re.search(r'previously (?:disclosed|reported)',context,re.I) and (datetime.fromisoformat(filed_at[:10]).date()-datetime.fromisoformat(origin).date()).days>30:
        state='historical_context'
    elif re.search(r'as previously (?:disclosed|reported)',context,re.I) and not origin:
        state='historical_context'
    if re.search(r'(?:terminat|cancel|withdraw).{0,80}(?:offering|purchase agreement|sales agreement)', context, re.I): state = 'termination_or_context'
    return {'state': state, 'types': sorted({r['type'] for r in findings}), 'variable_terms': bool(re.search(RESET, context, re.I)),
            'origin_contract_date':origin,'link_status':'inferred_contract_date' if origin else 'unlinked_accession',
            'passages': findings[:4], 'normalized_text_sha256': hashlib.sha256(text.encode()).hexdigest()}


def cached_financings(root, *, since='2021-01-01', max_files=25000):
    root = Path(root).resolve()
    local = root / '_system/data/reverse_splits/local'
    db = local / f'expansion/expansion_v2/runs/{RUN}/input.sqlite'
    conn = sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)
    conn.row_factory = sqlite3.Row
    raw_rows = [dict(r) for r in conn.execute("SELECT accession,cik,ticker,form,filed_at,available_at,clock_basis,text_file FROM disclosures WHERE filed_at>=? AND form IN ('8-K','8-K/A','6-K','6-K/A') ORDER BY filed_at,accession", (since,))]
    conn.close()
    out, coverage, inputs = [], Counter(), []
    for file_index, r in enumerate(raw_rows[:max_files]):
        if file_index % 1000 == 0: print('SEC cache scan', file_index, '/', min(max_files,len(raw_rows)), 'contexts', len(out), flush=True)
        p = (root / r['text_file']).resolve()
        if not p.is_relative_to(local.resolve()): raise ValueError('Source escapes local research cache')
        coverage['filings_considered'] += 1
        if not p.is_file(): coverage['missing_text'] += 1; continue
        if p.stat().st_size > 30_000_000: coverage['oversize_text'] += 1; continue
        raw = p.read_text(encoding='utf-8', errors='replace')
        lower = raw.lower()
        if not any(term in lower for term in ('offering','securities purchase','private placement','equity line','convertible','cashless','warrant inducement')): continue
        text = plain_text(raw)
        result = classify_financing(text,r['filed_at'])
        if not result: continue
        coverage['financing_contexts'] += 1
        stamp, clock = r['available_at'], r['clock_basis']
        full = local / 'raw/edgar' / f"{int(r['cik']):010d}" / (r['accession'].replace('-', '') + '.full.txt')
        if full.exists():
            with full.open(encoding='utf-8',errors='replace') as f: header=f.read(16000)
            bound_cik=re.search(r'CENTRAL INDEX KEY:\s*(\d+)',header)
            bound_accession=re.search(r'ACCESSION NUMBER:\s*(\d{10}-\d{2}-\d{6})',header)
            accepted=re.search(r'<ACCEPTANCE-DATETIME>\s*(20\d{12})',header)
            if bound_cik and int(bound_cik[1])==int(r['cik']) and bound_accession and bound_accession[1].replace('-','')==r['accession'].replace('-','') and accepted:
                stamp=datetime.strptime(accepted[1],'%Y%m%d%H%M%S').replace(tzinfo=NY).isoformat()
                clock='issuer_accession_bound_SEC_acceptance_ET'
        if not stamp: stamp, clock = next_day_clock(r['filed_at']), 'filing_date_plus_one_ET_day'
        compact = r['accession'].replace('-', '')
        source = sec_filing_url(r['cik'],compact)
        file_hash = digest(p)
        out.append({'id': key('financing', r['cik'], compact), 'deal_id': key('deal', r['cik'], result['origin_contract_date'] or compact),
            'issuer': issuer(r['cik']), 'cik': str(int(r['cik'])), 'ticker': r['ticker'], 'name': '',
            'family': 'financing', 'event_date': r['filed_at'], 'known_at': stamp,
            'clock_basis': clock, 'exchange': None, 'source_url': source, 'accession': r['accession'],
            'form': r['form'], 'source_locator': result['passages'][0]['locator'], 'source_sha256': file_hash,
            'source_dataset': 'cached_SEC_disclosures', 'review_status': 'extracted_context_requires_review',
            'identity_status': 'cached_CIK_ticker_requires_security_review', 'event_status': result['state'],
            'episode_start': True, 'features': {'financing_types': result['types'], 'variable_terms_flag': result['variable_terms'],
                'origin_contract_date':result['origin_contract_date'],'deal_link_status':result['link_status'],
                'quantified_saleable_supply': None, 'net_proceeds': None, 'terms_verified': False},
            'passages': result['passages'], 'normalized_text_sha256': result['normalized_text_sha256']})
        inputs.append({'accession': compact, 'sha256': file_hash})
    coverage['discovered_metadata_rows'] = len(raw_rows)
    coverage['file_limit_applied'] = max(0, len(raw_rows) - max_files)
    return out, dict(coverage), fingerprint(inputs)


def attach_financials(events, root, work):
    """As-filed feature cache keyed by original companyfacts bytes and event clock."""
    from .net_edge_evidence import filing_rating
    from _system.scripts import build_short_quant_screen as screen
    facts = Path(root) / '_system/data/reverse_splits/local/raw/companyfacts'
    cache = Path(work) / 'financial_features.local.json'
    saved = read(cache) if cache.exists() else {}
    grouped = defaultdict(list)
    for event in events:
        if event.get('known_at'): grouped[event['cik']].append(event)
    coverage = Counter()
    for cik, group in grouped.items():
        path = facts / f'CIK{int(cik):010d}.json'
        if not path.exists(): coverage['issuers_missing_companyfacts'] += 1; continue
        file_hash = digest(path)
        raw = None
        for event in group:
            ck = fingerprint([event['id'], event['known_at'], file_hash, 'PIT.v1'])
            if ck not in saved:
                if raw is None: raw = read(path)
                result = filing_rating(raw, event['known_at'], screen, expected_cik=cik)
                cash = result.get('balances', {}).get('cash')
                cfo = result.get('flows', {}).get('cfo')
                runway = cash / -cfo if cash is not None and cfo is not None and cfo < 0 else None
                saved[ck] = {'cash': cash, 'ttm_cfo': cfo, 'runway_years': runway,
                    'score': result['score'], 'period': result.get('period'), 'currency': result.get('currency'),
                    'cash_pressure': runway is not None and runway <= 1,
                    'cash_pressure_known': runway is not None, 'status': result['status'],
                    'source_sha256': file_hash, 'source_url': f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',
                    'evidence': [{k: r.get(k) for k in ('tag', 'end', 'filed', 'accn', 'val')} for r in result.get('evidence', [])]}
            event['financials'] = saved[ck]
            coverage['events_with_financial_file'] += 1
            if saved[ck]['cash_pressure_known']: coverage['events_with_runway'] += 1
        if coverage['events_with_financial_file'] % 100 < len(group):
            write(cache, saved)
            print('Dated financial features', coverage['events_with_financial_file'], flush=True)
    write(cache, saved)
    return dict(coverage)


def apply_terms_reviews(events, records):
    """Only complete, date-bound primary-document reviews can populate saleable supply."""
    index = {e['id']: e for e in events}
    for review in records:
        e = index.get(review['event_id'])
        if not e: raise ValueError('Review references unknown event')
        if review['kind'] != 'terms': continue
        known = datetime.fromisoformat(e['known_at'])
        if datetime.fromisoformat(review['evidence_known_at']) > known: raise ValueError('Later terms cannot rewrite an earlier event')
        f = e['features']
        f.update(terms_verified=True, quantified_saleable_supply=review['saleable_shares'],
                 shares_before=review['shares_before'], net_proceeds=review['net_proceeds'],
                 economic_state=review['economic_state'])
        e['review_status'] = 'primary_terms_reconciled'
        e['event_status'] = 'primary_terms_reconciled' if review['economic_state']!='terminated' else 'termination_or_context'
        e['terms_review'] = review


def materialize_events(work,root):
    """Join append-only public discoveries and source reviews without rewriting inputs."""
    from .profit_evidence import load
    work=Path(work)
    events=read(work/'events.local.json')
    for event in events:
        if event['source_dataset']=='cached_SEC_disclosures':
            event['source_url']=sec_filing_url(event['cik'],event['accession'])
            event['locator_basis']='cached_primary_text_normalized.v1'
            event['source_hash_basis']='cached_primary_text_bytes_not_raw_complete_submission'
    ids={e['id'] for e in events}
    public=work/'public_discovery.local.json'
    if public.exists():
        for r in read(public)['records']:
            identity=key('financing',r['cik'],r['accession'].replace('-',''))
            if identity in ids:continue
            parsed=r['classification']
            ticker,name=r.get('ticker') or '',r.get('name') or ''
            if not ticker:
                url=f'https://data.sec.gov/submissions/CIK{int(r["cik"]):010d}.json'
                cache=work/'public_cache'/(hashlib.sha256(url.encode()).hexdigest()+'.raw')
                if cache.exists():
                    submission=read(cache);ticker=(submission.get('tickers') or [''])[0];name=submission.get('name','')
            events.append({'id':identity,'deal_id':key('deal',r['cik'],r['accession'].replace('-','')),
                'issuer':issuer(r['cik']),'cik':r['cik'],'ticker':ticker,'name':name,
                'family':'financing','event_date':datetime.fromisoformat(r['known_at']).astimezone(NY).date().isoformat(),'known_at':r['known_at'],
                'clock_basis':'SEC_submission_acceptance_or_next_ET_day','source_url':r['source_url'],
                'source_sha256':r['source_sha256'],'accession':r['accession'],'form':r['form'],
                'source_locator':parsed['passages'][0]['locator'],'source_dataset':'public_SEC_submissions',
                'review_status':'extracted_context_requires_review','identity_status':'submission_ticker_requires_security_review',
                'event_status':parsed['state'],'episode_start':True,'features':{'financing_types':parsed['types'],
                'variable_terms_flag':parsed['variable_terms'],'quantified_saleable_supply':None,'net_proceeds':None,'terms_verified':False},
                'passages':parsed['passages'],'captured_at':r['captured_at']})
            ids.add(identity)
    records=[r['record'] for r in load(work)]
    apply_terms_reviews(events,[r for r in records if r['kind']=='terms'])
    events.sort(key=lambda e:(datetime.fromisoformat(e['known_at']).timestamp() if e.get('known_at') else float('inf'),e['id']))
    seen_states=set()
    for e in events:
        if e['family']!='financing':continue
        state=(e['issuer'],e.get('deal_id'),e['event_status'])
        e['features']['first_state_disclosure']=state not in seen_states
        seen_states.add(state)
    write(work/'effective_events.local.json',events)
    write(work/'review_queue.json',audit_queue(events))
    return events


def audit_queue(events, n=100):
    """Outcome-independent, stratified review panel, including unknown features."""
    buckets = defaultdict(list)
    for e in events:
        category = e['family'] + '/' + (e['features'].get('financing_types', [None])[0] or e['features'].get('deficiency_type', 'split'))
        buckets[category].append(e)
    for group in buckets.values(): group.sort(key=lambda e: hashlib.sha256(e['id'].encode()).hexdigest())
    selected=[]
    while len(selected) < n and any(buckets.values()):
        for label in sorted(buckets):
            if buckets[label] and len(selected) < n: selected.append(buckets[label].pop(0))
    return [{'event_id': e['id'], 'ticker': e['ticker'], 'family': e['family'], 'date': e['event_date'],
             'source_url': e['source_url'], 'locator': e['source_locator'], 'status': e['review_status'],
             'passages': e.get('passages', []), 'checks': {'identity': None, 'clock': None, 'economic_state': None,
             'cash_and_shares': None, 'saleability': None, 'second_review': None}} for e in selected]


def validate_event(event):
    if any(k in event.get('features', {}) for k in FUTURE_FIELDS): raise ValueError('Future label in features')
    if not event.get('source_url', '').startswith('https://'): raise ValueError('Missing primary/source URL')
    if not event.get('source_locator'): raise ValueError('Missing source locator')
    if event.get('known_at'):
        if datetime.fromisoformat(event['known_at']).utcoffset() is None: raise ValueError('Naive event clock')
    return event


def publish_events(events, destination):
    dest = Path(destination)
    groups = defaultdict(list)
    for e in events:
        validate_event(e)
        groups[e['family'] + '-' + e['event_date'][:4]].append(e)
    parts=[]
    for name, group in sorted(groups.items()):
        file = dest / ('events-' + name + '.json')
        write(file, {'schema_version': VERSION, 'events': group})
        parts.append({'file': file.name, 'rows': len(group), 'sha256': digest(file), 'bytes': file.stat().st_size})
    return parts
