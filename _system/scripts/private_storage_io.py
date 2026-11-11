"""Owned checkout views and publication through the single private storage interface."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
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


def _strict_json(raw):
    def pairs(rows):
        value={}
        for k,v in rows:
            if k in value:raise StorageError('Duplicate JSON key in preserved private bytes')
            value[k]=v
        return value
    def invalid(value):raise StorageError('Invalid nonfinite JSON in preserved private bytes')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def _retain_or_advance_private_bytes(path,relative,incoming):
    """Retain equivalent original bytes; real ledgers may only append verified remote rows."""
    original=path.read_bytes()
    if relative.endswith('/ledger.jsonl'):
        old=[_strict_json(line) for line in original.splitlines() if line.strip()]
        lines=[line for line in incoming.splitlines(keepends=True) if line.strip()]
        new=[_strict_json(line) for line in lines]
        if any(not isinstance(r,dict) for r in old+new):raise StorageError('Invalid real admission ledger')
        old_identity=[encoded_json(r) for r in old];new_identity=[encoded_json(r) for r in new]
        if new_identity[:len(old_identity)]!=old_identity:
            raise StorageError('Refusing divergent or older private ledger; original local bytes retained')
        if len(new)>len(old):
            with path.open('ab') as output:
                if original and not original.endswith((b'\n',b'\r')):output.write(b'\n')
                output.write(b''.join(lines[len(old):]));output.flush();os.fsync(output.fileno())
        return {'path':relative,'action':'append_verified_rows' if len(new)>len(old) else 'retain_original_serialization',
                'original_sha256':sha(original),'private_sha256':sha(incoming),'final_sha256':sha(path.read_bytes()),
                'original_rows':len(old),'final_rows':len(new),'original_raw_bytes_remain_exact_prefix':path.read_bytes().startswith(original)}
    if relative.endswith('.json'):
        try:equal=encoded_json(_strict_json(original))==encoded_json(_strict_json(incoming))
        except (ValueError,UnicodeError):equal=False
        if equal:
            return {'path':relative,'action':'retain_original_serialization','original_sha256':sha(original),
                    'private_sha256':sha(incoming),'final_sha256':sha(original),'typed_JSON_values_equal':True}
    return None


def _shared_build_control(relative):
    return relative.startswith('valuation-underwriting/runtime/') and relative != 'valuation-underwriting/runtime/ledger.jsonl'


def _local_author_view(vault):
    marker = Path(vault)/MARKER
    return marker.is_file() and json.loads(marker.read_text()).get('materialization_role') == 'local_author'


def selected_author_ticker(vault):
    marker = json.loads((Path(vault)/MARKER).read_text())
    ticker = marker.get('selected_ticker')
    if marker.get('materialization_role') != 'local_author' or not isinstance(ticker, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]*', ticker):
        raise StorageError('A local author view requires one selected ticker')
    return ticker


def _author_control_subject(relative):
    for prefix in ('valuation-underwriting/local-runtime/states/', 'valuation-underwriting/local-runtime/progress/', 'valuation-underwriting/local-runtime/cache/', 'valuation-underwriting/handoffs/latest/'):
        if relative.startswith(prefix):
            return relative[len(prefix):].split('/')[0].removesuffix('.json')
    return None


def _author_path_owned(vault, relative, ticker):
    path = path_in(vault, relative)
    if relative == 'valuation-underwriting/local-runtime/ledger.jsonl':
        return True  # All subjects' actual charges remain in the shared ledger.
    if relative == 'valuation-underwriting/local-runtime/batch.json':
        batch = _strict_json(path.read_bytes())
        return isinstance(batch, dict) and all(isinstance(batch.get(k) or [], list) and all(t == ticker for t in batch.get(k) or []) for k in ('selected', 'approved', 'completed'))
    subject = _author_control_subject(relative)
    if subject is not None:
        if subject != ticker:
            return False
        if not relative.startswith('valuation-underwriting/handoffs/latest/'):
            return True  # Retain even invalid paid responses under their real cache owner.
    if not relative.startswith(('valuation-underwriting/local-runtime/', 'valuation-underwriting/handoffs/')):
        return False
    value = _strict_json(path.read_bytes())
    return isinstance(value, dict) and value.get('ticker') == ticker


def author_publication_paths(vault, paths, ticker):
    if not isinstance(ticker, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]*', ticker):
        raise StorageError('A local author view requires one selected ticker')
    return {relative:path for relative,path in paths.items() if _author_path_owned(vault, relative, ticker)}


def initialize(vault, *, storage=None, prefixes=(), snapshot_only=False, materialization_role=None, selected_ticker=None):
    vault = owned(vault)
    if materialization_role not in (None, 'local_author'):
        raise StorageError('Unknown private materialization role')
    if materialization_role == 'local_author' and os.environ.get('GITHUB_ACTIONS') == 'true':
        raise StorageError('A local author view cannot be used by CI')
    if materialization_role == 'local_author':
        if not isinstance(selected_ticker, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]*', selected_ticker):
            raise StorageError('A local author view requires one selected ticker')
    elif selected_ticker is not None:
        raise StorageError('A selected ticker requires a local author view')
    prefixes = tuple(relative_path(p.rstrip("/"))+"/" for p in prefixes)
    storage = storage or PrivateStorage()
    commit, records = storage.snapshot()
    restored = 0
    preserved_serializations = []
    preserved_shared_build_controls = []
    preserved_unselected_author_controls = []
    # Bulk objects and source parts are demand-loaded; control/current records
    # are small and must override only a verified, clean legacy checkout.
    for relative, entry in records.items():
        if snapshot_only:
            continue
        if prefixes and not any(relative.startswith(p) for p in prefixes):
            continue
        if relative.startswith(('recovery/', 'audit/', 'legacy/')) or '/objects/' in relative or relative.endswith('.zip'):
            continue
        path = path_in(vault, relative)
        if materialization_role == 'local_author' and _author_control_subject(relative) not in (None, selected_ticker):
            if path.exists() and not path.is_file():
                raise StorageError('Invalid unselected author control: '+relative)
            preserved_unselected_author_controls.append({'path':relative,
                'original_sha256':sha(path.read_bytes()) if path.is_file() else None,
                'snapshot_sha256':entry['sha256']})
            continue
        if materialization_role == 'local_author' and _shared_build_control(relative):
            # GitHub build controls are not author inputs. Preserve unpublished
            # local bytes and pin their remote identity without selecting either.
            if path.exists() and not path.is_file():
                raise StorageError('Invalid preserved shared build control: '+relative)
            preserved_shared_build_controls.append({'path':relative,
                'original_sha256':sha(path.read_bytes()) if path.is_file() else None,
                'snapshot_sha256':entry['sha256']})
            continue
        if path.is_file() and sha(path.read_bytes()) == entry['sha256']:
            continue
        incoming = None
        if path.is_file() and relative.endswith(('.json','.jsonl')):
            incoming = storage.restore(relative,records=records)
            preservation = _retain_or_advance_private_bytes(path,relative,incoming)
            if preservation is not None:
                preserved_serializations.append(preservation)
                continue
        if path.exists():
            baseline = run_git(vault, 'show', 'HEAD:'+relative, check=False)
            if baseline.returncode or baseline.stdout != path.read_bytes():
                raise StorageError('Refusing differing unpublished private bytes: '+relative)
        raw = incoming if incoming is not None else storage.restore(relative, records=records)
        if path.exists():
            # The exact replaced baseline remains immutable in legacy Git.
            path.write_bytes(raw)
        else:
            write_new(path, raw)
        restored += 1
    marker = {'schema_version':'private-storage-view/1', 'catalog_commit':commit,
              'catalog_repository_id':storage.config['catalog_repository_id'],
              'materialization_role':materialization_role, 'selected_ticker':selected_ticker, 'preserved_shared_build_controls':preserved_shared_build_controls, 'preserved_unselected_author_controls':preserved_unselected_author_controls,
              'read_only':bool(prefixes) or snapshot_only, 'snapshot_validation_only':snapshot_only, 'materialized_prefixes':list(prefixes), 'preserved_original_serializations':preserved_serializations}
    (vault/MARKER).write_bytes(encoded_json(marker))
    return {'catalog_commit':commit, 'control_files_restored':restored, 'preserved_original_serializations':preserved_serializations, 'preserved_shared_build_controls':preserved_shared_build_controls}


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
    if _local_author_view(vault) and _shared_build_control(relative):
        raise StorageError('A local author view cannot read a shared build control')
    if _local_author_view(vault) and _author_control_subject(relative) not in (None, selected_author_ticker(vault)):
        raise StorageError('A local author view cannot read an unselected company control')
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
    entry = storage.lookup_entry(relative, records)
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
    if _local_author_view(vault) and any(p.startswith('valuation-underwriting/runtime/') for p in paths):
        raise StorageError('A local author view cannot publish a shared build control or ledger')
    if _local_author_view(vault):
        ticker = selected_author_ticker(vault)
        if any(not _author_path_owned(vault, relative, ticker) for relative in paths):
            raise StorageError('A local author view can publish only its selected company and actual ledger')
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
                     or relative.endswith('.zip') or relative.startswith(('legacy/','audit/','recovery/')))
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
    parser.add_argument('--snapshot-validation-only',action='store_true')
    args=parser.parse_args()
    if args.action == 'enabled':
        return 0 if enabled() else 1
    if not args.vault:
        parser.error('--vault required')
    result = initialize(args.vault, prefixes=args.prefix, snapshot_only=args.snapshot_validation_only) if args.action == 'initialize' else publish_paths(args.vault,selected_files(args.vault,args.pathspec))
    print(json.dumps(result))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
