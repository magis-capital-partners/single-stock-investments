#!/usr/bin/env python3
"""Fetch activist report index pages from known short/both publishers."""
from __future__ import annotations

import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from activist_common import (
    active_firms,
    activist_reports_dir,
    append_scan_log,
    load_ticker_index,
    now_iso,
    rel,
    safe_report_filename,
    save_ticker_index,
    text_matches_ticker,
    ticker_meta,
    upsert_report,
)

UA = "MarvinActivistScan/1.0 (+research)"
SLEEP_SEC = 1.0
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "activist_site_cache"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        text = ""
        self.links.append((href, text))

    def handle_data(self, data: str) -> None:
        if self.links:
            href, text = self.links[-1]
            self.links[-1] = (href, text + data)


def fetch_url(url: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = re.sub(r"[^a-zA-Z0-9._-]+", "_", urlparse(url).netloc + urlparse(url).path)
    cache_path = CACHE_DIR / f"{cache_key}.html"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 3600:
        return cache_path.read_text(encoding="utf-8", errors="ignore")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    cache_path.write_text(body, encoding="utf-8")
    time.sleep(SLEEP_SEC)
    return body


def extract_links(base_url: str, html: str) -> list[dict]:
    parser = LinkParser()
    parser.feed(html)
    out: list[dict] = []
    seen: set[str] = set()
    for href, text in parser.links:
        full = urljoin(base_url, href)
        if full in seen:
            continue
        seen.add(full)
        title = re.sub(r"\s+", " ", text).strip()
        if not title and href.startswith("http"):
            title = Path(urlparse(full).path).name.replace("-", " ")
        if not title:
            continue
        out.append({"url": full, "title": title})
    return out


def likely_report_link(url: str, title: str) -> bool:
    lower = f"{url} {title}".lower()
    if any(x in lower for x in ("privacy", "contact", "about", "subscribe", "twitter", "linkedin")):
        return False
    if url.lower().endswith(".pdf"):
        return True
    if any(x in lower for x in ("report", "research", "short", "analysis", "investigation")):
        return True
    path = urlparse(url).path.strip("/")
    if path and path.count("/") <= 2 and len(path) >= 4:
        return True
    return False


def download_binary(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        append_scan_log({"source": "site", "status": "download_fail", "url": url, "error": str(exc)})
        return False
    if url.lower().endswith(".pdf") and not data.startswith(b"%PDF-"):
        return False
    dest.write_bytes(data)
    time.sleep(SLEEP_SEC)
    return True


def scan_firm_site(firm: dict, tickers: list[str], *, dry_run: bool = False) -> list[dict]:
    domains = firm.get("domains") or []
    if not domains or firm.get("ingest_method") != "site_index":
        return []
    base = f"https://{domains[0]}/"
    try:
        html = fetch_url(base)
    except Exception as exc:
        append_scan_log({"source": "site", "firm_id": firm.get("id"), "status": "fetch_fail", "error": str(exc)})
        return []
    links = [l for l in extract_links(base, html) if likely_report_link(l["url"], l["title"])]
    hits: list[dict] = []
    firm_id = firm.get("id") or "unknown"
    side = "short" if firm.get("side") == "short" else "long"
    if firm.get("side") == "both":
        side = "short"

    for ticker in tickers:
        meta = ticker_meta(ticker)
        for link in links:
            blob = f"{link['title']} {link['url']}"
            if not text_matches_ticker(blob, meta):
                continue
            report_date = _guess_date(blob)
            ext = ".pdf" if link["url"].lower().endswith(".pdf") else ".html"
            dest_name = safe_report_filename(firm_id, report_date, Path(urlparse(link["url"]).path).stem[:40], ext)
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
                "status": "new",
                "tier": "context",
                "confidence": 0.75,
            }
            hits.append({**entry, "ticker": ticker})
            if not dry_run:
                index = load_ticker_index(ticker)
                if upsert_report(index, entry):
                    save_ticker_index(ticker, index)
    return hits


def _guess_date(text: str) -> str:
    m = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])[-_/](0[1-9]|[12]\d|3[01])", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(20\d{2})", text)
    if m:
        return f"{m.group(1)}-01-01"
    return now_iso()[:10]


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
