#!/usr/bin/env python3
"""Lint mechanical insider_signal-only changes.

  python3 _system/scripts/lint_insider_signal.py LMNR
  python3 _system/scripts/lint_insider_signal.py --from-diff origin/main
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "_system" / "reference" / "market-data" / "insider" / "manifest.json"

FORBIDDEN_VAL_KEYS = frozenset({
    "inputs", "scenarios", "implied_return", "results", "segment_build", "nav_overlay",
})


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def lint_insider_signal(ticker: str) -> list[str]:
    errors: list[str] = []
    vp = ROOT / ticker / "research" / "valuation.json"
    if not vp.exists():
        return [f"{ticker}: no valuation.json"]
    val = load_json(vp)
    sig = val.get("insider_signal")
    if not sig:
        return [f"{ticker}: missing insider_signal"]
    if "Lawrence base IRR" not in (sig.get("disclaimer") or ""):
        errors.append(f"{ticker}: insider_signal missing Lawrence disclaimer")
    if sig.get("in_base_irr"):
        errors.append(
            f"{ticker}: insider_signal.in_base_irr=true requires [HUMAN REVIEW] in this lint path"
        )
    ics = sig.get("ics")
    if not isinstance(ics, (int, float)) or not (0 <= float(ics) <= 10):
        errors.append(f"{ticker}: ICS out of range: {ics}")
    tilt = (sig.get("scenario_confidence") or {}).get("tilted") or {}
    if tilt:
        total = sum(float(v) for v in tilt.values() if isinstance(v, (int, float)))
        if abs(total - 1.0) > 0.02:
            errors.append(f"{ticker}: scenario tilt weights sum to {total:.3f}, not ~1.0")
    as_of = sig.get("as_of")
    if as_of:
        try:
            ld = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
            if (date.today() - ld).days > 14:
                errors.append(f"{ticker}: insider_signal as_of {as_of} stale (>14 days)")
        except ValueError:
            pass
    manifest = load_json(MANIFEST)
    m_as_of = manifest.get("as_of")
    if m_as_of:
        try:
            ld = datetime.strptime(str(m_as_of)[:10], "%Y-%m-%d").date()
            if (date.today() - ld).days > 14:
                errors.append(f"{ticker}: insider manifest as_of {m_as_of} stale (>14 days)")
        except ValueError:
            pass
    return errors


def valuation_diff_mechanical_only(ticker: str, base: str) -> bool:
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
        new = load_json(ROOT / ticker / "research" / "valuation.json")
    except json.JSONDecodeError:
        return False
    for key in FORBIDDEN_VAL_KEYS:
        if old.get(key) != new.get(key):
            return False
    return old.get("insider_signal") != new.get("insider_signal")


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
    args = ap.parse_args()
    tickers = tickers_from_diff(args.from_diff) if args.from_diff else args.tickers
    if not tickers:
        print("SKIP: no tickers")
        return 0
    failed = 0
    for tk in tickers:
        errs = lint_insider_signal(tk)
        for e in errs:
            print(f"FAIL: {e}")
            failed += 1
        if not errs:
            print(f"OK {tk}: insider_signal valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
