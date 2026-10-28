"""Measured input readiness and derived physical diagnostics, separate from assumptions."""
from datetime import date
from statistics import mean

from commodity_common import series

REQUIRED={
    'crude':['wti_spot','brent_spot','oecd_commercial_stocks','opec_spare_capacity','cushing_stocks','east_coast_distillate_stocks','east_coast_distillate_use'],
    'copper':['copper_spot'],
    'gold':['gold_bullion','real_yield','broad_dollar'],
    'silver':['gold_bullion','silver_bullion','london_silver_stocks'],
}
GAPS={
    'crude':[
        ('scenario_calibration','validation_required','Archived STEO publisher forecasts are evaluated separately. Stress coefficients and post-2027 scenarios still require independent validation.','https://www.eia.gov/outlooks/steo/outlook.php'),
        ('global_storage_capacity','not_publicly_observable','Regional tank capacity does not establish a global inventory ceiling.','https://www.eia.gov/petroleum/storagecapacity/')],
    'copper':[
        ('concentrate_balance','licensed_or_manual_source','Aligned concentrate supply, SX-EW and smelter intake are needed; total refined copper is not a substitute.','https://icsg.org/statistical/'),
        ('regional_exchange_stocks','source_integration_required','Separate dated LME, COMEX and SHFE stocks; warrants and warehouse stocks must not be double counted.','https://www.lme.com/en/Market-Data/Reports-and-data/Warehouse-and-stocks-reports/Warehouse-and-queue-data'),
        ('treatment_charge_history','licensed_or_manual_source','A comparable dated spot TC series is required; one press-release observation is not a time series.','https://icsg.org/publications-list/')],
    'gold':[
        ('global_miner_cost_curve','licensed_or_manual_source','FY2025 Newmont, Barrick and Agnico Eagle costs are attached. Broader standardized mine coverage is still needed for global percentiles; the three-company panel is not a bullion floor.','https://www.gold.org/goldhub/data')],
    'silver':[
        ('available_inventory','not_publicly_observable','Warehouse metal includes ETF holdings and unavailable private ownership. Do not infer an exhaustion date from gross stocks.','https://www.lbma.org.uk/prices-and-data/london-vault-data'),
        ('lease_rates','licensed_or_manual_source','A dated consistent lease-rate history is needed for financing stress.','https://www.lbma.org.uk/prices-and-data'),
        ('pv_technology_path','scenario_assumption','Technology adoption and silver intensity beyond published survey years remain explicit scenarios.','https://silverinstitute.org/silver-supply-demand/')],
}


def readiness(name,panel,as_of):
    rows=[]
    keys=REQUIRED[name]+(['cushing_working_capacity'] if name=='crude' else [])
    for key in keys:
        item=panel.get('series',{}).get(key,{})
        observations=series(panel,key,as_of)
        stale=item.get('stale',False)
        if observations:
            stale=stale or (as_of-date.fromisoformat(observations[-1]['date'])).days>item.get('max_age_days',120)
        status='missing' if not observations else 'fetch_failed' if item.get('status')=='fetch_failed' else 'stale' if stale else 'available'
        rows.append({'id':key,'status':status,'source_url':item.get('source_url'),'unit':item.get('unit'),'frequency':item.get('frequency'),
                     'last_observation':observations[-1]['date'] if observations else None,'observations':len(observations),'required':key in REQUIRED[name]})
    rows.extend({'id':key,'status':state,'reason':reason,'source_url':url,'required':False} for key,state,reason,url in GAPS[name])
    if name=='crude':
        validation=panel.get('oil_forecast_validation',{})
        rows.append({'id':'publisher_forecast_vintages','status':'available' if validation.get('complete') and validation.get('rows') else 'partial' if validation.get('rows') else 'missing',
                     'observations':validation.get('vintages',0),'source_url':'https://www.eia.gov/outlooks/steo/outlook.php','required':False})
    return {'available':sum(r['status']=='available' for r in rows),'total':len(rows),'items':rows,
            'required_ready':all(r['status']=='available' for r in rows if r['required'])}


def crude_inputs(panel,as_of):
    data={k:series(panel,k,as_of) for k in REQUIRED['crude']+['cushing_working_capacity']}
    result={}
    years=list(range(as_of.year-5,as_of.year));normals=[]
    for quarter in range(1,5):
        values=[r['value'] for r in data['oecd_commercial_stocks'] if int(r['date'][:4]) in years and int(r['date'][5:7])==quarter*3]
        if len(values)!=5:break
        normals.append(mean(values))
    if len(normals)==4:result.update(seasonal_oecd_stock_mb=normals,normal_basis=f"{years[0]}–{years[-1]} same-quarter end stocks; five-year mean, latest published vintage")
    for key,target,scale in [('opec_spare_capacity','spare_capacity_mbd',1),('cushing_stocks','cushing_stocks_mb',1000)]:
        if data[key]:result[target]=data[key][-1]['value']/scale
    # Match monthly use with stocks in that same month. Never divide current
    # weekly stock by old seasonal demand and label it current days of cover.
    use={r['date'][:7]:r for r in data['east_coast_distillate_use']}
    common=[r for r in data['east_coast_distillate_stocks'] if r['date'][:7] in use and use[r['date'][:7]]['value']>0]
    if common:
        stock=common[-1];consumption=use[stock['date'][:7]]
        result['east_coast_distillate_days']=stock['value']/consumption['value']
        result['distillate_basis']={'stock_date':stock['date'],'use_period':consumption['date'][:7],'note':'End-of-month weekly stock / monthly average product supplied; regional proxy, not current demand.'}
    if data['cushing_stocks'] and data['cushing_working_capacity']:
        capacity=data['cushing_working_capacity'][-1];stock=data['cushing_stocks'][-1]
        result['cushing_capacity']={'capacity_thousand_barrels':capacity['value'],'capacity_date':capacity['date'],'stock_date':stock['date'],'indicative_utilization_pct':100*stock['value']/capacity['value'],
                                    'capacity_stale':panel['series']['cushing_working_capacity'].get('stale',True),'note':'Different survey dates; diagnostic only. Cushing capacity is not a global storage constraint.'}
    result['input_dates']={k:v[-1]['date'] for k,v in data.items() if v}
    return result


def ratio_history(panel,as_of):
    gold={r['date'][:7]:r['value'] for r in series(panel,'gold_bullion',as_of)}
    return [{'period':r['date'][:7],'value':gold[r['date'][:7]]/r['value']} for r in series(panel,'silver_bullion',as_of) if r['date'][:7] in gold and r['value']>0]
