#!/usr/bin/env python3
"""Download Warsaw Stock Exchange (GPW.WA) investor documents from canonical IR PDF URLs."""
from __future__ import annotations

import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IR_DIR = Path(__file__).resolve().parent / "ir-gpw"
OFFICIAL = ROOT / "official-reports"
LOG_FILE = ROOT / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "2024-12-31_Consolidated_Financial_Statements_EN",
        "https://www.gpw.pl/pub/GPW/files/PDF/raporty/R2024/Q4/EN/Consolidated_financial_statements_GPW_Group_2024.pdf",
        OFFICIAL,
    ),
    (
        "2024-12-31_Annual_Selected_Consolidated_Data_EN",
        "https://www.gpw.pl/pub/GPW/files/PDF/raporty/R2024/Q4/EN/Selected_consolidated_financial_data_GPW_Group_2024.pdf",
        OFFICIAL,
    ),
    (
        "2025-03-31_Q1_Management_Report_EN",
        "https://www.pb.pl/static/att/emitent/2025-05/Sprawozdanie-Zarzadu-GK-GPW-1Q2025-EN_202505141434581747.pdf",
        IR_DIR,
    ),
    (
        "2025-03-31_Q1_Selected_Consolidated_Data",
        "https://www.pb.pl/static/att/emitent/2025-05/Selected-Consolidated-Financial-Data_202505141434581747.pdf",
        IR_DIR,
    ),
]


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        log(f"SKIP exists -> {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(f"FAIL {url} -> {e}")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.relative_to(ROOT)}")
    return True


def main() -> int:
    log("Starting GPW.WA IR download")
    ok_count = 0
    for label, url, folder in PDF_URLS:
        safe = re.sub(r"[^\w\-]+", "_", label)[:80]
        dest = folder / f"{safe}.pdf"
        if download(url, dest):
            ok_count += 1
        time.sleep(0.5)
    log(f"Done: {ok_count}/{len(PDF_URLS)} files")
    return 0 if ok_count == len(PDF_URLS) else 1


if __name__ == "__main__":
    sys.exit(main())
