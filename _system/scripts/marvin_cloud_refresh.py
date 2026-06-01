#!/usr/bin/env python3
"""Single-ticker Marvin pipeline for cloud and local refresh (same as batch_portfolio_refresh).

Usage:
  python _system/scripts/marvin_cloud_refresh.py AMZN --date 2026-05-29
  python _system/scripts/marvin_cloud_refresh.py SNOW --date 2026-05-29 --reindex
  python _system/scripts/marvin_cloud_refresh.py ICE --date 2026-05-29 --skip-milly
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable


def run(label: str, cmd: list[str], *, optional: bool = False) -> bool:
    print(f"  {label}...", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if out.strip():
        for line in out.strip().splitlines()[-10:]:
            print(f"    {line}")
    if r.returncode != 0:
        print(f"  {'WARN' if optional else 'FAIL'} {label} exit={r.returncode}")
        return optional
    return True


def run_milly(ticker: str, dive_date: str) -> bool:
    code = f"""
import json, sys
from pathlib import Path
ROOT = Path({repr(str(ROOT))})
sys.path.insert(0, str(ROOT / '_system/scripts'))
from milly_batch_pass import write_adversarial, add_dive_header_link, append_milly_log, latest_filing_facts
from lint_adversarial import lint_ticker, latest_dive

ticker = {repr(ticker)}
research = ROOT / ticker / 'research'
dive = latest_dive(research)
if not dive:
    raise SystemExit('no deep dive')
val = json.loads((research / 'valuation.json').read_text(encoding='utf-8'))
facts = latest_filing_facts(research / 'evidence')
errs, warns = lint_ticker(ticker, consistency_only=False, strict=False)
out = write_adversarial(ticker, {repr(dive_date)}, dive, val, facts, errs, warns)
blocked = any('returns_statement' in e for e in errs)
add_dive_header_link(ticker, dive, {repr(dive_date)}, blocked)
append_milly_log(ticker, not blocked, 'marvin_cloud_refresh')
print('OK', out)
"""
    return run("Milly adversarial", [PY, "-c", code])


def main() -> int:
    parser = argparse.ArgumentParser(description="Marvin cloud/local mechanical pipeline")
    parser.add_argument("ticker", help="Ticker symbol")
    parser.add_argument("--date", required=True, help="Deep dive date YYYY-MM-DD")
    parser.add_argument("--reindex", action="store_true", help="Rebuild INDEX.csv for this ticker")
    parser.add_argument("--skip-milly", action="store_true", help="Skip adversarial pass")
    parser.add_argument("--skip-evidence", action="store_true", help="Skip build_filing_evidence")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    research = ROOT / ticker / "research"
    if not research.is_dir():
        print(f"ERROR: {ticker}/research/ missing")
        return 1
    if not (research / "valuation.json").exists():
        print(f"ERROR: {ticker}/research/valuation.json missing — create inputs before pipeline")
        return 1
    dive = research / f"deep_dive_{args.date}.md"
    if not dive.exists():
        alt = sorted(research.glob("deep_dive_*.md"))
        if not alt:
            print(
                f"ERROR: no deep_dive_{args.date}.md — write narrative first "
                f"(see _system/prompts/cloud_marvin_runbook.md)"
            )
            return 1
        print(f"WARN: using latest dive for refresh; expected deep_dive_{args.date}.md")

    print(f"=== marvin_cloud_refresh {ticker} {args.date} ===")
    ok = True

    if args.reindex:
        ok &= run(
            "INDEX.csv",
            [PY, str(SCRIPTS / "build_folder_indexes.py"), "--ticker", ticker],
        )
    if not args.skip_evidence:
        ok &= run(
            "filing evidence",
            [PY, str(SCRIPTS / "build_filing_evidence.py"), ticker],
        )

    ok &= run(
        "HK extract refresh",
        [PY, str(SCRIPTS / "refresh_hk_extracts.py")],
        optional=True,
    )

    ok &= run(
        "third-party source scan",
        [
            PY,
            str(SCRIPTS / "scan_third_party_sources.py"),
            ticker,
            "--date",
            args.date,
            "--with-hk",
        ],
    )

    hk_index = ROOT / "_system" / "reference" / "investment-wisdom" / "hk_ticker_index.json"
    if hk_index.exists():
        idx = json.loads(hk_index.read_text(encoding="utf-8"))
        if ticker in idx.get("tickers", {}):
            pass  # HK scan already run via scan_third_party_sources --with-hk

    ok &= run(
        "valuation write",
        [PY, str(SCRIPTS / "marvin_valuation.py"), "--ticker", ticker, "--write"],
    )
    ok &= run(
        "deep dive v2 refresh",
        [PY, str(SCRIPTS / "refresh_deep_dive_v2.py"), ticker, "--date", args.date],
    )
    lint_ok = run(
        "lint deep dive",
        [PY, str(SCRIPTS / "lint_deep_dive.py"), ticker, "--milly"],
    )
    ok &= lint_ok

    if not args.skip_milly:
        ok &= run_milly(ticker, args.date)

    ok &= run(
        "sync classification",
        [PY, str(SCRIPTS / "sync_classification.py"), "--fix", "--ticker", ticker],
        optional=True,
    )
    ok &= run(
        "dashboard JSON",
        [PY, str(SCRIPTS / "build_dashboard_data.py")],
    )
    ok &= run(
        "cross-check verify",
        [PY, str(SCRIPTS / "check_cross_checks.py"), ticker],
        optional=True,
    )

    if not ok:
        print("DONE with failures — fix lint/errors before merge")
        return 1
    print("DONE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
