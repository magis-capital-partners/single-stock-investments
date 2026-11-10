"""Lossless private objects in R2; only small, versioned pointers go into Git.

The legacy vault is a read-only fallback. No operation rewrites its history,
changes a paid record, or changes underwriting/admission/economic validation.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
import gzip
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_METADATA_BYTES = 1024 * 1024
MAX_CATALOG_BYTES = 100 * 1024 * 1024
MAX_CHUNK_BYTES = 64 * 1024 * 1024
MAX_MEMORY_FILE_BYTES = 256 * 1024 * 1024


class StorageError(RuntimeError):
    pass


class ConcurrentUpdate(StorageError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded_json(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise StorageError("Unsafe private storage path")
    parts = value.split("/")
    reserved = {"con", "prn", "aux", "nul", *("com" + str(i) for i in range(1, 10)),
                *("lpt" + str(i) for i in range(1, 10))}
    if any(p.lower() in ("", ".", "..", ".git") or p.endswith((".", " "))
           or any(c in p for c in ':<>"|?*') or p.split(".")[0].lower() in reserved for p in parts):
        raise StorageError("Unsafe private storage path")
    if PurePosixPath(value).is_absolute():
        raise StorageError("Unsafe private storage path")
    return value


def load_config(root=ROOT, *, require_enabled=False):
    config = json.loads((Path(root) / "_system/config/private_storage.json").read_text())
    if config.get("schema_version") != "private-storage/1":
        raise StorageError("Unsupported private storage configuration")
    if config.get("catalog_repository") != "magis-capital-partners/research-catalog":
        raise StorageError("Unexpected private catalog repository")
    if not re.fullmatch(r"[0-9a-f]{32}", config.get("account_id", "")):
        raise StorageError("Explicit storage account required")
    if config.get("bucket") != "single-stock-investments-private":
        raise StorageError("Unexpected private bucket")
    if config.get("chunk_bytes") != MAX_CHUNK_BYTES:
        raise StorageError("Unsupported lossless chunk size")
    relative_path(config["object_prefix"])
    if require_enabled and config.get("enabled") is not True:
        raise StorageError("Private object storage is not activated")
    return config


def enabled(root=ROOT):
    path = Path(root) / "_system/config/private_storage.json"
    return path.is_file() and load_config(root).get("enabled") is True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise StorageError("Unexpected authenticated storage redirect")


class HTTP:
    def __init__(self, token, host, *, requests_per_second=2):
        self.token, self.host = token, host
        self.interval = 1 / requests_per_second
        self.lock, self.next_request = threading.Lock(), 0.0
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, body=None, *, limit=MAX_CHUNK_BYTES + 1024 * 1024):
        with self.lock:
            delay = max(0, self.next_request - time.monotonic())
            if delay:
                time.sleep(delay)
            self.next_request = time.monotonic() + self.interval
        request = urllib.request.Request(
            "https://" + self.host + path, data=body, method=method,
            headers={"Authorization": "Bearer " + self.token(),
                     "Content-Type": "application/octet-stream", "User-Agent": "Magis-private-storage/1"})
        try:
            with self.opener.open(request, timeout=120) as response:
                raw = response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            # Do not include credentials, signed URLs, or provider response bodies.
            raise StorageError(f"Private storage {method} failed: HTTP {exc.code}") from None
        if len(raw) > limit:
            raise StorageError("Private storage response exceeds its exact bounded size")
        return raw


def cloudflare_token():
    value = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if value:
        return value
    # Reuse the user's existing signed-in Wrangler session; never create keys.
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    path = appdata / "xdg.config/.wrangler/config/default.toml"
    values = tomllib.loads(path.read_text()) if path.is_file() else {}
    token = values.get("oauth_token")
    if not token:
        raise StorageError("Existing authorized Cloudflare storage credentials are required")
    return token


class R2Objects:
    def __init__(self, config, *, http=None):
        self.config = config
        self._verified_cache = OrderedDict()
        self.http = http or HTTP(cloudflare_token, "api.cloudflare.com",
                                 requests_per_second=config.get("requests_per_second", 2))
        self.base = "/client/v4/accounts/" + config["account_id"] + "/r2/buckets/" + config["bucket"] + "/objects/"

    def key(self, identity):
        if not HEX.fullmatch(identity):
            raise StorageError("Invalid immutable object identity")
        return self.config["object_prefix"] + "/" + identity[:2] + "/" + identity

    def get(self, identity, size):
        if type(size) is not int or not 0 <= size <= MAX_CHUNK_BYTES + 1024 * 1024:
            raise StorageError("Invalid immutable object size")
        cached = self._verified_cache.get(identity)
        if cached is not None:
            if len(cached) != size:
                raise StorageError("Immutable cached object size changed")
            self._verified_cache.move_to_end(identity)
            return cached
        raw = self.http.request("GET", self.base + self.key(identity), limit=size)
        if raw is None:
            return None
        if len(raw) != size or sha(raw) != identity:
            raise StorageError("Immutable private object hash or size changed")
        self._verified_cache[identity] = raw
        while len(self._verified_cache) > 2:
            self._verified_cache.popitem(last=False)
        return raw

    def put(self, raw):
        identity = sha(raw)
        prior = self.get(identity, len(raw))
        if prior is None:
            self.http.request("PUT", self.base + self.key(identity), raw, limit=1024 * 1024)
            if self.get(identity, len(raw)) != raw:
                raise StorageError("Private object upload did not round-trip")
        return identity


def compress(raw):
    # Never recompress an existing ZIP/gzip archive. Normal gzip has a stable
    # header on Windows and Linux; the object address also binds stored bytes.
    if raw.startswith((b"PK\x03\x04", b"\x1f\x8b")):
        return raw, "raw"
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, filename="", mode="wb", mtime=0) as stream:
        stream.write(raw)
    packed = out.getvalue()
    return (packed, "gzip") if len(packed) < len(raw) else (raw, "raw")


def store_bytes(objects, raw):
    chunks = []
    for start in range(0, len(raw), MAX_CHUNK_BYTES):
        piece = raw[start:start + MAX_CHUNK_BYTES]
        stored, codec = compress(piece)
        chunks.append({"sha256": sha(piece), "bytes": len(piece), "stored_sha256": objects.put(stored),
                       "stored_bytes": len(stored), "encoding": codec})
    return {"sha256": sha(raw), "bytes": len(raw), "chunks": chunks}


def store_file(objects, path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise StorageError("Only regular private files can be archived")
    before = path.stat()
    identity, chunks, size = hashlib.sha256(), [], 0
    with path.open("rb") as source:
        while piece := source.read(MAX_CHUNK_BYTES):
            identity.update(piece)
            size += len(piece)
            stored, codec = compress(piece)
            chunks.append({"sha256": sha(piece), "bytes": len(piece), "stored_sha256": objects.put(stored),
                           "stored_bytes": len(stored), "encoding": codec})
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or size != before.st_size:
        raise StorageError("Private source changed during archival; uploaded chunks remain preserved")
    return {"sha256": identity.hexdigest(), "bytes": size, "chunks": chunks}


def store_packed(objects, files):
    """Preserve many complete files with one verified bounded object per pack.

    Pack offsets are storage transport only. Original bytes, SHA-256 values,
    file boundaries and all prior chunk layouts remain unchanged.
    """
    entries, pending, packed = {}, [], bytearray()

    def flush():
        if not pending:
            return
        identity = objects.put(bytes(packed))
        size = len(packed)
        for target, metadata in pending:
            target.update(stored_sha256=identity, stored_bytes=size, **metadata)
        pending.clear()
        packed.clear()

    for relative, raw in files.items():
        relative_path(relative)
        if not isinstance(raw, bytes):
            raise StorageError("A complete binary private file is required")
        chunks = []
        entries[relative] = {"sha256": sha(raw), "bytes": len(raw), "chunks": chunks}
        for start in range(0, len(raw), MAX_CHUNK_BYTES):
            piece = raw[start:start + MAX_CHUNK_BYTES]
            stored, codec = compress(piece)
            if len(packed) + len(stored) > MAX_CHUNK_BYTES:
                flush()
            item = {"sha256": sha(piece), "bytes": len(piece), "encoding": "packed-" + codec}
            metadata = {"packed_offset": len(packed), "packed_bytes": len(stored)}
            pending.append((item, metadata))
            packed.extend(stored)
            chunks.append(item)
    flush()
    for relative, entry in entries.items():
        if restore_bytes(objects, entry) != files[relative]:
            raise StorageError("Complete packed private file did not round-trip")
    return entries


def decoded_chunks(objects, entry):
    if not HEX.fullmatch(entry.get("sha256", "")) or type(entry.get("bytes")) is not int or entry["bytes"] < 0:
        raise StorageError("Invalid private file identity")
    chunks = entry.get("chunks")
    if not isinstance(chunks, list) or len(chunks) > 16384:
        raise StorageError("Invalid private file chunk manifest")
    for item in chunks:
        if type(item.get("bytes")) is not int or not 0 < item["bytes"] <= MAX_CHUNK_BYTES:
            raise StorageError("Invalid private file chunk size")
        raw = objects.get(item.get("stored_sha256", ""), item.get("stored_bytes"))
        if raw is None:
            raise StorageError("Required immutable private object is missing")
        codec = item.get("encoding")
        if codec in ("packed-raw", "packed-gzip"):
            offset, size = item.get("packed_offset"), item.get("packed_bytes")
            if (type(offset) is not int or type(size) is not int or offset < 0
                    or size <= 0 or offset + size > len(raw)):
                raise StorageError("Invalid packed private file boundary")
            raw = raw[offset:offset + size]
            codec = codec.removeprefix("packed-")
        if codec == "gzip":
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                    raw = stream.read(item["bytes"] + 1)
            except (OSError, EOFError):
                raise StorageError("Invalid lossless private object") from None
        elif codec != "raw":
            raise StorageError("Unsupported lossless private object encoding")
        if len(raw) != item["bytes"] or sha(raw) != item.get("sha256"):
            raise StorageError("Decoded private chunk changed")
        yield raw


def restore_bytes(objects, entry):
    if type(entry.get("bytes")) is not int or not 0 <= entry["bytes"] <= MAX_MEMORY_FILE_BYTES:
        raise StorageError("Use streamed restoration for large private files")
    result = bytearray()
    for piece in decoded_chunks(objects, entry):
        result.extend(piece)
        if len(result) > entry["bytes"]:
            raise StorageError("Private file exceeds its declared complete size")
    raw = bytes(result)
    if len(raw) != entry["bytes"] or sha(raw) != entry["sha256"]:
        raise StorageError("Complete private file hash changed")
    return raw


def restore_file(objects, entry, destination):
    destination = Path(destination)
    identity, size, created = hashlib.sha256(), 0, False
    try:
        with destination.open("xb") as out:
            created = True
            for piece in decoded_chunks(objects, entry):
                identity.update(piece)
                size += len(piece)
                if size > entry["bytes"]:
                    raise StorageError("Private file exceeds its declared complete size")
                out.write(piece)
        if size != entry["bytes"] or identity.hexdigest() != entry["sha256"]:
            raise StorageError("Complete restored private file changed")
    except FileExistsError:
        raise StorageError("Refusing to overwrite an existing restoration target") from None
    except BaseException:
        # This function created this exact incomplete temporary file, never an
        # existing record. Preserve any pre-existing destination above.
        if created:
            destination.unlink(missing_ok=True)
        raise


def git_env():
    env = dict(os.environ)
    token = env.get("RESEARCH_CATALOG_TOKEN") or env.get("RESEARCH_VAULT_CLONE_TOKEN")
    if token:
        header = "AUTHORIZATION: basic " + base64.b64encode(("x-access-token:" + token).encode()).decode()
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
        env.update({"GIT_CONFIG_COUNT": str(count + 1), f"GIT_CONFIG_KEY_{count}": "http.https://github.com/.extraheader",
                    f"GIT_CONFIG_VALUE_{count}": header})
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def run_git(directory, *arguments, data=None, env=None, check=True):
    result = subprocess.run(["git", "-c", "gc.auto=0", "-c", "fetch.recurseSubmodules=false", *arguments],
                            cwd=directory, input=data, capture_output=True, timeout=180, env=env or git_env())
    if check and result.returncode:
        raise StorageError("Private catalog Git operation failed: " + arguments[0])
    return result


class Catalog:
    def __init__(self, config, directory=None):
        self.config = config
        self.directory = Path(directory or Path(tempfile.gettempdir()) / "magis-private-storage" / "catalog.git")
        self.url = "https://github.com/" + config["catalog_repository"] + ".git"

    def assert_private(self):
        env = dict(os.environ)
        token = env.get("RESEARCH_CATALOG_TOKEN") or env.get("RESEARCH_VAULT_CLONE_TOKEN")
        if token:
            env["GH_TOKEN"] = token
        result = subprocess.run(["gh", "api", "repos/" + self.config["catalog_repository"]],
                                capture_output=True, env=env, timeout=60)
        if result.returncode:
            raise StorageError("Private catalog access is required; no archive state was replaced")
        metadata = json.loads(result.stdout)
        if metadata.get("private") is not True or metadata.get("id") != self.config["catalog_repository_id"]:
            raise StorageError("Private catalog repository identity or privacy changed")
        if metadata.get("size", 0) > MAX_CATALOG_BYTES // 1024:
            raise StorageError("Private catalog exceeded its metadata-only repository budget")

    def fetch(self):
        self.assert_private()
        if not self.directory.exists():
            self.directory.parent.mkdir(parents=True, exist_ok=True)
            run_git(self.directory.parent, "clone", "--bare", "--depth", "1", self.url, str(self.directory))
        actual = run_git(self.directory, "remote", "get-url", "origin").stdout.decode().strip()
        if actual != self.url:
            raise StorageError("Unexpected private catalog remote")
        run_git(self.directory, "fetch", "--no-tags", "origin", self.config.get("catalog_branch", "main") + ":refs/remotes/origin/main")
        return run_git(self.directory, "rev-parse", "refs/remotes/origin/main").stdout.decode().strip()

    def read(self, commit):
        records = {}
        total = 0
        listing = run_git(self.directory, "ls-tree", "-rz", commit, "--", "index/").stdout
        for row in listing.split(b"\0"):
            if not row:
                continue
            metadata, name = row.split(b"\t", 1)
            path = name.decode()
            if not re.fullmatch(r"index/[0-9a-f]{2}\.json", path) or metadata.split()[:2] != [b"100644", b"blob"]:
                raise StorageError("Unexpected private catalog metadata")
            raw = run_git(self.directory, "show", commit + ":" + path).stdout
            total += len(raw)
            if len(raw) > MAX_METADATA_BYTES or total > MAX_CATALOG_BYTES:
                raise StorageError("Private catalog exceeds its metadata-only budget")
            shard = json.loads(raw)
            if not isinstance(shard, dict):
                raise StorageError("Invalid private catalog shard")
            for relative, entry in shard.items():
                relative_path(relative)
                if "index/" + sha(relative.encode())[:2] + ".json" != path or relative in records:
                    raise StorageError("Private catalog shard identity changed")
                if not isinstance(entry, dict) or not HEX.fullmatch(entry.get("sha256", "")):
                    raise StorageError("Invalid private catalog entry")
                records[relative] = entry
        return records

    def publish(self, updates, expected, *, control_files=None):
        control_files = control_files or {}
        if set(control_files) - {"control/admission-ledger.jsonl"}:
            raise StorageError("Unexpected private ledger control file")
        for relative in updates:
            relative_path(relative)
        for _ in range(3):
            parent = self.fetch()
            current = self.read(parent)
            changed = {}
            for relative, entry in updates.items():
                if current.get(relative) == entry:
                    continue
                if current.get(relative) != expected.get(relative):
                    raise ConcurrentUpdate("Private artifact changed concurrently: " + relative)
                changed[relative] = entry
            control_changes = {}
            for path, raw in control_files.items():
                if len(raw) > MAX_METADATA_BYTES:
                    raise StorageError('Real admission ledger exceeded its control metadata bound')
                prior = run_git(self.directory, 'show', parent+':'+path, check=False)
                if prior.returncode == 0:
                    if merge_ledger(prior.stdout, raw) != raw:
                        raise StorageError('Real admission ledger cannot lose or reorder prior events')
                    if prior.stdout == raw:
                        continue
                control_changes[path] = raw
            if not changed and not control_changes:
                return parent
            current.update(changed)
            shards = {}
            changed_prefixes = {sha(r.encode())[:2] for r in changed}
            for relative, entry in current.items():
                key = "index/" + sha(relative.encode())[:2] + ".json"
                if key[6:8] in changed_prefixes:
                    shards.setdefault(key, {})[relative] = entry
            index = self.directory / ("publication-" + os.urandom(12).hex() + ".index")
            env = {**git_env(), "GIT_INDEX_FILE": str(index), "GIT_AUTHOR_NAME": "Magis private storage",
                   "GIT_AUTHOR_EMAIL": "storage@users.noreply.github.com", "GIT_COMMITTER_NAME": "Magis private storage",
                   "GIT_COMMITTER_EMAIL": "storage@users.noreply.github.com"}
            try:
                run_git(self.directory, "read-tree", parent, env=env)
                for path, values in shards.items():
                    raw = encoded_json(values)
                    if len(raw) > MAX_METADATA_BYTES:
                        raise StorageError("Private catalog shard exceeds its metadata-only budget")
                    blob = run_git(self.directory, "hash-object", "-w", "--stdin", data=raw).stdout.decode().strip()
                    run_git(self.directory, "update-index", "--add", "--cacheinfo", "100644," + blob + "," + path, env=env)
                for path, raw in control_changes.items():
                    blob = run_git(self.directory, 'hash-object', '-w', '--stdin', data=raw).stdout.decode().strip()
                    run_git(self.directory, 'update-index', '--add', '--cacheinfo', '100644,'+blob+','+path, env=env)
                tree = run_git(self.directory, "write-tree", env=env).stdout.decode().strip()
                commit = run_git(self.directory, "commit-tree", tree, "-p", parent,
                                 data=b"Preserve verified private object references\n", env=env).stdout.decode().strip()
                pushed = run_git(self.directory, "push", "origin", commit + ":refs/heads/main", check=False)
                if pushed.returncode == 0:
                    return commit
                error = pushed.stderr.decode(errors="replace").lower()
                if not any(s in error for s in ("non-fast-forward", "fetch first", "failed to update ref")):
                    raise StorageError("Private catalog publication failed; verified objects remain preserved")
            finally:
                index.unlink(missing_ok=True)
        raise ConcurrentUpdate("Private catalog changed repeatedly; verified objects remain preserved")


class PrivateStorage:
    def __init__(self, root=ROOT, *, config=None, objects=None, catalog=None):
        self.config = config if config is not None else load_config(root, require_enabled=True)
        self.objects = objects or R2Objects(self.config)
        self.catalog = catalog or Catalog(self.config)
        self._legacy_indexes = OrderedDict()

    def snapshot(self):
        commit = self.catalog.fetch()
        return commit, self.catalog.read(commit)

    def publish(self, files, *, expected=None):
        if expected is None:
            _, expected = self.snapshot()
        updates = {}
        for relative, raw in files.items():
            relative_path(relative)
            prior = expected.get(relative)
            if prior and relative.endswith("/ledger.jsonl"):
                raw = merge_ledger(restore_bytes(self.objects, prior), raw)
            if prior and prior.get("sha256") == sha(raw) and prior.get("bytes") == len(raw):
                # A matching pointer alone is not proof the private bytes exist.
                if restore_bytes(self.objects, prior) != raw:
                    raise StorageError("Existing private file differs")
                continue
            immutable = re.search(r"(?:^|/)(?:objects|packets|handoffs)/[0-9a-f]{64}(?:\.json|\.zip)?$", relative)
            immutable = immutable or relative.startswith(("legacy/", "audit/", "recovery/"))
            if prior and immutable:
                raise StorageError("An immutable private artifact cannot be replaced")
            updates[relative] = store_bytes(self.objects, raw)
        return self.catalog.publish(updates, expected)

    def lookup_entry(self, relative, records):
        relative_path(relative)
        if relative in records:
            return records[relative]
        manifest_path = self.config.get("legacy_archive_manifest")
        if not manifest_path:
            return None
        relative_path(manifest_path)
        manifest_entry = records.get(manifest_path)
        if manifest_entry is None:
            raise StorageError("Required verified legacy manifest is missing")
        identity = manifest_entry["sha256"]
        if identity not in self._legacy_indexes:
            manifest = json.loads(restore_bytes(self.objects, manifest_entry))
            if (manifest.get("schema_version") != "private-legacy-manifest/1"
                    or manifest.get("source_commit") != self.config["legacy_pin"]
                    or manifest.get("complete") is not True
                    or set(manifest.get("shards", {})) != {format(i, "02x") for i in range(256)}
                    or type(manifest.get("path_count")) is not int or manifest["path_count"] <= 0
                    or type(manifest.get("unique_git_blobs")) is not int
                    or not 0 < manifest["unique_git_blobs"] <= manifest["path_count"]):
                raise StorageError("Legacy manifest source identity or completeness changed")
            self._legacy_indexes[identity] = manifest
        manifest = self._legacy_indexes[identity]
        prefix = sha(relative.encode())[:2]
        shard_path = manifest.get("shards", {}).get(prefix)
        if shard_path is None:
            raise StorageError("Complete legacy manifest is missing a path shard")
        relative_path(shard_path)
        shard_entry = records.get(shard_path)
        if shard_entry is None:
            raise StorageError("Required legacy path index is missing")
        shard_id = shard_entry["sha256"]
        if shard_id not in self._legacy_indexes:
            values = json.loads(restore_bytes(self.objects, shard_entry))
            if not isinstance(values, dict) or any(sha(k.encode())[:2] != prefix for k in values):
                raise StorageError("Legacy path index identity changed")
            self._legacy_indexes[shard_id] = values
            while len(self._legacy_indexes) > 3:
                victim = next(k for k in self._legacy_indexes if k != identity)
                del self._legacy_indexes[victim]
        entry = self._legacy_indexes[shard_id].get(relative)
        if entry is not None:
            if not re.fullmatch(r"[0-9a-f]{40}", entry.get("git_blob", "")):
                raise StorageError("Legacy Git blob identity is missing")
        return entry

    def restore(self, relative, *, records=None):
        relative_path(relative)
        if records is None:
            _, records = self.snapshot()
        entry = self.lookup_entry(relative, records)
        raw = None if entry is None else restore_bytes(self.objects, entry)
        if raw is not None and entry.get("git_blob"):
            git_identity = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if git_identity != entry["git_blob"]:
                raise StorageError("Restored legacy Git blob identity changed")
        return raw


def merge_ledger(original, incoming):
    def rows(raw):
        result = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        if any(not isinstance(row, dict) for row in result):
            raise StorageError("Invalid real admission ledger")
        return result
    old, new = rows(original), rows(incoming)
    if new[:len(old)] == old:
        return incoming
    preserved = list(old)
    seen = {sha(encoded_json(row)) for row in old}
    for row in new:
        identity = sha(encoded_json(row))
        if identity not in seen:
            preserved.append(row)
            seen.add(identity)
    if preserved == old:
        return original
    return b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode() for row in preserved)


def ensure_private_file(vault, relative, *, root=ROOT, storage=None):
    relative_path(relative)
    vault = Path(vault).resolve()
    destination = vault / relative
    if not destination.resolve().is_relative_to(vault):
        raise StorageError("Private materialization escaped its owned root")
    if destination.is_file():
        return destination
    if not enabled(root) and storage is None:
        return destination
    storage = storage or PrivateStorage(root)
    raw = storage.restore(relative)
    if raw is None:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Create-only: recovery never overwrites a differing existing file.
    try:
        with destination.open("xb") as out:
            out.write(raw)
    except FileExistsError:
        if destination.read_bytes() != raw:
            raise StorageError("Refusing differing existing private bytes")
    return destination
