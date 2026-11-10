import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_company_research import Builder
from company_source_cache import pack, restore
from push_company_source_parts import publish
from resolve_vault_manifest_conflict import merge_journal, reconcile, resolve

COMPANIES = {"CME": {"company": "CME Group Inc.", "market": "US"}}
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def legacy_archive_transport_fixture(monkeypatch):
    # Retain explicit coverage for the read-only legacy transport protocol.
    # The activated object-store path is covered by the owned-view suite.
    import private_storage
    monkeypatch.setattr(private_storage, 'enabled', lambda *a, **k: False)


def snapshot(tmp_path):
    b = Builder(tmp_path, None, tmp_path / "first", tmp_path / "cache", companies=COMPANIES)
    b.now = "2026-10-28T00:00:00+00:00"
    b.receipt("vault:letters", 1)
    rec = b.base("letter", "CME company report", "vault:letters", explicit=["CME"],
                 text="CME Group earnings increased and its clearing business generated more cash flow.")
    b.add(rec, [])
    b.publish()
    return b


def test_snapshot_preserves_sources_full_text_and_observation_dates(tmp_path):
    old = snapshot(tmp_path)
    b = Builder(tmp_path, None, tmp_path / "second", old.cache, companies=COMPANIES)
    b.registries = b.local_corpora = b.git_inventory = b.drive = lambda **kw: pytest.fail("Live discovery during publication")
    result = b.publish_cached()
    assert result["documents"] == 1
    assert result["generated_at"] == old.now
    assert result["receipts"] == old.receipts
    company = json.loads((b.output / "companies/CME.json").read_text())
    rows = json.loads((b.output / company["pages"][0]).read_text())
    content = json.loads((b.output / rows[0]["content_path"]).read_text())
    assert "clearing business" in content[rows[0]["id"]]["text"]


def test_snapshot_refuses_missing_bodies_and_changed_identity_rules(tmp_path):
    old = snapshot(tmp_path)
    b = Builder(tmp_path, None, tmp_path / "second", old.cache, companies=COMPANIES)
    b.match_version = "changed"
    with pytest.raises(RuntimeError, match="identities"):
        b.publish_cached()
    b.match_version = old.match_version
    next((old.cache / "published-text").glob("*.json")).unlink()
    with pytest.raises(RuntimeError, match="missing a recovered text"):
        b.publish_cached()


def test_snapshot_refuses_a_missing_record_partition(tmp_path):
    old = snapshot(tmp_path)
    b = Builder(tmp_path, None, tmp_path / "second", old.cache, companies=COMPANIES)
    b.previous["record_parts"].append("records/missing.json")
    with pytest.raises(RuntimeError, match="missing a record partition"):
        b.publish_cached()


def test_publication_restore_preserves_full_text_without_unpacking_originals(tmp_path):
    old = snapshot(tmp_path)
    (old.cache / "git").mkdir()
    (old.cache / "git/original.json").write_text('{"text":"original extraction"}')
    archive = tmp_path / "archive"
    pack(old.cache, archive)
    target = tmp_path / "restored"
    restore(archive, target, publication_only=True)
    assert not (target / "git").exists()
    result = Builder(tmp_path, None, tmp_path / "published", target, companies=COMPANIES).publish_cached()
    assert result["documents"] == 1


def test_line_endings_do_not_create_historical_source_editions(tmp_path):
    b = Builder(tmp_path, None, tmp_path / "first", tmp_path / "cache", companies=COMPANIES)
    text = "CME Group earnings increased.\nIts clearing business generated more cash flow."
    location = [{"url": "https://example.test/original.txt"}]
    for identity, body in [("windows", text.replace("\n", "\r\n"))]:
        rec = b.base(identity, "Company source", "vault:letters", text=body, explicit=["CME"], locations=location)
        rec["format"] = "txt"
        b.add(rec, [])
    b.publish()
    b = Builder(tmp_path, None, tmp_path / "second", b.cache, companies=COMPANIES)
    rec = b.base("linux", "Company source", "vault:letters", text=text, explicit=["CME"], locations=location)
    rec["format"] = "txt"
    b.add(rec, [])
    assert b.publish()["documents"] == 1
    # A genuine change at the same original URL remains a historical edition.
    b = Builder(tmp_path, None, tmp_path / "third", b.cache, companies=COMPANIES)
    rec = b.base("revised", "Company source", "vault:letters", text=text + " A material new risk emerged.", explicit=["CME"], locations=location)
    rec["format"] = "txt"
    b.add(rec, [])
    assert b.publish()["documents"] == 2


