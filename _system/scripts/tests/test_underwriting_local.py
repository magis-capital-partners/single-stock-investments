"""Local runtime boundaries and safe publication of private handoffs."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_local import local_lock, publish_runtime


def test_local_runtime_publishes_only_its_owned_private_json(tmp_path):
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
    git('add','.')
    git('commit','-q','-m','Baseline')
    git('init','-q','--bare',str(remote))
    git('remote','add','origin',str(remote))
    git('push','-q','origin','main')
    own=vault/'valuation-underwriting/local-runtime/states/TEST.json'
    own.parent.mkdir(parents=True)
    own.write_text('{"status":"approved_for_build"}')
    (vault/'auth.json').write_text('{"must_not_publish":true}')
    assert publish_runtime(vault,home)
    changed=git('diff','--name-only','HEAD','origin/main').splitlines()
    assert changed == ['valuation-underwriting/local-runtime/states/TEST.json']
    assert git('show','origin/main:valuation-underwriting/runtime/remote-job.json') == '{"preserve":true}'
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
