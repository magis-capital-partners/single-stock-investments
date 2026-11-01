"""Load google_drive_config.json, including its private snapshot.

The public file is a metadata placeholder. Commit 9a46bb7b90c redacted
``drive_roots`` because that key starts with ``drive_`` and stored the
previous config in the research vault. The private object is that config
(CRLF bytes of the parent blob) and still has ``hedge_fund_letters.folder_id``.
Letter Backfill checks out the ``minimal`` profile, which does not include
``dashboard/``, so the vault restore step no-ops and the importer used to
read the placeholder. This loader reads the vault object for a placeholder
and refuses to continue when the letters folder id is missing.
"""
from __future__ import annotations

import json
from pathlib import Path

MISSING_LETTERS_ROOT = "hedge_fund_letters folder_id missing in google_drive_config.json"
CONFIG_RELATIVE = "_system/reference/document-store/google_drive_config.json"


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def letters_folder_id(config: dict) -> str:
    roots = config.get("drive_roots") if isinstance(config, dict) else None
    entry = roots.get("hedge_fund_letters") if isinstance(roots, dict) else None
    folder_id = entry.get("folder_id") if isinstance(entry, dict) else None
    if not isinstance(folder_id, str) or not folder_id.strip():
        return ""
    return folder_id.strip()


def _repo_root(path: Path) -> Path:
    parts = path.resolve().parts
    if "_system" not in parts:
        raise SystemExit(f"{MISSING_LETTERS_ROOT} Config path is outside the repository: {path}")
    return Path(*parts[: parts.index("_system")])


def _resolve_private_config(path: Path, root: Path) -> dict:
    from private_dashboard_assets import read_resolved_json

    relative = path.resolve().relative_to(root.resolve()).as_posix()
    try:
        document, _restored = read_resolved_json(root, relative)
    except Exception as exc:
        raise SystemExit(
            f"{MISSING_LETTERS_ROOT} The public file is a private snapshot and its vault copy was not loaded."
        ) from exc
    if not isinstance(document, dict) or document.get("private_snapshot") is True:
        raise SystemExit(MISSING_LETTERS_ROOT)
    return document


def load_google_drive_config(path: Path, *, root: Path | None = None) -> dict:
    """Return the drive config, or exit when the letters folder id is absent.

    A private-snapshot placeholder is resolved from the vault receipt. The
    resolved document is not written back over the public file.
    """
    path = path.resolve()
    config = _load_json(path)
    if isinstance(config, dict) and config.get("private_snapshot") is True:
        config = _resolve_private_config(path, (root or _repo_root(path)).resolve())
    if not letters_folder_id(config if isinstance(config, dict) else {}):
        raise SystemExit(MISSING_LETTERS_ROOT)
    return config
