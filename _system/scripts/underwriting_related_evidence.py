"""Bounded acquisition-target evidence discovered from primary issuer disclosures.

Models choose search terms, never network destinations. SEC identities, parent
acquisition text and source hashes bind the additional evidence. Target shares
never inherit the parent's listing or split basis.
"""
from __future__ import annotations

import copy
import re
from urllib.parse import urlencode

from underwriting_contract import digest, require
from underwriting_foreign_financials import bounded_sources, source_budget


def name_tokens(name):
    stop = {'inc','incorporated','corp','corporation','company','companies','co','ltd','limited','plc','holdings','group','the'}
    return [x for x in re.findall(r'[a-z0-9]+', name.lower()) if x not in stop]


def acquisition_mentioned(packet, name):
    tokens = name_tokens(name)
    if not tokens:
        return False
    for doc in packet.get('documents') or []:
        for context in doc.get('contexts') or []:
            body = ' '.join(context.lower().split())
            # Match the issuer name as a phrase. Loose words such as "liquidity"
            # and "services" occur throughout unrelated acquisition disclosures.
            phrase = r'\b'+r'\W+'.join(re.escape(t) for t in tokens)+r'\b'
            for match in re.finditer(phrase, body):
                window = body[max(0,match.start()-120):match.end()+120]
                if re.search(r'acquir|acquisit|merg|purchase',window):
                    return True
    return False


def merge_related_packet(parent, target):
    require(acquisition_mentioned(parent,target.get('company') or ''), 'Primary parent evidence does not identify this acquisition')
    require(target.get('currency') == parent.get('currency'), 'Related issuer requires an explicit reporting-currency bridge')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,30}',target.get('ticker') or ''), 'Unsafe related issuer')
    result = copy.deepcopy(parent)
    ticker = target['ticker']
    result.setdefault('related_issuers', {})[ticker] = {k:target.get(k) for k in ('company','cik','latest_report','evidence_hash','source_hash')}
    known = {o['id'] for o in result['observations']}
    for point in target['observations']:
        if point.get('unit') == 'shares':
            continue
        point = copy.deepcopy(point)
        point.update(id='related_'+ticker+'_'+point['id'], issuer_ticker=ticker)
        require(point['id'] not in known, 'Related observation collision')
        known.add(point['id'])
        result['observations'].append(point)
    existing = {d['id']:d for d in result['documents']}
    for document in target['documents']:
        if document['id'] in existing:
            require(existing[document['id']]['content_hash'] == document['content_hash'], 'A primary document changed')
            continue
        result['documents'].append({**copy.deepcopy(document),'issuer_ticker':ticker})
    result['evidence_hash'] = digest({'parent_evidence_hash':parent['evidence_hash'], 'related_issuers':result['related_issuers']})
    result['packet_hash'] = digest({k:v for k,v in result.items() if k != 'packet_hash'})
    return result