def test_receipt_conflicts_keep_independent_additions_and_newer_upstream():
    base = {"assets": {"core": {"sha": "old"}, "unchanged": "same"}}
    upstream = {"assets": {"core": {"sha": "newer"}, "unchanged": "same", "new": "remote"}}
    incoming = {"assets": {"core": {"sha": "older-producer"}, "unchanged": "same", "recovery": "local"}}
    assert reconcile(base, upstream, incoming) == {"assets": {
        "core": {"sha": "newer"}, "unchanged": "same", "new": "remote", "recovery": "local"}}
    assert reconcile({}, {"assets": {"one": 1}}, {"assets": {"two": 2}}) == {"assets": {"one": 1, "two": 2}}
    assert reconcile(
        {"private_sha256": "old", "public_sha256": "old-public"},
        {"private_sha256": "new", "public_sha256": "old-public"},
        {"private_sha256": "different", "public_sha256": "different-public"},
    ) == {"private_sha256": "new", "public_sha256": "old-public"}


def test_journal_conflicts_keep_both_appends_in_upstream_order():
    upstream = '{"path":"a"}\n{"path":"b"}\n'
    incoming = '{"path":"b"}\n{"path":"c"}\n'
    assert merge_journal(upstream, incoming) == '{"path":"a"}\n{"path":"b"}\n{"path":"c"}\n'
    assert merge_journal("", "") == ""


def test_receipt_resolver_accepts_the_journal_beside_the_manifest(tmp_path, monkeypatch):
    calls = []

    def fake_git(argv, **kwargs):
        calls.append(argv)
        if argv[3:5] == ["diff", "--name-only"]:
            return b"dashboard-private/manifest.json\ndashboard-private/migration-journal.jsonl\n"
        if argv[3] == "show" and argv[4].endswith("manifest.json"):
            stage = {"1": {"assets": {}}, "2": {"assets": {"a": 1}}, "3": {"assets": {"b": 2}}}
            return json.dumps(stage[argv[4][1]]).encode()
        if argv[3] == "show" and "migration-journal" in argv[4]:
            return b'{"path":"up"}\n' if argv[4].startswith(":2:") else b'{"path":"in"}\n'
        return b""

    monkeypatch.setattr(subprocess, "check_output", fake_git)
    resolve(tmp_path)
    assert (tmp_path / "dashboard-private/migration-journal.jsonl").read_text(encoding="utf-8") == '{"path":"up"}\n{"path":"in"}\n'
    assert any(call[3:5] == ["add", "--sparse"] for call in calls)


def test_receipt_resolver_refuses_source_content_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: b"dashboard-private/original.txt\n")
    with pytest.raises(RuntimeError, match="refusing automatic resolution"):
        resolve(tmp_path)


def test_archive_parts_are_pushed_in_batches_before_manifest(tmp_path):
    remote, vault = tmp_path / "remote.git", tmp_path / "vault"
    def git(root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT).decode().strip()
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(vault)], check=True, capture_output=True)
    git(vault, "checkout", "-b", "main")
    git(vault, "config", "user.name", "Fixture")
    git(vault, "config", "user.email", "fixture@example.invalid")
    folder = vault / "dashboard-private/company-source-backfill-v2"
    folder.mkdir(parents=True)
    manifest = folder / "manifest.json"
    manifest.write_text('{"parts":[]}')
    (vault / "unrelated.txt").write_text("Preserve other vault collections")
    git(vault, "add", ".")
    git(vault, "commit", "-m", "initial")
    git(vault, "push", "origin", "HEAD:main")
    parts = []
    for raw in (b"first immutable part", b"second immutable part"):
        sha = hashlib.sha256(raw).hexdigest()
        (folder / (sha + ".zip")).write_bytes(raw)
        parts.append({"file": sha + ".zip", "sha256": sha})
    pending = json.dumps({"parts": parts})
    manifest.write_text(pending)
    result = publish(vault, limit=25)
    assert result == {"parts_uploaded": 2, "batches": 2}
    assert manifest.read_text() == pending
    assert json.loads(git(remote, "show", "main:dashboard-private/company-source-backfill-v2/manifest.json"))["parts"] == []
    assert git(remote, "show", "main:unrelated.txt") == "Preserve other vault collections"
    assert publish(vault, limit=25)["parts_uploaded"] == 0
    # Final publication only advances the manifest after all immutable parts exist.
    git(vault, "add", ".")
    git(vault, "commit", "-m", "publish manifest")
    git(vault, "fetch", "origin", "main")
    git(vault, "rebase", "origin/main")
    git(vault, "push", "origin", "HEAD:main")
    assert len(json.loads(git(remote, "show", "main:dashboard-private/company-source-backfill-v2/manifest.json"))["parts"]) == 2


