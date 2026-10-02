#!/usr/bin/env python3
"""Fail if any CSV under _system/reference/market-data is really an HTML page.

Data hosts answer bot checks and error pages with HTTP 200, and a downloader
that only checks the status writes the page to disk as `.csv`. That is how
benchmarks/spy_us.csv and bnd_us.csv held Stooq's JavaScript bot check from
2026-07-02 (and its "Get your apikey" notice before that) instead of prices,
while every reader parsed zero rows without complaint.

  python _system/scripts/check_market_data_csvs.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKET_DATA = ROOT / "_system" / "reference" / "market-data"

# Non-CSV bodies Stooq has served with HTTP 200.
STOOQ_MARKERS = (b"__verify", b"requires javascript to verify", b"get your apikey")


def problem(path: Path) -> str | None:
    with path.open("rb") as handle:
        head = handle.read(1024)
    stripped = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if stripped.startswith(b"<"):
        return "starts with '<' (HTML, not CSV)"
    lowered = head.lower()
    for marker in STOOQ_MARKERS:
        if marker in lowered:
            return f"contains Stooq non-CSV marker {marker.decode()!r}"
    return None


def scan(root: Path) -> list[tuple[Path, str]]:
    bad = []
    for path in sorted(root.rglob("*.csv")):
        reason = problem(path)
        if reason:
            bad.append((path, reason))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", type=Path, default=MARKET_DATA)
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"market-data directory not found: {args.root}", file=sys.stderr)
        return 2
    count = sum(1 for _ in args.root.rglob("*.csv"))
    bad = scan(args.root)
    for path, reason in bad:
        try:
            shown = path.relative_to(ROOT)
        except ValueError:
            shown = path
        print(f"::error file={shown.as_posix()}::{shown.as_posix()} {reason}")
    print(f"checked {count} CSV file(s) under {args.root}; {len(bad)} not CSV")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
