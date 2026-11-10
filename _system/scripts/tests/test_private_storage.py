import copy
import gzip
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_storage as store


class Objects:
    def __init__(self):
        self.data = {}

    def put(self, raw):
        identity = store.sha(raw)
        if identity in self.data:
            assert self.data[identity] == raw
        self.data[identity] = raw
        return identity

    def get(self, identity, size):
        raw = self.data.get(identity)
        if raw is not None and (len(raw) != size or store.sha(raw) != identity):
            raise store.StorageError("corrupt stored bytes")
        return raw


class MemoryCatalog:
    def __init__(self):
        self.records = {}

    def fetch(self):
        return "commit"

    def read(self, _):
        return copy.deepcopy(self.records)

    def publish(self, updates, expected):
        for key, value in updates.items():
            if self.records.get(key) != expected.get(key) and self.records.get(key) != value:
                raise store.ConcurrentUpdate(key)
        self.records.update(copy.deepcopy(updates))
        return "commit"


@pytest.mark.parametrize("raw", [b"", b"binary\x00\xff", "Exact original\r\n漢字 ".encode() * 100,
                                   b"a" * 50000, gzip.compress(b"already compressed"), b"PK\x03\x04unchanged ZIP bytes"],
                         ids=["empty", "binary", "unicode-crlf", "compressible", "existing-gzip", "existing-zip"])
def test_exact_byte_roundtrip(raw):
    objects = Objects()
    entry = store.store_bytes(objects, raw)
    assert store.restore_bytes(objects, entry) == raw
    assert entry["sha256"] == store.sha(raw)
    assert entry["bytes"] == len(raw)


def test_lossless_chunk_boundaries_and_streamed_restore(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MAX_CHUNK_BYTES", 64)
    objects = Objects()
    raw = bytes(range(256)) * 3
    source = tmp_path / "source"
    source.write_bytes(raw)
    entry = store.store_file(objects, source)
    assert len(entry["chunks"]) == 12
    destination = tmp_path / "restored"
    store.restore_file(objects, entry, destination)
    assert destination.read_bytes() == raw
    assert store.restore_bytes(objects, entry) == raw


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a//b", "a/../b", "a\\b", "C:/data", ".git/config",
                                     ".GIT/config", "a/CON.txt", "a/NUL", "a/LPT1.log", "a./b", "a /b", "a\x00b"])
def test_unsafe_paths_fail(path):
    with pytest.raises(store.StorageError):
        store.relative_path(path)


def test_corrupt_stored_bytes_fail_before_restore():
    objects = Objects()
    entry = store.store_bytes(objects, b"original" * 100)
    objects.data[entry["chunks"][0]["stored_sha256"]] = b"different"
    with pytest.raises(store.StorageError):
        store.restore_bytes(objects, entry)


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("bytes", 7), ("encoding", "unknown")])
def test_decoded_chunk_identity_and_codec_fail(field, value):
    objects = Objects()
    entry = store.store_bytes(objects, b"original" * 100)
    entry["chunks"][0][field] = value
    with pytest.raises(store.StorageError):
        store.restore_bytes(objects, entry)


def test_complete_file_identity_is_verified():
    objects = Objects()
    entry = store.store_bytes(objects, b"full file")
    entry["sha256"] = "0" * 64
    with pytest.raises(store.StorageError, match="Complete"):
        store.restore_bytes(objects, entry)


def test_missing_chunk_stays_held():
    objects = Objects()
    entry = store.store_bytes(objects, b"full file")
    objects.data.clear()
    with pytest.raises(store.StorageError, match="missing"):
        store.restore_bytes(objects, entry)


def test_existing_restoration_target_is_never_overwritten(tmp_path):
    objects = Objects()
    entry = store.store_bytes(objects, b"new")
    destination = tmp_path / "existing"
    destination.write_bytes(b"original")
    with pytest.raises(store.StorageError):
        store.restore_file(objects, entry, destination)
    assert destination.read_bytes() == b"original"


def test_incomplete_new_restoration_is_not_registered(tmp_path):
    objects = Objects()
    entry = store.store_bytes(objects, b"new")
    entry["sha256"] = "0" * 64
    destination = tmp_path / "incomplete"
    with pytest.raises(store.StorageError):
        store.restore_file(objects, entry, destination)
    assert not destination.exists()


def test_large_file_requires_streamed_reader(monkeypatch):
    monkeypatch.setattr(store, "MAX_MEMORY_FILE_BYTES", 2)
    objects = Objects()
    entry = store.store_bytes(objects, b"large")
    with pytest.raises(store.StorageError, match="streamed"):
        store.restore_bytes(objects, entry)


def test_object_addressed_private_publication_contains_no_payload_in_catalog():
    objects, catalog = Objects(), MemoryCatalog()
    storage = store.PrivateStorage(config={}, objects=objects, catalog=catalog)
    raw = b"private raw evidence and paid output" * 100
    storage.publish({"valuation-underwriting/packets/" + "a" * 64 + ".json": raw})
    assert b"private raw evidence" not in store.encoded_json(catalog.records)
    assert storage.restore(next(iter(catalog.records))) == raw


def test_missing_existing_objects_cannot_be_claimed_archived():
    objects, catalog = Objects(), MemoryCatalog()
    storage = store.PrivateStorage(config={}, objects=objects, catalog=catalog)
    storage.publish({"evidence/file.json": b"original"})
    objects.data.clear()
    with pytest.raises(store.StorageError):
        storage.publish({"evidence/file.json": b"original"})