@pytest.mark.parametrize('disk_available', [True, False])
def test_archive_staging_failure_reports_captured_git_diagnostic(tmp_path, monkeypatch, capsys, disk_available):
    folder = tmp_path / 'dashboard-private/company-source-backfill-v2'
    folder.mkdir(parents=True)
    raw = b'immutable source'
    sha = hashlib.sha256(raw).hexdigest()
    (folder / (sha+'.zip')).write_bytes(raw)
    (folder / 'manifest.json').write_text(json.dumps({'parts': [{'file': sha+'.zip', 'sha256': sha}]}))

    def fake_git(argv, **kwargs):
        if 'add' in argv and '--sparse' in argv:
            raise subprocess.CalledProcessError(128, argv, output=b'fatal: fixture object write failed\n')
        return b''

    monkeypatch.setattr(subprocess, 'check_output', fake_git)
    if not disk_available:
        def unavailable(*args):
            raise OSError('storage information unavailable')
        monkeypatch.setattr('push_company_source_parts.shutil.disk_usage', unavailable)
    with pytest.raises(subprocess.CalledProcessError):
        publish(tmp_path)
    assert 'fatal: fixture object write failed' in capsys.readouterr().err


def test_worker_pack_leaves_room_for_archive_git_objects(tmp_path, monkeypatch):
    """Replay the worker's pack -> upload boundary with a bounded disk budget."""
    worker = tmp_path / 'worker'
    cache = worker / '_private/company-research/cache'
    (cache / 'git').mkdir(parents=True)
    original = b'Complete primary research evidence.\n' * 5000
    (cache / 'git/aa.json').write_bytes(original)
    (cache / 'matches.json').write_text('{"version":"verified-current-identities"}')
    (cache / 'work.sqlite').write_bytes(b'Keep unpacked worker bookkeeping')
    vault = worker / '_external/research-vault'
    archive = vault / 'dashboard-private/company-source-backfill-v2'
    sentinel = worker / 'outside-cache.txt'
    sentinel.write_text('Never delete unrelated worker or vault files')
    workflow = yaml.safe_load((ROOT / '.github/workflows/company-source-backfill.yml').read_text())
    command = shlex.split(next(s['run'] for s in workflow['jobs']['backfill']['steps'] if s.get('id') == 'archive'))
    args = [sys.executable, str(ROOT / command[1]),
            *(arg.replace('$RESEARCH_VAULT_ROOT', str(vault)) for arg in command[2:])]
    subprocess.run(args, cwd=worker, check=True, capture_output=True)
    capacity = len(original) // 2
    staged = []

    def bounded_git(argv, **kwargs):
        if 'add' in argv and '--sparse' in argv:
            extracted = sum(p.stat().st_size for p in cache.rglob('*') if p.is_file())
            compressed = sum(p.stat().st_size for p in archive.glob('*.zip'))
            if extracted + 2 * compressed > capacity:
                raise subprocess.CalledProcessError(128, argv,
                    output=b'fatal: unable to write loose object file: No space left on device\n')
            staged[:] = argv[argv.index('--') + 1:]
        if 'diff' in argv and '--cached' in argv:
            return '\n'.join(staged).encode()
        return b''

    monkeypatch.setattr(subprocess, 'check_output', bounded_git)
    assert publish(vault)['parts_uploaded'] > 0
    restored = tmp_path / 'restored'
    restore(archive, restored)
    assert (restored / 'git/aa.json').read_bytes() == original
    assert json.loads((restored / 'matches.json').read_text())['version'] == 'verified-current-identities'
    assert (cache / 'work.sqlite').read_bytes() == b'Keep unpacked worker bookkeeping'
    assert sentinel.read_text() == 'Never delete unrelated worker or vault files'


def test_deployment_uses_snapshot_and_backfill_refreshes_before_batched_publication():
    action = yaml.safe_load((ROOT / ".github/actions/deploy-cloudflare-dashboard/action.yml").read_text())
    steps = action["runs"]["steps"]
    build = next(s["run"] for s in steps if s.get("name") == "Publish verified private company research snapshot")
    assert "--publication-only" in build and "--publish-cached" in build
    assert "--drive" not in build
    preserve = next(s for s in steps if s.get("uses") == "./.github/actions/preserve-private-dashboard")
    assert preserve["with"]["preserve-company-cache"] == "false"
    workflow = yaml.safe_load((ROOT / ".github/workflows/company-source-backfill.yml").read_text())
    steps = workflow["jobs"]["backfill"]["steps"]
    refresh = next(i for i, s in enumerate(steps) if s.get("name") == "Refresh the complete publication snapshot")
    parts = next(i for i, s in enumerate(steps) if s.get("id") == "parts")
    commit = next(i for i, s in enumerate(steps) if s.get("uses") == "./.github/actions/commit-vault")
    assert refresh < parts < commit
    assert "steps.parts.outcome == 'success'" in steps[commit]["if"]
