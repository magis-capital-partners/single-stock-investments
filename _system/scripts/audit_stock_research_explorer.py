"""Fail publication on missing identities, nonfinite values, look-ahead or size drift."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
import json
import math
from pathlib import Path
from urllib.parse import quote
from stock_research_explorer import SCHEMA, expand_company, LocalCompanies


def audit(companies,expected=None):
    errors=[];financial=valuation=points=0;metrics=Counter();largest=0;currencies=Counter()
    if expected and set(expected)!=set(companies):errors.append({'coverage_difference':sorted(set(expected)^set(companies))})
    for ticker in companies:
        compact=companies[ticker];doc=expand_company(compact)
        if doc.get('ticker')!=ticker or doc.get('schema_version')!=SCHEMA:errors.append({'ticker':ticker,'error':'identity/schema'})
        if doc.get('capital_actionable') is not False or doc.get('authority')!='screening_only':errors.append({'ticker':ticker,'error':'research authority'})
        seen=set();has_financial=has_valuation=False
        for s in doc.get('series',[]):
            if s['id'] in seen:errors.append({'ticker':ticker,'metric':s['id'],'error':'duplicate metric'})
            seen.add(s['id'])
            for f in ('annual','quarterly','monthly','annual_as_reported','quarterly_as_reported','ttm'):
                periods=[]
                for p in s.get(f,[]):
                    points+=1;v=p.get('value');periods.append(p.get('period'))
                    try:date.fromisoformat(p['period'])
                    except (ValueError,TypeError,KeyError):errors.append({'ticker':ticker,'metric':s['id'],'error':'invalid fiscal date'})
                    if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):errors.append({'ticker':ticker,'metric':s['id'],'error':'nonfinite metric'})
                    if f=='monthly':
                        has_valuation=True;metrics[s['id']]+=1
                        for ref in [p.get('source',{}),*p.get('source_refs',[])]:
                            if ref and ref.get('filed','9999')>=p['period']:errors.append({'ticker':ticker,'metric':s['id'],'error':'filing look-ahead','period':p['period']})
                        if not s['id'].endswith('yield') and p.get('denominator',0)<=0:errors.append({'ticker':ticker,'metric':s['id'],'error':'N/M denominator'})
                        if doc.get('profile') in {'bank','insurance','holding'} and s['id'] in {'pfcf','fcf_yield','ev_sales','ev_ebitda','ev_ebit'}:errors.append({'ticker':ticker,'metric':s['id'],'error':'financial company cash-flow multiple'})
                    elif f in {'annual','quarterly'}:has_financial=True
                    if not p.get('source') and not p.get('source_refs'):errors.append({'ticker':ticker,'metric':s['id'],'error':'uncited metric'})
                if periods!=sorted(set(periods)):errors.append({'ticker':ticker,'metric':s['id'],'frequency':f,'error':'duplicate or unordered periods'})
        financial+=has_financial;valuation+=has_valuation;currencies[doc.get('currency')]+=1
        size=len(json.dumps(compact,ensure_ascii=False,separators=(',',':')).encode());largest=max(largest,size)
        if size>20*1024*1024:errors.append({'ticker':ticker,'error':'hosting size limit'})
    return {'stocks':len(companies),'financial_history':financial,'valuation_history':valuation,'observations':points,'historical_valuation_observations':dict(metrics),'reporting_currencies':dict(currencies),'largest_company_bytes':largest,'errors':errors}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--core',type=Path);a=p.parse_args()
    manifest=json.loads((a.source/'explorer.json').read_text(encoding='utf-8'))
    companies=LocalCompanies({t:a.source/'companies'/(quote(t,safe='')+'.json') for t in manifest['company_parts']},wrapped=True)
    expected=[r['ticker'] for r in json.loads(a.core.read_text(encoding='utf-8'))['tickers']] if a.core else None
    report=audit(companies,expected);(a.source/'full-universe-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    if report['errors']:raise SystemExit(1)
