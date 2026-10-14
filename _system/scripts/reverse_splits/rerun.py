"""Frozen fundamental/cost experiment: all 96 independent account replays."""
import csv
import gzip
import hashlib
import json
import math
import re
import shutil
import sqlite3
from pathlib import Path
import platform
from importlib.metadata import version
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

import numpy as np

from .adjust import to_nominal, PriceFrame
from .execute import entry_index
from .filings import parse_accept_time
from .event_audit import audit_clause
from .config import PACKAGE_DIR
from .fundamentals import FundamentalBridge, relative_path
from .framework_plan import routes
from .realism import verified_announcements
from .replay import replay
from .run_book import load_events, load_frames, load_splits


def write_json(path, value):
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(value,allow_nan=False),encoding="utf-8")
    temp.replace(path)


def freeze_inputs(cfg):
    """Create once; an existing experiment always replays its original inputs."""
    root=cfg.data_dir/'reruns/fundamentals_v1';root.mkdir(parents=True,exist_ok=True)
    if not (root/'input.sqlite').exists():
        source=sqlite3.connect(cfg.db_path);target=sqlite3.connect(root/'input.sqlite')
        try:source.backup(target)
        finally:source.close();target.close()
    for source,name in ((cfg.reports_dir/'backtest_rerun_plan.json','plan.json'),
                        (cfg.reports_dir/'corporate_action_corrections.json','corporate_action_corrections.json'),
                        (cfg.public_dir/'backtest.json','backtest.json'),
                        (cfg.public_dir/'baseline_reference.json','baseline_reference.json')):
        if not (root/name).exists():shutil.copy2(source,root/name)
    ledger=cfg.data_dir/'strategy_decisions.sqlite'
    if ledger.exists() and not (root/'decisions.sqlite').exists():
        source=sqlite3.connect(ledger);target=sqlite3.connect(root/'decisions.sqlite')
        try:source.backup(target)
        finally:source.close();target.close()
    return root


def calendar_for(frames,cutoff):
    first=min(d for f in frames.values() for d in f.dates)
    import exchange_calendars as xc
    cal=xc.get_calendar("XNYS")
    return [str(d)[:10] for d in cal.sessions_in_range(first,cutoff)]


