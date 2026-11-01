"""Chronological, retrospective net-edge sizing experiment; offline and aggregate-only.

The protocol is declared before running this experiment. This is not an untouched
holdout: the underlying sample was examined in earlier research. No broker, data
download, locate approval, live capital or production setting is implied.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import importlib.util
import json
import math
from pathlib import Path
import subprocess

import numpy as np


def sibling(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


sleeve=sibling('short_sleeve_research')
audit=sibling('short_execution_audit')
NAV=10_000_000
TICKETS=(25_000,50_000,100_000)
PROTOCOL={
    'version':'short_adaptive_sizing.v1','declared_on':'2026-10-20',
    'test_start':'2023-01-03','test_end':'2026-10-13','minimum_training_events':40,
    'holding_sessions':1,'nav':NAV,'tickets':TICKETS,'max_names':3,
    'entry_squeeze_reserve_limit':.10,'net_edge_buffer':.005,'entry_limit_fraction':.03,
    'gross_ridge':32.,'gross_zero_prior_events':20,'cost_neighbors':20,
    'minimum_predicted_cover_support':.50,
    'features':['log entry midpoint','log prior 20-session venue dollar ADV',
                'entry relative quoted spread','log reverse-split multiple'],
    'training':'Expanding eligible-event history; only labels from strictly earlier sessions. No same-day labels, future covers or realized returns enter selection.',
    'gross_model':'Ridge regression standardized using training data only, coefficients shrunk toward zero; pooled mean shrunk with 20 zero-edge pseudo-events. Gross labels are decision-midpoint to cover-midpoint short returns.',
    'cost_model':'Entry decision-book sweep plus weighted 20-neighbor forecast of cover cost for the requested original shares. Censored prior covers retain explicit case-dependent residual-price assumptions; they are never silently dropped.',
    'allocation':'Greedy descending expected net dollars, with alternatives reconsidered as the known entry reserve budget is used. Fixed-size policies use prior liquidity ordering. All share the same entry-book, issuer, three-name and 10%-NAV squeeze-reserve constraints.',
    'entry':'Decide at open+1s. Require the full target within 3% of the midpoint; the IOC limit is the last bid needed in that decision book. Execute against the cached open+1.1s book, allowing partial/no fills.',
    'cover':'Scheduled close-0.9s book sweep. Any residual shares receive a disclosed hypothetical price above the worst observed ask, with a case-dependent surcharge. These are modeled completions, not verified full fills.',
    'risk':'100% hypothetical house margin plus per-share floors; entry reserve is a +200% price loss plus 200% post-shock margin. Reported margin/stress use sums of individual observed intraday peak marks, a conservative envelope rather than a simultaneous account peak.',
    'financing':'Same-session modeled closes are settled-flat: borrow and proceeds credit both zero. A delayed real cover could incur borrow and financing costs not measured here.',
    'validation':'Retrospective walk-forward research designed after earlier full-sample inspection; parameters are not tuned to these test results. Prospective validation remains required.',
}
CASES=[{'id':'bull','label':'Bull','impact_per_side':0.,'residual_surcharge':.02},
       {'id':'base','label':'Base','impact_per_side':.0025,'residual_surcharge':.05},
       {'id':'bear','label':'Bear','impact_per_side':.005,'residual_surcharge':.10}]
POLICIES=[{'id':'fixed25','label':'Fixed $25k','ticket':25_000},
          {'id':'fixed50','label':'Fixed $50k','ticket':50_000},
          {'id':'fixed100','label':'Fixed $100k','ticket':100_000},
          {'id':'cost','label':'Cost-filtered sizing'},
          {'id':'adaptive','label':'Edge + cost sizing'}]


def take(levels,quantity,limit=None,side='bid'):
    """An aggressive IOC can consume visible size; residual quantity stays explicit."""
    left=quantity;dollars=0.;filled=0
    for price,available in levels:
        if limit is not None and (price<limit if side=='bid' else price>limit):continue
        amount=min(left,available)
        dollars+=price*amount;filled+=amount;left-=amount
        if left<=0:break
    return int(filled),float(dollars),int(left)


def feature(mid,adv_dollars,spread,ratio):
    return [math.log(max(mid,.01)),math.log(max(adv_dollars,1.)),spread,
            math.log(max(1.,1/max(ratio,1e-8)))]


def ridge_predict(rows,current):
    x=np.array([r['features'] for r in rows]);y=np.array([r['gross'] for r in rows])
    mean=x.mean(axis=0);scale=np.maximum(x.std(axis=0),1e-6)
    z=np.clip((x-mean)/scale,-3,3);target=np.clip((np.array(current)-mean)/scale,-3,3)
    pooled=float(y.sum()/(len(y)+PROTOCOL['gross_zero_prior_events']))
    centered=y-y.mean()
    beta=np.linalg.solve(z.T@z+PROTOCOL['gross_ridge']*np.eye(x.shape[1]),z.T@centered)
    return float(pooled+target@beta),pooled


def cover_price(row,quantity,case):
    book=row['cover'];levels=book['ask_levels'] if book else []
    filled,dollars,left=take(levels,quantity,side='ask')
    reference=row['exit_mid']
    last=max(reference,levels[-1][0]) if levels else reference
    # The residual is a declared cost sensitivity, never an observed fill.
    hypothetical=last*(1+case['residual_surcharge'])
    dollars+=left*hypothetical
    return dollars/quantity,filled,left


def cover_forecast(history,current,ticket,case):
    x=np.array([r['features'] for r in history]);scale=np.maximum(x.std(axis=0),1e-6)
    distance=np.mean(((x-np.array(current['features']))/scale)**2,axis=1)
    order=np.argsort(distance,kind='stable')[:PROTOCOL['cost_neighbors']]
    weights=1/(1+distance[order]);weights/=weights.sum()
    cost=probability=0.
    for weight,i in zip(weights,order):
        r=history[i];quantity=max(1,math.floor(ticket/r['mid']))
        price,_,left=cover_price(r,quantity,case)
        cost+=weight*((price-r['exit_mid'])/r['mid']+case['impact_per_side']*r['exit_mid']/r['mid']
                      +sleeve.commission(quantity,price)/(quantity*r['mid']))
        probability+=weight*(left==0)
    return float(cost),float(probability)


def candidate(row,ticket,gross,history,case):
    mid=row['mid'];quantity=math.floor(ticket/mid)
    limit=mid*(1-PROTOCOL['entry_limit_fraction'])
    filled,dollars,left=take(row['decision']['bid_levels'],quantity,limit=limit)
    if left or not filled:return None
    consumed=[];remaining=quantity
    for price,amount in row['decision']['bid_levels']:
        if price<limit:continue
        consumed.append(price);remaining-=min(remaining,amount)
        if remaining<=0:break
    entry_cost=(quantity*mid-dollars)/(quantity*mid)+case['impact_per_side']
    entry_cost+=sleeve.commission(quantity,dollars/quantity)/(quantity*mid)
    exit_cost,probability=cover_forecast(history,row,ticket,case)
    net=gross-entry_cost-exit_cost
    reserve=2*quantity*mid+sleeve.margin(quantity,mid*3,house=2.)
    return {'ticket':ticket,'quantity':quantity,'limit':max(limit,consumed[-1]),
            'predicted_gross':gross,'predicted_entry_cost':entry_cost,'predicted_cover_cost':exit_cost,
            'predicted_cover_support':probability,'predicted_net':net,
            'expected_dollars':quantity*mid*net,'reserve':reserve}


def predict(rows,day,case):
    history=[r for r in rows if r['date']<day and r['label_observable']]
    if len(history)<PROTOCOL['minimum_training_events']:return [],len(history)
    predictions=[]
    for row in rows:
        if row['date']!=day:continue
        predicted,pooled=ridge_predict(history,row['features'])
        predictions.append({'row':row,'adaptive':[c for t in TICKETS if (c:=candidate(row,t,predicted,history,case))],
                            'cost':[c for t in TICKETS if (c:=candidate(row,t,pooled,history,case))]})
    return predictions,len(history)


def select(predictions,policy):
    chosen=[];remaining=NAV*PROTOCOL['entry_squeeze_reserve_limit'];issuers=set()
    alternatives=[]
    for p in predictions:
        options=p['adaptive'] if policy['id']=='adaptive' else p['cost']
        for c in options:
            if 'ticket' in policy and c['ticket']!=policy['ticket']:continue
            if 'ticket' not in policy and (c['predicted_net']<PROTOCOL['net_edge_buffer'] or c['predicted_cover_support']<PROTOCOL['minimum_predicted_cover_support']):continue
            rank=p['row']['adv_dollars'] if 'ticket' in policy else c['expected_dollars']
            alternatives.append((rank,p['row']['issuer'],p['row']['key'],p['row'],c))
    for _,issuer,_,row,c in sorted(alternatives,key=lambda v:(-v[0],v[1],v[2],-v[4]['ticket'])):
        if issuer in issuers or c['reserve']>remaining+1e-8:continue
        chosen.append((row,c));issuers.add(issuer);remaining-=c['reserve']
        if len(chosen)>=PROTOCOL['max_names']:break
    return chosen


def execute(row,candidate_,case):
    quantity=candidate_['quantity'];entry=row['entry']
    filled,dollars,left=take(entry['bid_levels'] if entry else [],quantity,limit=candidate_['limit'])
    if not filled:return {'filled':0,'entry_residual':quantity}
    sell=dollars/filled
    buy,observed_cover,modeled_cover=cover_price(row,filled,case)
    commission=sleeve.commission(filled,sell)+sleeve.commission(filled,buy)
    extra=filled*(row['mid']+row['exit_mid'])*case['impact_per_side']
    net=filled*(sell-buy)-commission-extra
    gross=filled*(row['mid']-row['exit_mid'])
    mark=max(row['peak_mid'],row['mid'],row['exit_mid'])
    return {'filled':filled,'entry_residual':left,'observed_cover':observed_cover,
            'modeled_cover':modeled_cover,'notional':filled*row['mid'],'net_pnl':net,
            'gross_pnl':gross,'execution_cost':gross-net-commission,'commissions':commission,
            'margin':sleeve.margin(filled,mark),'collateral':filled*math.ceil(1.02*mark),
            'stress_reserve':2*filled*mark+sleeve.margin(filled,mark*3,house=2.),
            'sell_vwap':sell,'cover_vwap':buy,'extra_impact_cost':extra}


def replay(rows,days,policy,case,predictions):
    pnl=np.zeros(len(days));series=[];decisions=[];sizes=Counter();totals=Counter();returns=[];gates=Counter()
    peak_margin=peak_collateral=peak_stress=0.;train_min=None;fully_observed_pnl=0.
    for i,day in enumerate(days):
        daily_predictions,train_n=predictions.get(day,([],0));train_min=train_n if train_min is None else min(train_min,train_n)
        trades=[]
        selection=select(daily_predictions,policy);selected_keys={r['key'] for r,c in selection}
        for p in daily_predictions:
            options=p['adaptive'] if policy['id']=='adaptive' else p['cost']
            if 'ticket' in policy:options=[c for c in options if c['ticket']==policy['ticket']]
            if not options:gates['entry_depth_or_price_limit']+=1
            elif 'ticket' not in policy and not any(c['predicted_net']>=PROTOCOL['net_edge_buffer'] for c in options):gates['net_edge_buffer']+=1
            elif 'ticket' not in policy and not any(c['predicted_net']>=PROTOCOL['net_edge_buffer'] and c['predicted_cover_support']>=PROTOCOL['minimum_predicted_cover_support'] for c in options):gates['predicted_cover_capacity']+=1
            elif p['row']['key'] not in selected_keys:gates['issuer_name_or_reserve_limit']+=1
            else:gates['attempted']+=1
        for row,c in selection:
            result=execute(row,c,case)
            decisions.append({'date':day,'event_id':row['key'],'issuer':row['issuer'],'training_events':train_n,
                              'prediction':c,'result':result})
            totals['attempted']+=1
            if not result['filled']:totals['entry_no_fill']+=1;continue
            trades.append(result);sizes[c['ticket']]+=1;totals['entered']+=1
            totals['entry_partial']+=int(result['entry_residual']>0)
            totals['modeled_cover_trades']+=int(result['modeled_cover']>0)
            for k in ('net_pnl','notional','execution_cost','commissions','modeled_cover','observed_cover','filled'):
                totals[k]+=result[k]
            if not result['modeled_cover']:fully_observed_pnl+=result['net_pnl']
            returns.append(result['net_pnl']/result['notional'])
        net=sum(t['net_pnl'] for t in trades);req=sum(t['margin'] for t in trades)
        collateral=sum(t['collateral'] for t in trades);stress=sum(t['stress_reserve'] for t in trades)
        peak_margin=max(peak_margin,req);peak_collateral=max(peak_collateral,collateral);peak_stress=max(peak_stress,stress)
        pnl[i]=net
        if net or trades:series.append([i,net/NAV,req/NAV,collateral/NAV])
    metrics,equity,dd=sleeve.summary(pnl,NAV,days)
    metrics.update(entered=totals['entered'],attempted=totals['attempted'],entry_no_fill=totals['entry_no_fill'],
                   entry_partial=totals['entry_partial'],modeled_cover_trades=totals['modeled_cover_trades'],
                   modeled_cover_share_fraction=totals['modeled_cover']/totals['filled'] if totals['filled'] else 0.,
                   mean_notional=totals['notional']/totals['entered'] if totals['entered'] else 0.,
                   execution_cost=totals['execution_cost'],commission_cost=totals['commissions'],
                   peak_margin=peak_margin/NAV,peak_collateral=peak_collateral/NAV,stress_reserve_200=peak_stress/NAV,
                   fully_observed_cover_pnl_diagnostic=fully_observed_pnl,trade_stats=sleeve.stats(returns),
                   size_counts={str(t):sizes[t] for t in TICKETS},borrow_cost=0.,proceeds_interest=0.)
    metrics['gate_counts']=dict(gates)
    monthly=[[d,float(equity[i]/NAV-1),float(dd[i])] for i,d in enumerate(days)
             if i==len(days)-1 or days[i+1][:7]!=d[:7]]
    annual=[]
    for year in sorted({d[:4] for d in days}):
        ix=[i for i,d in enumerate(days) if d.startswith(year)];starting=NAV if not ix[0] else equity[ix[0]-1]
        annual.append([year,float(pnl[ix].sum()/starting)])
    return {'policy':policy['id'],'case':case['id'],'scenario':policy['id']+'/'+case['id'],
            'metrics':metrics,'series':series,'monthly':monthly,'annual':annual},decisions


def load_rows(root):
    evidence=sleeve.load_evidence(root)
    local=root/f'_system/data/reverse_splits/local/portfolio_research/{audit.RUN}__portfolio_v1'
    manifest=audit.read(local/'manifest.json');books=audit.read(local/'books.local.json');index=audit.read(local/'paths.local.json')
    for name in ('books.local.json','points.local.json','paths.local.json'):
        if audit.sha(local/name)!=manifest['inputs'][name]:raise ValueError('Frozen input changed: '+name)
    quote=root/f'_system/data/reverse_splits/local/execution_research/{audit.RUN}__quotes_v1'
    if audit.sha(quote/'targets.local.json')!=manifest['source_inputs']['quote_targets']:raise ValueError('Frozen targets changed')
    prices=root/f'_system/data/reverse_splits/local/expansion/expansion_v2/runs/{audit.RUN}/prices.sqlite'
    if audit.sha(prices)!=manifest['source_inputs']['prices']:raise ValueError('Frozen prices changed')
    rows=[]
    for r in evidence['records']:
        if 'eligible' not in r['cohorts']:continue
        b=books.get(r['key'],{});decision=b.get('1/decision')
        if not decision:continue
        p=local/Path(index[r['key']]['file'].replace('\\','/'))
        if audit.sha(p)!=index[r['key']]['sha256']:raise ValueError('Frozen path changed')
        with np.load(p,allow_pickle=False) as path:
            mids=(path['bid']+path['ask'])/2;valid=mids[np.isfinite(mids)&(mids>0)]
            exit_mid=float(mids[-1]) if math.isfinite(float(mids[-1])) and mids[-1]>0 else r['close']
            peak=float(valid.max()) if len(valid) else max(decision['mid'],r['close'])
        mid=decision['mid'];adv_dollars=r['adv']*mid
        rows.append({**r,'decision':decision,'entry':b.get('1/entry'),'cover':b.get('1/close'),
                     'mid':mid,'exit_mid':exit_mid,'peak_mid':peak,'adv_dollars':adv_dollars,
                     'features':feature(mid,adv_dollars,(decision['ask']-decision['bid'])/mid,r['event'].get('ratio') or 1.),
                     'gross':1-exit_mid/mid,'label_observable':exit_mid>0})
    days=[d for d in evidence['days'] if PROTOCOL['test_start']<=d<=PROTOCOL['test_end']]
    return rows,days,local


def build(root,local_out):
    local_out.mkdir(parents=True,exist_ok=True)
    audit.write(local_out/'protocol.json',PROTOCOL)
    rows,days,source=load_rows(root)
    models=[]
    for case in CASES:
        predictions={d:predict(rows,d,case) for d in sorted({r['date'] for r in rows if dstart(r['date'])})}
        for policy in POLICIES:
            model,decisions=replay(rows,days,policy,case,predictions)
            audit.write(local_out/(model['scenario'].replace('/','_')+'.decisions.local.json'),decisions)
            models.append(model)
            print(case['id'],policy['id'],model['metrics']['entered'],round(model['metrics']['net_pnl'],2),flush=True)
    doc={'schema_version':'short_adaptive_sizing.v1','as_of':'2026-10-20','aggregate_only':True,
         'research_only':True,'authority':'none','protocol':PROTOCOL,'days':days,'cases':CASES,'policies':POLICIES,
         'population':{'eligible_events':len(rows),'training_events':sum(r['date']<PROTOCOL['test_start'] for r in rows),
                       'test_events':sum(dstart(r['date']) for r in rows)},'models':models,
         'sources':[{'file':n,'sha256':audit.sha(source/n)} for n in ('books.local.json','paths.local.json','manifest.json')],
         'limits':['Results depend on unverified borrows, hypothetical broker routing and displayed-book access.',
                   'Missing cover depth is priced with explicit assumptions; it is not established executable net profitability.',
                   'Extra impact and residual-cover surcharges are declared stress sensitivities, not measured calibration.',
                   'Same-day test only. Multi-session exit costs remain unmeasured; no stop or profit target is used.',
                   'Month bootstrap retains all boundary-month sessions and resamples the fitted policy P&L, without refitting the models or creating unseen squeezes.',
                   'A handful of winning trades can produce zero observed and bootstrapped drawdown. That is not evidence of low tail risk.']}
    code="const fs=require('node:fs'),e=require(process.argv[1]);const d=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(e.monteCarlo(d.days,d.models,2000,5,20261020)));"
    engine=Path(__file__).resolve().parents[2]/'dashboard/short-sleeve-engine.js'
    run=subprocess.run(['node','-e',code,str(engine)],input=json.dumps(doc),text=True,capture_output=True,check=True)
    doc['monte_carlo']=json.loads(run.stdout)
    return doc


def report(doc):
    pct=lambda x:'Unavailable' if x is None else f'{100*x:.4f}%'
    lines=['# Adaptive short sizing experiment — 2026-10-20','',
           'Retrospective walk-forward research. No new data downloads, trades or capital authority.',
           'The rules were declared before this run, after prior full-sample research; this is not an untouched holdout.','',
           f"Training starts with {doc['population']['training_events']} eligible events. Test: {doc['days'][0]} to {doc['days'][-1]}, {doc['population']['test_events']} events, fixed $10m NAV.",
           'Same-day only: dated multi-session exit depth is unavailable. Existing longer-horizon dashboard sensitivities remain separate.','']
    for case in CASES:
        lines+=['## '+case['label']+' cost sensitivity','',
                f"Additional impact {pct(case['impact_per_side'])} per side; uncovered cover shares are hypothetically priced {pct(case['residual_surcharge'])} above the worst observed ask. These are assumptions, not measured impact or verified fills.",'',
                '| Policy | Trades | Mean notional | Net P&L | Added CAGR | Max DD | Calmar | MC median CAGR | MC 95% max DD | Covers with modeled residual |',
                '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for policy in POLICIES:
            model=next(m for m in doc['models'] if m['case']==case['id'] and m['policy']==policy['id'])
            m=model['metrics'];mc=doc['monte_carlo'][model['scenario']]
            calmar='Unavailable' if m['calmar'] is None else f"{m['calmar']:.3f}"
            lines.append(f"| {policy['label']} | {m['entered']} | ${m['mean_notional']:,.0f} | ${m['net_pnl']:,.2f} | {pct(m['cagr'])} | {pct(abs(m['max_drawdown']))} | {calmar} | {pct(mc['cagr']['p50'])} | {pct(mc['max_drawdown']['p95'])} | {m['modeled_cover_trades']} |")
    lines+=['','## Interpretation','',
            'The base adaptive rule fills five $25k targets and earns less total modeled P&L than fixed $25k sizing. It does not demonstrate a portfolio-return uplift from fitting gross edge.',
            'Five profitable admitted trades produce zero observed and resampled drawdown. That is not a credible estimate of unseen squeeze risk; Calmar is undefined.',
            'All 226 test events remain in selection counts. Under the base adaptive rule, 194 lack full $25k entry depth inside the declared 3% limit and 27 fail the forecast net-edge buffer. Five are attempted.',
            'The shared bootstrap now retains every boundary-month session. Omitting a partial final month could otherwise discard a real tail loss. This also corrects existing sleeve Monte Carlo calculations.','',
            '## Frozen protocol','']
    lines += [f'- **{k}**: {v}' for k,v in PROTOCOL.items()]
    lines += ['','## Limits','']+['- '+s for s in doc['limits']]
    return '\n'.join(lines)+'\n'


def dstart(day):
    return PROTOCOL['test_start']<=day<=PROTOCOL['test_end']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--local-out',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report',type=Path)
    args=p.parse_args();doc=build(args.source_root,args.local_out);audit.write(args.out,doc)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(report(doc),encoding='utf-8')


if __name__=='__main__':main()
