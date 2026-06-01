#!/usr/bin/env python3
"""Download LSEG investor documents from canonical IR PDF URLs (UK LSE-listed)."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IR_DIR = Path(__file__).resolve().parent / "ir-lseg"
LOG_FILE = ROOT / "LSEG" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

# Canonical URLs — update when new results published
PDF_URLS = [
    (
        "annual_report_2025",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/annual-reports/lseg-annual-report-2025.pdf",
    ),
    (
        "annual_report_2024",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/annual-reports/lseg-annual-report-2024.pdf",
    ),
    (
        "preliminary_results_rns_2025_26feb2026",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/financial-results/preliminary-results/rns/lseg-2025-preliminary-results-rns-26feb2026.pdf",
    ),
    (
        "preliminary_results_presentation_2025_26feb2026",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/financial-results/preliminary-results/presentation/lseg-2025-preliminary-results-presentation-26feb2026.pdf",
    ),
    (
        "trading_update_q1_2026_rns_23apr2026",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/financial-results/trading-statement/rns/lseg-trading-update-q1-2026-rns-23apr2026.pdf",
    ),
    (
        "trading_update_q1_2026_presentation_23apr2026",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/financial-results/trading-statement/presentation/lseg-q1-trading-update-results-presentation23apr2026.pdf",
    ),
    (
        "preliminary_results_rns_2024_27feb2025",
        "https://www.lseg.com/content/dam/lseg/en_us/documents/investor-relations/financial-results/preliminary-results/rns/lseg-2024-preliminary-results-rns-27feb2025.pdf",
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
    log("Starting LSEG UK IR download")
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
    log(f"Done LSEG. IR={ok_count}/{len(PDF_URLS)}")


if __name__ == "__main__":
    main()
