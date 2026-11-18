import copy
import hashlib
import io as byte_io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import resume_company_source_publication as recovery
import private_storage as store
import private_storage_io as storage_io
from build_company_research import Builder
from company_source_cache import pack, restore
from company_sources import Matcher
from test_private_storage import Objects
from test_private_storage_io import VersionCatalog

COMPANIES = {"CME": {"company": "CME Group Inc.", "market": "US"},
             "NEM": {"company": "Newmont Corporation", "market": "US"}}
BODY = ("CME Group Inc. operates exchanges and generates cash flow from futures and clearing. "
        "Newmont Corporation operates gold mines and is increasing production at its largest assets.")


@pytest.fixture
def checkpoint(tmp_path, monkeypatch):
    workspace = tmp_path / "worker"
    vault = workspace / "_external/research-vault"
    vault.mkdir(parents=True)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    subprocess.run(["git", "init", "--quiet", str(vault)], check=True)
    producer = tmp_path / "producer"
    cache = producer / "cache"
    archive = producer / "archive"

    def build(companies, instant, destination):
        builder = Builder(producer, None, destination, cache, companies=companies)
        builder.now = instant
        builder.receipt("vault:letters", 1)
        row = builder.base("letter", "Investor letter", "vault:letters", text=BODY)
        builder.add(row, [])
        builder.publish()
        return builder

    old = build({"CME": COMPANIES["CME"]}, "2026-11-17T03:37:31+00:00", producer / "old")
    pack(cache, archive)
    old_manifest = (archive / "manifest.json").read_bytes()
    fake = store.PrivateStorage(config={"catalog_repository_id": 123},
                                objects=Objects(), catalog=VersionCatalog())
    original = json.loads(old_manifest)
    fake.publish({recovery.ARCHIVE + "/" + part["file"]: (archive / part["file"]).read_bytes()
                  for part in original["parts"]})
    fake.publish({recovery.ARCHIVE + "/manifest.json": old_manifest})
    before = copy.deepcopy(fake.catalog.records)
    future = build(COMPANIES, "2026-11-17T19:39:53+00:00", producer / "new")
    pack(cache, archive)
    updated = json.loads((archive / "manifest.json").read_bytes())
    # Replay the failed worker: immutable parts succeeded; its manifest did not.
    fake.publish({recovery.ARCHIVE + "/" + part["file"]: (archive / part["file"]).read_bytes()
                  for part in updated["parts"]})
    after = copy.deepcopy(fake.catalog.records)
    storage_io.initialize(vault, storage=fake)
    monkeypatch.setattr(storage_io, "enabled", lambda: True)
    local_archive = vault / recovery.ARCHIVE
    for part in original["parts"]:
        storage_io.materialize(vault, recovery.ARCHIVE + "/" + part["file"], storage=fake)
    restored = workspace / "_private/company-research/cache"
    restore(local_archive, restored)
    monkeypatch.setattr(recovery, "checkpoint_records", lambda storage, commit: (before, after))
    return vault, restored, fake, before, after, old_manifest, future.match_version


def test_preserved_matches_resume_canonical_build_without_publishing_a_manifest(checkpoint, monkeypatch):
    vault, cache, fake, before, after, manifest, version = checkpoint
    original_text = {p.name: p.read_bytes() for p in (cache / "published-text").glob("*.json")}
    result = recovery.resume(vault, cache, "a" * 40, storage=fake)
    assert result["resumed_parts"] == len(set(after) - set(before))
    assert result["canonical_refresh_required"] is True
    assert (vault / recovery.ARCHIVE / "manifest.json").read_bytes() == manifest
    assert fake.catalog.records == after
    assert json.loads((cache / "matches.json").read_bytes())["version"] == version
    assert {p.name: p.read_bytes() for p in (cache / "published-text").glob("*.json")} == original_text
    builder = Builder(cache.parents[2], None, cache.parent / "verified", cache, companies=COMPANIES)
    # The real canonical build reuses the exact preserved matching result.
    monkeypatch.setattr(Matcher, "match", lambda *a, **k: pytest.fail("Preserved match was recomputed"))
    builder.receipt("vault:letters", 1)
    builder.add(builder.base("letter", "Investor letter", "vault:letters", text=BODY), [])
    report = builder.publish()
    assert report["documents"] == 1 and report["linked_companies"] == 2
    assert builder.publish_cached()["companies"] == 2


@pytest.mark.parametrize("kind", ["mutable", "replacement", "removal", "empty"])
def test_checkpoint_cannot_replay_mutable_or_changed_existing_controls(kind):
    before = {"keep": {"sha256": "b" * 64}}
    after = copy.deepcopy(before)
    if kind == "mutable":
        after[recovery.ARCHIVE + "/manifest.json"] = {"sha256": "a" * 64}
    elif kind == "replacement":
        after["keep"] = {"sha256": "c" * 64}
    elif kind == "removal":
        after.clear()
    with pytest.raises(store.StorageError):
        recovery.added_parts(before, after)


def test_corrupt_uploaded_part_leaves_restored_cache_and_manifest_intact(checkpoint):
    vault, cache, fake, before, after, manifest, _ = checkpoint
    files = {p.relative_to(cache): p.read_bytes() for p in cache.rglob("*") if p.is_file()}
    part = recovery.added_parts(before, after)[0][1]
    fake.objects.data[part["chunks"][0]["stored_sha256"]] = b"corrupt remote bytes"
    with pytest.raises(store.StorageError, match="corrupt"):
        recovery.resume(vault, cache, "a" * 40, storage=fake)
    assert {p.relative_to(cache): p.read_bytes() for p in cache.rglob("*") if p.is_file()} == files
    assert (vault / recovery.ARCHIVE / "manifest.json").read_bytes() == manifest


