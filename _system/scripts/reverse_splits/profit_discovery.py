# Resumable, full-market SEC index discovery. No split-conditioned issuer filter.
from __future__ import annotations
import argparse,hashlib,json,re
from collections import Counter
from datetime import date,datetime,timezone
from pathlib import Path
from .config import load_config
from .free_evidence import FreeClient,cached_filing,column_rows,filing_time,source_url
from .profit_data import read,write,plain_text,classify_financing
ROOT=Path(__file__).resolve().parents[3]
FORMS={'8-K','6-K','424B4','424B5','S-1','S-3','F-1','F-3'}

def expand(root,work,*,since='2021-01-01',until=None,maximum=250):
 until=until or date.today().isoformat();cfg=load_config();client=FreeClient(work/'discovery_cache',cfg.section('edgar')['user_agent'],maximum=maximum)
 state_path=work/'discovery_progress.local.json';state=read(state_path) if state_path.exists() else {'processed':{},'indexes':{},'failures':[]}
 original=read(work/'public_discovery.local.json') if (work/'public_discovery.local.json').exists() else {'records':[]}
 records={(str(r['cik']),r['accession'].replace('-','')):r for r in original['records']};filings={}
 missing_indexes=[]
 for year in range(int(since[:4]),int(until[:4])+1):
  for quarter in range(1,5):
   if f'{year}-{(quarter-1)*3+1:02d}-01'>until or f'{year}-{quarter*3:02d}-31'<since:continue
   url=f'https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx'
   # The current quarter changes daily; immutable filing caches remain reusable.
   if year==date.today().year and quarter==(date.today().month-1)//3+1:
    current=FreeClient(work/'discovery_cache'/date.today().isoformat(),cfg.section('edgar')['user_agent'],maximum=max(0,maximum-client.requests))
    raw=current.get(url);client.requests+=current.requests
   else:raw=client.get(url)
   if raw is None:
    missing_indexes.append(url);continue
   state['indexes'][url]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
   for line in raw.decode('latin-1').splitlines():
    parts=line.split('|')
    if len(parts)!=5 or not parts[0].isdigit():continue
    cik,name,form,day,path=parts
    if form in FORMS and since<=day<=until:
     filings[path]={'cik':cik,'name':name,'form':form,'filingDate':day,'path':path}
 # Hash order is independent of subsequent returns. Cursor is resumable; no coverage claim until queue exhausted.
 ordered=sorted(filings,key=lambda p:hashlib.sha256(p.encode()).hexdigest());success=0
 for path in ordered:
  if path in state['processed']:continue
  if client.requests>=maximum or client.blocked:break
  f=filings[path];url='https://www.sec.gov/Archives/'+path;raw=client.get(url)
  if raw is None:
   state['failures'].append({'path':path,'status':'source_unavailable'});continue
  a=Path(path).stem;compact=a.replace('-','');p=Path(root)/f'_system/data/reverse_splits/local/raw/edgar/{int(f["cik"]):010d}/{compact}.full.txt';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  header=cached_filing(p,f['cik'])
  if not header or str(header.get('accessionNumber','')).replace('-','')!=compact:
   state['failures'].append({'path':path,'status':'unbound_submission_header'});continue
  text=plain_text(raw.decode('utf-8',errors='replace'));parsed=classify_financing(text,f['filingDate'])
  state['processed'][path]={'source_sha256':hashlib.sha256(raw).hexdigest(),'financing_context':bool(parsed)};success+=1
  if parsed:
   symbol=re.search(r'name\s*=\s*["\']dei:TradingSymbol["\'][^>]*>([^<]+)',raw.decode('utf-8',errors='replace'),re.I)
   ticker=symbol[1].strip().upper() if symbol else ''
   known=header['known_at'] if header else filing_time(f)
   records[(str(int(f['cik'])),compact)]={'cik':str(int(f['cik'])),'accession':a,'known_at':known,'ticker':ticker,'name':f['name'],'source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'form':f['form'],'classification':parsed,'captured_at':datetime.now(timezone.utc).isoformat(),'discovery_basis':'SEC_full_market_quarterly_index_hash_order_not_split_conditioned','clock_basis':'bound_SEC_acceptance' if header else 'conservative_filing_date_fallback'}
  if success%20==0:write(state_path,state)
 remaining=sum(p not in state['processed'] for p in filings)
 state.update(since=since,until=until,indexed_filings=len(filings),remaining_filings=remaining,last_requests=client.requests,last_run=datetime.now(timezone.utc).isoformat(),scope='Full-market SEC quarterly filing indexes; bounded source downloads, resumable cursor.');write(state_path,state)
 result={'records':list(records.values()),'requests':client.requests,'coverage_complete':remaining==0 and bool(filings) and not missing_indexes,'new_paid_downloads_usd':0,'since':since,'scope':state['scope'],'failures':state['failures'][-100:],'indexed_filings':len(filings),'processed_filings':sum(p in state['processed'] for p in filings),'remaining_filings':remaining,'missing_indexes':missing_indexes,'index_sources':state['indexes']};write(work/'public_discovery.local.json',result)
 print(json.dumps({k:result[k] for k in ['requests','coverage_complete','indexed_filings','processed_filings','remaining_filings']}),flush=True);print('Unique financing contexts',len(records),flush=True)
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,default=ROOT);p.add_argument('--work',type=Path);p.add_argument('--since',default='2021-01-01');p.add_argument('--until');p.add_argument('--max-requests',type=int,default=250);a=p.parse_args();expand(a.source_root,a.work or a.source_root/'_system/data/reverse_splits/local/profit_program/20261022_v1',since=a.since,until=a.until,maximum=a.max_requests)
if __name__=='__main__':main()
