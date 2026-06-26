#!/usr/bin/env python3
"""Copy dashboard/ to docs/ for GitHub Pages branch deploy (/docs)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "dashboard"
DEST = ROOT / "docs"
SKIP_DIR_NAMES = {".wrangler", "__pycache__", ".git"}
SKIP_FILE_NAMES = {".DS_Store"}


def sync() -> None:
    if not SRC.is_dir():
        print(f"Missing source folder: {SRC}", file=sys.stderr)
        sys.exit(1)

    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True, exist_ok=True)

    copied = 0
    for item in SRC.rglob("*"):
        rel = item.relative_to(SRC)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        if item.name in SKIP_FILE_NAMES:
            continue

        target = DEST / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1

    (DEST / ".nojekyll").touch()
    print(f"Synced {copied} files from dashboard/ to docs/ (+ .nojekyll)")


if __name__ == "__main__":
    sync()
