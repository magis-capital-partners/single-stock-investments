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
    result = subprocess.run(["git", "-C", str(repo), *args], check=False, capture_output=True)
    if check and result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    return result


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


def _changed(repo: Path, pathspecs: list[str]) -> list[tuple[str, str]]:
    shown = _git(repo, "status", "--porcelain=v1", "-z", "-uall", "--", *pathspecs)
    parts = shown.stdout.split(b"\0")
    found: list[tuple[str, str]] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if len(record) < 4:
            continue
        status = record[:2].decode("ascii", errors="replace")
        path = record[3:].decode("utf-8", errors="surrogateescape")
        if "R" in status or "C" in status:
            renamed = parts[index].decode("utf-8", errors="surrogateescape") if index < len(parts) else path
            index += 1
            found.append(("D ", path))
            found.append(("A ", renamed))
            continue
        found.append((status, path))
    return found


def stage_owned(repo: Path, pathspecs: list[str]) -> list[str]:
    """Stage pathspecs that are in the checkout. Return paths left unstaged.

    Never calls ``git add --sparse -A``. That command tries to delete tracked
    files the sparse checkout did not materialize and exits 128 on
    ``not uptodate; will not remove from working tree``.
    """
    if not pathspecs:
        return []
    sparse = _sparse(repo)
    skipped = _skip_worktree(repo) if sparse else set()
    patterns = _patterns(repo) if sparse else None
    refused: list[str] = []
    for status, path in _changed(repo, pathspecs):
        outside = path in skipped or (patterns is not None and not _in_sparse(path, patterns))
        if outside:
            refused.append(path)
            continue
        if "D" in status:
            _git(repo, "add", "-u", "--", path)
        else:
            _git(repo, "add", "--", path)
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
