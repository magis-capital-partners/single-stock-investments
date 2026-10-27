"""Discovery, evidence caching, history and atomic screener publication."""
from __future__ import annotations
import gzip
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from aggregates_facts import financial_history, balance_at
from aggregates_operating_metrics import METRICS, operating_periods
from aggregates_extract import parse_tables

VERSION='aggregates.v2'
PEERS={'VMC':'aggregates_focused','MLM':'aggregates_focused','CRH':'integrated_materials','AMRZ':'integrated_materials','KNF':'integrated_materials','ACA':'integrated_materials','GVA':'contractors_asphalt','ROAD':'contractors_asphalt','EXP':'cement','USLM':'lime','CX':'cement'}
REGISTRY={
 'TTAM':{'cik':'0002035304','currency':'USD','shares_per_listing_unit':1},
 'VMC':{'cik':'0001396009','currency':'USD','shares_per_listing_unit':1},
 'MLM':{'cik':'0000916076','currency':'USD','shares_per_listing_unit':1},
 'KNF':{'cik':'0001955520','currency':'USD','shares_per_listing_unit':1},
 'ACA':{'cik':'0001739445','currency':'USD','shares_per_listing_unit':1},
 'CRH':{'cik':'0000849395','currency':'USD','shares_per_listing_unit':1,'listing_unit_valid_from':'2023-09-25'},
 'AMRZ':{'cik':'0002035989','currency':'USD','shares_per_listing_unit':1,'listing_unit_valid_from':'2025-06-23'},
 'GVA':{'cik':'0000861459','currency':'USD','shares_per_listing_unit':1},
 'ROAD':{'cik':'0001718227','currency':'USD','shares_per_listing_unit':1,
         'identity_source_url':'https://www.sec.gov/Archives/edgar/data/1718227/000162828026054661/road-20260630.htm',
         'identity_locator':'Note 9: Class A and B identical except voting, conversion and transfer restrictions; cover gives both classes on the same date'},
 'EXP':{'cik':'0000918646','currency':'USD','shares_per_listing_unit':1},
 'USLM':{'cik':'0000082020','currency':'USD','shares_per_listing_unit':1},
 'CX':{'cik':'0001076378','currency':'USD','shares_per_listing_unit':10,
       'share_unit':'CPO','listing_unit':'ADS',
       'identity_source_url':'https://www.sec.gov/Archives/edgar/data/1076378/000119312526177605/d120395d20f.htm',
       'identity_locator':'20-F cover: each ADS represents ten CPOs; reported outstanding security is CPOs'},
}
PEERS['TTAM']='integrated_materials'


