#!/usr/bin/bin/env python3
"""Download BOLSAA.MX (Grupo BMV / Bolsa Mexicana de Valores) IR PDFs."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IR_DIR = Path(__file__).resolve().parent / "ir-bmv"
LOG_FILE = ROOT / "BOLSAA.MX" / "_download_log.txt"
BASE = "https://www.bmv.com.mx"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"

PDF_URLS = [
    (
        "integrated_annual_report_2024",
        f"{BASE}/docs-pub/informeAnual/Integrated%20Annual%20Report%202024.pdf",
    ),
    (
        "annual_report_2025",
        f"{BASE}/docs-pub/reporteAnualDictaminado/Reporte%20Anual%202025.pdf",
    ),
    (
        "annual_report_2024",
        f"{BASE}/docs-pub/reporteAnualDictaminado/Reporte%20Anual%202024%20Bolsa%20Mexicana%20de%20Valores%20.pdf",
    ),
    (
        "consolidated_financial_statements_2025",
        f"{BASE}/docs-pub/reporteAnualDictaminado/4.%20Consolidated%20Financial%20Statements.pdf",
    ),
    (
        "press_release_1q2026",
        f"{BASE}/docs-pub/reporteTrimestral/PRESS%20RELEASE%201Q26.pdf",
    ),
    (
        "quarterly_report_4q2025",
        f"{BASE}/docs-pub/reporteTrimestral/GBMV-doc-BMV_4Q25_ing.pdf",
    ),
    (
        "press_release_3q2025",
        f"{BASE}/docs-pub/reporteTrimestral/Press%20Release%203Q25.pdf",
    ),
    (
        "quarterly_report_2q2025",
        f"{BASE}/docs-pub/reporteTrimestral/GBMV-doc-BMV_2Q25_ing.pdf",
    ),
    (
        "annual_report_2023",
        f"{BASE}/docs-pub/reporteAnualDictaminado/reporteAnual_BOLSA_2023-12.pdf",
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
    if len(data) < 1000:
        log(f"FAIL {url} -> too small ({len(data)} bytes)")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.name}")
    return True


def main() -> None:
    log("Starting BOLSAA.MX BMV IR download")
    IR_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    ok_count = 0
    for label, url in PDF_URLS:
        safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
        dest = IR_DIR / safe
        time.sleep(0.2)
        ok = download(url, dest)
        if ok:
            ok_count += 1
        manifest.append({"label": label, "url": url, "local": str(dest.relative_to(ROOT)), "ok": ok})
    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Done BOLSAA.MX. IR={ok_count}/{len(PDF_URLS)}")


if __name__ == "__main__":
    main()
