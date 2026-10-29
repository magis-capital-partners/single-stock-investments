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
