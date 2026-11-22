"""Comparable financial share counts, with original reported values retained."""
from __future__ import annotations
from datetime import date
from datetime import datetime,timedelta,timezone
import re
import math
from urllib.parse import quote
from zoneinfo import ZoneInfo

SHARE_IDS={'shares','diluted_shares','basic_eps','diluted_eps','book_value_per_share','tangible_book_per_share','revenue_per_share','fcf_per_share'}


def captured_basis(capture,model,currency):
    meta=capture.get('data',{}).get('meta',{});zone=ZoneInfo(meta.get('exchangeTimezoneName') or 'UTC')
    blockers=[b for b in model.get('blockers',[]) if re.search(r'claim|ADR|share.basis|successor|listing|conversion|split|identity',b,re.I)]
    eligible=bool(capture.get('symbol')) and not blockers and model.get('method') not in {'preferred','payoff'} and meta.get('currency')==currency
    return {'eligible':eligible,'as_of':str(capture.get('retrieved_at',''))[:10],
            'source_url':'https://finance.yahoo.com/quote/'+quote(capture.get('symbol',''),safe='')+'/history/',
            'reason':'; '.join(blockers) or ('' if eligible else 'A verified common-share/listing/reporting basis is required.'),
            'splits':sorted([{'date':(datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=s['date'])).astimezone(zone).date().isoformat(),'factor':s['numerator']/s['denominator']} for s in capture.get('data',{}).get('events',{}).get('splits',{}).values() if s.get('denominator',0)>0],key=lambda s:s['date'])}


def align_series(doc,series):
    identity=series['id'];basis=doc.get('share_basis') or {}
    if series.get('statement')=='valuation' and 'share_basis' in doc and not basis.get('eligible'):
        return {**series,'monthly':[],'gap':basis.get('reason') or 'A verified common-share basis is required.'}
    if identity=='pe':
        earnings=next((s for s in doc.get('series',[]) if s['id']=='earnings_yield'),{})
        if 'monthly' in earnings:
            return {**series,'definition':'Then-available reported-share market capitalization / TTM common earnings; positive earnings only.',
                    'monthly':[{**p,'value':100/p['value'],'basis':'Reported-share market capitalization / then-available TTM common earnings'} for p in earnings['monthly'] if p['value']>0]}
    if identity not in SHARE_IDS:return series
    class_gap='share_basis' in doc and not basis.get('eligible') and re.search(r'multiple listed|ADR|conversion|share class|preferred|payoff|claim', ' '.join([basis.get('reason',''),*doc.get('gaps',[])]),re.I)
    if class_gap:return {**series,'annual':[],'quarterly':[],'gap':'The reported issuer share basis has not been reconciled to this quoted security.'}
    def adjust(p):
        if identity in {'basic_eps','diluted_eps'} and 'EPS rounding' in p.get('basis',''):return None
        if not basis.get('eligible'):return {**p,'share_basis_status':'unverified'}
        refs=[p.get('source') or {},*p.get('source_refs',[])]
        if identity in {'book_value_per_share','tangible_book_per_share','revenue_per_share','fcf_per_share'}:
            refs=[r for r in refs if re.search('shares',r.get('locator',''),re.I)]
        dates={r.get('filed') for r in refs if r.get('filed')}
        if not dates:return {**p,'share_basis_status':'unverified'}
        factors=set()
        for filed in dates:
            factor=1.
            for split in basis.get('splits',[]):
                if split['date']>filed:factor*=split['factor']
            factors.add(factor)
        if len(factors)!=1:
            # A weighted YTD difference spanning a split cannot be scaled once.
            return None
        factor=factors.pop()
        if factor<=0:return None
        value=p['value']*factor if series.get('unit')=='shares' else p['value']/factor
        if not math.isfinite(value):return None
        return {**p,'value':value,'reported_value':p.get('reported_value',p['value']),'share_factor':factor,'share_basis_status':'aligned',
                'basis':p.get('basis','Reported')+'; split-aligned to '+str(basis.get('as_of'))+' share basis',
                'source_refs':[*(p.get('source_refs') or [p.get('source')]),{'url':basis.get('source_url'),'locator':'Captured split ledger; factors applied only after the original source filing date'}]}
    return {**series,**{f:[q for p in series.get(f,[]) if (q:=adjust(p)) is not None] for f in ('annual','quarterly')}}
