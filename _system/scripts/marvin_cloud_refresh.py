#!/usr/bin/env python3
"""Single-ticker Marvin pipeline for cloud, batch, and local refresh.

Usage:
  python _system/scripts/marvin_cloud_refresh.py KEWL --date 2026-06-02
  python _system/scripts/marvin_cloud_refresh.py KEWL --date 2026-06-02 --strict-evidence
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

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import (  # noqa: E402
    has_evidence_refresh_config,
    latest_deep_dive_date,
    ticker_needs_commodity_inputs,
)


def run(label: str, cmd: list[str], *, optional: bool = False, cwd: Path | None = None) -> bool:
    print(f"  {label}...", flush=True)
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if out.strip():
        for line in out.strip().splitlines()[-10:]:
            print(f"    {line}")
    if r.returncode != 0:
        print(f"  {'WARN' if optional else 'FAIL'} {label} exit={r.returncode}")
        return optional
    return True


def run_script(label: str, script: str, script_args: list[str], *, optional: bool = False) -> bool:
    path = SCRIPTS / script
    if not path.exists():
        print(f"  SKIP {label}: {script} not in repo")
        return True
    return run(label, [PY, str(path), *script_args], optional=optional)


def ticker_has_cik(ticker: str) -> bool:
    """True when ticker has SEC CIK for Form 4 insider fetch."""
    try:
        from insider_signal_common import cik_for_ticker  # noqa: WPS433

        return bool(cik_for_ticker(ticker))
    except Exception:
        cfg_path = SCRIPTS / "us_ticker_config.json"
        if not cfg_path.exists():
            return False
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            entry = cfg.get(ticker.upper()) or cfg.get(ticker)
            return bool(isinstance(entry, dict) and entry.get("cik"))
        except json.JSONDecodeError:
            return False


def ticker_has_theme_tag(ticker: str) -> bool:
    """True when ticker is tagged to a thematic indicator panel."""
    cfg_path = ROOT / "_system" / "portfolio" / "holdings_themes.json"
    if not cfg_path.exists():
        return False
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    tk = ticker.upper()
    for blk in (cfg.get("themes") or {}).values():
        tickers = blk.get("tickers") or []
        if "*" in tickers:
            return True
        if tk in {t.upper() for t in tickers}:
            return True
    return False


def needs_evidence_gate(val: dict) -> bool:
    if has_evidence_refresh_config(val):
        return True
    if val.get("valuation_mode") == "optionality" and val.get("nav_overlay"):
        return True
    return ticker_needs_commodity_inputs(val)


def run_milly(ticker: str, dive_date: str, *, strict_evidence: bool = False) -> bool:
    code = f"""
import json, sys
from pathlib import Path
ROOT = Path({repr(str(ROOT))})
sys.path.insert(0, str(ROOT / '_system/scripts'))
from milly_batch_pass import write_adversarial, add_dive_header_link, append_milly_log, latest_filing_facts
from lint_adversarial import lint_ticker, latest_dive
from marvin_pipeline_common import has_evidence_refresh_config

ticker = {repr(ticker)}
strict_evidence = {strict_evidence}
research = ROOT / ticker / 'research'
dive = latest_dive(research)
if not dive:
    raise SystemExit('no deep dive')
val = json.loads((research / 'valuation.json').read_text(encoding='utf-8'))
facts = latest_filing_facts(research / 'evidence')
errs, warns = lint_ticker(ticker, consistency_only=False, strict=False)
blocked = any('returns_statement' in e for e in errs)
if strict_evidence and has_evidence_refresh_config(val):
    blocked = blocked or bool(errs)