def local_companyfacts(ticker, root, cache):
    """Reuse full local inline XBRL, accepting consolidated contexts only."""
    from buyback_facts import parse_filing_facts
    files=sorted((root/ticker/'investor-documents').glob('**/10-*_rpt*_acc*.htm'),reverse=True)
    if not files:return None
    signature=hashlib.sha256(json.dumps([(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files]).encode()).hexdigest()
    cached=cache/(ticker+'-inline-'+signature+'.gz')
    if cached.exists():return json.loads(gzip.decompress(cached.read_bytes()))
    facts={};annual=0;quarter=0
    for path in files:
        match=re.search(r'(10-[KQ])_(\d{8})_rpt(\d{8})_acc(\d{10})_(\d{2})_(\d{6})',path.name)
        if not match:continue
        form,filed,end,cik,yy,seq=match.groups()
        if form=='10-K':
            annual+=1
            if annual>6:continue
        else:
            quarter+=1
            if quarter>13:continue
        accession=f'{cik}-{yy}-{seq}';filed=f'{filed[:4]}-{filed[4:6]}-{filed[6:]}'
        rows=parse_filing_facts(path.read_text(encoding='utf-8',errors='replace'),accession=accession,filed=filed,url='')
        for r in rows:
            if r['scope']!='entity' or not r.get('end') or ':' not in r['tag']:continue
            namespace,tag=r['tag'].split(':',1)
            if namespace not in {'us-gaap','dei'}:continue
            unit='shares' if 'share' in str(r.get('unit')).lower() else 'USD' if 'usd' in str(r.get('unit')).lower() else None
            if unit is None:continue
            entry={'val':r['value'],'end':r['end'],'form':form,'filed':filed,'accn':accession}
            if r.get('start'):entry['start']=r['start']
            facts.setdefault(namespace,{}).setdefault(tag,{'units':{}})['units'].setdefault(unit,[]).append(entry)
    result={'facts':facts,'entityName':ticker}
    cache.mkdir(parents=True,exist_ok=True);cached.write_bytes(gzip.compress(json.dumps(result).encode()))
    return result


def dump(path, doc):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8');temp.replace(path)


def bounded_facts(facts,earliest_year):
    """Bound the published history, retaining the full cached SEC response."""
    cutoff=f'{earliest_year}-01-01'
    return {**facts,'facts':{namespace:{tag:{**block,'units':{
        unit:[row for row in rows if str(row.get('end') or '')>=cutoff]
        for unit,rows in block.get('units',{}).items()}}
        for tag,block in tags.items()} for namespace,tags in facts.get('facts',{}).items()}}


def request(url, cache, offline=False):
    path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.gz')
    if path.exists() and (offline or '/Archives/' in url or time.time()-path.stat().st_mtime<24*3600):return gzip.decompress(path.read_bytes()).decode('utf-8',errors='replace')
    if offline:raise OSError('Source is not cached')
    req=urllib.request.Request(url,headers={'User-Agent':'Magis Research research@magiscapital.com','Accept-Encoding':'identity'})
    try:
        with urllib.request.urlopen(req,timeout=20) as response:body=response.read().decode('utf-8',errors='replace')
        cache.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(body.encode()));time.sleep(.12);return body
    except OSError:
        if path.exists():return gzip.decompress(path.read_bytes()).decode('utf-8',errors='replace')
        raise


def reviewed_share_totals(rows,ticker):
    """ROAD's two economically identical classes, explicitly reviewed in Note 9."""
    if ticker!='ROAD':return []
    groups={}
    for row in rows:
        if row['tag']!='dei:EntityCommonStockSharesOutstanding' or row.get('start'):continue
        if row['scope'] not in {'us-gaap:CommonClassAMember','us-gaap:CommonClassBMember'}:continue
        groups.setdefault(row['end'],{}).setdefault(row['scope'],[]).append(row)
    result=[]
    for end,classes in groups.items():
        if len(classes)!=2 or any(len({r['value'] for r in part})!=1 for part in classes.values()):continue
        inputs=[part[0] for part in classes.values()]
        result.append({**inputs[0],'scope':'entity','value':sum(r['value'] for r in inputs),
                       'status':'derived','inputs':inputs,'locator':'10-Q cover Class A + Class B; Note 9 identical economic rights'})
    return result


def supplement_filing_facts(facts,ticker,cache,offline=False):
    """Fill companyfacts omissions from the latest primary inline filings.

    A companyfacts observation wins for the same concept/period. Conflicting
    inline duplicates are excluded instead of letting a note's scale overwrite
    a consolidated statement. Class-specific counts remain separate.
    """
    from buyback_facts import parse_filing_facts
    config=REGISTRY[ticker]
    submissions=json.loads(request(f"https://data.sec.gov/submissions/CIK{config['cik']}.json",cache,offline))
    recent=submissions.get('filings',{}).get('recent',{})
    result=json.loads(json.dumps(facts))
    chosen=[]
    for i,form in enumerate(recent.get('form',[])):
        if form in {'10-K','10-Q','20-F','40-F'} and form not in [recent['form'][j] for j in chosen]:chosen.append(i)
        if len(chosen)>=2:break
    for i in chosen:
        accession=recent['accessionNumber'][i]
        url=f"https://www.sec.gov/Archives/edgar/data/{int(config['cik'])}/{accession.replace('-','')}/{recent['primaryDocument'][i]}"
        raw=parse_filing_facts(request(url,cache,offline),accession=accession,filed=recent['filingDate'][i],url=url)
        raw.extend(reviewed_share_totals(raw,ticker))
        grouped={}
        for row in raw:
            if row['scope']!='entity' or not row.get('end') or ':' not in row['tag']:continue
            namespace,tag=row['tag'].split(':',1)
            if namespace not in {'us-gaap','ifrs-full','dei'}:continue
            unit='shares' if 'share' in str(row['unit']).lower() else 'USD' if 'usd' in str(row['unit']).lower() else None
            if unit is not None:grouped.setdefault((namespace,tag,unit,row.get('start'),row['end']),[]).append(row)
        for (namespace,tag,unit,start,end),rows in grouped.items():
            if len({r['value'] for r in rows})!=1:continue
            target=result.setdefault('facts',{}).setdefault(namespace,{}).setdefault(tag,{'units':{}})['units'].setdefault(unit,[])
            if any(r.get('start')==start and r['end']==end for r in target):continue
            entry={'val':rows[0]['value'],'end':end,'filed':recent['filingDate'][i],'accn':accession,'form':recent['form'][i]}
            if rows[0].get('inputs'):
                entry.update(inputs=rows[0]['inputs'],locator=rows[0]['locator'],status='derived')
            if start:entry['start']=start
            target.append(entry)
    return result


