"""Exercise the backfill worker's checkout -> pack -> publication disk peak."""
import errno
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import zipfile

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from company_source_cache import pack, restore
from push_company_source_parts import publish
from vault_source_archive_sparse import part_patterns

ROOT = Path(__file__).resolve().parents[3]
PREFIX = 'dashboard-private/company-source-backfill-v2'


@pytest.fixture(autouse=True)
def legacy_archive_transport_fixture(monkeypatch):
    # Retain explicit coverage for the read-only legacy transport protocol.
    # The activated object-store path is covered by the owned-view suite.
    import private_storage
    monkeypatch.setattr(private_storage, 'enabled', lambda *a, **k: False)


def git(root, *args, input=None):
    return subprocess.check_output(['git', '-C', str(root), '-c', 'core.autocrlf=false',
        *args], input=input, stderr=subprocess.STDOUT).decode().strip()


def test_worker_packing_does_not_materialize_historical_archive_versions(tmp_path, monkeypatch):
    remote, seed, worker = (tmp_path / n for n in ('remote.git', 'seed', 'worker'))
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    subprocess.run(['git', 'clone', str(remote), str(seed)], check=True, capture_output=True)
    git(seed, 'checkout', '-b', 'main')
    git(seed, 'config', 'user.name', 'Fixture')
    git(seed, 'config', 'user.email', 'fixture@example.invalid')
    source = tmp_path / 'original'
    (source / 'git').mkdir(parents=True)
    original = random.Random(14).randbytes(100_000)
    (source / 'git/aa.json').write_bytes(original)
    archive = seed / PREFIX
    pack(source, archive)
    historical = []
    for i in range(6):
        raw = random.Random(i).randbytes(100_000)
        name = hashlib.sha256(raw).hexdigest() + '.zip'
        (archive / name).write_bytes(raw)
        historical.append(name)
    (seed / 'other-collection.txt').write_text('Keep other vault collections')
    git(seed, 'add', '.')
    git(seed, 'commit', '-m', 'Current snapshot and retained historical parts')
    git(seed, 'push', 'origin', 'HEAD:main')
    subprocess.run(['git', 'clone', '--no-checkout', str(remote), str(worker)], check=True, capture_output=True)
    git(worker, 'checkout', 'main')
    workflow = yaml.safe_load((ROOT / '.github/workflows/company-source-backfill.yml').read_text())
    checkout = next(s for s in workflow['jobs']['backfill']['steps']
                    if s.get('uses') == './.github/actions/checkout-vault')['with']
    patterns = checkout['extra-paths']
    git(worker, 'sparse-checkout', 'set', '--no-cone', '--stdin', input=patterns.encode())
    if checkout.get('source-archive-current') == 'true':
        patterns = '\n'.join(part_patterns(json.loads((worker / PREFIX / 'manifest.json').read_text())))
        git(worker, 'sparse-checkout', 'add', '--stdin', input=patterns.encode())
    cache = tmp_path / 'cache'
    restore(worker / PREFIX, cache)
    # A genuinely changed bucket needs a new immutable output while its input
    # and checked-out source versions still coexist. Count those actual bytes.
    (cache / 'git/ab.json').write_bytes(random.Random(55).randbytes(100_000))
    capacity = 650_000
    original_write = zipfile.ZipFile.writestr

    def bounded_write(z, name, data, *args, **kwargs):
        used = sum(p.stat().st_size for root in (cache, worker / PREFIX)
                   for p in root.rglob('*') if p.is_file())
        if used + len(data) > capacity:
            raise OSError(errno.ENOSPC, 'No space left on device during archive packing')
        return original_write(z, name, data, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(zipfile.ZipFile, 'writestr', bounded_write)
        pack(cache, worker / PREFIX, release_packed_inputs=True)
    assert all(not (worker / PREFIX / n).exists() for n in historical)
    assert publish(worker)['parts_uploaded'] == 1
    # Use the workflow's real staging arguments: skipped historical paths must
    # remain in the index, and new parts must be tracked before the rebase.
    commit = next(s for s in workflow['jobs']['backfill']['steps']
                  if s.get('uses') == './.github/actions/commit-vault')
    import shlex
    git(worker, 'add', *shlex.split(commit['with']['git_add']))
    git(worker, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-m', 'Advance current manifest')
    git(worker, 'fetch', 'origin', 'main')
    git(worker, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'rebase', 'origin/main')
    git(worker, 'push', 'origin', 'HEAD:main')
    names = set(git(remote, 'ls-tree', '--name-only', 'main:' + PREFIX).splitlines())
    assert set(historical) <= names
    assert git(remote, 'show', 'main:other-collection.txt') == 'Keep other vault collections'
    # Rebase correctly re-applies the old sparse selection. The next consumer
    # selects the newly published manifest, which now also references ab.json.
    selected = part_patterns(json.loads((worker / PREFIX / 'manifest.json').read_text()))
    git(worker, 'sparse-checkout', 'add', '--stdin', input='\n'.join(selected).encode())
    final = tmp_path / 'restored'
    restore(worker / PREFIX, final)
    assert (final / 'git/aa.json').read_bytes() == original
    assert (final / 'git/ab.json').read_bytes() == random.Random(55).randbytes(100_000)


@pytest.mark.parametrize('manifest', [None, {}, {'parts': {}}, {'parts': [None]},
    {'parts': [{'file': '../outside.zip', 'sha256': 'a' * 64}]},
    {'parts': [{'file': 'b' * 64 + '.zip', 'sha256': 'a' * 64}]},
    {'parts': [{'file': '*' + '.zip', 'sha256': '*'}]},
    {'parts': [{'file': 'a' * 64 + '.zip', 'sha256': 'a' * 64}] * 2}])
def test_invalid_manifest_cannot_expand_sparse_checkout(manifest):
    with pytest.raises(ValueError):
        part_patterns(manifest)


def test_source_manifest_patterns_are_exact_and_keep_the_existing_selection():
    assert part_patterns({'parts': []}) == []
    assert part_patterns({'parts': [{'file': 'a' * 64 + '.zip', 'sha256': 'a' * 64}]}) == [
        '/' + PREFIX + '/' + 'a' * 64 + '.zip']
    action = yaml.safe_load((ROOT / '.github/actions/checkout-vault/action.yml').read_text())
    step = next(s for s in action['runs']['steps'] if s.get('name') == 'Materialize current source archive parts')
    assert 'sparse-checkout add' in step['run']
    assert 'sparse-checkout set' not in step['run']
    assert "inputs.source-archive-current == 'true'" in step['if']
    assert "inputs.include-source-archive == 'true'" in step['if']
