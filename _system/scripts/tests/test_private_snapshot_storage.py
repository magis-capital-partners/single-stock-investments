"""Large private snapshots preserve exact bytes below GitHub's object limit."""
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_dashboard_assets as assets
import migrate_dashboard_sources as migration


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root, vault = tmp_path/'public', tmp_path/'vault'
    (root/'dashboard').mkdir(parents=True)
    (vault/'.git').mkdir(parents=True)
    monkeypatch.setattr(assets, 'research_vault_root', lambda: vault)
    monkeypatch.setattr(migration, 'research_vault_root', lambda: vault)
    monkeypatch.setattr('vault_paths.research_vault_root', lambda: vault)
    monkeypatch.setattr(assets, 'COMPRESS_AFTER_BYTES', 100)
    return root, vault


def test_large_archive_restores_its_original_bytes_and_existing_manifest_schema(workspace):
    root, vault = workspace
    relative = '_system/reference/data-sources/insights_record_archive.json'
    source = root/relative
    source.parent.mkdir(parents=True)
    raw = ('{\n  "records": ["'+('Research € with spaces and \\"quotes\\". '*100)+'"]\n}\n').encode()
    source.write_bytes(raw)
    result = migration.migrate(root, paths=[relative])
    assert result['migrated_or_updated_assets'] == 1
    entry = assets.overlay_manifest(root/'dashboard')['repository_assets'][relative]
    assert entry['private_sha256'] == hashlib.sha256(raw).hexdigest()
    stored = assets.stored_object(vault, entry['private_sha256'])
    assert stored.read_bytes().startswith(b'\x1f\x8b')
    assert gzip.decompress(stored.read_bytes()) == raw
    restored = assets.private_source(root, relative, {'assets': {relative: entry}})
    assert restored.read_bytes() == raw
    assert not restored.is_relative_to(vault)  # Unpacked bytes cannot enter a vault commit.
    assert assets.hydrate_repository(root) == 1
    assert source.read_bytes() == raw
    before = stored.read_bytes()
    migration.migrate(root, paths=[])
    assert stored.read_bytes() == before


def test_legacy_objects_remain_byte_for_byte_identical(workspace):
    _, vault = workspace
    path = vault/'small-source.json'
    raw = b'{ "cash": 100 }\n'
    path.write_bytes(raw)
    sha = assets.preserve_object(vault, path)
    assert assets.stored_object(vault, sha).read_bytes() == raw
    assert assets.private_object(vault, sha) == assets.stored_object(vault, sha)


def test_corrupt_compressed_object_cannot_be_restored(workspace):
    _, vault = workspace
    raw = b'Correct private data.'*50
    sha = hashlib.sha256(raw).hexdigest()
    path = assets.stored_object(vault, sha)
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(b'Changed data.'*50, mtime=0))
    with pytest.raises(RuntimeError, match='hash'):
        assets.private_object(vault, sha)


def test_uncompressible_oversize_fails_before_public_redaction(workspace, monkeypatch):
    root, _ = workspace
    monkeypatch.setattr(assets, 'MAX_STORED_BYTES', 50)
    source = root/'dashboard/data/large.json'
    source.parent.mkdir(parents=True)
    raw = json.dumps({'text': ''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(20))}).encode()
    source.write_bytes(raw)
    with pytest.raises(RuntimeError, match='GitHub'):
        migration.migrate(root, paths=['dashboard/data/large.json'])
    assert source.read_bytes() == raw


def test_stored_bytes_verify_decoded_content_and_enforce_a_size_bound(monkeypatch):
    raw = b'x'*200
    sha = hashlib.sha256(raw).hexdigest()
    assert assets.decode_object_bytes(gzip.compress(raw), sha) == raw
    assert assets.decode_object_bytes(raw, sha) == raw
    monkeypatch.setattr(assets, 'MAX_UNPACKED_BYTES', 100)
    with pytest.raises(RuntimeError, match='size'):
        assets.decode_object_bytes(gzip.compress(raw), sha)


def test_search_can_read_a_compressed_private_jsonl_snapshot(workspace):
    import agent_search
    root, vault = workspace
    path = root/'_system/data/chunks.jsonl'
    path.parent.mkdir(parents=True)
    rows = [{'chunk_id': 'c1', 'text': 'Private facts. '*30}]
    path.write_text(json.dumps(rows[0])+'\n', encoding='utf-8')
    sha = assets.preserve_object(vault, path)
    (root/'dashboard/private-assets.json').write_text(json.dumps({'repository_assets': {
        '_system/data/chunks.jsonl': {'private_sha256': sha, 'public_sha256': 'unused'}}}), encoding='utf-8')
    path.write_text('{"private_snapshot":true}\n', encoding='utf-8')
    assert agent_search.restored_private_rows(root, path) == rows
