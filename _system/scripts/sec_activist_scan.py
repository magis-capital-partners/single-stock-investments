#!/usr/bin/env python3
"""Scan SEC EDGAR for activist filings on portfolio tickers (13D, proxy supplements)."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

from activist_common import (
    ACTIVIST_FORMS,
    activist_reports_dir,
    append_scan_log,
    load_ticker_index,
    match_firm_id,
    now_iso,
    rel,
    save_ticker_index,
    side_for_firm,
    ticker_meta,
    upsert_report,
)

SEC_UA = "MarvinActivistScan contact@example.com"
SLEEP_SEC = 0.12
ROOT = Path(__file__).resolve().parents[2]


def sec_url(cik_path: str, accession: str, primary: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{nodash}/{primary}"


def fetch_submissions(cik: str) -> dict:
    cik_padded = f"{int(cik):010d}"
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        append_scan_log({"source": "sec", "status": "download_fail", "url": url, "error": str(exc)})
        return False
    dest.write_bytes(data)
    return True


def read_filer_hint(path: Path, limit: int = 12000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def scan_ticker_sec(ticker: str, *, min_date: str = "2018-01-01", dry_run: bool = False) -> list[dict]:
    meta = ticker_meta(ticker)
    cik = meta.get("cik")
    if not cik:
        return []
    try:
        submissions = fetch_submissions(cik)
    except Exception as exc:
        append_scan_log({"source": "sec", "ticker": ticker, "status": "submissions_fail", "error": str(exc)})
        return []
    time.sleep(SLEEP_SEC)

    recent = submissions.get("filings", {}).get("recent") or {}
    forms = recent.get("form") or []
    hits: list[dict] = []
    cik_path = str(int(cik))

    for i, form in enumerate(forms):
        if form not in ACTIVIST_FORMS:
            continue
        filing_date = (recent.get("filingDate") or [""])[i]
        if filing_date < min_date:
            continue
        accession = (recent.get("accessionNumber") or [""])[i]
        primary = (recent.get("primaryDocument") or [""])[i]
        if not accession or not primary:
            continue
        url = sec_url(cik_path, accession, primary)
        ext = Path(primary).suffix or ".htm"
        side = "long"
        if form.startswith("SC 13G"):
            side = "long"
        dest_name = f"{form.replace(' ', '-')}_{filing_date.replace('-', '')}_acc{accession.replace('-', '_')}{ext}"
        dest = activist_reports_dir(ticker, side) / dest_name
        if not dry_run:
            ok = download(url, dest)
            if not ok:
                continue
        text = read_filer_hint(dest) if dest.exists() else ""
        firm_id = match_firm_id(text) or "unknown_activist"
        side = side_for_firm(firm_id, default=side)
        entry = {
            "firm_id": firm_id,
            "firm_name": firm_id.replace("_", " ").title(),
            "side": side,
            "report_date": filing_date,
            "title": f"{form} filing",
            "source": "sec_edgar",
            "source_url": url,
            "local_pdf": rel(dest) if dest.suffix.lower() == ".pdf" else None,
            "local_file": rel(dest),
            "form": form,
            "accession": accession,
            "status": "new",
            "tier": "context",
            "confidence": 0.9 if firm_id != "unknown_activist" else 0.5,
        }
        hits.append(entry)
        if not dry_run:
            index = load_ticker_index(ticker)
            if upsert_report(index, entry):
                save_ticker_index(ticker, index)
    return hits


def scan_portfolio_sec(tickers: list[str] | None = None, *, dry_run: bool = False) -> dict:
    tickers = tickers or []
    all_hits: list[dict] = []
    for ticker in tickers:
        hits = scan_ticker_sec(ticker, dry_run=dry_run)
        for hit in hits:
            hit["ticker"] = ticker
        all_hits.extend(hits)
    return {
        "source": "sec_edgar",
        "generated_at": now_iso(),
        "ticker_count": len(tickers),
        "hit_count": len(all_hits),
        "hits": all_hits,
    }
