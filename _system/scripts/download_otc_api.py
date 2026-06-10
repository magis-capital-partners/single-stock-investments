#!/usr/bin/env python3
"""Download OTC Markets financial report PDFs for thin-disclosure OTC tickers."""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SYMBOLS = ("OTCM", "FRMO", "KEWL", "BWEL", "AZLCZ", "HNFSA", "WRLC", "PDER", "BVERS", "GCCO")


def log(ticker: Path, msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with (ticker / "_download_log.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        # OTC API often returns epoch milliseconds
        ts = int(value)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def fetch_reports(symbol: str) -> list[dict]:
    url = (
        f"https://backend.otcmarkets.com/otcapi/company/{symbol}/financial-report"
        f"?symbol={symbol}&page=1&pageSize=50&statusId=A&sortOn=releaseDate&sortDir=DESC"
    )
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": f"https://www.otcmarkets.com/stock/{symbol}/disclosure",
        "Origin": "https://www.otcmarkets.com",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"FAIL API {symbol}: {e}")
        return []
    records = data.get("records") or data.get("financialReports") or []
    return records if isinstance(records, list) else []


def download_pdf(ticker: Path, subdir: str, report_id: int, title: str, period: str) -> tuple[bool, str]:
    url = f"https://www.otcmarkets.com/file/company/financial-report/{report_id}/content"
    safe_title = re.sub(r"[^\w.\-]", "_", title)[:60]
    safe_period = re.sub(r"[^\w.\-]", "_", period or "")[:20]
    fname = f"{safe_period}_{safe_title}.pdf".strip("_")
    if not fname.endswith(".pdf"):
        fname += ".pdf"
    dest = ticker / subdir / fname
    rel = str(dest.relative_to(ticker)).replace("\\", "/")
    if dest.exists() and dest.stat().st_size > 0:
        return True, rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": UA,
        "Referer": f"https://www.otcmarkets.com/stock/{ticker.name}/disclosure",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if len(data) < 500 or not data[:4].startswith(b"%PDF"):
            log(ticker, f"SKIP non-pdf id={report_id} size={len(data)}")
            return False, rel
        dest.write_bytes(data)
        log(ticker, f"OK {len(data):,} -> {dest.name}")
        return True, rel
    except Exception as e:
        log(ticker, f"FAIL id={report_id} {url} -> {e}")
        return False, rel


def write_index(ticker: Path, rows: list[dict]) -> None:
    idx = ticker / "INDEX.csv"
    with idx.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "title", "date", "source_url", "type"])
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    for symbol in SYMBOLS:
        ticker = ROOT / symbol
        subdir = f"investor-documents/ir-{symbol.lower()}"
        log(ticker, f"OTC API harvest {symbol}")
        records = fetch_reports(symbol)
        log(ticker, f"OTC records={len(records)}")
        rows: list[dict] = []
        ok = 0
        for rec in records:
            report_id = rec.get("id")
            if not report_id:
                continue
            title = rec.get("reportType") or rec.get("title") or "report"
            period = fmt_date(rec.get("periodDate") or rec.get("releaseDate"))
            success, rel = download_pdf(ticker, subdir, int(report_id), str(title), period)
            if success:
                ok += 1
            rows.append({
                "path": rel,
                "title": f"{title} ({period})",
                "date": period,
                "source_url": f"https://www.otcmarkets.com/file/company/financial-report/{report_id}/content",
                "type": "pdf",
            })
            time.sleep(0.15)
        write_index(ticker, rows)
        log(ticker, f"Done {symbol} pdfs={ok} index_rows={len(rows)}")


if __name__ == "__main__":
    main()
