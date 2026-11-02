"""Local runtime boundaries and safe publication of private handoffs."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_local import local_lock, publish_runtime


def test_slow_remote_ledger_probe_does_not_prevent_audit_import(tmp_path, monkeypatch):
    import underwriting_local as local
    vault = tmp_path / 'vault'
    (vault / '.git').mkdir(parents=True)
    name = 'valuation-underwriting/runtime/ledger.jsonl'
    ledger = b'{"run_id":"preserved-remote-charge"}\n'
    calls = []
    def git(directory, *args, **kwargs):
        calls.append(args)
        if args == ('remote', 'get-url', 'origin'):
            return ('https://github.com/' + local.VAULT + '.git\n').encode()
        if args[0] == 'ls-tree':
            return (name + '\n').encode()
        if args[0] == 'show':
            return ledger
        return b''
    def slow_probe(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 30)
    monkeypatch.setattr(local, 'git', git)
    monkeypatch.setattr(local.subprocess, 'run', slow_probe)
    assert local.clone_vault(tmp_path) == vault
    assert (vault / name).read_bytes() == ledger
    assert ('show', 'origin/main:' + name) in calls


def test_failed_remote_ledger_read_preserves_previous_charges(tmp_path, monkeypatch):
    import underwriting_local as local
    vault = tmp_path / 'vault'
    (vault / '.git').mkdir(parents=True)
    name = 'valuation-underwriting/runtime/ledger.jsonl'
    ledger = vault / name
    ledger.parent.mkdir(parents=True)
    ledger.write_bytes(b'{"run_id":"previous-charge"}\n')
    def git(directory, *args, **kwargs):
        if args[0] == 'remote':
            return ('https://github.com/' + local.VAULT + '.git\n').encode()
        if args[0] == 'ls-tree':
            return (name + '\n').encode()
        if args[0] == 'show':
            raise subprocess.TimeoutExpired(args, 180)
        return b''
    monkeypatch.setattr(local, 'git', git)
    monkeypatch.setattr(local.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0))
    with pytest.raises(subprocess.TimeoutExpired):
        local.clone_vault(tmp_path)
    assert ledger.read_bytes() == b'{"run_id":"previous-charge"}\n'


def test_local_run_publishes_private_proof_before_single_company_dispatch(tmp_path, monkeypatch):
    import underwriting_local as local
    import underwriting_codex
    monkeypatch.setenv('RESEARCH_VAULT_ROOT', str(tmp_path / 'vault'))
    monkeypatch.setenv('UNDERWRITING_ARCHIVE_ROOT', str(tmp_path / 'source'))
    (tmp_path / 'runtime-owner.json').write_text(json.dumps(
        {'repository': local.OPS, 'purpose': 'local-codex-underwriting'}))
    result = {'selected': ['V'], 'approved': ['V'], 'completed': [], 'blocked': []}
    batch_options, publication = {}, []
    monkeypatch.setattr(underwriting_codex, 'preflight', lambda: {})
    monkeypatch.setattr(local, 'clone_vault', lambda home: home / 'vault')
    monkeypatch.setattr(local, 'data_root', lambda *args: tmp_path)
    monkeypatch.setattr(local, 'stage_model', lambda *args: {'provider': 'codex-local'})
    def batch(*args, **kwargs):
        batch_options.update(kwargs)
        return result
    monkeypatch.setattr(local, 'run_batch', batch)
    monkeypatch.setattr(local, 'publish_runtime', lambda *args: publication.append('private-proof-pushed'))
    def dispatch(args, **kwargs):
        publication.append(json.loads(kwargs['input']))
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(local.subprocess, 'run', dispatch)
    assert local.run_once(tmp_path, tickers=['V'], launch=True) == result
    assert batch_options['limit'] == 1
    assert publication == ['private-proof-pushed', {
        'event_type': 'valuation-underwriting-run',
        'client_payload': {'tickers': 'V', 'limit': 1}}]


def test_local_runtime_publishes_only_its_owned_private_json(tmp_path,monkeypatch):
    import underwriting_local as local
    real_git=local.git
    index_updates=[]
    def tracked_git(*args,**kwargs):
        if 'update-index' in args:index_updates.append(args)
        return real_git(*args,**kwargs)
    monkeypatch.setattr(local,'git',tracked_git)
    vault,home,remote = tmp_path/'vault',tmp_path/'runtime',tmp_path/'remote.git'
    vault.mkdir()
    home.mkdir()
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=vault,stderr=subprocess.DEVNULL,text=True).strip()
    git('init','-q','-b','main')
    git('config','user.name','Fixture')
    git('config','user.email','fixture@example.test')
    untouched=vault/'valuation-underwriting/runtime/remote-job.json'
    untouched.parent.mkdir(parents=True)
    untouched.write_text('{"preserve":true}')
    ledger=vault/'valuation-underwriting/local-runtime/ledger.jsonl'
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"run_id":"remote-paid"}\n')
    newer=vault/'valuation-underwriting/local-runtime/states/NEWER.json'
    newer.parent.mkdir(parents=True)
    newer.write_text('{"last_attempt":"2026-10-30T22:00:00","status":"preserve newer"}')
    git('add','.')
    git('commit','-q','-m','Baseline')
    git('init','-q','--bare',str(remote))
    git('remote','add','origin',str(remote))
    git('push','-q','origin','main')
    own=vault/'valuation-underwriting/local-runtime/states/TEST.json'
    own.parent.mkdir(parents=True,exist_ok=True)
    own.write_text('{"status":"approved_for_build"}')
    ledger.write_text('{"run_id":"local-paid"}\n')
    newer.write_text('{"last_attempt":"2026-10-30T21:00:00","status":"older"}')
    (vault/'auth.json').write_text('{"must_not_publish":true}')
    assert publish_runtime(vault,home)
    changed=git('diff','--name-only','HEAD','origin/main').splitlines()
    assert changed == ['valuation-underwriting/local-runtime/ledger.jsonl','valuation-underwriting/local-runtime/states/TEST.json']
    assert git('show','origin/main:valuation-underwriting/runtime/remote-job.json') == '{"preserve":true}'
    assert json.loads(git('show','origin/main:valuation-underwriting/local-runtime/states/NEWER.json'))['status']=='preserve newer'
    assert {json.loads(line)['run_id'] for line in git('show','origin/main:valuation-underwriting/local-runtime/ledger.jsonl').splitlines()}=={'remote-paid','local-paid'}
    assert len(index_updates)==1
    assert not publish_runtime(vault,home)


def test_local_worker_lock_is_released_when_a_run_finishes(tmp_path):
    for _ in range(2):
        with local_lock(tmp_path/'runtime'):
            assert (tmp_path/'runtime/worker.lock').exists()


def test_isolated_data_uses_the_clean_source_archive_for_exact_accessions(tmp_path,monkeypatch):
    import underwriting_evidence as evidence
    source=tmp_path/'source'
    source.mkdir()
    monkeypatch.setenv('UNDERWRITING_ARCHIVE_ROOT',str(source))
    def read(args,**kw):
        assert kw['cwd'] == source
        return 'TEST/investor-documents/sec-edgar/10K_acc0000123456_26_000001.htm\n' if args[1]=='ls-tree' else b'Exact archived primary filing'
    monkeypatch.setattr(evidence.subprocess,'check_output',read)
    assert evidence.filing_bytes(tmp_path/'data','TEST','0000123456-26-000001',None,'https://issuer.test/filing') == b'Exact archived primary filing'
