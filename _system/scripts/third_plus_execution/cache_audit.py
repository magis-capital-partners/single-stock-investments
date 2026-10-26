"""Audit existing local execution caches. No API, downloads, paid data or holdout access."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import numpy as np

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def audit(source, project, output):
    study = project/'_system/data/reverse_splits/third_plus_signal_study'
    old = read(study/'fundamental_filters_v3/decision_audit.json')
    requested = read(study/'requested_sizing_v1/summary.json')
    states = requested['models']['requested_100k']['dilution']['audit']['statuses']
    local = source/'_system/data/reverse_splits/local'
    pfile = local/'patient_execution/20261020_v1/prepared.local.json'
    qfile = local/'execution_research/20261013T224003582762Z__quotes_v1/targets.local.json'
    prepared = read(pfile)['rows']
    quotes = read(qfile)
    bykey = {(r['ticker'], r['date']): r for r in prepared}
    qkeys = {(r['ticker'], r['date']) for r in quotes}
    rows, private, sources, capacity = [], [], {}, []
    for i, event in enumerate(old['events']):
        key = (event['ticker'], event['entry_day'])
        r = bykey.get(key)
        row = dict(id=event['id'], ticker=event['ticker'], event_date=event['event_date'],
                   entry_day=event['entry_day'], issuer=event['issuer'],
                   selected=not states[i].startswith('signal_'),
                   original_ssr_skip=states[i]=='ssr_rejected',
                   legacy_quote_index=key in qkeys, patient_index=r is not None,
                   prepared_file=False, sampled_30m='missing', sampled_60m='missing',
                   nbbo_certified=False, event_trades=False, queue_book=False,
                   borrow_history=False, route_verified=False)
        if r and r.get('prepared'):
            p = Path(r['prepared'])
            # Absolute cached paths are accepted only within the declared local cache.
            try:
                rel = p.resolve().relative_to(local.resolve())
            except ValueError as e:
                raise ValueError('Prepared file outside declared cache') from e
            if any(x.lower() in ('holdout', 'sealed') for x in rel.parts):
                raise ValueError('Sealed cache forbidden')
            if p.is_file():
                sources[str(rel).replace('\\','/')] = sha(p)
                row['prepared_file'] = True
                opened = int(datetime.fromisoformat(r['opened']).timestamp())
                with np.load(p, allow_pickle=False) as a:
                    required = {'ts', 'bid', 'ask', 'valid', 'volume'}
                    if not required.issubset(a.files):
                        raise ValueError('Malformed prepared cache')
                    if len(a['ts'])>1 and not np.all(np.diff(a['ts'])>0):
                        raise ValueError('Nonmonotonic prepared cache')
                    for minutes in (30,60):
                        # Match the proposed 09:31 + declared window, not 09:30 + window.
                        mask = (a['ts']>=opened+60)&(a['ts']<opened+60+minutes*60)
                        valid = mask&a['valid']&np.isfinite(a['bid'])&np.isfinite(a['ask'])&(a['bid']>0)&(a['ask']>=a['bid'])
                        count = int(valid.sum())
                        row[f'sampled_{minutes}m'] = 'complete_sample_grid' if count==minutes*60 else 'partial' if count else 'missing'
                        # This is observed venue-flow budgeting only; no legal price/queue fill claim.
                        at = np.flatnonzero(valid)
                        if len(at):
                            first = int(at[0])
                            mark = float((a['bid'][first]+a['ask'][first])/2)
                            volume = float(a['volume'][valid].sum())
                            if not np.isfinite(volume) or volume<0:
                                raise ValueError('Invalid recorded venue flow')
                            for rate in (.05,.10):
                                dollars = min(100000, int(rate*volume)*mark)
                                capacity.append(dict(id=event['id'], selected=row['selected'],
                                  restricted=row['original_ssr_skip'], minutes=minutes,
                                  rate=rate, usd=dollars))
                    private.append(dict(id=event['id'],file=str(p),sha256=sources[str(rel).replace('\\','/')]))
        rows.append(row)
    aggregates=[]
    for group in ('all_matched','selected','original_ssr_skips'):
        for minutes in (30,60):
            for rate in (.05,.10):
                values=[r['usd'] for r in capacity if r['minutes']==minutes and r['rate']==rate
                        and (group=='all_matched' or r['selected'] if group=='selected' else r['restricted'] if group=='original_ssr_skips' else True)]
                aggregates.append(dict(group=group,minutes=minutes,participation=rate,n=len(values),
                    mean_flow_budget_usd=float(np.mean(values)) if values else None,
                    median_flow_budget_usd=float(np.median(values)) if values else None,
                    p90_flow_budget_usd=float(np.quantile(values,.9)) if values else None,
                    parents_with_100k_flow_budget=sum(v>=100000 for v in values)))
    groups={}
    for name, rs in [('population', rows),('selected',[r for r in rows if r['selected']]),
                     ('original_ssr_skips',[r for r in rows if r['original_ssr_skip']])]:
        groups[name]=dict(events=len(rs),scheduled=sum(bool(r['entry_day']) for r in rs),
           quote_index=sum(r['legacy_quote_index'] for r in rs),patient_index=sum(r['patient_index'] for r in rs),
           prepared_files=sum(r['prepared_file'] for r in rs),
           complete_sampled_30m=sum(r['sampled_30m']=='complete_sample_grid' for r in rs),
           complete_sampled_60m=sum(r['sampled_60m']=='complete_sample_grid' for r in rs),
           certified_entry_replays=0,borrow_verified=0)
    raw = local/'raw/databento'
    schema_inventory = []
    for dataset in sorted(raw.iterdir()):
        if dataset.is_dir() and not any(x in dataset.name.lower() for x in ('holdout', 'sealed')):
            schemas = sorted(p.name for p in dataset.iterdir() if p.is_dir())
            headers = set()
            if dataset.name == 'profit_expansion':
                for csv in dataset.glob('*.csv'):
                    with csv.open(encoding='utf-8-sig') as stream:
                        headers.add(stream.readline().strip())
            schema_inventory.append(dict(dataset=dataset.name,directory_schemas=schemas,flat_csv_headers=sorted(headers)))
    result=dict(schema='third_plus_execution_cache_audit.v1',groups=groups,events=rows,raw_schema_metadata=schema_inventory,
        flow_budget_diagnostics=aggregates,
        sources=dict(cohort=sha(study/'fundamental_filters_v3/decision_audit.json'),
          requested=sha(study/'requested_sizing_v1/summary.json'),prepared_index=sha(pfile),
          quote_index=sha(qfile),auditor=sha(Path(__file__)),
          prepared_files_digest=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()),
        limitations=['The two named reuse indexes and matched prepared files were audited. The raw Databento cache schema directories and flat expansion CSV headers were also inspected; this is not an event-by-event reconstruction of all raw files.',
          'Sampled venue quotes are not certified consolidated NBBO. One-second OHLC volume does not identify aggressor, price-level queue or eligible fills.',
          'Flow-budget dollars are aggregate bounds on recorded venue flow, not estimated fills or obtainable position sizes. No performance is inferred.',
          'No archived usable borrow approval, native route confirmation or complete exact-cohort entry-and-exit replay is established by these caches.',
          'Prepared arrays were hash-inventoried; this audit does not independently revalidate every upstream raw record.'],
        broker_connections=0,new_market_data_usd=0,holdout_files_opened=0)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    private_output=local/'third_plus_signal_study/ssr_execution_v1/cache_sources.local.json'
    private_output.parent.mkdir(parents=True,exist_ok=True)
    private_output.write_text(json.dumps(dict(files=private,source_hashes=sources),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(groups,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    audit(a.source_root.resolve(),a.project_root.resolve(),a.output.resolve())
