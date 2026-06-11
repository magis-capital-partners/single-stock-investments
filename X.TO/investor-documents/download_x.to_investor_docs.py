#!/usr/bin/env python3
"""Download TMX Group (X.TO) investor documents from canonical IR PDF URLs."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IR_DIR = Path(__file__).resolve().parent / "ir-tmx"
LOG_FILE = ROOT / "X.TO" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "annual_report_2025",
        "https://s21.q4cdn.com/671813756/files/doc_financials/2025/ar/TMX_2025_Annual-Report_EN_Web.pdf",
    ),
    (
        "annual_report_2024",
        "https://s21.q4cdn.com/671813756/files/doc_financials/2024/ar/TMX_2024_Annual-Report_EN_Web.pdf",
    ),
    (
        "ye_2025_mda",
        "https://s21.q4cdn.com/671813756/files/doc_financials/2025/q4/TMX-Group-Limited-YE-2025-MD-A_EN_Final.pdf",
    ),
    (
        "ye_2025_financial_statements",
        "https://s21.q4cdn.com/671813756/files/doc_financials/2025/q4/EN-_-TMX-Group-Limited-YE-2025-Financial-Statements.pdf",
    ),
    (
        "q1_2026_mda",
        "https://s21.q4cdn.com/671813756/files/doc_financials/2026/q1/TMX-Group-Limited-Q1-2026-MDA-EN.pdf",
    ),
    (
        "q1_2026_financial_statements",
        "https://s21.q4cdn.com/671813756/files/doc_financials/2026/q1/EN-_-TMX-Group-Limited-Q1-2026-Financial-Statements.pdf",
    ),
    (
        "aif_2024",
        "https://s21.q4cdn.com/671813756/files/doc_downloads/1/TMX-Group-AIF-YE-Dec-31-2024-ENG-SEDAR-VERSION.pdf",
    ),
]


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
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
    log(f"OK {len(data):,} bytes -> {dest.name}")
    return True


def main() -> None:
    log("Starting X.TO (TMX Group) IR download")
    IR_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    ok_count = 0
    for label, url in PDF_URLS:
        safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
        dest = IR_DIR / safe
        time.sleep(0.15)
        ok = download(url, dest)
        if ok:
            ok_count += 1
        manifest.append({"label": label, "url": url, "local": str(dest.relative_to(ROOT)), "ok": ok})
    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Done X.TO. IR={ok_count}/{len(PDF_URLS)}")


if __name__ == "__main__":
    main()