def prepare_leads(events,verified,frames,calendar,bridge,cfg,corrections=None,*,min_price=1.0):
    splitmap=load_splits(events)
    for action in (corrections or {}).get('actions',[]):
        ticker=action['ticker'];existing=splitmap.setdefault(ticker,[])
        if not any(d==action['ex_date'] and abs(r-action['ratio'])<1e-10 for d,r in existing):
            existing.append((action['ex_date'],action['ratio']))
    calendar_set=set(calendar)
    converted={}
    audit=[];leads=[]
    for e in verified:
        row={"id":f"{int(e['cik'])}/{e['accession']}","ticker":e["ticker"],"cik":e["cik"],
             "filed_at":e["announce_date"],"accept_time":e.get("accept_time"),"source_url":e["source_url"],
             "announced_ratio":e["announced_ratio"],"announced_ex_date":e.get("announced_ex_date"),
             "identity_basis":"current ticker/CIK mapping; analyst reconciliation required"}
        # Filing text is a source locator, not automatically analyst-approved.
        paths=[cfg.edgar_cache/str(e["cik"]).zfill(10)/(e["accession"]+".txt")]
        text=next((p.read_text(encoding="utf-8",errors="ignore") for p in paths if p.exists()),"")
        match=re.search(r".{0,160}reverse\s+(?:stock\s+)?split.{0,500}",text,re.I|re.S)
        row.update(clause_excerpt=match.group(0).strip() if match else None,
                   filing_text_sha256=hashlib.sha256(text.encode()).hexdigest() if text else None,
                   clause_review_status="requires_analyst_review")
        accept=parse_accept_time(e.get("accept_time"))
        expected=entry_index(calendar,accept=accept,filed=e["announce_date"])
        if expected is None:
            row.update(status="pending_after_cutoff",reason="no_post_publication_market_session");audit.append(row);continue
        expected_day=calendar[expected]
        score=bridge.score(e["ticker"],e["cik"],expected_day)
        row.update(entry_evidence_date=expected_day,fundamental=score,
                   framework_routes=routes(score),score_ge_60=eligible_score(score,60))
        clause=audit_clause(text,e['announce_date'],e.get('announced_ex_date'))
        row.update(announcement_audit=clause,original_announced_ex_date=e.get('announced_ex_date'),
                   announced_ex_date=clause['announced_ex_date'],exact_announced_ratio=clause['exact_ratio'])
        e={**e,'announced_ex_date':clause['announced_ex_date']}
        if not clause['eligible']:
            row.update(status='excluded_or_unavailable',reason=clause['reason']);audit.append(row);continue
        ticker=e["ticker"]
        if e.get("exchange_class")!="listed":
            row.update(status="excluded",reason="not_listed_in_available_mapping");audit.append(row);continue
        if ticker not in frames:
            row.update(status="unavailable",reason="no_price_history");audit.append(row);continue
        if ticker not in converted:
            f=frames[ticker]
            keep=[i for i,d in enumerate(f.dates) if d<=calendar[-1]]
            clipped=PriceFrame(*[[getattr(f,k)[i] for i in keep] for k in ('dates','open','high','low','close','volume')])
            converted[ticker]=to_nominal(clipped,[(d,r) for d,r in splitmap.get(ticker,[]) if d<=calendar[-1]])
        series=converted[ticker];f=series.frame
        row['normalized_split_audit']=[vars(sp) for sp in series.splits]
        ix=entry_index(f.dates,accept=accept,filed=e["announce_date"])
        if ix is not None:
            vendor=frames[ticker].open[frames[ticker].dates.index(f.dates[ix])]
            row.update(observed_entry_date=f.dates[ix],nominal_entry_price=f.open[ix],vendor_entry_price=vendor,
                       price_reconstruction_factor=f.open[ix]/vendor if vendor else None)
        reason=None
        if ix is None:reason="no_observed_entry_quote"
        elif f.dates[ix]!=expected_day:reason="missing_first_eligible_session_quote"
        elif ix in series.ambiguous:reason="ambiguous_nominal_price_at_entry"
        elif f.open[ix]<min_price:reason="below_one_dollar"
        prior_volume=[v for v in f.volume[max(0,(ix or 0)-20):(ix or 0)] if v>0]
        if not reason and len(prior_volume)<20:reason="fewer_than_20_prior_volume_sessions"
        if not reason:
            prev_close=f.close[ix-1];older=f.close[ix-2] if ix>=2 else None
            if (older and f.low[ix-1]<=.9*older) or f.open[ix]<=.9*prev_close:reason="ssr_daily_bar_proxy"
        if not reason and e.get("announced_ex_date") and expected_day>=e["announced_ex_date"]:reason="known_split_already_effective"
        if reason:
            row.update(status="excluded_or_unavailable",reason=reason);audit.append(row);continue
        actual_splits=[sp for sp in series.splits if sp.status in {'raw','continuous'} and sp.ex_date>expected_day]
        marks={}
        blocked_after=min((sp.ex_date for sp in series.splits if sp.status=='ambiguous' and sp.ex_date>expected_day),default=None)
        for j in range(ix,len(f.dates)):
            d=f.dates[j]
            if d not in calendar_set or (blocked_after and d>=blocked_after):continue
            values=[f.open[j],f.high[j],f.low[j],f.close[j]]
            if any(not math.isfinite(v) or v<=0 for v in values) or f.high[j]<max(f.open[j],f.close[j]) or f.low[j]>min(f.open[j],f.close[j]):continue
            factor=math.prod(sp.ratio for sp in actual_splits if sp.ex_date<=d)
            marks[d]={"open":f.open[j],"high":f.high[j],"low":f.low[j],"close":f.close[j],"volume":f.volume[j],"factor":factor}
        if expected_day not in marks:
            row.update(status="unavailable",reason="invalid_entry_ohlc");audit.append(row);continue
        lead={"id":row["id"],"ticker":ticker,"cik":e["cik"],"entry_date":expected_day,"rows":marks,
              "adv":sum(prior_volume)/20,"prior_row":{"high":f.high[ix-1],"low":f.low[ix-1]},
              "announced_ex_date":e.get("announced_ex_date"),"source_url":e["source_url"],"fundamental":score,
              "announcement_category":clause['category']}
        leads.append(lead)
        row.update(status="prepared",reason=None,last_price_date=max(marks),ambiguous_action_after=blocked_after,
                   normalized_split_audit=[vars(sp) for sp in series.splits],adv=lead["adv"])
        audit.append(row)
    return leads,audit


def eligible_score(s,threshold):
    period=s.get("latest_period")
    return bool(s.get("historical_eligible") and s.get("source")=="raw_companyfacts" and s.get("profile")=="operating"
                and s.get("evidence_count",0)>=3 and s.get("score") is not None and s["score"]>=threshold and period
                and 0<=(date.fromisoformat(s["as_of"])-date.fromisoformat(period)).days<=200)


def approved_borrows(conn):
    """Availability alone is not permission. Approved locate evidence stays explicit."""
    result=defaultdict(list)
    for ticker,at,shares,fee,notes in conn.execute('SELECT ticker,asof_ts,shortable_shares,fee_rate,notes FROM borrow_snapshots'):
        try:meta=json.loads(notes or '{}')
        except (ValueError,TypeError):meta={}
        if not isinstance(meta,dict):meta={}
        approval={'approved':meta.get('locate_approved') is True,'reference':meta.get('locate_reference')}
        result[ticker].append((at,shares,fee,approval))
    return result


