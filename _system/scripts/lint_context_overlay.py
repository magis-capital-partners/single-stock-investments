#!/usr/bin/env python3
"""Lint mechanical context_overlay-only changes.

  python3 _system/scripts/lint_context_overlay.py TPL
  python3 _system/scripts/lint_context_overlay.py --from-diff origin/main
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES_MANIFEST = ROOT / "_system" / "reference" / "market-data" / "themes" / "manifest.json"

FORBIDDEN_VAL_KEYS = frozenset({
    "inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay",
})


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def lint_valuation_overlay(ticker: str) -> list[str]:
    errors: list[str] = []
    vp = ROOT / ticker / "research" / "valuation.json"
    if not vp.exists():
        return [f"{ticker}: no valuation.json"]
    val = load_json(vp)
    overlay = val.get("context_overlay")
    if not overlay:
        return [f"{ticker}: missing context_overlay"]
    if "Lawrence base IRR" not in (overlay.get("disclaimer") or ""):
        errors.append(f"{ticker}: context_overlay missing Lawrence disclaimer")
    for theme in overlay.get("themes") or []:
        for ind in theme.get("indicators") or []:
            if ind.get("in_base_irr"):
                errors.append(
                    f"{ticker}: indicator {ind.get('id')} has in_base_irr=true without human review in this lint path"
                )
    manifest = load_json(THEMES_MANIFEST)
    as_of = overlay.get("as_of")
    if as_of:
        try:
            ld = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
            if (date.today() - ld).days > 10:
                errors.append(f"{ticker}: context_overlay as_of {as_of} stale (>10 days)")
        except ValueError:
            pass
    staleness = manifest.get("staleness_max_days", 10)
    m_as_of = manifest.get("as_of")
    if m_as_of:
        try:
            ld = datetime.strptime(str(m_as_of)[:10], "%Y-%m-%d").date()
            if (date.today() - ld).days > staleness:
                errors.append(f"{ticker}: themes manifest as_of {m_as_of} stale (>{staleness} days)")
        except ValueError:
            pass
    return errors


def valuation_diff_mechanical_only(ticker: str, base: str) -> bool:
    vp = f"{ticker}/research/valuation.json"
    r = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--", vp],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if not r.stdout.strip():
        return False
    try:
        before = load_json(ROOT / ticker / "research" / "valuation.json")
    except Exception:
        before = {}
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
    except json.JSONDecodeError:
        return False
    new = before
    for key in FORBIDDEN_VAL_KEYS:
        if old.get(key) != new.get(key):
            return False
    return True


def tickers_from_diff(base: str) -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tickers: set[str] = set()
    for line in (r.stdout or "").splitlines():
        if "/research/" not in line:
            continue
        tk = line.split("/")[0]
        if tk and not tk.startswith(("_", ".")):
            tickers.add(tk)
    return sorted(tickers)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Tickers to lint")
    ap.add_argument("--from-diff", metavar="BASE", help="Lint tickers from git diff vs BASE")
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args()
    if args.from_diff:
        tickers = tickers_from_diff(args.from_diff)
    else:
        tickers = args.tickers
    if not tickers:
        print("SKIP: no tickers")
        return 0
    failed = 0
    for tk in tickers:
        errs = lint_valuation_overlay(tk)
        for e in errs:
            print(f"FAIL: {e}")
            failed += 1
        if not errs:
            print(f"OK {tk}: context_overlay valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
