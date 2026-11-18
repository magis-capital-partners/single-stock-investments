"""Resume verified publication work after archive upload but before manifest save.

This restores scratch matching inputs only. The normal inventory, matcher and
publication build must still succeed before any new manifest is published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from company_source_cache import PUBLICATION_FOLDERS, PUBLICATION_ROOT_FILES, restore_parts
from private_storage import PrivateStorage, StorageError, relative_path, run_git
from private_storage_io import materialize, owned, view

ARCHIVE = "dashboard-private/company-source-backfill-v2"
PART = re.compile(re.escape(ARCHIVE) + r"/([0-9a-f]{64})\.zip")
COMMIT = re.compile(r"[0-9a-f]{40}")


def checkpoint_records(storage, commit):
    """Read exactly one authenticated catalog commit and its parent."""
    if not COMMIT.fullmatch(commit):
        raise StorageError("An exact source checkpoint catalog commit is required")
    storage.catalog.fetch()  # Validates the private catalog identity and remote.
    directory = storage.catalog.directory
    run_git(directory, "fetch", "--no-tags", "--depth=2", "origin", commit)
    parent = run_git(directory, "rev-parse", commit + "^").stdout.decode().strip()
    return storage.catalog.read(parent), storage.catalog.read(commit)


def added_parts(before, after):
    """Accept only the immutable-part upload phase, never mutable controls."""
    if set(before) - set(after) or any(after[name] != value for name, value in before.items()):
        raise StorageError("A source recovery checkpoint cannot replace existing catalog entries")
    names = sorted(set(after) - set(before))
    if not names:
        raise StorageError("The source recovery checkpoint contains no uploaded parts")
    result = []
    for name in names:
        match = PART.fullmatch(name)
        if not match or after[name].get("sha256") != match.group(1):
            raise StorageError("A source recovery checkpoint must contain only immutable archive parts")
        result.append((name, after[name]))
    return result


def publication_member(name):
    relative_path(name)
    return name in PUBLICATION_ROOT_FILES or Path(name).parts[0] in PUBLICATION_FOLDERS


def resume(vault, cache, commit, *, storage=None):
    vault = owned(vault)
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", "")).resolve()
    cache = Path(cache)
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or vault != workspace / "_external/research-vault"
            or cache.is_symlink()
            or cache.resolve() != workspace / "_private/company-research/cache"
            or not cache.is_dir()
            or not (cache / "index.json").is_file()
            or not (cache / "matches.json").is_file()):
        raise StorageError("Publication recovery requires the restored cache in its owned CI checkout")
    cache = cache.resolve()
    storage = storage or PrivateStorage()
    before, after = checkpoint_records(storage, commit)
    parts = added_parts(before, after)
    selected = view(vault, storage)
    descriptors, members = [], set()
    archive = vault / ARCHIVE
    for name, entry in parts:
        if selected.get(name) != entry:
            raise StorageError("Uploaded source parts differ from this checkout's verified catalog view")
        path = materialize(vault, name, storage=storage)
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != entry["sha256"]:
                raise StorageError("Uploaded source archive checksum changed")
        with zipfile.ZipFile(path) as zipped:
            for item in zipped.infolist():
                if publication_member(item.filename):
                    if item.filename in members:
                        raise StorageError("Uploaded source checkpoint repeats a publication cache path")
                    members.add(item.filename)
        descriptors.append({"file": path.name, "sha256": entry["sha256"]})

    # A failed or interrupted restore cannot mix a new control file with an old
    # cache. Stage all bodies and verify their ZIP CRCs before adopting any file.
    with tempfile.TemporaryDirectory(prefix=".publication-resume-", dir=cache.parent) as temporary:
        staged = Path(temporary)
        restore_parts(archive, staged, descriptors, publication_only=True)
        controls = json.loads((staged / "matches.json").read_text(encoding="utf-8"))
        index = json.loads((staged / "index.json").read_text(encoding="utf-8"))
        if (not re.fullmatch(r"[0-9a-f]{64}", controls.get("version", ""))
                or not isinstance(controls.get("identities"), dict) or not controls["identities"]
                or not isinstance(controls.get("parts"), list) or not controls["parts"]
                or any(not re.fullmatch(r"relationships/[0-9a-f]{2}\.json", name)
                       for name in controls["parts"])
                or not isinstance(index.get("record_parts"), list) or not index["record_parts"]
                or any(not re.fullmatch(r"records/[0-9a-f]{2}\.json", name)
                       for name in index["record_parts"])
                or not index.get("generated_at")):
            raise StorageError("Uploaded work has no complete publication matching controls")
        files = [path for path in staged.rglob("*") if path.is_file()]
        targets = []
        for path in files:
            relative = path.relative_to(staged)
            target = cache / relative
            if (target.is_symlink() or not target.resolve().is_relative_to(cache)
                    or any(parent.is_symlink() for parent in target.parents if parent != cache)):
                raise StorageError("Publication recovery escaped its owned cache")
            targets.append((relative, path, target))
        # The matching control is adopted last. The workflow also requires the
        # subsequent canonical refresh to succeed before saving this recovery.
        for relative, source, target in sorted(
                targets, key=lambda row: (row[0].as_posix() in PUBLICATION_ROOT_FILES,
                                          row[0].as_posix() == "matches.json", row[0].as_posix())):
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
    return {"resumed_parts": len(parts), "publication_files": len(files),
            "catalog_commit": commit, "canonical_refresh_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--catalog-commit", required=True)
    args = parser.parse_args()
    print(resume(args.vault, args.cache, args.catalog_commit))
