#!/usr/bin/env python3
"""Download Schneider Electric (SU.PA) investor documents from canonical IR URLs."""
from __future__ import annotations

import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKER = "SU.PA"
IR_DIR = Path(__file__).resolve().parent / "ir-schneider"
LOG_FILE = ROOT / TICKER / "_download_log.txt"
INDEX = ROOT / TICKER / "document-index.csv"
UA = "Marvin Research single-stock-investments (contact: portfolio@local)"

# Euronext Paris: SU, ISIN FR0000121972. Q3 2026 revenues are scheduled 2026-10-16.
PDFS = [
    (
        "annual_urd_2025.pdf",
        "2025 Universal Registration Document",
        "2026-03-27",
        "annual",
        "https://download.se.com/files?p_Doc_Ref=2025-URD",
    ),
    (
        "annual_urd_2024.pdf",
        "2024 Universal Registration Document",
        "2025-03-26",
        "annual",
        "https://download.se.com/files?p_Doc_Ref=2024-URD",
    ),
    (
        "quarterly_half_year_accounts_2026.pdf",
        "2026 half-year financial report",
        "2026-07-30",
        "quarterly",
        "https://www.se.com/ww/en/assets/pdf/accounts-hy-results-2026",
    ),
    (
        "earnings_release_h1_2026.pdf",
        "2026 half-year results release",
        "2026-07-30",
        "earnings",
        "https://www.se.com/ww/en/assets/pdf/release-hy-results-2026",
    ),
    (
        "presentation_h1_2026.pdf",
        "2026 half-year results presentation",
        "2026-07-30",
        "presentation",
        "https://download.se.com/files?p_Doc_Ref=presentation-hy-results-2026",
    ),
    (
        "transcript_h1_2026.pdf",
        "2026 half-year results transcript",
        "2026-07-30",
        "transcript",
        "https://www.se.com/ww/en/assets/pdf/transcript-hy-results-2026",
    ),
    (
        "earnings_release_q1_2026.pdf",
        "Q1 2026 revenue release",
        "2026-04-30",
        "earnings",
        "https://www.se.com/ww/en/assets/pdf/release-q1-revenues-2026",
    ),
    (
        "presentation_q1_2026.pdf",
        "Q1 2026 revenue presentation",
        "2026-04-30",
        "presentation",
        "https://www.se.com/ww/en/assets/pdf/presentation-q1-revenues-2026",
    ),
    (
        "transcript_q1_2026.pdf",
        "Q1 2026 results transcript",
        "2026-04-30",
        "transcript",
        "https://www.se.com/ww/en/assets/pdf/transcript-Q1-results-2026",
    ),
]


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        with dest.open("rb") as handle:
            if handle.read(5) == b"%PDF-":
                log(f"SKIP exists -> {dest.name}")
                return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        log(f"FAIL {url} -> {exc}")
        return False
    if tmp.stat().st_size < 1000:
        tmp.unlink(missing_ok=True)
        log(f"FAIL {url} -> file too small")
        return False
    with tmp.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            tmp.unlink(missing_ok=True)
            log(f"FAIL {url} -> not a PDF")
            return False
    tmp.replace(dest)
    log(f"OK {dest.stat().st_size:,} bytes -> {dest.name}")
    return True


def main() -> None:
    log("Starting SU.PA Schneider Electric IR download")
    IR_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    ok_count = 0
    for filename, title, filed, kind, url in PDFS:
        dest = IR_DIR / filename
        time.sleep(0.3)
        ok = download(url, dest)
        if ok:
            ok_count += 1
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
    log(f"Done SU.PA. IR={ok_count}/{len(PDFS)}")


if __name__ == "__main__":
    main()
