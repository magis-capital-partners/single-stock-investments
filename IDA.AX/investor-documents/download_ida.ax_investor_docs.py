#!/usr/bin/env python3
"""Download IDA.AX IR PDFs from Indiana Resources website and Weblink ASX archive."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[2]
PRES = ROOT / "IDA.AX" / "investor-documents" / "presentations"
ASX_DIR = ROOT / "IDA.AX" / "investor-documents" / "asx-announcements"
REPORTS = ROOT / "IDA.AX" / "investor-documents" / "official-reports"
LOG_FILE = ROOT / "IDA.AX" / "_download_log.txt"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
WEBLINK_BASE = "https://wcsecure.weblink.com.au/Clients/indianaresources/v2"
SEED_URLS = [
    "https://indianaresources.com.au/investors/",
    "https://indianaresources.com.au/",
    "https://indianaresources.com.au/news/",
]
KNOWN_PDFS = [
    (
        "company_profile_june_2025",
        "https://indianaresources.com.au/wp-content/uploads/2025/06/IDA-company-profile-2025-June-1.pdf",
        PRES,
    ),
]
REPORT_KEYWORDS = (
    "annual report",
    "half yearly report",
    "half-yearly report",
    "quarterly report",
    "appendix 4e",
    "appendix 4g",
    "corporate governance",
)
PRESENTATION_KEYWORDS = (
    "presentation",
    "investor day",
    "conference",
)


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def discover_pdf_urls() -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for page in SEED_URLS:
        try:
            html = fetch_html(page)
        except Exception as e:
            log(f"SKIP page {page}: {e}")
            continue
        for m in re.finditer(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.I):
            href = m.group(1).strip()
            if "webdemo.cc" in href:
                continue
            full = urljoin(page, href)
            if "indianaresources.com.au" not in urlparse(full).netloc:
                continue
            label = Path(urlparse(full).path).stem[:80] or "document"
            found[full] = label
        time.sleep(0.2)
    return [(label, url) for url, label in sorted(found.items())]


def parse_weblink_page(raw: str) -> tuple[list[dict], int]:
    m = re.search(r"wl_headlinesFunction\((.*)\)\s*$", raw.strip(), re.S)
    if not m:
        return [], 0
    blob = m.group(1)
    total_m = re.search(r'"totalHeadlines"\s*:\s*(\d+)', blob)
    total = int(total_m.group(1)) if total_m else 0
    headlines: list[dict] = []
    item_re = re.compile(
        r'\{"datetime":"([^"]+)","pdfLink":"([^"]+)","HeadlineText":"((?:\\.|[^"\\])*)"',
        re.S,
    )
    for dt, link, title in item_re.findall(blob):
        headlines.append(
            {
                "datetime": dt,
                "pdfLink": link.replace("\\/", "/"),
                "HeadlineText": title.encode("utf-8").decode("unicode_escape"),
            }
        )
    return headlines, total


def fetch_weblink_headlines(page_number: int, per_page: int = 100) -> tuple[list[dict], int]:
    url = (
        f"{WEBLINK_BASE}/HeadlineJsonP2.aspx"
        f"?numberHdPerPage={per_page}&pageNumber={page_number}&hdGroup=0"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return parse_weblink_page(raw)


def ms_to_date(ms_match: str) -> str:
    m = re.search(r"(\d+)", ms_match)
    if not m:
        return "unknown-date"
    dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def classify_out_dir(headline_text: str) -> Path:
    low = headline_text.lower()
    if any(k in low for k in REPORT_KEYWORDS):
        return REPORTS
    if any(k in low for k in PRESENTATION_KEYWORDS):
        return PRES
    return ASX_DIR


def safe_filename(date_str: str, headline_id: str, headline_text: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", headline_text.strip())[:70].strip("_")
    return f"{date_str}_{headline_id}_{slug}.pdf"


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        log(f"SKIP exists -> {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/pdf,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(f"FAIL {url} -> {e}")
        return False
    if len(data) < 1000 or data[:4] != b"%PDF":
        log(f"FAIL not PDF ({len(data)} bytes) -> {dest.name}")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.relative_to(ROOT)}")
    return True


def collect_weblink_announcements(per_page: int = 100) -> list[dict]:
    all_rows: list[dict] = []
    page = 1
    total = 0
    while True:
        headlines, total = fetch_weblink_headlines(page, per_page)
        if not headlines:
            break
        all_rows.extend(headlines)
        log(f"Weblink page {page}: {len(headlines)} headlines (total catalog {total})")
        if len(all_rows) >= total or len(headlines) < per_page:
            break
        page += 1
        time.sleep(0.25)
    return all_rows


def main() -> int:
    log("Starting IDA.AX IR download (website + Weblink ASX)")
    manifest: list[dict] = []
    ok_count = 0
    targets: list[tuple[str, str, Path]] = list(KNOWN_PDFS)

    for label, url in discover_pdf_urls():
        if any(url == t[1] for t in targets):
            continue
        targets.append((label, url, PRES))

    weblink_rows = collect_weblink_announcements()
    seen_ids: set[str] = set()
    for row in weblink_rows:
        hid_m = re.search(r"headlineid=(\d+)", row.get("pdfLink", ""), re.I)
        if not hid_m:
            continue
        hid = hid_m.group(1)
        if hid in seen_ids:
            continue
        seen_ids.add(hid)
        title = row.get("HeadlineText", "announcement")
        date_str = ms_to_date(row.get("datetime", ""))
        fname = safe_filename(date_str, hid, title)
        out_dir = classify_out_dir(title)
        pdf_url = row["pdfLink"]
        if not pdf_url.lower().startswith("http"):
            pdf_url = urljoin(WEBLINK_BASE + "/", pdf_url)
        targets.append((fname.replace(".pdf", ""), pdf_url, out_dir))

    log(f"Download queue: {len(targets)} files ({len(seen_ids)} Weblink + website)")

    jobs: list[tuple[str, str, Path, Path]] = []
    for label, url, out_dir in targets:
        safe = label if label.endswith(".pdf") else label + ".pdf"
        if not safe.endswith(".pdf"):
            safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
        dest = out_dir / safe
        jobs.append((label, url, dest, out_dir))

    def _job(item: tuple[str, str, Path, Path]) -> tuple[str, str, str, bool]:
        label, url, dest, _ = item
        return label, url, str(dest.relative_to(ROOT)), download(url, dest)

    workers = min(12, max(4, len(jobs) // 50))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, j): j for j in jobs}
        for fut in as_completed(futures):
            label, url, local, ok = fut.result()
            if ok:
                ok_count += 1
            manifest.append({"label": label, "url": url, "local": local, "ok": ok})

    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"Done IDA.AX. downloaded={ok_count}/{len(targets)}")
    return 0 if ok_count >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
