"""A missing letters folder id fails when the drive config is loaded."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import drive_config  # noqa: E402
import private_dashboard_assets as assets  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = drive_config.CONFIG_RELATIVE
WORKFLOW = ROOT / ".github/workflows/letter-backfill.yml"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(folder_id: str | None) -> dict:
    entry = {"label": "Letters"}
    if folder_id is not None:
        entry["folder_id"] = folder_id
    return {"drive_roots": {"hedge_fund_letters": entry}}


def test_missing_letters_folder_id_fails_at_config_load(tmp_path: Path) -> None:
    path = tmp_path / "google_drive_config.json"
    _write(path, _config(None))
    with pytest.raises(SystemExit, match=drive_config.MISSING_LETTERS_ROOT):
        drive_config.load_google_drive_config(path, root=tmp_path)


def test_blank_letters_folder_id_fails_at_config_load(tmp_path: Path) -> None:
    path = tmp_path / "google_drive_config.json"
    _write(path, _config("  "))
    with pytest.raises(SystemExit, match=drive_config.MISSING_LETTERS_ROOT):
        drive_config.load_google_drive_config(path, root=tmp_path)


def test_present_letters_folder_id_loads(tmp_path: Path) -> None:
    path = tmp_path / "google_drive_config.json"
    _write(path, _config("letters-root"))
    loaded = drive_config.load_google_drive_config(path, root=tmp_path)
    assert drive_config.letters_folder_id(loaded) == "letters-root"


def _placeholder_repo(tmp_path: Path, private: dict | None) -> Path:
    root = tmp_path / "repo"
    public = root / RELATIVE
    placeholder = {"private_snapshot": True, "source_shape": "object", "entry_count": 9, "collection_counts": {}}
    _write(public, placeholder)
    public_hash = hashlib.sha256(public.read_bytes()).hexdigest()
    assets_doc: dict = {"assets": {}, "repository_assets": {}}
    if private is not None:
        raw = json.dumps(private).encode()
        private_hash = hashlib.sha256(raw).hexdigest()
        vault = tmp_path / "vault"
        obj = vault / "dashboard-private" / "objects" / private_hash
        obj.parent.mkdir(parents=True, exist_ok=True)
        obj.write_bytes(raw)
        assets_doc["repository_assets"][RELATIVE] = {
            "private_sha256": private_hash,
            "public_sha256": public_hash,
        }
    _write(root / "dashboard" / "private-assets.json", assets_doc)
    return root


def test_unresolved_placeholder_fails_with_the_letters_folder_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _placeholder_repo(tmp_path, private=None)
    monkeypatch.setattr(assets, "research_vault_root", lambda **_kwargs: None)
    with pytest.raises(SystemExit, match=drive_config.MISSING_LETTERS_ROOT):
        drive_config.load_google_drive_config(root / RELATIVE, root=root)


def test_private_snapshot_without_the_letters_folder_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _placeholder_repo(tmp_path, private={"default_drive_root": "general_pdfs"})
    monkeypatch.setattr(assets, "research_vault_root", lambda **_kwargs: tmp_path / "vault")
    with pytest.raises(SystemExit, match=drive_config.MISSING_LETTERS_ROOT):
        drive_config.load_google_drive_config(root / RELATIVE, root=root)


def test_private_snapshot_restores_the_letters_folder_without_writing_it_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _placeholder_repo(tmp_path, private=_config("letters-root"))
    public = root / RELATIVE
    before = public.read_bytes()
    monkeypatch.setattr(assets, "research_vault_root", lambda **_kwargs: tmp_path / "vault")
    loaded = drive_config.load_google_drive_config(public, root=root)
    assert drive_config.letters_folder_id(loaded) == "letters-root"
    assert public.read_bytes() == before
    assert b"letters-root" not in before


def test_committed_drive_config_stays_a_placeholder_without_a_folder_id() -> None:
    # Read the git blob, not the worktree. A vault hydrate replaces the
    # working file with the private config, and that copy must not be what
    # this check prints or treats as the public file.
    result = subprocess.run(
        ["git", "show", f"HEAD:{RELATIVE}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, "committed google_drive_config.json could not be read"
    text = result.stdout
    assert '"private_snapshot":true' in text or '"private_snapshot": true' in text
    assert "folder_id" not in text
    assert "hedge_fund_letters" not in text


def test_letter_ingest_materializes_the_receipt_and_does_not_hydrate_the_catalog() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    ingest = text.split("\n  ingest-letters:\n", 1)[1].split("\n  publish-dashboard:\n", 1)[0]
    assert "git sparse-checkout add /dashboard/private-assets.json" in ingest
    assert "test -f dashboard/private-assets.json" in ingest
    assert 'hydrate: "false"' in ingest
    publish = text.split("\n  publish-dashboard:\n", 1)[1]
    assert 'hydrate: "false"' not in publish
