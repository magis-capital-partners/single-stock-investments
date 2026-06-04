#!/usr/bin/env python3
"""Download IEX.NS filings from BSE (doc.iexindia.com blocks cloud egress)."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANNUAL_DIR = ROOT / "IEX.NS" / "official-reports" / "annual-reports"
INTERIM_DIR = ROOT / "IEX.NS" / "official-reports" / "interim-reports"
PRES_DIR = ROOT / "IEX.NS" / "presentations-and-media"
LOG_FILE = ROOT / "IEX.NS" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
BSE_REFERER = "https://www.bseindia.com/"

# BSE-hosted PDFs (NSE: IEX.NS, BSE scrip: 540750)
PDF_SOURCES: list[tuple[str, str, Path]] = [
    (
        "annual_report_fy_2023_24_bse",
        "https://www.bseindia.com/xml-data/corpfiling/AttachHis/35754ce2-aaee-4f63-9a72-564a21605a94.pdf",
        ANNUAL_DIR,
    ),
    (
        "investor_presentation_q4_fy25_bse",
        "https://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname=8a412546-2713-4839-88ad-52bd7b9043f7.pdf",
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
            "Referer": BSE_REFERER,
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(f"FAIL {url} -> {e}")
        return False
    if len(data) < 5000 or not data[:4] == b"%PDF":
        log(f"FAIL not a PDF ({len(data)} bytes) -> {dest.name}")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.relative_to(ROOT)}")
    return True


def main() -> int:
    log("Starting IEX.NS BSE download (India IN)")
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
    log(f"Done IEX.NS. downloaded={ok_count}/{len(PDF_SOURCES)}")
    log("NOTE: doc.iexindia.com FY24-25 annual + Q4 FY26 filings need Vicki/browser harvest [HUMAN REVIEW]")
    return 0 if ok_count >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
