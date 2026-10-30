"""Four separate economic engines. No caller writes a stock valuation or base IRR."""
from __future__ import annotations

import math
from datetime import date

from commodity_common import LB_PER_TONNE, check, finite, series, shell
from commodity_inputs import crude_inputs, ratio_history


def crude(config, panel, as_of):
    out = shell(config, panel, as_of)
    ref = {**config['reference'], **crude_inputs(panel,as_of)}
    out['reference'] = ref
    history = ref['quarterly']
    out['history'] = [{**r, 'basis': 'published_estimate' if r['period'] >= '2026-Q1' else 'published_history'} for r in history if r['period'] < ref['forecast_start']]
    out['observed_prices'] = {k: series(panel, k, as_of) for k in ['wti_spot', 'brent_spot']}
    out['publisher_forecast_validation']=panel.get('oil_forecast_validation',{})
    out['inventory_basis'] = 'OECD commercial inventories; world flows are accounted for separately. World absolute stocks unavailable.'
    for r in history:
        out['validation'].append(check(r['period'] + ' world flow', r['production_mbd'] - r['consumption_mbd'] + r['world_draw_mbd'], .025))
    for scenario in config['scenarios']:
        rows, stock, cumulative, high_quarters = [], ref['starting_oecd_stock_mb'], 0.0, 0
        previous = next(r for r in history if r['period'] == ref['forecast_start'])
        for year in range(2026, 2033):
            for quarter in range(1, 5):
                period = f'{year}-Q{quarter}'
                if period < ref['forecast_start']:
                    continue
                from calendar import monthrange
                days = sum(monthrange(year, m)[1] for m in range(quarter * 3 - 2, quarter * 3 + 1))
                official = next((r for r in history if r['period'] == period), None)
                extension = official is None
                base = official or {**previous, 'production_mbd': previous['production_mbd'] * (1+scenario['production_growth_pct']/400), 'consumption_mbd': previous['consumption_mbd'] * (1+scenario['demand_growth_pct']/400)}
                shock = scenario['supply_shock_mbd'] * (scenario['shock_decay_per_year'] ** max(0, year-2027))
                response = scenario['shale_response_mbd'] if high_quarters >= 4 and len(rows) >= scenario['shale_lag_quarters'] else 0
                production = base['production_mbd'] + shock + response
                demand = base['consumption_mbd'] + scenario['demand_shock_mbd']
                balance = production - demand
                world_change = balance * days
                cumulative += world_change
                # Never feed a global balance directly into OECD stocks.
                oecd_change = (base['oecd_stock_mb'] - stock if official else 0) + (shock + response - scenario['demand_shock_mbd']) * days * scenario['oecd_shock_share']
                # Official levels are anchors. Reconcile prior scenario deviation separately.
                if official:
                    prior_official = ref['starting_oecd_stock_mb'] if not rows else rows[-1]['reference_oecd_stock_mb']
                    oecd_change = official['oecd_stock_mb'] - prior_official + (shock + response - scenario['demand_shock_mbd']) * days * scenario['oecd_shock_share']
                else:
                    oecd_change = balance * days * scenario['oecd_shock_share']
                next_stock = stock + oecd_change
                feasible = next_stock > 0
                normal = ref['seasonal_oecd_stock_mb'][quarter-1]
                gap_days = (next_stock-normal) / base['oecd_consumption_mbd'] if feasible else None
                # Published prices only survive when all scenario shocks are zero.
                pure = scenario['id'] == 'steo' and official is not None
                spread = official['brent']-official['wti'] if pure else scenario['brent_wti_spread']
                if pure:
                    brent = official['brent']
                elif feasible:
                    # During EIA's horizon, stress its price using only the
                    # scenario's incremental stock deviation (no double count).
                    price_anchor = official['brent'] if official else scenario['anchor_brent']
                    price_gap = (next_stock-official['oecd_stock_mb'])/base['oecd_consumption_mbd'] if official else gap_days
                    brent = max(1.0, price_anchor-scenario['usd_per_inventory_day']*price_gap+scenario['disruption_premium'])
                else:
                    brent = None
                wti = max(.01, brent-spread) if brent is not None else None
                high_quarters = high_quarters+1 if wti is not None and wti > config['cost_floor']['value'] else 0
                rows.append({'period':period, 'basis':'published_forecast' if pure else 'analyst_extension' if extension else 'analyst_scenario',
                             'price_status':'published_forecast' if pure else 'reduced_form_assumption', 'price':round(brent,2) if brent is not None else None,
                             'wti':round(wti,2) if wti is not None else None, 'spread':spread, 'production_mbd':round(production,4), 'consumption_mbd':round(demand,4),
                             'world_balance_mbd':round(balance,4), 'world_stock_change_mb':round(world_change,4), 'world_cumulative_change_mb':round(cumulative,4),
                             'oecd_stock_mb':round(next_stock,3) if feasible else None, 'oecd_stock_change_mb':round(oecd_change,3),
                             'reference_oecd_stock_mb':base['oecd_stock_mb'], 'inventory_gap_days':round(gap_days,3) if gap_days is not None else None,
                             'shale_response_mbd':response, 'feasible':feasible, 'cost_binding':False, 'balance_residual':round(production-demand-world_change/days,8)})
                if not feasible:
                    break
                stock, previous = next_stock, base
        out['scenarios'].append({**scenario, 'rows':rows})
    out['validation'].append({'check':'scenario forecast holdout', 'passed':None, 'reason':'Archived publisher forecasts are evaluated separately. The dashboard stress coefficients have not been validated as forecasts.'})
    return out


