#!/usr/bin/env python3
"""Download Euronext N.V. investor documents from canonical IR PDF URLs."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IR_DIR = Path(__file__).resolve().parent / "ir-euronext"
LOG_FILE = ROOT / "ENX.PA" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "urd_2025",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2026-04/EUR_2025_URD_EN_VMEL.pdf",
    ),
    (
        "urd_2024",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2025-04/EUR_URD2024_MEL_.pdf",
    ),
    (
        "semi_annual_2025",
        "https://www.euronext.com/sites/default/files/2025-07/2025_semi-annual_report.pdf",
    ),
    (
        "semi_annual_2024",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2024-07/ENX_Semi_Annual_report_H1_2024_VF.pdf",
    ),
    (
        "q1_2026_press_release",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2026-05/Q1%202026%20Results%20-%20Press%20Release.pdf",
    ),
    (
        "q1_2026_presentation",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2026-05/Q1%202026%20Results%20-%20Presentation.pdf",
    ),
    (
        "q1_2025_press_release",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2025-05/q1_2025_results_-_press_release.pdf",
    ),
    (
        "q1_2025_presentation",
        "https://www.euronext.com/sites/default/files/financial-event-doc/2025-05/q1_2025_results_-_presentation.pdf",
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
    log("Starting ENX.PA Euronext IR download")
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
    log(f"Done ENX.PA. IR={ok_count}/{len(PDF_URLS)}")


if __name__ == "__main__":
    main()
