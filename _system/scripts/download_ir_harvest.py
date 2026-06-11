#!/usr/bin/env python3
"""Harvest IR PDFs for international tickers (uk_ir, au_asx, in_ir) from registry ir_roots."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from download_us_investor_docs import (
    IR_UA,
    SLEEP_SEC,
    download,
    harvest_ir_pdfs,
    ir_dest,
)
from portfolio_registry import ROOT, load_registry

# Optional canonical PDF URLs when IR crawl returns nothing (ticker -> list of (label, url))
CANONICAL_PDFS: dict[str, list[tuple[str, str]]] = {
    "0388.HK": [
        (
            "annual_report_fy2024",
            "https://www.hkexgroup.com/-/media/HKEX-Group-Site/ssd/Investor-Relations/"
            "Regulatory-Reports/documents/2025/250317ar_e.pdf",
        ),
        (
            "annual_report_fy2023",
            "https://www.hkexgroup.com/-/media/HKEX-Group-Site/ssd/Investor-Relations/"
            "Regulatory-Reports/documents/2024/240320ar_e.pdf",
        ),
    ],
    "ASX.AX": [
        (
            "annual_report_fy2025",
            "https://www.asx.com.au/content/dam/asx/about/investor-relations/"
            "annual-reports/ASX-Annual-Report-2025.pdf",
        ),
        (
            "half_year_fy2025",
            "https://www.asx.com.au/content/dam/asx/about/investor-relations/"
            "half-year-reports/ASX-Half-Year-Report-2025.pdf",
        ),
    ],
    "BMYS.KL": [
        (
            "annual_report_2024",
            "https://www.bursamalaysia.com/documents/20125/0/Bursa+Annual+Report+2024.pdf",
        ),
        (
            "quarterly_report_q1_2025",
            "https://www.bursamalaysia.com/documents/20125/0/Bursa+1Q2025+Financial+Results.pdf",
        ),
    ],
    "B3SA3.SA": [
        (
            "annual_report_2024",
            "https://www.b3.com.br/en_us/about-b3/investor-relations/results-center/"
            "annual-reports/relatorio-anual-2024-ing.pdf",
        ),
    ],
    "PSE": [
        (
            "annual_report_2024",
            "https://www.pse.com.ph/stockMarket/listedCompanyDirectory/PSE-Annual-Report-2024.pdf",
        ),
    ],
    "TASE": [
        (
            "annual_report_2024",
            "https://maya.tase.co.il/api/v1/attachment/english/annual-report-2024.pdf",
        ),
    ],
}


def log(log_file: Path, msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def eu_dest(ticker_root: Path, label: str) -> Path:
    annual = ticker_root / "official-reports" / "annual-reports"
    pres = ticker_root / "presentations-and-media"
    annual.mkdir(parents=True, exist_ok=True)
    pres.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
    if any(k in label.lower() for k in ("presentation", "deck", "slides", "investor")):
        return pres / safe
    return annual / safe


def install_wrapper(ticker: str) -> Path:
    inv = ROOT / ticker / "investor-documents"
    inv.mkdir(parents=True, exist_ok=True)
    script = inv / f"download_{ticker.lower()}_investor_docs.py"
    if not script.exists():
        script.write_text(
            f'''#!/usr/bin/env python3
"""Download {ticker} IR PDFs via shared Marvin IR harvest script."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
subprocess.check_call([
    sys.executable,
    str(ROOT / "_system" / "scripts" / "download_ir_harvest.py"),
    "--ticker",
    "{ticker}",
])
''',
            encoding="utf-8",
        )
    return script


def run_ticker(ticker: str) -> int:
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    if ticker not in holdings:
        print(f"Unknown ticker {ticker}")
        return 1

    h = holdings[ticker]
    dl = h.get("download") or {}
    ir_roots = dl.get("ir_roots") or []
    ticker_root = ROOT / ticker
    log_file = ticker_root / "_download_log.txt"
    install_wrapper(ticker)

    inv = ticker_root / "investor-documents"
    ir_dir = inv / f"ir-{ticker.lower()}"
    ir_dir.mkdir(parents=True, exist_ok=True)
    (ticker_root / "official-reports" / "annual-reports").mkdir(parents=True, exist_ok=True)
    (ticker_root / "presentations-and-media").mkdir(parents=True, exist_ok=True)

    log(log_file, f"Starting IR harvest for {ticker}")
    ok_count = 0

    pdfs = harvest_ir_pdfs(ir_roots, log_file) if ir_roots else set()
    log(log_file, f"IR crawl found {len(pdfs)} PDF URL(s)")

    for url in sorted(pdfs):
        dest = ir_dest(ir_dir, url)
        time.sleep(SLEEP_SEC)
        if download(url, dest, IR_UA, log_file):
            ok_count += 1

    for label, url in CANONICAL_PDFS.get(ticker, []):
        dest = eu_dest(ticker_root, label)
        time.sleep(SLEEP_SEC)
        if download(url, dest, IR_UA, log_file):
            ok_count += 1

    manifest_path = inv / "DOWNLOAD_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            [{"ticker": ticker, "ir_ok": ok_count, "crawl_urls": len(pdfs), "source": "ir_harvest"}],
            indent=2,
        ),
        encoding="utf-8",
    )
    log(log_file, f"Done {ticker}. IR downloads OK={ok_count}")
    return 0 if ok_count > 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    raise SystemExit(run_ticker(args.ticker.strip().upper()))


if __name__ == "__main__":
    main()
