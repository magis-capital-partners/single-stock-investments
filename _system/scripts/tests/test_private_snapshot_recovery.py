"""Pinned recovery of private snapshot objects, and the media-lane staged refusal."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_snapshot_recovery as recovery
import youtube_lane as lane
from migrate_dashboard_sources import public_snapshot

ROOT = Path(__file__).resolve().parents[3]
EPISODE = "data/insights/podcast_episodes/episode.json"


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false"),
                       ("core.autocrlf", "false")):
        _git(path, "config", key, value)
    return path


def _canonical(document):
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _config(path, *, commit, digest, relative=EPISODE):
    path.write_text(json.dumps({
        "schema_version": recovery.SCHEMA,
        "repository": "magis-capital-partners/single-stock-investments",
        "objects": [{"path": relative, "private_sha256": digest, "source_commit": commit}],
    }), encoding="utf-8")
    return path


@pytest.fixture
def published(tmp_path):
    repo = _repo(tmp_path / "public")
    full = _canonical({"episode_id": "e", "source_file": "restricted", "tickers": ["A"]})
    target = repo / "dashboard" / EPISODE
    target.parent.mkdir(parents=True)
    target.write_bytes(full)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "full document published")
    return repo, _git(repo, "rev-parse", "HEAD"), full


def test_pinned_object_is_recovered_from_public_history_with_its_exact_bytes(tmp_path, published):
    repo, commit, full = published
    digest = hashlib.sha256(full).hexdigest()
    config = _config(tmp_path / "recovery.json", commit=commit, digest=digest)
    vault = tmp_path / "vault"
    fetch = mock.Mock(return_value=None)
    assert recovery.recover(vault, digest, root=repo, config=config, fetch_raw=fetch) is True
    assert (vault / "dashboard-private" / "objects" / digest).read_bytes() == full
    fetch.assert_not_called()
    assert not list((vault / "dashboard-private" / "objects").glob("*.tmp"))


def test_unpinned_or_mismatched_objects_are_never_written(tmp_path, published):
    repo, commit, full = published
    vault = tmp_path / "vault"
    wrong = hashlib.sha256(full + b"x").hexdigest()
    config = _config(tmp_path / "recovery.json", commit=commit, digest=wrong)
    assert recovery.recover(vault, wrong, root=repo, config=config, fetch_raw=lambda *a: full) is False
    assert recovery.recover(vault, hashlib.sha256(full).hexdigest(), root=repo, config=config) is False
    assert not (vault / "dashboard-private").exists()


def test_missing_commit_falls_back_to_the_public_blob_and_still_verifies(tmp_path, published):
    _repo_unused, commit, full = published
    empty = _repo(tmp_path / "shallow")
    digest = hashlib.sha256(full).hexdigest()
    config = _config(tmp_path / "recovery.json", commit=commit, digest=digest)
    calls = []

    def fetch(repository, sha, path):
        calls.append((repository, sha, path))
        return full

    vault = tmp_path / "vault"
    assert recovery.recover(vault, digest, root=empty, config=config, fetch_raw=fetch) is True
    assert calls == [("magis-capital-partners/single-stock-investments", commit, "dashboard/" + EPISODE)]
    assert (vault / "dashboard-private" / "objects" / digest).read_bytes() == full
    tampered = tmp_path / "vault2"
    assert recovery.recover(tampered, digest, root=empty, config=config, fetch_raw=lambda *a: full + b" ") is False
    assert not (tampered / "dashboard-private").exists()


def test_unsafe_recovery_paths_are_rejected(tmp_path):
    config = _config(tmp_path / "recovery.json", commit="0" * 40, digest="0" * 64, relative="../secret.json")
    with pytest.raises(ValueError):
        recovery.load_items(config)


def test_committed_recovery_entries_name_the_current_receipt():
    items = recovery.load_items()
    receipt = json.loads((ROOT / "dashboard" / "private-assets.json").read_text(encoding="utf-8"))["assets"]
    assert items
    for digest, item in items.items():
        assert receipt[item["path"]]["private_sha256"] == digest


def _managed_repo(tmp_path):
    repo = _repo(tmp_path / "ops")
    document = {"episode_id": "e", "source_file": "restricted", "tickers": ["A"]}
    full = _canonical(document)
    placeholder = _canonical(public_snapshot(document))
    (repo / "dashboard" / "data" / "insights" / "podcast_episodes").mkdir(parents=True)
    (repo / "dashboard" / EPISODE).write_bytes(placeholder)
    receipt = {"assets": {EPISODE: {"private_sha256": hashlib.sha256(full).hexdigest(),
                                    "public_sha256": hashlib.sha256(placeholder).hexdigest()}}}
    (repo / "dashboard" / "private-assets.json").write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo, full, placeholder


def test_media_lane_refuses_and_unstages_a_full_managed_snapshot(tmp_path):
    repo, full, _placeholder = _managed_repo(tmp_path)
    (repo / "dashboard" / EPISODE).write_bytes(full)
    _git(repo, "add", "-A", "dashboard/data/insights/podcast_episodes")
    lines = []
    with mock.patch.object(lane, "log", side_effect=lines.append):
        assert lane._refuse_restricted_stage(repo, ["dashboard/data/insights/podcast_episodes"]) is True
    assert _git(repo, "diff", "--cached", "--name-only") == ""
    assert any(EPISODE in line for line in lines)
    assert not any("restricted\"" in line or "source_file\":" in line for line in lines)


def test_media_lane_allows_a_sealed_placeholder_and_ordinary_files(tmp_path):
    repo, _full, placeholder = _managed_repo(tmp_path)
    (repo / "dashboard" / "data" / "insights" / "podcasts.json").write_text('{"podcast_index":[]}\n', encoding="utf-8")
    (repo / "dashboard" / EPISODE).write_bytes(placeholder)
    _git(repo, "add", "-A", "dashboard/data/insights")
    with mock.patch.object(lane, "log"):
        assert lane._refuse_restricted_stage(repo, ["dashboard/data/insights"]) is False
    assert _git(repo, "diff", "--cached", "--name-only") == "dashboard/data/insights/podcasts.json"


def test_push_main_does_not_publish_when_sealing_is_skipped(tmp_path):
    repo, full, placeholder = _managed_repo(tmp_path)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "fetch", "-q", "origin")
    before = _git(origin, "rev-parse", "main")
    (repo / "dashboard" / EPISODE).write_bytes(full)
    lines = []
    with mock.patch.object(lane, "ROOT", repo), mock.patch.object(lane, "log", side_effect=lines.append), \
            mock.patch.object(lane, "_seal_in_place_publish"):
        pushed = lane.push_main("chore(podcasts): publish analysed episodes test",
                                paths=lane.PODCAST_PATHS, dirs=lane.PODCAST_DIRS)
    assert pushed is False, lines
    assert _git(origin, "rev-parse", "main") == before
    assert _git(origin, "show", f"main:dashboard/{EPISODE}") + "\n" == placeholder.decode()
