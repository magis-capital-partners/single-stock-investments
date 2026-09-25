#!/usr/bin/env python3
"""Verify that every CI check on one exact commit is green.

The automerge gate waits for a named workflow; this is the last look before
the squash, taken on the SHA that will be merged. It reads three sources:

* check runs (the jobs of every workflow run on the SHA),
* the workflow runs themselves (a run can fail before creating any job), and
* commit statuses (the older status API; failure and error are red).

Only the newest run of each *workflow* counts, keyed by workflow id, not by
display name: two workflows may share a name, and keying by name let a newer
green run of one hide a red run of the other. A run superseded by a later run
of the same workflow on the same SHA (a cancel-in-progress, a re-run) no longer
describes the commit. Runs of --exclude-workflow (automerge itself) are
ignored, since a job cannot wait for its own green.

Anything red fails at once. Anything still pending or queued is polled every
--poll-seconds for up to --wait-seconds before the verdict "blocked, will
retry".

Usage:
  python _system/scripts/verify_pr_checks.py --repo OWNER/NAME --sha SHA \\
      [--require-workflow "Research quality"] \\
      [--exclude-workflow "Auto - Agent PR Merge"] [--allow-no-checks] \\
      [--wait-seconds 600] [--poll-seconds 30]

Exit codes: 0 green; 1 red; 2 API or usage error; 3 still pending after the
wait (blocked, will retry).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Callable, Iterable

GREEN = {"success", "neutral", "skipped"}
STATUS_RED = {"failure", "error"}
EXIT_GREEN, EXIT_RED, EXIT_API, EXIT_PENDING = 0, 1, 2, 3


def _run_key(run: dict[str, Any]) -> tuple:
    return (int(run.get("run_number") or 0), int(run.get("run_attempt") or 0), str(run.get("created_at") or ""))


def workflow_key(run: dict[str, Any]) -> str:
    """Identity of the workflow a run belongs to: its id, else its file, else its name."""
    for field in ("workflow_id", "path", "name"):
        value = run.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return "name:"


def newest_runs(workflow_runs: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The newest run of each workflow, keyed by workflow_key()."""
    newest: dict[str, dict[str, Any]] = {}
    for run in workflow_runs:
        key = workflow_key(run)
        if key not in newest or _run_key(run) > _run_key(newest[key]):
            newest[key] = run
    return newest


def _matches(run: dict[str, Any], wanted: str) -> bool:
    return str(run.get("name") or "") == wanted or str(run.get("path") or "").endswith(wanted)


