#!/usr/bin/env python3
"""Fail if public holdings files carry letter provenance or a licensed export.

Scoped to the manager registry and the generated 13F dashboard files. Older
research notes elsewhere in the repo are not this check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from thirteenf_core import (  # noqa: E402
    FORBIDDEN_MANAGER_KEYS,
    licensed_path,
    manager_confidentiality_issues,
)

SCAN_FILES = (
    "_system/reference/market-data/ownership/managers.json",
    "dashboard/data/fund_holdings_summary.json",
)
SCAN_DIRS = (
    "_system/reference/market-data/ownership/13f",
    "dashboard/data/holdings",
)
BANNED_NAME = (
    "manager_13f_match",
    "tikr",
    "whalewisdom",
    "dataroma",
    "hedgefollow",
)


def _json_issues(path: Path, payload) -> list[str]:
    issues = []
    if path.name == "managers.json" and isinstance(payload, dict):
        issues.extend(manager_confidentiality_issues(payload))
    blob = json.dumps(payload)
    for key in FORBIDDEN_MANAGER_KEYS:
        if f'"{key}"' in blob:
            issues.append(f"{path}: contains forbidden field {key}")
    return issues


def scan(root: Path) -> list[str]:
    issues: list[str] = []
    files: list[Path] = []
    for relative in SCAN_FILES:
        path = root / relative
        if path.exists():
            files.append(path)
    for relative in SCAN_DIRS:
        folder = root / relative
        if folder.exists():
            files.extend(path for path in folder.rglob("*") if path.is_file())
    for path in files:
        relative = str(path.relative_to(root))
        if licensed_path(relative) or any(token in path.name.lower() for token in BANNED_NAME):
            issues.append(f"{relative}: licensed or working-match filename")
        if path.suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                issues.append(f"{relative}: not valid json")
                continue
            issues.extend(_json_issues(path, payload))
    return issues


def main() -> int:
    issues = scan(ROOT)
    if issues:
        print("\n".join(issues))
        return 1
    print("holdings confidentiality ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
