"""Bounded historical venue capture and honest event normalization. No Theta/IB access.

This is a venue execution sensitivity, not SIP NBBO or historical borrow proof.
Quotes are priced before download. The cumulative cap includes cached paid receipts.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from threading import Lock


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, value):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,allow_nan=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n')


def security_for(row):
    """Join dated primary-source symbol/venue events by issuer, never ticker alone."""
    ledger=read(Path(__file__).resolve().parents[2]/'data/reverse_splits/third_plus_signal_study/ssr_execution_v2/security_lifecycle.v1.json')
    symbol=row['ticker'];venue='NASDAQ';sources=[]
    for e in sorted(ledger['events'],key=lambda e:e['effective']):
        if e['issuer']!=row['issuer'] or e['ticker']!=symbol or e['effective']>row['date']:continue
        sources.append(e['source_url'])
        if e['kind']=='symbol_change':
            if e.get('same_security') is not True:raise ValueError('Unproven successor security')
            symbol=e['successor']
        else:venue='NASDAQ' if e['kind']=='venue_resume' else e['destination']
    return symbol,venue,sources


def make_plan(inputs):
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start='2023-01-01',end='2027-01-01')
    grouped=defaultdict(list)
    for s in inputs['sessions']: grouped[s['kind'],s['date']].append(s)
    jobs=[]
    for (kind,day),rows in sorted(grouped.items()):
        op=cal.session_open(day).to_pydatetime();cl=cal.session_close(day).to_pydatetime()
        start=op.timestamp() if kind=='entry' else cl.timestamp()-91*60
        end=op.timestamp()+61*60+5 if kind=='entry' else cl.timestamp()-15*60+5
        request=dict(dataset='XNAS.ITCH',schema='mbp-10',symbols=sorted({security_for(r)[0] for r in rows}),
                     start=datetime.fromtimestamp(start,timezone.utc).isoformat(),end=datetime.fromtimestamp(end,timezone.utc).isoformat())
        ident=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
        jobs.append(dict(id=ident,request=request,rows=rows,open_ms=int(op.timestamp()*1000),close_ms=int(cl.timestamp()*1000)))
    return dict(schema='third_plus_venue_capture_plan.v2',jobs=jobs,scope='single_venue_conditional_nbb_and_borrow',download_budget_usd=0)


def price(plan,client,work):
    old_file=work/'priced_plan.local.json'
    prior={j['id']:j for j in read(old_file)['jobs']} if old_file.exists() else {}
    def one(job):
        p=work/'raw'/f"{job['id']}.dbn.zst";receipt=p.with_suffix('.receipt.json')
        if p.exists() and receipt.exists():
            r=read(receipt)
            if r['request']!=job['request'] or r['sha256']!=sha(p): raise ValueError('Capture receipt mismatch')
            return {**job,**r,'cached':True}
        if job['id'] in prior and prior[job['id']].get('quoted_usd') is not None and prior[job['id']]['request']==job['request']:
            return {**job,'quoted_usd':prior[job['id']]['quoted_usd'],'cached':False}
        try:
            cost=float(client.metadata.get_cost(**job['request']))
            if not math.isfinite(cost) or cost<0: raise ValueError('Invalid cost')
            return {**job,'quoted_usd':cost,'cached':False}
        except Exception as e: return {**job,'quoted_usd':None,'error_type':type(e).__name__,'cached':False}
    with ThreadPoolExecutor(max_workers=4) as pool: jobs=list(pool.map(one,plan['jobs']))
    result={**plan,'jobs':jobs,'quoted_usd':sum(j['quoted_usd'] or 0 for j in jobs),
            'quote_failures':sum(j['quoted_usd'] is None for j in jobs)}
    write(work/'priced_plan.local.json',result)
    print(json.dumps({k:result[k] for k in ['quoted_usd','quote_failures']}),flush=True)
    return result


def collect(plan,client,work,budget):
    if not math.isfinite(budget) or budget<0: raise ValueError('Invalid total budget')
    quoted=sum(j['quoted_usd'] or 0 for j in plan['jobs'])
    if quoted>budget+1e-12 or budget==0 and quoted!=0: raise ValueError(f'Total quoted cost {quoted:.6f} exceeds authorized cap {budget:.2f}')
    ledger_file=work/'budget_ledger.local.json'
    ledger=read(ledger_file) if ledger_file.exists() else dict(reservations=[],cached_cost_usd=sum(j['quoted_usd'] or 0 for j in plan['jobs'] if j.get('cached')))
    spent=ledger.get('cached_cost_usd',0)+sum(x['usd'] for x in ledger['reservations'])
    if spent>budget+1e-12:raise ValueError('Previously reserved cost already exceeds cap')
    lock=Lock();done=[]
    def one(job):
        nonlocal spent
        if job.get('cached') or job['quoted_usd'] is None:return job
        # Refresh each exact quote, then reserve it before any paid request.
        cost=float(client.metadata.get_cost(**job['request']))
        with lock:
            if not math.isfinite(cost) or cost<0 or spent+cost>budget+1e-12 or budget==0 and cost!=0:raise ValueError('Refreshed quote exceeds remaining cap')
            spent+=cost
            ledger['reservations'].append(dict(request_id=job['id'],usd=cost,reserved_at=datetime.now(timezone.utc).isoformat()))
            write(ledger_file,ledger)
        p=work/'raw'/f"{job['id']}.dbn.zst";p.parent.mkdir(parents=True,exist_ok=True)
        part=p.with_suffix('.part')
        if part.exists(): part.unlink()
        try:
            client.timeseries.get_range(**job['request'],path=str(part));part.replace(p)
            receipt=dict(request=job['request'],quoted_usd=cost,sha256=sha(p),captured_at=datetime.now(timezone.utc).isoformat())
            write(p.with_suffix('.receipt.json'),receipt);return {**job,**receipt,'cached':True}
        except Exception as e:
            return {**job,'charged_reserve_usd':cost,'error_type':type(e).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(one,plan['jobs'])):
            done.append(result)
            write(work/'collection.local.json',dict(schema='third_plus_venue_collection.v2',jobs=done,authorized_cap_usd=budget,reserved_cost_usd=spent))
            if i%25==0:print(f'Historical captures {i+1}/{len(plan["jobs"])}; reserved ${spent:.4f}',flush=True)
    write(work/'collection.local.json',dict(schema='third_plus_venue_collection.v2',jobs=done,authorized_cap_usd=budget,reserved_cost_usd=spent))


def normalize_records(records,row,job,source_hash):
    """Normalize actual book/trade events. Quote-rule classification is explicitly inferred."""
    events=[];last=None;seen=set();epoch=0;capacity=0;previous_ask=None;previous_size=0;stats=defaultdict(int)
    status='restricted' if row.get('restricted')!=0 else 'clear';trading=True
    for v in records:
        at=int(v['available_ms']);ts=int(v['ts_ms'])
        if v.get('type')=='status':
            if v.get('restricted') in ('Y','N'):status='restricted' if v['restricted']=='Y' else 'clear'
            if v.get('trading') in ('Y','N'):trading=v['trading']=='Y'
            if last:events.append({**last,'ts_ms':ts,'available_ms':at,'status':status,'trading':trading})
            continue
        if at<ts or v.get('flags',0)&12:stats['bad_clock_or_book']+=1;continue
        bid,ask=v.get('bid'),v.get('ask');size=int(v.get('ask_size',0))
        if v.get('action')=='T' and v.get('price',0)>0 and v.get('size',0)>0 and last:
            key=str(v.get('sequence',at))
            if key not in seen:
                seen.add(key)
                # B/A are source aggressor sides; N is classified from the pre-event quote.
                side=v.get('side','N');basis='source_side'
                if side not in ('B','A'):
                    side='B' if v['price']>=last['ask'] else 'A' if v['price']<=last['bid'] else 'U';basis='pretrade_quote_rule'
                stats[basis]+=1
                events.append(dict(type='trade',ts_ms=ts,available_ms=at,venue='XNAS',trade_id=key,price=v['price'],size=int(v['size']),aggressor=side,aggressor_basis=basis,regular=trading))
        if not all(isinstance(x,(int,float)) and math.isfinite(x) and x>0 for x in (bid,ask)) or ask<bid:continue
        if ask!=previous_ask:epoch+=1;capacity=size
        else:capacity+=max(0,size-previous_size)
        previous_ask=ask;previous_size=size
        book=v.get('book') or {str(ask):size}
        m=dict(type='market',ts_ms=ts,available_ms=at,venue='XNAS',bid=bid,ask=ask,ask_size=size,ask_capacity=capacity,
               tick=.01 if bid>=1 else .0001,grid_id='pre-2026-11-US-equity-grid',status=status,
               trading=trading,feed_ok=True,liquidity_id=str(epoch),book=book)
        # Preserve trade-before-post-event-book order, including equal receipt clocks.
        events.append(m);last=m
    return dict(schema='third_plus_venue_session.v2',event_id=row['id'],issuer=row['issuer'],date=row['date'],
        open_ms=job['open_ms'],close_ms=job['close_ms'],capture_start_ms=int(datetime.fromisoformat(job['request']['start']).timestamp()*1000),
        capture_end_ms=int(datetime.fromisoformat(job['request']['end']).timestamp()*1000),source_hashes=[source_hash],volume_scope='single_venue',
        continuity_mode='complete_capture',evidence={k:True for k in ['identity','venue_book','eligible_trades','market_status','dated_price_grid','feed_continuity','receipt_clock','route_rules']},
        conditional_assumptions=['venue_BBO_is_not_NBBO','broker_enforces_national_price_test','historical_borrow_available','no_own_order_market_impact'],
        route_rules={'initial_display_exception':True},classification_counts=dict(stats),empty_observed=not bool(events),events=events)


def status_archive(source,work):
    """Reconstruct dated status and halts from cached exchange records and symbology."""
    import databento as db
    import numpy as np
    wanted=defaultdict(set)
    for r in read(work/'inputs.local.json')['sessions']:wanted[r['date']].add(r['ticker'])
    result={};sources={};wanted_symbols={s for symbols in wanted.values() for s in symbols}
    folder=source/'_system/data/reverse_splits/local/raw/databento/XNAS.ITCH/status'
    for p in sorted(folder.glob('*.dbn.zst')):
        side=p.with_name(p.name.replace('.dbn.zst','.symbology.json'))
        if not side.exists():continue
        ivs=read(side);byid=defaultdict(list)
        for iid,spans in ivs.items():
            for span in spans:
                if span['s'] not in wanted_symbols:continue
                days=[day for day,symbols in wanted.items() if span['d0']<=day<span['d1'] and span['s'] in symbols]
                for day in days:byid[int(iid)].append((day,span['s']))
        if not byid:continue
        a=db.DBNStore.from_file(str(p)).to_ndarray();a=a[np.isin(a['instrument_id'],list(byid))]
        digest=sha(p);sources[p.name]=digest
        for iid,keys in byid.items():
            rows=a[a['instrument_id']==iid]
            for day,symbol in keys:
                start=int(datetime.fromisoformat(day+'T00:00:00+00:00').timestamp()*10**9)
                subset=rows[(rows['ts_event']>=start)&(rows['ts_event']<start+86400*10**9)]
                records=[]
                for x in subset:
                    def ch(k):
                        y=x[k];return chr(int(y)) if isinstance(y,(int,np.integer)) else y.decode() if isinstance(y,bytes) else str(y)
                    records.append(dict(type='status',ts_ms=int(x['ts_event'])//1000000,available_ms=max(int(x['ts_recv']),int(x['ts_event']))//1000000,
                                        restricted=ch('is_short_sell_restricted'),trading=ch('is_trading')))
                if records:result[day+'|'+symbol]=dict(records=records,source_sha256=digest)
        print('Reconstructed exchange status',p.name,flush=True)
    write(work/'status.local.json',dict(sessions=result,sources=sources))


def normalize(work):
    import databento as db
    import numpy as np
    index=[];counts=defaultdict(int);statuses=read(work/'status.local.json')['sessions']
    for i,job in enumerate(read(work/'collection.local.json')['jobs']):
        p=work/'raw'/f"{job['id']}.dbn.zst"
        if not p.exists():counts['capture_missing']+=len(job['rows']);continue
        receipt=read(p.with_suffix('.receipt.json'))
        if receipt['sha256']!=sha(p) or receipt['request']!=job['request']:raise ValueError('Raw provenance mismatch')
        frame=db.DBNStore.from_file(str(p)).to_df(pretty_ts=False)
        for row in job['rows']:
            f=frame[frame['symbol']==row['ticker']] if len(frame) and 'symbol' in frame else frame.iloc[:0]
            records=[]
            for v in f.reset_index().to_dict('records'):
                records.append(dict(ts_ms=int(v['ts_event'])//1000000,available_ms=int(v['ts_recv'])//1000000,action=v['action'],side=v['side'],price=float(v['price']),size=int(v['size']),flags=int(v['flags']),sequence=int(v['sequence']),
                    bid=float(v['bid_px_00']),ask=float(v['ask_px_00']),ask_size=int(v['ask_sz_00']),book={str(float(v[f'ask_px_{n:02d}'])):int(v[f'ask_sz_{n:02d}']) for n in range(10) if math.isfinite(float(v[f'ask_px_{n:02d}'])) and float(v[f'ask_px_{n:02d}'])>0}))
            state=statuses.get(row['date']+'|'+row['ticker'])
            if state:
                end=int(datetime.fromisoformat(job['request']['end']).timestamp()*1000)
                records.extend(x for x in state['records'] if x['available_ms']<=end)
                records.sort(key=lambda x:x['available_ms'])
            s=normalize_records(records,row,job,receipt['sha256'])
            if state:s['source_hashes'].append(state['source_sha256'])
            else:s['conditional_assumptions'].append('intraday_status_unavailable_opening_state_carried')
            name=hashlib.sha256((row['id']+'|'+row['date']+'|'+row['kind']).encode()).hexdigest()[:24]+'.json'
            file=work/'sessions'/name;write(file,s)
            index.append(dict(event_id=row['id'],date=row['date'],kind=row['kind'],file='sessions/'+name,sha256=sha(file),events=len(s['events']),header={k:v for k,v in s.items() if k!='events'}))
            counts['sessions']+=1;counts['empty']+=not bool(s['events'])
        if i%25==0:print(f'Normalized {i+1} captures; {counts["sessions"]} event sessions',flush=True)
    write(work/'index.local.json',dict(schema='third_plus_venue_archive.v2',sessions=index,counts=dict(counts)))


def free_bars(source,work):
    """Acquire only zero-quoted one-second bars, grouped monthly, and preserve quality labels."""
    import databento as db
    import numpy as np
    sys.path.insert(0,str(source/'_system/scripts'))
    from reverse_splits.execution_realism import _client
    client=_client();free=work/'free_bars';free.mkdir(exist_ok=True)
    original=read(work/'plan.local.json')['jobs'];groups=defaultdict(list)
    for j in original:groups[j['rows'][0]['date'][:7]].append(j)
    jobs=[]
    for month,items in sorted(groups.items()):
        days=sorted(j['rows'][0]['date'] for j in items)
        start=datetime.fromtimestamp(min(j['open_ms'] for j in items)/1000-1800,timezone.utc).isoformat()
        end=datetime.fromtimestamp(max(j['close_ms'] for j in items)/1000+1,timezone.utc).isoformat()
        request=dict(dataset='XNAS.ITCH',schema='ohlcv-1s',symbols=sorted({s for j in items for s in j['request']['symbols']}),start=start,end=end)
        ident=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
        jobs.append(dict(id=ident,request=request,month=month))
    plan=price(dict(schema='third_plus_free_bar_plan.v2',jobs=jobs),client,free)
    if plan['quote_failures']:raise ValueError('Unpriced free-bar requests; rerun price before collecting')
    collect(plan,client,free,0)
    normalize_free(source,work)


def normalize_free(source,work):
    """Rebuild from hash-verified existing sources only. No client or network."""
    import databento as db
    import numpy as np
    free=work/'free_bars';groups=defaultdict(list)
    for j in read(work/'plan.local.json')['jobs']:groups[j['rows'][0]['date'][:7]].append(j)
    status=read(work/'status.local.json')['sessions'];prepared=read(source/'_system/data/reverse_splits/local/patient_execution/20261020_v1/prepared.local.json')['rows']
    quotes={(r['ticker'],r['date']):r for r in prepared if r.get('prepared')};index=[];counts=defaultdict(int)
    for job in read(free/'collection.local.json')['jobs']:
        p=free/'raw'/f"{job['id']}.dbn.zst";receipt=read(p.with_suffix('.receipt.json'))
        if sha(p)!=receipt['sha256'] or receipt['quoted_usd']!=0:raise ValueError('Nonzero cost or changed free source')
        frame=db.DBNStore.from_file(str(p)).to_df(pretty_ts=False)
        for original_job in groups[job['month']]:
            for row in original_job['rows']:
                symbol,venue,lineage_sources=security_for(row)
                source_complete=symbol in job['request']['symbols'] and venue=='NASDAQ'
                start=int(datetime.fromisoformat(original_job['request']['start']).timestamp())
                end=int(datetime.fromisoformat(original_job['request']['end']).timestamp())
                if row['kind']=='entry':end=original_job['close_ms']//1000-15*60+5
                f=frame[frame['symbol']==symbol].copy() if source_complete and len(frame) and 'symbol' in frame else frame.iloc[:0].copy()
                f=f[(f.index//10**9>=start-1800)&(f.index//10**9<end)]
                bars=[[int(at)//10**9,float(x.open),float(x.high),float(x.low),float(x.close),int(x.volume)] for at,x in f.iterrows()]
                q=quotes.get((symbol,row['date']));qp=[];hashes=[receipt['sha256']]
                if q:
                    qpfile=Path(q['prepared']);qpfile.resolve().relative_to((source/'_system/data/reverse_splits/local').resolve())
                    with np.load(qpfile,allow_pickle=False) as a:
                        mask=(a['ts']>=start-1)&(a['ts']<end)&a['valid']
                        qp=[[int(t),float(b),float(s)] for t,b,s in zip(a['ts'][mask],a['bid'][mask],a['ask'][mask]) if math.isfinite(b) and math.isfinite(s) and b>0 and s>=b]
                    hashes.append(sha(qpfile))
                st=status.get(row['date']+'|'+symbol,{})
                if st:hashes.append(st['source_sha256'])
                s=dict(schema='third_plus_bar_session.v2',event_id=row['id'],issuer=row['issuer'],date=row['date'],open_ms=original_job['open_ms'],close_ms=original_job['close_ms'],
                       capture_start_ms=start*1000,capture_end_ms=end*1000,source_hashes=hashes,bars=bars,quotes=qp,statuses=st.get('records',[]),
                       opening_restricted=row['restricted'],quote_basis='sampled_venue_quotes' if qp else 'missing',source_ticker=symbol,venue=venue,lineage_sources=lineage_sources,
                       data_gaps=[] if source_complete else ['venue_exit' if venue!='NASDAQ' else 'symbol_capture_missing'],
                       evidence_level='observed_bars_with_unverified_execution',volume_scope='single_venue',empty_observed=source_complete and not bool(bars))
                name=hashlib.sha256((row['id']+'|'+row['date']+'|'+row['kind']).encode()).hexdigest()[:24]+'.json'
                file=work/'sessions'/name;write(file,s)
                index.append(dict(event_id=row['id'],date=row['date'],kind=row['kind'],file='sessions/'+name,sha256=sha(file),events=len(bars),header={k:v for k,v in s.items() if k not in ('bars','quotes','statuses')}))
                counts['sessions']+=1;counts['sampled_quotes']+=bool(qp);counts['missing_quotes']+=not bool(qp);counts['empty_bars']+=source_complete and not bool(bars);counts['source_gaps']+=not source_complete
        print('Prepared free-bar month',job['month'],counts['sessions'],'sessions',flush=True)
    write(work/'index.local.json',dict(schema='third_plus_venue_archive.v2',mode='bar_sensitivity',sessions=index,counts=dict(counts)))
    write(work/'collection.local.json',dict(schema='third_plus_free_collection.v2',authorized_cap_usd=0,reserved_cost_usd=0,files=[j['sha256'] for j in read(free/'collection.local.json')['jobs'] if j.get('sha256')]))


def extend_covers(source,work):
    """Acquire follow-up coverage for retained liabilities, never select entries by exit outcomes."""
    import sqlite3
    inputs=read(work/'inputs.local.json');candidates={c['id']:c for c in inputs['candidates']}
    existing={(s['id'],s['date'],s['kind']) for s in inputs['sessions']};added=0
    db=sqlite3.connect('file:'+(source/'_system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z/prices.sqlite').as_posix()+'?mode=ro',uri=True)
    try:
        for p in sorted((work/'ledgers').glob('*_primary.local.json')):
            for x in read(p).get('missing_exits',[]):
                key=x['id'],x['date'],'cover'
                if x['reason']!='exit_session_missing' or key in existing:continue
                c=candidates[x['id']];state=db.execute('SELECT restricted FROM ssr_states WHERE ticker=? AND date=?',(c['ticker'],x['date'])).fetchone()
                inputs['sessions'].append(dict(id=c['id'],ticker=c['ticker'],issuer=c['issuer'],date=x['date'],kind='cover',restricted=state[0] if state else None))
                existing.add(key);added+=1
    finally:db.close()
    write(work/'inputs.local.json',inputs);write(work/'plan.local.json',make_plan(inputs));print('Added residual-cover sessions',added,flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['plan','price','collect','normalize','normalize-free','status','free-bars','extend-covers']);ap.add_argument('--source-root',type=Path,required=True);ap.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[3]);ap.add_argument('--budget-usd',type=float,default=0);a=ap.parse_args()
    work=a.source_root/'_system/data/reverse_splits/local/third_plus_signal_study/ssr_execution_v2';work.mkdir(parents=True,exist_ok=True)
    if a.command=='plan':
        subprocess.run(['node',str(Path(__file__).with_name('export_venue_inputs.cjs')),str(a.source_root),str(work/'inputs.local.json')],check=True)
        d=make_plan(read(work/'inputs.local.json'));write(work/'plan.local.json',d);print('Planned',len(d['jobs']),'grouped captures')
    elif a.command=='normalize':normalize(work)
    elif a.command=='status':status_archive(a.source_root,work)
    elif a.command=='free-bars':free_bars(a.source_root,work)
    elif a.command=='normalize-free':normalize_free(a.source_root,work)
    elif a.command=='extend-covers':extend_covers(a.source_root,work)
    else:
        sys.path.insert(0,str(a.source_root/'_system/scripts'))
        from reverse_splits.execution_realism import _client
        c=_client()
        if a.command=='price':price(read(work/'plan.local.json'),c,work)
        else:collect(read(work/'priced_plan.local.json'),c,work,a.budget_usd)

if __name__=='__main__':main()
