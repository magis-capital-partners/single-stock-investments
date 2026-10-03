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
JSONL = "_system/portfolio/research_events.jsonl"
MILLY = "_system/research/milly_log.md"
# Files that move on main all day and carry no research judgment. A conflict
# that is only these paths can be squashed without a second CI run: the gated
# SHA already passed, and -X theirs keeps main's copy.
GENERATED_EXACT = {JSONL, MILLY}
GENERATED_PREFIXES = (
    "dashboard/data/",
    "_system/reference/market-data/",
    "_system/memory/daily/",
)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )
    return proc


class HeadMoved(Exception):
    """The PR branch is no longer at the SHA the resolution was built on."""


def push_branch(head_ref: str, expected_sha: str) -> None:
    """Push HEAD to the PR branch only while the branch is still at ``expected_sha``.

    The lease is pinned to the SHA the merge was built on (in automerge, the
    SHA the gate saw). The old fallback fetched the branch and pushed with a
    bare --force-with-lease, whose expected value is the tip it had just
    fetched: an agent commit pushed while the resolver ran was overwritten.
    """
    push = run(
        ["git", "push", f"--force-with-lease=refs/heads/{head_ref}:{expected_sha}",
         "origin", f"HEAD:refs/heads/{head_ref}"],
        check=False,
    )
    if push.returncode == 0:
        return
    combined = (push.stderr or "") + (push.stdout or "")
    if "stale info" in combined or "non-fast-forward" in combined or "fetch first" in combined:
        raise HeadMoved(
            f"{head_ref} moved away from {expected_sha[:12]} while its conflicts were being "
            "resolved; not overwriting it."
        )
    raise subprocess.CalledProcessError(push.returncode, push.args, push.stdout, push.stderr)


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
    daily = ROOT / "_system" / "memory" / "daily"
    if not daily.is_dir():
        return None
    logs = sorted(daily.glob("*.md"), reverse=True)
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


def is_shallow() -> bool:
    proc = run(["git", "rev-parse", "--is-shallow-repository"], check=False)
    return proc.stdout.strip() == "true"


