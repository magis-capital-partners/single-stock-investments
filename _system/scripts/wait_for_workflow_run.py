#!/usr/bin/env python3
"""Wait for a GitHub Actions workflow run on a commit SHA to succeed.

Unlike lewagon/wait-on-check-action, this does not fail when matching checks
have not been created yet. It polls until a run appears and concludes, or
until the timeout elapses.

Exit codes:
  0 — workflow concluded success (or skipped with --allow-skipped)
  1 — workflow concluded failure/cancelled, or timeout with no success
  2 — usage / API error
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any


TERMINAL_FAIL = {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
TERMINAL_OK = {"success"}
TERMINAL_SKIP = {"skipped", "neutral"}


def _gh_json(args: list[str], *, token: str) -> Any:
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    proc = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "gh api failed").strip())
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def _matches_workflow(run: dict[str, Any], workflow: str) -> bool:
    wanted = workflow.lower().strip()
    return (
        (run.get("name") or "").lower() == wanted
        or (run.get("path") or "").lower().endswith(wanted)
        or (run.get("path") or "").lower() == wanted
    )


def run_titles_sha(run: dict[str, Any], sha: str) -> bool:
    """A repository_dispatch run is stored on the default branch.

    research-quality.yml sets run-name to "research-quality-pr <number> <sha>"
    so the run can still be found from the commit it actually tested.
    """
    parts = str(run.get("display_title") or "").split()
    return len(parts) >= 3 and parts[0] == "research-quality-pr" and parts[-1] == sha


def list_workflow_runs(repo: str, workflow: str, sha: str, token: str) -> list[dict[str, Any]]:
    # workflow can be file name or workflow name; prefer name filter client-side.
    path = f"repos/{repo}/actions/runs?per_page=30&head_sha={sha}"
    data = _gh_json([path], token=token)
    runs = [
        run
        for run in (data.get("workflow_runs") or [])
        if _matches_workflow(run, workflow)
    ]
    if runs:
        return runs
    recent = _gh_json([f"repos/{repo}/actions/runs?per_page=50"], token=token)
    return [
        run
        for run in (recent.get("workflow_runs") or [])
        if _matches_workflow(run, workflow) and run_titles_sha(run, sha)
    ]


def _run_sort_key(run: dict[str, Any]) -> tuple:
    return (
        str(run.get("created_at") or ""),
        str(run.get("updated_at") or ""),
        int(run.get("run_number") or 0),
        int(run.get("id") or 0),
    )


def newest_run(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Newest by created_at. The list API is newest-first, but a merged
    head_sha query plus a title search is not."""
    return max(runs, key=_run_sort_key)


def evaluate_runs(
    runs: list[dict[str, Any]],
    *,
    allow_skipped: bool,
) -> str:
    """Return 'success', 'failure', 'pending', 'superseded', or 'absent'.

    A cancelled run is not a failed test. Research quality cancels the older
    run when a newer one for the same PR starts, and a job that hits its
    timeout is also reported as cancelled (AMZN PR #1144, run 37996092550,
    fact-ledger checkout, 2026-10-09). The caller waits for or starts the
    current run. A real failure still fails immediately.
    """
    if not runs:
        return "absent"
    # Judge the latest run only. An older cancelled run must not hide a newer
    # in-progress or successful one, and an older success must not excuse a
    # newer failure.
    run = newest_run(runs)
    status = (run.get("status") or "").lower()
    conclusion = (run.get("conclusion") or "").lower()
    if status != "completed":
        return "pending"
    if conclusion in TERMINAL_OK:
        return "success"
    if allow_skipped and conclusion in TERMINAL_SKIP:
        return "success"
    if conclusion == "cancelled":
        return "superseded"
    if conclusion in TERMINAL_FAIL or conclusion in TERMINAL_SKIP:
        return "failure"
    return "pending"


def dispatch_research_quality(repo: str, sha: str, pr: str, token: str) -> None:
    """Start Research quality for this PR commit.

    repository_dispatch runs the workflow file on the default branch and checks
    out the sha in the payload. GITHUB_TOKEN may start this event. It may not
    start a pull_request run.
    """
    body = json.dumps(
        {
            "event_type": "research-quality-pr",
            "client_payload": {"pr": pr, "sha": sha},
        }
    )
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    proc = subprocess.run(
        ["gh", "api", "--method", "POST", f"repos/{repo}/dispatches", "--input", "-"],
        input=body,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "dispatch failed").strip())


