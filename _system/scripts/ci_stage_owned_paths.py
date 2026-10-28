#!/usr/bin/env python3
"""Stage pathspecs without force-adding files outside a sparse checkout.

`git add --sparse -A` records deletions of tracked files the checkout never
materialized, and it adds new blobs that are outside the sparse patterns.
LS-algo intake did both to BN/investor-documents/ir-bn/bn-ir-day-presentation-2026.pdf.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True)


def _sparse(repo: Path) -> bool:
    shown = _git(repo, "config", "--get", "core.sparseCheckout", check=False)
    return shown.returncode == 0 and shown.stdout.strip() == b"true"


def _patterns(repo: Path) -> list[str]:
    shown = _git(repo, "sparse-checkout", "list", check=False)
    patterns = []
    for line in shown.stdout.decode("utf-8", errors="replace").splitlines():
        pattern = line.strip().strip("/")
        if pattern:
            patterns.append(pattern)
    return patterns


def _in_sparse(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if path == pattern or path.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def _skip_worktree(repo: Path) -> set[str]:
    shown = _git(repo, "ls-files", "-v", "-z")
    found = set()
    for record in shown.stdout.split(b"\0"):
        if record.startswith(b"S ") or record.startswith(b"S"):
            # "S <path>" or "S<path>" depending on git version. The flag is the first character.
            text = record.decode("utf-8", errors="surrogateescape")
            if text.startswith("S "):
                found.add(text[2:])
            elif text.startswith("S"):
                found.add(text[1:].lstrip())
    return found


def stage_owned(repo: Path, pathspecs: list[str]) -> list[str]:
    """Stage pathspecs. Return paths that were left unstaged because they are outside the sparse checkout."""
    if not pathspecs:
        return []
    skipped = _skip_worktree(repo) if _sparse(repo) else set()
    patterns = _patterns(repo) if _sparse(repo) else None
    _git(repo, "add", "--sparse", "-A", "--", *pathspecs)
    refused: list[str] = []
    if patterns is None:
        return refused
    deleted = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=D", "-z").stdout.split(b"\0")
    added = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=A", "-z").stdout.split(b"\0")
    unstage = []
    for raw in deleted:
        if not raw:
            continue
        path = raw.decode("utf-8", errors="surrogateescape")
        if path in skipped:
            unstage.append(path)
    for raw in added:
        if not raw:
            continue
        path = raw.decode("utf-8", errors="surrogateescape")
        if not _in_sparse(path, patterns):
            unstage.append(path)
    if unstage:
        _git(repo, "restore", "--staged", "--", *unstage)
        refused.extend(unstage)
    return refused


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: ci_stage_owned_paths.py <pathspec>...", file=sys.stderr)
        return 2
    refused = stage_owned(Path.cwd(), argv[1:])
    for path in refused:
        print(f"left unstaged outside sparse checkout: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
