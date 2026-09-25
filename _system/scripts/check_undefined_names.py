#!/usr/bin/env python3
"""Fail on undefined names (ruff F821) and on files ruff cannot parse.

A file with a syntax error yields no F821 findings at all -- ruff cannot build
its scopes -- so an unparseable file hides every undefined name in it. Both
count as failures. There is no allowance list: the last known debt
(two_phase_watch.py's `fetch_ir` and `today`) is fixed on main.

Usage:
  python _system/scripts/check_undefined_names.py [PATH ...]
  (defaults: _system/scripts _system/trading)

Exit codes: 0 clean; 1 undefined names or unparseable files; 2 ruff did not run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

DEFAULT_PATHS = ("_system/scripts", "_system/trading")
SYNTAX_CODES = {None, "", "invalid-syntax", "E999"}


def run_ruff(paths: list[str]) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--select", "F821",
         "--output-format=json", "--exit-zero", *paths],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ruff failed").strip())
    return json.loads(proc.stdout or "[]")


def classify(diagnostics: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Split into (undefined names, unparseable). Anything else ruff reports
    under --select F821 is a parse failure too."""
    undefined = [d for d in diagnostics if d.get("code") == "F821"]
    unparseable = [d for d in diagnostics if d.get("code") != "F821"]
    return undefined, unparseable


def describe(diagnostic: dict[str, Any]) -> str:
    where = diagnostic.get("location") or {}
    path = str(diagnostic.get("filename") or "?").replace("\\", "/")
    code = diagnostic.get("code") or "invalid-syntax"
    return f"{path}:{where.get('row', '?')}:{where.get('column', '?')}: {code} {diagnostic.get('message', '')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS))
    args = parser.parse_args(argv)
    try:
        diagnostics = run_ruff(args.paths)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: ruff did not run: {exc}", file=sys.stderr)
        return 2
    undefined, unparseable = classify(diagnostics)
    for diagnostic in undefined + unparseable:
        line = describe(diagnostic)
        print(line)
        where = diagnostic.get("location") or {}
        path = str(diagnostic.get("filename") or "").replace("\\", "/")
        print(f"::error file={path},line={where.get('row', 1)}::{line}")
    if undefined or unparseable:
        print(f"FAIL: {len(undefined)} undefined name(s), {len(unparseable)} parse error(s) "
              "(a file ruff cannot parse hides its undefined names).")
        return 1
    print(f"OK: no undefined names and no parse errors in {', '.join(args.paths)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
