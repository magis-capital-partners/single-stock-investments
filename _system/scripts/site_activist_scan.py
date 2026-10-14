#!/usr/bin/env python3
"""Fetch activist report index pages from known short/both publishers."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from email.utils import parsedate_to_datetime
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
from activist_site_fetchers import fetch_firm_reports, parse_position_marker

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


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_NAME = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_ORDINAL = r"(?:st|nd|rd|th)?"
_YEAR = r"((?:19|20)\d{2})"


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _rfc822_date(value: str) -> str | None:
    """RSS pubDate ("Mon, 06 Oct 2025 14:00:00 +0000") -> ISO date, else None."""
    if not value or not re.search(r"[A-Za-z]{3}", value):
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None or parsed.year < 1990:
        return None
    return parsed.date().isoformat()


def _guess_date(link: dict) -> tuple[str | None, str, str | None]:
    """Best publication date for a fetched link: (iso, precision, source).

    Never invents a day: a bare year is not a date, so a link with nothing
    better returns (None, "unknown", None). The old year fallback stamped every
    Hindenburg/Grizzly/Fuzzy Panda archive row YYYY-01-01 with precision
    "year", which downstream code then sorted and displayed as a real date.
    """
    published = str(link.get("published") or "").strip()
    iso = _rfc822_date(published)
    if iso:
        return iso, "day", "publisher"
    text = f"{published} {link.get('title', '')}"
    blob = f"{published} {link.get('url', '')} {link.get('title', '')}"
    # "Mar 10, 2021", "January 7th, 2021"
    for m in re.finditer(rf"\b{_MONTH_NAME}\s+(\d{{1,2}}){_ORDINAL},?\s+{_YEAR}\b", blob, re.I):
        iso = _iso(int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
        if iso:
            return iso, "day", "publisher"
    # "06 Oct 2025", "7th January 2021"
    for m in re.finditer(rf"\b(\d{{1,2}}){_ORDINAL}\s+{_MONTH_NAME},?\s+{_YEAR}\b", blob, re.I):
        iso = _iso(int(m.group(3)), _MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
        if iso:
            return iso, "day", "publisher"
    m = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])[-_/](0[1-9]|[12]\d|3[01])", blob)
    if m:
        iso = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            return iso, "day", "publisher"
    # Byline dates such as Bleecker Street's "Chris Drose 1/17/24" (published
    # and title only: URL paths are full of slashes and numbers).
    m = re.search(r"(?<![\d/])(1[0-2]|0?[1-9])/(3[01]|[12]\d|0?[1-9])/(20\d{2}|\d{2})(?![\d/])", text)
    if m:
        year = int(m.group(3))
        year = year + 2000 if year < 100 else year
        iso = _iso(year, int(m.group(1)), int(m.group(2)))
        if iso:
            return iso, "day", "publisher"
    m = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])(?:[^0-9]|$)", blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01", "month", "publisher"
    return None, "unknown", None


_PAGE_DATE_PATTERNS = (
    re.compile(
        r"<meta[^>]+property=[\"']article:published_time[\"'][^>]+content=[\"'](\d{4}-\d{2}-\d{2})",
        re.I,
    ),
    re.compile(
        r"<meta[^>]+content=[\"'](\d{4}-\d{2}-\d{2})[^\"']*[\"'][^>]+property=[\"']article:published_time",
        re.I,
    ),
    re.compile(r"\"datePublished\"\s*:\s*\"(\d{4}-\d{2}-\d{2})"),
)


def _date_from_page(path: Path) -> str | None:
    """article:published_time / JSON-LD datePublished from a downloaded HTML page."""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:300_000]
    except OSError:
        return None
    for pattern in _PAGE_DATE_PATTERNS:
        m = pattern.search(head)
        if m:
            year, month, day = (int(part) for part in m.group(1).split("-"))
            iso = _iso(year, month, day)
            if iso:
                return iso
    return None


def _page_position(path: Path) -> str | None:
    try:
        return parse_position_marker(path.read_text(encoding="utf-8", errors="ignore")[:300_000])
    except OSError:
        return None


_HASH_LETTERS = str.maketrans("0123456789", "ghijklmnop")


def _dest_name(firm_id: str, url: str, report_date: str | None, ext: str) -> str:
    """Canonical file name. Undated links are named "undated" plus a URL hash.

    They used to be stamped with the fetch date, so every daily run wrote a new
    file and (because report_key included the file) a new index row: Bleecker
    Street ended up with 11 rows per report and Scorpion with 16 copies of
    IONQ.pdf.
    """
    stem = Path(urlparse(url).path).stem[:40]
    if report_date:
        return safe_report_filename(firm_id, report_date[:10], stem, ext)
    # Letters only: build_activist_feed and activist_date_parse read dates out
    # of file stems, and a hex hash such as "ab201934" would read as 2019.
    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8].translate(_HASH_LETTERS)
    return safe_report_filename(firm_id, "undated", f"{stem}-{url_hash}", ext)


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
        dest_name = _dest_name(firm_id, url, report_date, ext)
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

        page_exists = ext == ".html" and dest.exists()
        if not report_date and page_exists:
            page_date = _date_from_page(dest)
            if page_date:
                report_date, date_precision, date_source = page_date, "day", "page_meta"

        title_l = (link.get("title") or "").lower()
        link_side = side
        if firm.get("side") == "both" and any(
            tok in title_l for tok in ("letter to", "open letter", "board of directors", "nominat")
        ):
            link_side = "long"
        # A page that states its own side outranks the firm default: Spruce
        # Point is a short seller, but its Henry Schein page says
        # "Position: Long".
        position = link.get("position") or (_page_position(dest) if page_exists else None)
        if position in ("long", "short"):
            link_side = position
        filing_class = "publisher_report"
        if any(tok in title_l for tok in ("open letter", "letter to the board", "letter to board")):
            filing_class = "open_letter"
        elif "presentation" in title_l and any(tok in title_l for tok in ("board", "shareholder", "investor")):
            filing_class = "campaign_presentation"

        # Spruce Point cards print "NASDAQ: HSIC" beside the headline; it is
        # the strongest evidence on the page, so it joins the match text
        # (but not the stored title).
        ticker_hint = link.get("ticker_hint") or ""
        match_title = f"{link['title']} ({ticker_hint})" if ticker_hint else link["title"]
        for ticker in tickers:
            meta = ticker_meta(ticker)
            blob = f"{match_title} {link['url']}"
            ok, confidence, reason = publisher_match_allowed(url, match_title, blob, meta)
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
            if ticker_hint:
                entry["ticker_hint"] = ticker_hint
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