@bounded_sources
def collect_target(root, ticker, cik, as_of, currency, keywords=(), client=None):
    from sec_client import SecClient
    from underwriting_evidence import EXTRA_TAGS, _observation, document_record, filing_bytes
    client = client or SecClient(max_attempts=2)
    require(str(cik).isdigit(), 'SEC issuer identity must be numeric')
    base = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
    raw = client.get_json(base,timeout=30)
    submission = client.get_json(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json',timeout=30)
    recent = submission['filings']['recent']
    selected = {}
    for i,form in enumerate(recent['form']):
        if form in ('10-K','10-Q','20-F','40-F','6-K') and form not in selected and recent['filingDate'][i] <= as_of:
            selected[form] = i
    documents = []
    foreign = next((form for form in selected if form in ('10-K','20-F','40-F')), None) in ('20-F','40-F')
    for form,i in list(selected.items())[:3]:
        filename = recent['primaryDocument'][i]
        require(re.fullmatch(r'[A-Za-z0-9_.-]+',filename), 'Unsafe SEC document path')
        accession = recent['accessionNumber'][i]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/{filename}"
        try:
            filing_raw = (source_budget().fetch(url,0,
                lambda value:filing_bytes(root,ticker,accession,client,value))
                if foreign else filing_bytes(root,ticker,accession,client,url))
            doc = document_record(url,filing_raw,keywords,form=form)
            period = recent['reportDate'][i]
            if form == '6-K':
                from valuation_earnings import foreign_reporting_period
                period = foreign_reporting_period(filing_raw,as_of)
                doc['reported_event_date'] = recent['reportDate'][i]
            doc.update(form=form,filed=recent['filingDate'][i],period=period)
            documents.append(doc)
        except (OSError,ValueError):
            if not foreign:
                raise
            from underwriting_foreign_financials import collect_foreign_financials
            documents, proof = collect_foreign_financials(submission,cik,as_of,
                lambda value:client.get_bytes(value,timeout=40))
            require(proof['status']=='complete_current_financial_sources', 'Related foreign financial attachments remain unresolved')
            break
    require(documents, 'Related issuer primary reports are unavailable')
    latest = max(documents,key=lambda d:(d['period'],d['filed']))
    observations = {}
    for tag,concept in raw.get('facts',{}).get('us-gaap',{}).items():
        if tag not in EXTRA_TAGS:
            continue
        for point in concept.get('units',{}).get(currency,[]):
            if (point.get('form') not in ('10-K','10-Q','20-F','40-F','6-K') or point.get('filed','') > as_of
                    or point.get('end','9999') > as_of
                    or point.get('end','') < str(int(as_of[:4])-2)+'-01-01'):
                continue
            row = _observation({'field':tag,'value':point['val'],'period':point['end'],'start':point.get('start'),
                  'currency':currency,'filed':point['filed'],'form':point['form'],'tag':tag,'source_kind':'primary',
                  'source_url':base,'locator':tag+'; '+point.get('accn',''),'scope':ticker+' acquisition target'})
            observations[row['id']] = row
    require(observations, 'Related issuer monetary observations are unavailable in the parent reporting currency')
    target = {'ticker':ticker,'cik':str(cik),'company':submission.get('name') or raw.get('entityName'), 'currency':currency, 'status':'ready',
              'as_of':as_of,'latest_report':{k:latest[k] for k in ('period','filed','source_url')},
              'observations':list(observations.values()),'documents':documents}
    target['source_hash'] = digest({'observations':target['observations'],'latest_report':target['latest_report'],
                                    'documents':[(d['source_url'],d['content_hash']) for d in documents]})
    target['evidence_hash'] = digest({'source_hash':target['source_hash'],'contexts':[d['contexts'] for d in documents]})
    target['packet_hash'] = digest(target)
    return target


def discover_historical_targets(packet, requested, as_of, client, parent_cik=None):
    """Resolve primary legal names when an acquired issuer left the ticker list.

    Search supplies candidate CIKs only. SEC submissions must independently
    confirm the exact legal name and one reported ticker before collection.
    """
    names = []
    pattern = (r'\b([A-Z][A-Za-z0-9&.\'-]*(?:\s+[A-Z][A-Za-z0-9&.\'-]*){0,7}\s+'
               r'(?:Inc\.?|Corporation|Corp\.?|Limited|Ltd\.?|PLC|plc))(?=[\s,;(]|$)')
    for doc in packet.get('documents') or []:
        for context in doc.get('contexts') or []:
            for name in re.findall(pattern, context):
                tokens = name_tokens(name)
                if (tokens and tokens != name_tokens(packet.get('company') or '')
                        and re.search(r'\b'+re.escape(tokens[0])+r'\b', requested, re.I)
                        and acquisition_mentioned(packet, name) and tokens not in [name_tokens(n) for n in names]):
                    names.append(name)
    identities, seen = [], set()
    for name in names[:2]:
        query = 'https://efts.sec.gov/LATEST/search-index?' + urlencode({
            'q': '"'+name+'"', 'forms': '10-K,10-Q', 'dateRange': 'custom',
            'startdt': str(int(as_of[:4])-3)+'-01-01', 'enddt': as_of, 'from': 0, 'size': 20})
        result = client.get_json(query, timeout=30)
        ciks = []
        for hit in (result.get('hits') or {}).get('hits') or []:
            source = hit.get('_source') or {}
            if not source.get('file_date') or source['file_date'] > as_of:
                continue
            for cik in source.get('ciks') or []:
                if (str(cik).isdigit() and int(cik) not in ciks
                        and (not str(parent_cik).isdigit() or int(cik) != int(parent_cik))):
                    ciks.append(int(cik))
        for cik in ciks[:4]:
            url = f'https://data.sec.gov/submissions/CIK{cik:010d}.json'
            issuer = client.get_json(url, timeout=30)
            tickers = issuer.get('tickers') or []
            if (str(issuer.get('cik') or '').isdigit() and int(issuer['cik']) == cik and cik not in seen
                    and name_tokens(issuer.get('name') or '') == name_tokens(name)
                    and acquisition_mentioned(packet, issuer['name']) and len(tickers) == 1
                    and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,30}', tickers[0])
                    and tickers[0] != packet['ticker']):
                identities.append({'ticker': tickers[0], 'cik_str': cik, 'title': issuer['name'],
                                   'identity_discovery': {'method': 'primary_legal_name_and_sec_submissions',
                                                          'search_url': query, 'source_url': url, 'legal_name': name}})
                seen.add(cik)
    return identities


