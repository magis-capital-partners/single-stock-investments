"""Structure of the dashboard deploy workflow and its Cloudflare action.

Text checks live in _system/scripts/test_workflow_run_deploy_gate.py (they run
in a PyYAML-free CI job); these parse the YAML so a malformed file or a
mis-wired output cannot pass on a lucky substring.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "dashboard-pages.yml"
ACTION = ROOT / ".github" / "actions" / "deploy-cloudflare-dashboard" / "action.yml"

# A repo path as a shell word: not the tail of another path ("../dashboard",
# "$RUNNER_TEMP/..."), and not something the job itself creates at runtime.
REPO_PATH = re.compile(r"(?<![\w$./-])((?:_system|\.github|dashboard)/[A-Za-z0-9_.\-/\[\]]+)")
CREATED_AT_RUNTIME = ("node_modules", "/generated", "_cf_project")


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def shape(key: str) -> str:
    return re.sub(r"\$\{\{.*?\}\}", "*", key)


def steps_of(path: Path) -> list[tuple[str, dict]]:
    data = load(path)
    if path == ACTION:
        return [("action", step) for step in data["runs"]["steps"]]
    return [(name, step) for name, job in data["jobs"].items() for step in job.get("steps") or []]


def run_blocks() -> list[tuple[str, str]]:
    blocks = []
    for path in (ACTION, WORKFLOW):
        for where, step in steps_of(path):
            if "run" in step:
                blocks.append((f"{path.name} {where}: {step.get('name') or step.get('id') or '?'}", step["run"]))
    assert len(blocks) > 10
    return blocks


def test_no_run_block_contains_a_literal_backslash_n():
    # 2026-09-25: "tests \n          _system/..." reached action.yml where a
    # line continuation was meant; bash passed "n" to pytest and every deploy
    # died at the Verify step, before D1 and Pages.
    for where, script in run_blocks():
        assert "\\n" not in script, f"{where}: literal backslash-n in a run block"


def test_every_repo_path_a_run_block_names_exists():
    checked = 0
    for where, script in run_blocks():
        for token in REPO_PATH.findall(script):
            token = token.rstrip("/.")
            if any(marker in token for marker in CREATED_AT_RUNTIME):
                continue
            assert (ROOT / token).exists(), f"{where}: {token} does not exist"
            checked += 1
    assert checked >= 10


def test_every_local_action_exists():
    for path in (ACTION, WORKFLOW):
        for where, step in steps_of(path):
            uses = str(step.get("uses", ""))
            if uses.startswith("./"):
                assert (ROOT / uses[2:] / "action.yml").is_file(), f"{path.name} {where}: {uses}"


def test_verify_step_runs_pytest_on_real_targets():
    verify = next(
        step for _where, step in steps_of(ACTION)
        if str(step.get("name", "")).startswith("Verify Cloudflare boundary")
    )
    # Word-split the way bash will: continuations join, quotes and escapes
    # resolve. A stray "\n" becomes the target "n" here, as it did in CI.
    script = verify["run"].replace("\\\n", " ")
    commands = [shlex.split(line, comments=True) for line in script.splitlines()]
    pytest_words = next(words for words in commands if words[:3] == ["python", "-m", "pytest"])
    targets = [word for word in pytest_words[3:] if not word.startswith("-")]
    assert "_system/scripts/tests/test_dashboard_deploy_workflow.py" in targets
    for target in targets:
        assert (ROOT / target).exists(), f"pytest target {target!r} does not exist"
    pip_words = next(words for words in commands if words[:4] == ["python", "-m", "pip", "install"])
    assert "pyyaml" in pip_words, "without PyYAML this file's checks would skip in CI"


def test_no_job_uses_always():
    for name, job in load(WORKFLOW)["jobs"].items():
        assert "always()" not in str(job.get("if", "")), name
        for step in job.get("steps") or []:
            assert "always()" not in str(step.get("if", "")), f"{name}: {step.get('name')}"


def test_every_gate_lookup_has_a_matching_save():
    jobs = load(WORKFLOW)["jobs"]
    restores, saves = set(), set()
    for job in jobs.values():
        for step in job.get("steps") or []:
            uses = str(step.get("uses", ""))
            if uses.startswith("actions/cache/restore"):
                assert step["with"]["lookup-only"] is True
                restores.add((step["with"]["path"], shape(step["with"]["key"])))
            elif uses.startswith("actions/cache/save"):
                saves.add((step["with"]["path"], shape(step["with"]["key"])))
    # Same path string on both sides: it is part of the cache version.
    assert restores == saves
    assert {path for path, _ in restores} == {".deploy-gate-marker"}


def test_build_steps_after_the_recheck_are_gated():
    steps = load(WORKFLOW)["jobs"]["build"]["steps"]
    ids = [step.get("id") for step in steps]
    proceed = ids.index("proceed")
    for step in steps[proceed + 1:]:
        assert "steps.proceed.outputs.should_deploy == 'true'" in str(step.get("if", "")), step.get("name")


def test_action_outputs_come_from_the_d1_step():
    action = load(ACTION)
    ids = {step.get("id") for step in action["runs"]["steps"]}
    assert "d1" in ids
    for name in ("d1_deferred", "d1_deferred_stages", "d1_deferred_reason",
                 "d1_utc_date", "d1_pruned_today", "d1_rows_read", "d1_rows_written"):
        assert action["outputs"][name]["value"] == f"${{{{ steps.d1.outputs.{name} }}}}"
    workflow_uses = load(WORKFLOW)["jobs"]["build"]["steps"]
    deploy = next(step for step in workflow_uses if step.get("id") == "cloudflare")
    assert set(deploy["with"]) <= set(action["inputs"])


def test_d1_stage_runs_before_the_pages_deploy():
    names = [step["name"] for step in load(ACTION)["runs"]["steps"]]
    assert names.index("Apply D1 schema and synchronize current dashboard state") < names.index(
        "Deploy Cloudflare Pages"
    )
