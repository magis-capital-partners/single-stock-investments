#!/usr/bin/env python3
"""Download ATHEX Group investor documents from canonical IR PDF URLs."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IR_DIR = Path(__file__).resolve().parent / "ir-athex"
LOG_FILE = ROOT / "HEE" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "annual_report_2025",
        "https://athens.euronext.com/sites/default/files/2026-03/ATHEX_2025_Annual_Financial_Report_EN.pdf",
    ),
    (
        "annual_report_2024",
        "https://athens.euronext.com/sites/default/files/2025-04/ATHEX_2024_Annual_Financial_Report_EN_v2.pdf",
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
    log("Starting HEE (ATHEX Group) IR download")
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
    log(f"Done HEE. IR={ok_count}/{len(PDF_URLS)}")


if __name__ == "__main__":
    main()
