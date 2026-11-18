import copy
import os
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import company_source_cache as cache
import recover_company_source_manifest as recovery


def raw_part(rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in rows:
            archive.writestr(name, raw)
    raw = output.getvalue()
    identity = hashlib.sha256(raw).hexdigest()
    entry = {'file': identity + '.zip', 'sha256': identity}
    profile, _ = recovery.profile_part(raw, entry)
    return entry, profile


def fixture_parts():
    first, pfirst = raw_part([('records/aa01.json', b'old'), ('records/aa02.json', b'keep')])
    new, pnew = raw_part([('records/aa01.json', b'current'), ('records/aa02.json', b'keep')])
    other, pother = raw_part([('words/bb01.json', b'unchanged')])
    old = {'schema_version': 1, 'parts': copy.deepcopy([pfirst['entry'], pother['entry']])}
    return old, [new], {first['file']: pfirst, new['file']: pnew, other['file']: pother}


def test_exact_normal_pack_recovery_after_final_pointer_interruption(tmp_path):
    source, archive = tmp_path / 'cache', tmp_path / 'archive'
    source.mkdir()
    (source / 'index.json').write_text('{"generated_at":"old"}')
    (source / 'records').mkdir()
    (source / 'records/aa01.json').write_bytes(b'prior complete source')
    (source / 'words').mkdir()
    (source / 'words/bb01.json').write_bytes(b'unchanged full text')
    cache.pack(source, archive)
    previous_raw = (archive / 'manifest.json').read_bytes()
    previous = json.loads(previous_raw)
    (source / 'index.json').write_text('{"generated_at":"current"}')
    (source / 'records/aa01.json').write_bytes(b'current complete source')
    (source / 'records/aa02.json').write_bytes(b'added complete source')
    cache.pack(source, archive)
    current_raw = (archive / 'manifest.json').read_bytes()
    current = json.loads(current_raw)
    old_names = {p['file'] for p in previous['parts']}
    additions = [p for p in current['parts'] if p['file'] not in old_names]
    profiles = {}
    for part in [*previous['parts'], *additions]:
        profiles[part['file']], _ = recovery.profile_part((archive / part['file']).read_bytes(), part)
    (archive / 'manifest.json').write_bytes(previous_raw)
    cache.restore(archive, tmp_path / 'before')
    assert json.loads((tmp_path / 'before/index.json').read_bytes())['generated_at'] == 'old'
    recovered = recovery.reconstruct(previous, additions, profiles,
        expected_parts=len(current['parts']), expected_files=sum(p['files'] for p in current['parts']))
    assert recovery.encode_manifest(recovered, newline=os.linesep) == current_raw
    (archive / 'manifest.json').write_bytes(recovery.encode_manifest(recovered, newline=os.linesep))
    cache.restore(archive, tmp_path / 'after')
    for path in source.rglob('*'):
        if path.is_file():
            assert (tmp_path / 'after' / path.relative_to(source)).read_bytes() == path.read_bytes()


def test_changed_part_retains_all_unchanged_complete_members():
    previous, additions, profiles = fixture_parts()
    result = recovery.reconstruct(previous, additions, profiles, expected_parts=2, expected_files=3)
    assert [p['file'] for p in result['parts']] == [additions[0]['file'], previous['parts'][1]['file']]


def test_cannot_discard_original_member_from_a_replaced_part():
    previous, _, profiles = fixture_parts()
    addition, profile = raw_part([('records/aa01.json', b'current')])
    profiles = {p['file']: profiles[p['file']] for p in previous['parts']}
    profiles[addition['file']] = profile
    with pytest.raises(ValueError, match='drop an original'):
        recovery.reconstruct(previous, [addition], profiles, expected_parts=2, expected_files=2)


def test_new_parts_cannot_conflict_on_a_member():
    previous, additions, profiles = fixture_parts()
    other, profile = raw_part([('records/aa01.json', b'conflicting current source')])
    additions.append(other)
    profiles[other['file']] = profile
    with pytest.raises(ValueError, match='overlap'):
        recovery.reconstruct(previous, additions, profiles, expected_parts=3, expected_files=3)


@pytest.mark.parametrize('field', ['files', 'input_sha256'])
def test_pinned_prior_identity_cannot_change(field):
    previous, additions, profiles = fixture_parts()
    previous['parts'][0][field] = 999 if field == 'files' else '0' * 64
    with pytest.raises(ValueError, match='pinned identity'):
        recovery.reconstruct(previous, additions, profiles, expected_parts=2, expected_files=3)


@pytest.mark.parametrize('parts,files', [(3, 3), (2, 4)])
def test_completed_producer_counts_are_mandatory(parts, files):
    previous, additions, profiles = fixture_parts()
    with pytest.raises(ValueError, match='producer counts'):
        recovery.reconstruct(previous, additions, profiles, expected_parts=parts, expected_files=files)


def test_missing_full_profile_is_held():
    previous, additions, profiles = fixture_parts()
    profiles.pop(previous['parts'][0]['file'])
    with pytest.raises(ValueError, match='Incomplete'):
        recovery.reconstruct(previous, additions, profiles, expected_parts=2, expected_files=3)


def test_duplicate_transaction_part_is_held():
    previous, additions, profiles = fixture_parts()
    with pytest.raises(ValueError, match='Ambiguous'):
        recovery.reconstruct(previous, additions * 2, profiles, expected_parts=2, expected_files=3)


@pytest.mark.parametrize('name', ['../outside.json', '/index.json', 'outside.json', 'records/aa01.exe', 'records/../index.json', 'records' + chr(92) + 'aa01.json'])
def test_unsafe_or_unknown_source_paths_are_held(name):
    with pytest.raises(ValueError):
        recovery.bucket(name)


def test_wrong_raw_hash_is_held_before_reading_source():
    with pytest.raises(ValueError, match='hash changed'):
        recovery.profile_part(b'not a zip', {'file': '0' * 64 + '.zip', 'sha256': '0' * 64})


def test_mixed_source_bucket_is_held():
    with pytest.raises(ValueError, match='bucket'):
        raw_part([('records/aa01.json', b'complete'), ('records/bb01.json', b'complete')])


def test_unsorted_members_are_held():
    with pytest.raises(ValueError, match='ordering'):
        raw_part([('records/aa02.json', b'complete'), ('records/aa01.json', b'complete')])


def test_full_original_bytes_and_types_are_only_hashed():
    payload = bytes([239, 187, 191]) + b'{"values":[1,1.0,null,false]}' + bytes([13, 10])
    entry, profile = raw_part([('records/aa01.json', payload)])
    assert profile['members'] == [['records/aa01.json', hashlib.sha256(payload).hexdigest()]]
    assert profile['entry']['sha256'] == entry['sha256']


def test_normal_bucket_boundary_rebalance_is_recovered_without_lost_members(tmp_path):
    source, archive = tmp_path / 'cache', tmp_path / 'archive'
    (source / 'records').mkdir(parents=True)
    for name, size in [('aa11.json', 17000000), ('aa12.json', 15000000), ('aa13.json', 1000000)]:
        (source / 'records' / name).write_bytes(b'x' * size)
    cache.pack(source, archive)
    previous = json.loads((archive / 'manifest.json').read_bytes())
    (source / 'records/aa00.json').write_bytes(b'y' * 500000)
    cache.pack(source, archive)
    current_raw = (archive / 'manifest.json').read_bytes()
    current = json.loads(current_raw)
    old_names = {p['file'] for p in previous['parts']}
    additions = [p for p in current['parts'] if p['file'] not in old_names]
    profiles = {p['file']: recovery.profile_part((archive / p['file']).read_bytes(), p)[0]
                for p in [*previous['parts'], *additions]}
    result = recovery.reconstruct(previous, additions, profiles, expected_parts=2, expected_files=4)
    assert recovery.encode_manifest(result, newline=os.linesep) == current_raw
