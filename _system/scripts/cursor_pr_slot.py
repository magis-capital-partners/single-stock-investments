#!/usr/bin/env python3
"""One open Cursor pull request per ticker.

A later cloud-agent run for the same ticker continues the open branch. Dirty,
draft, and unknown merge states still count. Those were the duplicates that
moved main under the automerge queue.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any


def ticker_from_title(title: str) -> str | None:
    match = re.match(r"^([A-Z][A-Z0-9.]*)(?:[:\s]|$)", title or "")
    return match.group(1) if match else None


def pr_matches_ticker(pr: dict[str, Any], ticker: str) -> bool:
    ticker = ticker.upper()
    head = str(pr.get("headRefName") or "")
    if not head.startswith("cursor/"):
        return False
    if ticker_from_title(str(pr.get("title") or "")) == ticker:
        return True
    slug = head.split("/", 1)[1].upper()
    return slug == ticker or slug.startswith(ticker + "-")


def open_prs_for_ticker(prs: list[dict[str, Any]], ticker: str) -> list[dict[str, Any]]:
    return [pr for pr in prs if pr_matches_ticker(pr, ticker)]


def cursor_pr_count(prs: list[dict[str, Any]]) -> int:
    return sum(1 for pr in prs if str(pr.get("headRefName") or "").startswith("cursor/"))


def duplicates_of(prs: list[dict[str, Any]], ticker: str, keep_number: int) -> list[dict[str, Any]]:
    return [pr for pr in open_prs_for_ticker(prs, ticker) if int(pr.get("number") or 0) != int(keep_number)]


def _load_prs(path: str) -> list[dict[str, Any]]:
    data = json.loads(open(path, encoding="utf-8").read())
    if not isinstance(data, list):
        raise SystemExit("PR list JSON must be an array")
    return data


def _gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], text=True, capture_output=True, check=False)


def fold_duplicates(repo: str, ticker: str, keep_number: int, keep_branch: str, prs: list[dict[str, Any]]) -> list[int]:
    """Merge other open Cursor PRs for this ticker into ``keep_branch`` and close them.

    A fast-forward or clean merge updates the existing pull request. A conflict
    leaves the duplicate open so automerge can see it.
    """
    closed: list[int] = []
    for pr in duplicates_of(prs, ticker, keep_number):
        number = int(pr["number"])
        head = str(pr.get("headRefName") or "")
        if not head:
            continue
        merged = _gh([
            "api", "--method", "POST", f"repos/{repo}/merges",
            "-f", f"base={keep_branch}",
            "-f", f"head={head}",
            "-f", f"commit_message=fold {head} into {keep_branch}",
        ])
        if merged.returncode != 0:
            print(f"Left PR #{number} open; folding into {keep_branch} failed.", file=sys.stderr)
            print(merged.stderr or merged.stdout, file=sys.stderr)
            continue
        closed_pr = _gh([
            "pr", "close", str(number), "--repo", repo,
            "--comment",
            f"Folded into #{keep_number} so {ticker} keeps one open pull request.",
        ])
        if closed_pr.returncode != 0:
            print(closed_pr.stderr or closed_pr.stdout, file=sys.stderr)
            continue
        closed.append(number)
        print(f"Folded PR #{number} into #{keep_number}.")
    return closed


def main() -> None:
    parser = argparse.ArgumentParser(description="One open Cursor PR per ticker")
    sub = parser.add_subparsers(dest="command", required=True)

    count = sub.add_parser("count")
    count.add_argument("prs_json")

    match = sub.add_parser("match")
    match.add_argument("ticker")
    match.add_argument("prs_json")

    fold = sub.add_parser("fold")
    fold.add_argument("--repo", required=True)
    fold.add_argument("--ticker", required=True)
    fold.add_argument("--keep", required=True, type=int)
    fold.add_argument("--keep-branch", required=True)

    args = parser.parse_args()
    if args.command == "count":
        print(cursor_pr_count(_load_prs(args.prs_json)))
        return
    if args.command == "match":
        matches = open_prs_for_ticker(_load_prs(args.prs_json), args.ticker)
        if not matches:
            return
        chosen = matches[0]
        print(f"{chosen.get('number')}\t{chosen.get('headRefName')}")
        return
    listed = _gh([
        "pr", "list", "--repo", args.repo, "--state", "open", "--limit", "100",
        "--json", "number,headRefName,title",
    ])
    if listed.returncode != 0:
        raise SystemExit(listed.stderr or listed.stdout or "gh pr list failed")
    prs = json.loads(listed.stdout or "[]")
    fold_duplicates(args.repo, args.ticker, args.keep, args.keep_branch, prs)


if __name__ == "__main__":
    main()