def metrics(result,initial):
    rows=result["equity"];positions=result["positions"]
    values=np.array([initial]+[r["equity"] for r in rows],dtype=float)
    daily=np.divide(np.diff(values),values[:-1],out=np.zeros(len(values)-1),where=values[:-1]!=0)
    peak=np.maximum.accumulate(values)
    draw=values/peak-1
    closed=[p for p in positions if p["status"]=="closed"]
    pnls=[p["net_pnl"] for p in closed];win=sum(v for v in pnls if v>0);loss=-sum(v for v in pnls if v<0)
    valid=bool(positions) and not result["unresolved"] and not any(r["stale_names"] for r in rows) and np.all(values>0)
    enough=valid and len(closed)>=30 and len({p['cik'] for p in closed})>=20
    years=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(rows[0]['date'])).days/365.25 if rows else 0
    tail=sorted(daily)[:max(1,math.ceil(.05*len(daily)))]
    costs={k:sum(p[k] for p in positions) for k in ('raw_price_pnl','spread_cost','slippage_cost','borrow','commission')}
    total=(values[-1]-initial)
    assert abs(total-(costs['raw_price_pnl']-costs['spread_cost']-costs['slippage_cost']-costs['borrow']-costs['commission']))<max(1e-5,abs(total)*1e-10)
    return {"dollar_pnl":float(total),"final_equity":float(values[-1]),"account_return":float(total/initial),
            "max_drawdown":float(min(draw)),"taken":len(positions),"closed":len(closed),"unique_issuers":len({p['cik'] for p in positions}),
            "unresolved":result['unresolved'],"profit_factor":win/loss if loss else None,
            "mean_closed_return":float(np.mean([p['net_return'] for p in closed])) if closed else None,
            "median_closed_return":float(np.median([p['net_return'] for p in closed])) if closed else None,
            "hit_rate":sum(p['net_pnl']>0 for p in closed)/len(closed) if closed else None,
            "annualized_volatility":float(np.std(daily,ddof=1)*np.sqrt(252)) if valid else None,
            "sharpe_zero_rf":float(np.mean(daily)/np.std(daily,ddof=1)*np.sqrt(252)) if enough and np.std(daily)>0 else None,
            "cagr":float((values[-1]/initial)**(1/years)-1) if valid and years>0 else None,
            "daily_expected_shortfall_5pct":float(np.mean(tail)) if valid and len(daily)>=20 else None,
            "worst_daily_return":float(min(daily)) if valid else None,
            "margin_breach_days":sum(r['margin_breach'] for r in rows),"stale_mark_days":sum(bool(r['stale_names']) for r in rows),
            "partial_cover_positions":sum(p['partial_covers']>0 for p in positions),
            "blocked_cover_days":sum(p['blocked_cover_days'] for p in positions),
            "fractional_obligation_positions":sum(p['fractional_obligation_seen'] for p in positions),
            "turnover_notional":sum(p['notional'] for p in positions)+sum(c['shares']*c['fill'] for c in result['covers']),
            "max_gross_exposure":max((r['gross_exposure'] for r in rows),default=0),
            "worst_position_pnl":min((p['net_pnl'] for p in positions),default=None),
            "costs":costs,"net":float(total),"risk_metrics_basis":"Complete XNYS daily calendar; zero cash yield/risk-free proxy; Sharpe requires ≥30 closed trades/20 issuers and no stale or unresolved marks",
            "pnl_basis":"No trades simulated; no strategy return observed" if not positions else "final marked equity; unresolved liabilities prevent certified realized profitability" if result['unresolved'] else "fully closed modeled positions"}


