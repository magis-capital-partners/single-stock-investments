"""Read-only reconciliation of stored opening SSR states against existing DBN files."""
import argparse,bisect,hashlib,json,sqlite3
from datetime import datetime,time,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import databento as db
import numpy as np
ET=ZoneInfo('America/New_York')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def norm(s): return ''.join(c for c in s.upper() if c.isalnum())
def cutoff(day): return int(datetime.combine(datetime.fromisoformat(day).date(),time(9,30),ET).timestamp()*1e9)
def audit(source,events):
 directory=source/'_system/data/reverse_splits/local/raw/databento/XNAS.ITCH/status'
 join_file=source/'_system/data/reverse_splits/local/reports/rename_joins.json'
 joins=json.loads(join_file.read_text()) if join_file.exists() else []
 alias={(j['ticker'],j['ex_date']):j['filing_time_symbol'] for j in joins}
 targets=[dict(e,raw_symbol=alias.get((e['ticker'],e['event_date']),e['ticker'])) for e in events if e.get('entry_day')]
 wanted={norm(e['raw_symbol']) for e in targets}; latest={};sources=[]
 years=[int(e['entry_day'][:4]) for e in targets]
 for f in sorted(directory.glob('*.dbn.zst')):
  if not min(years)-1<=int(f.name[:4])<=max(years): continue
  sym=f.with_name(f.name.replace('.dbn.zst','.symbology.json'))
  spans=json.loads(sym.read_text()); matches=[]
  for iid,ivs in spans.items():
   for iv in ivs:
    if norm(iv['s']) in wanted: matches.append((int(iid),iv))
  if not matches: continue
  arr=db.DBNStore.from_file(str(f)).to_ndarray()
  arr=arr[np.isin(arr['instrument_id'],np.array(sorted({iid for iid,_ in matches}),dtype=arr['instrument_id'].dtype))]
  ts=arr['ts_event'].astype('uint64');ids=arr['instrument_id']
  for iid,iv in matches:
   lo=int(datetime.fromisoformat(iv['d0']).replace(tzinfo=ET).timestamp()*1e9);hi=int(datetime.fromisoformat(iv['d1']).replace(tzinfo=ET).timestamp()*1e9)
   rs=arr[(ids==iid)&(ts>=lo)&(ts<hi)];rs=np.sort(rs,order='ts_event')
   flags=rs['is_short_sell_restricted']; rs=rs[np.isin(flags,[b'Y',b'N'])]
   if not len(rs):continue
   times=rs['ts_event'].astype('uint64').tolist()
   for e in targets:
    if norm(e['raw_symbol'])!=norm(iv['s']):continue
    at=cutoff(e['entry_day']); k=bisect.bisect_right(times,at)-1
    if k<0:continue
    r=rs[k];stamp=int(r['ts_event']);old=latest.get(e['id'])
    if old is None or stamp>old['ts_event']:
     flag=r['is_short_sell_restricted'];restricted=flag==b'Y'
     latest[e['id']]={'ts_event':stamp,'restricted':int(restricted),'source_file':f.name,'source_instrument':iid,'symbol':iv['s'],'message_day':datetime.fromtimestamp(stamp/1e9,timezone.utc).astimezone(ET).date().isoformat()}
  sources.append({'file':f.name,'sha256':sha(f),'symbology_sha256':sha(sym)})
  print('Read cached SSR '+f.name,flush=True)
  del arr,ts,ids
 database=source/'_system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z/prices.sqlite'
 conn=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True);rows=[]
 for e in events:
  stored=conn.execute('SELECT restricted,source FROM ssr_states WHERE ticker=? AND date=?',(e['ticker'],e.get('entry_day'))).fetchone() if e.get('entry_day') else None
  raw=latest.get(e['id']);rows.append({'id':e['id'],'ticker':e['ticker'],'event_date':e['event_date'],'entry_day':e.get('entry_day'),'stored_state':stored[0] if stored else None,'stored_source':stored[1] if stored else None,'raw':raw,'matches':bool(raw and stored and raw['restricted']==stored[0]),'fresh_same_day':bool(raw and raw['message_day']==e.get('entry_day'))})
 conn.close()
 return {'schema':'third_plus_ssr_source_audit.v1','dataset':'XNAS.ITCH','cutoff':'last explicit Y/N with event timestamp <= 09:30 America/New_York, date-valid raw symbology','rows':rows,'sources':sources,'no_network_calls':True,'independent_broker_verification':False,'trigger_trade_reconstructed':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--events',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 data=json.loads(Path(a.events).read_text(encoding='utf-8'));events=data['audit']['events']
 result=audit(Path(a.source_root),events);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'events':len(result['rows']),'matches':sum(r['matches'] for r in result['rows']),'fresh':sum(r['fresh_same_day'] for r in result['rows'])}),flush=True)
