"""Opt-in narrowing of the vault checkout: workspace-scoped objects and a prefix-scoped catalog view."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ACTION = ROOT / ".github" / "actions" / "checkout-vault" / "action.yml"
WORKFLOWS = ROOT / ".github" / "workflows"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _step(name: str) -> dict:
    return next(s for s in _action()["runs"]["steps"] if s.get("name") == name)


def _run_step(step: dict, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    script = step["run"].replace("${{ inputs.publication-only }}", "false")
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **env})


def _scope_workspace(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "work"
    (work / "_system").mkdir(parents=True)
    (work / "_system/scripts").symlink_to(ROOT / "_system/scripts")
    (work / "_system/config").symlink_to(ROOT / "_system/config")
    selected = work / "dashboard/data/core.json"
    selected.parent.mkdir(parents=True)
    selected.write_text("{}")
    manifest = {"assets": {"data/core.json": {"private_sha256": "a" * 64},
                           "data/unselected.json": {"private_sha256": "b" * 64}}}
    (work / "dashboard/private-assets.json").write_text(json.dumps(manifest))
    vault = work / "_external/research-vault"
    vault.mkdir(parents=True)
    _git(vault, "init", "-q")
    _git(vault, "sparse-checkout", "init", "--no-cone")
    (vault / "dashboard-private/objects").mkdir(parents=True)
    (vault / "dashboard-private/objects" / ("a" * 64)).write_text("{}")
    return work, vault


def test_workspace_publication_scope_is_opt_in_and_restores_only_selected_objects(tmp_path):
    action = _action()
    assert action["inputs"]["publication-scope"]["default"] == "all"
    step = _step("Materialize publication objects")
    assert step["env"]["PUBLICATION_SCOPE"] == "${{ inputs.publication-scope }}"
    work, _ = _scope_workspace(tmp_path)
    env = {"GITHUB_WORKSPACE": str(work), "RUNNER_TEMP": str(tmp_path), "SNAPSHOT_VALIDATION_ONLY": "false",
           "GITHUB_ACTIONS": "", "CLOUDFLARE_API_TOKEN": ""}
    scoped = _run_step(step, work, {**env, "PUBLICATION_SCOPE": "workspace"})
    assert scoped.returncode == 0, scoped.stdout + scoped.stderr
    assert "publication objects present: 1 of 1" in scoped.stdout
    assert (tmp_path / "vault-object-patterns.txt").read_text().split() == ["/dashboard-private/objects/" + "a" * 64]
    # The default still requires every object the manifest names.
    full = _run_step(step, work, {**env, "PUBLICATION_SCOPE": "all"})
    assert full.returncode != 0
    assert "missing private object for data/unselected.json" in full.stdout
    assert "publication objects present: 1 of 2" in full.stdout
    bad = _run_step(step, work, {**env, "PUBLICATION_SCOPE": "some"})
    assert bad.returncode != 0 and "publication-scope must be all or workspace" in bad.stdout


def test_catalog_prefixes_become_read_only_prefix_arguments(tmp_path):
    action = _action()
    assert action["inputs"]["catalog-prefixes"]["default"] == ""
    step = _step("Materialize the verified private catalog view")
    assert step["env"]["CATALOG_PREFIXES"] == "${{ inputs.catalog-prefixes }}"
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "sparse-checkout", "init", "--no-cone")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "python").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$STUB_OUT/$2.txt"\n')
    (stub / "python").chmod(0o755)
    env = {"PATH": f"{stub}:{os.environ['PATH']}", "STUB_OUT": str(tmp_path), "SNAPSHOT_VALIDATION_ONLY": "false",
           "PUBLICATION_ONLY": "false"}
    for prefixes, expected in [("", []), ("videos/\n  \n  valuation-underwriting/packets/  \n",
                                          ["--prefix", "videos/", "--prefix", "valuation-underwriting/packets/"])]:
        result = _run_step(step, work, {**env, "CATALOG_PREFIXES": prefixes})
        assert result.returncode == 0, result.stdout + result.stderr
        args = (tmp_path / "initialize.txt").read_text().splitlines()
        assert args == ["_system/scripts/private_storage_io.py", "initialize", "--vault", "_external/research-vault",
                        "--sparse-scope", *expected]


def test_only_unit_tests_narrow_their_restore():
    """Builders and publishers keep the full object set and a writable catalog view."""
    callers = set()
    for path in sorted(list(WORKFLOWS.glob("*.yml")) + list((ROOT / ".github/actions").glob("*/action.yml"))):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs = (document.get("jobs") or {}).items() if "jobs" in document else [("", document.get("runs") or {})]
        for name, job in jobs:
            for step in job.get("steps") or []:
                options = step.get("with") or {}
                if step.get("uses") == "./.github/actions/checkout-vault" and (
                        options.get("publication-scope", "all") != "all" or options.get("catalog-prefixes")):
                    callers.add((path.name, name))
    assert callers == {("python-tests.yml", "unit-tests")}
