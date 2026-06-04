#!/usr/bin/env python3
"""Download IDA.AX IR PDFs from Indiana Resources website (ASX: IDA)."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[2]
PRES = ROOT / "IDA.AX" / "investor-documents" / "presentations"
ASX_DIR = ROOT / "IDA.AX" / "investor-documents" / "asx-announcements"
LOG_FILE = ROOT / "IDA.AX" / "_download_log.txt"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
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
        time.sleep(0.3)
    return [(label, url) for url, label in sorted(found.items())]


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 3000:
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
    if len(data) < 3000 or data[:4] != b"%PDF":
        log(f"FAIL not PDF ({len(data)} bytes) -> {dest.name}")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.relative_to(ROOT)}")
    return True


def main() -> int:
    log("Starting IDA.AX IR download (ASX)")
    manifest: list[dict] = []
    ok_count = 0
    targets: list[tuple[str, str, Path]] = list(KNOWN_PDFS)
    for label, url in discover_pdf_urls():
        if any(url == t[1] for t in targets):
            continue
        safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
        targets.append((label, url, ASX_DIR if "announce" in label.lower() else PRES))

    for label, url, out_dir in targets:
        safe = re.sub(r"[^\w.\-]", "_", label) + ".pdf"
        dest = out_dir / safe
        time.sleep(0.3)
        ok = download(url, dest)
        if ok:
            ok_count += 1
        manifest.append(
            {"label": label, "url": url, "local": str(dest.relative_to(ROOT)), "ok": ok}
        )

    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"Done IDA.AX. downloaded={ok_count}/{len(targets)}")
    log(
        "NOTE: Full ASX announcement archive on Weblink may need Vicki/browser "
        "[HUMAN REVIEW] — see research/shopbot/"
    )
    return 0 if ok_count >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
