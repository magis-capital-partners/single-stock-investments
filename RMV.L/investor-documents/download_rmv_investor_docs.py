#!/usr/bin/env python3
"""Download Rightmove PLC investor documents from canonical IR PDF URLs (LSE RMV.L)."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # RMV.L/
IR_DIR = Path(__file__).resolve().parent / "ir-rightmove"
OFFICIAL = ROOT / "official-reports"
LOG_FILE = ROOT / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "fy25_annual_report_2025",
        "https://plc.rightmove.co.uk/content/uploads/2026/03/RIG004-V2-2025-ARA-WEB-READY-260323.pdf",
        OFFICIAL,
    ),
    (
        "fy25_full_year_rns_27feb2026",
        "https://plc.rightmove.co.uk/content/uploads/2026/02/Rightmove-RNS-27.02.26.pdf",
        IR_DIR,
    ),
    (
        "fy25_results_presentation_27feb2026",
        "https://plc.rightmove.co.uk/content/uploads/2026/02/260227-FY25-Presentation.pdf",
        IR_DIR,
    ),
    (
        "fy24_annual_report_2024",
        "https://plc.rightmove.co.uk/content/uploads/2025/05/RIG001_2024AR_WEB_250321_160525.pdf",
        OFFICIAL,
    ),
    (
        "fy24_full_year_rns",
        "https://plc.rightmove.co.uk/content/uploads/2025/02/FY24-Full-RNS.pdf",
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


def main() -> None:
    log("Starting Rightmove UK IR download")
    manifest: list[dict] = []
    ok_count = 0
    for label, url, folder in PDF_URLS:
        safe = re.sub(r"[^\w\-]+", "_", label)[:80]
        dest = folder / f"{safe}.pdf"
        ok = download(url, dest)
        if ok:
            ok_count += 1
        manifest.append({"label": label, "url": url, "path": str(dest.relative_to(ROOT)), "ok": ok})
        time.sleep(0.3)
    manifest_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Done {ok_count}/{len(PDF_URLS)} files")
    sys.exit(0 if ok_count == len(PDF_URLS) else 1)


if __name__ == "__main__":
    main()
