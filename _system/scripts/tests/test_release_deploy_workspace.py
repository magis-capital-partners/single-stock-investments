import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_deploy_workspace import release


def git(vault, *args):
    return subprocess.check_output(['git', '-C', str(vault), *args])


def fixture(tmp_path):
    vault = tmp_path / '_external/research-vault'
    vault.mkdir(parents=True)
    git(vault, 'init', '-q')
    git(vault, 'config', 'user.email', 'test@example.test')
    git(vault, 'config', 'user.name', 'Test')
    files = {'dashboard-private/company-source-backfill-v2/part.zip': b'original compressed evidence',
             'dashboard-private/company-research-cache/published.json': b'complete source text',
             'dashboard-private/investor-history/part.bin': b'complete holdings checkpoint',
             'superinvestor-letters/insights.json': b'complete letters',
             'valuation-underwriting/packets/a.json': b'frozen valuation evidence'}
    for relative, raw in files.items():
        path = vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    git(vault, 'add', '.')
    git(vault, 'commit', '-qm', 'Immutable source inputs')
    site = tmp_path / '_cf_project/site/data/company-research'
    site.mkdir(parents=True)
    (site / 'manifest.json').write_text(json.dumps({'documents': 1}))
    os.link(vault / 'dashboard-private/company-research-cache/published.json', site / 'published.json')
    (vault / 'dashboard-private/company-research-cache/derived.tmp').write_text('reproducible extraction')
    return vault, site, files


@pytest.mark.parametrize('sparse', [False, True])
def test_release_keeps_staged_hardlinks_and_all_original_git_objects(tmp_path, sparse):
    vault, site, files = fixture(tmp_path)
    if sparse:
        git(vault, 'sparse-checkout', 'set', '--no-cone', '/*')
    result = release(tmp_path, vault)
    assert result['free_bytes_after'] > 0 and result['free_bytes_before'] > 0
    assert (site / 'published.json').read_bytes() == b'complete source text'
    assert not (vault / 'dashboard-private/company-source-backfill-v2').exists()
    assert not (vault / 'dashboard-private/company-research-cache').exists()
    for relative, raw in files.items():
        assert git(vault, 'show', 'HEAD:' + relative) == raw
        if 'company-' not in relative:
            assert (vault / relative).read_bytes() == raw
    assert git(vault, 'status', '--porcelain').strip() == b''


def test_release_refuses_a_vault_outside_the_deployment_checkout(tmp_path):
    outside = tmp_path / 'private-audit'
    outside.mkdir()
    evidence = outside / 'original.json'
    evidence.write_text('retain')
    with pytest.raises(ValueError, match='deployment checkout'):
        release(tmp_path, outside)
    assert evidence.read_text() == 'retain'


def test_release_requires_successfully_staged_company_documents(tmp_path):
    vault, site, files = fixture(tmp_path)
    (site / 'manifest.json').write_text(json.dumps({'documents': 0}))
    with pytest.raises(ValueError, match='Stage the complete'):
        release(tmp_path, vault)
    for relative, raw in files.items():
        assert (vault / relative).read_bytes() == raw
