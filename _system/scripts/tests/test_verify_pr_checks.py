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


def run(name, suite, *, number, status="completed", conclusion="success", created="2026-09-24T19:37:43Z"):
    return {
        "name": name, "check_suite_id": suite, "run_number": number, "run_attempt": 1,
        "status": status, "conclusion": conclusion if status == "completed" else None,
        "created_at": created,
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


def verdict(checks, runs, **kwargs):
    kwargs.setdefault("require_workflows", [QUALITY])
    kwargs.setdefault("exclude_workflows", [AUTOMERGE])
    return vpc.evaluate(checks, runs, **kwargs)


def test_a_fully_green_head_passes_while_automerge_itself_is_still_running():
    assert verdict(GREEN_CHECKS, GREEN_RUNS) == []


def test_the_untested_resolver_heads_that_were_squashed_are_refused():
    problems = verdict([], UNTESTED_1021)
    assert any("failure: workflow 'Research quality'" in p for p in problems), problems
    assert any("required workflow 'Research quality' is failure" in p for p in problems), problems


def test_a_head_with_no_research_quality_run_is_refused():
    problems = verdict([check("changes", 1)], [run("Something else", 1, number=5)])
    assert any("missing: required workflow 'Research quality'" in p for p in problems), problems


def test_any_red_check_blocks_even_outside_the_required_workflow():
    runs = GREEN_RUNS + [run("LLM Workflow Governance", 555, number=77, conclusion="failure")]
    checks = GREEN_CHECKS + [check("validate", 555, conclusion="failure")]
    problems = verdict(checks, runs)
    assert "failure: LLM Workflow Governance / validate" in problems


def test_a_pending_check_blocks():
    checks = [c if c["name"] != "graph-invariants" else check("graph-invariants", 97623145407, status="in_progress")
              for c in GREEN_CHECKS]
    runs = [run(QUALITY, 97623145407, number=1080, status="in_progress"), GREEN_RUNS[1]]
    problems = verdict(checks, runs)
    assert "pending: Research quality / graph-invariants" in problems
    assert any("still in_progress" in p for p in problems)


def test_a_superseded_run_of_the_same_workflow_does_not_count():
    # A cancel-in-progress leaves a cancelled older run on the same SHA; only
    # the newest run describes the commit.
    older = run(QUALITY, 111, number=1079, conclusion="cancelled", created="2026-09-24T19:30:00Z")
    runs = GREEN_RUNS + [older]
    checks = GREEN_CHECKS + [check("graph-invariants", 111, conclusion="cancelled")]
    assert verdict(checks, runs) == []


def test_zero_checks_is_allowed_only_when_asked():
    assert verdict([], [], require_workflows=[]) == ["no checks reported on this commit"]
    assert verdict([], [], require_workflows=[], allow_no_checks=True) == []


def test_cli_reads_github_and_exits_nonzero_for_the_1021_head(tmp_path, monkeypatch, capsys):
    pages = {
        "check-runs": [],
        "actions/runs": UNTESTED_1021,
    }

    def fake_run(cmd, capture_output, text, check):
        assert cmd[:3] == ["gh", "api", "--paginate"]
        key = "check-runs" if "check-runs" in cmd[3] else "actions/runs"
        out = "\n".join(json.dumps(row) for row in pages[key])
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(vpc.subprocess, "run", fake_run)
    code = vpc.main([
        "--repo", "o/r", "--sha", "6231144a5b8d713646312ad72287ac0a49538793",
        "--require-workflow", QUALITY, "--exclude-workflow", AUTOMERGE,
    ])
    assert code == 1
    assert "NOT GREEN" in capsys.readouterr().out


def test_cli_reports_api_errors_as_usage_errors(monkeypatch):
    def failing_run(cmd, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="HTTP 502")

    monkeypatch.setattr(vpc.subprocess, "run", failing_run)
    assert vpc.main(["--repo", "o/r", "--sha", "abc"]) == 2
