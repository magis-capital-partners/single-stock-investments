#!/usr/bin/env python3
"""Enrich S&P 500 constituents with company name + CIK from Wikipedia."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_constituents_enriched.json"
URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": "MarvinDarwin/1.0 (research; local)"})
    html = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
    m = re.search(r"<table[^>]*class=\"[^\"]*wikitable[^\"]*\"[^>]*>(.*?)</table>", html, re.S | re.I)
    if not m:
        raise SystemExit("wikitable not found")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S | re.I)
    out = []
    for row in rows[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        texts = [re.sub(r"<[^>]+>", "", c) for c in cells]
        texts = [re.sub(r"\s+", " ", t).replace("&amp;", "&").strip() for t in texts]
        if len(texts) < 2:
            continue
        sym = texts[0].upper()
        name = texts[1]
        cik = None
        for t in texts:
            if re.fullmatch(r"\d{10}", t):
                cik = t
                break
            if re.fullmatch(r"\d{6,10}", t):
                cik = t.zfill(10)
        out.append({"ticker": sym, "company": name, "cik": cik})
    payload = {
        "as_of": date.today().isoformat(),
        "source": "wikipedia_list_of_sp500_companies",
        "count": len(out),
        "constituents": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} count={len(out)} with_cik={sum(1 for x in out if x['cik'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
