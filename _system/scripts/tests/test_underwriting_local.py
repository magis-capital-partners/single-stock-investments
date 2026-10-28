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
