"""Release reproducible company-build inputs after authenticated assets are staged."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

ARCHIVE = 'dashboard-private/company-source-backfill-v2'
CACHE = 'dashboard-private/company-research-cache'


def _catalog_current(vault: Path, relatives: list[str], storage=None) -> set[str]:
    """Changed tracked paths whose exact bytes are the private catalog's record.

    The catalog view overlays published control records, such as the source
    archive manifest, on the pinned legacy commit; those bytes are preserved.
    """
    if not (vault / '.private-storage-view.json').is_file():
        return set()
    from private_storage import PrivateStorage
    from private_storage_io import path_in, view
    storage = storage or PrivateStorage()
    records = view(vault, storage)
    current = set()
    for relative in relatives:
        path = path_in(vault, relative)
        entry = storage.lookup_entry(relative, records)
        if not entry or not path.is_file():
            continue
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == entry.get('sha256'):
                current.add(relative)
    return current


def _restored_from_archive(vault: Path, relatives: list[str]) -> set[str]:
    """Changed cache files identical to what the verified source archive restores.

    Restoring the archive named by the current manifest rewrites cache files
    the pinned legacy commit still holds at older bytes; later parts win.
    """
    archive, cache = vault / ARCHIVE, CACHE + '/'
    wanted = {relative[len(cache):]: relative for relative in relatives if relative.startswith(cache)}
    manifest = archive / 'manifest.json'
    if not wanted or not manifest.is_file():
        return set()
    source = {}
    for part in json.loads(manifest.read_text(encoding='utf-8')).get('parts', []):
        path = archive / part['file']
        if path.parent != archive or path.is_symlink() or not path.is_file():
            continue
        with zipfile.ZipFile(path) as bundle:
            for name in set(bundle.namelist()) & set(wanted):
                source[name] = (path, part['sha256'])
    verified, current = {}, set()
    for name, (path, identity) in source.items():
        if path not in verified:
            with path.open('rb') as stream:
                verified[path] = hashlib.file_digest(stream, 'sha256').hexdigest() == identity
        target = vault / wanted[name]
        if not verified[path] or target.is_symlink() or not target.is_file():
            continue
        with zipfile.ZipFile(path) as bundle:
            if bundle.read(name) == target.read_bytes():
                current.add(wanted[name])
    return current


def release(workspace: Path, vault: Path, *, storage=None) -> dict:
    workspace, vault = workspace.resolve(), vault.resolve()
    if vault != (workspace / '_external/research-vault').resolve() or not vault.is_relative_to(workspace):
        raise ValueError('Only the deployment checkout may release build inputs')
    manifest = workspace / '_cf_project/site/data/company-research/manifest.json'
    if not manifest.is_file() or not json.loads(manifest.read_text(encoding='utf-8')).get('documents'):
        raise ValueError('Stage the complete authenticated company library first')
    def git(*args, **kwargs):
        return subprocess.run(['git', '-c', 'submodule.recurse=false', '-C', str(vault), *args],
                              capture_output=True, check=True, **kwargs)
    git('rev-parse', '--git-dir')
    omitted = (ARCHIVE, CACHE)
    # Compare complete tracked target bytes to their preserved commit. Hardlink
    # stat changes are harmless; staged or unstaged target changes must stay.
    # New private control overlays outside these two targets are never removed.
    # Inside them, only bytes the private catalog already holds may differ.
    changed = [p for p in git('diff', '--name-only', '-z', 'HEAD', '--', *omitted).stdout.decode().split('\0') if p]
    unpublished = sorted(set(changed) - _catalog_current(vault, changed, storage)) if changed else []
    if unpublished and ARCHIVE + '/manifest.json' not in unpublished:
        unpublished = sorted(set(unpublished) - _restored_from_archive(vault, unpublished))
    if unpublished:
        raise ValueError(f'Unpublished build input changes must stay ({len(unpublished)}): ' + ', '.join(unpublished[:5]))
    targets = [vault / relative for relative in omitted]
    if any(path.resolve() != path or not path.resolve().is_relative_to(vault) for path in targets):
        raise ValueError('Build cache escapes its deployment checkout')
    before = shutil.disk_usage(workspace).free
    sparse = subprocess.run(['git', '-C', str(vault), 'config', '--bool', 'core.sparseCheckout'],
                            capture_output=True, text=True, check=False).stdout.strip() == 'true'
    if sparse:
        name = Path(git('rev-parse', '--git-path', 'info/sparse-checkout').stdout.decode().strip())
        patterns = (name if name.is_absolute() else vault / name).read_text().splitlines()
    else:
        patterns = ['/*']
    patterns.extend('!/' + relative + '/' for relative in omitted)
    # Omit tracked inputs instead of recording deletions. Their immutable bytes
    # remain in the private Git objects; no remote repository is changed.
    git('sparse-checkout', 'set', '--no-cone', '--stdin', input=('\n'.join(patterns)+'\n').encode())
    for target in targets:
        if target.exists():
            # Restoring the compressed cache also creates untracked derived
            # files, which sparse checkout deliberately leaves behind.
            shutil.rmtree(target)
    return {'released_build_inputs': list(omitted),
            'free_bytes_before': before, 'free_bytes_after': shutil.disk_usage(workspace).free}


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('This cleanup is only for an ephemeral GitHub deployment workspace')
    print(json.dumps(release(Path(os.environ['GITHUB_WORKSPACE']), Path(os.environ['RESEARCH_VAULT_ROOT']))))