def test_unsafe_preserved_member_never_reaches_the_restored_cache(checkpoint, monkeypatch):
    vault, cache, fake, _, _, manifest, _ = checkpoint
    raw = byte_io.BytesIO()
    with zipfile.ZipFile(raw, "w") as zipped:
        zipped.writestr("records/../../escape.json", "private")
    identity = hashlib.sha256(raw.getvalue()).hexdigest()
    name = recovery.ARCHIVE + "/" + identity + ".zip"
    before = copy.deepcopy(fake.catalog.records)
    fake.publish({name: raw.getvalue()})
    after = copy.deepcopy(fake.catalog.records)
    storage_io.initialize(vault, storage=fake)
    monkeypatch.setattr(recovery, "checkpoint_records", lambda storage, commit: (before, after))
    files = {p.relative_to(cache): p.read_bytes() for p in cache.rglob("*") if p.is_file()}
    with pytest.raises(store.StorageError, match="Unsafe"):
        recovery.resume(vault, cache, "a" * 40, storage=fake)
    assert {p.relative_to(cache): p.read_bytes() for p in cache.rglob("*") if p.is_file()} == files
    assert (vault / recovery.ARCHIVE / "manifest.json").read_bytes() == manifest


def test_resume_work_must_pass_canonical_refresh_before_manifest_publication():
    root = Path(__file__).resolve().parents[3]
    job = yaml.safe_load((root / ".github/workflows/company-source-backfill.yml").read_text())["jobs"]["backfill"]
    steps = job["steps"]
    resume = next(i for i, s in enumerate(steps) if s.get("id") == "resume")
    refresh = next(i for i, s in enumerate(steps) if s.get("id") == "refresh")
    archive = next(s for s in steps if s.get("id") == "archive")
    scope = next(s for s in steps if s.get("id") == "scope")
    commit = next(s for s in steps if s.get("uses") == "./.github/actions/commit-vault")
    assert resume < refresh
    assert "steps.resume.outcome == 'success'" in archive["if"]
    assert "steps.refresh.outcome == 'success'" in archive["if"]
    assert "steps.parts.outcome == 'success'" in commit["if"]
    assert "steps.parts.outcome == 'success'" in scope["if"]
    assert "private_storage_io.py enabled; then" in scope["run"]
    assert "git_add=--sparse --force " + recovery.ARCHIVE + "/manifest.json" in scope["run"]
    assert "git_add=--sparse --force " + recovery.ARCHIVE + '"' in scope["run"]
    assert commit["with"]["git_add"] == "${{ steps.scope.outputs.git_add }}"


def test_manifest_only_save_does_not_reprocess_uploaded_archive_parts(checkpoint):
    vault, _, fake, _, after, _, _ = checkpoint
    archive = vault / recovery.ARCHIVE
    manifest = archive / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "parts": []}))
    selection = storage_io.selected_files(vault, "--sparse --force " + recovery.ARCHIVE + "/manifest.json")
    assert set(selection) == {recovery.ARCHIVE + "/manifest.json"}
    storage_io.publish_paths(vault, selection, storage=fake)
    for name, entry in after.items():
        if name.endswith(".zip"):
            assert fake.catalog.records[name] == entry
    assert fake.catalog.records[recovery.ARCHIVE + "/manifest.json"]["sha256"] == store.sha(manifest.read_bytes())


def test_checkpoint_reads_exact_commit_and_parent_from_a_shallow_catalog(tmp_path):
    seed, remote, worker = tmp_path / "seed", tmp_path / "remote.git", tmp_path / "catalog.git"
    seed.mkdir()

    def git(root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT).decode().strip()

    git(seed, "init", "--quiet")
    git(seed, "checkout", "-b", "main")
    git(seed, "config", "user.name", "Fixture")
    git(seed, "config", "user.email", "fixture@example.invalid")
    versions = []
    for version in ("before", "checkpoint", "later"):
        (seed / "state.json").write_text(json.dumps({"version": version}))
        git(seed, "add", ".")
        git(seed, "commit", "-qm", version)
        versions.append(git(seed, "rev-parse", "HEAD"))
    subprocess.run(["git", "clone", "--bare", str(seed), str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", "--bare", "--depth=1", remote.as_uri(), str(worker)],
                   check=True, capture_output=True)

    class Catalog:
        directory = worker
        checked = False

        def fetch(self):
            self.checked = True
            return versions[2]

        def read(self, commit):
            assert self.checked
            return json.loads(git(worker, "show", commit + ":state.json"))

    from types import SimpleNamespace
    before, after = recovery.checkpoint_records(SimpleNamespace(catalog=Catalog()), versions[1])
    assert before == {"version": "before"}
    assert after == {"version": "checkpoint"}


@pytest.mark.parametrize("commit", ["main", "a" * 39, "../main", "F" * 40])
def test_checkpoint_requires_an_exact_commit_before_accessing_storage(commit):
    from types import SimpleNamespace
    with pytest.raises(store.StorageError, match="exact"):
        recovery.checkpoint_records(SimpleNamespace(), commit)
