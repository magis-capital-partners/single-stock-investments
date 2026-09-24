"""Contract tests for .github/workflows/research-quality.yml.

The `changes` job's classifier is JavaScript run by actions/github-script. The
tests execute it in node with a stub `context`/`github`/`core`, so they check
what the job decides, not how the source looks.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "research-quality.yml"

HARNESS = r"""
const fs = require('fs');
const [scriptPath, eventName, filesJson] = process.argv.slice(2);
const files = JSON.parse(filesJson);
const outputs = {};
const summary = { addHeading() { return this; }, addTable() { return this; }, async write() {} };
const core = { setOutput: (key, value) => { outputs[key] = value; }, summary };
const payload = eventName === 'pull_request' ? { pull_request: { number: 1 } } : {};
const context = { eventName, payload, repo: { owner: 'o', repo: 'r' } };
const github = {
  paginate: async () => files.map(filename => ({ filename })),
  rest: { pulls: { listFiles: () => {} } },
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('github', 'context', 'core', fs.readFileSync(scriptPath, 'utf8'))(github, context, core)
  .then(() => console.log(JSON.stringify(outputs)))
  .catch(error => { console.error(error); process.exit(1); });
"""


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def triggers() -> dict:
    data = load()
    return data.get("on", data.get(True))  # PyYAML reads the bare `on:` key as True


def classify(tmp_path: Path, event: str, files: list[str]) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = load()["jobs"]["changes"]["steps"][0]["with"]["script"]
    (tmp_path / "classify.js").write_text(script, encoding="utf-8")
    (tmp_path / "harness.js").write_text(HARNESS, encoding="utf-8")
    proc = subprocess.run(
        [node, str(tmp_path / "harness.js"), str(tmp_path / "classify.js"), event, json.dumps(files)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_main_head_is_tested_on_a_schedule_off_the_hour():
    """Bot pushes use GITHUB_TOKEN and start no workflow: after 2026-09-23 22:46
    nothing tested main for a day."""
    schedule = triggers()["schedule"]
    assert schedule, "research-quality needs a schedule"
    for entry in schedule:
        minute = entry["cron"].split()[0]
        assert minute.isdigit() and minute != "0", entry["cron"]


def test_a_scheduled_run_checks_main_like_a_push(tmp_path):
    outputs = classify(tmp_path, "schedule", [])
    assert outputs["graph_invariants"] == "true"
    assert outputs["fact_currency"] == "true"
    assert outputs["ssi_pipeline"] == "true"
    # The PR-only jobs need a base ref and stay off.
    assert outputs["research_lint"] == "false"
    assert outputs["dashboard_integrity"] == "false"


def test_a_pr_touching_only_a_falsifier_draft_runs_graph_invariants(tmp_path):
    """The CEG / #988 failure: a draft-only PR skipped the job that runs the
    history check's promotion simulation."""
    for draft in (
        "CEG/research/falsifier_drafts/f8685f88d1aff5b6b56d0eba.json",
        "CEG/research/falsifier_drafts/archive/old.json",
        "CEG/research/falsifier_drafts/README.md",
    ):
        outputs = classify(tmp_path, "pull_request", [draft])
        assert outputs["graph_invariants"] == "true", draft


def test_a_push_touching_only_a_falsifier_draft_triggers_the_workflow():
    assert "**/research/falsifier_drafts/**" in triggers()["push"]["paths"]


def test_the_history_job_runs_the_promotion_gate_suite_when_present():
    steps = load()["jobs"]["graph-invariants"]["steps"]
    history = next(s for s in steps if "immutable history" in str(s.get("name", "")))
    run = history["run"]
    assert "[ -f _system/scripts/tests/test_falsifier_promotion_gate.py ]" in run
    assert 'PROMOTION_GATE="tests.test_falsifier_promotion_gate"' in run
    assert "test_resolve_falsifiers $PROMOTION_GATE" in run


def test_a_pr_touching_only_a_deep_dive_skips_graph_invariants(tmp_path):
    outputs = classify(tmp_path, "pull_request", ["ABC/research/deep_dive_2026-09-01.md"])
    assert outputs["graph_invariants"] == "false"
    assert outputs["research_lint"] == "true"


def test_every_job_tests_the_exact_commit():
    data = load()
    assert data["env"]["CHECKOUT_SHA"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    for name, job in data["jobs"].items():
        for step in job.get("steps", []):
            run = str(step.get("run", ""))
            if "ci_checkout_workspace.sh" in run:
                assert '"$CHECKOUT_SHA"' in run, f"{name}: {run}"
                assert "pull/${{" not in run, f"{name}: {run}"
            uses = str(step.get("uses", ""))
            is_bootstrap = "ci_checkout_workspace.sh" in str(step.get("with", {}).get("sparse-checkout", ""))
            if uses.startswith("actions/checkout") and not is_bootstrap:
                # A real checkout (not the bootstrap that fetches the checkout
                # scripts) pins the commit too.
                assert step["with"]["ref"] == "${{ env.CHECKOUT_SHA }}", name


def test_warrant_problems_do_not_red_unrelated_research_prs():
    """9/11-9/18: "warrants.json reports structural contract errors" failed
    every research PR's dashboard-integrity job. The warrant lane enforces;
    the PR gate reports. Checkers that predate --warn-only keep the old run."""
    steps = load()["jobs"]["dashboard-integrity"]["steps"]
    run = next(s["run"] for s in steps if "check_warrant_universe.py" in str(s.get("run", "")))
    assert 'check_warrant_universe.py --help | grep -q -- "--warn-only"' in run
    assert "check_warrant_universe.py --warn-only" in run


def test_a_scheduled_run_judges_history_against_itself():
    steps = load()["jobs"]["graph-invariants"]["steps"]
    history = next(s for s in steps if "immutable history" in str(s.get("name", "")))
    assert '"${{ github.event_name }}" = "schedule"' in history["run"]
    assert 'HISTORY_BASE="HEAD"' in history["run"]
