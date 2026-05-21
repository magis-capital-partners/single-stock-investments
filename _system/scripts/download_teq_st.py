#!/usr/bin/env python3
"""Download TEQ.ST PDFs from document-index.csv (beQuoted sources)."""
from __future__ import annotations

import csv
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKER = ROOT / "TEQ.ST"
INDEX = TICKER / "document-index.csv"
LOG = TICKER / "_download_log.txt"
UA = "Mozilla/5.0 MarvinPortfolioDocs/1.0"
SLEEP = 0.15


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    log("Starting TEQ.ST download from document-index.csv")
    ok = skip = fail = 0
    with INDEX.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("Source") or "").strip()
            rel = (row.get("File") or "").strip()
            if not url or not rel:
                continue
            dest = TICKER / rel.replace("\\", "/")
            if dest.exists() and dest.stat().st_size > 0:
                skip += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                dest.write_bytes(data)
                ok += 1
                log(f"OK {len(data):,} -> {dest.name}")
            except Exception as e:
                fail += 1
                log(f"FAIL {url} -> {e}")
            time.sleep(SLEEP)
    log(f"Done TEQ.ST downloaded={ok} skipped={skip} failed={fail}")


if __name__ == "__main__":
    main()
