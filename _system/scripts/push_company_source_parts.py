"""Push immutable source archive parts in bounded commits before its manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


def batches(paths, limit=200_000_000):
    group, size = [], 0
    for path in paths:
        length = path.stat().st_size
        if length > limit:
            raise ValueError("Archive part exceeds upload batch limit")
        if group and size + length > limit:
            yield group
            group, size = [], 0
        group.append(path)
        size += length
    if group:
        yield group


def publish(vault: Path, limit=200_000_000):
    vault = vault.resolve()
    relative = Path("dashboard-private/company-source-backfill-v2")
    archive = vault / relative
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    paths = []
    for part in manifest["parts"]:
        name = part["file"]
        if not re.fullmatch(r"[a-f0-9]{64}\.zip", name) or name != part["sha256"] + ".zip":
            raise ValueError("Invalid immutable archive part")
        path = archive / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != part["sha256"]:
            raise ValueError("Archive part checksum mismatch")
        paths.append(path)

    def git(root, *args):
        return subprocess.check_output(["git", "-C", str(root), "-c", "gc.auto=0", "-c", "maintenance.auto=false",
            "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            *args], stderr=subprocess.STDOUT).decode().strip()

    git(vault, "fetch", "origin", "main")
    remote_files = set(git(vault, "ls-tree", "--name-only", "origin/main:" + relative.as_posix()).splitlines())
    paths = [path for path in paths if path.name not in remote_files]
    if not paths:
        return {"parts_uploaded": 0, "batches": 0}
    uploaded = count = 0
    # A separate checkout leaves the caller's uncommitted manifest untouched.
    with tempfile.TemporaryDirectory(prefix="company-source-parts-") as temporary:
        worktree = Path(temporary) / "checkout"
        git(vault, "worktree", "add", "--detach", "--no-checkout", str(worktree), "origin/main")
        try:
            git(worktree, "sparse-checkout", "set", "--no-cone", "/" + relative.as_posix() + "/manifest.json")
            # --no-checkout starts with an empty index. Populate it before
            # staging parts so existing repository files cannot become deletes.
            git(worktree, "reset", "--hard", "HEAD")
            for group in batches(paths, limit):
                names = []
                for source in group:
                    target = worktree / relative / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        try:
                            os.link(source, target)
                        except OSError:
                            shutil.copy2(source, target)
                    names.append((relative / source.name).as_posix())
                git(worktree, "add", "--sparse", "--", *names)
                staged = set(git(worktree, "diff", "--cached", "--name-only").splitlines())
                if staged != set(names):
                    raise RuntimeError("Archive upload staged files outside its immutable parts")
                git(worktree, "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                    "commit", "-m", "Preserve immutable company-source archive parts")
                for attempt in range(3):
                    git(worktree, "fetch", "origin", "main")
                    git(worktree, "rebase", "origin/main")
                    try:
                        git(worktree, "push", "origin", "HEAD:main")
                        break
                    except subprocess.CalledProcessError:
                        if attempt == 2:
                            raise
                        time.sleep(2 ** attempt)
                uploaded += len(group)
                count += 1
                print(f"Preserved archive parts: {uploaded}/{len(paths)}", flush=True)
        finally:
            if not worktree.resolve().is_relative_to(Path(temporary).resolve()):
                raise RuntimeError("Temporary publisher checkout escaped its owned directory")
            git(vault, "worktree", "remove", "--force", str(worktree))
    return {"parts_uploaded": uploaded, "batches": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--max-bytes", type=int, default=200_000_000)
    args = parser.parse_args()
    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive")
    print(publish(args.vault, args.max_bytes))
