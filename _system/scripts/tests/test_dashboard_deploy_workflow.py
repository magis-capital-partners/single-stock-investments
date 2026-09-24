"""Structure of the dashboard deploy workflow and its Cloudflare action.

Text checks live in _system/scripts/test_workflow_run_deploy_gate.py (they run
in a PyYAML-free CI job); these parse the YAML so a malformed file or a
mis-wired output cannot pass on a lucky substring.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "dashboard-pages.yml"
ACTION = ROOT / ".github" / "actions" / "deploy-cloudflare-dashboard" / "action.yml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def shape(key: str) -> str:
    return re.sub(r"\$\{\{.*?\}\}", "*", key)


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
