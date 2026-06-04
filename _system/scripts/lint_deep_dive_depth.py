#!/usr/bin/env python3
"""Lint deep dive narrative depth (FRMO/TPL rubric).

Usage:
  python _system/scripts/lint_deep_dive_depth.py ICE
  python _system/scripts/lint_deep_dive_depth.py          # all latest dives
  python _system/scripts/lint_deep_dive_depth.py ICE --strict
  python _system/scripts/lint_deep_dive_depth.py ICE --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deep_dive_depth_common import PASS_SCORE, MAX_SCORE, DepthResult, score_dive  # noqa: E402


def latest_dive(research: Path) -> Path | None:
    dives = sorted(research.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def format_report(result: DepthResult) -> str:
    rel = result.path.relative_to(ROOT)
    lines = [
        f"{rel}: depth {result.total}/{MAX_SCORE} ({result.grade})"
        f" — {'PASS' if result.passed() else 'FAIL'} (need ≥{PASS_SCORE})",
    ]
    for c in result.criteria:
        if c.score < 2:
            lines.append(f"  [{c.score}/2] {c.label}: {c.detail}")
    if result.full_tier_count < 2 and result.ticker:
        lines.append(
            f"  WARN: full-tier filing extracts = {result.full_tier_count} (target ≥2)"
        )
    for w in result.archetype_warnings:
        lines.append(f"  WARN: {w}")
    for e in result.archetype_errors:
        lines.append(f"  ARCH: {e}")
    return "\n".join(lines)


def result_to_dict(result: DepthResult) -> dict:
    return {
        "path": str(result.path.relative_to(ROOT)),
        "ticker": result.ticker,
        "total": result.total,
        "max": MAX_SCORE,
        "grade": result.grade,
        "passed": result.passed(),
        "full_tier_count": result.full_tier_count,
        "criteria": [
            {"key": c.key, "label": c.label, "score": c.score, "detail": c.detail}
            for c in result.criteria
        ],
        "archetype_errors": result.archetype_errors,
        "archetype_warnings": result.archetype_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint deep dive narrative depth")
    parser.add_argument("ticker", nargs="?", help="Ticker symbol")
    parser.add_argument("--strict", action="store_true", help="Fail if score < 18 or archetype gaps")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    paths: list[Path] = []
    if args.ticker:
        d = latest_dive(ROOT / args.ticker / "research")
        if d:
            paths = [d]
    else:
        for td in sorted(ROOT.iterdir()):
            if td.name.startswith("_") or td.name.startswith("."):
                continue
            if td.is_dir() and (td / "research").is_dir():
                d = latest_dive(td / "research")
                if d:
                    paths.append(d)

    if not paths:
        print("No deep dives found.")
        return 0

    results = [score_dive(p, archetype_strict=args.strict) for p in paths]
    failed = False

    if args.json:
        print(json.dumps([result_to_dict(r) for r in results], indent=2))
    else:
        for r in results:
            print(format_report(r))
            print()

    for r in results:
        if not r.passed():
            failed = True
        if args.strict and r.archetype_errors:
            failed = True
        if r.full_tier_count < 2 and r.ticker and args.strict:
            failed = True

    if failed and args.strict:
        print(f"DEPTH LINT: {sum(1 for r in results if not r.passed())} dive(s) below {PASS_SCORE}/{MAX_SCORE}")
        return 1

    if any(not r.passed() for r in results) and not args.strict:
        n = sum(1 for r in results if not r.passed())
        print(f"WARN: {n} dive(s) below narrative pass bar ({PASS_SCORE}/{MAX_SCORE}); use --strict to fail")

    print(f"OK: {len(paths)} deep dive(s) depth-scored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
