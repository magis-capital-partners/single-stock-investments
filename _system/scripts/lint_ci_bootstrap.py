#!/usr/bin/env python3
"""Lint GitHub workflow bootstrap checkout blocks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REQUIRED = frozenset(
    {
        "_system/scripts/ci_checkout_workspace.sh",
        "_system/scripts/ci_resolve_checkout_ref.sh",
        "_system/scripts/ci_sparse_checkout_paths.py",
    }
)
SPARSE_BLOCK_RE = re.compile(
    r"sparse-checkout:\s*\|\s*\n((?:\s+.+\n)+)",
    re.MULTILINE,
)


def lint_workflow(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if "ci_checkout_workspace.sh" not in text:
        return []
    errors: list[str] = []
    for match in SPARSE_BLOCK_RE.finditer(text):
        block = match.group(1)
        if "ci_checkout_workspace.sh" not in block:
            continue
        paths = {line.strip() for line in block.splitlines() if line.strip()}
        missing = REQUIRED - paths
        if missing:
            errors.append(
                f"{path.relative_to(ROOT)}: bootstrap sparse-checkout missing "
                + ", ".join(sorted(missing))
            )
    if "ci_checkout_workspace.sh" in text and not SPARSE_BLOCK_RE.search(text):
        errors.append(f"{path.relative_to(ROOT)}: uses ci_checkout_workspace.sh without sparse-checkout block")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        errors.extend(lint_workflow(path))
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print(f"OK: bootstrap sparse-checkout lint passed ({len(list(WORKFLOWS.glob('*.yml')))} workflows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
