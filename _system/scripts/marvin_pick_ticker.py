#!/usr/bin/env python3
"""Pick the next ticker for Marvin's daily deep dive."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"_system", "dashboard", ".git", ".github", ".cursor"}
DATE_RE = re.compile(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$")


def list_tickers() -> list[str]:
    tickers = []
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in SKIP and not p.name.startswith("."):
            tickers.append(p.name)
    return sorted(tickers)


def latest_deep_dive_date(ticker: str) -> datetime | None:
    research = ROOT / ticker / "research"
    if not research.is_dir():
        return None
    dates: list[datetime] = []
    for path in research.glob("deep_dive_*.md"):
        m = DATE_RE.search(path.name)
        if m:
            dates.append(datetime.strptime(m.group(1), "%Y-%m-%d"))
        else:
            dates.append(datetime.fromtimestamp(path.stat().st_mtime))
    return max(dates) if dates else None


def pick_ticker(explicit: str | None = None) -> str:
    if explicit:
        explicit = explicit.strip()
        if explicit not in list_tickers():
            raise SystemExit(f"Unknown ticker: {explicit}")
        return explicit

    ranked: list[tuple[int, datetime, str]] = []
    for ticker in list_tickers():
        last = latest_deep_dive_date(ticker)
        if last is None:
            ranked.append((0, datetime.min, ticker))
        else:
            ranked.append((1, last, ticker))

    ranked.sort(key=lambda x: (x[0], x[1], x[2]))
    return ranked[0][2]


def main() -> None:
    explicit = sys.argv[1] if len(sys.argv) > 1 else None
    ticker = pick_ticker(explicit)
    print(ticker)


if __name__ == "__main__":
    main()
