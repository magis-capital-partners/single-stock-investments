"""verify_pr_checks.py: the last look before automerge squashes a SHA.

The fixtures are the check data GitHub reported for real PR heads on
2026-09-24, trimmed to the fields the verifier reads.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "verify_pr_checks.py"
spec = importlib.util.spec_from_file_location("verify_pr_checks", SCRIPT)
vpc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = vpc
spec.loader.exec_module(vpc)

QUALITY = "Research quality"
AUTOMERGE = "Auto - Agent PR Merge"
QUALITY_ID, AUTOMERGE_ID = 101, 202


def run(name, suite, *, number, status="completed", conclusion="success",
        created="2026-09-24T19:37:43Z", workflow_id=None):
    ids = {QUALITY: QUALITY_ID, AUTOMERGE: AUTOMERGE_ID}
    return {
        "name": name, "check_suite_id": suite, "run_number": number, "run_attempt": 1,
        "status": status, "conclusion": conclusion if status == "completed" else None,
        "created_at": created, "workflow_id": workflow_id or ids.get(name, 900 + suite % 97),
    }


def check(name, suite, *, status="completed", conclusion="success"):
    return {"name": name, "check_suite": {"id": suite}, "status": status,
            "conclusion": conclusion if status == "completed" else None}


# PR #1020 head 0448b9797e: every Research quality job green; automerge's own
# jobs present in their own suite.
GREEN_RUNS = [run(QUALITY, 97623145407, number=1080), run(AUTOMERGE, 97623145893, number=1425)]
GREEN_CHECKS = [
    check("changes", 97623145407),
    check("research-lint", 97623145407),
    check("graph-invariants", 97623145407),
    check("fact-ledger-currency", 97623145407),
    check("dashboard-integrity", 97623145407),
    check("ssi-pipeline", 97623145407, conclusion="skipped"),
    check("cloud-prompt-sync", 97623145407, conclusion="skipped"),
    check("resolve-pr", 97623145893),
    check("gate", 97623145893),
    check("merge", 97623145893, status="in_progress"),
]

# PR #1021 head 6231144a5b, the resolver's push: squashed at 20:35:02 with no
# check run at all, both workflow runs failed without creating a job.
UNTESTED_1021 = [
    run(AUTOMERGE, 97641249999, number=1431, conclusion="failure", created="2026-09-24T20:34:54Z"),
    run(QUALITY, 97641250321, number=1083, conclusion="failure", created="2026-09-24T20:34:54Z"),
]


def verdict(checks, runs, statuses=None, **kwargs):
    kwargs.setdefault("require_workflows", [QUALITY])
    kwargs.setdefault("exclude_workflows", [AUTOMERGE])
    return vpc.assess(checks, runs, statuses, **kwargs)


def test_a_fully_green_head_passes_while_automerge_itself_is_still_running():
    assert verdict(GREEN_CHECKS, GREEN_RUNS) == ([], [])


def test_the_untested_resolver_heads_that_were_squashed_are_refused():
    red, _ = verdict([], UNTESTED_1021)
    assert "failure: workflow 'Research quality'" in red, red
    assert "required workflow 'Research quality' did not succeed" in red, red


def test_a_head_with_no_research_quality_run_waits_for_it():
    red, pending = verdict([check("changes", 1)], [run("Something else", 1, number=5)])
    assert not red
    assert any("missing: required workflow 'Research quality'" in p for p in pending), pending


def test_any_red_check_blocks_even_outside_the_required_workflow():
    runs = GREEN_RUNS + [run("LLM Workflow Governance", 555, number=77, conclusion="failure")]
    checks = GREEN_CHECKS + [check("validate", 555, conclusion="failure")]
    red, _ = verdict(checks, runs)
    assert "failure: LLM Workflow Governance / validate" in red


def test_a_pending_check_is_pending_not_red():
    checks = [c if c["name"] != "graph-invariants" else check("graph-invariants", 97623145407, status="in_progress")
              for c in GREEN_CHECKS]
    runs = [run(QUALITY, 97623145407, number=1080, status="in_progress"), GREEN_RUNS[1]]
    red, pending = verdict(checks, runs)
    assert not red
    assert "in_progress: Research quality / graph-invariants" in pending
    assert "in_progress: workflow 'Research quality'" in pending


def test_a_superseded_run_of_the_same_workflow_does_not_count():
    # A cancel-in-progress leaves a cancelled older run on the same SHA; only
    # the newest run describes the commit.
    older = run(QUALITY, 111, number=1079, conclusion="cancelled", created="2026-09-24T19:30:00Z")
    runs = GREEN_RUNS + [older]
    checks = GREEN_CHECKS + [check("graph-invariants", 111, conclusion="cancelled")]
    assert verdict(checks, runs) == ([], [])


def test_two_workflows_with_one_name_cannot_hide_a_red_run():
    """Keyed by name, a newer green run of one workflow hid a red run of another."""
    red_one = run("Checks", 301, number=10, conclusion="failure", workflow_id=7, created="2026-09-24T19:00:00Z")
    green_other = run("Checks", 302, number=11, conclusion="success", workflow_id=8, created="2026-09-24T19:05:00Z")
    red, _ = verdict([check("test", 301, conclusion="failure"), check("test", 302)],
                     GREEN_RUNS + [red_one, green_other])
    assert "failure: workflow 'Checks'" in red
    assert "failure: Checks / test" in red


def test_commit_statuses_count():
    statuses = [
        {"context": "ci/legacy", "state": "failure"},
        {"context": "ci/other", "state": "error"},
        {"context": "ci/slow", "state": "pending"},
        {"context": "ci/ok", "state": "success"},
    ]
    red, pending = verdict(GREEN_CHECKS, GREEN_RUNS, statuses)
    assert "failure: status 'ci/legacy'" in red
    assert "error: status 'ci/other'" in red
    assert pending == ["pending: status 'ci/slow'"]


def test_zero_checks_is_allowed_only_when_asked():
    assert verdict([], [], require_workflows=[]) == ([], ["no checks reported on this commit yet"])
    assert verdict([], [], require_workflows=[], allow_no_checks=True) == ([], [])


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def pending_then(green_after: int):
    calls = {"n": 0}
    slow = [run(QUALITY, 97623145407, number=1080, status="in_progress"), GREEN_RUNS[1]]

    def fetch(repo, sha):
        calls["n"] += 1
        runs = GREEN_RUNS if calls["n"] > green_after else slow
        return GREEN_CHECKS, runs, []

    return fetch, calls


def test_pending_checks_are_polled_until_green():
    clock = Clock()
    fetch, calls = pending_then(green_after=2)
    code = vpc.verify("o/r", "abc", require_workflows=[QUALITY], exclude_workflows=[AUTOMERGE],
                      wait_seconds=600, poll_seconds=30, fetch_fn=fetch,
                      sleep_fn=clock.sleep, now_fn=lambda: clock.now)
    assert code == vpc.EXIT_GREEN
    assert calls["n"] == 3 and clock.sleeps == [30, 30]


def test_still_pending_after_the_wait_is_blocked_will_retry(capsys):
    clock = Clock()
    fetch, _ = pending_then(green_after=10**6)
    code = vpc.verify("o/r", "abc", require_workflows=[QUALITY], exclude_workflows=[AUTOMERGE],
                      wait_seconds=600, poll_seconds=30, fetch_fn=fetch,
                      sleep_fn=clock.sleep, now_fn=lambda: clock.now)
    assert code == vpc.EXIT_PENDING
    assert sum(clock.sleeps) == 600
    assert "BLOCKED, WILL RETRY" in capsys.readouterr().out


def test_red_fails_at_once_without_waiting():
    clock = Clock()
    code = vpc.verify("o/r", "abc", require_workflows=[QUALITY], exclude_workflows=[AUTOMERGE],
                      fetch_fn=lambda repo, sha: ([], UNTESTED_1021, []),
                      sleep_fn=clock.sleep, now_fn=lambda: clock.now)
    assert code == vpc.EXIT_RED and clock.sleeps == []


def test_cli_reads_github_and_exits_nonzero_for_the_1021_head(monkeypatch, capsys):
    pages = {"check-runs": [], "actions/runs": UNTESTED_1021, "/status": []}

    def fake_run(cmd, capture_output, text, check):
        assert cmd[:3] == ["gh", "api", "--paginate"]
        key = next(k for k in pages if k in cmd[3])
        out = "\n".join(json.dumps(row) for row in pages[key])
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(vpc.subprocess, "run", fake_run)
    code = vpc.main([
        "--repo", "o/r", "--sha", "6231144a5b8d713646312ad72287ac0a49538793",
        "--require-workflow", QUALITY, "--exclude-workflow", AUTOMERGE,
    ])
    assert code == vpc.EXIT_RED
    assert "NOT GREEN" in capsys.readouterr().out


def test_cli_reports_api_errors_as_usage_errors(monkeypatch):
    def failing_run(cmd, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="HTTP 502")

    monkeypatch.setattr(vpc.subprocess, "run", failing_run)
    assert vpc.main(["--repo", "o/r", "--sha", "abc"]) == vpc.EXIT_API
