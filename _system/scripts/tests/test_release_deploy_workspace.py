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
    source = vault / 'dashboard-private/company-research-cache/published.json'
    changed_stat = source.stat()
    os.utime(source, ns=(changed_stat.st_atime_ns, changed_stat.st_mtime_ns + 2_000_000_000))
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


def test_release_refuses_modified_tracked_inputs_before_removing_any_cache(tmp_path):
    vault, site, files = fixture(tmp_path)
    source = vault / 'dashboard-private/company-research-cache/published.json'
    source.write_bytes(b'uncommitted source change must survive')
    with pytest.raises(ValueError, match='Unpublished'):
        release(tmp_path, vault)
    assert source.read_bytes() == b'uncommitted source change must survive'
    assert (vault / 'dashboard-private/company-source-backfill-v2/part.zip').exists()


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


@pytest.mark.parametrize("staged", [False, True])
def test_release_preserves_unrelated_private_overlay_changes(tmp_path, staged):
    vault, site, files = fixture(tmp_path)
    outside=vault / "valuation-underwriting/packets/a.json"
    original=b"newer verified private overlay must survive"
    outside.write_bytes(original)
    if staged:git(vault,"add","valuation-underwriting/packets/a.json")
    release(tmp_path,vault)
    assert outside.read_bytes()==original
    assert (site/"published.json").read_bytes()==b"complete source text"
    assert not (vault/"dashboard-private/company-source-backfill-v2").exists()
    assert git(vault,"show","HEAD:valuation-underwriting/packets/a.json")==files["valuation-underwriting/packets/a.json"]


def test_release_refuses_staged_changed_target_before_any_removal(tmp_path):
    vault, site, files=fixture(tmp_path)
    source=vault/"dashboard-private/company-source-backfill-v2/part.zip"
    source.write_bytes(b"new unique archive bytes")
    git(vault,"add","dashboard-private/company-source-backfill-v2/part.zip")
    with pytest.raises(ValueError, match='Unpublished'):release(tmp_path,vault)
    assert source.read_bytes()==b"new unique archive bytes"
    assert (vault/"dashboard-private/company-research-cache").exists()


def catalog_view(tmp_path, monkeypatch, vault, records):
    import private_storage as storage
    import private_storage_io as io
    from tests.test_private_storage_io import Objects, VersionCatalog
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_WORKSPACE', str(tmp_path))
    fake = storage.PrivateStorage(config={'catalog_repository_id': 123}, objects=Objects(), catalog=VersionCatalog())
    fake.publish(records)
    io.initialize(vault, storage=fake)
    return fake


def test_release_accepts_targets_whose_bytes_are_the_published_catalog_record(tmp_path, monkeypatch):
    vault, site, files = fixture(tmp_path)
    manifest = 'dashboard-private/company-source-backfill-v2/manifest.json'
    git(vault, 'add', '-A'); git(vault, 'commit', '-qm', 'tracked derived')
    (vault / manifest).write_bytes(b'{"parts":["legacy"]}'); git(vault, 'add', manifest); git(vault, 'commit', '-qm', 'legacy manifest')
    fake = catalog_view(tmp_path, monkeypatch, vault, {manifest: b'{"parts":["current"]}'})
    assert (vault / manifest).read_bytes() == b'{"parts":["current"]}'
    release(tmp_path, vault, storage=fake)
    assert not (vault / 'dashboard-private/company-source-backfill-v2').exists()
    assert git(vault, 'show', 'HEAD:' + manifest) == b'{"parts":["legacy"]}'


@pytest.mark.parametrize('change', ['different', 'deleted', 'no-view'])
def test_release_refuses_target_changes_the_catalog_does_not_hold(tmp_path, monkeypatch, change):
    vault, site, files = fixture(tmp_path)
    source = vault / 'dashboard-private/company-research-cache/published.json'
    fake = None
    if change != 'no-view':
        fake = catalog_view(tmp_path, monkeypatch, vault, {'dashboard-private/company-research-cache/published.json': b'complete source text'})
    if change == 'deleted':
        source.unlink()
    else:
        source.write_bytes(b'unpublished local edit')
    with pytest.raises(ValueError, match='Unpublished'):
        release(tmp_path, vault, storage=fake)
    assert (vault / 'dashboard-private/company-source-backfill-v2/part.zip').exists()
    if change != 'deleted':
        assert source.read_bytes() == b'unpublished local edit'


def archive_fixture(tmp_path, monkeypatch, *, member, corrupt=False):
    import hashlib, io as bytes_io, zipfile
    vault, site, files = fixture(tmp_path)
    archive = vault / 'dashboard-private/company-source-backfill-v2'
    buffer = bytes_io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as bundle:
        bundle.writestr('published.json', member)
    raw = buffer.getvalue()
    name = hashlib.sha256(raw).hexdigest() + '.zip'
    (archive / name).write_bytes(raw + (b'tampered' if corrupt else b''))
    git(vault, 'add', '-A'); git(vault, 'commit', '-qm', 'legacy archive')
    manifest = 'dashboard-private/company-source-backfill-v2/manifest.json'
    fake = catalog_view(tmp_path, monkeypatch, vault,
                        {manifest: json.dumps({'parts': [{'file': name, 'sha256': hashlib.sha256(raw).hexdigest()}]}).encode()})
    return vault, fake


def test_release_accepts_cache_files_restored_from_the_verified_current_archive(tmp_path, monkeypatch):
    vault, fake = archive_fixture(tmp_path, monkeypatch, member=b'newer complete source text')
    cache = vault / 'dashboard-private/company-research-cache/published.json'
    cache.unlink(); cache.write_bytes(b'newer complete source text')
    release(tmp_path, vault, storage=fake)
    assert not (vault / 'dashboard-private/company-research-cache').exists()


@pytest.mark.parametrize('corrupt', [False, True])
def test_release_refuses_cache_bytes_the_verified_archive_does_not_restore(tmp_path, monkeypatch, corrupt):
    vault, fake = archive_fixture(tmp_path, monkeypatch, member=b'newer complete source text', corrupt=corrupt)
    cache = vault / 'dashboard-private/company-research-cache/published.json'
    cache.unlink()
    cache.write_bytes(b'newer complete source text' if corrupt else b'locally edited source text')
    with pytest.raises(ValueError, match='Unpublished'):
        release(tmp_path, vault, storage=fake)
    assert cache.exists()
