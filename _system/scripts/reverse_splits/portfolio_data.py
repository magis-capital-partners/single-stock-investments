"""Local, licensed quote paths and delayed execution books for portfolio research.

Historical REST only. No broker, Theta terminal, orders or subscription changes.
All new requests are quoted; a single invocation shares one total cost budget.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

from .config import load_config
from .databento_bars import client_from_env, fetch, is_complete
from .execution_research import snapshot
from .expansion import digest
from .ledger import read_json, write_json

VENUES = ('ARCX.PILLAR', 'EDGX.PITCH')
ALL_VENUES = ('ARCX.PILLAR','BATS.PITCH','BATY.PITCH','EDGA.PITCH','EDGX.PITCH','EPRL.DOM',
              'IEXG.TOPS','MEMX.MEMOIR','XASE.PILLAR','XBOS.ITCH','XCHI.PILLAR','XCIS.TRADESBBO',
              'XNAS.ITCH','XNYS.PILLAR','XPSX.ITCH')


@contextmanager
def reusable_http_connections():
    """Reuse authenticated HTTPS connections within each collecting thread.

    The pinned SDK creates a new requests connection for each call. Keep its
    parsing, authentication, TLS checks and error handling, and supply ordinary
    thread-local requests Sessions only for the duration of this collection.
    """
    import requests
    import databento.common.http as sdk_http
    original=sdk_http.requests;state=threading.local();sessions=[];lock=threading.Lock()
    def session():
        if not hasattr(state,'session'):
            state.session=requests.Session()
            with lock:sessions.append(state.session)
        return state.session
    sdk_http.requests=SimpleNamespace(get=lambda *a,**kw:session().get(*a,**kw),
                                      post=lambda *a,**kw:session().post(*a,**kw))
    try:yield
    finally:
        sdk_http.requests=original
        for client in sessions:client.close()


def access_receipt(root,rows):
    """Save free dated coverage and quality metadata, without a data download."""
    receipt=read_json(root/'access_receipt.local.json',{})
    receipt.setdefault('ranges',{});receipt.setdefault('degraded_target_dates',{})
    dates={r['date'] for r in rows};unavailable={}
    with reusable_http_connections():
        client=client_from_env()
        for venue in ALL_VENUES:
            try:
                span=client.metadata.get_dataset_range(dataset=venue)
                receipt['ranges'][venue]=span;time.sleep(.3)
                first=max('2018-05-01',span['start'][:10])
                quality=client.metadata.get_dataset_condition(dataset=venue,start_date=first,end_date='2026-10-13')
                receipt['degraded_target_dates'][venue]=[r for r in quality if r.get('date') in dates and r.get('condition') not in (None,'available')]
                print('Venue coverage',venue,span['start'][:10],len(receipt['degraded_target_dates'][venue]),'flagged target dates',flush=True)
            except Exception as exc:
                message=str(exc)
                if any(s in message.lower() for s in ('401','403','429','unauthorized','permission','license')):raise
                unavailable[venue]=message[:350]
            time.sleep(.3)
    receipt.update(checked_at=datetime.now(timezone.utc).isoformat(),
                   quality_checked_at=datetime.now(timezone.utc).isoformat(),unavailable_metadata=unavailable,
                   older_subscription_supplied=receipt.get('older_subscription_supplied',False))
    write_json(root/'access_receipt.local.json',receipt)
    return receipt


def supplemental_requests(rows,ranges):
    groups=defaultdict(set)
    for r in rows:
        for venue in ALL_VENUES:
            if venue in {r['dataset'],*VENUES}:continue
            span=ranges.get(venue,{}).get('schema',{}).get('bbo-1s',{})
            if not span or r['opened'][:10]<span['start'][:10] or r['closed'][:10]>=span['end'][:10]:continue
            groups[venue,r['opened'],r['closed']].add(r['symbol'])
    out=[]
    for (venue,start,end),symbols in sorted(groups.items()):
        req={'dataset':venue,'schema':'bbo-1s','symbols':sorted(symbols),'start':start,'end':end}
        rid=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()[:24]
        out.append({'id':rid,'point':'session','request':req})
    return out


def request_rows(rows, points=None, *, root=None):
    groups = defaultdict(set)
    index=read_json(root/'paths.local.json',{}) if root else {}
    cached_ranges=defaultdict(list)
    if points is not None and root:
        for record in read_json(root/'depth'/'collection.json',[]):
            if record['status'] not in {'cached','downloaded'}:continue
            req=record['request']
            for symbol in req['symbols']:
                cached_ranges[req['dataset'],symbol,req['start'][:10]].append((req['start'],req['end']))
    for row in rows:
        venues = tuple(dict.fromkeys((row['dataset'], *VENUES)))
        if points is None:
            windows = [('session', row['opened'], row['closed'], 'bbo-1s')]
        else:
            windows = []
            series=dict(np.load(root/index[row['key']]['file'])) if root else None
            for label,point in points[row['key']].items():
                if label.startswith('30/') and label not in {'30/entry','30/close','30/stop10'}:continue
                t = datetime.fromisoformat(point['fill_at'])
                # Detailed entry/close books are always requested. For risk exits,
                # a sampled top quote already prices orders up to $2k when its
                # displayed quantity fits; larger or thinner exits need depth.
                if series is not None and not label.endswith(('/entry','/close')):
                    at=t.timestamp();i=np.searchsorted(series['ts'],at,side='right')-1
                    if i>=0 and np.isfinite(series['ask'][i]) and series['ask'][i]*series['ask_size'][i]>=2000:continue
                windows.append(('depth', (t-timedelta(seconds=31)).isoformat(),
                                (t+timedelta(seconds=.001)).isoformat(), 'mbp-10'))
        for venue in venues:
            needed=[]
            for window in windows:
                _,start,end,_=window
                if any(a<=start and end<=b for a,b in cached_ranges[venue,row['symbol'],start[:10]]):continue
                needed.append(window)
            combined=[]
            for kind,start,end,schema in sorted(set(needed),key=lambda w:w[1]):
                if combined and start<=combined[-1][2]:
                    old=combined[-1];combined[-1]=(kind,old[1],max(old[2],end),schema)
                else:combined.append((kind,start,end,schema))
            for kind, start, end, schema in combined:
                groups[venue, kind, start, end, schema].add(row['symbol'])
    out=[]
    for (venue,kind,start,end,schema), symbols in sorted(groups.items()):
        req={'dataset':venue,'schema':schema,'symbols':sorted(symbols),'start':start,'end':end}
        rid=hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()[:24]
        out.append({'id':rid,'point':kind,'request':req})
    return out


def collect(root, requests, budget, workers=24):
    """Reuse and checksum caches; reserve the quoted cost before each download."""
    # Leave ample headroom under the provider's shared connection limit.
    workers=min(workers,24)
    root.mkdir(parents=True,exist_ok=True)
    saved={r['id']:r for r in read_json(root/'collection.json',[])}
    active={r['id']:r for r in requests}
    for rid,record in saved.items():
        active.setdefault(rid,{k:record[k] for k in ('id','point','request')})
    requests=list(active.values())
    lock=threading.Lock(); local=threading.local(); stop=threading.Event()
    reserved=0.; next_meta=0.; results=[]
    def save_progress():
        retained=dict(saved)
        retained.update({r['id']:r for r in results})
        write_json(root/'collection.json',sorted(retained.values(),key=lambda r:r['id']))
    def one(item):
        nonlocal reserved,next_meta
        req=item['request']; path=root/'raw'/req['dataset']/req['schema']/(item['id']+'.dbn.zst')
        previous=saved.get(item['id'],{})
        if previous.get('status')=='unresolved_venue_symbol' or previous.get('error','').startswith('422 symbology_invalid_request'):
            return {**previous,'status':'unresolved_venue_symbol'}
        if item['id'] in saved and is_complete(path):
            if digest(path)!=saved[item['id']].get('sha256'):
                stop.set()
                return {**saved[item['id']],'status':'error','error':'cache_fingerprint_mismatch; source retained for inspection'}
            return {**saved[item['id']],'status':'cached'}
        if stop.is_set(): return {**item,'status':'stopped'}
        if not hasattr(local,'client'): local.client=client_from_env()
        with lock:
            when=max(time.monotonic(),next_meta);next_meta=when+1/6
        time.sleep(max(0,when-time.monotonic()))
        if stop.is_set():return {**item,'status':'stopped'}
        try:
            quote=float(local.client.metadata.get_cost(**req))
            if not np.isfinite(quote) or quote<0: raise ValueError('Invalid cost quote')
            allowance=quote*1.05+1e-9 if quote else 0.
            with lock:
                if reserved+allowance>budget: return {**item,'status':'cost_refused','quoted_usd':quote}
                reserved+=allowance
            record=fetch(local.client,path,max_cost=allowance,quoted_cost=quote,**req)
            return {**item,'status':'downloaded','file':str(path.relative_to(root)),
                    'sha256':digest(path),'bytes':record['bytes'],'quoted_usd':quote}
        except Exception as e:
            message=str(e)
            if message.startswith('422 symbology_invalid_request'):
                return {**item,'status':'unresolved_venue_symbol','error':message[:350]}
            if any(s in message.lower() for s in ('401','403','429','unauthorized','permission','license')):stop.set()
            return {**item,'status':'error','error':message[:350]}
    with reusable_http_connections(),ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(one,item) for item in requests]
        for f in as_completed(futures):
            results.append(f.result())
            if len(results)%50==0 or len(results)==len(requests):
                save_progress()
                print('Quote collection',len(results),'/',len(requests),dict(Counter(r['status'] for r in results)),flush=True)
    save_progress()
    if stop.is_set():raise RuntimeError('Collection stopped after an authorization, licensing, rate-limit or cache-integrity error; inspect the saved receipt before retrying')
    return results


def merged_book(books):
    books=[b for b in books if b]
    if not books:return None
    offered=len(books);chosen=[];best_bid=-float('inf');best_ask=float('inf')
    # Prefer recent states. A stale conflicting venue must not manufacture an
    # arbitrage or discard every otherwise usable venue at that time.
    for b in sorted(books,key=lambda b:(b['age_seconds'],(b['ask']-b['bid'])/b['mid'])):
        bid=max(best_bid,b['bid']);ask=min(best_ask,b['ask'])
        if ask<bid:continue
        chosen.append(b);best_bid=bid;best_ask=ask
    books=chosen
    out={'venues':len(books),'age_seconds':max(b['age_seconds'] for b in books)}
    out['sampled']=any(b.get('sampled',False) for b in books)
    out['conflicting_venues_omitted']=offered-len(books)
    for side in ('bid','ask'):
        levels=defaultdict(int)
        for b in books:
            for p,q in b[side+'_levels']:levels[p]+=q
        out[side+'_levels']=sorted(levels.items(),reverse=side=='bid')
        out[side],out[side+'_size']=out[side+'_levels'][0]
    if out['ask']<out['bid']:return None
    out['mid']=(out['bid']+out['ask'])/2
    return out


def quote_paths(root,rows):
    import databento as db
    wanted=defaultdict(list)
    for r in rows:
        for venue in ALL_VENUES:wanted[venue,r['opened']].append(r)
    collection=read_json(root/'sessions'/'collection.json',[])+read_json(root/'supplemental'/'collection.json',[])
    by_session=defaultdict(list);selected=defaultdict(list)
    for item in collection:
        if item['status'] in {'cached','downloaded'}:by_session[item['request']['start']].append(item)
    for r in rows:selected[r['opened']].append(r)
    def session_frames():
        # Read only one trading day's frames at a time. Retaining every venue
        # for the full history would consume unnecessary workstation memory.
        for opened,day_rows in sorted(selected.items()):
            frames=defaultdict(list)
            for item in by_session[opened]:
                stage='sessions' if (root/'sessions'/item['file']).exists() else 'supplemental'
                p=root/stage/item['file']
                if digest(p)!=item['sha256']:raise ValueError('Quote path fingerprint changed')
                df=db.DBNStore.from_file(str(p)).to_df()
                if df.empty:continue
                req=item['request']
                for r in wanted[req['dataset'],req['start']]:
                    f=df.loc[df['symbol']==r['symbol']].sort_index(kind='stable')
                    if not f.empty:frames[r['key']].append((req['dataset'],f[['bid_px_00','ask_px_00','bid_sz_00','ask_sz_00','flags']]))
            for r in day_rows:yield r,frames[r['key']]
    folder=root/'paths';folder.mkdir(exist_ok=True)
    index={}; points={}; issues=Counter()
    for n,(r,venue_frames) in enumerate(session_frames()):
        opened=int(pd.Timestamp(r['opened']).timestamp());closed=int(pd.Timestamp(r['closed']).timestamp())
        ts=np.arange(opened+1,closed,dtype=np.int64)
        bids=[];asks=[];bs=[];az=[];names=[];ages=[]
        for venue,frame in venue_frames:
            ft=frame.index.astype('int64').to_numpy()
            clock_ns=ts*1_000_000_000
            loc=np.searchsorted(ft,clock_ns,side='right')-1;safe=np.maximum(loc,0)
            age=(clock_ns-ft[safe])/1_000_000_000
            bid=frame['bid_px_00'].to_numpy()[safe];ask=frame['ask_px_00'].to_numpy()[safe]
            bsize=frame['bid_sz_00'].to_numpy()[safe];asize=frame['ask_sz_00'].to_numpy()[safe]
            flags=frame['flags'].to_numpy()[safe].astype(int)
            # A complete session stream retains an unchanged resting quote.
            # No BBO record is emitted during an interval with no update/trade.
            # Invalid/gap records reset validity; never carry across sessions.
            ok=(loc>=0)&(bid>0)&(ask>=bid)&np.isfinite(bid)&np.isfinite(ask)&(bsize>0)&(asize>0)&((flags&12)==0)
            bids.append(np.where(ok,bid,np.nan));asks.append(np.where(ok,ask,np.nan))
            bs.append(np.where(ok,bsize,0));az.append(np.where(ok,asize,0))
            names.append(venue)
            ages.append(np.where(ok,age,np.inf))
        if bids:
            b=np.array(bids);a=np.array(asks)
            spread=np.where(np.isfinite(b),(a-b)/((a+b)/2),np.inf)
            order=np.argsort(np.array(ages)+spread*.001,axis=0);cols=np.arange(len(ts))
            bid=np.full(len(ts),-np.inf);ask=np.full(len(ts),np.inf);bqty=np.zeros(len(ts),dtype=np.int64);aqty=bqty.copy();count=bqty.copy()
            sb,sa=np.array(bs),np.array(az)
            for rank in range(len(b)):
                vi=order[rank];vb,va=b[vi,cols],a[vi,cols];nb=np.maximum(bid,vb);na=np.minimum(ask,va)
                accept=np.isfinite(vb)&np.isfinite(va)&(nb<=na)
                qb=np.where(vb>bid,sb[vi,cols],np.where(vb==bid,bqty+sb[vi,cols],bqty))
                qa=np.where(va<ask,sa[vi,cols],np.where(va==ask,aqty+sa[vi,cols],aqty))
                bid=np.where(accept,nb,bid);ask=np.where(accept,na,ask);bqty=np.where(accept,qb,bqty);aqty=np.where(accept,qa,aqty);count+=accept
            good=count>0
            bid=np.where(good,bid,np.nan);ask=np.where(good,ask,np.nan)
        else:
            bid=ask=np.full(len(ts),np.nan);bqty=aqty=count=np.zeros(len(ts),dtype=int)
        mid=(bid+ask)/2
        rid=hashlib.sha256(r['key'].encode()).hexdigest()[:24]
        p=folder/(rid+'.npz')
        np.savez_compressed(p,ts=ts,bid=bid,ask=ask,bid_size=bqty,ask_size=aqty,venues=count,
                            venue_names=np.array(names),venue_bid=np.array(bids),venue_ask=np.array(asks),
                            venue_bid_size=np.array(bs),venue_ask_size=np.array(az),venue_age=np.array(ages))
        index[r['key']]={'file':str(p.relative_to(root)),'sha256':digest(p),'valid_seconds':int(np.isfinite(mid).sum()),'seconds':len(ts)}
        points[r['key']]={}
        for offset in (1,30):
            idx=offset-1;ref=float(mid[idx]) if np.isfinite(mid[idx]) else r['open']
            entry=opened+offset
            rules={'entry':entry,'close':closed-1,'time15':min(entry+15*60,closed-1),'time60':min(entry+60*60,closed-1)}
            for stop in (5,10,20):
                hit=np.flatnonzero((ts>entry+.1)&np.isfinite(mid)&(mid>=ref*(1+stop/100)))
                rules['stop'+str(stop)]=int(ts[hit[0]]) if len(hit) else closed-1
            for rule,t in rules.items():
                label=str(offset)+'/'+rule
                fill=t+.1
                points[r['key']][label]={'decision_at':datetime.fromtimestamp(t,timezone.utc).isoformat(),
                    'fill_at':datetime.fromtimestamp(fill,timezone.utc).isoformat(),'reference_mid':ref,
                    'reference_observed':bool(np.isfinite(mid[idx])),
                    'triggered':rule.startswith('stop') and t<closed-1}
        if not np.isfinite(mid).any():issues['no_valid_session_quotes']+=1
        if n%100==0:print('Quote paths',n+1,'/',len(rows),flush=True)
    write_json(root/'paths.local.json',index);write_json(root/'points.local.json',points)
    write_json(root/'path_coverage.json',{'events':len(rows),'issues':dict(issues),'valid_seconds':sum(v['valid_seconds'] for v in index.values())})
    return index,points


def depth_books(root,rows,points):
    import databento as db
    wanted=defaultdict(list)
    for r in rows:
        for label,point in points[r['key']].items():
            for venue in tuple(dict.fromkeys((r['dataset'],*VENUES))):
                wanted[venue,point['fill_at'][:10]].append((r,label,point))
    collected=defaultdict(list);blocked=set()
    for item in read_json(root/'depth'/'collection.json',[]):
        if item['status'] not in {'cached','downloaded'}:continue
        p=root/'depth'/item['file']
        if digest(p)!=item['sha256']:raise ValueError('Depth source fingerprint changed')
        req=item['request'];start=pd.Timestamp(req['start']);end=pd.Timestamp(req['end'])
        df=db.DBNStore.from_file(str(p)).to_df()
        if df.empty:continue
        for r,label,point in wanted[req['dataset'],req['start'][:10]]:
            if r['symbol'] not in req['symbols'] or not start<=pd.Timestamp(point['fill_at'])<end:continue
            identity=req['dataset'],r['key'],label
            frame=df.loc[df['symbol']==r['symbol']].sort_index(kind='stable')
            book,reason=snapshot(frame,point['fill_at'],sampled=False)
            if book:book['venue']=req['dataset'];collected[r['key'],label].append(book)
            elif reason in {'provider_bad_timestamp_or_book_gap','invalid_or_crossed_book','empty_book_side','nonmonotone_book'}:blocked.add(identity)
            if label.endswith('/entry'):
                decision,_=snapshot(frame,point['decision_at'],sampled=False)
                if decision:decision['venue']=req['dataset'];collected[r['key'],label.split('/')[0]+'/decision'].append(decision)
    out={r['key']:{label:None for label in list(points[r['key']])+['1/decision','30/decision']} for r in rows}
    index=read_json(root/'paths.local.json',{})
    for r in rows:
        series=dict(np.load(root/index[r['key']]['file']))
        extra={str(offset)+'/decision':{**points[r['key']][str(offset)+'/entry'],'fill_at':points[r['key']][str(offset)+'/entry']['decision_at']} for offset in (1,30)}
        for label,point in {**points[r['key']],**extra}.items():
            at=pd.Timestamp(point['fill_at']).timestamp();i=np.searchsorted(series['ts'],at,side='right')-1
            original={}
            for candidate in collected[r['key'],label]:
                venue=candidate['venue']
                if venue not in original or candidate['age_seconds']<original[venue]['age_seconds']:
                    original[venue]=candidate
            additions=[]
            if i>=0 and 'venue_names' in series:
                for vi,venue in enumerate(series['venue_names']):
                    if venue in original or (venue,r['key'],label) in blocked:continue
                    b,a=series['venue_bid'][vi,i],series['venue_ask'][vi,i]
                    if not np.isfinite(b) or not np.isfinite(a):continue
                    bs,az=int(series['venue_bid_size'][vi,i]),int(series['venue_ask_size'][vi,i])
                    age=float(series['venue_age'][vi,i]) if 'venue_age' in series else 0.
                    additions.append({'bid':float(b),'ask':float(a),'mid':float((b+a)/2),'bid_levels':[(float(b),bs)],
                                      'ask_levels':[(float(a),az)],'age_seconds':age+at-float(series['ts'][i]),'sampled':True,'venue':str(venue)})
            all_books=list(original.values())+additions
            if all_books:
                out[r['key']][label]=merged_book(all_books)
                continue
            if 'venue_names' in series:continue
            if i<0 or not np.isfinite(series['bid'][i]) or not np.isfinite(series['ask'][i]):continue
            b,a=float(series['bid'][i]),float(series['ask'][i]);bs,az=int(series['bid_size'][i]),int(series['ask_size'][i])
            out[r['key']][label]={'bid':b,'ask':a,'mid':(a+b)/2,'bid_levels':[(b,bs)],'ask_levels':[(a,az)],
                                  'bid_size':bs,'ask_size':az,'venues':int(series['venues'][i]),'sampled':True,
                                  'age_seconds':at-float(series['ts'][i])}
    write_json(root/'books.local.json',out)
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('access','sessions','supplemental','paths','depth','books'),required=True)
    parser.add_argument('--max-cost',type=float,default=0)
    parser.add_argument('--workers',type=int,default=24)
    args=parser.parse_args(argv);cfg=load_config()
    source=cfg.local_dir/'execution_research'/'20261013T224003582762Z__quotes_v1'
    root=cfg.local_dir/'portfolio_research'/'20261013T224003582762Z__portfolio_v1';root.mkdir(parents=True,exist_ok=True)
    rows=read_json(source/'targets.local.json',[])
    if args.stage=='access':access_receipt(root,rows)
    elif args.stage=='sessions':
        req=request_rows(rows);write_json(root/'session_requests.json',req)
        spent=sum(r.get('quoted_usd',0) for stage in ('sessions','supplemental','depth','repair/sessions','repair/supplemental') for r in read_json(root/stage/'collection.json',[]) if r['status'] in {'cached','downloaded'})
        collect(root/'sessions',req,max(0,args.max_cost-spent),args.workers)
    elif args.stage=='supplemental':
        req=supplemental_requests(rows,read_json(root/'access_receipt.local.json',{}).get('ranges',{}));write_json(root/'supplemental_requests.json',req)
        spent=sum(r.get('quoted_usd',0) for stage in ('sessions','supplemental','depth','repair/sessions','repair/supplemental') for r in read_json(root/stage/'collection.json',[]) if r['status'] in {'cached','downloaded'})
        collect(root/'supplemental',req,max(0,args.max_cost-spent),args.workers)
    elif args.stage=='paths':quote_paths(root,rows)
    elif args.stage=='depth':
        points=read_json(root/'points.local.json',{});req=request_rows(rows,points,root=root)
        write_json(root/'depth_requests.json',req)
        spent=sum(r.get('quoted_usd',0) for stage in ('sessions','supplemental','depth','repair/sessions','repair/supplemental') for r in read_json(root/stage/'collection.json',[]) if r['status'] in {'cached','downloaded'})
        collect(root/'depth',req,max(0,args.max_cost-spent),args.workers)
    else:depth_books(root,rows,read_json(root/'points.local.json',{}))


if __name__=='__main__':main()
