#!/usr/bin/env python3
"""Post or update automerge's single marker comment on a PR.

The comment is where a stalled automerge shows on the PR itself, so every
outcome that leaves a PR unmerged writes it: a failed gate, a failed merge, a
conflict resolution whose new head needs CI re-triggered, checks still
pending. One comment per PR, updated in place, never stacked.

It never comments on a PR that is no longer open. A pull_request run and a
workflow_run run fire for the same head, and the one that merges can finish
while the other is deciding; "blocked" on a merged PR is noise (it happened on
#1013, #1018 and #1020).

Usage:
  python _system/scripts/automerge_comment.py --repo OWNER/NAME --pr N \\
      --headline "Automerge is blocked" --message "why" [--run-url URL]
"""
from __future__ import annotations

import argparse
import subprocess
from typing import Callable

MARKER = "<!-- automerge-blocked -->"


def _gh(args: list[str]) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"gh {' '.join(args)} failed").strip())
    return proc.stdout


def render(headline: str, message: str, run_url: str = "") -> str:
    lines = [MARKER, f"**{headline}**: {message}"]
    if run_url:
        lines += ["", f"[Automerge run]({run_url})."]
    return "\n".join(lines) + "\n"


def upsert(repo: str, pr: str, body: str, *, gh: Callable[[list[str]], str] = _gh) -> str:
    """Write the marker comment; return "skipped", "updated" or "created"."""
    state = gh(["pr", "view", pr, "--repo", repo, "--json", "state", "-q", ".state"]).strip()
    if state != "OPEN":
        print(f"PR #{pr} is {state or 'unknown'}; not commenting.")
        return "skipped"
    found = gh([
        "api", f"repos/{repo}/issues/{pr}/comments", "--paginate",
        "--jq", f'[.[] | select(.body | startswith("{MARKER}"))][0].id // empty',
    ])
    existing = next((line.strip() for line in found.splitlines() if line.strip()), "")
    if existing:
        gh(["api", "--method", "PATCH", f"repos/{repo}/issues/comments/{existing}", "-f", f"body={body}"])
        print(f"Updated the automerge comment on PR #{pr}.")
        return "updated"
    gh(["api", "--method", "POST", f"repos/{repo}/issues/{pr}/comments", "-f", f"body={body}"])
    print(f"Posted the automerge comment on PR #{pr}.")
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--headline", default="Automerge is blocked")
    parser.add_argument("--message", required=True)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args(argv)
    upsert(args.repo, args.pr, render(args.headline, args.message, args.run_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
