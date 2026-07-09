#!/usr/bin/env python3
"""Locate Verdad Biotech Investing PDF URL from Squarespace page HTML."""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

UA = "MarvinResearch/1.0 (biotech-quant library; academic use)"
PAGE = "https://verdadcap.com/archive/biotech-investing"


def main() -> int:
    req = urllib.request.Request(PAGE, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    out = Path(__file__).with_name("_page_snapshot.html")
    out.write_text(html, encoding="utf-8")
    pdfs = sorted(set(re.findall(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]*)?", html, flags=re.I)))
    # Squarespace asset links sometimes omit .pdf in href but include in data attributes
    assets = sorted(
        set(
            re.findall(
                r"https?://(?:static1\.squarespace\.com|images\.squarespace-cdn\.com)[^\s\"'<>]+",
                html,
                flags=re.I,
            )
        )
    )
    button_hrefs = re.findall(
        r'class="[^"]*sqs-block-button-element[^"]*"[^>]*href="([^"]+)"',
        html,
        flags=re.I,
    )
    if not button_hrefs:
        button_hrefs = re.findall(
            r'href="([^"]+)"[^>]*class="[^"]*sqs-block-button-element',
            html,
            flags=re.I,
        )
    print("pdfs:", len(pdfs))
    for u in pdfs:
        print(" PDF", u)
    print("buttons:", button_hrefs[:10])
    print("assets_sample:", assets[:15])
    # Also search for 'BIOTECH' near href
    for m in re.finditer(r'href="([^"]+)"[^>]{0,200}BIOTECH|BIOTECH[^<]{0,80}href="([^"]+)"', html, re.I):
        print(" near:", m.group(1) or m.group(2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
