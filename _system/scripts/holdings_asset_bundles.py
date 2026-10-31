"""Lossless physical packaging of logical holdings JSON assets for Pages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def _path(data, relative, roots):
    path = PurePosixPath(relative)
    if (
        "\\" in relative
        or path.is_absolute()
        or path.as_posix() != relative
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[0] not in roots
        or path.suffix != ".json"
    ):
        raise ValueError(f"Invalid holdings asset path: {relative}")
    target = (data / relative).resolve()
    if not target.is_relative_to(data.resolve()):
        raise ValueError(f"Holdings asset escapes its directory: {relative}")
    return target


def unpack_assets(data):
    """Restore logical files before regenerating a previously staged directory."""
    data = Path(data)
    index_path = data / "directory_index.json"
    if not index_path.exists():
        return
    index = json.loads(index_path.read_text(encoding="utf-8"))
    mapping = index.get("asset_bundles", {})
    groups = {}
    for relative, bundle in mapping.items():
        _path(data, relative, {"history", "disclosures"})
        _path(data, bundle, {"bundles"})
        groups.setdefault(bundle, set()).add(relative)
    for bundle, expected in groups.items():
        assets = json.loads((data / bundle).read_text(encoding="utf-8"))["assets"]
        if set(assets) != expected:
            raise ValueError(f"Holdings bundle inventory mismatch: {bundle}")
        for relative, payload in assets.items():
            target = _path(data, relative, {"history", "disclosures"})
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if mapping:
        del index["asset_bundles"]
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        for bundle in groups:
            _path(data, bundle, {"bundles"}).unlink()


def pack_assets(data, *, max_bytes=8 * 1024 * 1024):
    """Keep every logical JSON body, sharing bounded bundles across managers.

    Root indexes and legacy by_manager/by_ticker endpoints stay directly readable.
    Only the historical directory consumes the new logical-to-physical mapping.
    """
    data = Path(data)
    unpack_assets(data)
    index_path = data / "directory_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    paths = sorted(
        path
        for directory in ("history", "disclosures")
        for path in (data / directory).rglob("*.json")
    )
    mapping = {}
    entries = []
    relatives = []
    size = len(b'{"assets":{}}')
    total_bytes = 0

    def flush():
        nonlocal total_bytes
        body = b'{"assets":{' + b",".join(entries) + b"}}"
        relative = f"bundles/{hashlib.sha256(body).hexdigest()}.json"
        target = _path(data, relative, {"bundles"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        mapping.update(dict.fromkeys(relatives, relative))
        total_bytes += len(body)

    for path in paths:
        relative = path.relative_to(data).as_posix()
        _path(data, relative, {"history", "disclosures"})
        body = path.read_bytes().strip()
        json.loads(body)  # Reject a corrupt source before changing its index.
        entry = json.dumps(relative, ensure_ascii=False).encode("utf-8") + b":" + body
        if len(entry) + len(b'{"assets":{}}') > max_bytes:
            raise ValueError(f"Holdings asset exceeds bundle size bound: {relative}")
        addition = len(entry) + bool(entries)
        if entries and size + addition > max_bytes:
            flush()
            entries, relatives = [], []
            size = len(b'{"assets":{}}')
            addition = len(entry)
        entries.append(entry)
        relatives.append(relative)
        size += addition
    if entries:
        flush()
    index["asset_bundles"] = mapping
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    # Publish the complete mapping before removing any logical source files.
    for path in paths:
        path.unlink()
    retained = set(mapping.values())
    for path in (data / "bundles").glob("*.json"):
        relative = path.relative_to(data).as_posix()
        if relative not in retained:
            _path(data, relative, {"bundles"}).unlink()
    return {
        "logical_assets": len(mapping),
        "asset_bundles": len(retained),
        "bundle_bytes": total_bytes,
    }


def validate_site_budget(site, *, max_files=20_000, max_bytes=20 * 1024 * 1024):
    files = [path for path in Path(site).rglob("*") if path.is_file()]
    if len(files) > max_files:
        raise RuntimeError(
            f"Site has {len(files)} files; deployment limit is {max_files}"
        )
    oversized = [path for path in files if path.stat().st_size >= max_bytes]
    if oversized:
        raise RuntimeError(
            f"{len(oversized)} site assets exceed the deployment size bound"
        )
    return len(files)
