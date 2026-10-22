"""Immutable local evidence, forward forecasts and execution calibration.

Imports files only. Does not connect to a broker, place orders or fabricate fills.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import math

from .profit_data import distribution, fingerprint, read, write

KINDS={'terms','borrow','recall','quote','fill','cashflow','forecast','outcome','review'}


def aware(value):
    got=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if got.utcoffset() is None:raise ValueError('Evidence time must include timezone')
    return got


def positive(value,zero=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or (value==0 and not zero):
        raise ValueError('Invalid finite amount')


def validate(record,*,now=None):
    r=dict(record)
    if r.get('kind') not in KINDS:raise ValueError('Unknown evidence kind')
    if not r.get('event_id'):raise ValueError('Missing event identity')
    if not r.get('source_url','').startswith('https://') or not r.get('locator'):raise ValueError('Evidence needs a source URL and locator')
    known=aware(r['known_at']);kind=r['kind'];now=now or datetime.now(timezone.utc)
    if known>now:raise ValueError('Evidence cannot be known in the future')
    if kind=='terms':
        if aware(r['evidence_known_at'])>known:raise ValueError('Terms precede their source evidence')
        for k in ['shares_before','saleable_shares','net_proceeds']:positive(r[k],zero=k!='shares_before')
        if r.get('economic_state') not in {'priced','closed','exercisable','terminated'}:raise ValueError('Terms need an economic state')
        required=['claims_and_cash_reconciled','split_basis_reconciled','saleability_reconciled']
        if not all(r.get(k) is True for k in required):raise ValueError('Incomplete primary terms reconciliation')
        if not r.get('reviewer'):raise ValueError('Missing reviewer')
    if kind=='borrow':
        positive(r['annual_rate'],zero=True);positive(r['shares'],zero=True)
        if r.get('status') not in {'indication','approval','accrual'}:raise ValueError('Unknown borrow evidence status')
        if r['status']=='approval' and (r.get('approved') is not True or not r.get('broker_reference') or r['shares']<=0):raise ValueError('Approval requires positive shares and broker evidence')
    if kind=='recall' and not r.get('broker_reference'):raise ValueError('Recall needs broker evidence')
    if kind=='quote':
        positive(r['bid']);positive(r['ask'])
        if r['ask']<r['bid']:raise ValueError('Crossed quote')
        if aware(r['quote_at'])>known:raise ValueError('Quote precedes evidence availability')
        if r.get('nbbo_verified') is not True:raise ValueError('Calibration quote must be verified NBBO')
    if kind=='fill':
        positive(r['shares']);positive(r['price']);positive(r['commission_usd'],zero=True)
        aware(r['fill_at']);aware(r['arrival_at'])
        if aware(r['fill_at'])<aware(r['arrival_at']):raise ValueError('Fill precedes order arrival')
        if aware(r['fill_at'])>known:raise ValueError('Fill is not yet available')
        if r.get('phase') not in {'entry','cover'}:raise ValueError('Unknown fill phase')
        if r.get('observed') is not True or r.get('compliance_verified') is not True or not r.get('broker_reference'):
            raise ValueError('Fill is not observed, compliant broker evidence')
        if not r.get('policy_sha256'):raise ValueError('Fill is not bound to a policy')
    if kind=='cashflow':
        if aware(r['value_at'])>known:raise ValueError('Cash flow is not yet available')
        if not isinstance(r.get('amount_usd'),(int,float)) or not math.isfinite(r['amount_usd']):raise ValueError('Invalid cash flow')
        if r.get('category') not in {'borrow','credit','dividend','cash_in_lieu','locate','other'}:raise ValueError('Unknown cash-flow category')
    if kind=='forecast':
        entry=aware(r['entry_at'])
        if entry<=now or known>now:raise ValueError('Forward forecast must be frozen before future entry')
        if r.get('status') not in {'estimate','abstain'}:raise ValueError('Forecast needs estimate or abstain')
        if not r.get('policy_sha256') or not r.get('input_sha256'):raise ValueError('Forecast needs frozen policy and inputs')
        for prefix in ['policy','input']:
            snapshot=r.get(prefix+'_snapshot')
            if not isinstance(snapshot,dict) or fingerprint(snapshot)!=r[prefix+'_sha256']:
                raise ValueError('Forecast hash does not match frozen '+prefix+' snapshot')
        if r['input_snapshot'].get('id')!=r['event_id'] or aware(r['input_snapshot']['known_at'])>known:
            raise ValueError('Forecast input identity or clock mismatch')
        from .profit_data import validate_event
        validate_event(r['input_snapshot'])
        if r['status']=='estimate':
            for k in ['expected_gross_return','expected_net_dollars']:
                if not isinstance(r.get(k),(int,float)) or not math.isfinite(r[k]):raise ValueError('Missing forecast estimate')
    if kind=='outcome':
        if not r.get('forecast_sha256'):raise ValueError('Outcome must reference frozen forecast')
        if aware(r['exit_at'])>known:raise ValueError('Outcome is not yet available')
        if not isinstance(r.get('net_dollars'),(int,float)) or not math.isfinite(r['net_dollars']):raise ValueError('Missing outcome dollars')
    if kind=='review':
        if not r.get('reviewer') or r.get('outcome_blinded') is not True:raise ValueError('Review needs identity and outcome blinding')
        for k in ['identity','clock','economic_state','cash_and_shares','saleability']:
            if r.get('checks',{}).get(k) not in {'pass','fail','unresolved'}:raise ValueError('Incomplete review checks')
    return r


def load(work):
    p=Path(work)/'evidence.local.jsonl'
    if not p.exists():return []
    records=[];previous=None
    for line in p.read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        got=fingerprint({k:v for k,v in row.items() if k!='sha256'})
        if got!=row['sha256'] or row['previous_sha256']!=previous:raise ValueError('Evidence chain mismatch')
        previous=row['sha256'];records.append(row)
    return records


def import_file(path,work,*,now=None):
    raw=Path(path).read_text(encoding='utf-8')
    incoming=json.loads(raw) if raw.lstrip().startswith('[') else [json.loads(x) for x in raw.splitlines() if x.strip()]
    # Validate the complete batch before mutating the chain.
    incoming=[validate(r,now=now) for r in incoming]
    existing=load(work);dedup={fingerprint(r['record']) for r in existing}
    forecasts={r['sha256']:r['record'] for r in existing if r['record']['kind']=='forecast'}
    evaluated={r['record']['forecast_sha256']:fingerprint(r['record']) for r in existing if r['record']['kind']=='outcome'}
    for record in incoming:
        if record['kind']=='outcome':
            forecast=forecasts.get(record['forecast_sha256'])
            if not forecast:raise ValueError('Unknown frozen forecast')
            if record['event_id']!=forecast['event_id'] or aware(record['exit_at'])<aware(forecast['entry_at']):
                raise ValueError('Outcome identity or exit clock mismatch')
            if forecast['status']!='estimate':raise ValueError('An abstention has no traded outcome')
            prior=evaluated.get(record['forecast_sha256'])
            if prior and prior!=fingerprint(record):raise ValueError('Cannot replace a frozen forecast outcome')
            evaluated[record['forecast_sha256']]=fingerprint(record)
    previous=existing[-1]['sha256'] if existing else None
    for record in incoming:
        fp=fingerprint(record)
        if fp in dedup:continue
        if record['kind']=='forecast' and any(r['record']['kind']=='forecast' and r['record']['event_id']==record['event_id'] and r['record']['policy_sha256']==record['policy_sha256'] for r in existing):
            raise ValueError('Cannot replace a frozen event/policy forecast')
        row={'record':record,'imported_at':(now or datetime.now(timezone.utc)).isoformat(),'previous_sha256':previous}
        row['sha256']=fingerprint(row);previous=row['sha256'];existing.append(row);dedup.add(fp)
    destination=Path(work)/'evidence.local.jsonl';destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_suffix('.tmp')
    temp.write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n' for r in existing),encoding='utf-8')
    temp.replace(destination)
    return {'records':len(existing),'chain_sha256':previous}


def status(work):
    chain=load(work);records=[r['record'] for r in chain]
    counts=dict(Counter(r['kind'] for r in records))
    forecasts=[r for r in chain if r['record']['kind']=='forecast']
    outcomes=[r['record'] for r in chain if r['record']['kind']=='outcome']
    by_hash={r['sha256']:r['record'] for r in forecasts}
    calibration=[]
    for r in outcomes:
        if r['forecast_sha256'] in by_hash:
            f=by_hash[r['forecast_sha256']]
            calibration.append({'event_id':f['event_id'],'forecast':f.get('expected_net_dollars'),'net_dollars':r['net_dollars']})
    reviews=[r for r in records if r['kind']=='review']
    fills=[r for r in records if r['kind']=='fill']
    quotes=[r for r in records if r['kind']=='quote']
    costs=[]
    for f in fills:
        candidates=[q for q in quotes if q['event_id']==f['event_id'] and aware(q['quote_at'])<=aware(f['arrival_at'])
                    and 0<=(aware(f['arrival_at'])-aware(q['quote_at'])).total_seconds()<=5]
        if not candidates:continue
        q=max(candidates,key=lambda q:aware(q['quote_at']));mid=(q['bid']+q['ask'])/2
        shortfall=(mid-f['price'])/mid if f['phase']=='entry' else (f['price']-mid)/mid
        costs.append({'phase':f['phase'],'notional':f['shares']*f['price'],'implementation_shortfall':shortfall,
                      'commission_usd':f['commission_usd']})
    return {'counts':counts,'chain_sha256':chain[-1]['sha256'] if chain else None,
        'frozen_estimates':sum(r['record']['status']=='estimate' for r in forecasts),
        'frozen_abstentions':sum(r['record']['status']=='abstain' for r in forecasts),
        'evaluated_forecasts':len(calibration),'forward_net_dollars':sum(r['net_dollars'] for r in calibration),
        'source_reviews':len({r['event_id'] for r in reviews}),
        'review_passes':sum(all(x=='pass' for x in r['checks'].values()) for r in reviews),
        'observed_fills':len(fills),'nbbo_matched_fills':len(costs),
        'entry_shortfall':distribution([r['implementation_shortfall'] for r in costs if r['phase']=='entry']),
        'cover_shortfall':distribution([r['implementation_shortfall'] for r in costs if r['phase']=='cover']),
        'measured_cost_status':'observed_sample_requires_size_and_selection_checks' if costs else 'no_observed_execution_calibration',
        'borrow_approvals':sum(r['kind']=='borrow' and r.get('status')=='approval' for r in records)}


def collect_public(work,*,ciks,user_agent,maximum=200,since='2026-10-14'):
    """Bounded SEC-only expansion, separate from the split-phrase research cache."""
    from .free_evidence import FreeClient, column_rows, filing_time, source_url
    from .profit_data import classify_financing, plain_text
    client=FreeClient(Path(work)/'public_cache',user_agent,maximum=maximum)
    records=[];failures=[]
    for cik in ciks:
        try:
            url=f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
            raw=json.loads(client.get(url))
            for f in column_rows(raw):
                if f.get('form') not in {'8-K','6-K','424B4','424B5','S-1','S-3','F-1','F-3'} or f.get('filingDate','')<since:continue
                if client.requests>=maximum:break
                filing_url=source_url(cik,f['accessionNumber'],f.get('primaryDocument',''))
                body=client.get(filing_url)
                parsed=classify_financing(plain_text(body.decode('utf-8',errors='replace')),f.get('filingDate'))
                if parsed:
                    records.append({'cik':str(int(cik)),'accession':f['accessionNumber'],'known_at':filing_time(f),
                        'ticker':(raw.get('tickers') or [''])[0],'name':raw.get('name',''),
                        'source_url':filing_url,'source_sha256':__import__('hashlib').sha256(body).hexdigest(),
                        'form':f['form'],'classification':parsed,'captured_at':datetime.now(timezone.utc).isoformat(),
                        'discovery_basis':'SEC_submissions_not_conditioned_on_split_completion'})
        except Exception as exc:
            failures.append({'cik':str(cik),'error':str(exc)[:240]})
            if client.blocked or client.requests>=maximum:break
    result={'records':records,'failures':failures,'requests':client.requests,'coverage_complete':False,
            'new_paid_downloads_usd':0,'since':since,'scope':'Selected issuer recent SEC submissions, not full market. Older submission shards not searched.'}
    write(Path(work)/'public_discovery.local.json',result)
    return result
