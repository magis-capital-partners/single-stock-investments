#!/usr/bin/env python3
"""Fetch activist report index pages from known short/both publishers."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from activist_common import (
    active_firms,
    activist_reports_dir,
    load_ticker_index,
    match_report_to_ticker,
    now_iso,
    rel,
    safe_report_filename,
    save_ticker_index,
    ticker_meta,
    upsert_report,
    url_target_mismatch,
)
from activist_site_fetchers import fetch_firm_reports

ROOT = Path(__file__).resolve().parents[2]


def download_binary(url: str, dest: Path) -> bool:
    from activist_site_fetchers import fetch_bytes

    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = fetch_bytes(url)
    except Exception:
        return False
    if url.lower().endswith(".pdf") and not data.startswith(b"%PDF-"):
        return False
    dest.write_bytes(data)
    return True


def _guess_date(link: dict) -> str:
    blob = f"{link.get('published', '')} {link.get('url', '')} {link.get('title', '')}"
    m = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])[-_/](0[1-9]|[12]\d|3[01])", blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(20\d{2})", blob)
    if m:
        return f"{m.group(1)}-01-01"
    return now_iso()[:10]


def scan_firm_site(firm: dict, tickers: list[str], *, dry_run: bool = False) -> list[dict]:
    if firm.get("ingest_method") != "site_index":
        return []
    links = fetch_firm_reports(firm)
    hits: list[dict] = []
    firm_id = firm.get("id") or "unknown"
    side = "short" if firm.get("side") in ("short", "both") else "long"

    for ticker in tickers:
        meta = ticker_meta(ticker)
        for link in links:
            blob = f"{link['title']} {link['url']}"
            if url_target_mismatch(link["url"], link["title"], meta):
                continue
            matched, confidence, reason = match_report_to_ticker(blob, meta)
            if not matched or confidence < 0.9:
                continue
            report_date = _guess_date(link)
            ext = ".pdf" if link["url"].lower().endswith(".pdf") else ".html"
            dest_name = safe_report_filename(
                firm_id, report_date, Path(urlparse(link["url"]).path).stem[:40], ext
            )
            dest = activist_reports_dir(ticker, side) / dest_name
            if not dry_run and not download_binary(link["url"], dest):
                continue
            entry = {
                "firm_id": firm_id,
                "firm_name": firm.get("name") or firm_id,
                "side": side,
                "report_date": report_date,
                "title": link["title"][:200],
                "source": "publisher_site",
                "source_url": link["url"],
                "local_pdf": rel(dest) if dest.suffix.lower() == ".pdf" else None,
                "local_file": rel(dest) if dest.exists() else None,
                "filing_class": "publisher_report",
                "include_in_feed": True,
                "status": "new",
                "tier": "context",
                "confidence": 0.8,
            }
            hits.append({**entry, "ticker": ticker})
            if not dry_run:
                index = load_ticker_index(ticker)
                if upsert_report(index, entry):
                    save_ticker_index(ticker, index)
    return hits


def scan_publisher_sites(tickers: list[str] | None = None, *, dry_run: bool = False) -> dict:
    tickers = tickers or []
    firms = [f for f in active_firms(side="short") if f.get("ingest_method") == "site_index"]
    firms.extend(f for f in active_firms(side="both") if f.get("ingest_method") == "site_index")
    all_hits: list[dict] = []
    for firm in firms:
        hits = scan_firm_site(firm, tickers, dry_run=dry_run)
        all_hits.extend(hits)
    return {
        "source": "publisher_site",
        "generated_at": now_iso(),
        "firm_count": len(firms),
        "hit_count": len(all_hits),
        "hits": all_hits,
    }
