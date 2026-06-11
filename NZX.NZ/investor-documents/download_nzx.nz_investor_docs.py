#!/usr/bin/env python3
"""Download NZX.NZ IR PDFs from NZX public announcement API."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "NZX.NZ" / "investor-documents" / "official-reports"
PRES = ROOT / "NZX.NZ" / "investor-documents" / "presentations"
ANN = ROOT / "NZX.NZ" / "investor-documents" / "nzx-announcements"
LOG_FILE = ROOT / "NZX.NZ" / "_download_log.txt"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Key announcements (id, slug hint)
SEED_ANNOUNCEMENTS = [
    ("468191", "FY2025_results_annual_report"),
    ("472052", "Q1_2026_revenue_metrics"),
    ("473842", "shareholder_metrics_may_2026"),
    ("471819", "quaystreet_externalisation"),
    ("472511", "equity_derivatives_launch"),
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


def discover_pdfs(announcement_id: str) -> list[tuple[str, str]]:
    page = f"https://www.nzx.com/announcements/{announcement_id}"
    html = fetch_html(page)
    links = re.findall(
        rf'href="(https://api\.nzx\.com/public/announcement/{announcement_id}/attachment/[^"]+\.pdf)"',
        html,
    )
    return [(announcement_id, url) for url in links]


def classify_dir(announcement_id: str) -> Path:
    if announcement_id == "468191":
        return REPORTS
    if announcement_id in {"472052", "473842", "471819", "472511"}:
        return ANN
    return ANN


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        log(f"SKIP exists -> {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
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


def main() -> int:
    log("Starting NZX.NZ IR download (NZX announcement API)")
    manifest: list[dict] = []
    ok = 0
    targets: list[tuple[str, str, Path]] = []

    for ann_id, slug in SEED_ANNOUNCEMENTS:
        try:
            pdfs = discover_pdfs(ann_id)
        except Exception as e:
            log(f"SKIP announcement {ann_id}: {e}")
            continue
        out_dir = classify_dir(ann_id)
        for i, (_, url) in enumerate(pdfs):
            name = url.split("/")[-1]
            dest = out_dir / f"{ann_id}_{slug}_{i+1}_{name}"
            targets.append((slug, url, dest))
        time.sleep(0.3)

    for slug, url, dest in targets:
        success = download(url, dest)
        if success:
            ok += 1
        manifest.append({"label": slug, "url": url, "local": str(dest.relative_to(ROOT)), "ok": success})

    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"Done NZX.NZ. downloaded={ok}/{len(targets)}")
    return 0 if ok >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
