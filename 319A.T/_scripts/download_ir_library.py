#!/usr/bin/env python3
"""Download Next Generation Technology Group (319A.T) IR PDFs from the company library."""
from __future__ import annotations

import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = "https://ngt-g.com/en/ir-library/"
UA = "Marvin Research single-stock-investments (contact: portfolio@local)"
SLEEP = 0.25


def dest_for(url: str, label: str) -> Path:
    name = url.rsplit("/", 1)[-1]
    blob = f"{label} {name}".lower()
    if "financial results" in blob or "決算" in blob:
        folder = ROOT / "02_Quarterly" / "Earnings"
    elif name.startswith("S100"):
        folder = ROOT / "01_Official" / "Securities_Reports"
    elif "timely" in blob or "disclosure" in blob:
        folder = ROOT / "03_Events" / "Timely_Disclosure"
    else:
        folder = ROOT / "06_References" / "IR_Materials"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def links() -> list[tuple[str, str]]:
    req = urllib.request.Request(LIBRARY, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", "replace")
    parts = re.split(
        r'(href="https://azcms\.ir-service\.net/DATA/319A/ir/[^"]+\.pdf")',
        html,
    )
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    i = 1
    while i < len(parts):
        match = re.search(
            r'https://azcms\.ir-service\.net/DATA/319A/ir/[^"]+\.pdf',
            parts[i],
        )
        prev = re.sub(r"<[^>]+>", " ", parts[i - 1])
        prev = re.sub(r"\s+", " ", prev)
        date = ""
        dates = re.findall(r"20\d{2}-\d{2}-\d{2}", prev)
        if dates:
            date = dates[-1]
        kind = "IR"
        for token in (
            "Securities Report",
            "Financial Results Summary",
            "Timely Disclosure",
            "IR Documents",
        ):
            if token in prev:
                kind = token
                break
        if match:
            url = match.group(0)
            if url not in seen:
                seen.add(url)
                found.append((url, f"{date} {kind}".strip()))
        i += 2
    return found


def main() -> int:
    rows = links()
    url_file = ROOT / "_pdf_urls.txt"
    log_file = ROOT / "_download_log.txt"
    url_file.write_text(
        "# IR PDF URLs for 319A.T harvested from https://ngt-g.com/en/ir-library/\n"
        + "\n".join(url for url, _ in rows)
        + "\n",
        encoding="utf-8",
    )
    ok = 0
    skipped = 0
    failed = 0
    lines = [
        f"{datetime.now(timezone.utc).isoformat()} harvest {len(rows)} urls from {LIBRARY}"
    ]
    for url, label in rows:
        target = dest_for(url, label)
        if target.exists() and target.stat().st_size > 1000:
            skipped += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
            if not data.startswith(b"%PDF"):
                failed += 1
                lines.append(f"FAIL not-pdf {url}")
                continue
            target.write_bytes(data)
            ok += 1
            lines.append(f"OK {target.relative_to(ROOT)} {len(data)} {label}")
        except Exception as exc:
            failed += 1
            lines.append(f"FAIL {url} {type(exc).__name__}: {exc}")
        time.sleep(SLEEP)
    lines.append(f"done ok={ok} skipped={skipped} failed={failed}")
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("\n".join(lines[-8:]))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
