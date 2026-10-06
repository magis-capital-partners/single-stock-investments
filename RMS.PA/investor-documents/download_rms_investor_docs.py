#!/usr/bin/env python3
"""Download Hermès International (RMS.PA) regulated filings from finance.hermes.com."""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[2]
TICKER = "RMS.PA"
IR_DIR = Path(__file__).resolve().parent / "ir-hermes"
LOG_FILE = ROOT / TICKER / "_download_log.txt"
INDEX = ROOT / TICKER / "document-index.csv"
UA = "Marvin Research single-stock-investments (contact: portfolio@local)"
PAGES = (
    "https://finance.hermes.com/en/regulated-information/",
    "https://finance.hermes.com/en/financial-publications/",
)
KEEP = re.compile(
    r"urd|rfs|result|sales|revenue|chiffre|semestr|half-year|half_year|annual",
    re.I,
)
DROP = re.compile(r"voting|liquidity|nombre-de-droits|sharecapital", re.I)
YEAR = re.compile(r"202[4-6]")


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def discover() -> list[str]:
    found: list[str] = []
    for page in PAGES:
        try:
            html = fetch(page).decode("utf-8", "replace")
        except Exception as exc:
            log(f"FAIL list {page} -> {exc}")
            continue
        for href in re.findall(r'href="([^"]+)"', html):
            if ".pdf" not in href.lower():
                continue
            absolute = urljoin(page, href.split("?")[0])
            if DROP.search(absolute):
                continue
            if not KEEP.search(absolute):
                continue
            if not YEAR.search(absolute):
                continue
            if re.search(r"(_fr|fr\.pdf|-fr\.|-fr_)", absolute, re.I):
                continue
            if absolute not in found:
                found.append(absolute)
    if not any("urd2025" in url for url in found):
        found.append(
            "https://assets-finance.hermes.com/s3fs-public/node/pdf_file/2026-04/1777391712/260320_hermes_urd2025_en.pdf"
        )
    if not any("rfs" in url for url in found):
        found.append(
            "https://assets-finance.hermes.com/s3fs-public/node/pdf_file/2026-09/1789652378/hermes_20260729_rfs_en_eaccessible.pdf"
        )
    return found


def local_name(url: str) -> tuple[str, str, str]:
    leaf = url.rstrip("/").split("/")[-1]
    low = leaf.lower()
    if "availability" in low:
        return "earnings_urd_availability_2025.pdf", "Availability of the 2025 universal registration document", "earnings"
    if "urd" in low:
        year = "2025" if "2025" in low or "260320" in low else "2024" if "2024" in low else "annual"
        return f"annual_urd_{year}.pdf", f"Universal registration document {year}", "annual"
    if "rfs" in low or "half" in low or "semestr" in low:
        return "quarterly_half_year_report_2026.pdf", "2026 half-year financial report", "quarterly"
    if "result" in low or "sales" in low or "revenue" in low or "chiffre" in low:
        stamp = re.search(r"(20\d{6})", low)
        tag = stamp.group(1) if stamp else "release"
        return f"earnings_release_{tag}.pdf", f"Results release {tag}", "earnings"
    safe = re.sub(r"[^\w.\-]", "_", leaf)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    return safe, leaf, "other"


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        with dest.open("rb") as handle:
            if handle.read(5) == b"%PDF-":
                log(f"SKIP exists -> {dest.name}")
                return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    try:
        data = fetch(url)
    except Exception as exc:
        log(f"FAIL {url} -> {exc}")
        return False
    if len(data) < 1000 or not data.startswith(b"%PDF-"):
        log(f"FAIL {url} -> not a PDF ({len(data)} bytes)")
        return False
    tmp.write_bytes(data)
    tmp.replace(dest)
    log(f"OK {dest.stat().st_size:,} bytes -> {dest.name}")
    return True


def main() -> None:
    log("Starting RMS.PA Hermès IR download")
    IR_DIR.mkdir(parents=True, exist_ok=True)
    urls = discover()
    log(f"Discovered {len(urls)} candidate PDFs")
    rows: list[dict] = []
    ok_count = 0
    used: set[str] = set()
    for url in urls:
        filename, title, kind = local_name(url)
        if filename in used:
            stem = filename[:-4]
            filename = f"{stem}_{len(used)}.pdf"
        used.add(filename)
        dest = IR_DIR / filename
        time.sleep(0.25)
        ok = download(url, dest)
        if ok:
            ok_count += 1
        filed = ""
        match = re.search(r"(20\d{2})-(\d{2})", url)
        if match:
            filed = f"{match.group(1)}-{match.group(2)}-01"
        rows.append(
            {
                "path": str(dest.relative_to(ROOT / TICKER)).replace("\\", "/"),
                "title": title,
                "date": filed,
                "type": kind,
                "url": url,
                "ok": ok,
            }
        )
    INDEX.write_text("path,title,date,type\n", encoding="utf-8")
    with INDEX.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            if row["ok"]:
                writer.writerow([row["path"], row["title"], row["date"], row["type"]])
    manifest = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    manifest.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    log(f"Done RMS.PA. IR={ok_count}/{len(urls)}")


if __name__ == "__main__":
    main()
