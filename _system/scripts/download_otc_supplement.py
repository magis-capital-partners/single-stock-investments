#!/usr/bin/env python3
"""Supplement downloads for OTC / thin-disclosure tickers and CSU."""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = "Mozilla/5.0 MarvinPortfolioDocs/1.0"


def log(ticker: Path, msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    (ticker / "_download_log.txt").open("a", encoding="utf-8").write(line + "\n")


def fetch_pdfs_from_pages(pages: list[str]) -> set[str]:
    pdfs: set[str] = set()
    for page in pages:
        try:
            req = urllib.request.Request(page, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.findall(r"https?://[^\s\"'<>]+\.pdf", html, re.I):
            pdfs.add(m)
        for m in re.findall(r'href=(["\'])(.*?)\1', html, re.I):
            if ".pdf" not in m[1].lower():
                continue
            u = m[1] if m[1].startswith("http") else urllib.parse.urljoin(page, m[1])
            pdfs.add(u)
        time.sleep(0.12)
    return pdfs


def download_to(ticker: Path, subdir: str, url: str) -> bool:
    name = re.sub(r"[^\w.\-]", "_", url.rsplit("/", 1)[-1])
    dest = ticker / subdir / name
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        dest.write_bytes(data)
        log(ticker, f"OK {len(data):,} -> {dest.name}")
        return True
    except Exception as e:
        log(ticker, f"FAIL {url} -> {e}")
        return False


def run() -> None:
    jobs = {
        "FRMO": {
            "dir": "investor-documents/ir-frmo",
            "pages": [
                "http://www.frmocorp.com/index.html",
                "http://www.frmocorp.com/annual-reports.html",
                "http://www.frmocorp.com/reports.html",
            ],
        },
        "OTCM": {
            "dir": "investor-documents/ir-otcm",
            "pages": [
                "https://www.otcmarkets.com/about/company/investor-relations",
                "https://www.otcmarkets.com/filing/company/financial-report/141813/content",
                "https://www.otcmarkets.com/otcapi/company/141813/financial-report",
            ],
        },
        "KEWL": {
            "dir": "investor-documents/ir-kewl",
            "pages": [
                "https://www.keweenawland.com/",
                "https://www.keweenawland.com/investor-relations/",
                "https://www.keweenawland.com/annual-reports/",
            ],
        },
        "HNFSA": {
            "dir": "investor-documents/ir-hnfsa",
            "pages": [
                "https://www.hanoverfoods.com/",
                "https://www.otcmarkets.com/stock/HNFSA/financials",
            ],
        },
        "CSU": {
            "dir": "official-reports",
            "pages": [
                "https://www.csisoftware.com/about-us/investor-relations",
                "https://www.csisoftware.com/about-us/investor-relations/press-releases",
                "https://www.csisoftware.com/about-us/investor-relations/events-and-presentations",
                "https://www.csisoftware.com/about-us/investor-relations/shareholder-reports",
                "https://www.csisoftware.com/about-us/investor-relations/financial-statements",
            ],
        },
    }
    for ticker_name, meta in jobs.items():
        ticker = ROOT / ticker_name
        log(ticker, f"Supplement harvest start {ticker_name}")
        pdfs = fetch_pdfs_from_pages(meta["pages"])
        log(ticker, f"Supplement URLs {len(pdfs)}")
        for url in sorted(pdfs):
            download_to(ticker, meta["dir"], url)
            time.sleep(0.12)


if __name__ == "__main__":
    run()
