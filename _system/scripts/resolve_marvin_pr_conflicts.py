#!/usr/bin/env python3
"""Merge main into a Marvin deep-dive PR branch and restore ticker log rows."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "_system" / "memory" / "daily"
JSONL = "_system/portfolio/research_events.jsonl"
MILLY = "_system/research/milly_log.md"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )
    return proc


def push_branch(head_ref: str) -> None:
    push = run(["git", "push", "origin", f"HEAD:{head_ref}"], check=False)
    if push.returncode == 0:
        return
    combined = (push.stderr or "") + (push.stdout or "")
    if "non-fast-forward" not in combined and "stale info" not in combined:
        raise subprocess.CalledProcessError(push.returncode, push.args, push.stdout, push.stderr)
    run(["git", "fetch", "origin", head_ref])
    run(["git", "push", "origin", f"HEAD:{head_ref}", "--force-with-lease"])


def gh_json(args: list[str]) -> dict:
    return json.loads(run(["gh", *args]).stdout)


def infer_ticker(pr_number: str) -> str:
    data = gh_json(["pr", "view", pr_number, "--json", "title,headRefName"])
    title = data.get("title") or ""
    m = re.match(r"^([A-Z0-9._-]+)", title)
    if m:
        return m.group(1)
    raise SystemExit(f"Cannot infer ticker from PR #{pr_number} title: {title!r}")


def latest_daily_log() -> Path | None:
    if not DAILY.is_dir():
        return None
    logs = sorted(DAILY.glob("*.md"), reverse=True)
    return logs[0] if logs else None


def git_show(ref: str, path: str) -> str | None:
    proc = run(["git", "show", f"{ref}:{path}"], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def extract_section(content: str, ticker: str) -> str | None:
    pattern = rf"(## {re.escape(ticker)} [^\n]+\n(?:.*?\n)*?)(?=## |\Z)"
    m = re.search(pattern, content, re.DOTALL)
    if not m:
        return None
    return m.group(1).rstrip() + "\n\n"


def lines_for_ticker(text: str, ticker: str, *, kind: str) -> list[str]:
    if not text:
        return []
    if kind == "jsonl":
        return [
            ln.strip()
            for ln in text.splitlines()
            if f'"ticker": "{ticker}"' in ln or f'"ticker":"{ticker}"' in ln
        ]
    return [ln.strip() for ln in text.splitlines() if f"| {ticker} |" in ln]


def restore_ticker_logs(
    ticker: str,
    *,
    daily_section: str | None,
    jsonl_lines: list[str],
    milly_lines: list[str],
) -> None:
    daily_path = latest_daily_log()
    if daily_path and daily_section:
        body = daily_path.read_text(encoding="utf-8")
        if f"## {ticker} " not in body:
            lines = body.splitlines(keepends=True)
            if lines:
                daily_path.write_text(
                    lines[0].rstrip() + "\n\n" + daily_section + "".join(lines[1:]),
                    encoding="utf-8",
                )
            else:
                daily_path.write_text(daily_section, encoding="utf-8")

    jsonl_path = ROOT / JSONL
    if jsonl_path.is_file() and jsonl_lines:
        body = jsonl_path.read_text(encoding="utf-8")
        missing = [ln for ln in jsonl_lines if ln not in body]
        if missing:
            jsonl_path.write_text(body.rstrip() + "\n" + "\n".join(missing) + "\n", encoding="utf-8")

    milly_path = ROOT / MILLY
    if milly_path.is_file() and milly_lines:
        body = milly_path.read_text(encoding="utf-8")
        missing = [ln for ln in milly_lines if ln not in body]
        if missing:
            milly_path.write_text(body.rstrip() + "\n" + "\n".join(missing) + "\n", encoding="utf-8")


def resolve(pr_number: str, ticker: str | None = None) -> None:
    ticker = ticker or infer_ticker(pr_number)
    data = gh_json(["pr", "view", pr_number, "--json", "headRefName,mergeable"])
    head_ref = data["headRefName"]
    if data.get("mergeable") != "CONFLICTING":
        print(f"PR #{pr_number} mergeable={data.get('mergeable')} — nothing to resolve.")
        return

    print(f"Resolving conflicts for PR #{pr_number} ({ticker}) on {head_ref}")

    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    # Fetch the PR head explicitly; sparse/local clones often lack origin/<branch> refs.
    run(["git", "fetch", "origin", "main", head_ref])
    run(["git", "fetch", "origin", f"+{head_ref}:refs/remotes/origin/{head_ref}"], check=False)

    branch_ref = f"origin/{head_ref}"
    tip = run(["git", "rev-parse", "--verify", branch_ref], check=False)
    if tip.returncode != 0:
        branch_ref = "FETCH_HEAD"
    daily_path = latest_daily_log()
    daily_rel = str(daily_path.relative_to(ROOT)).replace("\\", "/") if daily_path else None
    daily_section = None
    if daily_rel:
        daily_orig = git_show(branch_ref, daily_rel)
        if daily_orig:
            daily_section = extract_section(daily_orig, ticker)

    jsonl_lines = lines_for_ticker(git_show(branch_ref, JSONL) or "", ticker, kind="jsonl")
    milly_lines = lines_for_ticker(git_show(branch_ref, MILLY) or "", ticker, kind="milly")

    run(["git", "checkout", "-B", f"conflict-fix-{pr_number}", branch_ref])
    merge = run(
        ["git", "merge", "origin/main", "-X", "theirs", "-m", f"merge main into {ticker} deep dive PR"],
        check=False,
    )
    if merge.returncode != 0 and not (ROOT / ".git" / "MERGE_HEAD").exists():
        print(merge.stderr or merge.stdout, file=sys.stderr)
        raise SystemExit(merge.returncode)

    restore_ticker_logs(ticker, daily_section=daily_section, jsonl_lines=jsonl_lines, milly_lines=milly_lines)

    run(["git", "add", "-A"])
    status = run(["git", "status", "--porcelain"], check=False)
    if status.stdout.strip():
        run(["git", "commit", "-m", f"fix: resolve {ticker} deep dive conflicts with main"])
    push_branch(head_ref)
    print(f"Pushed conflict resolution for PR #{pr_number} ({ticker})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve Marvin deep-dive PR merge conflicts")
    parser.add_argument("pr_number", help="GitHub pull request number")
    parser.add_argument("--ticker", help="Ticker symbol (optional; inferred from PR title)")
    args = parser.parse_args()
    resolve(args.pr_number, args.ticker)


if __name__ == "__main__":
    main()
