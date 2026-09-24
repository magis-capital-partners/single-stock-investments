#!/usr/bin/env python3
"""Verify that every CI check on one exact commit is green.

The automerge gate waits for a named workflow; this is the last look before
the squash, taken on the SHA that will be merged. It fails when anything on
that SHA is pending, red, or missing, so a check that goes red after the gate
(or a workflow that never started) blocks the merge instead of riding along.

Only the newest run of each workflow counts. A run superseded by a later run
of the same workflow on the same SHA (a cancel-in-progress, a re-run) no
longer describes the commit. Runs of --exclude-workflow (automerge itself)
are ignored, since a job cannot wait for its own green.

Usage:
  python _system/scripts/verify_pr_checks.py --repo OWNER/NAME --sha SHA \\
      [--require-workflow "Research quality"] \\
      [--exclude-workflow "Auto - Agent PR Merge"] [--allow-no-checks]

Exit codes: 0 green, 1 not green (the reasons are printed), 2 API or usage error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any, Iterable

GREEN = {"success", "neutral", "skipped"}


def _run_key(run: dict[str, Any]) -> tuple:
    return (int(run.get("run_number") or 0), int(run.get("run_attempt") or 0), str(run.get("created_at") or ""))


def newest_runs(workflow_runs: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The newest run of each workflow, keyed by workflow name."""
    newest: dict[str, dict[str, Any]] = {}
    for run in workflow_runs:
        name = str(run.get("name") or "")
        if name not in newest or _run_key(run) > _run_key(newest[name]):
            newest[name] = run
    return newest


def evaluate(
    check_runs: list[dict[str, Any]],
    workflow_runs: list[dict[str, Any]],
    *,
    require_workflows: Iterable[str] = (),
    exclude_workflows: Iterable[str] = (),
    allow_no_checks: bool = False,
) -> list[str]:
    """Return the reasons the commit is not green; an empty list means green."""
    excluded = set(exclude_workflows)
    current = {name: run for name, run in newest_runs(workflow_runs).items() if name not in excluded}
    suite_to_workflow = {run.get("check_suite_id"): str(run.get("name") or "") for run in workflow_runs}
    current_suites = {run.get("check_suite_id") for run in current.values()}

    problems: list[str] = []
    counted = 0
    for check in check_runs:
        suite = (check.get("check_suite") or {}).get("id")
        workflow = suite_to_workflow.get(suite)
        if workflow is not None and (workflow in excluded or suite not in current_suites):
            continue  # automerge's own jobs, or a superseded run of some workflow
        counted += 1
        label = f"{workflow} / {check.get('name')}" if workflow else str(check.get("name"))
        if check.get("status") != "completed":
            problems.append(f"pending: {label}")
        elif check.get("conclusion") not in GREEN:
            problems.append(f"{check.get('conclusion')}: {label}")

    for name, run in sorted(current.items()):
        # Judge the run as well as its jobs: a job with `needs:` has no check
        # run until it is queued, and a run that fails before creating any job
        # (a workflow-file error, a startup failure) has no check runs at all.
        if run.get("status") != "completed":
            problems.append(f"pending: workflow {name!r} is still {run.get('status')}")
        elif run.get("conclusion") not in GREEN:
            problems.append(f"{run.get('conclusion')}: workflow {name!r}")

    for name in require_workflows:
        run = current.get(name)
        if run is None:
            problems.append(f"missing: required workflow {name!r} has no run on this commit")
        elif run.get("status") != "completed" or run.get("conclusion") != "success":
            conclusion = run.get("conclusion") or run.get("status")
            problems.append(f"required workflow {name!r} is {conclusion}, not success")

    if counted == 0 and not current and not allow_no_checks:
        problems.append("no checks reported on this commit")
    return problems


def _gh_lines(path: str, jq: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["gh", "api", "--paginate", path, "--jq", jq],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"gh api {path} failed").strip())
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--require-workflow", action="append", default=[])
    parser.add_argument("--exclude-workflow", action="append", default=[])
    parser.add_argument("--allow-no-checks", action="store_true")
    args = parser.parse_args(argv)
    try:
        check_runs = _gh_lines(
            f"repos/{args.repo}/commits/{args.sha}/check-runs?per_page=100", ".check_runs[]"
        )
        workflow_runs = _gh_lines(
            f"repos/{args.repo}/actions/runs?head_sha={args.sha}&per_page=100", ".workflow_runs[]"
        )
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read checks for {args.sha}: {exc}", file=sys.stderr)
        return 2
    problems = evaluate(
        check_runs,
        workflow_runs,
        require_workflows=args.require_workflow,
        exclude_workflows=args.exclude_workflow,
        allow_no_checks=args.allow_no_checks,
    )
    if problems:
        print(f"NOT GREEN: {args.sha}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"GREEN: every check on {args.sha} passed ({len(check_runs)} check run(s) read).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