def wait_for_workflow(
    *,
    repo: str,
    workflow: str,
    sha: str,
    token: str,
    timeout_seconds: int,
    poll_seconds: int,
    allow_skipped: bool,
    sleep_fn=time.sleep,
    now_fn=time.time,
    list_fn=list_workflow_runs,
    rerun_fn=None,
    max_reruns: int = 1,
) -> int:
    deadline = now_fn() + timeout_seconds
    last_state = "absent"
    ignored: set[Any] = set()
    # An older success must not excuse a newer cancelled run. Once the latest
    # run is cancelled, only a run started after it counts.
    floor: tuple | None = None
    reruns = 0
    while now_fn() < deadline:
        runs = list_fn(repo, workflow, sha, token)
        fresh = [
            run for run in runs
            if run.get("id") not in ignored
            and (floor is None or _run_sort_key(run) > floor)
        ]
        state = evaluate_runs(fresh, allow_skipped=allow_skipped)
        last_state = state
        if state == "success":
            print(f"OK: workflow '{workflow}' on {sha[:12]} concluded successfully.")
            return 0
        if state == "failure":
            run = newest_run(fresh)
            print(
                f"FAIL: workflow '{workflow}' on {sha[:12]} concluded "
                f"{run.get('conclusion')} ({run.get('html_url')})",
                file=sys.stderr,
            )
            return 1
        if state == "superseded":
            run = newest_run(fresh)
            floor = _run_sort_key(run)
            ignored.add(run.get("id"))
            url = run.get("html_url") or run.get("id")
            if rerun_fn is not None and reruns < max_reruns:
                reruns += 1
                # The cancelled run already used the clock (AMZN PR #1144
                # waited out a 30-minute checkout, then the job was cancelled).
                # The fresh check gets one full window. max_reruns bounds it.
                deadline = now_fn() + timeout_seconds
                print(
                    f"workflow '{workflow}' on {sha[:12]} was cancelled "
                    f"({url}). Waiting for the latest run on this commit, "
                    f"and starting a fresh check (rerun {reruns}/{max_reruns})."
                )
                try:
                    rerun_fn()
                except RuntimeError as exc:
                    print(f"::warning::could not start a fresh check: {exc}", file=sys.stderr)
            elif rerun_fn is not None:
                print(
                    f"FAIL: workflow '{workflow}' on {sha[:12]} was cancelled "
                    f"again after {reruns} fresh check(s) ({url})",
                    file=sys.stderr,
                )
                return 1
            else:
                print(
                    f"workflow '{workflow}' on {sha[:12]} was cancelled ({url}). "
                    "Waiting for a newer run on this commit."
                )
            sleep_fn(poll_seconds)
            continue
        print(f"waiting: workflow '{workflow}' on {sha[:12]} state={state}")
        sleep_fn(poll_seconds)
    print(
        f"FAIL: timed out after {timeout_seconds}s waiting for '{workflow}' "
        f"on {sha[:12]} (last_state={last_state})",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--sha", required=True, help="head commit SHA")
    parser.add_argument("--workflow", required=True, help="workflow name or file")
    parser.add_argument("--timeout-seconds", type=int, default=2700)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument(
        "--allow-skipped",
        action="store_true",
        help="Treat skipped/neutral conclusions as success",
    )
    parser.add_argument(
        "--rerun-on-cancelled",
        action="store_true",
        help="If the latest run for this SHA was cancelled, dispatch a fresh Research quality run and wait for it",
    )
    parser.add_argument("--pr", default="", help="PR number, required with --rerun-on-cancelled")
    parser.add_argument(
        "--token",
        default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "",
    )
    args = parser.parse_args(argv)
    if not args.token:
        print("FAIL: GH_TOKEN / GITHUB_TOKEN required", file=sys.stderr)
        return 2
    if args.rerun_on_cancelled and not args.pr:
        print("FAIL: --pr is required with --rerun-on-cancelled", file=sys.stderr)
        return 2
    rerun_fn = None
    if args.rerun_on_cancelled:
        def rerun_fn() -> None:
            dispatch_research_quality(args.repo, args.sha, args.pr, args.token)
    try:
        return wait_for_workflow(
            repo=args.repo,
            workflow=args.workflow,
            sha=args.sha,
            token=args.token,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            allow_skipped=args.allow_skipped,
            rerun_fn=rerun_fn,
        )
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
