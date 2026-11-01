# Public IBKR borrow indications. No Gateway, account login, subscriptions or orders.
from __future__ import annotations
import argparse,csv,ftplib,hashlib,json,math,re,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[3]
HOST='ftp2.interactivebrokers.com'
URL='ftp://'+HOST+'/usa.txt'
NY=ZoneInfo('America/New_York')
SCHEMA='''CREATE TABLE IF NOT EXISTS short_borrow_sources(
 id TEXT PRIMARY KEY,source TEXT NOT NULL,as_of TEXT NOT NULL,captured_at TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,source_rows INTEGER NOT NULL,checksum_verified INTEGER NOT NULL,
 time_basis TEXT NOT NULL,source_url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS short_borrow_observations(
 source_id TEXT NOT NULL,symbol TEXT NOT NULL,as_of TEXT NOT NULL,fee_apr REAL,rebate_apr REAL,
 available_shares INTEGER,available_at_least INTEGER NOT NULL DEFAULT 0,conid TEXT,isin TEXT,
 cusip TEXT,currency TEXT,quality TEXT NOT NULL,PRIMARY KEY(source_id,symbol));
CREATE INDEX IF NOT EXISTS idx_short_borrow_symbol_time ON short_borrow_observations(symbol,as_of DESC);
CREATE INDEX IF NOT EXISTS idx_short_borrow_source_time ON short_borrow_sources(source,as_of DESC);
CREATE TABLE IF NOT EXISTS short_borrow_current(
 symbol TEXT PRIMARY KEY,source_id TEXT NOT NULL,as_of TEXT NOT NULL,fee_apr REAL,
 available_shares INTEGER,available_at_least INTEGER NOT NULL,quality TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS short_borrow_collections(
 id TEXT PRIMARY KEY,attempted_at TEXT NOT NULL,status TEXT NOT NULL,detail TEXT,source_id TEXT);
'''
def now():return datetime.now(timezone.utc).isoformat()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def write(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp')
 t.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');t.replace(p)
def connect(path):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(p,timeout=30);db.row_factory=sqlite3.Row;db.executescript(SCHEMA);return db
def numeric(value):
 try:
  n=float(str(value).strip().lstrip('>'));return n if math.isfinite(n) else None
 except (ValueError,TypeError):return None

def fetch(raw_dir,*,ftp_factory=ftplib.FTP):
 data=bytearray();checksum=bytearray();ftp=ftp_factory()
 try:
  ftp.connect(HOST,timeout=35);ftp.login('shortstock','')
  ftp.retrbinary('RETR usa.txt',data.extend);ftp.retrbinary('RETR usa.txt.md5',checksum.extend)
 finally:ftp.close()
 expected=checksum.decode('ascii').strip().split()[0].lower()
 if not re.fullmatch('[a-f0-9]{32}',expected) or hashlib.md5(bytes(data).replace(b'\r\n',b'\n')).hexdigest()!=expected:
  raise ValueError('IBKR file failed published checksum; archive rejected')
 p=Path(raw_dir)/('usa_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.txt')
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.with_suffix('.md5').write_bytes(checksum);return p

def parse(path):
 from ..refresh_short_alpha_borrow import parse_public_ftp
 rows,meta=parse_public_ftp(Path(path));raw=Path(path).read_bytes()
 stamp=datetime.fromisoformat(meta['as_of'].replace('Z','+00:00'))
 if stamp>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('Future IBKR source clock')
 text=raw.decode('utf-8-sig');header=next(l[1:].rstrip('|') for l in text.splitlines() if l.startswith('#SYM|'))
 extra={r['SYM'].strip().upper():r for r in csv.DictReader((l for l in text.splitlines() if l and not l.startswith('#')),fieldnames=header.split('|'),delimiter='|')}
 if len({r['ticker'] for r in rows})!=len(rows):raise ValueError('Duplicate IBKR symbols')
 for r in rows:
  if r['rate_pct'] is not None and r['rate_pct']<0:raise ValueError('Negative fee-only rate')
  if r['available'] is not None and r['available']<0:raise ValueError('Negative availability')
  x=extra[r['ticker']];rebate=numeric(x.get('REBATERATE'))
  r.update(conid=x.get('CON'),isin=x.get('ISIN'),cusip=x.get('CUSIP'),currency=x.get('CUR'),rebate_apr=rebate/100 if rebate is not None else None)
 return rows,meta,raw

def ingest_ftp(db,path,*,checksum_verified=False):
 rows,meta,raw=parse(path);sha=digest(raw);identity=digest(('ibkr_public_ftp|'+meta['as_of']).encode())
 old=db.execute('SELECT source_sha256 FROM short_borrow_sources WHERE id=?',(identity,)).fetchone()
 if old and old[0]!=sha:raise ValueError('Conflicting immutable source vintage')
 if old:return identity,False
 with db:
  db.execute('INSERT INTO short_borrow_sources VALUES(?,?,?,?,?,?,?,?,?)',(identity,'ibkr_public_ftp',meta['as_of'],now(),sha,len(rows),int(checksum_verified),'IBKR_BOF_US_Eastern',URL))
  db.executemany('INSERT INTO short_borrow_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',[(identity,r['ticker'],r['as_of'],r['rate_pct']/100 if r['rate_pct'] is not None else None,r['rebate_apr'],r['available'],int(r.get('at_least',False)),r['conid'],r['isin'],r['cusip'],r['currency'],'public_indication') for r in rows])
 return identity,True

def watchlist(root):
 p=Path(root)/'_system/data/reverse_splits/profit_program';result=set()
 if (p/'summary.json').exists():
  doc=json.loads((p/'summary.json').read_text(encoding='utf-8'))
  for part in doc['parts']:
   for e in json.loads((p/part['file']).read_text(encoding='utf-8'))['events']:
    if e.get('ticker'):result.add(e['ticker'].upper())
 from ..refresh_short_alpha_borrow import ledger_tickers
 result.update(ledger_tickers());return sorted(s for s in result if re.fullmatch(r'[A-Z0-9][A-Z0-9.\-/]{0,24}',s))

def import_etf(db,path,symbols):
 raw=Path(path).read_bytes();doc=json.loads(raw);sha=digest(raw)
 overlap=sorted(set(doc.get('symbols',{}))&set(symbols));total=0
 for symbol in overlap:
  for r in doc['symbols'][symbol]:
   day=r.get('date','')
   if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):continue
   asof=(datetime.fromisoformat(day).replace(tzinfo=NY)+timedelta(days=1)).astimezone(timezone.utc).isoformat()
   identity=digest(('etf_daily_proxy|'+day+'|'+sha).encode());fee=numeric(r.get('borrow_current'));avail=numeric(r.get('shares_available'))
   if fee is not None and fee<0:fee=None
   with db:
    db.execute('INSERT OR IGNORE INTO short_borrow_sources VALUES(?,?,?,?,?,?,?,?,?)',(identity,'etf_daily_proxy',asof,now(),sha,len(doc['symbols']),0,'date_only_reconstructed_not_observed_clock','https://github.com/magis-capital-partners/etf-dashboard/blob/main/data/borrow_history.json'))
    cur=db.execute('INSERT OR IGNORE INTO short_borrow_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(identity,symbol,asof,fee,None,int(avail) if avail is not None and avail>=0 else None,0,None,None,None,'USD','etf_daily_proxy_unverified'));total+=cur.rowcount
 return {'source_sha256':sha,'symbols_in_source':len(doc.get('symbols',{})),'overlap_symbols':overlap,'inserted_observations':total,'time_basis':'Reconstructed daily proxy; not verified intraday availability or an approved loan.'}

def latest(db,symbols):
 source=db.execute("SELECT * FROM short_borrow_sources WHERE source='ibkr_public_ftp' ORDER BY as_of DESC LIMIT 1").fetchone()
 if not source:return {'schema_version':'short_borrow.v1','generated_at':now(),'source':None,'rows':[],'checked_symbols':symbols}
 source=dict(source);found={r['symbol']:dict(r) for r in db.execute('SELECT * FROM short_borrow_observations WHERE source_id=?',(source['id'],))};rows=[]
 for s in symbols:
  r=found.get(s);rows.append({**({'symbol':s,'as_of':source['as_of'],'fee_apr':None,'available_shares':None,'available_at_least':0,'quality':'not_listed_in_source'} if r is None else r),'status':'not_listed' if r is None else 'indication','locate_approved':False})
 return {'schema_version':'short_borrow.v1','generated_at':now(),'source':source,'checked_symbols':symbols,'rows':rows,'matched_symbols':sum(r['status']=='indication' for r in rows),'note':'Fee-only annual fractions. Absent names have unknown availability, never zero fees. Indications are not approved loans; historical ticker aliases need review.'}

def export(db,root,symbols):
 doc=latest(db,symbols);base=Path(root)/'_system/data/reverse_splits/borrow_monitor';public=Path(root)/'dashboard/data/short_borrow'
 for p in [base/'latest.json',public/'latest.json']:write(p,doc)
 if not doc['source']:return doc
 source=doc['source'];matched=[r for r in doc['rows'] if r['status']=='indication']
 with db:
  db.executemany('INSERT INTO short_borrow_current VALUES(?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET source_id=excluded.source_id,as_of=excluded.as_of,fee_apr=excluded.fee_apr,available_shares=excluded.available_shares,available_at_least=excluded.available_at_least,quality=excluded.quality WHERE excluded.as_of>=short_borrow_current.as_of',[(r['symbol'],source['id'],r['as_of'],r['fee_apr'],r['available_shares'],r['available_at_least'],r['quality']) for r in matched])
 day=source['as_of'][:10];vintage=base/'daily'/f'{day}.json'
 history=json.loads(vintage.read_text(encoding='utf-8')) if vintage.exists() else {'schema_version':'short_borrow_day.v1','date':day,'snapshots':[]}
 history['snapshots']=[r for r in history['snapshots'] if r['source']['id']!=source['id']]+[{'source':source,'rows':matched}]
 history['snapshots'].sort(key=lambda r:r['source']['as_of']);write(vintage,history);return doc

def sql_literal(v):
 if v is None:return 'NULL'
 if isinstance(v,(int,float)):
  if not math.isfinite(v):raise ValueError('Non-finite SQL number')
  return str(v)
 return "'"+str(v).replace("'","''")+"'"

def d1_export(db,root,path,*,since=None):
 base=Path(root)/'_system/data/reverse_splits/borrow_monitor/daily';sources={};rows={}
 for p in sorted(base.glob('*.json')):
  if since and p.stem<since:continue
  for snap in json.loads(p.read_text(encoding='utf-8'))['snapshots']:
   s=snap['source'];sources[s['id']]=s
   for r in snap['rows']:rows[(s['id'],r['symbol'])]=r
 statements=[SCHEMA]
 for r in rows.values():
  values=[r.get(k) for k in ['source_id','symbol','as_of','fee_apr','rebate_apr','available_shares','available_at_least','conid','isin','cusip','currency','quality']]
  statements.append('INSERT OR IGNORE INTO short_borrow_observations VALUES('+','.join(map(sql_literal,values))+');')
 if sources:
  s=max(sources.values(),key=lambda r:r['as_of'])
  for r in rows.values():
   if r['source_id']==s['id']:
    values=[r.get(k) for k in ['symbol','source_id','as_of','fee_apr','available_shares','available_at_least','quality']]
    statements.append('INSERT INTO short_borrow_current VALUES('+','.join(map(sql_literal,values))+') ON CONFLICT(symbol) DO UPDATE SET source_id=excluded.source_id,as_of=excluded.as_of,fee_apr=excluded.fee_apr,available_shares=excluded.available_shares,available_at_least=excluded.available_at_least,quality=excluded.quality WHERE excluded.as_of>=short_borrow_current.as_of;')
 # Publish source markers last: interrupted remote imports must not advertise a partial vintage.
 for s in sources.values():
  values=[s[k] for k in ['id','source','as_of','captured_at','source_sha256','source_rows','checksum_verified','time_basis','source_url']]
  statements.append('INSERT OR IGNORE INTO short_borrow_sources VALUES('+','.join(map(sql_literal,values))+');')
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('\n'.join(statements),encoding='utf-8');return {'sources':len(sources),'observations':len(rows),'estimated_indexed_writes':len(rows)*2+len(sources)*2,'sql':str(p)}

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['collect','import','import-etf','export','sql']);ap.add_argument('--source-root',type=Path,default=ROOT);ap.add_argument('--input',type=Path);ap.add_argument('--db',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--since');ap.add_argument('--legacy-archive',action='store_true')
 a=ap.parse_args(argv);local=a.source_root/'_system/data/reverse_splits/local';db=connect(a.db or local/'borrow_monitor/borrow.sqlite');symbols=watchlist(ROOT)
 try:
  if a.command in {'collect','import'}:
   path=fetch(local/'raw/borrow_monitor') if a.command=='collect' else a.input
   if path is None:ap.error('--input required')
   identity,added=ingest_ftp(db,path,checksum_verified=a.command=='collect');doc=export(db,ROOT,symbols)
   if a.legacy_archive:
    from .borrow_archive import archive
    from .config import load_config
    archive(load_config(),input_path=path)
   print(json.dumps({'as_of':doc['source']['as_of'],'us_symbols':doc['source']['source_rows'],'ssi_matches':doc['matched_symbols'],'checked_ssi_symbols':len(symbols),'new_vintage':added,'source_sha256':doc['source']['source_sha256'],'locate_approved':False}))
  elif a.command=='import-etf':
   if not a.input:ap.error('--input required')
   receipt=import_etf(db,a.input,symbols)
   for p in [ROOT/'_system/data/reverse_splits/borrow_monitor/etf-import.json',ROOT/'dashboard/data/short_borrow/etf-import.json']:write(p,receipt)
   print(json.dumps(receipt))
  elif a.command=='sql':print(json.dumps(d1_export(db,ROOT,a.output or local/'borrow_monitor/d1.sql',since=a.since)))
  else:
   doc=export(db,ROOT,symbols);print(json.dumps({'rows':len(doc['rows']),'matched':doc.get('matched_symbols',0)}))
 except Exception as exc:
  with db:db.execute('INSERT INTO short_borrow_collections VALUES(?,?,?,?,?)',(digest(now().encode()),now(),'failed',str(exc)[:500],None))
  raise
 finally:db.close()
if __name__=='__main__':main()
