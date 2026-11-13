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


def test_source_parts_use_verified_object_store_before_manifest(environment,monkeypatch):
    vault,fake=environment
    io.initialize(vault,storage=fake)
    import push_company_source_parts as parts
    import private_storage
    monkeypatch.setattr(private_storage,'enabled',lambda:True)
    actual_publish=io.publish_paths
    monkeypatch.setattr(io,'publish_paths',lambda root,paths:actual_publish(root,paths,storage=fake))
    raw=b'PK\x03\x04complete original archive bytes'
    identity=storage.sha(raw)
    folder=vault/'dashboard-private/company-source-backfill-v2'
    folder.mkdir(parents=True)
    path=folder/(identity+'.zip');path.write_bytes(raw)
    (folder/'manifest.json').write_text(json.dumps({'parts':[{'file':path.name,'sha256':identity}]}))
    result=parts.publish(vault)
    assert result['parts_uploaded']==1
    relative=path.relative_to(vault).as_posix()
    assert fake.restore(relative)==raw
    assert fake.restore('dashboard-private/company-source-backfill-v2/manifest.json') is None
    assert subprocess.check_output(['git','log','--format=%s'],cwd=vault).strip()==b'baseline'


def test_relative_vault_root_matches_normal_CI_publication(environment,monkeypatch):
    vault,fake=environment
    io.initialize(vault,storage=fake)
    path=vault/'valuation-underwriting/runtime/states/V.json'
    path.parent.mkdir(parents=True);path.write_text('{"status":"validated"}')
    monkeypatch.chdir(vault.parent.parent)
    relative=Path('_external/research-vault')
    selected=io.selected_files(relative,'--force valuation-underwriting')
    assert list(selected)==['valuation-underwriting/runtime/states/V.json']
    result=io.publish_paths(relative,selected,storage=fake)
    assert result['files_preserved']==1
    assert fake.restore('valuation-underwriting/runtime/states/V.json')==path.read_bytes()


def test_validation_view_restores_only_complete_packets_and_cannot_publish(environment):
    vault,fake=environment
    packet='valuation-underwriting/packets/'+'b'*64+'.json'
    paid='valuation-underwriting/local-runtime/paid/receipt.json'
    fake.publish({packet:b'complete original packet',paid:b'private paid receipt'})
    io.initialize(vault,storage=fake,prefixes=['valuation-underwriting/packets/'])
    assert (vault/packet).read_bytes()==b'complete original packet'
    assert not (vault/paid).exists()
    with pytest.raises(storage.StorageError,match='cannot publish'):
        io.publish_paths(vault,{packet:vault/packet},storage=fake)


def test_sparse_scoped_view_restores_only_paths_the_checkout_selects(environment):
    vault,fake=environment
    excluded='dashboard-private/company-source-backfill-v2/manifest.json'
    kept='dashboard-private/manifest.json'
    extra='superinvestor-letters/drive_import_manifest.json'
    fake.publish({'baseline.json':b'{"current":true}\n',excluded:b'{"parts":[]}',kept:b'{"current":1}',extra:b'{"current":2}',
                  'superinvestor-letters/letters_index.json':b'{}'})
    subprocess.run(['git','-C',str(vault),'sparse-checkout','set','--no-cone','--stdin'],check=True,capture_output=True,
                   input='/baseline.json\n/dashboard-private/manifest.json\n/superinvestor-letters/drive_import_manifest.json\n',text=True)
    result=io.initialize(vault,storage=fake,sparse_scoped=True)
    assert result['control_files_restored']==3 and result['catalog_records_outside_checkout']==2
    assert (vault/'baseline.json').read_bytes()==b'{"current":true}\n'
    assert (vault/kept).read_bytes()==b'{"current":1}' and (vault/extra).read_bytes()==b'{"current":2}'
    assert not (vault/'dashboard-private/company-source-backfill-v2').exists()
    assert not (vault/'superinvestor-letters/letters_index.json').exists()


def test_sparse_scope_keeps_every_record_in_a_full_checkout(environment):
    vault,fake=environment
    fake.publish({'baseline.json':b'{"current":true}\n','dashboard-private/investor-history/manifest.json':b'{}'})
    result=io.initialize(vault,storage=fake,sparse_scoped=True)
    assert result['control_files_restored']==2 and result['catalog_records_outside_checkout']==0
    assert (vault/'dashboard-private/investor-history/manifest.json').is_file()


