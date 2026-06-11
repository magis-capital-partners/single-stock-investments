#!/usr/bin/env python3
"""Download TASE investor documents from Maya (Israel exchange disclosure system)."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANNUAL_DIR = ROOT / "TASE" / "official-reports" / "annual-reports"
PRES_DIR = ROOT / "TASE" / "presentations-and-media"
LOG_FILE = ROOT / "TASE" / "_download_log.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarvinPortfolioDocs/1.0"
MAYA_BASE = "https://maya.tase.co.il"

# FY2024 results + presentation (from PR Newswire 2025-03-04 links)
REPORT_IDS = [
    (1649220, "fy2024_financial_statements", ANNUAL_DIR),
    (1649225, "fy2024_investor_presentation", PRES_DIR),
]


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_report(report_id: int) -> dict:
    url = f"{MAYA_BASE}/api/v1/reports/{report_id}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def download_pdf(relative_url: str, dest: Path, report_id: int) -> bool:
    if dest.exists() and dest.stat().st_size > 5000 and dest.read_bytes()[:4] == b"%PDF":
        log(f"SKIP exists -> {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{MAYA_BASE}/{relative_url.lstrip('/')}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": f"{MAYA_BASE}/he/reports/{report_id}",
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        log(f"FAIL {url} -> {exc}")
        return False
    if len(data) < 5000 or data[:4] != b"%PDF":
        log(f"FAIL not PDF ({len(data)} bytes) -> {dest.name}")
        return False
    dest.write_bytes(data)
    log(f"OK {len(data):,} bytes -> {dest.relative_to(ROOT)}")
    return True


def main() -> int:
    log("Starting TASE Maya IR download")
    ok_count = 0
    manifest: list[dict] = []
    for report_id, label, out_dir in REPORT_IDS:
        time.sleep(0.3)
        try:
            meta = fetch_report(report_id)
        except Exception as exc:
            log(f"FAIL report {report_id} metadata -> {exc}")
            continue
        for att in meta.get("attachments") or []:
            if att.get("fileType", "").startswith("pdf"):
                fname = att.get("fileName") or f"{label}.pdf"
                safe = re.sub(r"[^\w.\-]", "_", label) + "_" + re.sub(r"[^\w.\-]", "_", fname)
                dest = out_dir / safe
                ok = download_pdf(att["url"], dest, report_id)
                if ok:
                    ok_count += 1
                manifest.append({"report_id": report_id, "label": label, "url": att["url"], "ok": ok})
    man_path = Path(__file__).resolve().parent / "DOWNLOAD_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Done TASE. downloaded={ok_count}")
    return 0 if ok_count >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
