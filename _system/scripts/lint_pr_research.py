#!/usr/bin/env python3
"""Lint deep dives for tickers touched in a PR diff.

Usage:
  python _system/scripts/lint_pr_research.py
  python _system/scripts/lint_pr_research.py --base origin/main
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable
TICKER_RE = re.compile(r"^([^/]+)/research/")

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import has_evidence_refresh_config  # noqa: E402


def tickers_from_diff(base: str) -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        r = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    tickers: set[str] = set()
    for line in (r.stdout or "").splitlines():
        line = line.strip().replace("\\", "/")
        if "/research/" not in line:
            continue
        m = TICKER_RE.match(line)
        if m and not m.group(1).startswith(("_", ".")):
            tickers.add(m.group(1))
    return sorted(tickers)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main", help="Git base ref for diff")
    args = parser.parse_args()

    tickers = tickers_from_diff(args.base)
    if not tickers:
        print("SKIP: no ticker research paths in diff")
        return 0

    failed = 0
    for ticker in tickers:
        dive = ROOT / ticker / "research"
        if not dive.is_dir():
            continue
        if not list(dive.glob("deep_dive_*.md")):
            print(f"SKIP {ticker}: no deep dive")
            continue
        print(f"\n=== lint {ticker} ===")
        for script, extra in (
            ("lint_deep_dive.py", ["--milly"]),
            ("lint_adversarial.py", ["--consistency-only"]),
        ):
            cmd = [PY, str(SCRIPTS / script), ticker, *extra]
            r = subprocess.run(cmd, cwd=ROOT)
            if r.returncode != 0:
                failed += 1
        val_path = ROOT / ticker / "research" / "valuation.json"
        if val_path.exists():
            try:
                val = json.loads(val_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                val = {}
            if has_evidence_refresh_config(val) or val.get("valuation_mode") == "optionality":
                r = subprocess.run(
                    [PY, str(SCRIPTS / "check_evidence_completeness.py"), ticker],
                    cwd=ROOT,
                )
                if r.returncode != 0:
                    failed += 1

    if failed:
        print(f"\nFAIL: {failed} lint invocation(s)")
        return 1
    print(f"\nOK: {len(tickers)} ticker(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
