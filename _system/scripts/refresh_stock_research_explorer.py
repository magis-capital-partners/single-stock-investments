"""Incremental HTTPS-only financial refresh, independent of research-library builds."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import threading
from urllib.parse import quote

from atomic_io import _atomic_write_text
from build_stock_research_explorer import build_company
from build_stock_research_history import fetch_performance
from private_storage import PrivateStorage
from publish_stock_research_explorer import publish_live, isolated_storage_client
from sec_client import SecClient
from stock_research_explorer import SCHEMA, compact_company, expand_company, LocalCompanies, read_explorer_json
from stock_valuation_aliases import research_aliases


def refresh(root,cache,*,only=None,publish=False,as_of=None):
    as_of=as_of or datetime.now(timezone.utc).date().isoformat()
    store=PrivateStorage(root=root);objects=store.objects
    pointer_raw=objects.http.request('GET',objects.base+'research-explorer/v1/current.json',limit=1024*1024)
    if not pointer_raw:raise ValueError('Publish the initial verified explorer release before refreshing')
    pointer=json.loads(pointer_raw)
    models=read_explorer_json(root,'_system/reference/stock-research/valuation-inputs.json',store)['companies']
    core=read_explorer_json(root,'dashboard/data/core.json',store)
    aliases=research_aliases(root)
    stubs={r['ticker']:r for r in core.get('tickers',[]) if r['ticker'] not in aliases}
    sec=SecClient();registry=sec.get_json('https://www.sec.gov/files/company_tickers.json')
    ciks={r['ticker']:str(r['cik_str']).zfill(10) for r in registry.values()}
    from collections import Counter
    class_counts=Counter(ciks.values())
    cache.mkdir(parents=True,exist_ok=True);(cache/'sec').mkdir(exist_ok=True)
    captures=cache/'prices'/as_of
    # Reuse immutable company objects locally when the release hash agrees.
    company_paths={};failures=[];changed=[]
    readers=threading.local()
    def restore_cached(item):
        ticker,record=item
        path=cache/'companies'/(quote(ticker,safe='')+'.json');path.parent.mkdir(exist_ok=True)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']:raw=path.read_bytes()
        else:
            if not hasattr(readers,'store'):readers.store=isolated_storage_client(store)
            raw=readers.store.restore('live/'+ticker,records={'live/'+ticker:record});path.write_bytes(raw)
        return ticker,path
    with ThreadPoolExecutor(max_workers=3) as pool:
        company_paths.update(pool.map(restore_cached,pointer['companies'].items()))
    companies=LocalCompanies(company_paths)
    def task(ticker):
        row=dict(stubs[ticker]);old=expand_company(companies.get(ticker,{}));model=models.get(ticker) or {'ticker':ticker,'inputs':{},'cases':{},'blockers':['A reviewed valuation input snapshot is required for this new listing.']}
        cik=(model.get('source_identity') or {}).get('current_cik') or old.get('identity',{}).get('cik') or ciks.get(ticker.replace('.','-'))
        source={}
        if cik and str(cik).isdigit():
            cik=str(cik).zfill(10);path=cache/'sec'/(cik+'.json.gz');stamp=path.with_suffix('.date')
            try:
                if not path.exists() or not stamp.exists() or stamp.read_text()!=as_of:
                    data=sec.get_json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
                    if int(data.get('cik',0))!=int(cik):raise ValueError('SEC identity mismatch')
                    path.write_bytes(gzip.compress(json.dumps(data,separators=(',',':')).encode(),mtime=0));stamp.write_text(as_of)
                source=json.loads(gzip.decompress(path.read_bytes()))
            except Exception as exc:
                failures.append({'ticker':ticker,'source':'SEC','error':type(exc).__name__})
                if path.exists():source=json.loads(gzip.decompress(path.read_bytes()))
        row['multiple_quoted_classes']=class_counts.get(str(cik).zfill(10),0)>1
        try:fetch_performance(ticker,row,captures)
        except Exception as exc:failures.append({'ticker':ticker,'source':'prices','error':type(exc).__name__})
        path=captures/(quote(ticker,safe='')+'.json.gz')
        if not path.exists():
            failures.append({'ticker':ticker,'source':'prices','error':'unavailable'})
            if old:return compact_company(old)
        capture=json.loads(gzip.decompress(path.read_bytes())) if path.exists() else {}
        brief={'profile':{'category':old.get('profile','operating')},'financials':{'currency':old.get('currency','USD'),'series':old.get('series',[]),'fiscal_year_end':old.get('fiscal_year_end')}}
        supplements={k:old.get(k,[]) for k in ('expectations','segments')}
        # Operating supplements are explicit, sourced custom series only.
        supplements['series']=[s for s in old.get('series',[]) if s.get('statement')=='operating']
        vendor=None
        if not source:
            from stock_valuation_sources import fetch_history, vendor_history
            try:vendor=vendor_history(fetch_history(capture.get('symbol') or ticker,cache/'vendor'/as_of),as_of)
            except Exception as exc:failures.append({'ticker':ticker,'source':'vendor_annual','error':type(exc).__name__})
        document=build_company(ticker,brief,row,model,source,capture,as_of,supplements,vendor)
        document['events']=sorted({json.dumps(e,sort_keys=True):e for e in [*document['events'],*old.get('events',[])]}.values(),key=lambda e:e.get('date',''),reverse=True)[:200]
        if old.get('kpis'):document['kpis']=old['kpis']
        if old.get('peers'):document['peers']=old['peers']
        return compact_company(document)
    selected=sorted(set(only or stubs)&set(stubs))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(task,t):t for t in selected}
        for i,future in enumerate(as_completed(futures),1):
            ticker=futures[future]
            try:
                result=future.result();path=cache/'companies'/(quote(ticker,safe='')+'.json')
                _atomic_write_text(path,json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n');company_paths[ticker]=path;changed.append(ticker)
            except Exception as exc:failures.append({'ticker':ticker,'source':'build','error':type(exc).__name__})
            if i%25==0:print(json.dumps({'refreshed':i,'requested':len(selected),'source_gaps':len(failures)}),flush=True)
    companies=LocalCompanies({t:p for t,p in company_paths.items() if t in stubs})
    if set(stubs)-set(companies):raise ValueError('Missing stock documents after refresh')
    if not changed:raise ValueError('No company refresh completed; retaining the prior release')
    document={'schema_version':SCHEMA,'as_of':as_of,'companies':companies}
    report={'stocks':len(companies),'refreshed':len(changed),'source_gaps':failures}
    from audit_stock_research_explorer import audit
    verified=audit(companies,stubs)
    if verified['errors']:raise ValueError('Financial refresh failed source/identity/size audit: '+json.dumps(verified['errors'][:5]))
    report['audit']={k:v for k,v in verified.items() if k!='errors'}
    if publish:
        report['publication']=publish_live(root,document,store,workers=3)
        from stock_research_alerts import evaluate_saved_alerts
        report['monitoring']=evaluate_saved_alerts(root,store)
    _atomic_write_text(cache/'last-refresh.json',json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--cache',type=Path,required=True);p.add_argument('--ticker',action='append');p.add_argument('--publish',action='store_true');a=p.parse_args()
    print(json.dumps(refresh(a.root,a.cache,only=a.ticker,publish=a.publish)),flush=True)
