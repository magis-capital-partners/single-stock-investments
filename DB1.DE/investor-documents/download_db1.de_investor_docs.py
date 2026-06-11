#!/usr/bin/env python3
"""Download Deutsche Börse Group investor documents from canonical IR PDF URLs."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IR_DIR = Path(__file__).resolve().parent / "ir-db1"
LOG_FILE = ROOT / "DB1.DE" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "annual_report_2025",
        "https://www.deutsche-boerse.com/resource/blob/4911290/d6d302b8d549de98f963142a9e3987d1/data/DBG-annual-report-2025.pdf",
    ),
    (
        "annual_report_2024",
        "https://www.deutsche-boerse.com/resource/blob/4171108/ed6eebbf4732a0df7e5338f963c388eb/data/DBG-annual-report-2024-a4.pdf",
    ),
    (
        "quarterly_statement_q1_2026",
        "https://www.deutsche-boerse.com/resource/blob/5053028/5524b27e0d1ea96ed562d1b6dedd7465/data/gdb-quarterly-statement-q1-2026_en.pdf",
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
    log("Starting DB1.DE IR download")
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
    log(f"Done DB1.DE. IR={ok_count}/{len(PDF_URLS)}")


if __name__ == "__main__":
    main()
