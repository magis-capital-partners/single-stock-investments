#!/usr/bin/env python3
"""Harvest *The King of California* text for BWEL research-notes.

Internet Archive blocks unattended PDF/EPUB/djvu.txt (HTTP 401) on borrow-restricted
items. This script uses Open Library search-inside FTS (public snippets) and
optionally extracts full text from a locally placed PDF.

Usage:
  python3 BWEL/investor-documents/scrape_king_of_california.py
  python3 BWEL/investor-documents/scrape_king_of_california.py --pdf path/to/book.pdf
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

TICKER_DIR = Path(__file__).resolve().parents[1]
NOTES = TICKER_DIR / "investor-documents" / "research-notes"
OLID = "OL3689947M"
ARCHIVE_URL = "https://archive.org/details/kingofcalifornia0000arax"
DEFAULT_QUERIES = [
    "Boswell", "water", "Tulare", "Kern", "Kings County", "irrigation",
    "acre", "cotton", "San Joaquin", "groundwater", "rights", "Corcoran",
    "lake", "farm", "California", "empire", "family", "dam", "river",
    "pump", "district", "land", "million", "flood", "drainage", "Pima",
    "aquifer", "allotment", "reclamation", "fallow",
]


def page_num(fields: dict) -> int | None:
    pn = (fields or {}).get("page_num")
    if not pn or not isinstance(pn, list):
        return None
    inner = pn[0]
    if isinstance(inner, list) and inner:
        return int(inner[0])
    if isinstance(inner, (int, float)):
        return int(inner)
    return None


def fetch_ol(q: str, limit: int = 30) -> dict:
    url = (
        "https://openlibrary.org/search/inside.json?"
        + urllib.parse.urlencode({"q": q, "olid": OLID, "limit": limit})
    )
    req = urllib.request.Request(url, headers={"User-Agent": "MarvinBWEL/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def harvest_snippets(queries: list[str]) -> list[dict]:
    seen: set[tuple] = set()
    rows: list[dict] = []
    for q in queries:
        for attempt in range(3):
            try:
                data = fetch_ol(q)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"skip query {q!r}: {e}", file=sys.stderr)
                    data = {"hits": {"hits": []}}
                time.sleep(1.5 * (attempt + 1))
        for hit in data.get("hits", {}).get("hits", []):
            for t in (hit.get("highlight") or {}).get("text") or []:
                clean = re.sub(r"\{+\{?", "", t)
                clean = re.sub(r"\}+\}?", "", clean).strip()
                page = page_num(hit.get("fields") or {})
                key = (page, clean[:180])
                if len(clean) < 35 or key in seen:
                    continue
                seen.add(key)
                rows.append({"page": page, "query": q, "text": clean})
        print(f"{q}: cumulative {len(rows)}")
        time.sleep(0.35)
    rows.sort(key=lambda x: (x["page"] is None, x["page"] or 99999))
    return rows


def write_outputs(rows: list[dict]) -> None:
    NOTES.mkdir(parents=True, exist_ok=True)
    md = NOTES / "King_of_California_OL_search_excerpts.md"
    js = NOTES / "King_of_California_OL_search_excerpts.json"
    with md.open("w", encoding="utf-8") as f:
        f.write("# The King of California — Open Library search-inside excerpts\n\n")
        f.write(f"| Archive reader | {ARCHIVE_URL}/page/n5/mode/2up |\n")
        f.write(f"| Open Library ID | {OLID} |\n\n")
        f.write(
            "**Not a full book.** IA PDF/djvu.txt require borrow (401 from bots). "
            "Snippets from Open Library FTS for Marvin context only.\n\n"
        )
        f.write(f"**Excerpt count:** {len(rows)}\n\n---\n\n")
        for r in rows:
            f.write(f"## Page ~{r['page']} (search: {r['query']})\n\n{r['text']}\n\n")
    js.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"wrote {md} ({len(rows)} excerpts)")


def extract_pdf(pdf: Path) -> Path:
    try:
        import pypdf  # type: ignore
    except ImportError:
        print("pypdf not installed; pip install pypdf for --pdf", file=sys.stderr)
        return pdf
    out = NOTES / "King_of_California_pdf_extract.txt"
    reader = pypdf.PdfReader(str(pdf))
    parts = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        parts.append(f"\n\n--- page {i + 1} ---\n\n{text}")
    out.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {out} ({len(reader.pages)} pages)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, help="Local PDF after Archive borrow")
    ap.add_argument("--limit", type=int, default=30, help="OL hits per query")
    args = ap.parse_args()
    if args.pdf:
        extract_pdf(args.pdf)
    rows = harvest_snippets(DEFAULT_QUERIES)
    write_outputs(rows)
    log = TICKER_DIR / "_download_log.txt"
    with log.open("a", encoding="utf-8") as f:
        f.write(
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} | king_of_california | "
            f"OL search-inside harvest {len(rows)} excerpts\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
