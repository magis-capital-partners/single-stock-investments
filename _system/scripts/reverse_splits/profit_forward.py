# Immutable research policies and prospective estimate/abstention registration.
from __future__ import annotations
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .profit_data import read,write,fingerprint
from .profit_evidence import load,import_file
ROOT=Path(__file__).resolve().parents[3];NY=ZoneInfo('America/New_York')

def freeze(work,*,now=None):
 now=now or datetime.now(timezone.utc);path=Path(work)/'forward_policies.json'
 policies=[]
 for name,signal in [('Post-split five-session research','split'),('Verified financing supply with cash pressure','financing_both')]:
  policy={'version':'short_forward.v1','name':name,'signal':signal,'target_ceiling':25000,'horizon_sessions':5,'case':'base','sizing':'fixed','exit_policy':'time','entry':'First regular-session open after bound public timestamp + five minutes; split baseline also waits until the session after the effective action.','entry_participation':.05,'cover_participation':.05,'borrow_apr_assumption':.5,'execution_roundtrip_25k':.0595,'observations':'Fresh public borrow indications inform research only, never approve a loan.','source_gate':'Bound issuer, accession and publication clock. Financing requires reconciled registered issued-common supply and cash pressure; completed split requires verified action.','risk':'One position per issuer; +200% stress loss reserve <=2% of hypothetical $10m NAV; margin headroom 20%; no live capital authority.','training_snapshot':'591bf8b55d7902e65853c432','parameter_selection':'Chosen after exploratory historical comparisons. Future observations cannot change this version.','mode':'paper_research_only','promotion':'New version required for any rule change; execution calibration and independent forward evidence required before production.'}
  policies.append({'policy':policy,'sha256':fingerprint(policy)})
 if path.exists():
  existing=read(path)
  if any(fingerprint(p['policy'])!=p['sha256'] for p in existing['policies']) or [p['sha256'] for p in existing['policies']]!=[p['sha256'] for p in policies]:raise ValueError('Frozen forward policy changed; use a new version')
  return existing
 doc={'schema_version':'short_forward_policies.v1','frozen_at':now.isoformat(),'policies':policies,'new_paid_downloads_usd':0,'broker_authority':'none'};write(path,doc);return doc

def entry_clock(event,*,now=None):
 import exchange_calendars as xc
 at=datetime.fromisoformat(event['known_at'])+timedelta(minutes=5)
 if event['family']=='split':at=max(at,datetime.fromisoformat(event['event_date']).replace(tzinfo=NY)+timedelta(days=1))
 day=at.astimezone(NY).date();cal=xc.get_calendar('XNYS',start=str(day-timedelta(days=5)),end=str(day+timedelta(days=45)))
 for session in cal.sessions:
  opening=cal.session_open(session).to_pydatetime()
  if opening>=at:return opening
 raise ValueError('No upcoming exchange session')

def register(work,*,now=None):
 now=now or datetime.now(timezone.utc);frozen=freeze(work,now=now);records=[];missed=[]
 events=read(Path(work)/'effective_events.local.json');chain=load(work)
 existing={(r['record']['event_id'],r['record']['policy_sha256']) for r in chain if r['record']['kind']=='forecast'}
 for item in frozen['policies']:
  p=item['policy']
  for e in events:
   if (p['signal']=='split')!=(e['family']=='split') or e['family'] not in {'split','financing'}:continue
   if not e.get('known_at') or datetime.fromisoformat(e['known_at'])>now:continue
   if (e['id'],item['sha256']) in existing:continue
   if e['event_date']<frozen['frozen_at'][:10]:continue
   entry=entry_clock(e)
   if entry<=now:
    missed.append({'event_id':e['id'],'policy_sha256':item['sha256'],'reason':'Entry clock already passed before registration; no retrospective forecast created.'});continue
   # Until live inputs and cost calibration exist, freeze the missing-evidence decision explicitly.
   reasons=[]
   if not e.get('source_review'):reasons.append('Primary source not reviewed')
   if p['signal']=='financing_both' and not e.get('features',{}).get('terms_verified'):reasons.append('Saleable common supply unreconciled')
   if p['signal']=='financing_both' and e.get('financials',{}).get('cash_pressure') is not True:reasons.append('Cash-pressure evidence missing or absent')
   reasons.append('Contemporaneous executable entry/cover costs and approved borrow unverified')
   record={'kind':'forecast','event_id':e['id'],'known_at':now.isoformat(),'entry_at':entry.isoformat(),'source_url':e['source_url'],'locator':e['source_locator'],'status':'abstain','reason':'; '.join(reasons),'policy_snapshot':p,'policy_sha256':item['sha256'],'input_snapshot':e,'input_sha256':fingerprint(e),'paper_only':True}
   records.append(record)
 if records:
  path=Path(work)/'forward_import.json';write(path,records);import_file(path,work,now=now)
 write(Path(work)/'forward_registration_receipt.json',{'as_of':now.isoformat(),'frozen_policies':len(frozen['policies']),'new_abstentions':len(records),'missed_entry_clocks':missed,'no_fills_or_returns_invented':True})
 return {'frozen_policies':len(frozen['policies']),'new_abstentions':len(records),'missed':len(missed)}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['freeze','register']);p.add_argument('--work',type=Path,required=True);a=p.parse_args();print(json.dumps(freeze(a.work) if a.command=='freeze' else register(a.work)))
if __name__=='__main__':main()
