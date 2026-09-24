"""lint_pr_research.py lints what a PR changed, and labels what it inherited.

PR #1019 (AMZN, 2026-09-24) touched a falsifier draft, a review receipt and
the agent manifest. It was blocked by the deep dive's return statement, which
it never opened: "Returns statement (synthesis) 3.11% vs valuation.json base
2.64%". The daily download sync had rewritten valuation.json on main.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "lint_pr_research.py"
DRIFT = (
    "LINT: AMZN/research/deep_dive_2026-07-25.md: Returns statement (synthesis) 3.11% "
    "vs valuation.json base 2.64% (tol 0.25pp)"
)
PR_1019_FILES = [
    "AMZN/research/agent_run_state.json",
    "AMZN/research/epistemic_review_receipt_2026-09-24.md",
    "AMZN/research/falsifier_drafts/bfb8c41c4edab4687e691df6.json",
    "AMZN/research/research_agent_manifest.json",
    "_system/memory/daily/2026-09-24.md",
]


@pytest.fixture
def lint(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("lint_pr_research_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    head = tmp_path / "head"
    research = head / "AMZN" / "research"
    research.mkdir(parents=True)
    (research / "deep_dive_2026-07-25.md").write_text("# AMZN\n", encoding="utf-8")
    (research / "valuation.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", head)
    yield module
    sys.modules.pop(spec.name, None)


class FakeProcesses:
    """Stands in for subprocess.run: lint scripts answer from a table keyed by
    (which tree, script name); git calls report "not found"."""

    def __init__(self, head: Path, answers: dict[tuple[str, str], tuple[int, str]]):
        self.head = head
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def __call__(self, cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not found")
        script = Path(cmd[1]).name
        tree = "head" if Path(kwargs.get("cwd", "")) == self.head else "base"
        self.calls.append((tree, script))
        code, out = self.answers.get((tree, script), (0, "OK: 1 deep dive(s)\n"))
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")


class FakeBaseTrees:
    tree_path: Path | None = None

    def __init__(self, base):
        self.base = base

    def tree(self, ticker):
        return self.tree_path

    def cleanup(self):
        pass


def run_main(module, monkeypatch, tmp_path, files, answers, base_tree="present"):
    names = tmp_path / "pr-files.txt"
    names.write_text("\n".join(files) + "\n", encoding="utf-8")
    fake = FakeProcesses(module.ROOT, answers)
    monkeypatch.setattr(module.subprocess, "run", fake)
    if base_tree == "present":
        (tmp_path / "base").mkdir(exist_ok=True)
        FakeBaseTrees.tree_path = tmp_path / "base"
    else:
        FakeBaseTrees.tree_path = None
    # raising=False: the pre-fix module has no BaseTrees, and must still run.
    monkeypatch.setattr(module, "BaseTrees", FakeBaseTrees, raising=False)
    monkeypatch.setattr(sys, "argv", ["lint_pr_research.py", "--base", "origin/main", "--name-only-file", str(names)])
    return module.main(), fake.calls


def test_pr_1019_is_not_linted_on_a_deep_dive_it_never_touched(lint, monkeypatch, tmp_path, capsys):
    code, calls = run_main(lint, monkeypatch, tmp_path, PR_1019_FILES, {("head", "lint_deep_dive.py"): (1, DRIFT)})
    assert code == 0
    assert ("head", "lint_deep_dive.py") not in calls
    assert "SKIP AMZN: deep-dive consistency lint" in capsys.readouterr().out


def test_a_failure_already_on_main_is_labelled_inherited_and_does_not_block(lint, monkeypatch, tmp_path, capsys):
    files = PR_1019_FILES + ["AMZN/research/valuation.json"]
    answers = {
        ("head", "lint_deep_dive.py"): (1, f"WARN: something else\n{DRIFT}\n"),
        ("base", "lint_deep_dive.py"): (1, f"{DRIFT}\n"),
    }
    code, calls = run_main(lint, monkeypatch, tmp_path, files, answers)
    out = capsys.readouterr().out
    assert code == 0, out
    assert ("head", "lint_deep_dive.py") in calls and ("base", "lint_deep_dive.py") in calls
    assert "INHERITED AMZN lint_deep_dive.py" in out
    assert "::warning title=Inherited research lint (AMZN)::" in out


def test_a_new_failure_blocks_even_when_main_also_fails(lint, monkeypatch, tmp_path, capsys):
    files = ["AMZN/research/deep_dive_2026-07-25.md"]
    introduced = "LINT: AMZN/research/deep_dive_2026-07-25.md: missing Why the market might be wrong"
    answers = {
        ("head", "lint_deep_dive.py"): (1, f"{DRIFT}\n{introduced}\n"),
        ("base", "lint_deep_dive.py"): (1, f"{DRIFT}\n"),
    }
    code, _ = run_main(lint, monkeypatch, tmp_path, files, answers)
    out = capsys.readouterr().out
    assert code == 1
    assert f"NEW AMZN lint_deep_dive.py: {introduced}" in out


def test_a_failure_without_a_base_copy_blocks(lint, monkeypatch, tmp_path):
    files = ["AMZN/research/deep_dive_2026-07-25.md"]
    code, _ = run_main(lint, monkeypatch, tmp_path, files, {("head", "lint_deep_dive.py"): (1, DRIFT)}, base_tree=None)
    assert code == 1


def test_touching_the_deep_dive_still_lints_it(lint, monkeypatch, tmp_path):
    files = ["AMZN/research/deep_dive_2026-07-25.md"]
    code, calls = run_main(lint, monkeypatch, tmp_path, files, {})
    assert code == 0
    assert ("head", "lint_deep_dive.py") in calls
    assert ("head", "lint_adversarial.py") in calls


def test_base_trees_materialise_the_base_copy_with_git_archive(lint, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / "_system" / "scripts").mkdir(parents=True)
    (repo / "_system" / "scripts" / "lint_deep_dive.py").write_text("print('base')\n", encoding="utf-8")
    (repo / "AMZN" / "research").mkdir(parents=True)
    (repo / "AMZN" / "research" / "deep_dive_2026-07-25.md").write_text("base dive\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x"}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)
    monkeypatch.setattr(lint, "ROOT", repo)
    trees = lint.BaseTrees("main")
    try:
        tree = trees.tree("AMZN")
        assert tree is not None
        assert (tree / "AMZN" / "research" / "deep_dive_2026-07-25.md").read_text(encoding="utf-8") == "base dive\n"
        assert (tree / "_system" / "scripts" / "lint_deep_dive.py").exists()
        assert trees.tree("NEWCO") is None  # a ticker new in this PR has no base copy
    finally:
        trees.cleanup()
    assert not tree.exists()
