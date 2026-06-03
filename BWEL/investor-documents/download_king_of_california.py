#!/usr/bin/env python3
"""Fetch or register *The King of California* (Arax & Wartzman, 2003) for BWEL research-notes.

Internet Archive often returns HTTP 401 for unattended PDF pulls (borrow-only).
If auto-download fails, borrow at https://archive.org/details/kingofcalifornia0000arax_z8i9
and save the PDF to TARGET_NAME below, then re-run this script to verify and log.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

TICKER_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = TICKER_DIR / "investor-documents" / "research-notes"
TARGET_NAME = "Arax_Wartzman_2003_The_King_of_California.pdf"
ARCHIVE_URL = (
    "https://archive.org/download/kingofcalifornia0000arax_z8i9/"
    "kingofcalifornia0000arax_z8i9.pdf"
)
LOG = TICKER_DIR / "_download_log.txt"


def log(msg: str) -> None:
    line = f"{__import__('datetime').datetime.utcnow().isoformat()}Z | king_of_california | {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(msg)


def is_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 100_000:
        return False
    with path.open("rb") as f:
        return f.read(5) == b"%PDF-"


def try_download(dest: Path) -> bool:
    req = Request(
        ARCHIVE_URL,
        headers={"User-Agent": "MarvinBWEL/1.0 (+https://github.com/GoldmanDrew/single-stock-investments)"},
    )
    try:
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        log(f"download failed: {e}")
        return False
    if len(data) < 100_000 or not data.startswith(b"%PDF-"):
        log(f"download rejected or non-PDF ({len(data)} bytes)")
        return False
    dest.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()[:16]
    log(f"saved {dest.name} ({len(data)} bytes) sha256={digest}")
    return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / TARGET_NAME
    if is_pdf(dest):
        log(f"already present: {dest} ({dest.stat().st_size} bytes)")
        return 0
    if try_download(dest):
        return 0
    log(
        "MANUAL: Borrow or purchase the book, then place PDF at "
        f"{dest} and re-run this script."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