def copper(config, panel, as_of):
    out = shell(config, panel, as_of)
    ref = config['reference']
    out['history'] = ref['history']
    out['observed_prices']={'copper_spot':series(panel,'copper_spot',as_of)}
    supply, intake = ref.get('concentrate_supply_kt'), ref.get('smelter_intake_kt')
    concentrate_balance = supply-intake if finite(supply) and finite(intake) else None
    out['concentrate'] = {'mine_supply_kt': ref['annual'][0]['mine_kt'], 'sxew_kt':ref.get('sxew_kt'), 'concentrate_supply_kt':supply,
                         'smelter_intake_kt':intake, 'balance_kt':concentrate_balance,
                         'treatment_charge':ref.get('treatment_charge'), 'status':'measured' if concentrate_balance is not None else 'missing_concentrate_split',
                         'note':'Total mined copper includes SX-EW. A concentrate balance cannot be inferred by subtracting total refined use from mine supply.'}
    out['exchange_stocks'] = ref['exchange_stocks']
    use_kt = next(r['use_kt'] for r in ref['annual'] if r['year']==2026)
    out['exchange_stocks'] = {**out['exchange_stocks'], 'aggregate_global_use_days': ref['exchange_stocks']['total_t']/1000/use_kt*365}
    out['validation'] = [check(str(r['year'])+' refined accounting',r['refined_kt']-r['use_kt']-r['balance_kt'],1.01) for r in ref['annual']]
    for row in ref.get('monthly_balances',[]):
        out['validation'].append(check(row['period']+' monthly refined accounting',row['refined_kt']-row['use_kt']-row['balance_kt'],1.01))
    exchange=ref['exchange_stocks']
    changes=[exchange[k].get('ytd_change_t') for k in ['COMEX','SHFE','LME']]
    if all(finite(v) for v in changes):out['validation'].append(check('exchange stock change geography',sum(changes)-exchange['year_to_date_change_t'],1))
    for s in config['scenarios']:
        rows=[]
        previous=ref['annual'][0]
        for year in range(2026,2033):
            official=next((r for r in ref['annual'] if r['year']==year),None)
            base=official or {'refined_kt':previous['refined_kt']*(1+s['refined_growth_pct']/100),'use_kt':previous['use_kt']*(1+s['demand_growth_pct']/100),'mine_kt':previous['mine_kt']*(1+s['mine_growth_pct']/100)}
            price=s['price_path'][min(year-2026,len(s['price_path'])-1)]
            scrap=max(0,price/ref['price_anchor_usd_tonne']-1)*s['scrap_response_kt']
            production=base['refined_kt']-s['concentrate_disruption_kt']+scrap
            use=base['use_kt']+s['unreported_china_absorption_kt']
            balance=production-use
            rows.append({'period':str(year), 'basis':'analyst_scenario' if official else 'analyst_extension','price_status':'analyst_assumption','price':price,'usd_lb':round(price/LB_PER_TONNE,4),
                         'mine_kt':round(base['mine_kt'],3), 'refined_kt':round(production,3),'use_kt':round(use,3),'balance_kt':round(balance,3),
                         'published_balance_kt':official['balance_kt'] if official else None,'scrap_response_kt':round(scrap,3),
                         'concentrate_balance_kt':concentrate_balance-s['concentrate_disruption_kt'] if concentrate_balance is not None else None,
                         'concentrate_disruption_kt':s['concentrate_disruption_kt'],'unreported_china_absorption_kt':s['unreported_china_absorption_kt'],
                         'balance_residual':round(production-use-balance,8)})
            previous=base
        out['scenarios'].append({**s,'rows':rows})
    out['validation'].append({'check':'concentrate mass balance','passed':None if concentrate_balance is None else True,'reason':'Dated concentrate supply and smelter intake required; no invented concentrate deficit.' if concentrate_balance is None else 'Concentrate supply minus smelter intake. Scenario shocks are counted once in refined production.'})
    return out


