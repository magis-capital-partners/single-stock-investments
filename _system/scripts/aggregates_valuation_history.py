"""Monthly valuation marks using only financial filings available by each mark."""
from aggregates_facts import financial_history, balance_at


def build(vintages, shares, prices, config, calculate):
    if config.get('shares_per_listing_unit') is None:return []
    monthly={}
    for mark in prices:
        if mark.get('price',0)>0 and mark.get('date'):monthly[mark['date'][:7]]=mark
    result=[]
    for mark in sorted(monthly.values(),key=lambda r:r['date']):
        day=mark['date']
        if day<config.get('listing_unit_valid_from','0000'):continue
        available=[r for r in vintages if r.get('filed_at') and r['filed_at']<=day and r['period_end']<=day]
        selected={}
        for r in available:
            key=(r['metric'],r.get('period_start'),r['period_end'])
            if key not in selected or r['filed_at']>selected[key]['filed_at']:selected[key]=r
        observed=list(selected.values())
        annual=[r for r in financial_history(observed) if r['period_type']=='FY' and r.get('revenue_usd') is not None]
        counts=[r for r in shares if r.get('filed') and r['filed']<=day and r.get('end','')<=day and not r.get('start') and r.get('val',0)>0]
        if not annual or not counts:continue
        count=max(counts,key=lambda r:(r['end'],r['filed']))
        from datetime import date
        if (date.fromisoformat(day)-date.fromisoformat(count['end'])).days>120:continue
        instant_dates=sorted({r['period_end'] for r in observed if r['period_type']=='instant'})
        if not instant_dates:continue
        balance=balance_at(observed,instant_dates[-1])
        financial={**annual[-1],**{k:v for k,v in balance.items() if k!='sources'}}
        mcap=mark['price']*count['val']/config['shares_per_listing_unit']
        metrics=calculate(financial,mark['price'],mcap)
        result.append({'date':day,'price':mark['price'],'financial_period_end':annual[-1]['period_end'],'balance_date':instant_dates[-1],'shares_as_of':count['end'],'flow_basis':'FY','ev_ebitda':metrics['ev_ebitda'],'fcf_yield_pct':metrics['fcf_yield_pct'],'basis':'Monthly close; only then-public filed financial observations; EV and EBITDA proxies'})
    return result
