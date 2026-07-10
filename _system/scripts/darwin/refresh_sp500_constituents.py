#!/usr/bin/env python3
"""Fetch / normalize S&P 500 constituents for Darwin universe filter.

Usage:
  python _system/scripts/darwin/refresh_sp500_constituents.py
  python _system/scripts/darwin/refresh_sp500_constituents.py --offline  # keep existing file
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _normalize_ticker(raw: str) -> str:
    t = (raw or "").strip().upper()
    t = t.replace("\xa0", "").replace("&AMP;", "&")
    # Wikipedia uses BRK.B; Yahoo often BRK-B — keep both forms via alias set later
    return t


def fetch_wikipedia_constituents() -> list[dict]:
    req = urllib.request.Request(
        WIKI_URL,
        headers={"User-Agent": "MarvinDarwin/1.0 (research dashboard; local refresh)"},
    )
    html = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
    m = re.search(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        html,
        re.S | re.I,
    )
    if not m:
        raise RuntimeError("Could not find S&P 500 wikitable")
    body = m.group(1)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S | re.I)
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        if len(cells) < 2:
            continue

        def _cell_text(c: str) -> str:
            c = re.sub(r"<[^>]+>", "", c)
            c = re.sub(r"&#\d+;", "", c)
            return c.replace("&amp;", "&").replace("\n", " ").strip()

        sym = _normalize_ticker(_cell_text(cells[0]))
        company = _cell_text(cells[1])
        if not sym or not re.match(r"^[A-Z][A-Z0-9.\-]{0,7}$", sym):
            continue
        if sym in seen:
            continue
        seen.add(sym)
        out.append({"ticker": sym, "company": company or sym})
    if len(out) < 400:
        raise RuntimeError(f"Unexpectedly few tickers ({len(out)}); aborting write")
    return out


def fetch_wikipedia_tickers() -> list[str]:
    return [r["ticker"] for r in fetch_wikipedia_constituents()]


def registry_overlap(tickers: list[str]) -> tuple[list[str], int]:
    if not REGISTRY_PATH.exists():
        return [], 0
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    holdings = set((reg.get("holdings") or {}).keys())
    # Alias BRK.B <-> BRK-B etc.
    spx: set[str] = set()
    for t in tickers:
        spx.add(t)
        if "." in t:
            spx.add(t.replace(".", "-"))
        if "-" in t:
            spx.add(t.replace("-", "."))
    overlap = sorted(h for h in holdings if h.upper() in spx or h in spx)
    return overlap, len(holdings)


def write_constituents(rows: list[dict], source: str) -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tickers = [r["ticker"] for r in rows]
    companies = {r["ticker"]: r["company"] for r in rows}
    payload = {
        "as_of": date.today().isoformat(),
        "source": source,
        "count": len(tickers),
        "tickers": tickers,
        "companies": companies,
        "rows": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return OUT_PATH


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Do not fetch; print overlap for existing file",
    )
    args = ap.parse_args()

    if args.offline:
        if not OUT_PATH.exists():
            print(f"Missing {OUT_PATH}", file=sys.stderr)
            return 1
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        tickers = data.get("tickers") or []
        source = data.get("source", "existing")
    else:
        rows = fetch_wikipedia_constituents()
        source = "wikipedia_list_of_sp500_companies"
        write_constituents(rows, source)
        tickers = [r["ticker"] for r in rows]

    overlap, n_hold = registry_overlap(tickers)
    print(f"Wrote/loaded {len(tickers)} S&P 500 tickers ({source})")
    print(f"Path: {OUT_PATH}")
    print(f"Registry holdings: {n_hold} · overlap: {len(overlap)}")
    if overlap:
        print("Overlap sample:", ", ".join(overlap[:25]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
