#!/usr/bin/env python3
"""Fetch activist report index pages from known short/both publishers."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from activist_common import (
    firms_for_ingest,
    canonical_report_path,
    classify_publisher_page,
    firm_has_ingest,
    load_ticker_index,
    now_iso,
    publisher_match_allowed,
    rel,
    safe_report_filename,
    save_ticker_index,
    ticker_meta,
    upsert_report,
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


def _guess_date(link: dict) -> tuple[str | None, str, str | None]:
    blob = f"{link.get('published', '')} {link.get('url', '')} {link.get('title', '')}"
    m = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})\b",
        blob,
        re.I,
    )
    if m:
        month_map = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
            "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        month = month_map.get(m.group(1).lower()[:4], month_map.get(m.group(1).lower()[:3], "01"))
        return f"{m.group(3)}-{month}-{int(m.group(2)):02d}", "day", "publisher"
    m = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])[-_/](0[1-9]|[12]\d|3[01])", blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "day", "publisher"
    m = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])(?:[^0-9]|$)", blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01", "month", "publisher"
    m = re.search(r"\b(20[12]\d)\b", blob)
    if m:
        year = int(m.group(1))
        if year >= 2010:
            return f"{year}-01-01", "year", "publisher"
    return None, "unknown", None


def scan_firm_site(firm: dict, tickers: list[str], *, dry_run: bool = False) -> list[dict]:
    if not firm_has_ingest(firm, "site_index"):
        return []
    links = fetch_firm_reports(firm)
    hits: list[dict] = []
    firm_id = firm.get("id") or "unknown"
    # Long activist letters go under long/; short forensic reports under short/.
    # "both" firms (e.g. Kerrisdale) default to short for site pages unless
    # the title clearly looks like a long/open-letter campaign.
    side = "short" if firm.get("side") in ("short", "both") else "long"
    downloaded: dict[str, Path] = {}

    for link in links:
        url = link["url"]
        is_report, _page_reason = classify_publisher_page(url, link.get("title") or "")
        if not is_report:
            continue
        report_date, date_precision, date_source = _guess_date(link)
        ext = ".pdf" if url.lower().endswith(".pdf") else ".html"
        stem = Path(urlparse(url).path).stem[:40]
        date_part = (report_date or now_iso()[:10])[:10]
        dest_name = safe_report_filename(firm_id, date_part, stem, ext)
        dest = canonical_report_path(firm_id, dest_name)

        if not dry_run:
            if url not in downloaded:
                if not download_binary(url, dest):
                    continue
                downloaded[url] = dest
            else:
                dest = downloaded[url]

        canonical_ref = rel(dest) if dry_run or dest.exists() else None
        if not dry_run and not canonical_ref:
            continue

        title_l = (link.get("title") or "").lower()
        link_side = side
        if firm.get("side") == "both" and any(
            tok in title_l for tok in ("letter to", "open letter", "board of directors", "nominat")
        ):
            link_side = "long"
        filing_class = "publisher_report"
        if any(tok in title_l for tok in ("open letter", "letter to the board", "letter to board")):
            filing_class = "open_letter"
        elif "presentation" in title_l and any(tok in title_l for tok in ("board", "shareholder", "investor")):
            filing_class = "campaign_presentation"

        for ticker in tickers:
            meta = ticker_meta(ticker)
            blob = f"{link['title']} {link['url']}"
            ok, confidence, reason = publisher_match_allowed(url, link["title"], blob, meta)
            if not ok:
                continue
            entry = {
                "firm_id": firm_id,
                "firm_name": firm.get("name") or firm_id,
                "side": link_side,
                "report_date": report_date,
                "date_precision": date_precision,
                "date_source": date_source or "publisher",
                "title": link["title"][:200],
                "source": "publisher_site",
                "source_url": url,
                "canonical_file": canonical_ref,
                "local_pdf": canonical_ref if ext == ".pdf" else None,
                "local_file": canonical_ref,
                "filing_class": filing_class,
                "include_in_feed": True,
                "status": "new",
                "tier": "context",
                "confidence": confidence,
                "match_reason": reason,
                "match_confidence": confidence,
            }
            hits.append({**entry, "ticker": ticker})
            if not dry_run:
                index = load_ticker_index(ticker)
                if upsert_report(index, entry):
                    save_ticker_index(ticker, index)
    return hits


def scan_publisher_sites(tickers: list[str] | None = None, *, dry_run: bool = False) -> dict:
    tickers = tickers or []
    # Long + short + both firms that opt into site_index (Wave A long newsrooms included).
    firms = firms_for_ingest("site_index")
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
