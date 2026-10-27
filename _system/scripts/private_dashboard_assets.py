"""Private full dashboard snapshots with safe, provenance-free public counterparts."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

from vault_paths import research_vault_root

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_NAME = "private-assets.json"


def safe_relative(relative: str) -> Path:
    if not relative or relative.startswith("/") or Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe private asset path")
    return Path(relative)


def private_object(vault: Path, sha256: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("Invalid private object digest")
    return vault / "dashboard-private" / "objects" / sha256


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
