# Source-only review packets and public evidence operations for the short strategy lab.
from __future__ import annotations
import argparse,hashlib,json,re,sqlite3
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from .profit_data import plain_text,read,write,digest,RUN,NY
from .free_evidence import FreeClient,cached_filing,column_rows,filing_time,source_url
ROOT=Path(__file__).resolve().parents[3]
def compact_accession(e):
 a=e.get('accession') or ''
 if not a:
  m=re.search(r'/([0-9]{18})/',e.get('source_url',''));a=m[1] if m else ''
 return a.replace('-','')
def dash_accession(a):return a[:10]+'-'+a[10:12]+'-'+a[12:] if len(a)==18 else a

def source_document(e,root,client,*,download=True):
 a=compact_accession(e);cik=int(e['cik']);base=Path(root)/'_system/data/reverse_splits/local'
 candidates=[base/f'raw/edgar/{cik:010d}/{a}.full.txt',base/f'expansion/expansion_v2/text/{cik:010d}/{a}.txt']
 fallback=None
 for p in candidates:
  if p.exists():
   raw=p.read_bytes();text=raw.decode('utf-8',errors='replace');header=cached_filing(p,cik)
   # A partial cached report remains useful context; only a bound header establishes its own clock.
   fallback={'raw':raw,'text':plain_text(text),'source_url':e['source_url'],'source_sha256':digest(p),'header':{k:v for k,v in (header or {}).items() if k not in {'text','path'}},'cache_basis':'bound_SEC_header' if header else 'issuer_accession_cache_context'}
   if header:return fallback
 if not download:return fallback
 url=source_url(cik,dash_accession(a)) if a else e['source_url'];raw=client.get(url)
 if raw is None:return fallback
 p=base/f'raw/edgar/{cik:010d}/{a}.full.txt'
 if a:
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 header=cached_filing(p,cik) if a else None
 return {'raw':raw,'text':plain_text(raw.decode('utf-8',errors='replace')),'source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'header':{k:v for k,v in (header or {}).items() if k not in {'text','path'}},'cache_basis':'bound_SEC_header' if header else 'downloaded_primary_context'}

def clauses(text,family):
 patterns={'financing':r'Item\s+[138]\.0[123]|registered direct|gross proceeds|net proceeds|[\d,]+\s+shares of common|outstanding|resale|exercis|purchase price|terminat',
 'deficiency':r'Item\s+3\.01|Nasdaq|NYSE|deficien|minimum bid|stockholders.{0,10}equity|market value|compliance|notification',
 'split':r'reverse.{0,10}split|one.for|1.for|effective|CUSIP|outstanding'}
 spans=[]
 for m in re.finditer(patterns[family],text,re.I):
  lo=max(0,m.start()-180);hi=min(len(text),m.end()+540)
  if spans and lo<=spans[-1][1]:spans[-1]=(spans[-1][0],min(max(hi,spans[-1][1]),spans[-1][0]+2600))
  else:spans.append((lo,hi))
  if len(spans)>=12:break
 return [{'locator':f'normalized_text[{a}:{b}]','excerpt':text[a:b]} for a,b in spans]

def prepare(root,work,maximum=150):
 from .config import load_config
 client=FreeClient(work/'operations_public_cache',load_config().section('edgar')['user_agent'],maximum=maximum)
 events={e['id']:e for e in read(work/'effective_events.local.json')};queue=read(work/'review_queue.json');packets=[]
 for q in queue:
  e=events[q['event_id']];doc=source_document(e,root,client)
  packet={k:e.get(k) for k in ['id','cik','ticker','family','event_date','known_at','clock_basis','source_url','accession','event_status','features']}
  packet['features']={k:v for k,v in (packet.get('features') or {}).items() if k not in {'prior_financing_flag'}}
  packet['source_available']=bool(doc)
  if doc:
   packet.update({k:doc[k] for k in ['source_url','source_sha256','header','cache_basis']});packet['clauses']=clauses(doc['text'],e['family'])
   write(work/'review_sources'/f"{hashlib.sha256(e['id'].encode()).hexdigest()}.json",{**packet,'normalized_text':doc['text']})
  else:packet['clauses']=[]
  packets.append(packet)
 write(work/'review_packets.local.json',{'prepared_at':datetime.now(timezone.utc).isoformat(),'outcomes_included':False,'records':packets,'requests':client.requests,'blocked_hosts':sorted(client.blocked)})
 print(json.dumps({'packets':len(packets),'sources_available':sum(p['source_available'] for p in packets),'requests':client.requests,'families':dict(Counter(p['family'] for p in packets))}))

def audit_liabilities(root,work,maximum=150):
 from .config import load_config
 client=FreeClient(work/'operations_public_cache',load_config().section('edgar')['user_agent'],maximum=maximum)
 events={e['id']:e for e in read(work/'effective_events.local.json')};positions={};models={}
 for p in sorted((work/'replays').glob('*__h5__*__base__fixed__time.local.json')):
  for t in read(p)['trades']:
   if t['units']<=1e-8:continue
   models.setdefault(t['id'],[]).append(p.stem.replace('.local',''))
   if t['id'] not in positions or t['entry_notional']>positions[t['id']]['entry_notional']:positions[t['id']]=t
 rows=[]
 for identity,t in positions.items():
  e=events[identity];doc=source_document(e,root,client);header=doc['header'] if doc else {}
  rows.append({'event_id':identity,'ticker':t['ticker'],'cik':e['cik'],'entry_day':t['entry_day'],'planned_exit_day':t['planned_exit_day'],'last_mark_day':t['last_mark_day'],'units_in_entry_basis':t['units'],'split_price_factor':t['factor'],'marked_liability':t['units']/t['factor']*t['last_nominal'],'modeled_borrow':t['borrow'],'identity_unresolved':t['identity_unresolved'],'action_unresolved':t['action_unresolved'],'source_url':doc['source_url'] if doc else e['source_url'],'source_sha256':doc['source_sha256'] if doc else None,'primary_header_bound':bool(header),'related_models':models[identity],'resolution_status':'primary_identity_checked_loan_end_unverified' if header else 'primary_source_or_security_continuity_missing','loan_termination_verified':False,'obligation_retained':True})
 rows.sort(key=lambda r:(-r['marked_liability'],r['event_id']));write(work/'liability_audit.local.json',{'schema_version':'short_liability_audit.v1','as_of':datetime.now(timezone.utc).isoformat(),'scope':'Five-session base fixed models, both target sizes; deduplicated event obligations. Amounts use the largest modeled position, not a combined portfolio.','rows':rows,'requests':client.requests})
 print(json.dumps({'unique_obligations':len(rows),'bound_primary_headers':sum(r['primary_header_bound'] for r in rows),'verified_loan_terminations':0,'requests':client.requests}))

def supporting_terms(root,work,maximum=150):
 from .config import load_config
 from datetime import timedelta
 client=FreeClient(work/'operations_public_cache',load_config().section('edgar')['user_agent'],maximum=maximum)
 packets=read(work/'review_packets.local.json')['records'];documents=[]
 for e in packets:
  if e['ticker'] not in {'XXII','PAVS','ENGN','TTNP','SONN','VTLE'} or e['family']!='financing':continue
  raw=client.get(f'https://data.sec.gov/submissions/CIK{int(e["cik"]):010d}.json')
  if raw is None:continue
  sub=json.loads(raw);filings=column_rows(sub)
  lo=(datetime.fromisoformat(e['event_date'])-timedelta(days=10)).date().isoformat();hi=e['event_date']
  for shard in sub.get('filings',{}).get('files',[]):
   if shard.get('filingFrom','9999')<=hi and shard.get('filingTo','0000')>=lo:
    data=client.get('https://data.sec.gov/submissions/'+shard['name'])
    if data is not None:filings+=column_rows(json.loads(data))
  for f in filings:
   if f.get('form') not in {'424B4','424B5'} or not lo<=f.get('filingDate','')<=hi:continue
   at=filing_time(f)
   if at and e.get('header',{}).get('known_at') and datetime.fromisoformat(at)>datetime.fromisoformat(e['header']['known_at']):continue
   url=source_url(e['cik'],f['accessionNumber'],f.get('primaryDocument',''));raw=client.get(url)
   if raw is None:continue
   text=plain_text(raw.decode('utf-8',errors='replace'))
   doc={'event_id':e['id'],'ticker':e['ticker'],'source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'known_at':at,'text':text,'accession':f['accessionNumber']}
   documents.append(doc)
 write(work/'supporting_terms.local.json',{'documents':documents,'requests':client.requests})
 print(json.dumps({'supporting_prospectuses':len(documents),'requests':client.requests}))

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['prepare-reviews','audit-liabilities','supporting-terms']);ap.add_argument('--source-root',type=Path,default=ROOT);ap.add_argument('--work',type=Path);ap.add_argument('--max-requests',type=int,default=150);a=ap.parse_args(argv)
 work=a.work or a.source_root/'_system/data/reverse_splits/local/profit_program/20261022_v1'
 {'prepare-reviews':prepare,'audit-liabilities':audit_liabilities,'supporting-terms':supporting_terms}[a.command](a.source_root,work,a.max_requests)
if __name__=='__main__':main()
