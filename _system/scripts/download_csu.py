#!/usr/bin/env python3
"""Download Constellation Software (CSU) IR PDFs and update document-index.csv."""
from __future__ import annotations

import csv
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKER = ROOT / "CSU"
LOG = TICKER / "_download_log.txt"
UA = "Mozilla/5.0 MarvinPortfolioDocs/1.0"
PAGES = [
    "https://www.csisoftware.com/about-us/investor-relations",
    "https://www.csisoftware.com/category/stat-filings/",
]
KNOWN_PDFS = [
    "https://www.csisoftware.com/wp-content/uploads/2026/04/Q4-2025-Shareholder-Report.pdf",
    "https://www.csisoftware.com/wp-content/uploads/2026/04/Q3-2025-Shareholder-Report.pdf",
    "https://www.csisoftware.com/wp-content/uploads/2026/04/Q2-2025-Shareholder-Report.pdf",
    "https://www.csisoftware.com/wp-content/uploads/2026/04/Q1-2025-Shareholder-Report.pdf",
    "https://www.csisoftware.com/wp-content/uploads/2026/05/Q1-2026-Shareholder-Report.pdf",
    "https://www.csisoftware.com/wp-content/uploads/2026/05/CSI-Financial-Statement-Q126-Final.pdf",
    "https://www.csisoftware.com/wp-content/uploads/2026/05/CSI-MDA-Q1-2026-Final.pdf",
]


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def crawl_csu_pages() -> set[str]:
    start = "https://www.csisoftware.com/about-us/investor-relations"
    seen_pages: set[str] = set()
    queue = [start]
    pdfs: set[str] = set()
    while queue and len(seen_pages) < 40:
        page = queue.pop(0)
        if page in seen_pages:
            continue
        seen_pages.add(page)
        try:
            req = urllib.request.Request(page, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="ignore")
        except Exception as e:
            log(f"FAIL page {page} -> {e}")
            continue
        for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", html, re.I):
            pdfs.add(m)
        for m in re.findall(r'href=(["\'])(.*?)\1', html, re.I):
            href = m[1]
            if ".pdf" in href.lower():
                u = href if href.startswith("http") else urllib.parse.urljoin(page, href)
                pdfs.add(u)
                continue
            if href.startswith("/") and "investor-relations" in href:
                queue.append(urllib.parse.urljoin("https://www.csisoftware.com", href))
        time.sleep(0.12)
    return pdfs


def main() -> None:
    log("Starting CSU IR harvest")
    pdfs = crawl_csu_pages()
    pdfs.update(KNOWN_PDFS)
    ok = 0
    rows = []
    for url in sorted(pdfs):
        name = re.sub(r"[^\w.\-]", "_", url.rsplit("/", 1)[-1])
        dest = TICKER / "official-reports" / name
        if dest.exists() and dest.stat().st_size > 0:
            ok += 1
        else:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                ok += 1
                log(f"OK {len(data):,} -> {name}")
            except Exception as e:
                log(f"FAIL {url} -> {e}")
                continue
        rows.append({
            "path": str(dest.relative_to(TICKER)).replace("\\", "/"),
            "title": name,
            "date": datetime.fromtimestamp(dest.stat().st_mtime).strftime("%Y-%m-%d"),
            "source_url": url,
            "type": "pdf",
        })
        time.sleep(0.12)

    idx = TICKER / "document-index.csv"
    with idx.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "title", "date", "source_url", "type"])
        w.writeheader()
        w.writerows(rows)
    log(f"Done CSU pdfs={ok} index_rows={len(rows)}")


if __name__ == "__main__":
    main()
