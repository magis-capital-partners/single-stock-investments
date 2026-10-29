"""Bounded EDGAR disclosure fetch using the repository's polite SEC client."""
from __future__ import annotations

import html
import re
from datetime import date, timedelta
from urllib.parse import quote

from sec_client import SecClient


def html_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " | ", raw)
    return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).replace("\xa0", " ")


def recent_exhibits(cik: int, *, forms=("8-K",), item: str | None = None,
                    days: int = 120, limit: int = 6):
    """Yield one source per document; never join unrelated exhibits under one URL."""
    client = SecClient(max_attempts=2)
    data = client.get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", timeout=30)
    columns = (data.get("filings") or {}).get("recent") or {}
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = [dict(zip(columns, values)) for values in zip(*columns.values())]
    selected = [r for r in rows if r.get("form") in forms and r.get("filingDate", "") >= cutoff
                and (not item or item in r.get("items", ""))]
    for row in sorted(selected, key=lambda r: r["filingDate"], reverse=True)[:limit]:
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{row['accessionNumber'].replace('-', '')}/"
        index = client.get_json(base + "index.json", timeout=30)
        docs = [r["name"] for r in index.get("directory", {}).get("item", [])
                if re.search(r"exx?-?99|exhibit99|dex99|earnings|release", r["name"], re.I)
                and r["name"].lower().endswith((".htm", ".html", ".txt"))]
        if not docs and row.get("primaryDocument"):
            docs = [row["primaryDocument"]]
        for name in docs[:2]:
            url = base + quote(name)
            yield row, html_text(client.get_bytes(url, timeout=30).decode("utf-8", "replace")), url