def gold_residual(panel, as_of):
    """Fit a historical diagnostic on 2010-2021; never extrapolate it as a price target."""
    from collections import defaultdict
    import numpy as np
    monthly={}
    for key in ['gold_bullion','real_yield','broad_dollar']:
        buckets=defaultdict(list)
        for r in series(panel,key,as_of):
            if key=='real_yield' or r['value']>0:
                buckets[r['date'][:7]].append(r['value'])
        monthly[key]={k:sum(v)/len(v) for k,v in buckets.items()}
    dates=sorted(set(monthly['gold_bullion']) & set(monthly['real_yield']) & set(monthly['broad_dollar']))
    training=[d for d in dates if '2010-01' <= d <= '2021-12']
    if len(training)<60:
        return {'status':'unavailable','reason':'At least 60 aligned monthly bullion, real-yield and broad-dollar observations required. Futures and ETF history are not substituted.','rows':[]}
    X=lambda d:[1, monthly['real_yield'][d], math.log(monthly['broad_dollar'][d])]
    coef,_,rank,_=np.linalg.lstsq(np.array([X(d) for d in training]), np.array([math.log(monthly['gold_bullion'][d]) for d in training]),rcond=None)
    if rank<3:return {'status':'unavailable','reason':'Training inputs have insufficient independent variation.','rows':[]}
    rows=[{'period':d,'observed':monthly['gold_bullion'][d],'fitted':math.exp(float(np.dot(coef,X(d)))), 'residual_usd_oz':monthly['gold_bullion'][d]-math.exp(float(np.dot(coef,X(d))))} for d in dates]
    holdout=[r for r in rows if r['period']>'2021-12']
    anchor=monthly['gold_bullion'][training[-1]]
    diagnostics={'months':len(holdout),'rmse_usd_oz':math.sqrt(sum(r['residual_usd_oz']**2 for r in holdout)/len(holdout)) if holdout else None,
                 'constant_2021_price_rmse_usd_oz':math.sqrt(sum((r['observed']-anchor)**2 for r in holdout)/len(holdout)) if holdout else None,
                 'basis':'Post-training residuals using realized contemporaneous inputs and latest revised history. Not an investable forecast backtest.'}
    return {'status':'historical_diagnostic','train_end':'2021-12','training_months':len(training),'coefficients':coef.tolist(),'holdout_diagnostic':diagnostics,
            'rows':rows,
            'note':'Diagnostic only. The post-2021 residual may reflect omitted drivers; it does not identify a causal central-bank premium.'}


