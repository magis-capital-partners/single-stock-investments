#!/usr/bin/env python3
"""Remove ghost activist index entries (missing files, spurious cross-ticker matches)."""
from __future__ import annotations

import argparse

from activist_common import portfolio_tickers, prune_ghost_index_entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune ghost activist index entries.")
    parser.add_argument("--ticker", action="append", help="Restrict to ticker (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tickers = [t.upper() for t in args.ticker] if args.ticker else portfolio_tickers()
    total = 0
    for ticker in tickers:
        removed = prune_ghost_index_entries(ticker, dry_run=args.dry_run)
        if removed:
            print(f"{ticker}: removed {removed} ghost entries")
        total += removed
    print(f"Done: {total} ghost entries {'would be ' if args.dry_run else ''}removed across {len(tickers)} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
