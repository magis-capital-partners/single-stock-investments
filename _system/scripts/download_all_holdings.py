#!/usr/bin/env python3
"""Orchestrate downloads for all portfolio holdings (registry-driven)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import load_registry

ROOT = Path(__file__).resolve().parents[2]


def dedicated_investor_script(ticker: str) -> Path | None:
    inv = ROOT / ticker / "investor-documents"
    if not inv.is_dir():
        return None
    scripts = sorted(inv.glob("download_*_investor_docs.py"))
    return scripts[0] if scripts else None
PY = sys.executable
SCRIPTS = ROOT / "_system" / "scripts"


def dedicated_investor_script(ticker: str) -> Path | None:
    inv = ROOT / ticker / "investor-documents"
    if not inv.is_dir():
        return None
    scripts = sorted(inv.glob("download_*_investor_docs.py"))
    return scripts[0] if scripts else None


def run(cmd: list[str], label: str, *, cwd: Path | None = None) -> None:
    print(f"\n=== {label} ===")
    subprocess.run(cmd, cwd=cwd or ROOT, check=False)


def powershell_script(script: Path) -> list[str]:
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return [exe, "-ExecutionPolicy", "Bypass", "-File", str(script)]
    raise RuntimeError(f"PowerShell not found; cannot run {script}")


def main() -> None:
    reg = load_registry()
    holdings = reg.get("holdings") or {}

    for ticker in sorted(holdings.keys()):
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
                run(powershell_script(script), ticker)
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

    if any((holdings.get(t, {}).get("download") or {}).get("type") == "eu_teq" for t in holdings):
        run([PY, str(SCRIPTS / "download_teq_st.py")], "TEQ.ST")

    if "CSU" in holdings:
        run([PY, str(SCRIPTS / "download_csu.py")], "CSU")

    if any(t in holdings for t in ("OTCM", "FRMO", "KEWL")):
        run([PY, str(SCRIPTS / "download_otc_api.py")], "OTC tickers (OTCM/FRMO/KEWL)")

    run([PY, str(SCRIPTS / "download_transcripts.py"), "--register-legacy"], "Transcript harvest (IR + Polygon timing)")
    run([PY, str(SCRIPTS / "transcript_gap_report.py")], "Transcript coverage report")

    for ticker in sorted(holdings.keys()):
        val_path = ROOT / ticker / "research" / "valuation.json"
        if not val_path.exists():
            continue
        try:
            val = json.loads(val_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        er = val.get("evidence_refresh") or {}
        if er.get("type") == "commodity_nav" or ticker in ("KEWL", "MSB"):
            run(
                [PY, str(SCRIPTS / "fetch_market_inputs.py"), ticker, "--merge"],
                f"{ticker} market inputs",
            )
        tx_dir = ROOT / ticker / "investor-documents" / "transcripts"
        if tx_dir.is_dir() and any(tx_dir.iterdir()):
            run(
                [PY, str(SCRIPTS / "build_management_evidence.py"), ticker],
                f"{ticker} management evidence",
            )

    run([PY, "-m", "darwin.import_external_data"], "Sync etf-dashboard external data", cwd=SCRIPTS)
    run([PY, str(SCRIPTS / "extract_theme_facts.py")], "Extract filing theme panels")
    run([PY, str(SCRIPTS / "fetch_theme_panel.py")], "Thematic indicator panels")
    run([PY, str(SCRIPTS / "apply_context_overlay.py")], "Apply thematic context overlay")
    run([PY, str(SCRIPTS / "fetch_ls_microstructure.py")], "L/S microstructure context")
    run([PY, str(SCRIPTS / "fetch_peer_panel.py")], "Peer comparison panels")
    run([PY, str(SCRIPTS / "fetch_insider_transactions.py")], "Insider Form 4 transactions")
    run([PY, str(SCRIPTS / "apply_insider_signal.py")], "Insider conviction overlay")

    run([PY, str(SCRIPTS / "build_folder_indexes.py")], "Build INDEX.csv files")
    run([PY, str(SCRIPTS / "sync_portfolio_from_registry.py")], "Sync portfolio from registry")
    run([PY, str(SCRIPTS / "refresh_equity_model.py")], "Equity model refresh (IR + pipeline)")
    run([PY, str(SCRIPTS / "build_dashboard_data.py")], "Rebuild dashboard JSON")
    print("\nAll download jobs finished.")


if __name__ == "__main__":
    main()
