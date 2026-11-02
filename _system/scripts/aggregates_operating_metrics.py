"""Comparable issuer operating observations; nulls never imply zero."""
from __future__ import annotations
from datetime import date, timedelta
from aggregates_facts import finite

METRICS={
 'shipments_million_tons':('million short tons','Shipments'),
 'organic_volume_growth_pct':('%','Organic volume growth'),
 'price_per_ton':('USD/short ton','Freight-adjusted price / ton'),
 'organic_price_growth_pct':('%','Organic price growth'),
 'cash_gp_per_ton':('USD/short ton','Cash gross profit / ton'),
 'cash_cost_per_ton':('USD/short ton','Cash cost / ton'),
 'segment_ebitda_usd':('USD','Aggregates segment EBITDA'),
 'segment_revenue_usd':('USD','Aggregates segment revenue'),
 'gross_profit_per_ton':('USD/short ton','Gross profit / ton'),
 'reserves_million_tons':('million short tons','Proven and probable reserves'),
 'production_million_tons':('million short tons','Annual production'),
 'reserve_life_years':('years','Reserve life'),
 'permitted_reserve_life_years':('years','Permitted reserve life'),
 'reserve_additions_million_tons':('million short tons','Reserve additions'),
 'maintenance_capex_usd':('USD','Maintenance capex'),
 'growth_capex_usd':('USD','Growth capex'),
 'backlog_usd':('USD','Contracting backlog'),
 'quarries':('sites','Active quarries'),
 'terminals':('sites','Terminals'),
 'aggregates_revenue_mix_pct':('%','Aggregates revenue mix'),
 'aggregates_profit_mix_pct':('%','Aggregates profit mix'),
    'segment_gross_profit_usd':('USD','Aggregates segment gross profit'),
    'organic_profit_growth_pct':('%','Organic profit growth'),
    'acquired_profit_growth_pct':('%','Acquired profit contribution'),
}
COMPARABILITY=('business_segment','geography','product','freight_basis','sales_scope','perimeter_basis','unit','currency')


def validate(row):
    required=['ticker','metric','value','unit','period_end','period_type','business_segment','geography','product','freight_basis','sales_scope','perimeter_basis','status','source_url','locator','published_at','retrieved_at']
    missing=[k for k in required if row.get(k) is None]
    if missing:raise ValueError('Missing observation fields: '+', '.join(missing))
    if row['metric'] not in METRICS:raise ValueError('Unknown operating metric: '+row['metric'])
    if not finite(row['value']):raise ValueError('Non-finite operating observation')
    if not row['source_url'].startswith('https://'):raise ValueError('Primary source URL required')
    date.fromisoformat(row['period_end'])
    if row['unit']!=METRICS[row['metric']][0]:raise ValueError('Normalize units before ranking')
    if row['metric']=='permitted_reserve_life_years' and not row.get('permission_evidence'):raise ValueError('Permitted life needs explicit permission evidence')
    return row


def comparable(a,b):
    return all(a.get(k)==b.get(k) for k in COMPARABILITY)


