import hashlib,json,sqlite3
from pathlib import Path
import pytest
from _system.scripts.reverse_splits import profit_borrow as b

def sample(path):
 path.write_text('#BOF|2026.10.22|09:00:00\n#SYM|CUR|NAME|CON|ISIN|CUSIP|REBATERATE|FEERATE|AVAILABLE|\nABC|USD|Alpha|1|US00001|12345|2.5|50.0|>10000|\nXYZ|USD|Beta|2|US00002|67890|NA|NA|0|\n#EOF|2\n',encoding='utf-8');return path

def test_units_missing_fees_and_idempotency(tmp_path):
 db=b.connect(tmp_path/'b.sqlite');p=sample(tmp_path/'usa.txt');identity,added=b.ingest_ftp(db,p);assert added
 assert b.ingest_ftp(db,p)==(identity,False)
 doc=b.latest(db,['ABC','XYZ','ABSENT']);rows={r['symbol']:r for r in doc['rows']}
 assert rows['ABC']['fee_apr']==.5 and rows['ABC']['available_at_least']==1
 assert rows['XYZ']['fee_apr'] is None and rows['XYZ']['available_shares']==0
 assert rows['ABSENT']['fee_apr'] is None and rows['ABSENT']['status']=='not_listed'
 assert all(r['locate_approved'] is False for r in rows.values());db.close()

def test_truncated_and_conflicting_sources_are_rejected(tmp_path):
 db=b.connect(tmp_path/'b.sqlite');p=sample(tmp_path/'usa.txt');b.ingest_ftp(db,p)
 p.write_text(p.read_text().replace('50.0','60.0'));with_conflict=False
 with pytest.raises(ValueError,match='Conflicting'):b.ingest_ftp(db,p)
 p.write_text(p.read_text().replace('#EOF|2','#EOF|3'))
 with pytest.raises(Exception,match='truncated'):b.ingest_ftp(db,p)
 assert db.execute('SELECT COUNT(*) FROM short_borrow_observations').fetchone()[0]==2;db.close()

def test_etf_history_cannot_replace_current_public_indications(tmp_path):
 db=b.connect(tmp_path/'b.sqlite');b.ingest_ftp(db,sample(tmp_path/'usa.txt'))
 p=tmp_path/'etf.json';p.write_text(json.dumps({'symbols':{'ABC':[{'date':'2026-10-21','borrow_current':.01,'shares_available':100}]}}))
 receipt=b.import_etf(db,p,['ABC']);assert receipt['inserted_observations']==1
 assert b.latest(db,['ABC'])['rows'][0]['fee_apr']==.5
 assert db.execute("SELECT quality FROM short_borrow_observations WHERE quality LIKE 'etf%'").fetchone()[0]=='etf_daily_proxy_unverified';db.close()

def test_export_is_replayable_and_publishes_source_marker_last(tmp_path):
 db=b.connect(tmp_path/'b.sqlite');p=sample(tmp_path/'usa.txt');b.ingest_ftp(db,p)
 doc=b.export(db,tmp_path,['ABC']);out=tmp_path/'d1.sql';receipt=b.d1_export(db,tmp_path,out)
 sql=out.read_text(encoding='utf-8')
 assert sql.rindex('INSERT OR IGNORE INTO short_borrow_sources')>sql.rindex('INSERT OR IGNORE INTO short_borrow_observations')
 restored=b.connect(tmp_path/'restored.sqlite');restored.executescript(sql)
 assert b.ingest_ftp(restored,p)[1] is False
 assert b.latest(restored,['ABC'])['source']['captured_at']==doc['source']['captured_at']
 assert receipt['observations']==1
 db.close();restored.close()