def local_commit_count() -> int:
    proc = run(["git", "rev-list", "--count", "--all"], check=False)
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def merge_base(left: str, right: str) -> str | None:
    proc = run(["git", "merge-base", left, right], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def fetch_with_merge_base(head_ref: str, *, start_depth: int = 64, max_depth: int = 4096) -> str:
    """Fetch main and the PR branch with enough history to share a merge-base.

    A shallow checkout (``actions/checkout`` with ``fetch-depth: 1``) truncates
    origin/main at the checked-out tip. A PR forked before that tip then shares
    no local ancestor with it, and ``git merge`` stops with "refusing to merge
    unrelated histories" (automerge run 35944388953, PR #1014). A plain fetch
    of the branch into that clone is also the expensive kind: git walks the
    branch all the way to the root commit.

    So in a nearly empty shallow clone -- the merge job's depth-1 checkout --
    both refs are fetched to a bounded depth and deepened until the fork point
    is local, with ``--unshallow`` as the last resort. ``--depth`` can also
    SHORTEN history, so it is used only while the whole local history is
    shorter than ``start_depth`` (nothing there to shorten); any other clone,
    such as a long-lived workstation checkout, gets a plain fetch. Returns the
    merge-base; exits if there is none.
    """
    refspecs = [
        "+refs/heads/main:refs/remotes/origin/main",
        f"+refs/heads/{head_ref}:refs/remotes/origin/{head_ref}",
    ]
    branch_ref = f"origin/{head_ref}"
    if not is_shallow() or local_commit_count() > start_depth:
        run(["git", "fetch", "origin", *refspecs])
    else:
        depth = start_depth
        run(["git", "fetch", f"--depth={depth}", "origin", *refspecs])
        while merge_base("origin/main", branch_ref) is None and is_shallow():
            if depth >= max_depth:
                run(["git", "fetch", "--unshallow", "origin", *refspecs])
                break
            run(["git", "fetch", f"--deepen={depth}", "origin", *refspecs])
            depth *= 2
    base = merge_base("origin/main", branch_ref)
    if base is None:
        raise SystemExit(f"No merge-base between origin/main and {branch_ref}, even with full history.")
    return base


def unmerged_paths() -> list[str]:
    proc = run(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_generated_path(path: str) -> bool:
    path = path.replace("\\", "/").lstrip("./")
    if path in GENERATED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in GENERATED_PREFIXES)


def conflicted_paths(branch_ref: str) -> list[str]:
    """Paths that conflict between the PR tip and origin/main.

    ``git merge-tree --write-tree`` exits 0 when the merge is clean and 1 when
    it conflicts. ``--name-only`` prints the conflicted paths. A 40-hex line is
    a tree id, not a path.
    """
    proc = run(
        ["git", "merge-tree", "--write-tree", "--name-only", branch_ref, "origin/main"],
        check=False,
    )
    if proc.returncode not in (0, 1):
        detail = (proc.stderr or proc.stdout or "merge-tree failed").strip()
        raise SystemExit(detail)
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip().replace("\\", "/")
        if not line or re.fullmatch(r"[0-9a-f]{40}", line):
            continue
        if line.startswith("Auto-merging ") or line.startswith("CONFLICT "):
            continue
        paths.append(line)
    return paths


def conflicts_are_generated(paths: list[str]) -> bool:
    return bool(paths) and all(is_generated_path(path) for path in paths)


def resolve(
    pr_number: str,
    ticker: str | None = None,
    expected_sha: str | None = None,
    info: dict | None = None,
) -> str | None:
    """Merge main into the PR branch and push it.

    Returns the pushed head SHA, or None when there was nothing to push.
    ``info["generated_only"]`` is true when every conflicted path is generated.
    The workflow may squash that push in the same run, because the research
    tree is unchanged and the gated SHA's checks still apply. Any other push
    has never been through CI (PRs #1017 and #1021 were squashed seconds after
    the push, with zero check runs on the merged head) and must wait.

    ``expected_sha`` is the head the caller vetted (automerge passes the gated
    SHA). The resolution is built only on that head and pushed only while the
    branch is still there; otherwise HeadMoved is raised and nothing is pushed.
    """
    ticker = ticker or infer_ticker(pr_number)
    data = gh_json(["pr", "view", pr_number, "--json", "headRefName,mergeable"])
    head_ref = data["headRefName"]
    if info is not None:
        info["generated_only"] = False
    if data.get("mergeable") != "CONFLICTING":
        print(f"PR #{pr_number} mergeable={data.get('mergeable')} — nothing to resolve.")
        return None

    print(f"Resolving conflicts for PR #{pr_number} ({ticker}) on {head_ref}")

    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    fetch_with_merge_base(head_ref)

    branch_ref = f"origin/{head_ref}"
    original_tip = run(["git", "rev-parse", "--verify", branch_ref]).stdout.strip()
    if expected_sha and original_tip != expected_sha:
        raise HeadMoved(f"{head_ref} is at {original_tip[:12]}, not the vetted {expected_sha[:12]}.")
    daily_path = latest_daily_log()
    daily_rel = str(daily_path.relative_to(ROOT)).replace("\\", "/") if daily_path else None
    daily_section = None
    if daily_rel:
        daily_orig = git_show(branch_ref, daily_rel)
        if daily_orig:
            daily_section = extract_section(daily_orig, ticker)

    jsonl_lines = lines_for_ticker(git_show(branch_ref, JSONL) or "", ticker, kind="jsonl")
    milly_lines = lines_for_ticker(git_show(branch_ref, MILLY) or "", ticker, kind="milly")
    generated_only = conflicts_are_generated(conflicted_paths(branch_ref))
    if info is not None:
        info["generated_only"] = generated_only
    print(f"PR #{pr_number}: generated_only={str(generated_only).lower()}")

    run(["git", "checkout", "-B", f"conflict-fix-{pr_number}", branch_ref])
    merge = run(
        ["git", "merge", "origin/main", "-X", "theirs", "-m", f"merge main into {ticker} deep dive PR"],
        check=False,
    )
    in_merge = run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], check=False).returncode == 0
    if merge.returncode != 0 and not in_merge:
        print(merge.stderr or merge.stdout, file=sys.stderr)
        raise SystemExit(merge.returncode)
    # -X theirs settles content conflicts. A modify/delete or rename conflict is
    # left unmerged, and `git add -A` would quietly resurrect a file main
    # deleted. That needs a human, not a bot commit.
    stuck = unmerged_paths()
    if stuck:
        run(["git", "merge", "--abort"], check=False)
        raise SystemExit(
            f"PR #{pr_number}: conflicts -X theirs cannot settle; resolve by hand: " + ", ".join(stuck[:20])
        )

    restore_ticker_logs(ticker, daily_section=daily_section, jsonl_lines=jsonl_lines, milly_lines=milly_lines)

    run(["git", "add", "-A"])
    status = run(["git", "status", "--porcelain"], check=False)
    if status.stdout.strip():
        run(["git", "commit", "-m", f"fix: resolve {ticker} deep dive conflicts with main"])
    new_tip = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    if new_tip == original_tip:
        print(f"PR #{pr_number}: merging main changed nothing; nothing to push.")
        return None
    push_branch(head_ref, expected_sha or original_tip)
    print(f"Pushed conflict resolution for PR #{pr_number} ({ticker}) at {new_tip}")
    return new_tip


def write_github_output(
    path: str,
    pushed_sha: str | None,
    *,
    head_moved: bool = False,
    generated_only: bool = False,
) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"pushed={'true' if pushed_sha else 'false'}\n")
        handle.write(f"pushed_sha={pushed_sha or ''}\n")
        handle.write(f"head_moved={'true' if head_moved else 'false'}\n")
        handle.write(f"generated_only={'true' if generated_only else 'false'}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve Marvin deep-dive PR merge conflicts")
    parser.add_argument("pr_number", help="GitHub pull request number")
    parser.add_argument("--ticker", help="Ticker symbol (optional; inferred from PR title)")
    parser.add_argument(
        "--github-output",
        default="",
        help="Append pushed, pushed_sha and head_moved to this file (a step's $GITHUB_OUTPUT).",
    )
    parser.add_argument(
        "--expected-sha",
        default="",
        help="Only resolve and push while the PR branch is at this SHA (automerge passes the gated SHA).",
    )
    args = parser.parse_args()
    info: dict = {}
    try:
        pushed_sha = resolve(args.pr_number, args.ticker, args.expected_sha or None, info)
    except HeadMoved as moved:
        print(f"PR #{args.pr_number}: {moved} Its own run gates the new head.")
        if args.github_output:
            write_github_output(args.github_output, None, head_moved=True)
        return
    if args.github_output:
        write_github_output(
            args.github_output,
            pushed_sha,
            generated_only=bool(info.get("generated_only")),
        )


if __name__ == "__main__":
    main()
