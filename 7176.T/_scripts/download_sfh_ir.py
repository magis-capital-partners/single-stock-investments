#!/usr/bin/env python3
"""Download 7176.T IR PDFs from simplexasset.com/sfh/ XML feeds."""
from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "_download_log.txt"
URLS_FILE = ROOT / "_pdf_urls.txt"

FEEDS = (
    ("financial_results", "http://www.simplexasset.com/sfh/financial_results/feed.xml"),
    ("ir_information", "http://www.simplexasset.com/sfh/ir_information/feed.xml"),
    ("shareholders_meeting_notice", "http://www.simplexasset.com/sfh/shareholders_meeting_notice/feed.xml"),
)

UA = "MarvinResearch/1.0 (7176.T IR harvest; contact: research@local)"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip())


def dest_folder(section: str, title: str, filename: str) -> Path:
    t = title or ""
    f = filename.lower()
    if section == "financial_results" or "決算公告" in t:
        return ROOT / "02_Quarterly" / "Financial_Announcements"
    if section == "shareholders_meeting_notice" or "株主総会" in t:
        return ROOT / "03_Events" / "Shareholder_Meeting"
    if "コーポレート・ガバナンス" in t or "ガバナンス報告書" in t:
        return ROOT / "01_Official" / "Governance"
    if "発行者情報" in t:
        return ROOT / "01_Official" / "Issuer_Information"
    if "中間決算短信" in t or f.endswith("m.pdf") or "finfo" in f and "m.pdf" in f:
        return ROOT / "02_Quarterly" / "Interim_Earnings"
    if "決算短信" in t or re.match(r"finfo\d{4}\.pdf", f):
        return ROOT / "02_Quarterly" / "Earnings_Releases"
    if "差異" in t or f.startswith("pnotice"):
        return ROOT / "02_Quarterly" / "Earnings_Variance_Notices"
    return ROOT / "03_Events" / "Timely_Disclosures"


def safe_name(title: str, url: str, year: str, month: str, day: str) -> str:
    base = Path(url.split("?")[0]).name
    slug = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff\-]+", "_", (title or base))[:80].strip("_")
    if not slug:
        slug = base
    prefix = f"{year}{month.zfill(2)}{day.zfill(2)}_" if year else ""
    if not base.lower().endswith(".pdf"):
        base = base + ".pdf"
    return f"{prefix}{slug}__{base}"


def parse_feed(section: str, feed_url: str) -> list[tuple[str, str, str, str, str, str]]:
    req = urllib.request.Request(feed_url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=60).read()
    root = ET.fromstring(data)
    base = feed_url.rsplit("/", 1)[0] + "/"
    out: list[tuple[str, str, str, str, str, str]] = []
    for art in root.findall("article"):
        link = (art.findtext("linkUrl") or "").strip()
        if not link:
            continue
        title = (art.findtext("title") or "").strip()
        year = (art.findtext("year") or "").strip()
        month = (art.findtext("month") or "").strip()
        day = (art.findtext("day") or "").strip()
        url = link if link.startswith("http") else base + link.lstrip("/")
        out.append((section, title, url, year, month, day))
    return out


def download_one(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        log(f"SKIP exists -> {dest.relative_to(ROOT)}")
        return True
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
        if len(body) < 500:
            log(f"FAIL small body ({len(body)} B) {url}")
            return False
        dest.write_bytes(body)
        log(f"OK {len(body)} B -> {dest.relative_to(ROOT)}")
        return True
    except urllib.error.HTTPError as e:
        log(f"FAIL HTTP {e.code} {url}")
        return False
    except Exception as e:
        log(f"FAIL {e} {url}")
        return False


def main() -> int:
    entries = []
    for section, feed_url in FEEDS:
        entries.extend(parse_feed(section, feed_url))

    seen: set[str] = set()
    unique = []
    for row in entries:
        if row[2] not in seen:
            seen.add(row[2])
            unique.append(row)

    log(f"START harvest {len(unique)} PDFs from simplexasset.com/sfh/")

    ok = fail = 0
    url_lines = ["# IR PDF URLs for 7176.T (simplexasset.com/sfh feeds)", f"# Generated {datetime.now(timezone.utc).isoformat()}", ""]
    for section, title, url, year, month, day in unique:
        folder = dest_folder(section, title, Path(url).name)
        fname = safe_name(title, url, year, month, day)
        dest = folder / fname
        url_lines.append(url)
        if download_one(url, dest):
            ok += 1
        else:
            fail += 1
        time.sleep(0.15)

    URLS_FILE.write_text("\n".join(url_lines) + "\n", encoding="utf-8")
    log(f"DONE ok={ok} fail={fail} urls={len(unique)}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
