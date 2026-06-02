#!/usr/bin/env python3
"""Recompute Lawrence owner-cash IRRs at 7-year horizon and refresh dives + dashboard.

Usage:
  python _system/scripts/regenerate_lawrence_7yr.py
  python _system/scripts/regenerate_lawrence_7yr.py --only ICE FRMO
  python _system/scripts/regenerate_lawrence_7yr.py --skip-lint
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system/scripts"
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import latest_deep_dive_date  # noqa: E402


def tickers_from_registry() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    data = json.loads(reg.read_text(encoding="utf-8"))
    return sorted(data.get("holdings", {}).keys())


def refresh_ticker(ticker: str, *, skip_lint: bool) -> bool:
    research = ROOT / ticker / "research"
    val_path = research / "valuation.json"
    if not val_path.exists():
        print(f"SKIP {ticker}: no valuation.json")
        return True
    dive_date = latest_deep_dive_date(research)
    if not dive_date:
        print(f"SKIP {ticker}: no deep_dive_*.md")
        return True
    print(f"=== {ticker} {dive_date} ===", flush=True)
    book_cfg = research / "book_estimate_config.json"
    if book_cfg.exists():
        subprocess.run(
            [PY, str(SCRIPTS / "current_book_estimate.py"), ticker, "--write"],
            cwd=ROOT,
            check=False,
        )
    r = subprocess.run(
        [PY, str(SCRIPTS / "marvin_valuation.py"), "--ticker", ticker, "--write"],
        cwd=ROOT,
    )
    if r.returncode != 0:
        return False
    r = subprocess.run(
        [PY, str(SCRIPTS / "refresh_deep_dive_v2.py"), ticker, "--date", dive_date],
        cwd=ROOT,
    )
    if r.returncode != 0:
        return False
    if not skip_lint:
        r = subprocess.run(
            [PY, str(SCRIPTS / "lint_deep_dive.py"), ticker],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.stdout:
            print(r.stdout.strip())
        if r.returncode != 0:
            print(f"WARN lint {ticker}")
    subprocess.run(
        [PY, str(SCRIPTS / "sync_classification.py"), "--fix", "--ticker", ticker],
        cwd=ROOT,
        check=False,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Subset of tickers")
    parser.add_argument("--skip", nargs="*", default=[], help="Tickers to skip")
    parser.add_argument("--skip-lint", action="store_true")
    args = parser.parse_args()

    tickers = [t.upper() for t in (args.only or tickers_from_registry())]
    skip = {t.upper() for t in args.skip}
    ok, fail = [], []

    for ticker in tickers:
        if ticker in skip:
            continue
        if refresh_ticker(ticker, skip_lint=args.skip_lint):
            ok.append(ticker)
        else:
            fail.append(ticker)

    subprocess.run([PY, str(SCRIPTS / "build_dashboard_data.py")], cwd=ROOT, check=False)
    subprocess.run([PY, str(SCRIPTS / "sync_classification.py"), "--fix"], cwd=ROOT, check=False)

    print(f"\nDone: OK={len(ok)} FAIL={len(fail)}")
    if fail:
        print("Failed:", ", ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
