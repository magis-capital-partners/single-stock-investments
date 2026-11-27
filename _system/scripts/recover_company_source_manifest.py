"""Recover a completed source archive from verified uploaded immutable parts.

No source collection, matching, financial assumptions, or model calls occur here.
The normal publication identity and source-completeness checks still apply.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

from company_source_cache import FOLDERS, ROOT_FILES

HEX = re.compile(r'[a-f0-9]{64}')
PREFIX = 'dashboard-private/company-source-backfill-v2/'


def bucket(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or '..' in path.parts or chr(92) in name
            or not path.parts or path.as_posix() != name):
        raise ValueError('Unsafe source cache member')
    if len(path.parts) == 1:
        if name not in ROOT_FILES:
            raise ValueError('Unknown source cache root')
        return ('root', name)
    if path.parts[0] not in FOLDERS or path.suffix not in {'.json', '.txt', '.md'}:
        raise ValueError('Unknown source cache member')
    return (path.parts[0], path.stem[:2])


def profile_part(raw, expected):
    identity = hashlib.sha256(raw).hexdigest()
    if expected.get('sha256') != identity or expected.get('file') != identity + '.zip':
        raise ValueError('Source archive hash changed')
    signature = hashlib.sha256()
    members, roots = [], {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for item in archive.infolist():
            if item.is_dir() or item.flag_bits & 1:
                raise ValueError('Unexpected source archive member')
            bucket(item.filename)
            digest = hashlib.sha256()
            with archive.open(item) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            members.append([item.filename, digest.hexdigest()])
            signature.update(item.filename.encode() + bytes([0]) + digest.digest())
            if item.filename in ROOT_FILES:
                roots[item.filename] = archive.read(item)
    names = [row[0] for row in members]
    if not names or len(set(names)) != len(names):
        raise ValueError('Empty or duplicate source members')
    if names != sorted(names, key=PurePosixPath) or len({bucket(n) for n in names}) != 1:
        raise ValueError('Source bucket or member ordering changed')
    entry = {'file': identity + '.zip', 'sha256': identity,
             'files': len(names), 'input_sha256': signature.hexdigest()}
    if any(expected.get(k) != entry[k] for k in ('files', 'input_sha256') if k in expected):
        raise ValueError('Source archive input identity changed')
    return {'entry': entry, 'members': members}, roots


def reconstruct(previous, additions, profiles, *, expected_parts, expected_files):
    if previous.get('schema_version') != 1 or not isinstance(previous.get('parts'), list):
        raise ValueError('Unsupported previous source archive')
    old = previous['parts']
    old_names = [p['file'] for p in old]
    added_names = [p['file'] for p in additions]
    if (len(set(old_names)) != len(old_names) or len(set(added_names)) != len(added_names)
            or set(old_names) & set(added_names)):
        raise ValueError('Ambiguous source part transaction')
    if set(profiles) != set(old_names) | set(added_names):
        raise ValueError('Incomplete verified source profiles')
    for part in [*old, *additions]:
        actual = profiles[part['file']]['entry']
        if any(actual.get(k) != v for k, v in part.items()):
            raise ValueError('Source part profile differs from its pinned identity')
    changed_members = set()
    for name in added_names:
        members = {row[0] for row in profiles[name]['members']}
        if changed_members & members:
            raise ValueError('New source parts overlap')
        changed_members.update(members)
    selected = list(added_names)
    for name in old_names:
        members = {row[0] for row in profiles[name]['members']}
        overlap = members & changed_members
        if overlap:
            if not members <= changed_members:
                raise ValueError('Recovery would drop an original source member')
        else:
            selected.append(name)
    selected.sort(key=lambda n: (bucket(profiles[n]['members'][0][0]),
                                  PurePosixPath(profiles[n]['members'][0][0])))
    seen = set()
    for name in selected:
        members = {row[0] for row in profiles[name]['members']}
        if seen & members:
            raise ValueError('Recovered source parts overlap')
        seen.update(members)
    if len(selected) != expected_parts or len(seen) != expected_files:
        raise ValueError('Recovery differs from the completed producer counts')
    return {'schema_version': 1, 'parts': [profiles[n]['entry'] for n in selected]}


def encode_manifest(manifest, *, newline=chr(10)):
    if newline not in (chr(10), chr(13) + chr(10)):
        raise ValueError('Unsupported manifest newline')
    return (json.dumps(manifest, indent=2).replace(chr(10), newline) + newline).encode()


def main():
    import argparse
    import collections
    import concurrent.futures
    import copy
    from datetime import datetime, timezone
    import threading
    import time
    from private_storage import PrivateStorage, run_git

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', required=True, choices=['CPRT'])
    parser.add_argument('--limit', type=int, required=True, choices=[1])
    parser.add_argument('--parts-commit', required=True)
    parser.add_argument('--expected-parts', type=int, required=True)
    parser.add_argument('--expected-files', type=int, required=True)
    parser.add_argument('--expected-generated-at', required=True)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--work', type=Path, default=Path('_private/source-manifest-recovery'))
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}', args.parts_commit):
        parser.error('An immutable parts-only private catalog commit is required')
    if args.expected_parts <= 0 or args.expected_files <= 0:
        parser.error('The completed producer counts are required')
    root = Path(__file__).resolve().parents[2]
    work = args.work.resolve()
    if not work.is_relative_to((root / '_private').resolve()) or work.exists():
        parser.error('Recovery requires a new owned private work directory')
    work.mkdir(parents=True)
    storage = PrivateStorage()
    storage.catalog.fetch()
    # A fresh metadata-only catalog starts shallow; fetch this immutable pair.
    run_git(storage.catalog.directory, 'fetch', '--no-tags', '--depth', '2', 'origin', args.parts_commit)
    parent = run_git(storage.catalog.directory, 'rev-parse', args.parts_commit + '^').stdout.decode().strip()
    if run_git(storage.catalog.directory, 'diff', '--name-only', parent, args.parts_commit, '--', 'control/').stdout:
        raise ValueError('The source parts transaction changed a control file')
    records = storage.catalog.read(args.parts_commit)
    before = storage.catalog.read(parent)
    changed = {k: v for k, v in records.items() if before.get(k) != v}
    if not changed or any(not k.startswith(PREFIX) or not k.endswith('.zip') for k in changed):
        raise ValueError('The producer transaction must contain immutable source parts only')
    key = PREFIX + 'manifest.json'
    old_raw = storage.restore(key, records=records)
    if old_raw is None or records.get(key) != before.get(key):
        raise ValueError('The interrupted producer must retain its original manifest')
    previous = json.loads(old_raw)
    additions = [{'file': k.removeprefix(PREFIX), 'sha256': v['sha256']} for k, v in changed.items()]
    expected = {p['file']: p for p in [*previous['parts'], *additions]}
    profiles, roots = {}, {}
    local = threading.local()
    lock = threading.Lock()
    started = time.monotonic()

    def read_verified(item):
        name, prior = item
        if not hasattr(local, 'reader'):
            objects = copy.copy(storage.objects)
            objects._verified_cache = collections.OrderedDict()
            local.reader = PrivateStorage(config=storage.config, objects=objects, catalog=storage.catalog)
        raw = local.reader.restore(PREFIX + name, records=records)
        if raw is None:
            raise ValueError('A required source part is absent from the private catalog')
        profile, payloads = profile_part(raw, prior)
        path = work / (prior['sha256'] + '.json')
        path.write_bytes((json.dumps(profile, separators=(',', ':')) + chr(10)).encode())
        with lock:
            profiles[name] = profile
            for member, body in payloads.items():
                # New transaction parts supersede the prior snapshot's root.
                if member not in roots or name in {p['file'] for p in additions}:
                    roots[member] = body
            if len(profiles) % 100 == 0:
                print(json.dumps({'verified_parts': len(profiles), 'total': len(expected),
                                  'elapsed_seconds': round(time.monotonic() - started, 1)}), flush=True)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    futures = [pool.submit(read_verified, item) for item in expected.items()]
    try:
        for future in concurrent.futures.as_completed(futures):
            future.result()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    recovered = reconstruct(previous, additions, profiles,
                            expected_parts=args.expected_parts, expected_files=args.expected_files)
    index = json.loads(roots.get('index.json', b'null'))
    if not isinstance(index, dict) or index.get('generated_at') != args.expected_generated_at:
        raise ValueError('Recovery does not match the completed producer source epoch')
    raw = encode_manifest(recovered)
    identity = hashlib.sha256(raw).hexdigest()
    proof = {'schema_version': 'verified-source-manifest-recovery/1',
             'at': datetime.now(timezone.utc).isoformat(), 'ticker': args.ticker, 'limit': args.limit,
             'parts_commit': args.parts_commit, 'parts_parent': parent,
             'previous_manifest_sha256': hashlib.sha256(old_raw).hexdigest(),
             'recovered_manifest_sha256': identity, 'parts': len(recovered['parts']),
             'files': args.expected_files, 'source_generated_at': index['generated_at'],
             'every_complete_archive_member_CRC_and_hash_verified': True,
             'all_original_members_retained': True, 'new_model_calls': 0,
             'source_identity_and_normal_publication_checks_unchanged': True}
    (work / 'recovered-manifest.json').write_bytes(raw)
    (work / 'previous-manifest.json').write_bytes(old_raw)
    (work / 'proof.json').write_text(json.dumps(proof, indent=2) + chr(10))
    if args.publish:
        tip, current = storage.snapshot()
        if current.get(key) != records.get(key):
            raise ValueError('Another source producer advanced the manifest; recovery held')
        if any(current.get(PREFIX + p['file']) != records.get(PREFIX + p['file']) for p in recovered['parts']):
            raise ValueError('A verified immutable source part changed before publication')
        audit = io.BytesIO()
        with zipfile.ZipFile(audit, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(work.glob('*.json')):
                archive.writestr(path.name, path.read_bytes())
        audit_raw = audit.getvalue()
        relative = 'recovery/CPRT/source-manifest/' + identity + '/'
        updates = {relative + 'complete-profiles.zip': audit_raw,
                   relative + 'proof.json': (work / 'proof.json').read_bytes(),
                   relative + 'previous-manifest.json': old_raw,
                   relative + 'recovered-manifest.json': raw,
                   key: raw}
        storage.publish(updates, expected=current)
        published, after = storage.snapshot()
        if storage.restore(key, records=after) != raw or storage.restore(relative + 'complete-profiles.zip', records=after) != audit_raw:
            raise ValueError('Complete recovery archive readback failed')
        proof.update(private_pin_before=tip, verified_private_pin=published,
                     complete_audit_sha256=hashlib.sha256(audit_raw).hexdigest(),
                     complete_audit_bytes=len(audit_raw), current_manifest_readback_passed=True)
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
