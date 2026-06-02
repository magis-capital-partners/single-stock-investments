#!/usr/bin/env python3
"""Full Marvin refresh for all registry holdings (delegates to marvin_cloud_refresh).

Usage:
  python _system/scripts/batch_portfolio_refresh.py --date 2026-05-29
  python _system/scripts/batch_portfolio_refresh.py --date 2026-05-29 --milly
  python _system/scripts/batch_portfolio_refresh.py --only KEWL MSB --skip-milly
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import latest_deep_dive_date  # noqa: E402


def tickers_from_registry() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    data = json.loads(reg.read_text(encoding="utf-8"))
    return sorted(data.get("holdings", {}).keys())


def run_cloud_refresh(
    ticker: str,
    dive_date: str,
    *,
    milly: bool,
    strict_evidence: bool,
    reindex: bool,
) -> bool:
    cmd = [
        PY,
        str(SCRIPTS / "marvin_cloud_refresh.py"),
        ticker,
        "--date",
        dive_date,
        "--skip-dashboard",
    ]
    if not milly:
        cmd.append("--skip-milly")
    if strict_evidence:
        cmd.append("--strict-evidence")
    if reindex:
        cmd.append("--reindex")
    print(f"\n=== {ticker} (dive {dive_date}) ===", flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    return r.returncode == 0


def resolve_dive_date(ticker: str, requested: str) -> str | None:
    research = ROOT / ticker / "research"
    explicit = research / f"deep_dive_{requested}.md"
    if explicit.exists():
        return requested
    latest = latest_deep_dive_date(research)
    if latest:
        if latest != requested:
            print(f"  WARN {ticker}: no deep_dive_{requested}.md — using {latest}")
        return latest
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="Target dive date YYYY-MM-DD")
    parser.add_argument("--skip", nargs="*", default=[], help="Tickers to skip")
    parser.add_argument("--only", nargs="*", help="Only these tickers")
    parser.add_argument(
        "--milly",
        action="store_true",
        help="Run Milly adversarial per ticker (default: skip for batch speed)",
    )
    parser.add_argument(
        "--strict-evidence",
        action="store_true",
        help="Fail tickers that fail check_evidence_completeness",
    )
    parser.add_argument("--reindex", action="store_true", help="Rebuild INDEX.csv per ticker")
    args = parser.parse_args()

    tickers = [t.upper() for t in (args.only or tickers_from_registry())]
    skip = {t.upper() for t in args.skip}
    ok, fail, skipped = [], [], []

    for ticker in tickers:
        if ticker in skip:
            skipped.append(ticker)
            print(f"SKIP {ticker} (--skip)")
            continue
        research = ROOT / ticker / "research"
        if not research.is_dir():
            print(f"SKIP {ticker}: no research/")
            skipped.append(ticker)
            continue
        if not (research / "valuation.json").exists():
            print(f"SKIP {ticker}: no valuation.json")
            skipped.append(ticker)
            continue
        dive_date = resolve_dive_date(ticker, args.date)
        if not dive_date:
            print(f"SKIP {ticker}: no deep_dive_*.md")
            skipped.append(ticker)
            continue
        if run_cloud_refresh(
            ticker,
            dive_date,
            milly=args.milly,
            strict_evidence=args.strict_evidence,
            reindex=args.reindex,
        ):
            ok.append(ticker)
        else:
            fail.append(ticker)

    subprocess.run([PY, str(SCRIPTS / "build_dashboard_data.py")], cwd=ROOT, check=False)

    print(f"\n=== Done {args.date} ===")
    print(f"OK ({len(ok)}): {', '.join(ok) or 'none'}")
    print(f"FAIL ({len(fail)}): {', '.join(fail) or 'none'}")
    print(f"SKIP ({len(skipped)}): {', '.join(skipped) or 'none'}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