def assess(
    check_runs: list[dict[str, Any]],
    workflow_runs: list[dict[str, Any]],
    statuses: list[dict[str, Any]] | None = None,
    *,
    require_workflows: Iterable[str] = (),
    exclude_workflows: Iterable[str] = (),
    allow_no_checks: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (red, pending) reasons; both empty means green."""
    excluded_names = set(exclude_workflows)
    excluded_keys = {workflow_key(run) for run in workflow_runs
                     if any(_matches(run, name) for name in excluded_names)}
    current = {key: run for key, run in newest_runs(workflow_runs).items() if key not in excluded_keys}
    suite_owner = {run.get("check_suite_id"): workflow_key(run) for run in workflow_runs}
    current_suites = {run.get("check_suite_id") for run in current.values()}

    red: list[str] = []
    pending: list[str] = []
    counted = 0
    for check in check_runs:
        suite = (check.get("check_suite") or {}).get("id")
        owner = suite_owner.get(suite)
        if owner is not None and (owner in excluded_keys or suite not in current_suites):
            continue  # automerge's own jobs, or a superseded run of some workflow
        counted += 1
        label = str(check.get("name"))
        if owner is not None:
            label = f"{current_run_name(current, suite)} / {label}"
        if check.get("status") != "completed":
            pending.append(f"{check.get('status')}: {label}")
        elif check.get("conclusion") not in GREEN:
            red.append(f"{check.get('conclusion')}: {label}")

    for run in sorted(current.values(), key=lambda r: str(r.get("name"))):
        # Judge the run as well as its jobs: a job with `needs:` has no check
        # run until it is queued, and a run that fails before creating any job
        # (a workflow-file error, a startup failure) has no check runs at all.
        name = run.get("name")
        if run.get("status") != "completed":
            pending.append(f"{run.get('status')}: workflow {name!r}")
        elif run.get("conclusion") not in GREEN:
            red.append(f"{run.get('conclusion')}: workflow {name!r}")

    for status in statuses or []:
        state = str(status.get("state") or "")
        label = f"status {status.get('context')!r}"
        if state in STATUS_RED:
            red.append(f"{state}: {label}")
        elif state == "pending":
            pending.append(f"pending: {label}")

    for wanted in require_workflows:
        runs = [run for run in current.values() if _matches(run, wanted)]
        if not runs:
            pending.append(f"missing: required workflow {wanted!r} has no run on this commit yet")
        elif not any(run.get("status") == "completed" and run.get("conclusion") == "success" for run in runs):
            if all(run.get("status") == "completed" for run in runs):
                red.append(f"required workflow {wanted!r} did not succeed")

    if counted == 0 and not current and not statuses and not allow_no_checks:
        pending.append("no checks reported on this commit yet")
    return red, pending


def current_run_name(current: dict[str, dict[str, Any]], suite: Any) -> str:
    for run in current.values():
        if run.get("check_suite_id") == suite:
            return str(run.get("name"))
    return "?"


def evaluate(*args, **kwargs) -> list[str]:
    """Every reason the commit is not green (red first); empty means green."""
    red, pending = assess(*args, **kwargs)
    return red + pending


def _gh_lines(path: str, jq: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["gh", "api", "--paginate", path, "--jq", jq],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"gh api {path} failed").strip())
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def fetch(repo: str, sha: str) -> tuple[list, list, list]:
    check_runs = _gh_lines(f"repos/{repo}/commits/{sha}/check-runs?per_page=100", ".check_runs[]")
    workflow_runs = _gh_lines(f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100", ".workflow_runs[]")
    statuses = _gh_lines(f"repos/{repo}/commits/{sha}/status?per_page=100", ".statuses[]")
    return check_runs, workflow_runs, statuses


def verify(
    repo: str,
    sha: str,
    *,
    require_workflows: Iterable[str] = (),
    exclude_workflows: Iterable[str] = (),
    allow_no_checks: bool = False,
    wait_seconds: float = 600,
    poll_seconds: float = 30,
    fetch_fn: Callable[[str, str], tuple[list, list, list]] = fetch,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], float] = time.monotonic,
) -> int:
    deadline = now_fn() + wait_seconds
    while True:
        try:
            check_runs, workflow_runs, statuses = fetch_fn(repo, sha)
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read checks for {sha}: {exc}", file=sys.stderr)
            return EXIT_API
        red, pending = assess(
            check_runs, workflow_runs, statuses,
            require_workflows=require_workflows,
            exclude_workflows=exclude_workflows,
            allow_no_checks=allow_no_checks,
        )
        if red:
            print(f"NOT GREEN: {sha}")
            for reason in red + pending:
                print(f"  - {reason}")
            return EXIT_RED
        if not pending:
            print(f"GREEN: every check on {sha} passed ({len(check_runs)} check run(s), "
                  f"{len(statuses)} status(es) read).")
            return EXIT_GREEN
        if now_fn() >= deadline:
            print(f"BLOCKED, WILL RETRY: {len(pending)} check(s) on {sha} still pending after "
                  f"{int(wait_seconds)}s:")
            for reason in pending:
                print(f"  - {reason}")
            return EXIT_PENDING
        print(f"waiting on {len(pending)} pending check(s): {'; '.join(pending[:3])}")
        sleep_fn(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--require-workflow", action="append", default=[],
                        help="Workflow name or file that must have succeeded on the SHA.")
    parser.add_argument("--exclude-workflow", action="append", default=[],
                        help="Workflow name or file to ignore (the caller's own workflow).")
    parser.add_argument("--allow-no-checks", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=600)
    parser.add_argument("--poll-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    return verify(
        args.repo, args.sha,
        require_workflows=args.require_workflow,
        exclude_workflows=args.exclude_workflow,
        allow_no_checks=args.allow_no_checks,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
