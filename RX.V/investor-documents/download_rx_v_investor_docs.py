#!/usr/bin/env python3
"""Fetch BioSyent (TSXV: RX / registry RX.V) investor PDFs.

Does not use the Constellation Software downloader. Official biosyent.com
files are often behind a Cloudflare challenge. Each attempt is appended to
RX.V/_download_log.txt. Existing PDFs are not deleted.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).resolve().parent
LOG = ROOT / "RX.V" / "_download_log.txt"
UA = "Marvin research single-stock-investments (RX.V BioSyent; contact: research)"

FILES = [
    (
        "https://www.biosyent.com/wp-content/uploads/2026/04/2025-BioSyent-AR_web-FINAL.pdf",
        DEST / "annual-reports" / "2025-BioSyent-AR.pdf",
    ),
    (
        "https://www.biosyent.com/wp-content/uploads/2026/08/2026-BioSyent-Q2-Financials-FINAL.pdf",
        DEST / "interim" / "2026-Q2-financials.pdf",
    ),
    (
        "https://www.biosyent.com/wp-content/uploads/2026/08/2026-BioSyent-Q2-MDA-FINAL.pdf",
        DEST / "interim" / "2026-Q2-mda-official.pdf",
    ),
    (
        "https://www.biosyent.com/wp-content/uploads/2026/08/PR-2026-08-20-Q2-Earnings-Release-FINAL-v3.pdf",
        DEST / "press" / "2026-08-20-q2-earnings.pdf",
    ),
    (
        "https://newsfile.futunn.com/public/NN-PersistNoticeAttachment/7781/20260821/SEDAR_PLUS/CSA_SEDAR_PLUS_NOTICE_RECORD_ID_2483060.pdf",
        DEST / "interim" / "2026-Q2-mda.pdf",
    ),
]


def log(line: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {line}\n")


def fetch(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.biosyent.com/investors/"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        log(f"FAIL {exc.code} {url}")
        return
    except urllib.error.URLError as exc:
        log(f"FAIL {exc.reason} {url}")
        return
    if not body.startswith(b"%PDF"):
        log(f"FAIL not-pdf status={status} bytes={len(body)} {url}")
        return
    if path.exists() and path.read_bytes() == body:
        log(f"UNCHANGED {path.relative_to(ROOT)} bytes={len(body)}")
        return
    path.write_bytes(body)
    log(f"SAVED {path.relative_to(ROOT)} bytes={len(body)} {url}")


def main() -> None:
    log("START RX.V BioSyent investor PDF fetch")
    for url, path in FILES:
        fetch(url, path)
    log("END RX.V BioSyent investor PDF fetch")


if __name__ == "__main__":
    main()
