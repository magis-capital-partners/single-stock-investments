#!/usr/bin/env python3
"""Orchestrate downloads for all portfolio holdings (registry-driven).

Modes:
  (default)  Full harvest — per-ticker document/transcript downloads (network +
             OCR heavy) followed by the daily market/thematic/dashboard refresh.
  --light    Daily refresh only — skip the heavy per-ticker document harvest and
             only refresh the fast, daily-changing market/thematic data plus the
             dashboard. Intended for the daily schedule; the full harvest runs a
             couple of times per week.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SCRIPTS = ROOT / "_system" / "scripts"


def dedicated_investor_script(ticker: str) -> Path | None:
    inv = ROOT / ticker / "investor-documents"
    if not inv.is_dir():
        return None
    scripts = sorted(inv.glob("download_*_investor_docs.py"))
    return scripts[0] if scripts else None


def run(cmd: list[str], label: str, *, cwd: Path | None = None, timeout: int = 900) -> None:
    print(f"\n=== {label} ===")
    try:
        subprocess.run(cmd, cwd=cwd or ROOT, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A slow or broken issuer endpoint must not consume the entire Actions
        # allocation.  The next bounded run will resume at the next ticker.
        print(f"! {label} exceeded {timeout}s; continuing")


def powershell_script(script: Path) -> list[str] | None:
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return [exe, "-ExecutionPolicy", "Bypass", "-File", str(script)]
    return None


def harvest_documents(holdings: dict, *, tickers: list[str], include_aggregates: bool) -> None:
    """Heavy, network- and OCR-intensive per-ticker document/transcript harvest."""
    for ticker in tickers:
        dl = (holdings[ticker].get("download") or {})
        dtype = dl.get("type", "us_shared")

        if dtype == "us_dedicated":
            script = ROOT / ticker / "investor-documents" / f"download_{ticker.lower()}_investor_docs.py"
            if ticker == "QDEL":
                script = ROOT / "QDEL/investor-documents/download_qdel_investor_docs.py"
            run([PY, str(script)], f"{ticker} (dedicated)")
        elif dtype == "us_shared":
            run([PY, str(SCRIPTS / "download_us_investor_docs.py"), "--ticker", ticker], ticker)
        elif dtype == "jp_ps1":
            script = ROOT / ticker / "_scripts" / "download_and_organize.ps1"
            if script.exists() and script.stat().st_size > 80:
                ps_cmd = powershell_script(script)
                if ps_cmd:
                    run(ps_cmd, ticker)
                else:
                    print(f"\n=== {ticker} (jp_ps1 skipped — no PowerShell) ===")
        elif dtype == "jp_archive":
            ir_script = ROOT / ticker / "_scripts" / "download_sfh_ir.py"
            if ir_script.exists():
                run([PY, str(ir_script)], f"{ticker} IR harvest")
            else:
                log = ROOT / ticker / "_download_log.txt"
                log.write_text(
                    f"{datetime.now().isoformat()} Archive present; INDEX rebuilt by Marvin\n",
                    encoding="utf-8",
                )
                script_dir = ROOT / ticker / "_scripts"
                script_dir.mkdir(parents=True, exist_ok=True)
                dl_script = script_dir / "download_and_organize.ps1"
                if not dl_script.exists():
                    dl_script.write_text(
                        "# Placeholder: PDFs already mirrored. Rebuild INDEX via build_folder_indexes.py\n",
                        encoding="utf-8",
                    )
        elif dtype in {"uk_ir", "au_asx", "in_ir"}:
            script = dedicated_investor_script(ticker)
            if script:
                run([PY, str(script)], f"{ticker} ({dtype})")
            else:
                run([PY, str(SCRIPTS / "download_ir_harvest.py"), "--ticker", ticker], f"{ticker} ({dtype} harvest)")

    if include_aggregates and any((holdings.get(t, {}).get("download") or {}).get("type") == "eu_teq" for t in tickers):
        run([PY, str(SCRIPTS / "download_teq_st.py")], "TEQ.ST")

    if include_aggregates and "CSU" in tickers:
        run([PY, str(SCRIPTS / "download_csu.py")], "CSU")

    if include_aggregates and any(t in tickers for t in ("OTCM", "FRMO", "KEWL")):
        run([PY, str(SCRIPTS / "download_otc_api.py")], "OTC tickers (OTCM/FRMO/KEWL)")

    if include_aggregates:
        run([PY, str(SCRIPTS / "download_transcripts.py"), "--register-legacy"], "Transcript harvest (IR + Polygon timing)")
        run([PY, str(SCRIPTS / "transcript_gap_report.py")], "Transcript coverage report")

    for ticker in tickers:
        tx_dir = ROOT / ticker / "investor-documents" / "transcripts"
        if tx_dir.is_dir() and any(tx_dir.iterdir()):
            run(
                [PY, str(SCRIPTS / "build_management_evidence.py"), ticker],
                f"{ticker} management evidence",
            )

    if include_aggregates:
        run([PY, str(SCRIPTS / "refresh_equity_model.py")], "Equity model refresh (IR + pipeline)")


def daily_refresh(holdings: dict, *, build_indexes: bool = True) -> None:
    """Fast, daily-changing market/thematic refresh plus dashboard rebuild."""
    for ticker in sorted(holdings.keys()):
        val_path = ROOT / ticker / "research" / "valuation.json"
        if not val_path.exists():
            continue
        try:
            val = json.loads(val_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        er = val.get("evidence_refresh") or {}
        if er.get("type") == "commodity_nav" or ticker == "KEWL":
            run(
                [PY, str(SCRIPTS / "fetch_market_inputs.py"), ticker, "--merge"],
                f"{ticker} market inputs",
            )

    run([PY, "-m", "darwin.import_external_data"], "Sync etf-dashboard external data", cwd=SCRIPTS)
    run([PY, str(SCRIPTS / "extract_theme_facts.py")], "Extract filing theme panels")
    run([PY, str(SCRIPTS / "fetch_theme_panel.py")], "Thematic indicator panels")
    run([PY, str(SCRIPTS / "apply_context_overlay.py")], "Apply thematic context overlay")
    run([PY, str(SCRIPTS / "fetch_ls_microstructure.py")], "L/S microstructure context")
    run([PY, str(SCRIPTS / "fetch_peer_panel.py")], "Peer comparison panels")
    run([PY, str(SCRIPTS / "fetch_insider_transactions.py")], "Insider Form 4 transactions")
    run([PY, str(SCRIPTS / "apply_insider_signal.py")], "Insider conviction overlay")

    if build_indexes:
        run([PY, str(SCRIPTS / "build_folder_indexes.py")], "Build INDEX.csv files", timeout=1200)
    run([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], "Sync portfolio from registry")
    run(
        [PY, str(SCRIPTS / "refresh_cvr_universe.py")],
        "CVR universe refresh (sleeve + registry)",
    )
    run([PY, str(SCRIPTS / "build_dashboard_data.py")], "Rebuild dashboard JSON")


def select_batch(holdings: dict, batch_size: int, cursor_path: Path) -> list[str]:
    """Return the next deterministic issuer batch and persist the resume cursor."""
    tickers = sorted(holdings)
    if not tickers or batch_size <= 0:
        return tickers
    try:
        state = json.loads(cursor_path.read_text(encoding="utf-8"))
        offset = int(state.get("next_offset", 0)) % len(tickers)
    except (OSError, ValueError, json.JSONDecodeError):
        offset = 0
    batch = [tickers[(offset + i) % len(tickers)] for i in range(min(batch_size, len(tickers)))]
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "universe_size": len(tickers),
                "last_batch": batch,
                "next_offset": (offset + len(batch)) % len(tickers),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--light",
        action="store_true",
        help="Skip the heavy per-ticker document/transcript harvest; only refresh "
        "daily market/thematic data and rebuild the dashboard.",
    )
    parser.add_argument("--batch-size", type=int, default=0, help="Bound full-harvest work to the next N holdings.")
    parser.add_argument("--skip-indexes", action="store_true", help="Skip portfolio-wide INDEX.csv rebuild for a light refresh.")
    parser.add_argument("--skip-aggregate-harvest", action="store_true", help="Skip transcript/model aggregate work in a bounded batch.")
    args = parser.parse_args()

    reg = load_registry()
    holdings = reg.get("holdings") or {}

    batch = select_batch(holdings, args.batch_size, ROOT / "_system" / "data" / "download_cursor.json")
    if args.light:
        print("=== Light daily refresh (document harvest skipped) ===")
    else:
        print(f"=== Bounded document harvest: {len(batch)} of {len(holdings)} holdings ===")
        harvest_documents(holdings, tickers=batch, include_aggregates=not args.skip_aggregate_harvest)

    daily_refresh(holdings, build_indexes=not args.skip_indexes)
    print("\nLight daily refresh finished." if args.light else "\nAll download jobs finished.")


if __name__ == "__main__":
    main()
