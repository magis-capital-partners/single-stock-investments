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

MECHANICAL_EVIDENCE = re.compile(r"^[^/]+/research/evidence/thematic_context_\d{4}-\d{2}-\d{2}\.md$")
MECHANICAL_INSIDER = re.compile(r"^[^/]+/research/evidence/insider_signal_\d{4}-\d{2}-\d{2}\.md$")
MECHANICAL_MI = re.compile(r"^[^/]+/research/market_inputs\.json$")

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import has_evidence_refresh_config  # noqa: E402


def git_diff_names(base: str) -> list[str]:
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
    return [line.strip().replace("\\", "/") for line in (r.stdout or "").splitlines() if line.strip()]


def tickers_from_diff(base: str) -> list[str]:
    tickers: set[str] = set()
    for line in git_diff_names(base):
        if "/research/" not in line:
            continue
        m = TICKER_RE.match(line)
        if m and not m.group(1).startswith(("_", ".")):
            tickers.add(m.group(1))
    return sorted(tickers)


def valuation_overlay_only_diff(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r = subprocess.run(
        ["git", "show", f"{base}:{vp}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False
    try:
        old = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    new_path = ROOT / ticker / "research" / "valuation.json"
    if not new_path.exists():
        return False
    try:
        new = json.loads(new_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    forbidden = ("inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay")
    for key in forbidden:
        if old.get(key) != new.get(key):
            return False
    return old.get("context_overlay") != new.get("context_overlay")


def valuation_insider_only_diff(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r2 = subprocess.run(
        ["git", "show", f"{base}:{vp}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        return False
    try:
        old = json.loads(r2.stdout)
        new = json.loads((ROOT / ticker / "research" / "valuation.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    forbidden = ("inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay")
    for key in forbidden:
        if old.get(key) != new.get(key):
            return False
    return old.get("insider_signal") != new.get("insider_signal")


def research_diff_kind(ticker: str, paths: list[str], base: str) -> str:
    """Per ticker: mechanical_only | narrative | mixed."""
    tk_paths = [p for p in paths if p.startswith(f"{ticker}/research/")]
    if not tk_paths:
        return "narrative"
    non_mechanical = []
    for p in tk_paths:
        if p.endswith("/research/valuation.json"):
            if not (valuation_overlay_only_diff(ticker, base) or valuation_insider_only_diff(ticker, base)):
                non_mechanical.append(p)
            continue
        if MECHANICAL_EVIDENCE.match(p) or MECHANICAL_INSIDER.match(p) or MECHANICAL_MI.match(p):
            continue
        if "/research/evidence/filing_facts_" in p and p.endswith(".json"):
            continue
        non_mechanical.append(p)
    if not non_mechanical:
        return "mechanical_only"
    val_only = all(p.endswith("/research/valuation.json") for p in non_mechanical)
    if val_only and (valuation_overlay_only_diff(ticker, base) or valuation_insider_only_diff(ticker, base)):
        return "mechanical_only"
    if any(p.endswith(".md") for p in non_mechanical):
        return "mixed" if any(not p.endswith(".md") for p in non_mechanical) else "narrative"
    return "mixed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main", help="Git base ref for diff")
    args = parser.parse_args()

    paths = git_diff_names(args.base)
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
        kind = research_diff_kind(ticker, paths, args.base)
        print(f"\n=== lint {ticker} ({kind}) ===")
        if kind == "mechanical_only":
            val_path = ROOT / ticker / "research" / "valuation.json"
            val: dict = {}
            if val_path.exists():
                try:
                    val = json.loads(val_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    val = {}
            if val.get("context_overlay"):
                r = subprocess.run(
                    [PY, str(SCRIPTS / "lint_context_overlay.py"), ticker],
                    cwd=ROOT,
                )
                if r.returncode != 0:
                    failed += 1
            if val.get("insider_signal"):
                r = subprocess.run(
                    [PY, str(SCRIPTS / "lint_insider_signal.py"), ticker],
                    cwd=ROOT,
                )
                if r.returncode != 0:
                    failed += 1
            continue
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
