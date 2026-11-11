"""One selected author may preserve its work without selecting another issuer's stale controls."""
import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import private_storage as storage
import private_storage_io as io
import underwriting_local as local
from test_private_storage import Objects
from test_private_storage_io import VersionCatalog
from test_private_storage_author_view import vault,put,Storage
MA='valuation-underwriting/local-runtime/states/MA.json'
CPRT='valuation-underwriting/local-runtime/states/CPRT.json'
LEDGER='valuation-underwriting/local-runtime/ledger.jsonl'
@pytest.fixture(autouse=True)
def local_environment(monkeypatch):monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
class LegacyStorage(storage.PrivateStorage):
 def __init__(self):
  super().__init__(config={'catalog_repository_id':123},objects=Objects(),catalog=VersionCatalog());self.legacy={}
 def lookup_entry(self,relative,records):return records.get(relative) or self.legacy.get(relative)

def marker(v,fake,subject='CPRT'):
 pin,records=fake.snapshot();(v/io.MARKER).write_bytes(storage.encoded_json({'schema_version':'private-storage-view/1','catalog_commit':pin,'catalog_repository_id':123,'read_only':False,'materialization_role':'local_author','selected_ticker':subject}))

def test_normal_private_save_cannot_replace_newer_unselected_legacy_state(tmp_path,monkeypatch):
 v=vault(tmp_path);fake=LegacyStorage();correct=b'{"contract_hash":"reviewed-main","stage_attempts":{"author":15},"last_attempt":"2026-11-01"}'
 fake.legacy[MA]=storage.store_bytes(fake.objects,correct);put(v,MA,b'{"contract_hash":"superseded-local","stage_attempts":{"author":1},"last_attempt":"2026-10-29"}')
 put(v,CPRT,b'{"stage_attempts":{"author":9}}');put(v,LEDGER,b'{"subject":"CPRT","status":"completed"}\n');marker(v,fake)
 monkeypatch.setattr(storage,'enabled',lambda *a,**kw:True);monkeypatch.setattr(io,'PrivateStorage',lambda:fake)
 assert local.publish_runtime(v,tmp_path)
 assert fake.restore(MA)==correct
 assert fake.restore(CPRT)==(v/CPRT).read_bytes()
 assert MA not in fake.catalog.records

@pytest.mark.parametrize('path',['valuation-underwriting/local-runtime/states/MA.json','valuation-underwriting/local-runtime/progress/MA.json','valuation-underwriting/local-runtime/cache/MA/old/receipt.json','valuation-underwriting/handoffs/latest/MA.json'])
def test_selected_view_preserves_unselected_local_bytes_without_selecting_them(tmp_path,path):
 v=vault(tmp_path);old=b'{"historic":true}';put(v,path,old);store=Storage({path:b'{"current_remote":true}',CPRT:b'{"author":9}'})
 io.initialize(v,storage=store,materialization_role='local_author',selected_ticker='CPRT')
 assert (v/path).read_bytes()==old and path not in store.restored
 assert (v/CPRT).read_bytes()==store.files[CPRT]
 m=json.loads((v/io.MARKER).read_bytes());assert m['selected_ticker']=='CPRT'
 assert m['preserved_unselected_author_controls'][0]['path']==path
 with pytest.raises(storage.StorageError,match='unselected'):io.materialize(v,path,storage=store)

@pytest.mark.parametrize('path',[MA,'valuation-underwriting/local-runtime/progress/MA.json','valuation-underwriting/handoffs/latest/MA.json','valuation-underwriting/local-runtime/packets/other.json','valuation-underwriting/handoffs/other.json'])
def test_scoped_writer_refuses_other_issuer_before_any_upload(tmp_path,path):
 v=vault(tmp_path);fake=LegacyStorage();put(v,path,b'{"ticker":"MA"}');marker(v,fake)
 with pytest.raises(storage.StorageError,match='selected company'):io.publish_paths(v,{path:v/path},storage=fake)
 assert not fake.catalog.records

@pytest.mark.parametrize('subject',[None,'','CPRT,MA','../CPRT','CPRT/MA'])
def test_author_view_requires_one_safe_selected_ticker(tmp_path,subject):
 with pytest.raises(storage.StorageError,match='selected ticker'):io.initialize(vault(tmp_path),storage=Storage({}),materialization_role='local_author',selected_ticker=subject)

