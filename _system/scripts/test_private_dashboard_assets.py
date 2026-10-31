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
    assert json.loads(path.read_text()) == {"private_snapshot": True, "source_shape": "object", "entry_count": 6, "collection_counts": {}}
    assert migration.migrate(root, paths=[])["migrated_or_updated_assets"] == 0
    assert assets.private_source(source, "data/letters.json") == first
    assert assets.hydrate(source) == 1
    journal = vault / "dashboard-private/migration-journal.jsonl"
    previous_journal = journal.read_bytes()
    migration.migrate(root, paths=[])
    assert journal.read_bytes() == previous_journal
    assets.hydrate(source)
    original["count"] = 4
    write(path, original)
    assert migration.migrate(root, paths=[])["migrated_or_updated_assets"] == 1
    second = assets.private_source(source, "data/letters.json")
    assert json.loads(second.read_text())["count"] == 4
    assert second != first and first.read_bytes() == before


def test_public_snapshot_is_an_allowlist_even_for_unknown_extract_fields():
    doc = {"fund": "Source identity", "raw_field_we_have_never_seen": "verbatim secret", "risks": ["copied source paragraph"], "drive_file_id": "secret", "letters": [{"anything": "private"}]}
    clean = migration.public_snapshot(doc)
    assert clean == {"private_snapshot": True, "source_shape": "object", "entry_count": 5, "collection_counts": {"letters": 1}}
    assert "secret" not in json.dumps(clean) and "verbatim" not in json.dumps(clean)


def test_explicit_missing_input_restore_preserves_verified_source_and_other_assets(workspace):
    root, source, vault = workspace
    relative = "data/holdings/directory_index.json"
    path = source / relative
    original = {"fund_ids": ["private-fund"], "managers": []}
    write(path, original)
    other = source / "data/other.json"
    write(other, {"fund": "Other private source"})
    migration.migrate(root, paths=["dashboard/" + relative, "dashboard/data/other.json"])
    receipt = assets.overlay_manifest(source)["assets"][relative]
    path.unlink()  # The generated, ignored index is absent in a fresh checkout.
    assert assets.restore_managed_input(source, relative) == 0
    assert not path.exists()
    assert assets.restore_managed_input(source, relative, include_missing=True) == 1
    assert json.loads(path.read_text()) == original
    assert json.loads(other.read_text())["private_snapshot"] is True
    write(path, {**original, "updated": True})
    # An already restored build input keeps legitimate edits on a second pass.
    assert assets.restore_managed_input(source, relative, include_missing=True) == 0
    migration.migrate(root, paths=["dashboard/" + relative])
    assert json.loads(assets.private_source(source, relative).read_text())["updated"]
    assert assets.digest(assets.private_object(vault, receipt["private_sha256"])) == receipt["private_sha256"]


def test_missing_input_restore_requires_valid_private_bytes(workspace):
    _, source, vault = workspace
    relative = "data/holdings/directory_index.json"
    path = source / relative
    write(path, {"fund_ids": ["private-fund"]})
    migration.migrate(source.parent, paths=["dashboard/" + relative])
    receipt = assets.overlay_manifest(source)["assets"][relative]
    path.unlink()
    assets.private_object(vault, receipt["private_sha256"]).write_text("corrupt")
    with pytest.raises(RuntimeError, match="mismatched"):
        assets.restore_managed_input(source, relative, include_missing=True)
    assert not path.exists()


def test_cold_investor_export_can_publish_and_build_a_managed_ignored_directory(workspace, monkeypatch):
    import global_disclosures as disclosures
    import investor_history as history
    import ownership_common as ownership

    root, source, _ = workspace
    data = source / "data/holdings"
    path = data / "directory_index.json"
    write(path, {"fund_ids": ["old-source"], "managers": []})
    migration.migrate(root, paths=["dashboard/data/holdings/directory_index.json"])
    path.unlink()
    monkeypatch.setattr(history, "ROOT", root)
    monkeypatch.setattr(disclosures, "ROOT", root)
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    db = history.connect(root / "archive.sqlite")
    history.export(db, [], data)
    universe = {"managers": [{"manager_id": "example", "display_name": "Example"}], "source_ids": {"private-fund": "example"}}
    disclosures.publish([], universe, data=data, save_archive=False)
    restored = json.loads(assets.private_source(source, "data/holdings/directory_index.json").read_text())
    assert restored["managers"][0]["fund_ids"] == ["private-fund"]
    assert "private-fund" not in path.read_text()
    path.unlink()  # A subsequent deployment starts from another fresh checkout.
    (source / "index.html").write_text("<!doctype html>", encoding="utf-8")
    write(source / "data/core.json", {"tickers": []})
    write(source / "data/insights/manifest.json", {"schema": 1})
    monkeypatch.setattr(builder, "ROOT", root)
    output = root / "site"
    builder.build(source, output)
    shipped = json.loads((output / "data/holdings/directory_index.json").read_text())
    assert shipped["managers"][0]["fund_ids"] == ["private-fund"]
    assert json.loads((output / "_routes.json").read_text())["exclude"] == []


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
    with pytest.raises(RuntimeError, match="changed"):
        assets.restore_managed_input(source, "data/letter.json", include_missing=True)
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


def test_legacy_redacted_payload_is_upgraded_from_verified_private_original(workspace):
    root, source, _ = workspace
    path = source / "data/letter.json"
    write(path, {"source_url": "https://drive.google.com/file/d/SECRET", "unrecognized_prose": "original private prose"})
    migration.migrate(root, paths=["dashboard/data/letter.json"])
    private = assets.private_source(source, "data/letter.json")
    original = private.read_bytes()
    write(path, {"risks": ["A source paragraph left by an older sanitizer"]})
    manifest = assets.overlay_manifest(source)
    manifest.pop("publication_format")
    manifest["assets"]["data/letter.json"]["public_sha256"] = assets.digest(path)
    write(source / assets.MANIFEST_NAME, manifest)
    migration.migrate(root, paths=[])
    assert json.loads(path.read_text())["private_snapshot"] is True
    assert "source paragraph" not in path.read_text()
    assert assets.private_source(source, "data/letter.json").read_bytes() == original


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
    assert json.loads(catalog.read_text()) == {"private_snapshot": True, "source_shape": "array", "entry_count": 1}
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
