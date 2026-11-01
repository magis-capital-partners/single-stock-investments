"""Matched execution-cost audit from immutable, licensed local quote caches.

Publishes aggregates only. Never connects to a broker or ThetaData, purchases
data, or treats a displayed book as an actual fill. NBBO downloads require an
existing licensed provider key; absence is recorded rather than substituted.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote

import numpy as np

RUN = "20261013T224003582762Z"
SIZES = (500, 25_000, 50_000, 100_000)
HORIZONS = (1, 2, 5, 10, 20)
PROTOCOL = {
    "version": "execution_cost_audit.v1", "declared_on": "2026-10-19",
    "purpose": "Execution measurement; no strategy optimization or order authority.",
    "clocks": "Matched decision quotes at open +1s/+30s and close -1s. Cached depth at those clocks +100ms.",
    "sizes": SIZES, "horizons": HORIZONS,
    "pilot": "100 deterministic round-robin strata by entry year, listing venue and prior-volume tercile; no outcome feature.",
    "denominators": "All targeted events remain in coverage counts. Full-book costs are conditional on sufficient displayed quantity on both legs, never an admission screen.",
    "same_shares": "Whole shares floor(ticket / official opening auction price), bought back in full; no favorable cover-dollar resizing.",
    "costs": "Spread + displayed-book depth + separate fixed commissions. Auction-to-continuous timing is reported separately. No added flat depth proxy.",
    "impact": "Static sweeps assume simultaneous access to displayed venues; cancellations, replenishment, our market impact, queue priority and actual fills remain unmeasured.",
    "funding": "Execution audit excludes borrow, proceeds interest, margin funding and regulatory/exchange charges.",
    "authority": "none",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, doc):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()


def distribution(values):
    a = np.asarray(values, dtype=float)
    if not len(a): return {"n": 0}
    if not np.isfinite(a).all(): raise ValueError("Nonfinite audit observation")
    return {"n": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
            **{f"p{int(q*100):02d}": float(np.quantile(a,q)) for q in (.1,.25,.75,.9,.95)},
            "min": float(a.min()), "max": float(a.max())}


def spread_cost(entry, cover, denominator=None):
    return ((entry["mid"]-entry["bid"])+(cover["ask"]-cover["mid"]))/(denominator or entry["mid"])


def nbbo_at(records, moment_ns):
    """Last SIP-observable state; an invalid latest state cannot revive an old quote."""
    prior=[r for r in records if r.get('sip_timestamp',moment_ns+1)<=moment_ns]
    if not prior:return None
    r=max(prior,key=lambda r:(r['sip_timestamp'],r.get('sequence_number',0)))
    b,a=r.get('bid_price',0),r.get('ask_price',0)
    if not all(math.isfinite(v) and v>0 for v in (b,a)) or a<b or min(r.get('bid_size',0),r.get('ask_size',0))<=0:return None
    return {'bid':b,'ask':a,'mid':(b+a)/2,'bid_size':r['bid_size'],'ask_size':r['ask_size'],
            'sip_timestamp':r['sip_timestamp']}


def compare_nbbo(targets, folder):
    windows={}
    for path in folder.glob('*.window.local.json') if folder.exists() else []:
        w=read(path)
        if not w['complete']:continue
        r=w['request'];windows[r['event_id'],r['leg'],r.get('horizon',0)]=w['records']
    rows=[]
    for t in targets:
        entry=windows.get((t['key'],'entry',0));cover=windows.get((t['key'],'cover',1))
        if entry is None or cover is None:continue
        for offset in (1,30):
            op=int(datetime.fromisoformat(t['opened']).timestamp())+offset
            cl=int(datetime.fromisoformat(t['closed']).timestamp())-1
            e=nbbo_at(entry,op*1_000_000_000);x=nbbo_at(cover,cl*1_000_000_000)
            if e and x:rows.append({'event':t['key'],'offset':offset,'spread':spread_cost(e,x)})
    return {'verified_events':len({r['event'] for r in rows}),
            'groups':[{'entry_seconds':o,'spread':distribution([r['spread'] for r in rows if r['offset']==o])} for o in (1,30)]}


def sweep(levels, quantity):
    if quantity <= 0: return None
    left, dollars = quantity, 0.
    for price, available in levels:
        if not math.isfinite(price) or price <= 0 or available <= 0: raise ValueError("Invalid level")
        take = min(left, available); dollars += price*take; left -= take
        if left <= 1e-9: return dollars/quantity
    return None


def costs(target, entry, cover, dollars):
    q = math.floor(dollars/target["open"])
    if q < 1: return None
    sell, buy = sweep(entry["bid_levels"],q), sweep(cover["ask_levels"],q)
    if sell is None or buy is None: return None
    notional = q*target["open"]
    spread = q*((entry["mid"]-entry["bid"])+(cover["ask"]-cover["mid"]))
    depth = q*((entry["bid"]-sell)+(buy-cover["ask"]))
    commission = sum(min(max(1.,.005*q),.01*q*p) for p in (sell,buy))
    timing = q*((target["open"]-entry["mid"])+(cover["mid"]-target["close"]))
    shortfall = q*((target["open"]-target["close"])-(sell-buy))
    if not math.isclose(shortfall,spread+depth+timing,abs_tol=1e-6): raise ValueError("Cost bridge failed")
    return {"notional": notional, "shares": q, "spread": spread/notional, "depth": depth/notional,
            "spread_depth": (spread+depth)/notional, "commissions": commission/notional,
            "execution_including_commissions": (spread+depth+commission)/notional,
            "timing": timing/notional, "auction_shortfall_including_commissions": (shortfall+commission)/notional}


def summarize_costs(rows):
    fields = ("spread","depth","spread_depth","commissions","execution_including_commissions",
              "timing","auction_shortfall_including_commissions")
    out = {}
    for field in fields: out[field] = distribution([r[field] for r in rows])
    out["dollar_weighted_spread_depth"] = sum(r["notional"]*r["spread_depth"] for r in rows)/sum(r["notional"] for r in rows) if rows else None
    return out


def size_audit(targets, books, offset, cohort):
    pool = [t for t in targets if cohort in t["cohorts"]]
    paired = [(t,books.get(t["key"],{}).get(f"{offset}/entry"),books.get(t["key"],{}).get(f"{offset}/close")) for t in pool]
    paired = [(t,e,x) for t,e,x in paired if e and x]
    supported = {}; output = []
    for dollars in SIZES:
        fitted = []; entry_fit = exit_fit = bounded = 0
        for t,e,x in paired:
            q = math.floor(dollars/t["open"])
            entry_fit += int(sweep(e["bid_levels"],q) is not None)
            exit_fit += int(sweep(x["ask_levels"],q) is not None)
            # Diagnostic only: ex-post ability to finish each leg without walking
            # more than 1% from that leg's displayed best price.
            eb = [(p,n) for p,n in e["bid_levels"] if p>=e["bid"]*.99]
            xa = [(p,n) for p,n in x["ask_levels"] if p<=x["ask"]*1.01]
            bounded += int(sweep(eb,q) is not None and sweep(xa,q) is not None)
            v = costs(t,e,x,dollars)
            if v is not None: fitted.append({**v,"key":t["key"]})
        supported[dollars] = fitted
        output.append({"ticket":dollars,"target_events":len(pool),"paired_books":len(paired),
                       "entry_book_supports":entry_fit,"cover_book_supports":exit_fit,
                       "full_order_pairs":len(fitted),"full_order_fraction":len(fitted)/len(pool) if pool else 0.,
                       "both_legs_within_1pct_of_touch":bounded,"costs":summarize_costs(fitted)})
    common = {r["key"] for r in supported[max(SIZES)]}
    common_rows = [{"ticket":d,"events":len(common),"costs":summarize_costs([r for r in supported[d] if r["key"] in common])} for d in SIZES]
    return {"cohort":cohort,"entry_seconds":offset,"sizes":output,"common_support":common_rows}


def matched_quotes(targets, observations, root, index):
    rows = []; verified = 0
    for i,t in enumerate(targets):
        item=index.get(t["key"])
        if not item: continue
        path=root/Path(item["file"].replace("\\","/"))
        if sha(path)!=item["sha256"]: raise ValueError("Cached quote path changed")
        verified += 1
        with np.load(path, allow_pickle=False) as a:
            stamps,bids,asks,counts=a["ts"],a["bid"],a["ask"],a["venues"]
            if stamps[0] != int(datetime.fromisoformat(t['opened']).timestamp())+1 or stamps[-1] != int(datetime.fromisoformat(t['closed']).timestamp())-1:
                raise ValueError("Quote path session clock mismatch")
            for offset in (1,30):
                j=offset-1;k=len(stamps)-1
                if not (math.isfinite(bids[j]) and math.isfinite(bids[k])):continue
                e={"bid":float(bids[j]),"ask":float(asks[j]),"mid":float((bids[j]+asks[j])/2)}
                x={"bid":float(bids[k]),"ask":float(asks[k]),"mid":float((bids[k]+asks[k])/2)}
                if min(e['mid'],x['mid'])<=0:continue
                o=observations.get(t["key"],{})
                le=o.get(f"bbo-1s/open/{offset}",{}).get("book")
                lx=o.get("bbo-1s/close/-1",{}).get("book")
                r={"key":t["key"],"cohorts":t["cohorts"],"offset":offset,"multi":spread_cost(e,x),
                   "venues_entry":int(counts[j]),"venues_cover":int(counts[k])}
                if le and lx:
                    r.update(listing=spread_cost(le,lx),multi_common_denominator=spread_cost(e,x,le['mid']))
                rows.append(r)
        if (i+1)%100==0:print(f"Verified quote paths {i+1}/{len(targets)}",flush=True)
    groups=[]
    for cohort in ("primary","eligible"):
        for offset in (1,30):
            all_rows=[r for r in rows if cohort in r["cohorts"] and r["offset"]==offset]
            both=[r for r in all_rows if "listing" in r]
            groups.append({"cohort":cohort,"entry_seconds":offset,"target_events":sum(cohort in t['cohorts'] for t in targets),
                           "multi_quote_pairs":len(all_rows),"matched_pairs":len(both),
                           "listing":distribution([r['listing'] for r in both]),
                           "multi_matched":distribution([r['multi_common_denominator'] for r in both]),
                           "paired_reduction":distribution([r['listing']-r['multi_common_denominator'] for r in both]),
                           "multi_all_available":distribution([r['multi'] for r in all_rows]),
                           "venues_entry":distribution([r['venues_entry'] for r in all_rows]),
                           "venues_cover":distribution([r['venues_cover'] for r in all_rows])})
    return groups,rows,verified


def pilot_and_plan(targets, source):
    import exchange_calendars as xc
    cal=xc.get_calendar("XNYS",start="2018-03-01",end="2027-01-15")
    days=[d.date().isoformat() for d in cal.sessions]
    conn=sqlite3.connect((source/'prices.sqlite').resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    volume={}
    for t in targets:
        v=conn.execute("SELECT p.close,p.volume FROM prices_daily p JOIN price_provenance v USING(ticker,date) WHERE p.ticker=? AND p.date<? AND v.nominal=1 ORDER BY p.date DESC LIMIT 20",(t['ticker'],t['date'])).fetchall()
        volume[t['key']]=sum(p*q for p,q in v if p is not None and q is not None and p>0 and q>=0)/20
    conn.close()
    cuts=np.quantile(list(volume.values()),[1/3,2/3]);strata=defaultdict(list)
    for t in targets:
        strata[t['date'][:4],t['dataset'],int(np.searchsorted(cuts,volume[t['key']]))].append(t)
    for values in strata.values():values.sort(key=lambda t:hashlib.sha256(t['key'].encode()).hexdigest())
    selected=[]
    while len(selected)<min(100,len(targets)):
        for key in sorted(strata):
            if strata[key] and len(selected)<100:selected.append(strata[key].pop())
    pilot={t['key'] for t in selected};plan=[]
    for t in targets:
        i=days.index(t['date']);op=datetime.fromisoformat(t['opened'])
        plan.append({"event_id":t['key'],"ticker":t['symbol'],"pilot":t['key'] in pilot,"leg":"entry",
                     "date":t['date'],"start":(op-timedelta(minutes=1)).isoformat(),"end":(op+timedelta(minutes=16)).isoformat(),"symbol_status":"entry_historical_symbol_verified"})
        for h in HORIZONS:
            day=days[i+h-1]
            if day>"2026-10-13":continue
            close=cal.session_close(day).to_pydatetime()
            plan.append({"event_id":t['key'],"ticker":t['symbol'],"pilot":t['key'] in pilot,"leg":"cover","horizon":h,
                         "date":day,"start":(close-timedelta(minutes=16)).isoformat(),"end":close.isoformat(),
                         "symbol_status":"same_day_verified" if h==1 else "exit_date_symbol_mapping_requires_confirmation"})
    return plan


def collect_nbbo(plan, folder, *, key=None, session=None, max_requests=20):
    """Existing-entitlement API only; bounded, resumable, safe pagination.

    The key is carried only as an Authorization header, never in saved URLs.
    A denial stops collection and remains a gap. No purchase/upgrade path exists.
    """
    key=key or os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY") or os.environ.get("POLYGON_IO_API_KEY")
    if not key:return {"status":"unavailable_no_configured_key","requests":0,"nbbo_verified_pairs":0}
    if session is None:
        import requests
        session=requests.Session()
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    session.headers.update({"Authorization":"Bearer "+key})
    receipts=[];used=0
    for item in plan:
        if not item['pilot']:continue
        if item['symbol_status']=='exit_date_symbol_mapping_requires_confirmation':continue
        params={"timestamp.gte":int(datetime.fromisoformat(item['start']).timestamp()*1e9),
                "timestamp.lt":int(datetime.fromisoformat(item['end']).timestamp()*1e9),"order":"asc","sort":"timestamp","limit":50000}
        url="https://api.massive.com/v3/quotes/"+quote(item['ticker'],safe='')+"?"+urlencode(params);seen=set();records=[];complete=False
        while url and used<max_requests:
            parsed=urlparse(url)
            if parsed.scheme!='https' or parsed.hostname!='api.massive.com':raise ValueError("Untrusted NBBO pagination host")
            url=urlunparse(parsed._replace(query=urlencode([(k,v) for k,v in parse_qsl(parsed.query) if k.lower()!='apikey'])))
            if url in seen:raise ValueError("Repeated NBBO cursor")
            seen.add(url);name=hashlib.sha256(url.encode()).hexdigest()+'.json';path=folder/name
            if path.exists():body=read(path)
            else:
                response=session.get(url,timeout=(10,40));used+=1
                if response.status_code!=200:return {"status":f"provider_HTTP_{response.status_code}","requests":used,"completed_windows":len(receipts),"nbbo_verified_pairs":0}
                body=response.json()
                if body.get('next_url'):
                    nxt=urlparse(body['next_url']);body['next_url']=urlunparse(nxt._replace(query=urlencode([(k,v) for k,v in parse_qsl(nxt.query) if k.lower()!='apikey'])))
                write(path,{"results":body.get('results',[]),"next_url":body.get('next_url')})
            records.extend(body.get('results',[]));url=body.get('next_url');complete=not url
        identity=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
        write(folder/(identity+'.window.local.json'),{"request":item,"complete":complete,"records":records})
        receipts.append({"window":identity,"records":len(records),"complete":complete})
        if used>=max_requests:break
    return {"status":"bounded_collection_complete","requests":used,"windows":len(receipts),"complete_windows":sum(r['complete'] for r in receipts),"nbbo_verified_pairs":0}


def databento_access(receipt, verified_events):
    """Publish only allowlisted metadata from the authenticated, zero-download check."""
    if receipt.get('provider')!='Databento' or receipt.get('authenticated') is not True:
        raise ValueError('Databento authentication receipt is not verified')
    if (receipt.get('sip_status')!='dataset_not_found' or receipt.get('all_feeds_bundle_status')!='dataset_not_found'
            or receipt.get('mini_is_official_nbbo') is not False):
        raise ValueError('Databento dataset access changed; review the published interpretation')
    if receipt.get('downloads')!=0 or receipt.get('charged_usd')!=0:
        raise ValueError('Databento receipt does not match the zero-download budget')
    return {"provider":"Databento","status":"authenticated_sip_not_retrievable","authenticated":True,
            "checked_as_of":receipt['as_of'],"sip_status":receipt['sip_status'],
            "all_feeds_bundle_status":receipt['all_feeds_bundle_status'],"mini_start":receipt['mini_start'],
            "mini_is_official_nbbo":False,"new_download_budget_usd":0,"downloads":0,"charged_usd":0,
            "nbbo_verified_pairs":verified_events,
            "note":"Databento access verified. EQUS.SIP and EQUS.ALL returned dataset_not_found through the authenticated historical API. Available EQUS.MINI is a derived venue-subset BBO from 2023-03-28, not official NBBO. New downloads are capped at $0 by request. The sampled quote/depth requests have positive usage prices, so none were downloaded. Existing cached-data estimates are unchanged.",
            "sample_usage_quotes":[{k:r[k] for k in ('dataset','schema','date','quoted_usd')} for r in receipt.get('sample_quotes',[]) if 'quoted_usd' in r]}


def build(root, outdir, *, collect=False, databento_receipt=None):
    if collect and databento_receipt is not None:
        raise ValueError('Publish the Databento check separately from optional NBBO collection')
    local=root/'_system/data/reverse_splits/local';qroot=local/f'execution_research/{RUN}__quotes_v1'
    proot=local/f'portfolio_research/{RUN}__portfolio_v1';source=local/f'expansion/expansion_v2/runs/{RUN}'
    outdir.mkdir(parents=True,exist_ok=True);write(outdir/'protocol.json',PROTOCOL)
    targets=read(qroot/'targets.local.json');obs=read(qroot/'observations.local.json');books=read(proot/'books.local.json');index=read(proot/'paths.local.json')
    manifest=read(proot/'manifest.json')
    for name in ('books.local.json','points.local.json','paths.local.json'):
        if sha(proot/name)!=manifest['inputs'][name]:raise ValueError('Frozen execution inputs changed: '+name)
    if sha(qroot/'targets.local.json')!=manifest['source_inputs']['quote_targets']:raise ValueError('Target fingerprint changed')
    if sha(source/'prices.sqlite')!=manifest['source_inputs']['prices']:raise ValueError('Frozen nominal-price database changed')
    quotes,rows,verified=matched_quotes(targets,obs,proot,index)
    audits=[size_audit(targets,books,offset,cohort) for cohort in ('primary','eligible') for offset in (1,30)]
    plan=pilot_and_plan(targets,source);write(outdir/'acquisition_plan.local.json',plan);write(outdir/'matched_quotes.local.json',rows)
    access=collect_nbbo(plan,outdir/'nbbo') if collect else {"status":"not_requested","requests":0,"nbbo_verified_pairs":0}
    nbbo=compare_nbbo(targets,outdir/'nbbo');access['nbbo_verified_pairs']=nbbo['verified_events']
    if databento_receipt is not None:
        access=databento_access(read(databento_receipt),nbbo['verified_events'])
    result={"schema_version":"short_execution_audit.v1","as_of":"2026-10-19","research_only":True,"authority":"none","aggregate_only":True,
            "protocol":PROTOCOL,"quote_comparisons":quotes,"size_audits":audits,"access":access,"nbbo":nbbo,
            "coverage":{"target_events":len(targets),"paths_hash_verified":verified,"pilot_events":len({p['event_id'] for p in plan if p['pilot']}),
                        "planned_windows":len(plan),"pilot_windows":sum(p['pilot'] for p in plan),"confirmed_nbbo_pairs":nbbo['verified_events'],
                        "multi_session_execution_costs":"not_established_no_verified_endpoint_books","actual_broker_fills":0},
            "limits":["Multi-venue quotes cover observed feeds, not official consolidated NBBO.",
                      "Cached decision quotes are matched exactly in clock; depth books add a modeled 100ms response and may mix sampled top quotes with deeper books.",
                      "Full-order statistics exclude unsupported orders and are conditional on future cover depth; missing costs are not zero and these are not strategy returns.",
                      "Different size rows have different surviving samples. Common-support rows hold the same events fixed but select a liquid subset with hindsight.",
                      "Static books do not establish smart-router access, successful fills, replenishment, cancellations, price impact or borrow approval.",
                      "Auction-to-continuous timing is separate from spread/depth. Multi-session exits and stops need additional dated quote paths.",
                      "No real trades were submitted. New chargeable quote downloads require a budget; no purchase or subscription upgrade is performed."],
            "sources":[{"file":name,"sha256":sha(path)} for name,path in [('targets.local.json',qroot/'targets.local.json'),('observations.local.json',qroot/'observations.local.json'),('books.local.json',proot/'books.local.json'),('paths.local.json',proot/'paths.local.json'),('prices.sqlite',source/'prices.sqlite')]]}
    return result


def report(doc):
    fmt=lambda v:f'{v*100:.2f}%' if v is not None else 'Unavailable'
    lines=['# Short execution-cost audit — 2026-10-19','',
           'Research estimates from historical displayed quotes and books; no broker fills. Borrow and financing are excluded.','',
           '## Matched quote comparison','',
           '| Cohort | Entry delay | Matched events | Listing median | Multi-venue median | Multi-venue mean |',
           '|---|---:|---:|---:|---:|---:|']
    for r in doc['quote_comparisons']:
        lines.append(f"| {r['cohort']} | {r['entry_seconds']}s | {r['matched_pairs']} | {fmt(r['listing'].get('median'))} | {fmt(r['multi_matched'].get('median'))} | {fmt(r['multi_matched'].get('mean'))} |")
    for a in doc['size_audits']:
        lines+=['',f"## Displayed-book size test: {a['cohort']}, entry +{a['entry_seconds']}s",'',
                '| Ticket | Full pairs / target events | Spread + depth median | Mean | P90 | Mean incl. commissions | Both legs within 1% of best quote |',
                '|---:|---:|---:|---:|---:|---:|---:|']
        for r in a['sizes']:
            c=r['costs']['spread_depth'];inc=r['costs']['execution_including_commissions']
            lines.append(f"| ${r['ticket']:,} | {r['full_order_pairs']} / {r['target_events']} | {fmt(c.get('median'))} | {fmt(c.get('mean'))} | {fmt(c.get('p90'))} | {fmt(inc.get('mean'))} | {r['both_legs_within_1pct_of_touch']} |")
        lines+=['','Same events supported at every size (selected with hindsight):','',
                '| Ticket | Common events | Median spread + depth | Mean |','|---:|---:|---:|---:|']
        for r in a['common_support']:
            c=r['costs']['spread_depth'];lines.append(f"| ${r['ticket']:,} | {r['events']} | {fmt(c.get('median'))} | {fmt(c.get('mean'))} |")
    a=next(a for a in doc['size_audits'] if a['cohort']=='eligible' and a['entry_seconds']==1)
    lines+=['','## Bridge to the auction-price backtest: eligible cohort, entry +1s','',
            '| Ticket | Mean spread | Mean depth | Mean commissions | Mean timing shortfall | Mean total shortfall vs auction benchmark |',
            '|---:|---:|---:|---:|---:|---:|']
    for r in a['sizes']:
        if r['ticket']<25000:continue
        c=r['costs'];lines.append(f"| ${r['ticket']:,} | {fmt(c['spread']['mean'])} | {fmt(c['depth']['mean'])} | {fmt(c['commissions']['mean'])} | {fmt(c['timing']['mean'])} | {fmt(c['auction_shortfall_including_commissions']['mean'])} |")
    lines+=['','Timing measures background price differences between auction benchmarks and sampled continuous midpoints. It is not causal market impact. Every row retains its conditional supported sample.']
    lines+=['','## Remaining work','',f"NBBO access: {doc['access']['status']}. Verified NBBO events: {doc['coverage']['confirmed_nbbo_pairs']}. Actual broker fills: 0.",
            f"Prepared {doc['coverage']['planned_windows']} windows, including {doc['coverage']['pilot_windows']} for the deterministic 100-event pilot.",
            'Multi-session exit costs remain unmeasured; no same-day spread estimate is relabeled as a measured multi-session cost.','']
    if doc['access'].get('note'):lines += [doc['access']['note'],'']
    lines += ['- '+x for x in doc['limits']]
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--local-out',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--collect-nbbo',action='store_true')
    p.add_argument('--databento-access-receipt',type=Path)
    args=p.parse_args();doc=build(args.source_root,args.local_out,collect=args.collect_nbbo,databento_receipt=args.databento_access_receipt);write(args.out,doc)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(report(doc),encoding='utf-8')
    print(json.dumps(doc['coverage']));print(json.dumps(doc['access']))


if __name__=='__main__':main()
