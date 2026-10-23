#!/usr/bin/env python3
"""Hold a desk-bot pull request unless it touches only allowlisted data paths.

Grok desk bots open pull requests on ``grok/<desk>/<yyyy-mm-dd>-<slug>``
branches. They may write data (briefs, register rows, ledger rows, notes),
never code or human-gated files. This guard reads the list of changed paths
and exits non-zero when any path falls outside ``GROK_DATA_ALLOWLIST``. The
automerge workflow runs it before the data gate; ``docs/WRITE_MAP.md`` is the
prose copy of the same list and a test keeps the two in step.

Usage::

    python _system/scripts/check_contributor_paths.py --head-ref grok/special_situations/2026-10-12-mdt --files changed.txt
"""
from __future__ import annotations

import argparse
import fnmatch
import re
from pathlib import Path

GROK_BRANCH_RE = re.compile(r"^grok/[a-z0-9_]+/\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")

# Path globs a grok/ branch may touch. Keep in step with docs/WRITE_MAP.md.
GROK_DATA_ALLOWLIST: tuple[str, ...] = (
    "_system/data/desk_briefs/*/????-??-??.json",
    # Rebuilt by build_desk_briefs.py in the same commit as a new brief.
    # The Inbox reads this file; the brief directory alone leaves it stale.
    "dashboard/data/desk_briefs.json",
    "_system/memory-hub/research-equity/daily/????-??-??.md",
    "_system/memory-hub/research-equity/CONTEXT.md",
    "_system/data/separations/separation_registry.jsonl",
    "_system/data/separations/separation_amendments.jsonl",
    "_system/research/short-alpha/candidates.json",
    "_system/reference/activist-reports/short_scorecard/*",
    "*/third-party-analyses/vic/*.md",
    "_system/reviews/pending/*.md",
    "_system/memory/daily/????-??-??.md",
)

# Never writable by a bot, whatever the allowlist says.
HUMAN_GATED: tuple[str, ...] = (
    "_system/memory/MEMORY.md",
    "_system/reviews/approved/*",
    "*/research/human_decision.json",
    ".github/*",
    "_system/scripts/*",
    "_system/frameworks/*",
    "_system/graph/*",
    "CLAUDE.md",
    "CONTRIBUTING.md",
)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    norm = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(norm, pattern):
            return True
        # fnmatch's * crosses slashes; re-check that a single-segment wildcard
        # pattern did not match a deeper path by accident.
    return False


def _single_segment_ok(path: str, pattern: str) -> bool:
    """True when ``*`` in ``pattern`` matched within one path segment only."""
    norm = path.replace("\\", "/")
    if not fnmatch.fnmatch(norm, pattern):
        return False
    if pattern.startswith("*/"):
        # "*/third-party-analyses/vic/*.md": leading * is the ticker folder.
        return norm.count("/") == pattern.count("/")
    return norm.count("/") == pattern.count("/")


def is_allowlisted(path: str) -> bool:
    norm = path.replace("\\", "/")
    if any(fnmatch.fnmatch(norm, p) for p in HUMAN_GATED):
        return False
    return any(_single_segment_ok(norm, p) for p in GROK_DATA_ALLOWLIST)


def classify_branch(head_ref: str) -> str:
    """``grok`` for a well-formed desk-bot branch, ``other`` otherwise."""
    return "grok" if GROK_BRANCH_RE.match(head_ref or "") else "other"


def check(head_ref: str, files: list[str]) -> tuple[bool, list[str]]:
    """Return (ok, offending paths). Non-grok branches always pass this guard."""
    if classify_branch(head_ref) != "grok":
        return True, []
    offending = [f for f in files if not is_allowlisted(f)]
    return not offending, offending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--files", type=Path, required=True, help="newline-separated changed paths")
    args = parser.parse_args(argv)
    files = [line.strip() for line in args.files.read_text(encoding="utf-8").splitlines() if line.strip()]
    ok, offending = check(args.head_ref, files)
    if classify_branch(args.head_ref) != "grok":
        print(f"{args.head_ref}: not a grok/ branch; path guard does not apply")
        return 0
    if ok:
        print(f"{args.head_ref}: {len(files)} path(s), all on the bot data allowlist")
        return 0
    print(f"{args.head_ref}: {len(offending)} path(s) outside the bot data allowlist; a human must review:")
    for path in offending:
        print(f"  {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
