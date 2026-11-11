import json,subprocess,sys,hashlib,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import migrate_private_storage as migration
import private_storage as store
from test_private_storage import Objects,MemoryCatalog

def fixture(tmp_path):
    repo=tmp_path/'staging.git';repo.mkdir()
    def git(*args):return subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=True).stdout
    git('init');git('config','core.autocrlf','false');git('config','user.name','Test');git('config','user.email','test@example.invalid')
    for i,raw in enumerate([b'alpha\r\n',b'\0\xffbinary',b'duplicate',b'duplicate']):
        (repo/('file'+str(i))).write_bytes(raw)
    git('add','.');git('commit','-m','Complete original');pin=git('rev-parse','HEAD').decode().strip()
    git('remote','add','origin','https://github.com/magis-capital-partners/research-vault.git')
    (repo/'migration-owner.json').write_text(json.dumps({'purpose':'verified-private-legacy-migration','source_commit':pin}))
    storage=store.PrivateStorage(config={'legacy_pin':pin,'legacy_repository':'magis-capital-partners/research-vault'},objects=Objects(),catalog=MemoryCatalog())
    return repo,pin,storage

def test_real_git_blob_inventory_and_complete_binary_reader(tmp_path):
    repo,pin,s=fixture(tmp_path);rows,identity=migration.inventory(repo,pin)
    assert len(rows)==4 and len(identity)==64
    values=dict(migration.read_blobs(repo,list(dict.fromkeys(r['git_blob'] for r in rows))))
    for row in rows:assert values[row['git_blob']]==(repo/row['path']).read_bytes()

def test_resumable_migration_retains_every_path_and_git_identity(tmp_path,monkeypatch):
    repo,pin,s=fixture(tmp_path);real=migration.run_git
    def run(directory,*args,**kwargs):
        if 'fetch' in args:return type('Result',(),{'stdout':b''})()
        return real(directory,*args,**kwargs)
    monkeypatch.setattr(migration,'run_git',run)
    out=tmp_path/'proof';first=migration.migrate(repo,out,storage=s,batch_files=1,max_batches=1)
    assert first['complete'] is False
    final=migration.migrate(repo,out,storage=s,batch_files=1)
    assert final['complete'] is True and final['files_verified']==4
    s.config['legacy_archive_manifest']=final['manifest_path']
    for i in range(4):assert s.restore('file'+str(i))==(repo/('file'+str(i))).read_bytes()
    rows=json.loads((out/'migration-journal.json').read_text())['batches'];assert sum(r['files'] for r in rows)==4
    assert (repo/'file0').exists()

def test_migration_refuses_unowned_or_relabelled_source(tmp_path):
    repo,pin,s=fixture(tmp_path);(repo/'migration-owner.json').write_text('{}')
    with pytest.raises(store.StorageError,match='Owned'):migration.migrate(repo,tmp_path/'proof',storage=s)

def test_missing_or_truncated_git_blob_is_held(tmp_path):
    repo,pin,s=fixture(tmp_path)
    with pytest.raises(store.StorageError,match='missing'):list(migration.read_blobs(repo,['0'*40]))

def test_pinned_inventory_never_accepts_branch_name(tmp_path):
    repo,pin,s=fixture(tmp_path)
    with pytest.raises(store.StorageError):migration.inventory(repo,'main')

def test_git_reader_handles_more_output_than_pipe_capacity(tmp_path):
    repo,pin,s=fixture(tmp_path);raw=b'full binary'+bytes(range(256))*200;(repo/'large').write_bytes(raw)
    subprocess.run(['git','-C',str(repo),'add','large'],check=True,capture_output=True)
    identity=subprocess.run(['git','-C',str(repo),'hash-object','large'],check=True,capture_output=True).stdout.decode().strip()
    count=0
    for actual,data in migration.read_blobs(repo,[identity]*128):
        assert actual==identity and data==raw;count+=1
    assert count==128

