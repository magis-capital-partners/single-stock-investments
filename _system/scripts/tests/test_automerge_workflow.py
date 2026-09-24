"""Contract tests for .github/workflows/marvin-pr-automerge.yml.

Each test pins one failure seen in production (run IDs in the docstrings) to
the property of the workflow file that prevents it.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "marvin-pr-automerge.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def step(job: dict, name_fragment: str) -> dict:
    matches = [s for s in job["steps"] if name_fragment in str(s.get("name", ""))]
    assert len(matches) == 1, f"expected one step named like {name_fragment!r}, got {[s.get('name') for s in matches]}"
    return matches[0]


def step_index(job: dict, name_fragment: str) -> int:
    return next(i for i, s in enumerate(job["steps"]) if name_fragment in str(s.get("name", "")))


def test_the_squash_is_pinned_to_the_sha_the_gate_passed():
    """PRs #1017 and #1021 were squashed at heads no gate had seen."""
    merge = load()["jobs"]["merge"]
    assert "needs.gate.outputs.head_sha" in merge["env"]["GATED_SHA"]
    assert "needs.code-gate.outputs.head_sha" in merge["env"]["GATED_SHA"]
    squash = step(merge, "Squash merge and delete branch")
    assert '-f sha="$GATED_SHA"' in squash["run"]
    # The merge job only runs for a SHA a gate actually handed over.
    assert "needs.gate.outputs.head_sha != ''" in merge["if"]
    assert "needs.code-gate.outputs.head_sha != ''" in merge["if"]


def test_a_resolver_push_is_never_merged_in_the_same_run():
    """Run 35948543025 pushed a resolution at 03:07:46 and squashed it at 03:08:00."""
    merge = load()["jobs"]["merge"]
    resolve = step(merge, "Resolve merge conflicts")
    assert "--github-output" in resolve["run"]
    for later in ("Verify every check", "Ensure mergeable", "Squash merge"):
        assert "steps.resolve.outputs.pushed != 'true'" in step(merge, later)["if"], later
        assert "resolve_marvin_pr_conflicts.py" not in step(merge, later)["run"], later


def test_every_check_on_the_gated_sha_is_verified_before_the_squash():
    merge = load()["jobs"]["merge"]
    verify = step(merge, "Verify every check")
    assert "verify_pr_checks.py" in verify["run"]
    assert '--sha "$GATED_SHA"' in verify["run"]
    assert '--require-workflow "Research quality"' in verify["run"]
    assert '--exclude-workflow "Auto - Agent PR Merge"' in verify["run"]
    assert step_index(merge, "Verify every check") < step_index(merge, "Squash merge")


def test_provenance_is_read_at_the_pinned_sha_not_the_branch_name():
    """AM2 (run 36045846504): the twin run read ?ref=<branch> after the branch
    was deleted and failed with HTTP 404."""
    gate = load()["jobs"]["gate"]
    provenance = step(gate, "Verify immutable agent provenance")
    assert "?ref=$SHA" in provenance["run"]
    assert "HEAD_REF" not in provenance["run"]
    assert "steps.head.outputs.sha" in provenance["env"]["SHA"]
    wait = step(gate, "Wait for Research quality")
    assert "steps.head.outputs.sha" in wait["run"]
    assert "steps.validated.outputs.sha" in gate["outputs"]["head_sha"]


def test_pr_state_is_rechecked_before_every_side_effect():
    """The twin run commented "Automerge is blocked" on merged PRs #1013, #1018
    and #1020."""
    jobs = load()["jobs"]
    first_gate_step = jobs["gate"]["steps"][0]
    assert "--json state" in first_gate_step["run"]
    notify = jobs["notify"]["steps"][0]["run"]
    assert notify.index("--json state") < notify.index("--method POST")
    squash = step(jobs["merge"], "Squash merge")["run"]
    assert squash.index("--json state") < squash.index("--method PUT")
    assert "merge=false" in step(jobs["merge"], "Skip unless the PR is still open")["run"]


def test_workflow_run_only_reacts_to_pull_request_runs():
    """Research quality now also runs on push and on a schedule against main."""
    condition = load()["jobs"]["resolve-pr"]["if"]
    assert "github.event.workflow_run.event == 'pull_request'" in condition
    assert "github.event.workflow_run.conclusion == 'success'" in condition


def test_validators_and_resolver_run_from_the_base_branch():
    jobs = load()["jobs"]
    for job_name in ("gate", "merge"):
        checkout = next(s for s in jobs[job_name]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
        assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}", job_name
        # Blobless and sparse: the old full-tree checkout took 10-13 minutes,
        # which is the window the twin-run race lived in.
        assert checkout["with"]["filter"] == "blob:none", job_name
        assert "/_system/scripts/" in checkout["with"]["sparse-checkout"], job_name


def test_code_lane_gate_pins_one_sha():
    code_gate = load()["jobs"]["code-gate"]
    script = step(code_gate, "Wait for every check")["run"]
    # The SHA is read once, before the loop, and handed to the merge job.
    assert script.index("SHA=$(gh pr view") < script.index("while :; do")
    assert re.search(r'echo "sha=\$SHA" >> "\$GITHUB_OUTPUT"', script)
    assert "steps.checks.outputs.sha" in code_gate["outputs"]["head_sha"]
