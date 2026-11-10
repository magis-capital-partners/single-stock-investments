import json
import subprocess
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_storage as storage
import private_storage_io as io
from test_private_storage import Objects, MemoryCatalog
import copy

class VersionCatalog(MemoryCatalog):
    def __init__(self):
        super().__init__()
        self.versions = {}
    def fetch(self):
        commit = storage.sha(storage.encoded_json(self.records))[:40]
        self.versions[commit] = copy.deepcopy(self.records)
        return commit
    def read(self, commit):
        return copy.deepcopy(self.versions[commit])
    def publish(self, updates, expected, **kwargs):
        super().publish(updates, expected)
        return self.fetch()

@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    monkeypatch.setenv('GITHUB_WORKSPACE',str(tmp_path))
    vault=tmp_path/'_external/research-vault'
    vault.mkdir(parents=True)
    subprocess.run(['git','init',str(vault)],check=True,capture_output=True)
    def git(*args):
        return subprocess.run(['git','-c','user.name=test','-c','user.email=test@example.test',*args],cwd=vault,check=True,capture_output=True)
    (vault/'baseline.json').write_bytes(b'{"old":true}\n')
    git('add','.');git('commit','-m','baseline')
    fake=storage.PrivateStorage(config={'catalog_repository_id':123},objects=Objects(),catalog=VersionCatalog())
    return vault,fake

def test_owned_scope_rejects_ordinary_checkout(environment,tmp_path):
    vault,_=environment
    assert io.owned(vault)==vault
    with pytest.raises(storage.StorageError,match='owned'):
        io.owned(tmp_path/'normal-project')

def test_verified_catalog_control_overlay_and_lazy_bulk(environment):
    vault,fake=environment
    fake.publish({'baseline.json':b'{"approved":true}\r\n','dashboard-private/objects/'+'a'*64:b'private object',
                  'recovery/V/approved.zip':b'PK\x03\x04exact'})
    result=io.initialize(vault,storage=fake)
    assert result['control_files_restored']==1
    assert (vault/'baseline.json').read_bytes()==b'{"approved":true}\r\n'
    assert not (vault/'recovery').exists()
    assert not (vault/'dashboard-private').exists()

def test_initialize_refuses_unpublished_local_changes(environment):
    vault,fake=environment
    fake.publish({'baseline.json':b'new remote'})
    (vault/'baseline.json').write_bytes(b'new local')
    with pytest.raises(storage.StorageError,match='unpublished'):
        io.initialize(vault,storage=fake)
    assert (vault/'baseline.json').read_bytes()==b'new local'

def test_lazy_exact_restore_is_create_only(environment,monkeypatch):
    vault,fake=environment
    relative='dashboard-private/objects/'+'a'*64
    fake.publish({relative:b'exact\r\noriginal'})
    io.initialize(vault,storage=fake)
    monkeypatch.setattr(io,'enabled',lambda:True)
    destination=io.materialize(vault,relative,storage=fake)
    assert destination.read_bytes()==b'exact\r\noriginal'
    destination.write_bytes(b'unpublished')
    assert io.materialize(vault,relative,storage=fake).read_bytes()==b'unpublished'

def test_publication_uses_original_view_for_concurrent_updates(environment):
    vault,fake=environment
    fake.publish({'a.json':b'old a','b.json':b'old b'})
    io.initialize(vault,storage=fake)
    # Another publisher changes b while this checkout only changes a.
    fake.publish({'b.json':b'new remote b'})
    (vault/'a.json').write_bytes(b'new a')
    io.publish_paths(vault,{'a.json':vault/'a.json'},storage=fake)
    assert io.view(vault,fake)['b.json']['sha256']==storage.sha(b'old b')
    (vault/'b.json').write_bytes(b'stale local b')
    with pytest.raises(storage.ConcurrentUpdate):
        io.publish_paths(vault,{'b.json':vault/'b.json'},storage=fake)

def test_successive_publications_keep_own_expected_revision(environment):
    vault,fake=environment
    io.initialize(vault,storage=fake)
    path=vault/'new.json';path.write_bytes(b'first')
    io.publish_paths(vault,{'new.json':path},storage=fake)
    path.write_bytes(b'second')
    io.publish_paths(vault,{'new.json':path},storage=fake)
    assert fake.restore('new.json')==b'second'

def test_paid_handoff_never_replaced(environment):
    vault,fake=environment
    name='valuation-underwriting/handoffs/'+'a'*64+'.json'
    fake.publish({name:b'approved'})
    io.initialize(vault,storage=fake)
    (vault/name).write_bytes(b'changed')
    with pytest.raises(storage.StorageError,match='immutable'):
        io.publish_paths(vault,{name:vault/name},storage=fake)
    assert fake.restore(name)==b'approved'

def test_force_selection_retains_ignored_paid_receipts(environment):
    vault,fake=environment
    (vault/'.gitignore').write_text('valuation-underwriting/\n')
    paid=vault/'valuation-underwriting/local-runtime/paid/receipt.json'
    paid.parent.mkdir(parents=True);paid.write_text('{"usage":"unknown"}')
    paths=io.selected_files(vault,'--force valuation-underwriting')
    assert list(paths)==['valuation-underwriting/local-runtime/paid/receipt.json']
    assert not io.selected_files(vault,'-A').get('valuation-underwriting/local-runtime/paid/receipt.json')

def test_pathspec_exclusions_and_deletion_hold(environment):
    vault,_=environment
    (vault/'new.json').write_text('{}')
    assert 'new.json' not in io.selected_files(vault,'-A . :!new.json')
    (vault/'baseline.json').unlink()
    with pytest.raises(storage.StorageError,match='deletion'):
        io.selected_files(vault,'-A')

def test_ledger_preserves_unknown_and_prior_events(environment):
    vault,fake=environment
    name='valuation-underwriting/local-runtime/ledger.jsonl'
    old=b'{"usage":"unknown","id":1}\n'
    fake.publish({name:old})
    io.initialize(vault,storage=fake)
    (vault/name).write_bytes(old+b'{"usage":"reported","id":2}\n')
    io.publish_paths(vault,{name:vault/name},storage=fake)
    assert fake.restore(name)==old+b'{"usage":"reported","id":2}\n'


def test_company_builds_require_explicit_ticker_and_limit():
    import yaml
    workflow=Path(__file__).resolve().parents[3]/'.github/workflows/valuation-underwriting.yml'
    config=yaml.load(workflow.read_text(),Loader=yaml.BaseLoader)
    assert set(config['on'])=={'repository_dispatch'}
    step=next(s for s in config['jobs']['underwrite']['steps'] if s.get('name')=='Author, independently challenge and build company valuations')
    assert 'test "$REQUESTED_LIMIT" = "1"' in step['run']
    assert '--tickers "$REQUESTED_TICKERS" --limit 1' in step['run']
