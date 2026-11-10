"""Owned checkout views and publication through the single private storage interface."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

from private_storage import (ROOT, PrivateStorage, StorageError, enabled, encoded_json,
                             relative_path, restore_file, run_git, sha, store_file)

MARKER = '.private-storage-view.json'
_LAZY_STORAGE = None
_VIEW_CACHE = {}


def owned(vault):
    vault = Path(vault).resolve()
    workspace = os.environ.get('GITHUB_WORKSPACE')
    if os.environ.get('GITHUB_ACTIONS') == 'true' and workspace:
        if vault == (Path(workspace).resolve()/'_external/research-vault').resolve():
            return vault
    owner = vault.parent/'runtime-owner.json'
    if vault.name == 'vault' and owner.is_file():
        value = json.loads(owner.read_text())
        if value.get('repository') == 'magis-capital-partners/single-stock-investments' and value.get('purpose') == 'local-codex-underwriting':
            return vault
    raise StorageError('Private storage changes require an owned CI or underwriting checkout')


def path_in(vault, relative):
    vault = Path(vault).resolve()
    relative_path(relative)
    path = vault/relative
    if path.is_symlink() or not path.resolve().is_relative_to(vault):
        raise StorageError('Private path escaped the owned checkout')
    return path


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output:
        output.write(raw)


def initialize(vault, *, storage=None, prefixes=()):
    vault = owned(vault)
    prefixes = tuple(relative_path(p.rstrip("/"))+"/" for p in prefixes)
    storage = storage or PrivateStorage()
    commit, records = storage.snapshot()
    restored = 0
    # Bulk objects and source parts are demand-loaded; control/current records
    # are small and must override only a verified, clean legacy checkout.
    for relative, entry in records.items():
        if prefixes and not any(relative.startswith(p) for p in prefixes):
            continue
        if relative.startswith(('recovery/', 'audit/', 'legacy/')) or '/objects/' in relative or relative.endswith('.zip'):
            continue
        path = path_in(vault, relative)
        if path.is_file() and sha(path.read_bytes()) == entry['sha256']:
            continue
        if path.exists():
            baseline = run_git(vault, 'show', 'HEAD:'+relative, check=False)
            if baseline.returncode or baseline.stdout != path.read_bytes():
                raise StorageError('Refusing differing unpublished private bytes: '+relative)
        raw = storage.restore(relative, records=records)
        if path.exists():
            # The exact replaced baseline remains immutable in legacy Git.
            path.write_bytes(raw)
        else:
            write_new(path, raw)
        restored += 1
    marker = {'schema_version':'private-storage-view/1', 'catalog_commit':commit,
              'catalog_repository_id':storage.config['catalog_repository_id'],
              'read_only':bool(prefixes), 'materialized_prefixes':list(prefixes)}
    (vault/MARKER).write_bytes(encoded_json(marker))
    return {'catalog_commit':commit, 'control_files_restored':restored}


def view(vault, storage):
    vault = owned(vault)
    marker = json.loads((vault/MARKER).read_text())
    if marker.get('schema_version') != 'private-storage-view/1' or marker.get('catalog_repository_id') != storage.config['catalog_repository_id']:
        raise StorageError('Private checkout view identity changed')
    commit = marker.get('catalog_commit','')
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise StorageError('Invalid private checkout catalog revision')
    records = storage.catalog.read(commit)
    for relative, entry in marker.get("published_entries", {}).items():
        relative_path(relative)
        records[relative] = entry
    return records


def materialize(vault, relative, *, storage=None):
    vault = Path(vault).resolve()
    destination = path_in(vault, relative)
    if destination.is_file():
        return destination
    if not enabled() or not (vault/MARKER).is_file():
        return destination
    global _LAZY_STORAGE
    if storage is None:
        if _LAZY_STORAGE is None:
            _LAZY_STORAGE = PrivateStorage()
        storage = _LAZY_STORAGE
    cache_key = (str(vault), sha((vault/MARKER).read_bytes()))
    if cache_key not in _VIEW_CACHE:
        _VIEW_CACHE[cache_key] = view(vault, storage)
    records = _VIEW_CACHE[cache_key]
    entry = records.get(relative)
    if entry:
        destination.parent.mkdir(parents=True, exist_ok=True)
        restore_file(storage.objects, entry, destination)
    return destination


def selected_files(vault, pathspec):
    vault = owned(vault)
    arguments = shlex.split(pathspec)
    # Preserve Git pathspec/exclusion behavior without staging private bytes.
    options = [a for a in arguments if a.startswith('-')]
    if any(a not in ('-A','-f','--force','--all','--sparse','--') for a in options):
        raise StorageError('Unsupported private publication selection')
    patterns = [a for a in arguments if not a.startswith('-')]
    result = subprocess.run(['git','ls-files','--modified','--others',*([] if any(a in options for a in ('-f','--force')) else ['--exclude-standard']),'-z','--',*patterns],
                            cwd=vault, capture_output=True, check=True, timeout=180)
    staged = subprocess.run(['git','diff','--cached','--name-only','-z','--',*patterns],
                            cwd=vault, capture_output=True, check=True, timeout=180)
    names = {r.decode() for r in (result.stdout+staged.stdout).split(b'\0') if r}
    names.discard(MARKER)
    paths = {}
    for relative in sorted(names):
        path = path_in(vault, relative)
        if not path.is_file():
            raise StorageError('Private deletion requires a separately verified pruning manifest: '+relative)
        paths[relative] = path
    return paths


def publish_paths(vault, paths, *, storage=None):
    vault = owned(vault)
    storage = storage or PrivateStorage()
    if json.loads((vault/MARKER).read_text()).get("read_only"):
        raise StorageError("A packet-validation view cannot publish private files")
    expected = view(vault, storage)
    # Complete upload/read-back precedes the one atomic catalog update.
    updates = {}
    control = {}
    for relative, path in paths.items():
        path = path_in(vault, relative)
        prior = expected.get(relative)
        entry = store_file(storage.objects, path)
        if relative == 'valuation-underwriting/local-runtime/ledger.jsonl':
            from private_storage import merge_ledger
            raw = path.read_bytes()
            if prior:
                raw = merge_ledger(storage.restore(relative, records=expected), raw)
            control['control/admission-ledger.jsonl'] = raw
        if prior == entry:
            continue
        immutable = ('/objects/' in relative or '/packets/' in relative or '/handoffs/' in relative and '/latest/' not in relative
                     or relative.endswith('.zip'))
        if prior and immutable and prior['sha256'] != entry['sha256']:
            raise StorageError('An immutable private artifact cannot be replaced')
        if prior and relative.endswith('/ledger.jsonl'):
            from private_storage import merge_ledger, store_bytes
            old = storage.restore(relative, records=expected)
            merged = merge_ledger(old, path.read_bytes())
            entry = store_bytes(storage.objects, merged)
        updates[relative] = entry
    commit = storage.catalog.publish(updates, expected, **({"control_files":control} if control else {}))
    # Refresh the view revision only after successful publication. No checkout
    # or paid source bytes are rewritten by the publisher.
    marker = json.loads((vault/MARKER).read_text())
    marker.setdefault('published_entries', {}).update(updates)
    marker['last_published_commit'] = commit
    (vault/MARKER).write_bytes(encoded_json(marker))
    return {'catalog_commit':commit,'files_preserved':len(updates),'legacy_git_written':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['enabled','initialize','publish'])
    parser.add_argument('--vault',type=Path)
    parser.add_argument('--pathspec',default='-A')
    parser.add_argument('--prefix',action='append',default=[])
    args=parser.parse_args()
    if args.action == 'enabled':
        return 0 if enabled() else 1
    if not args.vault:
        parser.error('--vault required')
    result = initialize(args.vault, prefixes=args.prefix) if args.action == 'initialize' else publish_paths(args.vault,selected_files(args.vault,args.pathspec))
    print(json.dumps(result))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