def test_validation_view_rejects_unsafe_prefix(environment):
    vault,fake=environment
    with pytest.raises(storage.StorageError,match='Unsafe'):
        io.initialize(vault,storage=fake,prefixes=['../outside/'])


def test_strict_validation_reads_trusted_storage_before_replay():
    import yaml
    root=Path(__file__).resolve().parents[3]
    job=yaml.safe_load((root/'.github/workflows/underwriting-validation.yml').read_text())['jobs']['validate']
    assert 'CLOUDFLARE_API_TOKEN' in job['env']
    trusted=next(s for s in job['steps'] if s.get('name')=='Read trusted validators from main')
    assert '_system/config/private_storage.json' in trusted['with']['sparse-checkout']
    names=[s.get('name') for s in job['steps']]
    assert names.index('Restore named immutable packets from the private catalog')<names.index('Recompile every reviewed candidate from its exact frozen evidence')
    restore=next(s for s in job['steps'] if s.get('name')=='Restore named immutable packets from the private catalog')
    assert '--prefix valuation-underwriting/packets/' in restore['run']

def test_investor_checkpoint_published_only_to_private_storage_restores(environment,monkeypatch,tmp_path):
    import shutil
    import investor_history as history
    import investor_history_checkpoint as checkpoint
    vault,fake=environment
    cache=tmp_path/'cache'
    history.connect(cache/'archive.sqlite').close()
    history.write_json(cache/'universe.json',{'revision':'published after activation'})
    source=vault/'dashboard-private/investor-history'
    manifest=checkpoint.pack(cache,source)
    fake.publish({p.relative_to(vault).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file()})
    shutil.rmtree(source)
    io.initialize(vault,storage=fake)
    assert (source/'manifest.json').is_file() and not (source/'objects').exists()
    (source/manifest['identity']/'manifest.json').unlink()
    monkeypatch.setattr(io,'enabled',lambda:True)
    monkeypatch.setattr(io,'_LAZY_STORAGE',fake)
    subprocess.run(['git','-C',str(vault),'sparse-checkout','set','--no-cone','--stdin'],input='/*\n',text=True,check=True,capture_output=True)
    selected=checkpoint.materialize(source,identity=manifest['identity'])
    assert selected['sparse'] is True and selected['parts']==len(manifest['parts'])
    assert checkpoint.restore(source,tmp_path/'restored',identity=manifest['identity'])
    assert json.loads((tmp_path/'restored/universe.json').read_text())=={'revision':'published after activation'}
    assert checkpoint.restore(source,tmp_path/'latest')
    assert all((source/part['name']).is_file() for part in manifest['parts'])


def test_investor_checkpoint_outside_private_view_still_requires_local_parts(tmp_path,monkeypatch):
    import investor_history as history
    import investor_history_checkpoint as checkpoint
    monkeypatch.setattr(io,'enabled',lambda:True)
    cache=tmp_path/'cache'
    history.connect(cache/'archive.sqlite').close()
    source=tmp_path/'vault/dashboard-private/investor-history'
    manifest=checkpoint.pack(cache,source)
    (source/manifest['parts'][0]['name']).unlink()
    with pytest.raises(FileNotFoundError):
        checkpoint.restore(source,tmp_path/'restored')


def test_read_only_snapshot_view_skips_unrelated_control_and_restores_full_object(environment,monkeypatch):
    vault,fake=environment;relative='dashboard-private/objects/'+'a'*64
    fake.publish({'valuation-underwriting/local-runtime/states/V.json':b'paid state',relative:b'complete snapshot\r\n'})
    result=io.initialize(vault,storage=fake,snapshot_only=True)
    assert result['control_files_restored']==0 and not (vault/'valuation-underwriting').exists()
    monkeypatch.setattr(io,'enabled',lambda:True)
    assert io.materialize(vault,relative,storage=fake).read_bytes()==b'complete snapshot\r\n'
    assert json.loads((vault/io.MARKER).read_text())['read_only'] is True
    with pytest.raises(storage.StorageError,match='cannot publish'):io.publish_paths(vault,{},storage=fake)
