"""Bounded $0 SEC financial backfill and prospective disclosure monitoring."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path
from .config import load_config
from .free_evidence import FreeClient
from .profit_data import read, write, materialize_events, digest, key, sec_filing_url
ROOT=Path(__file__).resolve().parents[3]

def split_candidates(root,since,now):
    """Source leads only, excluding subsequent prices, returns and outcome labels."""
    path=Path(root)/'_system/data/reverse_splits/events.jsonl';events=[]
    if not path.exists():return events
    for line in path.read_text(encoding='utf-8').splitlines():
        r=json.loads(line);day=r.get('announced_ex_date') or r.get('ex_date');at=r.get('accept_time');accession=r.get('accession')
        if not day or day<since or not at or datetime.fromisoformat(at.replace('Z','+00:00'))>now or not accession:continue
        try:url=sec_filing_url(r['cik'],accession)
        except (ValueError,KeyError):continue
        events.append({'id':key('split',r['cik'],day),'issuer':'cik/'+str(int(r['cik'])),'cik':str(int(r['cik'])),'ticker':r.get('ticker',''),'family':'split','event_date':day,'known_at':at,'source_url':url,'source_locator':'SSI public split ledger; primary action/clock needs review','event_status':'discovered_action_unverified','source_dataset':'public_split_ledger','features':{'split_from':r.get('split_from'),'split_to':r.get('split_to')},'identity_status':'unverified','review_status':'awaiting_primary_review'})
    return events

def facts(root,work,maximum=100):
    directory=Path(root)/'_system/data/reverse_splits/local/raw/companyfacts'
    ciks={str(int(e['cik'])) for e in read(work/'effective_events.local.json')}
    pending=sorted([c for c in ciks if not (directory/f'CIK{int(c):010d}.json').exists()],key=lambda c:hashlib.sha256(c.encode()).hexdigest())
    client=FreeClient(work/'facts_cache',load_config().section('edgar')['user_agent'],maximum=maximum)
    added=[];unavailable=[]
    for cik in pending:
        if client.requests>=maximum or client.blocked:break
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json';raw=client.get(url)
        if raw is None:unavailable.append(cik);continue
        doc=json.loads(raw)
        if str(int(doc.get('cik',-1)))!=cik or not isinstance(doc.get('facts'),dict):raise ValueError('Companyfacts issuer/schema mismatch')
        directory.mkdir(parents=True,exist_ok=True);path=directory/f'CIK{int(cik):010d}.json';path.write_bytes(raw)
        added.append({'cik':cik,'source_url':url,'source_sha256':digest(path)})
    receipt={'as_of':datetime.now(timezone.utc).isoformat(),'requested':client.requests,'added':added,'unavailable':unavailable,'missing_before':len(pending),'missing_after':len(pending)-len(added),'new_paid_downloads_usd':0,'method':'As-filed observations are filtered again at each event public clock. Missing XBRL is unknown; foreign/custom-tag data need separate source review.'}
    write(work/'financial_backfill_receipt.json',receipt);return {k:receipt[k] for k in ['requested','missing_before','missing_after','new_paid_downloads_usd']}

def monitor(root,maximum=80):
    from .profit_discovery import expand
    from .profit_forward import register
    from .profit_evidence import load, status
    public=Path(root)/'_system/data/reverse_splits/profit_forward';work=Path(root)/'_system/data/reverse_splits/local/profit_forward_monitor';work.mkdir(parents=True,exist_ok=True)
    if not (public/'forward_policies.json').exists():raise ValueError('Publish the frozen policies before starting monitoring')
    for name in ['forward_policies.json','discovery_progress.local.json','public_discovery.local.json','evidence.local.jsonl']:
        if (public/name).exists():shutil.copyfile(public/name,work/name)
    policies=read(work/'forward_policies.json');since=policies['frozen_at'][:10]
    write(work/'events.local.json',split_candidates(root,since,datetime.now(timezone.utc)))
    discovery=expand(root,work,since=since,maximum=maximum)
    materialize_events(work,root)
    result=register(work)
    if any(r['record'].get('kind')!='forecast' or r['record'].get('paper_only') is not True for r in load(work)):
        raise ValueError('Public monitoring state accepts paper decisions only; keep broker/other evidence in the private research work folder')
    evidence=status(work)
    public.mkdir(parents=True,exist_ok=True)
    for name in ['forward_policies.json','discovery_progress.local.json','public_discovery.local.json','evidence.local.jsonl','forward_registration_receipt.json']:
        if (work/name).exists():shutil.copyfile(work/name,public/name)
    write(public/'status.json',{'as_of':datetime.now(timezone.utc).isoformat(),**result,'total_abstentions':evidence['frozen_abstentions'],'total_estimates':evidence['frozen_estimates'],'financing_contexts':len(discovery['records']),'split_candidates':len(read(work/'events.local.json')),'coverage_complete':discovery['coverage_complete'],'remaining_filings':discovery['remaining_filings'],'missing_indexes':len(discovery.get('missing_indexes',[])),'independent_forward_outcomes':0,'mode':'Paper monitoring; unverified inputs create explicit abstentions, never trades or synthetic profits.'})
    target=Path(root)/'dashboard/data/short_forward';target.mkdir(parents=True,exist_ok=True)
    for name in ['forward_policies.json','status.json','forward_registration_receipt.json']:shutil.copyfile(public/name,target/name)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['facts','monitor']);p.add_argument('--source-root',type=Path,default=ROOT);p.add_argument('--work',type=Path);p.add_argument('--max-requests',type=int,default=100);a=p.parse_args()
    if a.command=='facts' and a.work is None:p.error('facts requires --work to identify the versioned research dataset')
    if a.max_requests<1:p.error('--max-requests must be positive')
    result=facts(a.source_root,a.work,a.max_requests) if a.command=='facts' else monitor(a.source_root,a.max_requests)
    print(json.dumps(result))
if __name__=='__main__':main()
