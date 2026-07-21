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


def list_workflow_runs(repo: str, workflow: str, sha: str, token: str) -> list[dict[str, Any]]:
    # workflow can be file name or workflow name; prefer name filter client-side.
    path = f"repos/{repo}/actions/runs?per_page=30&head_sha={sha}"
    data = _gh_json([path], token=token)
    runs = data.get("workflow_runs") or []
    wanted = workflow.lower().strip()
    return [
        run
        for run in runs
        if (run.get("name") or "").lower() == wanted
        or (run.get("path") or "").lower().endswith(wanted)
        or (run.get("path") or "").lower() == wanted
    ]


def evaluate_runs(
    runs: list[dict[str, Any]],
    *,
    allow_skipped: bool,
) -> str:
    """Return 'success', 'failure', 'pending', or 'absent'."""
    if not runs:
        return "absent"
    # Prefer the newest run (API returns newest first).
    run = runs[0]
    status = (run.get("status") or "").lower()
    conclusion = (run.get("conclusion") or "").lower()
    if status != "completed":
        return "pending"
    if conclusion in TERMINAL_OK:
        return "success"
    if allow_skipped and conclusion in TERMINAL_SKIP:
        return "success"
    if conclusion in TERMINAL_FAIL or conclusion in TERMINAL_SKIP:
        return "failure"
    return "pending"


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
) -> int:
    deadline = now_fn() + timeout_seconds
    last_state = "absent"
    while now_fn() < deadline:
        runs = list_fn(repo, workflow, sha, token)
        state = evaluate_runs(runs, allow_skipped=allow_skipped)
        last_state = state
        if state == "success":
            print(f"OK: workflow '{workflow}' on {sha[:12]} concluded successfully.")
            return 0
        if state == "failure":
            run = runs[0]
            print(
                f"FAIL: workflow '{workflow}' on {sha[:12]} concluded "
                f"{run.get('conclusion')} ({run.get('html_url')})",
                file=sys.stderr,
            )
            return 1
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
        "--token",
        default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "",
    )
    args = parser.parse_args(argv)
    if not args.token:
        print("FAIL: GH_TOKEN / GITHUB_TOKEN required", file=sys.stderr)
        return 2
    try:
        return wait_for_workflow(
            repo=args.repo,
            workflow=args.workflow,
            sha=args.sha,
            token=args.token,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            allow_skipped=args.allow_skipped,
        )
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
