import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_storage as storage
from test_private_storage import MemoryCatalog, Objects
from verify_private_storage_git import verify_restores


def make_reader(monkeypatch):
    pin = "1" * 40
    objects, catalog = Objects(), MemoryCatalog()
    original = "evidence/old.txt"
    alias = "current/renamed.txt"
    raw = b"Exact private archive bytes\r\n"
    legacy = storage.store_packed(objects, {original: raw})[original]
    legacy.update(git_blob=hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest(), git_mode="100644")
    empty = storage.store_bytes(objects, storage.encoded_json({}))
    prefix = storage.sha(original.encode())[:2]
    shards = {f"{i:02x}": f"legacy/test/{i:02x}.json" for i in range(256)}
    catalog.records.update({path: empty for path in shards.values()})
    catalog.records[shards[prefix]] = storage.store_bytes(objects, storage.encoded_json({original: legacy}))
    manifest = "legacy/test/manifest.json"
    catalog.records[manifest] = storage.store_bytes(objects, storage.encoded_json({
        "schema_version": "private-legacy-manifest/1", "source_commit": pin, "complete": True,
        "path_count": 1, "unique_git_blobs": 1, "shards": shards,
    }))
    catalog.records[alias] = storage.store_bytes(objects, raw)
    calls = []

    def get(_reader, path, entry):
        calls.append((path, entry["git_blob"]))
        assert path == original and entry == legacy
        return raw

    monkeypatch.setattr(storage.LegacyGitReader, "get", get)
    reader = storage.PrivateStorage(
        config={
            "legacy_pin": pin, "legacy_archive_manifest": manifest, "legacy_repository_id": 123,
            "legacy_repository": "magis-capital-partners/research-vault-legacy",
        },
        objects=objects, catalog=catalog,
    )
    return reader, catalog.records, original, alias, raw, calls


def test_reader_and_materializer_restore_exact_bytes_with_r2_payload_masked(monkeypatch):
    reader, records, original, alias, _, calls = make_reader(monkeypatch)
    entries = [reader.lookup_entry(path, records) for path in (original, alias)]
    digests = {chunk["stored_sha256"] for entry in entries for chunk in entry["chunks"]}
    assert verify_restores(reader, records, [original, alias], digests)["verified_restore_paths"] == 2
    assert [path for path, _ in calls] == [original] * 4


def test_current_catalog_wins_even_when_a_newer_revision_is_missing(monkeypatch, tmp_path):
    reader, records, original, _, _, calls = make_reader(monkeypatch)
    newer = storage.store_bytes(reader.objects, b"Current, different evidence")
    records[original] = newer
    assert reader.restore(original, records=records) == b"Current, different evidence"
    for chunk in newer["chunks"]:
        reader.objects.data.pop(chunk["stored_sha256"])
    target = tmp_path / "new.json"
    with pytest.raises(storage.MissingPrivateObject):
        reader.restore_to(original, target, records=records)
    assert calls == [] and not target.exists()


def test_corrupt_r2_data_fails_without_substituting_git(monkeypatch):
    reader, records, _, alias, _, calls = make_reader(monkeypatch)
    digest = records[alias]["chunks"][0]["stored_sha256"]
    reader.objects.data[digest] = b"wrong bytes"
    with pytest.raises(storage.StorageError, match="corrupt stored bytes"):
        reader.restore(alias, records=records)
    assert calls == []


def test_unchanged_git_backed_file_does_not_reupload_retired_chunks(monkeypatch, tmp_path):
    reader, records, _, alias, raw, calls = make_reader(monkeypatch)
    prior = records[alias]
    for chunk in prior["chunks"]:
        reader.objects.data.pop(chunk["stored_sha256"])
    path = tmp_path / "unchanged"
    path.write_bytes(raw)
    assert reader.reuse_file(alias, path, prior, records)
    before = set(reader.objects.data)
    reader.publish({alias:raw}, expected=records)
    assert set(reader.objects.data) == before
    assert len(calls) == 2
