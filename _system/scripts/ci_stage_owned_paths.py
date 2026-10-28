#!/usr/bin/env python3
"""Stage pathspecs without force-adding files outside a sparse checkout.

`git add --sparse -A` records deletions of tracked files the checkout never
materialized, and it adds new blobs that are outside the sparse patterns.
LS-algo intake did both to BN/investor-documents/ir-bn/bn-ir-day-presentation-2026.pdf.

Do not discover those paths with `git status`. On the marvin-pick checkout
that command re-matches every index path against every non-cone sparse
pattern (about 177,000 files by 6,000 patterns). Run 40704555082 printed
"Vault pushed (attempt 1)." and was still inside that `git status` 79
minutes later, when the 90-minute job timeout cancelled the step. `git
diff` trusts the skip-worktree bit already stored in the index, so files
the checkout never materialized are not reported as deletions. Untracked
paths are listed with sparse matching turned off for that one read-only
command, then accepted or refused from the pattern list.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

# diff and ls-files on this checkout finish in seconds. A hang must fail
# here, with the command named, instead of waiting out the job timeout.
GIT_COMMAND_TIMEOUT = 180


def _log(message: str) -> None:
    print(message, flush=True)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.Popen(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=GIT_COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        stdout, stderr = proc.communicate()
        preview = " ".join(args[:8])
        _log(f"::error::git timed out after {GIT_COMMAND_TIMEOUT}s: {preview}")
        raise subprocess.TimeoutExpired(
            proc.args, GIT_COMMAND_TIMEOUT, output=stdout, stderr=stderr,
        ) from None
    result = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
    if check and result.returncode != 0:
        sys.stderr.buffer.write(stderr)
        raise subprocess.CalledProcessError(result.returncode, result.args, stdout, stderr)
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


def _pattern_matcher(patterns: list[str]):
    """Prefix membership without comparing every path to every pattern."""
    known = {pattern.strip().strip("/") for pattern in patterns if pattern.strip().strip("/")}

    def contains(path: str) -> bool:
        path = path.strip().strip("/")
        while path:
            if path in known:
                return True
            slash = path.rfind("/")
            if slash < 0:
                return False
            path = path[:slash]
        return False

    return contains


def _in_sparse(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if path == pattern or path.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def _parse_name_status(blob: bytes) -> list[tuple[str, str]]:
    """Parse `git diff -z --name-status` (status NUL path, or rename NUL old NUL new)."""
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    found: list[tuple[str, str]] = []
    index = 0
    while index < len(parts):
        status = parts[index].decode("ascii", errors="replace")
        index += 1
        if index >= len(parts):
            break
        path = parts[index].decode("utf-8", errors="surrogateescape")
        index += 1
        if status[:1] in {"R", "C"}:
            renamed = parts[index].decode("utf-8", errors="surrogateescape") if index < len(parts) else path
            index += 1
            found.append(("D ", path))
            found.append(("A ", renamed))
            continue
        found.append((status, path))
    return found


def _tracked(repo: Path, pathspecs: list[str]) -> list[tuple[str, str]]:
    _log("stage: diff of tracked paths")
    shown = _git(repo, "diff", "-z", "--name-status", "--", *pathspecs)
    found = _parse_name_status(shown.stdout)
    _log(f"stage: tracked changes={len(found)}")
    return found


def _untracked(repo: Path, pathspecs: list[str]) -> list[tuple[str, str]]:
    # Read-only. Sparse matching stays on for every other git command.
    # Turning it off here avoids the non-cone pattern walk; membership is
    # decided from the pattern list after this listing returns.
    _log("stage: listing untracked paths")
    shown = _git(
        repo, "-c", "core.sparseCheckout=false",
        "ls-files", "--others", "--exclude-standard", "-z", "--", *pathspecs,
    )
    found = []
    for record in shown.stdout.split(b"\0"):
        if not record:
            continue
        found.append(("??", record.decode("utf-8", errors="surrogateescape")))
    _log(f"stage: untracked paths={len(found)}")
    return found


def _batches(paths: list[str]):
    for offset in range(0, len(paths), 80):
        yield paths[offset:offset + 80]


def _stage_batches(repo: Path, deletions: list[str], additions: list[str]) -> None:
    total = len(deletions) + len(additions)
    _log(f"stage: staging {total} paths")
    done = 0
    # -u records a deletion. It also skips untracked files, so new paths
    # are a separate git add.
    for batch in _batches(deletions):
        _git(repo, "add", "-u", "--", *batch)
        done += len(batch)
        _log(f"stage: staged {done}/{total}")
    for batch in _batches(additions):
        _git(repo, "add", "--", *batch)
        done += len(batch)
        _log(f"stage: staged {done}/{total}")
    if total == 0:
        _log("stage: staged 0/0")


def stage_owned(repo: Path, pathspecs: list[str]) -> list[str]:
    """Stage pathspecs that are in the checkout. Return paths left unstaged.

    Never calls ``git add --sparse -A`` or ``git status``.
    """
    if not pathspecs:
        _log("stage: no pathspecs")
        return []
    _log("stage: reading sparse checkout")
    sparse = _sparse(repo)
    patterns = _patterns(repo) if sparse else None
    contains = _pattern_matcher(patterns) if patterns is not None else None
    _log(f"stage: sparse={str(sparse).lower()} patterns={0 if patterns is None else len(patterns)}")
    refused: list[str] = []
    deletions: list[str] = []
    additions: list[str] = []
    for status, path in _tracked(repo, pathspecs) + _untracked(repo, pathspecs):
        outside = contains is not None and not contains(path)
        if outside:
            refused.append(path)
            continue
        if "D" in status:
            deletions.append(path)
        else:
            additions.append(path)
    _stage_batches(repo, deletions, additions)
    _log(f"stage: done staged={len(deletions) + len(additions)} refused={len(refused)}")
    return refused


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: ci_stage_owned_paths.py <pathspec>...", file=sys.stderr)
        return 2
    _log(f"stage: start pathspecs={len(argv) - 1}")
    refused = stage_owned(Path.cwd(), argv[1:])
    for path in refused:
        _log(f"left unstaged outside sparse checkout: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