add_dive_header_link(ticker, dive, {repr(dive_date)}, blocked)
append_milly_log(ticker, not blocked, 'marvin_cloud_refresh')
out = write_adversarial(ticker, {repr(dive_date)}, dive, val, facts, errs, warns)
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
    parser.add_argument("--skip-dashboard", action="store_true", help="Skip dashboard JSON rebuild")
    parser.add_argument(
        "--strict-evidence",
        action="store_true",
        help="Fail on check_evidence_completeness; stricter Milly when evidence_refresh set",
    )
    parser.add_argument(
        "--strict-depth",
        action="store_true",
        help="Fail when lint_deep_dive_depth.py score < 18/24",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    research = ROOT / ticker / "research"
    if not research.is_dir():
        print(f"ERROR: {ticker}/research/ missing")
        return 1
    val_path = research / "valuation.json"
    if not val_path.exists():
        print(f"ERROR: {ticker}/research/valuation.json missing — create inputs before pipeline")
        return 1
    val = json.loads(val_path.read_text(encoding="utf-8"))
    strict_evidence = args.strict_evidence or needs_evidence_gate(val)

    dive = research / f"deep_dive_{args.date}.md"
    if not dive.exists():
        latest = latest_deep_dive_date(research)
        if not latest:
            print(
                f"ERROR: no deep_dive_{args.date}.md — write narrative first "
                f"(see _system/prompts/cloud_marvin_runbook.md)"
            )
            return 1
        print(f"WARN: using deep_dive_{latest}.md; expected deep_dive_{args.date}.md")
        args.date = latest

    print(f"=== marvin_cloud_refresh {ticker} {args.date} ===")
    ok = True

    if args.reindex:
        ok &= run(
            "INDEX.csv",
            [PY, str(SCRIPTS / "build_folder_indexes.py"), "--ticker", ticker],
        )
    if not args.skip_evidence:
        ok &= run(
            "seed dive overlays",
            [PY, str(SCRIPTS / "seed_dive_overlays.py"), ticker, "--write"],
            optional=True,
        )
        ok &= run(
            "download transcripts",
            [PY, str(SCRIPTS / "download_transcripts.py"), ticker, "--register-legacy"],
            optional=True,
        )
        ok &= run(
            "filing evidence",
            [PY, str(SCRIPTS / "build_filing_evidence.py"), ticker],
        )
        ok &= run(
            "management evidence",
            [PY, str(SCRIPTS / "build_management_evidence.py"), ticker],
            optional=True,
        )

    ok &= run(
        "market inputs",
        [PY, str(SCRIPTS / "fetch_market_inputs.py"), ticker, "--merge"],
        optional=not ticker_needs_commodity_inputs(val),
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
    ok &= run(
        "valuation write",
        [PY, str(SCRIPTS / "marvin_valuation.py"), "--ticker", ticker, "--write"],
    )
    if ticker_has_theme_tag(ticker):
        run(
            "etf-dashboard sync",
            [PY, "-m", "darwin.import_external_data"],
            optional=True,
            cwd=SCRIPTS,
        )
        run(
            "filing theme panels",
            [PY, str(SCRIPTS / "extract_theme_facts.py"), ticker],
            optional=True,
        )
        run(
            "thematic indicator panels",
            [PY, str(SCRIPTS / "fetch_theme_panel.py")],
            optional=True,
        )
        run(
            "thematic context overlay",
            [PY, str(SCRIPTS / "apply_context_overlay.py"), ticker],
            optional=True,
        )
        run(
            "peer panels",
            [PY, str(SCRIPTS / "fetch_peer_panel.py")],
            optional=True,
        )
    if ticker_has_cik(ticker):
        run(
            "insider Form 4 fetch",
            [PY, str(SCRIPTS / "fetch_insider_transactions.py"), ticker],
            optional=True,
        )
        run(
            "insider conviction signal",
            [PY, str(SCRIPTS / "apply_insider_signal.py"), ticker],
            optional=True,
        )
    run(
        "L/S microstructure",
        [PY, str(SCRIPTS / "fetch_ls_microstructure.py"), ticker],
        optional=True,
    )
    if has_evidence_refresh_config(val):
        ok &= run(
            "optionality evidence refresh",
            [PY, str(SCRIPTS / "refresh_optionality_valuation.py"), ticker],
        )
    book_cfg = research / "book_estimate_config.json"
    if book_cfg.exists():
        ok &= run(
            "book estimate",
            [PY, str(SCRIPTS / "current_book_estimate.py"), ticker, "--write"],
            optional=True,
        )
    ok &= run(
        "fill cross-check (pre-dive)",
        [PY, str(SCRIPTS / "fill_cross_check.py"), ticker, "--date", args.date, "--write"],
        optional=not strict_evidence,
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
    depth_args = [ticker]
    if args.strict_depth or strict_evidence:
        depth_args.append("--strict")
    ok &= run(
        "lint deep dive depth",
        [PY, str(SCRIPTS / "lint_deep_dive_depth.py"), *depth_args],
        optional=not (args.strict_depth or strict_evidence),
    )

    if not args.skip_milly:
        ok &= run_milly(ticker, args.date, strict_evidence=strict_evidence)

    ok &= run(
        "evidence completeness",
        [PY, str(SCRIPTS / "check_evidence_completeness.py"), ticker, "--date", args.date]
        + (["--strict"] if strict_evidence else []),
        optional=not strict_evidence,
    )
    ok &= run(
        "sync classification",
        [PY, str(SCRIPTS / "sync_classification.py"), "--fix", "--ticker", ticker],
        optional=True,
    )
    if not args.skip_dashboard:
        ok &= run(
            "dashboard JSON",
            [PY, str(SCRIPTS / "build_dashboard_data.py")],
            optional=True,
        )
    ok &= run(
        "cross-check verify",
        [PY, str(SCRIPTS / "check_cross_checks.py"), ticker],
        optional=not strict_evidence,
    )
    if strict_evidence:
        ok &= run(
            "lint deep dive (post-check)",
            [PY, str(SCRIPTS / "lint_deep_dive.py"), ticker, "--milly"],
        )

    status_path = ROOT / ticker / ".onboard_status.json"
    if status_path.exists():
        try:
            st = json.loads(status_path.read_text(encoding="utf-8"))
            if st.get("deep_dive_pending"):
                st["deep_dive_pending"] = False
                st["deep_dive_completed"] = args.date
                status_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
        except json.JSONDecodeError:
            pass

    if not ok:
        print("DONE with failures — fix lint/errors before merge")
        return 1
    print("DONE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
