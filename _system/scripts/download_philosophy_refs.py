#!/usr/bin/env python3
"""Download Popper / Deutsch reference PDFs into _system/reference/philosophy/deutsch-popper/."""
from __future__ import annotations

import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "_system/reference/philosophy/deutsch-popper"
URLS_FILE = DEST / "_pdf_urls.txt"
LOG = DEST / "_download_log.txt"
UA = "Mozilla/5.0 MarvinPortfolioDocs/1.0 (philosophy reference library)"


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_urls() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for raw in URLS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            url, name = line.split("|", 1)
        else:
            url, name = line, Path(line).name
        entries.append((url.strip(), name.strip()))
    return entries


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)
    log(f"OK {dest.name} ({len(data)} bytes) <- {url}")


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    for url, name in parse_urls():
        dest = DEST / name
        if dest.exists() and dest.stat().st_size > 1000:
            log(f"SKIP exists {name}")
            ok += 1
            continue
        try:
            download(url, dest)
            ok += 1
            time.sleep(0.5)
        except Exception as e:
            log(f"FAIL {name} <- {url} :: {e}")
            fail += 1
    log(f"DONE ok={ok} fail={fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