def operating_periods(observations):
    observations=[r for r in observations if r.get('status')!='superseded']
    # Reconcile cumulative disclosures into standalone quarters. Dollar/ton
    # observations require their matching shipment weights; never subtract ASPs.
    additive={'shipments_million_tons','segment_revenue_usd','segment_ebitda_usd','segment_gross_profit_usd','production_million_tons','maintenance_capex_usd','growth_capex_usd'}
    derived=[]
    for current in observations:
        if current.get('period_type') not in {'FY','YTD'} or not current.get('period_start'):continue
        previous=[r for r in observations if r['ticker']==current['ticker'] and r['metric']==current['metric'] and r.get('period_start')==current['period_start'] and r['period_end']<current['period_end'] and comparable(r,current)]
        if not previous:continue
        prior=max(previous,key=lambda r:(r['period_end'],r['published_at']))
        start=(date.fromisoformat(prior['period_end'])+timedelta(days=1)).isoformat()
        days=(date.fromisoformat(current['period_end'])-date.fromisoformat(start)).days+1
        if not 70<=days<=110:continue
        if any(r['ticker']==current['ticker'] and r['metric']==current['metric'] and r.get('period_start')==start and r['period_end']==current['period_end'] and r['period_type']=='Q' for r in observations):continue
        value=None;inputs=[current,prior]
        if current['metric'] in additive:value=current['value']-prior['value']
        elif current['metric'].endswith('_per_ton'):
            tons=[]
            for item in [current,prior]:
                matches=[r for r in observations if r['ticker']==item['ticker'] and r['metric']=='shipments_million_tons' and r.get('period_start')==item['period_start'] and r['period_end']==item['period_end'] and all(r.get(k)==item.get(k) for k in COMPARABILITY if k not in {'unit','currency','freight_basis'})]
                tons.append(max(matches,key=lambda r:(r['published_at'],r['retrieved_at'])) if matches else None)
            if all(tons) and tons[0]['value']>tons[1]['value']:
                value=(current['value']*tons[0]['value']-prior['value']*tons[1]['value'])/(tons[0]['value']-tons[1]['value']);inputs+=tons
        if value is not None:
            derived.append({**current,'value':round(value,6),'period_start':start,'period_type':'Q','status':'derived','inputs':inputs,'formula_version':'cumulative-period-difference-v1'})
    observations+=derived
    selected={}
    for row in observations:
        validate(row)
        key=(row['ticker'],row['metric'],row.get('period_start'),row['period_end'],row['period_type'],tuple(row.get(k) for k in COMPARABILITY))
        old=selected.get(key)
        if not old or (row['published_at'],row['retrieved_at'])>(old['published_at'],old['retrieved_at']):selected[key]=row
    periods={}
    for row in selected.values():
        key=(row['ticker'],row['period_end'],row['period_type'])
        p=periods.setdefault(key,{'ticker':row['ticker'],'period_start':row.get('period_start'),'period_end':row['period_end'],'period_type':row['period_type'],'metrics':{},'conflicts':[]})
        old=p['metrics'].get(row['metric'])
        if old and (old['value']!=row['value'] or not comparable(old,row)):
            p['conflicts'].append(row['metric']);p['metrics'].pop(row['metric'],None)
        elif row['metric'] not in p['conflicts']:p['metrics'][row['metric']]=row
    result=sorted(periods.values(),key=lambda r:(r['period_end'],r['period_type']))
    # TTM unit economics are shipment-weighted, never an average of ASPs.
    for ticker in sorted({p['ticker'] for p in result}):
        quarters=[p for p in result if p['ticker']==ticker and p['period_type']=='Q']
        for index in range(3,len(quarters)):
            four=quarters[index-3:index+1]
            if not all(p.get('period_start') for p in four):continue
            if not all((date.fromisoformat(b['period_start'])-date.fromisoformat(a['period_end'])).days==1 for a,b in zip(four,four[1:])):continue
            tons=[p['metrics'].get('shipments_million_tons') for p in four]
            if not all(tons) or not all(comparable(tons[0],t) for t in tons[1:]):continue
            total=sum(t['value'] for t in tons)
            if total<=0:continue
            ttm={'ticker':ticker,'period_start':four[0]['period_start'],'period_end':four[-1]['period_end'],'period_type':'TTM','metrics':{},'conflicts':[]}
            for key in ['shipments_million_tons','segment_revenue_usd','segment_ebitda_usd','segment_gross_profit_usd','price_per_ton','cash_gp_per_ton','cash_cost_per_ton']:
                observations=[p['metrics'].get(key) for p in four]
                if not all(observations) or not all(comparable(observations[0],o) for o in observations[1:]):continue
                value=sum(o['value']*t['value'] for o,t in zip(observations,tons))/total if key.endswith('_per_ton') else sum(o['value'] for o in observations)
                ttm['metrics'][key]={**observations[-1],'value':round(value,6),'period_start':ttm['period_start'],'period_end':ttm['period_end'],'period_type':'TTM','status':'derived','inputs':observations,'formula_version':'four-contiguous-quarters-v1'}
            result.append(ttm)
    result.sort(key=lambda r:(r['period_end'],r['period_type']))
    for p in result:
        m=p['metrics'];price=m.get('price_per_ton');profit=m.get('cash_gp_per_ton')
        if price and profit and all(price.get(k)==profit.get(k) for k in COMPARABILITY if k!='unit') and 'cash_cost_per_ton' not in m:
            m['cash_cost_per_ton']={**price,'metric':'cash_cost_per_ton','value':round(price['value']-profit['value'],6),'status':'derived','inputs':[price,profit],'formula_version':'price-minus-cash-profit-v1'}
        previous=[x for x in result if x['ticker']==p['ticker'] and x['period_type']==p['period_type'] and x['period_end'][:4]==str(int(p['period_end'][:4])-1) and x['period_end'][5:7]==p['period_end'][5:7]]
        prior=previous[-1] if previous else None
        p['changes']={}
        if prior:
            for key,row in m.items():
                old=prior['metrics'].get(key)
                if old and comparable(row,old):
                    p['changes'][key]={'delta':round(row['value']-old['value'],6),'growth_pct':round(100*(row['value']/old['value']-1),3) if old['value'] else None,'start':prior['period_end'],'end':p['period_end']}
            price_change=p['changes'].get('price_per_ton');cost_change=p['changes'].get('cash_cost_per_ton')
            p['price_cost_spread_change']=round(price_change['delta']-cost_change['delta'],6) if price_change and cost_change else None
        reserves=m.get('reserves_million_tons');production=m.get('production_million_tons')
        if reserves and production and production['value']>0 and 'reserve_life_years' not in m and all(reserves.get(k)==production.get(k) for k in COMPARABILITY):
            m['reserve_life_years']={**reserves,'metric':'reserve_life_years','unit':'years','value':round(reserves['value']/production['value'],2),'status':'derived','inputs':[reserves,production],'formula_version':'reserves-over-production-v1'}
        revenue=m.get('segment_revenue_usd');ebitda=m.get('segment_ebitda_usd')
        p['segment_ebitda_margin_pct']=round(100*ebitda['value']/revenue['value'],2) if revenue and ebitda and revenue['value']>0 and all(revenue.get(k)==ebitda.get(k) for k in COMPARABILITY) else None
        p['incremental_margin_pct']=None
        if prior and revenue and ebitda:
            old_rev=prior['metrics'].get('segment_revenue_usd');old_profit=prior['metrics'].get('segment_ebitda_usd')
            if old_rev and old_profit and comparable(revenue,old_rev) and comparable(ebitda,old_profit) and abs(revenue['value']-old_rev['value'])>max(abs(old_rev['value'])*.01,1e6):
                p['incremental_margin_pct']=round(100*(ebitda['value']-old_profit['value'])/(revenue['value']-old_rev['value']),2)
    return result
