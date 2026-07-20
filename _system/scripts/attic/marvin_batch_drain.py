#!/usr/bin/env python3
"""Run Marvin cloud deep dives sequentially; wait for each PR to merge before the next."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
DEEP_DIVE_JS = SCRIPTS / "marvin_deep_dive.mjs"
RESOLVE_PY = SCRIPTS / "resolve_marvin_pr_conflicts.py"

PR_URL_RE = re.compile(r"^PR:\s*(https://github\.com/[^\s]+/pull/(\d+))", re.MULTILINE)


def run(cmd: list[str], *, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=check, env=merged)


def gh_json(args: list[str]) -> dict:
    import json

    return json.loads(run(["gh", *args]).stdout)


def parse_pr_from_output(stdout: str) -> tuple[str, str] | None:
    m = PR_URL_RE.search(stdout)
    if m:
        return m.group(1), m.group(2)
    return None


def find_open_pr_for_ticker(ticker: str) -> tuple[str, str] | None:
    import json

    out = run(["gh", "pr", "list", "--state", "open", "--json", "number,title,url,headRefName", "--limit", "100"])
    for row in json.loads(out.stdout):
        head = row.get("headRefName") or ""
        if not head.startswith("cursor/"):
            continue
        title = row.get("title") or ""
        if title.startswith(f"{ticker}:") or title.startswith(f"{ticker} "):
            return row["url"], str(row["number"])
    return None


def list_open_cursor_prs() -> list[str]:
    import json

    out = run(
        ["gh", "pr", "list", "--state", "open", "--json", "number,headRefName", "--limit", "100"],
        check=False,
    )
    numbers: list[int] = []
    for row in json.loads(out.stdout or "[]"):
        if (row.get("headRefName") or "").startswith("cursor/"):
            numbers.append(int(row["number"]))
    return [str(n) for n in sorted(numbers)]


def drain_open_cursor_prs() -> None:
    open_prs = list_open_cursor_prs()
    if not open_prs:
        return
    print(f"Draining {len(open_prs)} open cursor PR(s) oldest-first: {', '.join(f'#{n}' for n in open_prs)}")
    for pr_number in open_prs:
        ensure_pr_ready(pr_number)
        wait_for_pr_merged(pr_number)


def ensure_pr_ready(pr_number: str) -> None:
    data = gh_json(["pr", "view", pr_number, "--json", "isDraft"])
    if data.get("isDraft"):
        print(f"PR #{pr_number} is draft - marking ready.")
        run(["gh", "pr", "ready", pr_number], check=False)


def check_conclusion(checks: list[dict], name: str) -> str | None:
    for row in checks:
        row_name = row.get("name") or ""
        if row_name == name or name in row_name:
            return row.get("conclusion") or row.get("status")
    return None


def research_checks_passed(checks: list[dict]) -> bool:
    lint = check_conclusion(checks, "research-lint")
    sync = check_conclusion(checks, "cloud-prompt-sync")
    return lint in ("SUCCESS", "SKIPPED") and sync in ("SUCCESS", "SKIPPED")


def format_research_check_status(checks: list[dict]) -> str:
    lint = check_conclusion(checks, "research-lint") or "missing"
    sync = check_conclusion(checks, "cloud-prompt-sync") or "missing"
    return f"research-lint={lint}, cloud-prompt-sync={sync}"


def trigger_automerge(pr_number: str) -> None:
    run(
        ["gh", "workflow", "run", "marvin-pr-automerge.yml", "-f", f"pr_number={pr_number}"],
        check=False,
    )


def wait_for_pr_merged(
    pr_number: str,
    *,
    timeout_sec: int = 5400,
    poll_sec: int = 30,
    automerge_redispatch_sec: int = 1200,
) -> None:
    deadline = time.time() + timeout_sec
    last_automerge_at = 0.0
    last_checks: list[dict] = []
    while time.time() < deadline:
        data = gh_json(["pr", "view", pr_number, "--json", "state,mergeable,isDraft,statusCheckRollup"])
        state = data.get("state")
        mergeable = data.get("mergeable")

        if state == "MERGED":
            print(f"PR #{pr_number} merged.")
            return

        if data.get("isDraft"):
            ensure_pr_ready(pr_number)
            last_automerge_at = 0.0

        checks = data.get("statusCheckRollup") or []
        last_checks = checks
        check_status = format_research_check_status(checks)
        now = time.time()

        if mergeable == "CONFLICTING":
            print(f"PR #{pr_number} is CONFLICTING - running conflict resolver...")
            proc = run([sys.executable, str(RESOLVE_PY), pr_number], check=False)
            if proc.returncode != 0:
                print(proc.stderr or proc.stdout, file=sys.stderr)
            last_automerge_at = 0.0
            trigger_automerge(pr_number)
            last_automerge_at = now
            print(f"Dispatched automerge for PR #{pr_number} after conflict resolution.")
        elif mergeable == "MERGEABLE" and research_checks_passed(checks):
            if now - last_automerge_at >= automerge_redispatch_sec:
                trigger_automerge(pr_number)
                last_automerge_at = now
                print(f"Dispatched automerge for PR #{pr_number} ({check_status}).")

        print(f"Waiting on PR #{pr_number} (state={state}, mergeable={mergeable}, {check_status})...")
        time.sleep(poll_sec)

    check_status = format_research_check_status(last_checks)
    raise TimeoutError(
        f"Timed out waiting for PR #{pr_number} to merge ({check_status})"
    )


def run_agent(ticker: str, pick_reason: str) -> tuple[str, str]:
    env = os.environ.copy()
    env.setdefault("TICKER", ticker)
    env.setdefault("PICK_REASON", pick_reason)
    proc = run(["node", str(DEEP_DIVE_JS)], env=env, check=False)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"Marvin agent failed for {ticker} (exit {proc.returncode})")

    found = parse_pr_from_output(proc.stdout)
    if found:
        return found
    found = find_open_pr_for_ticker(ticker)
    if found:
        return found
    raise RuntimeError(f"No PR found for {ticker} after agent run")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequential Marvin batch drain")
    parser.add_argument("--tickers-json", help="JSON array of tickers (default: stdin or env TICKERS_JSON)")
    parser.add_argument("--pick-reason", default="batch_onboard_pending")
    parser.add_argument("--start-at", type=int, default=0, help="Skip first N tickers (resume)")
    parser.add_argument("--max-count", type=int, default=0, help="Stop after N tickers (0 = all)")
    args = parser.parse_args()

    raw = args.tickers_json or os.environ.get("TICKERS_JSON", "")
    if not raw:
        raw = sys.stdin.read()
    tickers: list[str] = json.loads(raw)
    if args.start_at:
        tickers = tickers[args.start_at :]
    if args.max_count:
        tickers = tickers[: args.max_count]

    if not tickers:
        print("No tickers to process.")
        return

    print(f"Sequential drain: {len(tickers)} tickers")
    drain_open_cursor_prs()
    failures: list[str] = []

    for i, ticker in enumerate(tickers, 1):
        print(f"\n=== [{i}/{len(tickers)}] {ticker} ===")
        try:
            _url, pr_number = run_agent(ticker, args.pick_reason)
            print(f"Agent PR: #{pr_number}")
            ensure_pr_ready(pr_number)
            wait_for_pr_merged(pr_number)
        except Exception as exc:
            print(f"::error::{ticker} failed: {exc}", file=sys.stderr)
            failures.append(ticker)

    if failures:
        print(f"\nFailed ({len(failures)}): {', '.join(failures)}", file=sys.stderr)
        raise SystemExit(1)
    print(f"\nDone - {len(tickers)} tickers merged.")


if __name__ == "__main__":
    main()
