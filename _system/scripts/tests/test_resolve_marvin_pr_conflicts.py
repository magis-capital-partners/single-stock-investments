"""The automerge conflict resolver against real git repositories.

Each test builds a throwaway origin (a bare repo) and a clone of it, points the
resolver's ROOT at the clone, and stubs only the GitHub CLI. Nothing here talks
to GitHub.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "resolve_marvin_pr_conflicts.py"
BRANCH = "cursor/abc-falsifier-1234"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def git(cwd: Path, *args: str) -> str:
    import os

    env = {**os.environ, **GIT_ENV}
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=cwd, capture_output=True, text=True, env=env, check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr or proc.stdout}")
    return proc.stdout.strip()


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def resolver(monkeypatch):
    spec = importlib.util.spec_from_file_location("resolve_marvin_pr_conflicts_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def build_origin(tmp_path: Path, *, main_deletes_note: bool = False) -> dict[str, str]:
    """origin/main: A-B-C-D; the PR branch forks at B and adds F."""
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    write(seed, "_system/memory/daily/2026-09-01.md", "# Daily log 2026-09-01\n")
    write(seed, "_system/portfolio/research_events.jsonl", '{"ticker": "ZZZ"}\n')
    write(seed, "_system/research/milly_log.md", "| ZZZ | ok |\n")
    write(seed, "ABC/research/note.md", "base note\n")
    a = commit_all(seed, "A")
    write(seed, "ABC/research/other.md", "b\n")
    b = commit_all(seed, "B")

    git(seed, "checkout", "-q", "-b", BRANCH, b)
    write(seed, "ABC/research/note.md", "branch rewrites the note\n")
    f = commit_all(seed, "F: branch work")

    git(seed, "checkout", "-q", "main")
    write(seed, "XYZ/research/unrelated.md", "c\n")
    c = commit_all(seed, "C")
    if main_deletes_note:
        (seed / "ABC/research/note.md").unlink()
    else:
        write(seed, "ABC/research/note.md", "main rewrites the note\n")
    d = commit_all(seed, "D")

    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(seed, "push", "-q", str(origin), "main", BRANCH)
    # A plain path, cloned with --no-local: the real transport runs (so --depth
    # makes a genuinely shallow clone) without file:// URL parsing, which
    # differs across Git for Windows environments.
    return {"A": a, "B": b, "C": c, "D": d, "F": f, "origin": str(origin)}


def point_resolver_at(module, monkeypatch, clone: Path, mergeable: str = "CONFLICTING") -> None:
    monkeypatch.setattr(module, "ROOT", clone)
    if hasattr(module, "DAILY"):  # older versions froze the daily dir at import
        monkeypatch.setattr(module, "DAILY", clone / "_system" / "memory" / "daily")
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda args: {"headRefName": BRANCH, "mergeable": mergeable, "title": "ABC: falsifier"},
    )


def test_a_shallow_checkout_behind_the_fork_point_still_merges(tmp_path, resolver, monkeypatch):
    # AM3 (automerge run 35944388953): the merge job checked out main at
    # fetch-depth 1, so origin/main stopped at the checkout tip, the PR forked
    # further back, and git refused to merge "unrelated histories".
    refs = build_origin(tmp_path)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", "--depth", "1", "--branch", "main", refs["origin"], str(clone))
    assert git(clone, "rev-parse", "--is-shallow-repository") == "true"
    point_resolver_at(resolver, monkeypatch, clone)

    pushed = resolver.resolve("1014", "ABC")

    assert pushed
    origin_tip = git(tmp_path, "--git-dir", str(tmp_path / "origin.git"), "rev-parse", BRANCH)
    assert origin_tip == pushed
    parents = git(clone, "rev-list", "--parents", "-n", "1", pushed).split()[1:]
    assert refs["D"] in parents and refs["F"] in parents
    # -X theirs: main's side of the conflicting note wins.
    assert git(clone, "show", f"{pushed}:ABC/research/note.md") == "main rewrites the note"


def test_a_conflict_theirs_cannot_settle_is_never_committed(tmp_path, resolver, monkeypatch):
    # main deleted the note, the branch modified it: a modify/delete conflict
    # that -X theirs leaves unmerged. `git add -A` used to commit the branch
    # copy, silently resurrecting a file main had removed.
    refs = build_origin(tmp_path, main_deletes_note=True)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", refs["origin"], str(clone))
    point_resolver_at(resolver, monkeypatch, clone)

    with pytest.raises(SystemExit) as excinfo:
        resolver.resolve("1014", "ABC")

    assert "ABC/research/note.md" in str(excinfo.value)
    origin_tip = git(tmp_path, "--git-dir", str(tmp_path / "origin.git"), "rev-parse", BRANCH)
    assert origin_tip == refs["F"], "nothing may be pushed when conflicts remain"


def test_a_mergeable_pr_is_left_alone(tmp_path, resolver, monkeypatch):
    refs = build_origin(tmp_path)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", refs["origin"], str(clone))
    point_resolver_at(resolver, monkeypatch, clone, mergeable="MERGEABLE")

    assert resolver.resolve("1014", "ABC") is None
    origin_tip = git(tmp_path, "--git-dir", str(tmp_path / "origin.git"), "rev-parse", BRANCH)
    assert origin_tip == refs["F"]


def test_the_workflow_learns_what_was_pushed(tmp_path, resolver, monkeypatch):
    # The merge job must stop after a resolver push and let fresh checks gate
    # the new head, so it needs to know a push happened and at which SHA.
    refs = build_origin(tmp_path)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", refs["origin"], str(clone))
    point_resolver_at(resolver, monkeypatch, clone)
    output = tmp_path / "github_output"
    monkeypatch.setattr(sys, "argv", ["resolve", "1014", "--ticker", "ABC", "--github-output", str(output)])

    resolver.main()

    lines = output.read_text(encoding="utf-8").splitlines()
    origin_tip = git(tmp_path, "--git-dir", str(tmp_path / "origin.git"), "rev-parse", BRANCH)
    assert "pushed=true" in lines
    assert f"pushed_sha={origin_tip}" in lines
    assert "head_moved=false" in lines


def origin_tip(tmp_path: Path) -> str:
    return git(tmp_path, "--git-dir", str(tmp_path / "origin.git"), "rev-parse", BRANCH)


def test_an_agent_commit_pushed_during_resolution_is_never_overwritten(tmp_path, resolver, monkeypatch):
    # The old fallback re-fetched the branch and pushed --force-with-lease with
    # no expected value, i.e. "whatever I just fetched": the agent's commit.
    refs = build_origin(tmp_path)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", refs["origin"], str(clone))
    point_resolver_at(resolver, monkeypatch, clone)
    agent = tmp_path / "agent"
    git(tmp_path, "clone", "-q", "--no-local", "--branch", BRANCH, refs["origin"], str(agent))
    real_restore = resolver.restore_ticker_logs

    def agent_pushes_mid_resolution(*args, **kwargs):
        write(agent, "ABC/research/late.md", "agent work\n")
        commit_all(agent, "agent: late commit")
        git(agent, "push", "-q", "origin", BRANCH)
        return real_restore(*args, **kwargs)

    monkeypatch.setattr(resolver, "restore_ticker_logs", agent_pushes_mid_resolution)
    # No expected SHA: the lease defaults to the tip the merge was built on.
    with pytest.raises(Exception, match="moved away"):
        resolver.resolve("1014", "ABC")
    late = git(agent, "rev-parse", "HEAD")
    assert origin_tip(tmp_path) == late, "the agent's commit was overwritten"


def test_a_head_that_moved_since_the_gate_is_not_resolved(tmp_path, resolver, monkeypatch):
    refs = build_origin(tmp_path)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", refs["origin"], str(clone))
    point_resolver_at(resolver, monkeypatch, clone)
    output = tmp_path / "github_output"
    monkeypatch.setattr(sys, "argv", ["resolve", "1014", "--ticker", "ABC",
                                      "--expected-sha", refs["B"], "--github-output", str(output)])

    resolver.main()

    assert origin_tip(tmp_path) == refs["F"]
    lines = output.read_text(encoding="utf-8").splitlines()
    assert "head_moved=true" in lines and "pushed=false" in lines


def test_a_long_lived_shallow_clone_is_never_shortened(tmp_path, resolver, monkeypatch):
    # `git fetch --depth=N` can SHORTEN history. It is only for the merge job's
    # near-empty checkout; a deeper clone (a workstation checkout) gets a plain
    # fetch. Scaled down: history of 3 commits against start_depth=2.
    refs = build_origin(tmp_path)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", "--depth", "3", "--branch", "main", refs["origin"], str(clone))
    assert git(clone, "rev-list", "--count", "HEAD") == "3"
    point_resolver_at(resolver, monkeypatch, clone)
    commands: list[list[str]] = []
    real_run = resolver.run

    def recording_run(cmd, **kwargs):
        commands.append(list(cmd))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(resolver, "run", recording_run)

    base = resolver.fetch_with_merge_base(BRANCH, start_depth=2)

    assert base == refs["B"]
    fetches = [cmd for cmd in commands if cmd[:2] == ["git", "fetch"]]
    assert fetches, commands
    assert not [cmd for cmd in fetches if any(arg.startswith("--depth") for arg in cmd)], fetches
    assert int(git(clone, "rev-list", "--count", "origin/main")) >= 3


def test_the_resolver_works_in_the_merge_jobs_checkout(tmp_path, resolver, monkeypatch):
    # The merge job's checkout: depth 1, blobless (a promisor remote), sparse,
    # with the conflicting file outside the sparse set.
    refs = build_origin(tmp_path)
    git(Path(refs["origin"]), "config", "uploadpack.allowFilter", "true")
    git(Path(refs["origin"]), "config", "uploadpack.allowAnySHA1InWant", "true")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", "--depth", "1", "--filter=blob:none", "--sparse",
        "--branch", "main", refs["origin"], str(clone))
    git(clone, "sparse-checkout", "set", "--no-cone", "/_system/scripts/", "/_system/memory/daily/",
        "/_system/portfolio/research_events.jsonl", "/_system/research/milly_log.md")
    point_resolver_at(resolver, monkeypatch, clone)

    pushed = resolver.resolve("1014", "ABC")

    assert pushed and origin_tip(tmp_path) == pushed
    assert git(clone, "show", f"{pushed}:ABC/research/note.md") == "main rewrites the note"
    assert git(clone, "show", f"{pushed}:ABC/research/other.md") == "b"
