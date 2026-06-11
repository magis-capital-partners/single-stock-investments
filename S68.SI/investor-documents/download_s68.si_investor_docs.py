#!/usr/bin/env python3
"""Download S68.SI filings from SGX Group investor relations."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANNUAL_DIR = ROOT / "S68.SI" / "official-reports" / "annual-reports"
PRES_DIR = ROOT / "S68.SI" / "presentations-and-media"
INTERIM_DIR = ROOT / "S68.SI" / "official-reports" / "interim-reports"
LOG_FILE = ROOT / "S68.SI" / "_download_log.txt"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
IR_REFERER = "https://investorrelations.sgx.com/"

PDF_SOURCES: list[tuple[str, str, Path]] = [
    (
        "annual_report_fy2025",
        "https://investorrelations.sgx.com/static-files/5d920b13-c5bb-4280-9b84-74025f006fc5",
        ANNUAL_DIR,
    ),
    (
        "financial_statements_fy2025",
        "https://investorrelations.sgx.com/static-files/634d5dd6-260a-4d66-ba38-3502fbe92587",
        ANNUAL_DIR,
    ),
    (
        "investor_presentation_jan2025_fy2024",
        "https://investorrelations.sgx.com/static-files/da9d8d49-6e49-40e6-a937-1cc0b2bf4338",
        PRES_DIR,
    ),
]


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 5000:
        log(f"SKIP exists -> {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": IR_REFERER,
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(f"FAIL {url} -> {e}")
        return False
    if len(data) < 5000 or data[:4] != b"%PDF":
        log(f"FAIL not a PDF ({len(data)} bytes) -> {dest.name}")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.relative_to(ROOT)}")
    return True


def main() -> int:
    log("Starting S68.SI SGX IR download (Singapore EU/SE)")
    manifest: list[dict] = []
    ok_count = 0
    for label, url, out_dir in PDF_SOURCES:
        safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
        dest = out_dir / safe
        time.sleep(0.3)
        ok = download(url, dest)
        if ok:
            ok_count += 1
        manifest.append(
            {"label": label, "url": url, "local": str(dest.relative_to(ROOT)), "ok": ok}
        )
    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"Done S68.SI. downloaded={ok_count}/{len(PDF_SOURCES)}")
    return 0 if ok_count >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
