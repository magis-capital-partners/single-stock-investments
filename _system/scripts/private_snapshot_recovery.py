"""Recover named private snapshot objects whose bytes were once committed publicly.

A media lane can commit a managed dashboard document in full before its private
object is stored. Those bytes cannot be recalled from public history, but they
are still the private snapshot the receipt must name. This module copies only
the exact objects listed in _system/config/private_snapshot_recovery.json,
pinned by path, commit and SHA-256, into the private vault view. The normal
preserve step then publishes them to private storage. Contents are never logged.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "_system" / "config" / "private_snapshot_recovery.json"
SCHEMA = "private-snapshot-recovery/1"
MAX_BYTES = 64 * 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")


def _safe_dashboard_relative(relative: str) -> str:
    if (not isinstance(relative, str) or not relative or relative.startswith("/") or "\\" in relative
            or ":" in relative or ".." in Path(relative).parts):
        raise ValueError("Unsafe recovery path")
    return relative


def load_items(config: Path = CONFIG) -> dict[str, dict]:
    if not config.is_file():
        return {}
    document = json.loads(config.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA:
        raise ValueError("Unknown private snapshot recovery schema")
    items = {}
    for item in document.get("objects") or []:
        _safe_dashboard_relative(item.get("path"))
        if not HEX64.fullmatch(item.get("private_sha256", "")) or not HEX40.fullmatch(item.get("source_commit", "")):
            raise ValueError("Invalid private snapshot recovery entry")
        items[item["private_sha256"]] = dict(item, repository=document.get("repository"))
    return items


def _from_git(root: Path, commit: str, path: str) -> bytes | None:
    try:
        shown = subprocess.run(["git", "-C", str(root), "cat-file", "blob", f"{commit}:{path}"],
                               capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return shown.stdout if shown.returncode == 0 else None


def _from_public_raw(repository: str, commit: str, path: str) -> bytes | None:
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return None
    url = "https://raw.githubusercontent.com/" + repository + "/" + commit + "/" + urllib.parse.quote(path)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = response.read(MAX_BYTES + 1)
    except OSError:
        return None
    return raw if len(raw) <= MAX_BYTES else None


def recover(vault: Path, private_sha256: str, *, root: Path = ROOT, config: Path = CONFIG,
            fetch_raw=_from_public_raw) -> bool:
    """Write one pinned object into the vault view. False when it is not pinned or cannot be verified."""
    item = load_items(config).get(private_sha256)
    if item is None:
        return False
    destination = Path(vault) / "dashboard-private" / "objects" / private_sha256
    if destination.is_file():
        return hashlib.sha256(destination.read_bytes()).hexdigest() == private_sha256
    path = "dashboard/" + item["path"]
    raw = _from_git(root, item["source_commit"], path)
    if raw is None or hashlib.sha256(raw).hexdigest() != private_sha256:
        raw = fetch_raw(item.get("repository"), item["source_commit"], path)
    if raw is None or hashlib.sha256(raw).hexdigest() != private_sha256:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".recovery.tmp")
    try:
        temporary.write_bytes(raw)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != private_sha256:
            return False
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True