def test_existing_repository_is_never_repurposed(tmp_path):
    repository=tmp_path/'ordinary';repository.mkdir();(repository/'precious').write_bytes(b'unpublished')
    with pytest.raises(store.StorageError):migration.initialize_repository(repository,{'legacy_pin':'a'*40,'legacy_repository':'magis-capital-partners/research-vault'})
    assert (repository/'precious').read_bytes()==b'unpublished'

def test_hosted_migration_has_no_model_or_automatic_trigger():
    workflow=(Path(__file__).resolve().parents[3]/'.github/workflows/private-storage.yml').read_text(encoding='utf-8')
    assert 'private-storage-migrate' in workflow and 'timeout-minutes: 100' in workflow
    assert 'schedule:' not in workflow and 'workflow_dispatch:' not in workflow
    assert 'migrate_private_storage.py' in workflow and '--release-staging-packs' in workflow
    assert 'ANTHROPIC_API_KEY' not in workflow and 'OPENAI_API_KEY' not in workflow


def test_large_logical_batch_uses_bounded_exact_source_fetches(tmp_path, monkeypatch):
    repo, pin, storage = fixture(tmp_path)
    for number in range(20):
        (repo / ('extra' + str(number))).write_bytes(('complete source ' + str(number)).encode())
    subprocess.run(['git', '-C', str(repo), 'add', '--', *('extra' + str(i) for i in range(20))], capture_output=True, check=True)
    subprocess.run(['git', '-C', str(repo), 'commit', '-m', 'Complete additional originals'], capture_output=True, check=True)
    pin = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD']).decode().strip()
    storage.config['legacy_pin'] = pin
    (repo / 'migration-owner.json').write_text(json.dumps({'purpose': 'verified-private-legacy-migration', 'source_commit': pin}))
    rows, _ = migration.inventory(repo, pin)
    expected = list(dict.fromkeys(row['git_blob'] for row in rows))
    real = migration.run_git
    fetched = []
    def download(directory, *args, **kwargs):
        if 'fetch' in args:
            wants = list(args[args.index('origin') + 1:])
            if len(wants) > 16:
                raise subprocess.TimeoutExpired(['git', 'fetch'], 180)
            fetched.extend(wants)
            return type('Result', (), {'stdout': b''})()
        return real(directory, *args, **kwargs)
    monkeypatch.setattr(migration, 'run_git', download)
    result = migration.migrate(repo, tmp_path / 'proof', storage=storage, batch_files=256)
    assert result['complete'] and result['files_verified'] == len(rows)
    assert fetched == expected
    storage.config['legacy_archive_manifest'] = result['manifest_path']
    for row in rows:
        assert storage.restore(row['path']) == (repo / row['path']).read_bytes()


def test_source_fetch_failure_preserves_prior_verified_checkpoint(tmp_path, monkeypatch):
    repo, pin, storage = fixture(tmp_path)
    real = migration.run_git
    def download(directory, *args, **kwargs):
        if 'fetch' in args:
            return type('Result', (), {'stdout': b''})()
        return real(directory, *args, **kwargs)
    monkeypatch.setattr(migration, 'run_git', download)
    output = tmp_path / 'proof'
    assert not migration.migrate(repo, output, storage=storage, batch_files=1, max_batches=1)['complete']
    before_journal = (output / 'migration-journal.json').read_bytes()
    before_catalog = copy.deepcopy(storage.catalog.records)
    def unavailable(directory, *args, **kwargs):
        if 'fetch' in args:
            raise subprocess.TimeoutExpired(['git', 'fetch'], 180)
        return real(directory, *args, **kwargs)
    monkeypatch.setattr(migration, 'run_git', unavailable)
    with pytest.raises(subprocess.TimeoutExpired):
        migration.migrate(repo, output, storage=storage, batch_files=256)
    assert (output / 'migration-journal.json').read_bytes() == before_journal
    assert storage.catalog.records == before_catalog
    monkeypatch.setattr(migration, 'run_git', download)
    assert migration.migrate(repo, output, storage=storage, batch_files=256)['complete']