def test_selected_control_conflict_and_global_ledger_divergence_still_fail(tmp_path,monkeypatch):
 import subprocess
 v=vault(tmp_path);p=put(v,CPRT,b'{"author":9}');put(v,MA,b'{"author":1}');store=Storage({CPRT:b'{"author":8}',MA:b'{"author":15}'})
 monkeypatch.setattr(io,'run_git',lambda *a,**k:subprocess.CompletedProcess(a,1,b'',b''))
 with pytest.raises(storage.StorageError):io.initialize(v,storage=store,materialization_role='local_author',selected_ticker='CPRT')
 assert p.read_bytes()==b'{"author":9}'
 (tmp_path/'ledger-scope').mkdir();w=vault(tmp_path/'ledger-scope');put(w,LEDGER,b'{"subject":"OTHER","id":2}\n')
 with pytest.raises(storage.StorageError,match='divergent'):io.initialize(w,storage=Storage({LEDGER:b'{"subject":"OTHER","id":1}\n'}),materialization_role='local_author',selected_ticker='CPRT')

def test_scope_cannot_select_a_different_issuer_packet_under_an_owned_filename(tmp_path):
 v=vault(tmp_path);fake=LegacyStorage();p=put(v,'valuation-underwriting/handoffs/latest/CPRT.json',b'{"ticker":"MA"}');marker(v,fake)
 with pytest.raises(storage.StorageError,match='selected company'):io.publish_paths(v,{p.relative_to(v).as_posix():p},storage=fake)


def test_owned_paid_failures_packets_and_handoffs_are_all_retained_with_the_full_ledger(tmp_path,monkeypatch):
 v=vault(tmp_path);fake=LegacyStorage();marker(v,fake)
 files={
  CPRT:b'{"stage_attempts":{"author":9}}',
  'valuation-underwriting/local-runtime/progress/CPRT.json':b'{"feedback":{"retain":true}}',
  'valuation-underwriting/local-runtime/cache/CPRT/failure/output.json':b'{"ticker":"OTHER","invalid_paid_response":"preserve exact bytes"}',
  'valuation-underwriting/local-runtime/packets/own.json':b'{"ticker":"CPRT","whole_evidence":true}',
  'valuation-underwriting/handoffs/own.json':b'{"ticker":"CPRT","immutable":true}',
  'valuation-underwriting/handoffs/latest/CPRT.json':b'{"ticker":"CPRT","handoff_hash":"own"}',
  'valuation-underwriting/local-runtime/batch.json':b'{"selected":["CPRT"],"approved":[],"completed":[]}',
  LEDGER:b'{"subject":"OTHER","id":1}\n{"subject":"CPRT","id":2}\n',
 }
 for path,raw in files.items():put(v,path,raw)
 put(v,MA,b'{"historic":"other issuer"}')
 monkeypatch.setattr(storage,'enabled',lambda *a,**k:True);monkeypatch.setattr(io,'PrivateStorage',lambda:fake)
 assert local.publish_runtime(v,tmp_path,tickers=['CPRT'])
 for path,raw in files.items():assert fake.restore(path)==raw,path
 assert MA not in fake.catalog.records


def test_explicit_save_ticker_must_match_the_owned_view(tmp_path,monkeypatch):
 v=vault(tmp_path);fake=LegacyStorage();put(v,CPRT,b'{}');marker(v,fake)
 monkeypatch.setattr(storage,'enabled',lambda *a,**k:True)
 with pytest.raises(Exception,match='one selected ticker'):local.publish_runtime(v,tmp_path,tickers=['MA'])
 assert not fake.catalog.records


def test_other_issuer_batch_cannot_be_published_under_selected_scope(tmp_path):
 v=vault(tmp_path);fake=LegacyStorage();marker(v,fake);rel='valuation-underwriting/local-runtime/batch.json';p=put(v,rel,b'{"selected":["MA"]}')
 with pytest.raises(storage.StorageError,match='selected company'):io.publish_paths(v,{rel:p},storage=fake)
 assert not fake.catalog.records


def test_unscoped_author_marker_cannot_publish(tmp_path):
 v=vault(tmp_path);fake=LegacyStorage();put(v,CPRT,b'{}');marker(v,fake,None)
 with pytest.raises(storage.StorageError,match='selected ticker'):io.publish_paths(v,{CPRT:v/CPRT},storage=fake)


def test_default_ci_or_validation_view_cannot_borrow_a_company_scope(tmp_path):
 with pytest.raises(storage.StorageError,match='local author'):io.initialize(vault(tmp_path),storage=Storage({}),selected_ticker='CPRT')
