"""Exercise native Git and PowerShell startup boundaries, without remote access."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_local import git, local_lock

BOOTSTRAP = Path(__file__).resolve().parents[1]/'underwriting_local.ps1'


@pytest.mark.parametrize('key', ['submodule.recurse', 'fetch.recurseSubmodules'])
def test_runtime_git_overrides_recursive_settings_only_for_its_own_command(tmp_path, key):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', key, 'true'], check=True)
    assert git(tmp_path, 'config', '--type=bool', '--get', key).strip() == b'false'
    assert subprocess.check_output(['git', '-C', str(tmp_path), 'config', '--get', key]).strip() == b'true'


def test_powershell_uses_the_same_nonrecursive_git_contract(tmp_path):
    shell = shutil.which('pwsh')
    if not shell:
        pytest.skip('PowerShell is required for the Windows bootstrap contract')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'submodule.recurse', 'true'], check=True)
    body = re.search(r'^function Run-Git \{.*?^\}', BOOTSTRAP.read_text(encoding='utf-8'), re.M | re.S).group()
    directory = "'"+str(tmp_path).replace("'", "''")+"'"
    command = body+'\nRun-Git -C '+directory+' config --type=bool --get submodule.recurse'
    result = subprocess.run([shell, '-NoProfile', '-Command', command], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'false'


@pytest.mark.skipif(os.name != 'nt', reason='Windows file-sharing and byte-range locks')
def test_running_worker_prevents_any_source_update(tmp_path):
    shell = shutil.which('pwsh')
    if not shell:
        pytest.skip('PowerShell unavailable')
    owner = {'repository': 'magis-capital-partners/single-stock-investments', 'purpose': 'local-codex-underwriting'}
    (tmp_path/'runtime-owner.json').write_text(json.dumps(owner), encoding='utf-8')
    with local_lock(tmp_path):
        result = subprocess.run([shell, '-NoProfile', '-File', str(BOOTSTRAP), '-RuntimeHome', str(tmp_path), '-PrepareOnly'],
                                capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'already running' in result.stdout
    assert not (tmp_path/'source').exists()
