"""Private full dashboard snapshots with safe, provenance-free public counterparts."""
from __future__ import annotations

import hashlib
import gzip
import io
import json
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from vault_paths import research_vault_root

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_NAME = "private-assets.json"
COMPRESS_AFTER_BYTES = 80 * 1024 * 1024
MAX_STORED_BYTES = 99 * 1024 * 1024
MAX_UNPACKED_BYTES = 512 * 1024 * 1024


def safe_relative(relative: str) -> Path:
    if not relative or relative.startswith("/") or Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe private asset path")
    return Path(relative)


def stored_object(vault: Path, sha256: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("Invalid private object digest")
    return vault / "dashboard-private" / "objects" / sha256


def decode_object_bytes(raw: bytes, sha256: str) -> bytes:
    """The object name always identifies the exact original, unpacked bytes."""
    if raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(MAX_UNPACKED_BYTES+1)
    if len(raw) > MAX_UNPACKED_BYTES:
        raise RuntimeError('Private snapshot exceeds the unpacked size bound')
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise RuntimeError('Private snapshot hash mismatch')
    return raw


def private_object(vault: Path, sha256: str) -> Path:
    stored = stored_object(vault, sha256)
    if not stored.is_file():
        return stored
    with stored.open('rb') as stream:
        compressed = stream.read(2) == b'\x1f\x8b'
    if not compressed:
        return stored
    # Never stage unpacked bytes in the vault. This is a disposable, per-vault
    # temporary cache; all consumers still verify the original content hash.
    identity = hashlib.sha256(str(vault.resolve()).encode()).hexdigest()[:20]
    cache = Path(tempfile.gettempdir())/'magis-private-snapshots'/identity
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = cache/sha256
    if target.is_file() and digest(target) == sha256:
        return target
    data = decode_object_bytes(stored.read_bytes(), sha256)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return target


def preserve_object(vault: Path, source: Path) -> str:
    raw = source.read_bytes()
    if len(raw) > MAX_UNPACKED_BYTES:
        raise RuntimeError('Private snapshot exceeds the unpacked size bound')
    sha256 = hashlib.sha256(raw).hexdigest()
    stored = stored_object(vault, sha256)
    if stored.is_file():
        if digest(private_object(vault, sha256)) != sha256:
            raise RuntimeError('Existing private snapshot hash mismatch')
        if stored.stat().st_size < MAX_STORED_BYTES:
            return sha256
    encoded = gzip.compress(raw, compresslevel=6, mtime=0) if len(raw) > COMPRESS_AFTER_BYTES else raw
    if len(encoded) >= MAX_STORED_BYTES:
        raise RuntimeError('Private snapshot exceeds the GitHub object limit after lossless compression; split the source before publishing')
    stored.parent.mkdir(parents=True, exist_ok=True)
    temporary = stored.with_name(stored.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(encoded)
        if hashlib.sha256(decode_object_bytes(temporary.read_bytes(), sha256)).hexdigest() != sha256:
            raise RuntimeError('Private snapshot preservation hash mismatch')
        temporary.replace(stored)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlay_manifest(source: Path) -> dict:
    path = source / MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assets": {}}


def hydration_state(root: Path) -> dict:
    path = root / "_private/fund_letters/hydration.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_hydration(root: Path, state: dict) -> None:
    path = root / "_private/fund_letters/hydration.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def restore_copy(private: Path, public: Path, root: Path) -> None:
    temporary = root / "_private/fund_letters/restore" / uuid.uuid4().hex
    temporary.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(private, temporary)
        temporary.replace(public)
    finally:
        temporary.unlink(missing_ok=True)


def _receipt_manifest(source: Path) -> dict:
    if (source / MANIFEST_NAME).is_file():
        return overlay_manifest(source)
    nested = source / "dashboard" / MANIFEST_NAME
    if nested.is_file():
        return overlay_manifest(source / "dashboard")
    return {"assets": {}}


def _manifest_view(source: Path, relative: str) -> dict:
    """assets view for a dashboard file, or repository_assets for a repo file."""
    manifest = _receipt_manifest(source)
    if relative in (manifest.get("assets") or {}):
        return manifest
    repository = manifest.get("repository_assets") or {}
    if relative in repository:
        return {"assets": repository}
    return {"assets": {}}


def read_resolved_json(source: Path, relative: str) -> tuple[dict, bool]:
    """Read a JSON file, following a private snapshot without copying it.

    The second value is true when the bytes came from the vault object. A
    hydrated checkout returns the public file and false, because that file
    already holds the private bytes. Callers must not write the resolved
    document back over a public placeholder. A placeholder with no vault
    receipt, or a placeholder whose vault object is missing, raises rather
    than handing back the metadata stub.
    """
    safe_relative(relative)
    public = source / relative
    if not public.is_file():
        return {}, False
    document = json.loads(public.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("private_snapshot") is not True:
        return document if isinstance(document, dict) else {}, False
    view = _manifest_view(source, relative)
    if relative not in view.get("assets", {}):
        raise RuntimeError(f"Private snapshot placeholder has no vault receipt: {relative}")
    resolved = private_source(source, relative, view)
    if resolved == public:
        return document, False
    loaded = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Private snapshot is not a JSON object: {relative}")
    if loaded.get("private_snapshot") is True:
        raise RuntimeError(f"Private snapshot was not restored: {relative}")
    return loaded, True


def private_source(source: Path, relative: str, manifest: dict | None = None) -> Path:
    safe_relative(relative)
    entry = (manifest or overlay_manifest(source)).get("assets", {}).get(relative)
    public = source / relative
    if not entry:
        return public
    vault = research_vault_root()
    if vault is None:
        raise RuntimeError(f"Private research vault required to restore {relative}")
    private = private_object(vault, entry["private_sha256"])
    if not private.is_file() or digest(private) != entry["private_sha256"]:
        raise RuntimeError(f"Private snapshot is missing or mismatched: {relative}")
    current = digest(public) if public.exists() else None
    if current == entry["private_sha256"]:
        return public  # Explicitly hydrated local build, not a public-ready payload.
    if current != entry["public_sha256"]:
        raise RuntimeError(f"Managed dashboard asset changed; export its private snapshot before deployment: {relative}")
    return private


def restore_managed_input(source: Path, relative: str, *, include_missing=False) -> int:
    """Restore one explicitly selected build input, retaining its write receipt."""
    public = source / safe_relative(relative)
    manifest = overlay_manifest(source)
    entry = manifest.get("assets", {}).get(relative)
    if not entry or (not public.exists() and not include_missing):
        return 0
    if public.exists() and not public.is_file():
        raise RuntimeError(f"Managed dashboard input is not a file: {relative}")
    vault = research_vault_root()
    if vault is None:
        raise RuntimeError(f"Private research vault required to restore {relative}")
    private = private_object(vault, entry["private_sha256"])
    if not private.is_file() or digest(private) != entry["private_sha256"]:
        raise RuntimeError(f"Private snapshot is missing or mismatched: {relative}")
    state = hydration_state(source.parent)
    key = source.name + "/" + relative
    if public.is_file():
        if state.get(key) == entry["private_sha256"] and digest(public) != entry["public_sha256"]:
            return 0  # This verified input already contains the build's edits.
        private = private_source(source, relative, manifest)
    changed = private != public
    if changed:
        public.parent.mkdir(parents=True, exist_ok=True)
        restore_copy(private, public, source.parent)
    state[key] = entry["private_sha256"]
    write_hydration(source.parent, state)
    return int(changed)


def hydrate(source: Path) -> int:
    import shutil
    manifest = overlay_manifest(source)
    state = hydration_state(source.parent)
    count = 0
    for relative in manifest.get("assets", {}):
        if not (source / safe_relative(relative)).is_file():
            continue  # Sparse checkouts need only the inputs they selected.
        private = private_source(source, relative, manifest)
        public = source / relative
        if private != public:
            restore_copy(private, public, source.parent)
            count += 1
        state[source.name + "/" + relative] = manifest["assets"][relative]["private_sha256"]
    write_hydration(source.parent, state)
    return count


def hydrate_repository(root: Path) -> int:
    import shutil
    manifest = {"assets": overlay_manifest(root / "dashboard").get("repository_assets", {})}
    state = hydration_state(root)
    count = 0
    for relative in manifest["assets"]:
        if not (root / safe_relative(relative)).is_file():
            continue
        private = private_source(root, relative, manifest)
        public = root / relative
        if private != public:
            restore_copy(private, public, root)
            count += 1
        state[relative] = manifest["assets"][relative]["private_sha256"]
    write_hydration(root, state)
    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-only", action="store_true")
    args = parser.parse_args()
    count = hydrate_repository(ROOT) + (0 if args.repository_only else hydrate(ROOT / 'dashboard'))
    print(f"Restored {count} private snapshots for authorized processing.")
