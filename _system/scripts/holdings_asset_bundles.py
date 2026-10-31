"""Lossless physical packaging of logical holdings JSON assets for Pages."""

from __future__ import annotations

import hashlib
import gzip
import io
import json
from pathlib import Path, PurePosixPath

MAX_MEMBER_BYTES = 20 * 1024 * 1024


def _decompress(member):
    with gzip.GzipFile(fileobj=io.BytesIO(member)) as stream:
        body = stream.read(MAX_MEMBER_BYTES)
    if len(body) >= MAX_MEMBER_BYTES:
        raise ValueError("Holdings member exceeds decoded size bound")
    json.loads(body)
    return body


def _path(data, relative, roots):
    path = PurePosixPath(relative)
    if (
        "\\" in relative
        or path.is_absolute()
        or path.as_posix() != relative
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[0] not in roots
        or path.suffix not in ({".json", ".bin"} if roots == {"bundles"} else {".json"})
    ):
        raise ValueError(f"Invalid holdings asset path: {relative}")
    target = (data / relative).resolve()
    if not target.is_relative_to(data.resolve()):
        raise ValueError(f"Holdings asset escapes its directory: {relative}")
    return target


def iter_packed_assets(data):
    """Read every logical body with bounded memory, also for privacy validation."""
    data = Path(data)
    index_path = data / "directory_index.json"
    if not index_path.exists():
        return
    index = json.loads(index_path.read_text(encoding="utf-8"))
    mapping = index.get("asset_bundles", {})
    groups = {}
    for relative, location in mapping.items():
        bundle = location if isinstance(location, str) else location[0]
        _path(data, relative, {"history", "disclosures"})
        _path(data, bundle, {"bundles"})
        groups.setdefault(bundle, {})[relative] = location
    for bundle, expected in groups.items():
        body = (data / bundle).read_bytes()
        if bundle.endswith(".json"):
            assets = json.loads(body)["assets"]
            if set(assets) != set(expected):
                raise ValueError(f"Holdings bundle inventory mismatch: {bundle}")
            for relative, value in assets.items():
                yield relative, json.dumps(value, ensure_ascii=False).encode("utf-8")
        else:
            ranges = []
            for relative, (_, offset, length) in expected.items():
                if (
                    not isinstance(offset, int)
                    or not isinstance(length, int)
                    or offset < 0
                    or length <= 0
                    or offset + length > len(body)
                ):
                    raise ValueError(f"Invalid holdings member range: {relative}")
                ranges.append((offset, length, relative))
            cursor = 0
            for offset, length, relative in sorted(ranges):
                if offset != cursor:
                    raise ValueError(f"Holdings bundle inventory mismatch: {bundle}")
                cursor += length
            if cursor != len(body):
                raise ValueError(f"Holdings bundle inventory mismatch: {bundle}")
            for offset, length, relative in ranges:
                yield relative, _decompress(body[offset : offset + length])


def unpack_assets(data):
    """Restore exact logical bytes before regenerating a staged directory."""
    data = Path(data)
    index_path = data / "directory_index.json"
    if not index_path.exists():
        return
    index = json.loads(index_path.read_text(encoding="utf-8"))
    mapping = index.get("asset_bundles", {})
    for relative, payload in iter_packed_assets(data):
        target = _path(data, relative, {"history", "disclosures"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    if mapping:
        del index["asset_bundles"]
        index.pop("asset_bundle_format", None)
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        for bundle in {
            location if isinstance(location, str) else location[0]
            for location in mapping.values()
        }:
            _path(data, bundle, {"bundles"}).unlink()


def pack_assets(data, *, max_bytes=16 * 1024 * 1024):
    """Store individually gzip-compressed JSON bodies in bounded binary bundles.

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
    size = 0
    total_bytes = 0

    def flush():
        nonlocal total_bytes
        body = b"".join(entries)
        relative = f"bundles/{hashlib.sha256(body).hexdigest()}.bin"
        target = _path(data, relative, {"bundles"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        offset = 0
        for name, member in zip(relatives, entries):
            mapping[name] = [relative, offset, len(member)]
            offset += len(member)
        total_bytes += len(body)

    for path in paths:
        relative = path.relative_to(data).as_posix()
        _path(data, relative, {"history", "disclosures"})
        body = path.read_bytes()
        if len(body) >= MAX_MEMBER_BYTES:
            raise ValueError(f"Holdings asset exceeds decoded size bound: {relative}")
        json.loads(body)  # Reject a corrupt source before changing its index.
        entry = gzip.compress(body, compresslevel=6, mtime=0)
        if len(entry) > max_bytes:
            raise ValueError(f"Holdings asset exceeds bundle size bound: {relative}")
        addition = len(entry)
        if entries and size + addition > max_bytes:
            flush()
            entries, relatives = [], []
            size = 0
            addition = len(entry)
        entries.append(entry)
        relatives.append(relative)
        size += addition
    if entries:
        flush()
    index["asset_bundles"] = mapping
    index["asset_bundle_format"] = "gzip-members-v1"
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    # Publish the complete mapping before removing any logical source files.
    for path in paths:
        path.unlink()
    retained = {location[0] for location in mapping.values()}
    for path in (data / "bundles").glob("*"):
        if path.suffix not in {".bin", ".json"}:
            continue
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