def test_immutable_handoff_cannot_be_replaced():
    objects, catalog = Objects(), MemoryCatalog()
    storage = store.PrivateStorage(config={}, objects=objects, catalog=catalog)
    path = "valuation-underwriting/handoffs/" + "a" * 64 + ".json"
    storage.publish({path: b"original approved handoff"})
    with pytest.raises(store.StorageError, match="immutable"):
        storage.publish({path: b"different"})
    assert storage.restore(path) == b"original approved handoff"


def test_changed_expected_pointer_fails_closed():
    objects, catalog = Objects(), MemoryCatalog()
    storage = store.PrivateStorage(config={}, objects=objects, catalog=catalog)
    _, before = storage.snapshot()
    storage.publish({"state/current.json": b"other writer"})
    with pytest.raises(store.ConcurrentUpdate):
        storage.publish({"state/current.json": b"stale writer"}, expected=before)
    assert storage.restore("state/current.json") == b"other writer"


def ledger(*rows):
    return b"".join(json.dumps(row).encode() + b"\r\n" for row in rows)


def test_ledger_extension_preserves_exact_incoming_bytes():
    a, b = {"status": "unknown", "timestamp": "2026-11-01"}, {"status": "reserved", "timestamp": "2026-11-02"}
    assert store.merge_ledger(ledger(a), ledger(a, b)) == ledger(a, b)


def test_ledger_older_copy_never_erases_events():
    a, b = {"status": "unknown"}, {"status": "pending"}
    assert store.merge_ledger(ledger(a, b), ledger(a)) == ledger(a, b)


def test_ledger_union_keeps_original_order_values_and_duplicate_history():
    a, b, c = {"status": "unknown"}, {"status": "reserved"}, {"status": "completed"}
    rows = [json.loads(x) for x in store.merge_ledger(ledger(a, a, b), ledger(a, c)).splitlines()]
    assert rows == [a, a, b, c]


def test_materialization_is_create_only_and_path_bounded(tmp_path):
    objects, catalog = Objects(), MemoryCatalog()
    storage = store.PrivateStorage(config={}, objects=objects, catalog=catalog)
    storage.publish({"packets/verified.json": b"exact"})
    out = store.ensure_private_file(tmp_path, "packets/verified.json", storage=storage)
    assert out.read_bytes() == b"exact"
    out.write_bytes(b"existing local bytes")
    store.ensure_private_file(tmp_path, "packets/verified.json", storage=storage)
    assert out.read_bytes() == b"existing local bytes"


def test_public_catalog_is_rejected(tmp_path):
    config = {"catalog_repository": "magis-capital-partners/research-catalog", "catalog_repository_id": 1}
    catalog = store.Catalog(config, tmp_path / "catalog.git")
    result = subprocess.CompletedProcess([], 0, b'{"id":1,"private":false}', b"")
    with patch.object(subprocess, "run", return_value=result), pytest.raises(store.StorageError, match="privacy"):
        catalog.assert_private()


def test_real_git_catalog_preserves_nonoverlapping_changes_and_rejects_conflicts(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    for args in (("config", "user.name", "Test"), ("config", "user.email", "test@example.invalid"),
                 ("checkout", "-b", "main")):
        subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)
    (work / "README").write_text("metadata only")
    for args in (("add", "README"), ("commit", "-m", "initial"), ("push", "origin", "main")):
        subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    config = {"catalog_repository": "magis-capital-partners/research-catalog", "catalog_repository_id": 1}
    first, second = store.Catalog(config, tmp_path / "one.git"), store.Catalog(config, tmp_path / "two.git")
    for catalog in (first, second):
        catalog.url = str(remote)
        monkeypatch.setattr(catalog, "assert_private", lambda: None)
    original = first.read(first.fetch())
    a = {"sha256": "a" * 64, "bytes": 0, "chunks": []}
    b = {"sha256": "b" * 64, "bytes": 0, "chunks": []}
    first.publish({"one.json": a}, original)
    second.publish({"two.json": b}, original)
    assert second.read(second.fetch()) == {"one.json": a, "two.json": b}
    with pytest.raises(store.ConcurrentUpdate):
        second.publish({"one.json": b}, original)


def test_real_ledger_control_is_append_only(tmp_path, monkeypatch):
    remote=tmp_path/'remote.git'
    work=tmp_path/'work'
    subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
    subprocess.run(['git','clone',str(remote),str(work)],check=True,capture_output=True)
    for args in [('config','user.name','Test'),('config','user.email','test@example.invalid'),('checkout','-b','main')]:
        subprocess.run(['git','-C',str(work),*args],check=True,capture_output=True)
    (work/'README').write_text('metadata only')
    for args in [('add','README'),('commit','-m','baseline'),('push','origin','main')]:
        subprocess.run(['git','-C',str(work),*args],check=True,capture_output=True)
    subprocess.run(['git','-C',str(remote),'symbolic-ref','HEAD','refs/heads/main'],check=True)
    catalog=store.Catalog({'catalog_repository':'magis-capital-partners/research-catalog'},tmp_path/'catalog.git')
    catalog.url=str(remote)
    monkeypatch.setattr(catalog,'assert_private',lambda:None)
    old=ledger({'status':'unknown'},{'status':'reserved'})
    new=old+ledger({'status':'completed'})
    catalog.publish({}, {}, control_files={'control/admission-ledger.jsonl':old})
    head=catalog.publish({}, {}, control_files={'control/admission-ledger.jsonl':new})
    assert store.run_git(catalog.directory,'show',head+':control/admission-ledger.jsonl').stdout==new
    with pytest.raises(store.StorageError,match='lose or reorder'):
        catalog.publish({}, {}, control_files={'control/admission-ledger.jsonl':ledger({'status':'completed'})})
