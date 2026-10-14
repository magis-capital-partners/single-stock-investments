"""Current public IBKR rate sensitivities; never historical locate evidence."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import math
import shutil
import statistics

from .expansion import digest
from .expansion_imports import evidence
from .ledger import load_jsonl, read_json
from .rerun import eligible_score
from .execute import session_open
from .strategy_research import summarize


def freeze_current_rates(cfg, root, observed, post):
    meta = read_json(cfg.ledger_dir / 'borrow_history/latest.json', {})
    path = cfg.ledger_dir / meta.get('path', 'missing')
    if not path.is_file():
        return {}, {'status': 'current_quotes_unavailable', 'populations': []}, []
    frozen = root / 'current_borrow.jsonl'
    shutil.copy2(path, frozen)
    rows = load_jsonl(frozen)
    quotes = {r['ticker']: r for r in rows}
    primary_names = {e['ticker'] for e in observed if e['verification'] in {'primary_schedule_matched','structured_corporate_action'} and any(o['cohort']=='ex_plus_1_h1' and o['status']=='observed_price_path' for o in e['outcomes'])}
    fund_names = {l['ticker'] for l in post if eligible_score(l['fundamental'],60)}
    populations = []
    for name, tickers in [('archived_universe', set(quotes)), ('one_day_verified_names', primary_names), ('fundamental_60_names', fund_names)]:
        rates = sorted(quotes[t]['fee_annual_fraction'] for t in tickers if t in quotes and quotes[t]['available_shares']>0 and quotes[t]['fee_annual_fraction'] is not None and math.isfinite(quotes[t]['fee_annual_fraction']))
        populations.append({'population': name, 'target_names': len(tickers), 'quoted_available_names': len(rates), 'missing_names':len(tickers)-len(rates),
                            'mean_annual_fraction':statistics.mean(rates) if rates else None, 'median_annual_fraction':statistics.median(rates) if rates else None,
                            'p75_annual_fraction':rates[min(len(rates)-1,int(len(rates)*.75))] if rates else None, 'p90_annual_fraction':rates[min(len(rates)-1,int(len(rates)*.90))] if rates else None})
    relevant = next(p for p in populations if p['population']=='one_day_verified_names')
    cap_paths=[]
    cap_gaps=Counter()
    for event in observed:
        if event['verification'] not in {'primary_schedule_matched','structured_corporate_action'}:
            continue
        outcome=next(o for o in event['outcomes'] if o['cohort']=='ex_plus_1_h1')
        if outcome['status']!='observed_price_path':
            continue
        quote=quotes.get(event['ticker'])
        if not quote or quote['available_shares']<=0 or quote['fee_annual_fraction'] is None:
            cap_gaps['current_quote_or_quantity_unavailable']+=1
        elif quote['fee_annual_fraction']>.5:
            cap_gaps['current_rate_above_50pct']+=1
        else:
            cap_paths.append({'issuer':event['issuer'],'year':event['ex_date'][:4],'net_return':outcome['gross_short_return']})
    cases=[]
    for selector in ('event_only','fundamental_60'):
        for stat in ('median','mean','p90'):
            rate = relevant[stat+'_annual_fraction']
            if rate is not None:
                cases.append({'id':f'post_split_{selector}_h1_current_{stat}', 'selector':selector, 'horizon_sessions':1, 'fee_annual':rate, 'execution':'base', 'stage':'post_split_1', 'rate_basis':f'flat current one-day-universe {stat}; not historical fee'})
        cases.append({'id':f'post_split_{selector}_h1_current_cap50', 'selector':selector, 'horizon_sessions':1, 'fee_annual':relevant['mean_annual_fraction'] or 1.0, 'execution':'one_day_budget','account':'conservative', 'stage':'post_split_1','current_rate_cap':.5, 'rate_basis':'per-name current indication <=50%; retrospective illustration, no historical approval'})
    return quotes, {'as_of':meta['as_of'], 'source_url':'ftp://ftp2.interactivebrokers.com/usa.txt', 'file_sha256':digest(frozen), 'populations':populations,
                     'current_cap50_gross':summarize(cap_paths),'current_cap50_exclusions':dict(cap_gaps),
                     'assumption':'Equal weight per currently quoted available name. Current symbol matching is not a historical security master. Missing rates are not zero. Flat-rate sensitivities apply current population rates across history; the cap illustration additionally filters on current inventory/rates and is not a tradable historical backtest.'}, cases


def attach_post_evidence(conn, post, events, calendar):
    import exchange_calendars as xc
    from zoneinfo import ZoneInfo
    cal=xc.get_calendar('XNYS', start=calendar[0], end=calendar[-1])
    quotes=evidence(conn,'quote')
    margins=evidence(conn,'margin')
    theses=evidence(conn,'thesis')
    eventmap={e['event_id']: e for e in events}
    for lead in post:
        sec=lead.get('dated_security')
        if not sec:
            continue
        for q in quotes:
            if q['security_id']!=sec['security_id'] or q['ticker']!=lead['ticker']:
                continue
            at=datetime.fromisoformat(q['timestamp'])
            day=at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            if day not in lead['rows'] or day not in calendar:
                continue
            boundary=session_open(day) if q['session_point']=='open' else cal.session_close(day).to_pydatetime()
            if 0<=(boundary-at).total_seconds()<=60:
                lead['rows'][day]['quote_'+q['session_point']]=q
        matching=[m for m in margins if m['security_id']==sec['security_id'] and m['ticker']==lead['ticker'] and datetime.fromisoformat(m['timestamp'])<=session_open(lead['entry_date'])]
        lead['dated_margin']=max(matching,key=lambda m:m['timestamp']) if matching else None
        accession=eventmap[lead['id']].get('accession')
        matching=[t for t in theses if accession and t['accession'].replace('-','')==accession.replace('-','') and datetime.fromisoformat(t['available_at'])<=session_open(lead['entry_date'])]
        lead['dated_thesis']=max(matching,key=lambda t:t['available_at']) if matching else None
