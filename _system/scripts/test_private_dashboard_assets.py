from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import private_dashboard_assets as assets
import migrate_dashboard_sources as migration
import audit_fund_letter_exposure as exposure
import build_cloudflare_pages_site as builder


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "public"
    source = root / "dashboard"
    source.mkdir(parents=True)
    vault = tmp_path / "vault"
    (vault / ".git").mkdir(parents=True)
    monkeypatch.setattr(assets, "research_vault_root", lambda: vault)
    monkeypatch.setattr(migration, "research_vault_root", lambda: vault)
    return root, source, vault


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_private_preservation_public_redaction_idempotence_and_new_versions(workspace):
    root, source, vault = workspace
    path = source / "data/letters.json"
    original = {"fund": "Example", "count": 3, "source_url": "https://drive.google.com/file/d/SECRET", "source_file": "_system/reference/superinvestor-letters/a.pdf", "commentary": "verbatim", "position": {"ticker": "X"}}
    write(path, original)
    before = path.read_bytes()
    assert migration.migrate(root, paths=["dashboard/data/letters.json"])["managed_private_assets"] == 1
    entry = assets.overlay_manifest(source)["assets"]["data/letters.json"]
    first = assets.private_object(vault, entry["private_sha256"])
    assert first.read_bytes() == before
    assert json.loads(path.read_text()) == {"fund": "Example", "count": 3, "position": {"ticker": "X"}}
    assert migration.migrate(root, paths=[])["migrated_or_updated_assets"] == 0
    assert assets.private_source(source, "data/letters.json") == first
    assert assets.hydrate(source) == 1
    original["count"] = 4
    write(path, original)
    assert migration.migrate(root, paths=[])["migrated_or_updated_assets"] == 1
    second = assets.private_source(source, "data/letters.json")
    assert json.loads(second.read_text())["count"] == 4
    assert second != first and first.read_bytes() == before


def test_nested_letter_text_is_removed_but_non_letter_numbers_remain():
    doc = {"rows": [{"source_type": "superinvestor_letter", "text": "extract", "items": [{"claim": "another extract", "ticker": "ACME"}]}, {"source_type": "earnings", "text": "reported results", "revenue": 42}]}
    assert migration.redact(doc) == {"rows": [{"source_type": "superinvestor_letter", "items": [{"ticker": "ACME"}]}, {"source_type": "earnings", "text": "reported results", "revenue": 42}]}
    mapped = migration.redact({"_system/reference/superinvestor-letters/2020Q1/a.pdf": "bare-private-drive-id"})
    assert list(mapped.values()) == [None]
    assert "superinvestor-letters" not in json.dumps(mapped)
    assert migration.redact({"drive_file_id":"private-id", "driveFolderId":"private-folder", "folder_id":"private-root", "links":{"letter.pdf":"bare-id"}, "fund":"A"}) == {"fund":"A"}


def test_changed_public_snapshot_cannot_replace_private_copy(workspace):
    root, source, vault = workspace
    path = source / "data/letter.json"
    write(path, {"fund": "A", "source_file": "_system/reference/superinvestor-letters/a.pdf"})
    migration.migrate(root, paths=["dashboard/data/letter.json"])
    private = assets.private_source(source, "data/letter.json")
    write(path, {"fund": "Edited without hydrating"})
    with pytest.raises(RuntimeError, match="Hydrate"):
        migration.migrate(root, paths=[])
    with pytest.raises(RuntimeError, match="changed"):
        assets.private_source(source, "data/letter.json")
    assert "source_file" in json.loads(private.read_text())


def test_missing_or_corrupt_private_snapshot_fails_before_cleaning_artifact(workspace, monkeypatch):
    root, source, vault = workspace
    path = source / "data/letter.json"
    write(path, {"source_url": "https://drive.google.com/file/d/SECRET"})
    migration.migrate(root, paths=["dashboard/data/letter.json"])
    private = assets.private_source(source, "data/letter.json")
    private.write_text("corrupt", encoding="utf-8")
    (source / "index.html").write_text("reader", encoding="utf-8")
    output = root / "site"
    output.mkdir()
    (output / "previous").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(builder, "ROOT", root)
    with pytest.raises(RuntimeError, match="mismatched"):
        builder.build(source, output)
    assert (output / "previous").read_text() == "keep"


def test_interrupted_manifest_write_recovers_from_private_journal(workspace):
    root, source, vault = workspace
    path = source / "data/letter.json"
    write(path, {"fund": "A", "source_url": "https://drive.google.com/file/d/SECRET"})
    migration.migrate(root, paths=["dashboard/data/letter.json"])
    expected = assets.overlay_manifest(source)
    (source / assets.MANIFEST_NAME).unlink()
    assert migration.migrate(root, paths=[])["managed_private_assets"] == 1
    assert assets.overlay_manifest(source) == expected
    assert "SECRET" in assets.private_source(source, "data/letter.json").read_text()