def gold(config, panel, as_of):
    out=shell(config,panel,as_of)
    ref=config['reference']
    out['history']=ref['history']
    out['observed_prices']={'gold_bullion':series(panel,'gold_bullion',as_of)}
    out['residual_diagnostic']=gold_residual(panel,as_of)
    out['validation']=[check('above-ground categories',sum(ref['stock_categories_t'].values())-ref['above_ground_t'],100),
                       check('quarterly supply',ref['mine_q2_t']+ref['hedging_q2_t']+ref['recycling_q2_t']-ref['supply_q2_t'],.11),
                       check('quarterly demand',sum(ref['demand_q2_t'].values())-ref['supply_q2_t'],.11)]
    for s in config['scenarios']:
        rows=[]
        stock=ref['above_ground_t']
        for year in range(2027,2033):
            step=year-2026
            mine=ref['mine_annual_t']*(1+s['mine_growth_pct']/100)**step
            prior=stock
            # End-Q2 stock anchor: the first year includes the intervening half year explicitly.
            elapsed=1.5 if year==2027 else 1
            stock+=mine*elapsed
            rates=s['real_yield_change_pp']*min(step/2,1)
            dollar=s['dollar_change_pct']*min(step/2,1)/100
            official_bid=(s['central_bank_t']-ref['central_bank_annual_t'])/1000
            exponent=s['yield_elasticity']*rates+s['dollar_elasticity']*math.log1p(dollar)+s['official_bid_elasticity']*official_bid
            price=ref['price_usd_oz']*math.exp(exponent)*(1+s['nominal_drift_pct']/100)**step
            recycling=ref['recycling_annual_t']*(1+s['recycling_price_elasticity']*max(0,price/ref['price_usd_oz']-1))
            jewellery=ref['jewellery_annual_t']*max(.1,1-s['jewellery_price_elasticity']*max(0,price/ref['price_usd_oz']-1))
            rows.append({'period':str(year),'basis':'analyst_extension','price_status':'reduced_form_assumption','price':round(price,2),'above_ground_t':round(stock,2),
                         'mine_t':round(mine,2),'elapsed_years':elapsed,'recycling_t':round(recycling,2),'jewellery_t':round(jewellery,2),
                         'central_bank_t':s['central_bank_t'],'etf_t':s['etf_t'],'real_yield_change_pp':rates,'dollar_change_pct':dollar*100,
                         'stock_residual':round(stock-prior-mine*elapsed,8),'cost_binding':None})
        out['scenarios'].append({**s,'rows':rows})
    return out


def silver(config, panel, as_of, gold_model):
    out=shell(config,panel,as_of)
    ref=config['reference']
    out['history']=ref['annual']
    out['observed_prices']={'silver_bullion':series(panel,'silver_bullion',as_of)}
    out['observed_gold_silver_ratio']=ratio_history(panel,as_of)
    out['warehouse_inventory']={'london':series(panel,'london_silver_stocks',as_of),'unit':'million troy oz','available_inventory_moz':None,
                               'note':'London vault stocks already contain ETF metal. ETF ownership is not added to physical stocks. Gross holdings do not establish available inventory.'}
    out['gold_dependency_hash']=gold_model['config_sha256']
    out['validation']=[check(str(r['year'])+' physical balance',r['supply_moz']-r['demand_moz']-r['balance_moz'],.11) for r in ref['annual']]
    for s in config['scenarios']:
        rows=[]
        gold_path=next(g for g in gold_model['scenarios'] if g['id']==s['gold_scenario'])['rows']
        base=ref['annual'][-1]
        cumulative=0
        for g in gold_path:
            year=int(g['period']); step=year-2026
            pv=base['pv_moz']*(1+s['pv_growth_pct']/100)**step
            byproduct_base=ref['byproduct_2025_moz']*(1+s['byproduct_growth_pct']/100)
            byproduct=byproduct_base*(1+s['byproduct_growth_pct']/100)**step
            primary=(base['mine_moz']-byproduct_base)*(1+s['primary_growth_pct']/100)**step
            recycling=base['recycling_moz']*(1+s['recycling_growth_pct']/100)**step
            # 2026 supply also includes hedging and other published adjustments.
            other_supply=base['supply_moz']-base['mine_moz']-base['recycling_moz']
            supply=primary+byproduct+recycling+other_supply
            non_pv=base['demand_moz']-base['pv_moz']
            demand=non_pv*(1+s['other_demand_growth_pct']/100)**step+pv
            balance=supply-demand
            less_etp=balance-s['etp_moz']
            cumulative+=less_etp
            price=g['price']/s['gold_silver_ratio']
            rows.append({'period':str(year),'basis':'analyst_extension','price_status':'gold_path_divided_by_assumed_ratio','price':round(price,2),
                         'gold_price':g['price'],'gold_silver_ratio':s['gold_silver_ratio'],'pv_moz':round(pv,2),'primary_moz':round(primary,2),
                         'byproduct_moz':round(byproduct,2),'recycling_moz':round(recycling,2),'other_supply_moz':round(other_supply,2),
                         'supply_moz':round(supply,2),'demand_moz':round(demand,2),'balance_moz':round(balance,2),'etp_moz':s['etp_moz'],
                         'balance_less_etp_moz':round(less_etp,2),'cumulative_inventory_change_moz':round(cumulative,2),
                         'cost_binding':price<=config['cost_floor']['value'],'balance_residual':round(supply-demand-balance,8)})
        out['scenarios'].append({**s,'rows':rows})
    out['byproduct_bridge']={'included_in_balance':False,'note':'Copper-linked disruption is a cross-check only; the byproduct path already accounts for its own growth assumption.'}
    return out