def stability(result):
    closed=[p for p in result['positions'] if p['status']=='closed']
    output={}
    for field in ('year','issuer','score_band','price_band','liquidity_band','framework_family','announcement_category'):
        buckets=defaultdict(list)
        for p in closed:
            if field=='year':keys=[p['entry_date'][:4]]
            elif field=='issuer':keys=[p['cik']]
            elif field=='score_band':keys=['unscored' if p['score']['score'] is None else '<40' if p['score']['score']<40 else '40–59' if p['score']['score']<60 else '60–79' if p['score']['score']<80 else '80+']
            elif field=='price_band':keys=['$1–2.50' if p['entry_price']<2.5 else '$2.50–5' if p['entry_price']<5 else '$5+']
            elif field=='liquidity_band':keys=['partial/delayed' if p['partial_covers'] or p['blocked_cover_days'] else 'within capacity']
            elif field=='announcement_category':keys=[p['announcement_category']]
            else:keys=routes(p['score'])['suggested_families'] or ['unscored']
            for k in keys:buckets[k].append(p)
        output[field]=[{"group":k,"trades":len(ps),"pnl":sum(p['net_pnl'] for p in ps)} for k,ps in sorted(buckets.items())]
    output['issuer_cluster_interval']=None
    issuers=defaultdict(list)
    for p in closed:issuers[p['cik']].append(p['net_return'])
    if len(issuers)>=10:
        sums=np.array([sum(v) for v in issuers.values()]);counts=np.array([len(v) for v in issuers.values()])
        ix=np.random.default_rng(20261011).integers(0,len(sums),(2000,len(sums)))
        draws=sums[ix].sum(axis=1)/counts[ix].sum(axis=1)
        output['issuer_cluster_interval']=[float(np.quantile(draws,.025)),float(np.quantile(draws,.975))]
    output['leave_one_issuer_out_attribution']=[{"cik":cik,"pnl_without_issuer":sum(p['net_pnl'] for p in closed)-sum(p['net_pnl'] for p in closed if p['cik']==cik)} for cik in issuers]
    daily=result['equity']
    output['calendar_block_interval']=None
    active_blocks={i//20 for i,r in enumerate(daily) if r['gross_exposure'] or (i and r['equity']!=daily[i-1]['equity'])}
    if len(active_blocks)>=10 and not result['unresolved'] and not any(r['stale_names'] for r in daily):
        values=np.array([50000]+[r['equity'] for r in daily])
        if np.all(values>0):
            returns=np.diff(values)/values[:-1]
            log=np.log1p(returns);blocks=[log[i:i+20] for i in range(0,len(log),20)]
            # Full-calendar blocks include cash/idle days; preserve within-block dependence.
            sums=np.array([b.sum() for b in blocks]);counts=np.array([len(b) for b in blocks])
            ix=np.random.default_rng(20261011).integers(0,len(blocks),(2000,len(blocks)))
            draws=np.expm1(252*sums[ix].sum(axis=1)/counts[ix].sum(axis=1))
            output['calendar_block_interval']=[float(np.quantile(draws,.025)),float(np.quantile(draws,.975))]
    output['uncertainty_basis']='Issuer interval: mean closed-trade return, ≥10 issuers. Calendar interval: annualized geometric daily return, 20-session blocks, ≥10 active blocks, fully closed/fresh marks. These do not correct selection bias.'
    cohort=[];sets=[];boundaries=[0,len(daily)//3,2*len(daily)//3,len(daily)]
    for j,label in enumerate(('early','middle','late')):
        start,end=boundaries[j],boundaries[j+1]
        end=max(start,end-(20 if j<2 else 0))
        days={r['date'] for r in daily[start:end]}
        ps=[p for p in closed if p['entry_date'] in days and p['last_cover_date'] in days]
        sets.append({p['cik'] for p in ps})
        cohort.append({'cohort':label,'first':daily[start]['date'] if start<len(daily) else None,
                       'last':daily[end-1]['date'] if end>start else None,'trades':len(ps),
                       'issuers':len(sets[-1]),'pnl':sum(p['net_pnl'] for p in ps)})
    output['chronological_cohorts']=cohort
    output['embargo_sessions']=20
    output['overlapping_cohort_issuers']=sorted((sets[0]&sets[1])|(sets[0]&sets[2])|(sets[1]&sets[2]))
    output['chronological_excluded_trades']=len(closed)-sum(c['trades'] for c in cohort)
    output['note']='Historical stability and deletion attribution; not untouched validation or a rule for deleting known losers. Framework groups overlap. Broad fundamentals-only control needs an independent universe.'
    return output


def run_rerun(cfg):
    root=cfg.data_dir/'reruns/fundamentals_v1'
    spec=json.loads((root/'plan.json').read_text(encoding='utf-8'))
    # The frozen specification may gain explicit field clarifications before execution.
    latest=json.loads((cfg.reports_dir/'backtest_rerun_plan.json').read_text(encoding='utf-8'))
    if spec.get('borrow_max_age_hours') is None:spec['borrow_max_age_hours']=latest['borrow_max_age_hours']
    assert len(spec['cases'])==96
    corrections=json.loads((root/'corporate_action_corrections.json').read_text(encoding='utf-8'))
    conn=sqlite3.connect(root/'input.sqlite');conn.row_factory=sqlite3.Row
    events=load_events(conn);frames=load_frames(conn);borrows=approved_borrows(conn)
    verified,funnel=verified_announcements(events,[dict(r) for r in conn.execute('SELECT * FROM edgar_hits')])
    calendar=calendar_for(frames,spec['input_cutoff'])
    quality=dict(conn.execute('SELECT count(*) AS rows, sum(open IS NULL OR high IS NULL OR low IS NULL) AS substituted_ohlc, sum(volume IS NULL OR volume<=0) AS zero_volume FROM prices_daily').fetchone())
    conn.close()
    refresh=json.loads((root/'source_refresh.json').read_text(encoding='utf-8'))
    bridge=FundamentalBridge(cfg)
    for source in refresh['results']:
        path=bridge.cache/source['file']
        if source.get('sha256') and (not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']):
            raise ValueError(f"Source changed since freeze: {source['file']}; restore the preserved source before reproduction")
    leads,audit=prepare_leads(events,verified,frames,calendar,bridge,cfg,corrections)
    print(f'Prepared {len(leads)} leads; {sum(eligible_score(l["fundamental"],60) for l in leads)} pass score 60 + freshness',flush=True)
    details=root/'scenarios';details.mkdir(exist_ok=True)
    public=cfg.public_dir/'rerun';public.mkdir(parents=True,exist_ok=True)
    summary=[]
    for case in spec['cases']:
        selected=leads if case['selector']=='announcement_only' else [l for l in leads if eligible_score(l['fundamental'],case.get('score_floor',60))]
        try:
            result=replay(selected,calendar,spec,case,borrows)
            m=metrics(result,spec['initial_equity'])
            result.update(case=case,metrics=m,stability=stability(result))
            status='no_historical_borrow_evidence' if case['test']=='strict_borrow' and not result['positions'] else 'unresolved_positions' if result['unresolved'] else 'completed'
            result['status']=status
            write_json(details/(case['id']+'.json'),result)
            write_json(public/(case['id']+'.json'),result)
            summary.append({**case,'status':status,'metrics':m})
            print(case['id'],case['test'],case['selector'],f"P&L {m['dollar_pnl']:.2f}",f"trades {m['taken']} residuals {m['unresolved']}",flush=True)
        except Exception as exc:
            summary.append({**case,'status':'failed','error':str(exc)})
            failure={'case':case,'status':'failed','error':str(exc)}
            write_json(details/(case['id']+'.json'),failure);write_json(public/(case['id']+'.json'),failure)
            print(case['id'],'FAILED',str(exc),flush=True)
        write_json(root/'progress.json',{'completed':len(summary),'total':96,'cases':summary})
    unlimited=[]
    for selector in spec['selectors']:
        case={'id':'unlimited_'+selector,'test':'reconciliation_only','selector':selector,'horizon_sessions':5,'fee_annual':1,'execution':'base'}
        selected=leads if selector=='announcement_only' else [l for l in leads if eligible_score(l['fundamental'],60)]
        r=replay(selected,calendar,spec,case,borrows,constrain_exits=False)
        unlimited.append({'case':case,'metrics':metrics(r,spec['initial_equity'])})
        write_json(root/(case['id']+'.json'),r)
    paired=[]
    for c in summary:
        if c['test']!='core' or c['selector']!='announcement_fundamental_60' or 'metrics' not in c:continue
        other=next((u for u in summary if u['test']=='core' and u['selector']=='announcement_only' and all(u[k]==c[k] for k in ('horizon_sessions','fee_annual','execution'))),None)
        if other and 'metrics' in other:
            paired.append({'filtered':c['id'],'announcement':other['id'],'pnl_difference':c['metrics']['net']-other['metrics']['net'],
                           'drawdown_difference':c['metrics']['max_drawdown']-other['metrics']['max_drawdown'],
                           'taken_difference':c['metrics']['taken']-other['metrics']['taken']})
    regions=[]
    for selector in spec['selectors']:
        for horizon in spec['horizons_sessions']:
            for execution in ('optimistic','base','stress'):
                cells=[c for c in summary if c['test']=='core' and c['selector']==selector and c['horizon_sessions']==horizon and c['execution']==execution]
                positive=[c for c in cells if c.get('metrics',{}).get('net',-1)>0 and c['status']=='completed']
                regions.append({'selector':selector,'horizon_sessions':horizon,'execution':execution,
                    'positive_closed_fee_levels':[c['fee_annual'] for c in positive],
                    'tested_fees':[{ 'fee':c['fee_annual'],'pnl':c.get('metrics',{}).get('net'),'status':c['status'],'trades':c.get('metrics',{}).get('taken'),'drawdown':c.get('metrics',{}).get('max_drawdown')} for c in cells],
                    'interpretation':'Tested account rerun brackets only; no interpolated break-even or availability claim'})
    result={'schema_version':'rerun_results.v1','built_at':datetime.now(timezone.utc).isoformat(),'spec':spec,
            'coverage':{'parsed_announcements':len(verified),'prepared':len(leads),'fundamental_60':sum(eligible_score(l['fundamental'],60) for l in leads),'issuers':len({e['cik'] for e in verified}),
                        'raw_sources_available':sum(r['kind']=='facts' and r['status'] in {'cached','downloaded'} for r in refresh['results']),
                        'funnel':funnel,'exclusions':dict(Counter(a.get('reason') for a in audit if a.get('reason'))),'price_quality':quality,'historical_locates':sum(len(v) for v in borrows.values())},
            'calendar':{'first':calendar[0],'last':calendar[-1],'sessions':len(calendar),'basis':'XNYS exchange calendar'},
            'cases':summary,'lead_audit':audit,'paired':paired,'profitability_regions':regions,'unlimited_exit_reconciliation':unlimited,
            'event_audit':{'version':'event_evidence_audit.v1','categories':dict(Counter(a.get('announcement_audit',{}).get('category','pending') for a in audit)),
                           'corrections':corrections,'corrections_sha256':hashlib.sha256((root/'corporate_action_corrections.json').read_bytes()).hexdigest(),
                           'preliminary_superseded':'Pre-clause-audit four-trade results are preserved privately and superseded. ASTI was a historical split reference; omitted PALI/IBO splits inflated nominal prices.'},
            'limits':spec['limits']+['Exit volume cap uses final daily volume and is an ex-post feasibility proxy, not proof of auction liquidity','Residuals are marked and charged; marks may be stale and obligations unresolved','Corporate action price reconstruction uses historical classification and a partial independently checked repair ledger, not a complete contemporaneous print master','Dividend, recall/buy-in and cash-in-lieu payments are not measured; resulting additional liabilities remain unmodeled','Opening-gap margin covers use the open as a conditional fill proxy; actual broker liquidation is unknown','Settlement/billing timing is approximated by calendar-day daily-mark accrual','Conservative automated clause audit distinguishes scheduled actions, authorizations and past references; final analyst adjudication and exhibit reconciliation remain pending'],
            'provenance':{'input_db_sha256':hashlib.sha256((root/'input.sqlite').read_bytes()).hexdigest(),
                          'plan_sha256':hashlib.sha256((root/'plan.json').read_bytes()).hexdigest(),
                          'code':[{'file':relative_path(p,cfg.repo_root),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(PACKAGE_DIR.glob('*.py'))],
                          'source_refresh':refresh,'ssi':bridge.manifest()}}
    result['execution_status']='completed' if not any(c['status']=='failed' for c in summary) else 'completed_with_failures'
    if (root/'action_source_archives.json').exists():
        result['provenance']['action_source_archives']=json.loads((root/'action_source_archives.json').read_text(encoding='utf-8'))
    result['provenance']['runtime']={'python':platform.python_version(),'packages':{p:version(p) for p in ('numpy','pandas','exchange_calendars','python-dateutil')}}
    scored=[a for a in audit if a.get('fundamental',{}).get('historical_eligible')]
    result['coverage'].update(scored_leads=len(scored),unscored_or_pending_leads=len(audit)-len(scored),
                             prepared_scored=sum(l['fundamental']['historical_eligible'] for l in leads),
                             prepared_by_category=dict(Counter(l['announcement_category'] for l in leads)),
                             fundamental_60_by_category=dict(Counter(l['announcement_category'] for l in leads if eligible_score(l['fundamental'],60))),
                             clause_locators=sum(bool(a['clause_excerpt']) for a in audit))
    result['integrity']={}
    for name in ('backtest.json','baseline_reference.json'):
        saved=root/name;current=cfg.public_dir/name
        result['integrity'][name]={'sha256':hashlib.sha256(saved.read_bytes()).hexdigest(),
                                   'unchanged':saved.read_bytes()==current.read_bytes()}
    def ledger_rows(path):
        db=sqlite3.connect(path)
        try:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {t:db.execute('SELECT * FROM "'+t+'" ORDER BY rowid').fetchall() for t in tables}
        finally:db.close()
    result['integrity']['decisions_unchanged']=ledger_rows(root/'decisions.sqlite')==ledger_rows(cfg.data_dir/'strategy_decisions.sqlite')
    if not all(result['integrity'][n]['unchanged'] for n in ('backtest.json','baseline_reference.json')) or not result['integrity']['decisions_unchanged']:
        raise AssertionError('A preserved comparator or decision ledger changed; reconcile before publication')
    archive=root/'used_ssi';archive.mkdir(exist_ok=True)
    for link in result['provenance']['ssi']['links']:
        path=Path(link['local_path'])
        if path.exists():shutil.copy2(path,archive/path.name)
    sic=bridge.root/'_system/reference/market-data/fundamentals/_sic_map.json'
    if sic.exists():
        shutil.copy2(sic,archive/sic.name)
        result['provenance']['ssi']['sic_map_sha256']=hashlib.sha256(sic.read_bytes()).hexdigest()
    filing_store=root/'used_filing_text';filing_store.mkdir(exist_ok=True)
    for a in audit:
        source=cfg.edgar_cache/str(a['cik']).zfill(10)/(a['id'].split('/')[-1]+'.txt')
        target=filing_store/(a['id'].replace('/','_')+'.txt.gz')
        if source.exists() and not target.exists():
            with source.open('rb') as reader,gzip.open(target,'wb') as writer:shutil.copyfileobj(reader,writer)
    code_store=root/'used_code';code_store.mkdir(exist_ok=True)
    for path in sorted(PACKAGE_DIR.glob('*.py')):shutil.copy2(path,code_store/path.name)
    # Preserve exact used SEC documents for later reproduction.
    store=root/'used_companyfacts';store.mkdir(exist_ok=True)
    for r in refresh['results']:
        source=bridge.cache/r['file'];target=store/(r['file']+'.gz')
        if source.exists() and not target.exists():
            with source.open('rb') as reader,gzip.open(target,'wb') as writer:shutil.copyfileobj(reader,writer)
    write_json(root/'results.json',result);write_json(cfg.public_dir/'rerun.json',result)
    publish_report(cfg,result,root)
    return result


def publish_report(cfg,result,root):
    cfg.public_dir.mkdir(parents=True,exist_ok=True)
    cases=result['cases'];coverage=result['coverage']
    primary=next(c for c in cases if c['id']=='rerun_044')['metrics']
    paired=next(c for c in cases if c['id']=='rerun_008')['metrics']
    ten=next(c for c in cases if c['id']=='rerun_056')['metrics']
    ten_cases=[c for c in cases if c['test']=='core' and c['selector']=='announcement_fundamental_60' and c['horizon_sessions']==10]
    ten_positive=sum(c['status']=='completed' and c['metrics']['net']>0 for c in ten_cases)
    cash=lambda n: ('−$' if n<0 else '$')+f'{abs(n):,.2f}'
    rows=['# Fundamental portfolio rerun results','',f"Built {result['built_at']}. Frozen price cutoff {result['calendar']['last']}. All 96 planned accounts receive an explicit status.",'',
          f"Primary five-session/base-cost/100%-borrow result: **{cash(primary['net'])}** on {primary['taken']} trade(s), {primary['account_return']:.2%} account return and {primary['max_drawdown']:.2%} drawdown. Paired announcement-only marked result: **{cash(paired['net'])}**, with {paired['unresolved']} unresolved liability.",'',
          f"Ten-session/base/100%-borrow filtered result: {cash(ten['net'])}, {ten['account_return']:.2%} account return, {ten['max_drawdown']:.2%} drawdown, {ten['taken']} trade(s). {ten_positive} of twelve ten-session filtered cost/fee brackets are positive and fully closed. A sparse repeated sample does not establish broad alpha.",'',
          '**Filing and corporate-action audit supersedes the preliminary four-trade gains.** ASTI was already a completed split when its filing was published. PALI and IBO had missing reverse-split factors, which inflated their historical printed prices above the $1 entry floor. Preliminary results are archived under `data/reruns/fundamentals_v1/pre_clause_audit`; the original 124-trade comparator is preserved separately. The remaining primary candidate is EDBL, a shareholder-authorization event. Authorizations/proposals remain a distinct cohort and never imply a final ratio or executed action.','',
          f"Coverage: {coverage['parsed_announcements']} parsed leads; {coverage['prepared']} prepared; {coverage['fundamental_60']} pass the primary filter; {coverage['raw_sources_available']} raw companyfacts sources. Historical locates: {coverage['historical_locates']}.",'',
          'Profitable marked accounts with residual positions do not establish realized executable profitability. All results are exploratory and conditional on the available event/price universe.','',
          '| ID | Test | Selector | Sessions | Fee | Costs | Trades | P&L | Drawdown | Residuals | Status |','|---|---|---|---:|---:|---|---:|---:|---:|---:|---|']
    for c in cases:
        m=c.get('metrics',{})
        rows.append(f"| {c['id']} | {c['test']} | {c['selector']} | {c['horizon_sessions']} | {c['fee_annual']} | {c['execution']} | {m.get('taken','—')} | {m.get('dollar_pnl',0):,.2f} | {m.get('max_drawdown',0):.1%} | {m.get('unresolved','—')} | {c['status']} |")
    rows+=['','## Interpretation and limitations','']+[f'- {v}' for v in result['limits']]
    rows+=['','## Tested fee and execution brackets','',
           '| Selector | Hold | Execution | Positive fully closed annual fee levels |','|---|---:|---|---|']
    for region in result['profitability_regions']:
        fees=', '.join(f'{f:.0%}' for f in region['positive_closed_fee_levels']) or 'none'
        rows.append(f"| {region['selector']} | {region['horizon_sessions']} | {region['execution']} | {fees} |")
    rows+=['','These are actual separate account reruns. A transition between tested fee levels brackets conditional profitability; no exact break-even rate is interpolated. Closed P&L excludes residual certification, and none of these cases proves historical locates.','',
           '## Input and preservation checks','',f"{result['calendar']['sessions']} XNYS sessions. {result['coverage']['scored_leads']} leads have historically eligible numeric scores before execution screening. {result['coverage']['unscored_or_pending_leads']} are unscored or pending. {result['coverage']['clause_locators']} cached clause excerpts remain analyst review prompts.",'',
           f"Original dashboard and comparator byte hashes match their preserved copies; append-only decision rows are unchanged: {result['integrity']['decisions_unchanged']}. Every account passes equity and cost-waterfall reconciliation. Input DB SHA-256 `{result['provenance']['input_db_sha256']}`; plan SHA-256 `{result['provenance']['plan_sha256']}`."]
    rows+=['','The same-universe paired comparisons isolate the filter conditional on costs/account rules; positions and capital competition change with each replay. All calendar-year/issuer/score/liquidity groups and leave-one-issuer-out attribution are in scenario detail files. No full-market fundamentals-only causal control or true prospective validation is claimed.','',
           'Sharpe is suppressed for sparse, stale or unresolved books. Daily equity uses every XNYS session including idle capital, with zero cash yield/risk-free proxy. External cash flows are zero in these hypothetical accounts. SSI live holdings/cash flows are not connected.','']
    rows+=['','## Corporate-action correction sources','',
           'The repair ledger is partial. Later confirmation is used only to reconstruct printed-share accounting, never to qualify earlier evidence or change an earlier scheduled exit.']
    rows += [f"- [{a['ticker']} {a['ex_date']} action]({a['source_url']}) — {a['basis']}" for a in result['event_audit']['corrections']['actions']]
    text='\n'.join(rows)
    (cfg.reports_dir/'fundamental_rerun_report.md').write_text(text,encoding='utf-8')
    (cfg.public_dir/'fundamental_rerun_report.md').write_text(text,encoding='utf-8')
    fields=['id','test','selector','horizon_sessions','fee_annual','execution','status','taken','closed','dollar_pnl','max_drawdown','unresolved']
    with (cfg.reports_dir/'rerun_summary.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for c in cases:writer.writerow({k:({**c,**c.get('metrics',{})}).get(k) for k in fields})
    shutil.copy2(cfg.reports_dir/'rerun_summary.csv',cfg.public_dir/'rerun_summary.csv')
    with (cfg.reports_dir/'rerun_ledgers.csv').open('w',newline='',encoding='utf-8') as f, (cfg.reports_dir/'rerun_daily.csv').open('w',newline='',encoding='utf-8') as daily_file:
        fields=['scenario_id','record_type','id','ticker','cik','entry_date','planned_exit','last_cover_date','status','entry_shares','remaining','notional','net_pnl','borrow','commission','partial_covers','mark','mark_date','reason','score','payload_json']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        daily_fields=['scenario_id','date','equity','daily_pnl','gross_exposure','encumbered_proceeds','margin_required','cash_buffer','open_names','stale_names','margin_breach']
        daily_writer=csv.DictWriter(daily_file,fieldnames=daily_fields);daily_writer.writeheader()
        for c in cases:
            path=root/'scenarios'/(c['id']+'.json')
            if not path.exists():continue
            d=json.loads(path.read_text(encoding='utf-8'))
            for kind,entries in (('position',d['positions']),('rejection',d['rejections']),('cover',d['covers'])):
                for p in entries:
                    row={k:p.get(k) for k in fields};row.update(scenario_id=c['id'],record_type=kind,payload_json=json.dumps(p))
                    row['score']=p.get('score',{}).get('score');writer.writerow(row)
            previous=result['spec']['initial_equity']
            for p in d['equity']:
                row={k:p.get(k) for k in daily_fields};row.update(scenario_id=c['id'],daily_pnl=p['equity']-previous)
                daily_writer.writerow(row);previous=p['equity']
    for name in ('rerun_ledgers.csv','rerun_daily.csv'):shutil.copy2(cfg.reports_dir/name,cfg.public_dir/name)
    # SSI handoff contains scenario accounting, not actual accepted/live positions.
    handoff={'schema_version':'rerun_portfolio_handoff.v1','strategy_id':'reverse_split_impairment','usage':'hypothetical scenario series; not live holdings',
             'cash_flow_assumption':'No deposits/withdrawals; zero cash yield','live_owner_reconciliation':'pending','scenarios':[]}
    for c in cases:
        path=root/'scenarios'/(c['id']+'.json')
        if path.exists():
            detail=json.loads(path.read_text(encoding='utf-8'));daily=[];previous=result['spec']['initial_equity']
            for e in detail['equity']:
                daily.append({**e,'daily_pnl':e['equity']-previous});previous=e['equity']
            handoff['scenarios'].append({'scenario_id':c['id'],'assumptions':c,'daily':daily})
    write_json(cfg.public_dir/'rerun_ssi_handoff.json',handoff)
    write_json(root/'completion.json',{'status':result['execution_status'],'scenarios':len(cases),
               'case_statuses':dict(Counter(c['status'] for c in cases)),'integrity':result['integrity'],
               'published_at':result['built_at'],'input_cutoff':result['calendar']['last'],
               'report':'data/reports/fundamental_rerun_report.md'})
