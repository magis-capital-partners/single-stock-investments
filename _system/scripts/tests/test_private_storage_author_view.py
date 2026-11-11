"""Local author views preserve obsolete build controls and require every real ledger row."""
import json,sys,subprocess
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import private_storage_io as io
from private_storage import StorageError,sha,encoded_json
BATCH='valuation-underwriting/runtime/batch.json'
LEDGER='valuation-underwriting/runtime/ledger.jsonl'
LOCAL_STATE='valuation-underwriting/local-runtime/states/CPRT.json'
@pytest.fixture(autouse=True)
def local_environment(monkeypatch):monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
def vault(tmp_path):
 v=tmp_path/'vault';v.mkdir();(tmp_path/'runtime-owner.json').write_text(json.dumps({'repository':'magis-capital-partners/single-stock-investments','purpose':'local-codex-underwriting'}));return v
class Storage:
 def __init__(self,files):self.files=files;self.restored=[];self.config={'catalog_repository_id':123};self.objects=None
 def snapshot(self):return 'a'*40,{p:{'sha256':sha(b)} for p,b in self.files.items()}
 def restore(self,path,**kw):self.restored.append(path);return self.files[path]
def put(v,name,raw):p=v/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return p

def test_default_view_still_refuses_differing_unpublished_build_record(tmp_path,monkeypatch):
 v=vault(tmp_path);p=put(v,BATCH,b'{"selected":["old"]}');store=Storage({BATCH:b'{"selected":["current"]}'})
 monkeypatch.setattr(io,'run_git',lambda *a,**k:subprocess.CompletedProcess(a,1,b'',b''))
 with pytest.raises(StorageError,match='differing unpublished'):io.initialize(v,storage=store)
 assert p.read_bytes()==b'{"selected":["old"]}' and not (v/io.MARKER).exists()

def test_author_view_preserves_unneeded_shared_batch_and_advances_only_verified_ledger(tmp_path):
 v=vault(tmp_path);original=b'{"selected":["old unpublished build"]}';p=put(v,BATCH,original);ledger=put(v,LEDGER,b'{ "id":1 }\r\n')
 store=Storage({BATCH:b'{"selected":["remote build"]}',LEDGER:b'{"id":1}\n{"id":2}\n'})
 result=io.initialize(v,storage=store,materialization_role='local_author',selected_ticker='CPRT')
 assert p.read_bytes()==original and BATCH not in store.restored
 assert ledger.read_bytes()==b'{ "id":1 }\r\n{"id":2}\n'
 marker=json.loads((v/io.MARKER).read_bytes());assert marker['materialization_role']=='local_author' and not marker['read_only']
 record=marker['preserved_shared_build_controls'][0]
 assert record['path']==BATCH and record['original_sha256']==sha(original)
 assert record['snapshot_sha256']==sha(store.files[BATCH]) and result['preserved_shared_build_controls']==[record]

@pytest.mark.parametrize('path,old,new',[(LEDGER,b'{"id":2}\n',b'{"id":1}\n'),(LOCAL_STATE,b'{"author":8}',b'{"author":0}')])
def test_author_view_never_skips_required_ledger_or_paid_state_conflicts(tmp_path,monkeypatch,path,old,new):
 v=vault(tmp_path);p=put(v,path,old);store=Storage({path:new})
 monkeypatch.setattr(io,'run_git',lambda *a,**k:subprocess.CompletedProcess(a,1,b'',b''))
 with pytest.raises(StorageError):io.initialize(v,storage=store,materialization_role='local_author',selected_ticker='CPRT')
 assert p.read_bytes()==old

def test_local_author_role_cannot_be_used_by_a_ci_checkout(tmp_path,monkeypatch):
 v=vault(tmp_path);monkeypatch.setenv('GITHUB_ACTIONS','true')
 with pytest.raises(StorageError,match='local author'):io.initialize(v,storage=Storage({}),materialization_role='local_author',selected_ticker='CPRT')
 assert not (v/io.MARKER).exists()

def test_excluded_shared_build_record_cannot_be_returned_as_current(tmp_path):
 v=vault(tmp_path);put(v,BATCH,b'old');(v/io.MARKER).write_text(json.dumps({'materialization_role':'local_author'}))
 with pytest.raises(StorageError,match='shared build control'):io.materialize(v,BATCH)

def test_author_view_cannot_publish_shared_build_controls(tmp_path):
 v=vault(tmp_path);p=put(v,BATCH,b'old');(v/io.MARKER).write_text(json.dumps({'materialization_role':'local_author','read_only':False}))
 with pytest.raises(StorageError,match='shared build control'):io.publish_paths(v,{BATCH:p},storage=Storage({}))

@pytest.mark.parametrize('role',['build','all','anything'])
def test_unknown_materialization_roles_fail_closed(tmp_path,role):
 with pytest.raises(StorageError,match='materialization role'):io.initialize(vault(tmp_path),storage=Storage({}),materialization_role=role)

@pytest.mark.parametrize('path',[BATCH,'valuation-underwriting/runtime/states/CPRT.json','valuation-underwriting/runtime/stage-cache/old/receipt.json'])
def test_absent_or_existing_build_inputs_are_inaccessible_to_author_view(tmp_path,path):
 v=vault(tmp_path);store=Storage({path:b'{"unused":true}'})
 io.initialize(v,storage=store,materialization_role='local_author',selected_ticker='CPRT')
 assert not (v/path).exists() and store.restored==[]
 with pytest.raises(StorageError,match='shared build control'):io.materialize(v,path,storage=store)

def test_author_view_materializes_and_reads_the_shared_ledger(tmp_path):
 v=vault(tmp_path);raw=b'{"reservation_id":"existing shared charge"}\n';store=Storage({LEDGER:raw})
 io.initialize(v,storage=store,materialization_role='local_author',selected_ticker='CPRT')
 assert io.materialize(v,LEDGER,storage=store).read_bytes()==raw
 with pytest.raises(StorageError,match='shared build control'):io.publish_paths(v,{LEDGER:v/LEDGER},storage=store)

def test_default_view_still_materializes_shared_build_inputs(tmp_path):
 v=vault(tmp_path);store=Storage({BATCH:b'{"selected":["approved company"]}'})
 io.initialize(v,storage=store)
 assert (v/BATCH).read_bytes()==store.files[BATCH] and store.restored==[BATCH]

def test_preserved_shared_control_cannot_be_a_directory(tmp_path):
 v=vault(tmp_path);(v/BATCH).mkdir(parents=True)
 with pytest.raises(StorageError,match='Invalid preserved'):io.initialize(v,storage=Storage({BATCH:b'{}'}),materialization_role='local_author',selected_ticker='CPRT')

def test_clone_vault_selects_author_view_without_reset_or_shared_checkout(tmp_path,monkeypatch):
 import underwriting_local as local,private_storage
 v=vault(tmp_path);(v/'.git').mkdir();calls=[];roles=[]
 def git(directory,*args,**kwargs):
  calls.append(args)
  return ('https://github.com/'+local.VAULT+'.git\n').encode() if args==('remote','get-url','origin') else b''
 monkeypatch.setattr(local,'git',git);monkeypatch.setattr(private_storage,'enabled',lambda:True)
 monkeypatch.setattr(io,'initialize',lambda v,**kw:roles.append(kw))
 assert local.clone_vault(tmp_path,tickers=['CPRT'])==v and roles==[{'materialization_role':'local_author','selected_ticker':'CPRT'}]
 assert calls==[('remote','get-url','origin'),('fetch','-q','origin','main')]