@bounded_sources
def augment_requested_targets(root, packet, gaps, as_of, client=None):
    from sec_client import SecClient
    from underwriting_evidence import requested_keywords, source_fingerprint
    from underwriting_pipeline import read, write
    client = client or SecClient(max_attempts=2)
    requested = ' '.join(str(g.get('detail') or '') for g in gaps).lower()
    if not re.search(r'acquisit|acquir|merger',requested):
        return packet
    if packet.get('primary_reference_usage'):
        source_budget().resume(packet['primary_reference_usage'])
    identities = client.get_json('https://www.sec.gov/files/company_tickers.json',timeout=30)
    parent_cik = (((read(root/'_system/portfolio/registry.json').get('holdings') or {})
                   .get(packet['ticker']) or {}).get('download') or {}).get('cik')
    candidates = []
    for identity in identities.values():
        tokens = name_tokens(identity.get('title') or '')
        if (tokens and str(identity.get('cik_str')).isdigit()
                and (not str(parent_cik).isdigit() or int(identity['cik_str']) != int(parent_cik))
                and re.search(r'\b'+re.escape(tokens[0])+r'\b',requested) and identity.get('ticker') != packet['ticker']
                and acquisition_mentioned(packet,identity['title'])):
            candidates.append(identity)
    if not candidates:
        candidates = discover_historical_targets(packet, requested, as_of, client, parent_cik)
    unique = {}
    for identity in candidates:
        unique.setdefault(str(int(identity['cik_str'])), identity)
    candidates = list(unique.values())
    for identity in candidates[:2]:
        target = collect_target(root,identity['ticker'],identity['cik_str'],as_of,packet['currency'],requested_keywords(gaps),client)
        if identity.get('identity_discovery'):
            target['identity_discovery'] = identity['identity_discovery']
            target['packet_hash'] = digest({k:v for k,v in target.items() if k != 'packet_hash'})
        packet = merge_related_packet(packet,target)
        if any(source_budget().snapshot()['counts']):
            packet['primary_reference_usage'] = source_budget().snapshot()
        path = root/'_system/reference/market-data/valuation_related_evidence'/(target['ticker']+'.json')
        write(path,target)
    if candidates:
        path = root/'_system/reference/market-data/valuation_fundamentals'/(packet['ticker']+'.json')
        data = read(path)
        data['underwriting_related_issuers'] = packet['related_issuers']
        write(path,data)
        packet['input_fingerprint'] = source_fingerprint(root,packet['ticker'])
        packet['packet_hash'] = digest({k:v for k,v in packet.items() if k != 'packet_hash'})
    return packet


@bounded_sources
def refresh_related_sources(root, ticker, as_of):
    from underwriting_pipeline import read, write
    model = read(root/ticker/'research/valuation.json')
    related = (model.get('underwriting') or {}).get('related_issuers') or {}
    for symbol, metadata in list(related.items())[:2]:
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,30}',symbol), 'Unsafe linked issuer')
        path = root/'_system/reference/market-data/valuation_related_evidence'/(symbol+'.json')
        cached = read(path)
        # An acquired issuer can file after the morning refresh on the same day.
        # Recheck on each scheduled collection, just as for the parent issuer.
        try:
            target = collect_target(root,symbol,metadata['cik'],as_of,(model.get('economic_analysis') or {})['currency'])
        except (ValueError,OSError,KeyError,TypeError):
            write(path,{**cached,'source_hash':cached.get('source_hash') or metadata.get('source_hash'),
                        'status':'collection_failed','as_of':as_of})
            raise
        write(path,target)