def discover(ticker,root,cache,offline=False,limit=32):
    config=REGISTRY[ticker];cik=config['cik'];items=[];errors=[]
    try:
        submissions=json.loads(request(f'https://data.sec.gov/submissions/CIK{cik}.json',cache,offline))
        files=[submissions.get('filings',{}).get('recent',{})]
        for part in submissions.get('filings',{}).get('files',[])[:2]:
            if str(part.get('filingTo',''))[:4]>=str(datetime.now().year-6):
                try:files.append(json.loads(request('https://data.sec.gov/submissions/'+part['name'],cache,offline)))
                except (OSError,ValueError):pass
        for recent in files:
            for i,form in enumerate(recent.get('form',[])):
                if form not in {'10-K','10-K/A','10-Q','10-Q/A','20-F','20-F/A','40-F'}:continue
                end=recent.get('reportDate',[])[i]
                if end[:4]<str(datetime.now().year-6):continue
                accession=recent['accessionNumber'][i]
                items.append({'ticker':ticker,'issuer_id':'cik:'+cik,'accession':accession,'form':form,'period_end':end,'published_at':recent['filingDate'][i],
                    'source_url':f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/{recent['primaryDocument'][i]}",
                    'retrieved_at':datetime.now(timezone.utc).isoformat()})
    except (OSError,ValueError,IndexError) as e:errors.append(str(e))
    records=[]
    for meta in sorted(items,key=lambda r:r['period_end'],reverse=True)[:limit]:
        try:records.extend(parse_tables(request(meta['source_url'],cache,offline),meta))
        except (OSError,ValueError) as e:errors.append(meta['accession']+': '+str(e))
    # Existing downloaded filing evidence is useful when public transport is down.
    for path in sorted((root/ticker/'investor-documents').glob('**/10-*_rpt*_acc*.htm')):
        match=re.search(r'(10-[KQ])_(\d{8})_rpt(\d{8})_acc(\d{10})_(\d{2})_(\d{6})',path.name)
        if not match:continue
        form,filed,end,cikpart,yy,seq=match.groups();accession=f'{cikpart}-{yy}-{seq}'
        meta={'ticker':ticker,'issuer_id':'cik:'+cik,'accession':accession,'form':form,'period_end':f'{end[:4]}-{end[4:6]}-{end[6:]}','published_at':f'{filed[:4]}-{filed[4:6]}-{filed[6:]}','retrieved_at':datetime.now(timezone.utc).isoformat(),'source_url':f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/"}
        try:records.extend(parse_tables(path.read_text(encoding='utf-8',errors='replace'),meta))
        except ValueError as e:errors.append(path.name+': '+str(e))
    return records,errors


def enrich(row, sec, operating, quote, builder, previous=None):
    ticker=row['ticker'];config=REGISTRY[ticker]
    periods=operating_periods([r for r in operating if r['ticker']==ticker])
    latest={kind:next((p for p in reversed(periods) if p['period_type']==kind),None) for kind in ['FY','Q','TTM']}
    relevant=latest['FY'] or latest['Q']
    financial=sec.get('financial_history',[])
    sources=sec.get('financial_observations',[])
    for item in sources:item['ticker']=ticker
    history=[]
    for period in financial:
        end=period['period_end'];balance=balance_at(sources,end)
        scoped={**period,**{k:v for k,v in balance.items() if k!='sources'}}
        history.append({**period,**builder.compute_rock_metrics(scoped,None,None)})
    safe_quote=quote and quote.get('currency')==config['currency'] and config['shares_per_listing_unit'] is not None and sec.get('shares_outstanding') and sec.get('shares_as_of')
    warnings=[]
    if not safe_quote:warnings.append(config.get('reason','A dated quote, currency and matching share class are required for valuation.'))
    elif not 0<=(datetime.fromisoformat(quote['as_of'].replace('Z','+00:00')).date()-datetime.fromisoformat(sec['shares_as_of']).date()).days<=120:
        warnings.append('Share count must precede the quote by no more than 120 days.');safe_quote=False
    price=quote.get('price') if safe_quote else None
    mcap=price*sec['shares_outstanding']/config['shares_per_listing_unit'] if price else None
    metrics=builder.compute_rock_metrics(sec,price,mcap)
    missing=[k for k in ['shipments_million_tons','price_per_ton','cash_gp_per_ton','organic_volume_growth_pct','reserve_life_years'] if not relevant or k not in relevant['metrics']]
    row={**row,**{k:v for k,v in sec.items() if k.endswith('_usd') or k in {'fiscal_year_end','filing_as_of','shares_outstanding','shares_as_of','debt_basis'}},**metrics,'schema_version':VERSION,'peer_group':PEERS[ticker],'is_pure_rock':PEERS[ticker]=='aggregates_focused',
        'quote':quote,'valuation_warnings':warnings,'operating_latest':latest,'operating_coverage':{'available':len(relevant['metrics']) if relevant else 0,'required_missing':missing,'FY':sum(p['period_type']=='FY' for p in periods),'Q':sum(p['period_type']=='Q' for p in periods)},
        'financial_status':'verified' if sec.get('financial_sources') else 'unverified_legacy','financial_basis':sec.get('flow_basis') or 'legacy snapshot; source periods require refresh',
        'financial_as_of':sec.get('fiscal_year_end') or row.get('fiscal_year_end'),'balance_as_of':sec.get('filing_as_of'),
        'reserve_life_years':relevant['metrics'].get('reserve_life_years',{}).get('value') if relevant else None,
        'cash_gross_profit_per_ton':relevant['metrics'].get('cash_gp_per_ton',{}).get('value') if relevant else None}
    # Old display strings cannot resurrect a valuation withheld by the new contract.
    for key,metric,fmt in [('ev_ebitda_display','ev_ebitda',builder.fmt_multiple),('fcf_yield_display','fcf_yield_pct',builder.fmt_pct),('net_debt_ebitda_display','net_debt_ebitda',builder.fmt_multiple),('roic_display','roic_average_pct',builder.fmt_pct)]:row[key]=fmt(metrics.get(metric))
    detail={'ticker':ticker,'company':row['company'],'schema_version':VERSION,'operating_history':periods,'financial_history':history,'financial_sources':sec.get('financial_sources',[]),'balance_sources':sec.get('balance_sources',[]),'identity':config,'quote':quote,'warnings':warnings,'research_tasks':[{'metric':key,'reason':'Not disclosed or extraction/definition requires review','next_action':'Inspect latest aggregates segment tables and primary filing.'} for key in missing]}
    digest=hashlib.sha256(json.dumps(detail,sort_keys=True).encode()).hexdigest()[:20]
    row['detail_ref']=f'aggregates/details/{ticker}-{digest}.json'
    return row,detail


def publish(root, rows, details, errors):
    from build_rock_aggregates_screener import build_payload
    payload=build_payload(rows);payload['schema_version']=VERSION;payload['generated_at']=datetime.now(timezone.utc).isoformat()
    payload['coverage']={'issuers':len(rows),'operating':sum(bool(r.get('operating_latest',{}).get('FY')) for r in rows),'financial_verified':sum(r.get('financial_status')=='verified' for r in rows),'failures':errors}
    payload['criteria']='Period-aligned FULL-YEAR financial comparisons and separately sourced aggregates operations. Corporate EBITDA is an operating-income-plus-DD&A proxy; ROIC uses a labeled 21% tax assumption. Missing observations are never zero.'
    candidate_path=root/'_system/reference/market-data/screens/rock_aggregates_candidates.json'
    candidates=json.loads(candidate_path.read_text(encoding='utf-8')) if candidate_path.exists() else {}
    payload['discovery']=candidates.get('rows',[])
    payload['retired']=candidates.get('retired',[])
    for row,detail in zip(rows,details):dump(root/'dashboard/data'/row['detail_ref'],detail)
    dump(root/'dashboard/data/rock_aggregates_screener.json',payload)
    return payload


def check(root):
    payload=json.loads((root/'dashboard/data/rock_aggregates_screener.json').read_text(encoding='utf-8'))
    assert payload['schema_version']==VERSION
    assert payload['row_count']==len(payload['rows'])
    for row in payload['rows']:
        ref=row['detail_ref']
        assert re.fullmatch(r'aggregates/details/[A-Z]+-[a-f0-9]{20}\.json',ref)
        detail=json.loads((root/'dashboard/data'/ref).read_text(encoding='utf-8'))
        assert detail['ticker']==row['ticker']
        for period in detail['operating_history']:
            for metric in period['metrics'].values():
                assert metric.get('source_url') and metric.get('locator')
    return payload


def run(root, *, offline=False, refresh_operating=False, write=True):
    import build_rock_aggregates_screener as builder
    ledger=root/'_system/data/aggregates/observations.jsonl'
    operating=[json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines() if line.strip()] if ledger.exists() else []
    cache=root/'_system/data/aggregates/cache'
    try:prior=json.loads((root/'dashboard/data/rock_aggregates_screener.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):prior={}
    baseline={r['ticker']:r for r in prior.get('rows',[])}
    holdings,watchlist=builder.load_registry_sets()
    rows=[];details=[];errors={}
    for seed in builder.load_seed_rows():
        ticker=seed['ticker'];config=REGISTRY[ticker];old=baseline.get(ticker,{})
        error=[];sec={};quote=None;prices=[]
        try:
            facts=json.loads(request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{config['cik']}.json",cache,offline))
            try:facts=supplement_filing_facts(facts,ticker,cache,offline)
            except (OSError,ValueError,KeyError,IndexError) as exc:error.append('Inline filing supplement: '+str(exc))
            sec=builder.screen_ticker(config['cik'],facts=bounded_facts(facts,datetime.now().year-6))
        except (ValueError,OSError) as e:error.append('Financial facts: '+str(e))
        if not sec.get('financial_history'):
            local=local_companyfacts(ticker,root,cache)
            if local:sec=builder.screen_ticker(config['cik'],facts=local)
        if not sec.get('financial_history') and old.get('detail_ref'):
            try:
                previous=json.loads((root/'dashboard/data'/old['detail_ref']).read_text(encoding='utf-8'))
                history=previous.get('financial_history',[])
                if history:
                    sec={**old,'financial_history':history,'financial_sources':previous.get('financial_sources',[]),'balance_sources':previous.get('balance_sources',[]),'financial_observations':previous.get('financial_observations',[]),'financial_vintages':previous.get('financial_vintages',[]),'share_history':previous.get('share_history',[])}
            except (OSError,ValueError):pass
        if not sec.get('financial_sources'):
            # Preserve raw legacy facts as unverified context; suppress derived ranks.
            sec={**{k:v for k,v in old.items() if k.endswith('_usd') or k in {'fiscal_year_end','filing_as_of','shares_outstanding','shares_as_of'}},**sec}
            for key in ['total_debt_usd','long_term_debt_usd','short_term_debt_usd']:sec[key]=None
        try:
            chart=json.loads(request(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5y',cache,offline))
            result=chart['chart']['result'][0]
            meta=result['meta']
            from market_sessions import completed_session
            cutoff=completed_session()
            closes=result.get('indicators',{}).get('quote',[{}])[0].get('close',[])
            for stamp,price in zip(result.get('timestamp',[]),closes):
                day=datetime.fromtimestamp(stamp,timezone.utc).date().isoformat()
                if price is not None and price>0 and day<=cutoff:prices.append({'date':day,'price':price})
            if meta.get('regularMarketTime') and meta.get('regularMarketPrice'):
                quote={'price':meta['regularMarketPrice'],'currency':meta.get('currency'),'as_of':datetime.fromtimestamp(meta['regularMarketTime'],timezone.utc).isoformat(),'source_url':f'https://finance.yahoo.com/quote/{ticker}/','listing':ticker}
        except (OSError,ValueError,KeyError,TypeError,IndexError) as e:
            quote=old.get('quote');error.append('Quote: '+str(e))
            if not quote:
                try:
                    tech=json.loads((root/'dashboard/data/technical_summary.json').read_text(encoding='utf-8')).get('by_ticker',{}).get(ticker,{})
                    if tech.get('data_quality')=='ready' and tech.get('latest',{}).get('close') and tech.get('as_of'):
                        from market_sessions import session_close
                        quote={'price':tech['latest']['close'],'currency':config['currency'],'as_of':session_close(tech['as_of']).isoformat(),'source_url':f'https://finance.yahoo.com/quote/{ticker}/','listing':ticker,'basis':'Latest dated close from the existing technical snapshot'}
                except (OSError,ValueError):pass
        if refresh_operating:
            discovered,gaps=discover(ticker,root,cache,offline)
            operating.extend(discovered);error.extend(gaps)
        row,detail=enrich({**old,**seed,'in_holdings':ticker in holdings,'in_watchlist':ticker in watchlist,'cik':config['cik']},sec,operating,quote,builder,old)
        detail['financial_observations']=sec.get('financial_observations',[])
        detail['financial_vintages']=sec.get('financial_vintages',[])
        detail['share_history']=sec.get('share_history',[])
        from aggregates_valuation_history import build as valuation_history
        detail['valuation_history']=valuation_history(sec.get('financial_vintages',[]),sec.get('share_history',[]),prices,config,builder.compute_rock_metrics)
        detail['source_failures']=error
        footprint_path=root/'_system/data/aggregates/footprint.json'
        footprint=json.loads(footprint_path.read_text(encoding='utf-8')).get(ticker,[]) if footprint_path.exists() else []
        for item in footprint:
            if not item.get('source_url','').startswith('https://') or not item.get('as_of') or not item.get('locator'):raise ValueError('Footprint needs dated primary evidence')
        detail['footprint']=footprint
        # Final detail hash includes recovery provenance and source failures.
        digest=hashlib.sha256(json.dumps(detail,sort_keys=True).encode()).hexdigest()[:20]
        row['detail_ref']=f'aggregates/details/{ticker}-{digest}.json'
        row['source_failures']=len(error)
        if error:errors[ticker]=error[:12]
        rows.append(row);details.append(detail)
    # Stable evidence identity retains restatements/publication vintages.
    unique={json.dumps({k:r.get(k) for k in ['ticker','metric','period_start','period_end','period_type','published_at','source_url','locator','value','unit','freight_basis','perimeter_basis']},sort_keys=True):r for r in operating}
    if write:
        ledger.parent.mkdir(parents=True,exist_ok=True)
        tmp=ledger.with_suffix('.tmp');tmp.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in sorted(unique.values(),key=lambda r:(r['ticker'],r['period_end'],r['metric'],r['published_at']))),encoding='utf-8');tmp.replace(ledger)
        result=publish(root,rows,details,errors)
        check(root)
        return result
    result=builder.build_payload(rows);result['coverage']={'failures':errors};return result