def test_raw_original_is_verified_and_preserved_before_removal(workspace):
    root, source, vault = workspace
    relative = "_system/reference/superinvestor-letters/2020Q1/a.pdf"
    path = root / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original PDF bytes")
    assert migration.migrate(root, paths=[relative])["originals_migrated"] == 1
    assert not path.exists()
    assert (vault / "dashboard-private/originals" / relative).read_bytes() == b"original PDF bytes"


def test_no_vault_never_redacts(workspace, monkeypatch):
    root, source, _ = workspace
    path = source / "data/letter.json"
    write(path, {"source_url": "https://drive.google.com/file/d/SECRET"})
    monkeypatch.setattr(migration, "research_vault_root", lambda: None)
    with pytest.raises(RuntimeError, match="required"):
        migration.migrate(root, paths=["dashboard/data/letter.json"])
    assert "SECRET" in path.read_text()


@pytest.mark.parametrize("relative", ["../escape", "data/../../escape", "C:/escape", "data\\escape", "/absolute"])
def test_unsafe_manifest_paths_rejected(workspace, relative):
    _, source, _ = workspace
    with pytest.raises(ValueError):
        assets.private_source(source, relative)


def test_authorized_artifact_gets_exact_private_bytes(workspace, monkeypatch):
    root, source, _ = workspace
    (source / "index.html").write_text("dashboard", encoding="utf-8")
    write(source / "data/core.json", {"tickers": []})
    write(source / "data/insights/manifest.json", {"source_url": "https://drive.google.com/file/d/SECRET"})
    before = (source / "data/insights/manifest.json").read_bytes()
    migration.migrate(root, paths=["dashboard/data/insights/manifest.json"])
    monkeypatch.setattr(builder, "ROOT", root)
    report = builder.build(source, root / "site")
    assert report["restored_private_assets"] == 1
    assert (root / "site/data/insights/manifest.json").read_bytes() == before
    assert "SECRET" not in (source / "data/insights/manifest.json").read_text()


def test_staged_guard_inspects_staged_bytes_and_private_hash(workspace):
    root, source, _ = workspace
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    path = source / "data/letter.json"
    write(path, {"source_url": "https://drive.google.com/file/d/SECRET"})
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    # A clean working copy does not conceal a leaked staged payload.
    migration.migrate(root, paths=["dashboard/data/letter.json"])
    assert not exposure.audit(root, staged=True)["source_restriction_ready"]
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    assert exposure.audit(root, staged=True)["source_restriction_ready"]
    write(path, {"fund": "silently changed sanitized snapshot"})
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    assert "managed_private_snapshot_not_sanitized" in {r["kind"] for r in exposure.audit(root, staged=True)["findings"]}


def test_repository_jsonl_and_source_linked_research_restore_exactly(workspace):
    root, source, _ = workspace
    catalog = root / "_system/data/chunks.jsonl"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"source_file": "_system/reference/superinvestor-letters/2020Q1/a.txt", "text": "private passage", "ticker": "A"}) + "\n", encoding="utf-8")
    note = root / "A/research/note.md"
    note.parent.mkdir(parents=True)
    note.write_text("Evidence from _system/reference/superinvestor-letters/2020Q1/a.txt\nprivate passage", encoding="utf-8")
    original = {p: p.read_bytes() for p in (catalog, note)}
    result = migration.migrate(root, paths=[p.relative_to(root).as_posix() for p in original])
    assert result["managed_private_assets"] == 2
    assert json.loads(catalog.read_text()) == {"ticker": "A"}
    assert "private passage" not in note.read_text()
    assert migration.migrate(root, paths=[])["migrated_or_updated_assets"] == 0
    assert assets.hydrate_repository(root) == 2
    assert all(p.read_bytes() == content for p, content in original.items())


def test_git_line_ending_conversion_cannot_change_snapshot_checksums(workspace):
    root, source, vault = workspace
    path = source / "data/letter.json"
    path.parent.mkdir(parents=True)
    original = b'{\r\n  "source_url": "https://drive.google.com/file/d/SECRET",\r\n  "fund": "Example"\r\n}\r\n'
    path.write_bytes(original)
    csv_path = source / "data/letters.csv"
    csv_path.write_bytes(b'fund,source_url\r\nExample,https://drive.google.com/file/d/SECRET\r\n')
    migration.migrate(root, paths=["dashboard/data/letter.json", "dashboard/data/letters.csv"])
    private = assets.private_source(source, "data/letter.json")
    for repo in (root, vault):
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=repo, check=True)
        subprocess.run(["git", "add", "--force", "."], cwd=repo, check=True)
        subprocess.run(["git", "checkout-index", "--force", "--all"], cwd=repo, check=True)
    entry = assets.overlay_manifest(source)["assets"]["data/letter.json"]
    assert assets.digest(path) == entry["public_sha256"]
    assert private.read_bytes() == original
    assert assets.digest(private) == entry["private_sha256"]
    assert assets.digest(csv_path) == assets.overlay_manifest(source)["assets"]["data/letters.csv"]["public_sha256"]
