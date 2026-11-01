# Zero-dollar Databento expansion. Raw files remain private; historical input is immutable.
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,sqlite3
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from .profit_data import read,write,fingerprint,digest
from .execution_realism import _load_key
ROOT=Path(__file__).resolve().parents[3]
FEEDS=['XNAS.ITCH','XNYS.PILLAR','XASE.PILLAR']

def daily_observation(row):
 try:
  symbol=row['symbol'].replace('.','-');day=row['ts_event'][:10]
  vals=[float(row[k]) for k in ['open','high','low','close']];vol=float(row['volume'])
 except (ValueError,TypeError,KeyError,AttributeError):return None
 if not symbol or len(day)!=10 or not all(math.isfinite(x) and x>0 for x in vals) or not math.isfinite(vol) or vol<0:return None
 if vals[2]>min(vals[0],vals[3]) or vals[1]<max(vals[0],vals[3]):return None
 return symbol,day,vals,vol

def collect(root,work,*,maximum_symbols=600,through=None):
 through=through or (date.today()-timedelta(days=1)).isoformat();end=(date.fromisoformat(through)+timedelta(days=1)).isoformat()
 events=read(work/'effective_events.local.json');symbols=sorted({e['ticker'] for e in events if e.get('ticker')},key=lambda s:hashlib.sha256(s.encode()).hexdigest())
 state=read(work/'market_data_receipt.local.json') if (work/'market_data_receipt.local.json').exists() else {'requests':[]}
 completed={(r['dataset'],s) for r in state['requests'] if r.get('status')=='downloaded' and r.get('end')==end for s in r['symbols']}
 _load_key();auth=(os.environ["DATABENTO_API_KEY"],"");paths=[];processed=0
 def request_one(feed,batch):
  req={'dataset':feed,'schema':'ohlcv-1d','symbols':[s.replace('-','.') for s in batch],'stype_in':'raw_symbol','start':'2020-10-01','end':end}
  ident=fingerprint(req)[:24];path=Path(root)/f'_system/data/reverse_splits/local/raw/databento/profit_expansion/{ident}.csv'
  rec={'dataset':feed,'symbols':batch,'end':end,'schema':'ohlcv-1d','status':'pending','new_paid_downloads_usd':0}
  try:
   data={**req,'symbols':','.join(req['symbols'])}
   response=requests.post('https://hist.databento.com/v0/metadata.get_cost',data=data,auth=auth,timeout=45);response.raise_for_status();quote=float(response.json());rec['quoted_usd']=quote if math.isfinite(quote) else None
   if not math.isfinite(quote) or quote!=0:
    rec['status']='refused_nonzero_or_invalid_quote'
   else:
    side=path.with_suffix('.ok.json');expected=fingerprint(req)
    cached=path.exists() and side.exists() and read(side).get('request_sha256')==expected and read(side).get('source_sha256')==hashlib.sha256(path.read_bytes()).hexdigest()
    if not cached:
     path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.part')
     with requests.post('https://hist.databento.com/v0/timeseries.get_range',data={**data,'encoding':'csv','compression':'none','pretty_px':'true','pretty_ts':'true','map_symbols':'true'},auth=auth,timeout=90,stream=True) as response:
      response.raise_for_status();size=0
      with temp.open('wb') as out:
       for chunk in response.iter_content(65536):
        size+=len(chunk)
        if size>128*1024*1024:raise ValueError('CSV request exceeded bounded 128 MiB')
        out.write(chunk)
     temp.replace(path);write(side,{'request_sha256':expected,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'quoted_usd':0})
    rec['status']='downloaded';rec['raw_file']=path.name
  except Exception as exc:
   rec.update(status='unavailable',error=type(exc).__name__)
   if isinstance(exc,requests.HTTPError) and exc.response is not None:rec['http_status']=exc.response.status_code
  return rec
 jobs=[]
 for feed in FEEDS:
  pending=[s for s in symbols if (feed,s) not in completed][:maximum_symbols]
  jobs.extend((feed,pending[i:i+200]) for i in range(0,len(pending),200))
 # Two independent requests at a time; each request still has its own exact-$0 gate.
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(request_one,feed,batch) for feed,batch in jobs]
  for future in as_completed(futures):
   rec=future.result()
   if rec['status']=='downloaded':processed+=len(rec['symbols'])
   state['requests'].append(rec);write(work/'market_data_receipt.local.json',state);print(rec['dataset'],rec['status'],len(rec['symbols']),flush=True)
 # Reuse every successful cache, including previous invocations.
 paths=[]
 for rec in state['requests']:
  if rec.get('status')=='downloaded' and rec.get('end')==end:
   path=Path(root)/'_system/data/reverse_splits/local/raw/databento/profit_expansion'/rec['raw_file']
   if path.exists() and path.with_suffix('.ok.json').exists():paths.append((rec['dataset'],path))
 by_day=defaultdict(dict);skipped=0
 for feed,path in dict.fromkeys(paths):
  if read(path.with_suffix('.ok.json')).get('source_sha256')!=digest(path):raise ValueError('Cached daily CSV hash mismatch')
  with path.open(encoding='utf-8',newline='') as handle:
   reader=csv.DictReader(handle)
   if not {'symbol','ts_event','open','high','low','close','volume'}.issubset(reader.fieldnames or []):raise ValueError('Daily bars lack dated symbol mapping or prices')
   for row in reader:
    observation=daily_observation(row)
    if observation is None:skipped+=1;continue
    symbol,day,vals,vol=observation
    by_day[symbol,day][feed]=(*vals,vol)
 overlay=work/'prices_overlay.sqlite';conn=sqlite3.connect(overlay)
 conn.executescript('CREATE TABLE IF NOT EXISTS prices_daily(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,date)); CREATE TABLE IF NOT EXISTS price_provenance(ticker TEXT,date TEXT,nominal INTEGER,source TEXT,volume_basis TEXT,PRIMARY KEY(ticker,date));')
 with conn:
  for (symbol,day),venues in by_day.items():
   feed,bar=max(venues.items(),key=lambda x:x[1][4]);volume=sum(x[4] for x in venues.values())
   conn.execute('INSERT OR REPLACE INTO prices_daily VALUES(?,?,?,?,?,?,?)',(symbol,day,*bar[:4],volume))
   conn.execute('INSERT OR REPLACE INTO price_provenance VALUES(?,?,?,?,?)',(symbol,day,1,'Databento '+feed,'sum distinct recorded venue volumes; incomplete consolidated coverage'))
 conn.close()
 state.update(through=through,actual_last_day=max((d for _,d in by_day),default=None),overlay_rows=len(by_day),skipped_missing_invalid_rows=skipped,downloaded_symbols_this_run=processed,new_paid_downloads_usd=0,raw_data_published=False,price_overlay_sha256=digest(overlay),raw_manifest_sha256=fingerprint({p.name:read(p.with_suffix('.ok.json'))['source_sha256'] for _,p in paths}),completed_at=datetime.now(timezone.utc).isoformat(),identity_warning='Raw-symbol histories can include ticker reuse; dated issuer continuity remains required. Not NBBO or proof of fills.')
 write(work/'market_data_receipt.local.json',state);print(json.dumps({k:state[k] for k in ['through','overlay_rows','downloaded_symbols_this_run','new_paid_downloads_usd']}))
 return state

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,default=ROOT);p.add_argument('--work',type=Path);p.add_argument('--max-symbols',type=int,default=600);p.add_argument('--through');a=p.parse_args();collect(a.source_root,a.work or a.source_root/'_system/data/reverse_splits/local/profit_program/20261022_v2_operations',maximum_symbols=a.max_symbols,through=a.through)
if __name__=='__main__':main()
