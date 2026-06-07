#!/usr/bin/env python3
"""Fetch SEC Form 4 insider transactions for US tickers with CIK.

Writes:
  _system/reference/market-data/insider/{TICKER}_transactions.csv
  _system/reference/market-data/insider/manifest.json

  python3 _system/scripts/fetch_insider_transactions.py           # all US CIK tickers in registry
  python3 _system/scripts/fetch_insider_transactions.py LMNR    # subset
  python3 _system/scripts/fetch_insider_transactions.py --offline LMNR  # skip network; keep cached CSV
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from insider_signal_common import (  # noqa: E402
    cik_for_ticker,
    fetch_transactions_for_ticker,
    load_json,
    read_transactions_csv,
    update_manifest,
    write_transactions_csv,
)
from insider_signal_common import CONFIG_PATH  # noqa: E402


def registry_us_tickers() -> list[str]:
    from portfolio_registry import load_registry  # noqa: WPS433

    holdings = (load_registry().get("holdings") or {}).keys()
    return sorted(t for t in holdings if cik_for_ticker(t))


def fetch_ticker(ticker: str, *, offline: bool = False) -> str:
    tk = ticker.upper()
    if not cik_for_ticker(tk):
        return f"skip {tk} (no CIK in us_ticker_config.json)"
    if offline:
        txs = read_transactions_csv(tk)
        if not txs:
            return f"skip {tk} (offline, no cached CSV)"
        update_manifest(tk, txs)
        return f"OK {tk}: {len(txs)} cached transaction(s) (offline)"
    cfg = load_json(CONFIG_PATH)
    window = int(cfg.get("window_days", 365))
    try:
        txs = fetch_transactions_for_ticker(tk, window)
    except Exception as exc:
        cached = read_transactions_csv(tk)
        update_manifest(tk, cached, error=str(exc))
        return f"WARN {tk}: fetch failed ({exc}); kept {len(cached)} cached row(s)"
    if not txs:
        cached = read_transactions_csv(tk)
        if cached:
            update_manifest(tk, cached, error="fetch returned 0; kept cache")
            return f"WARN {tk}: fetch returned 0; kept {len(cached)} cached row(s)"
        update_manifest(tk, [], error="no transactions in window")
        return f"skip {tk} (no transactions in {window}d window)"
    path = write_transactions_csv(tk, txs)
    update_manifest(tk, txs)
    return f"OK {tk}: {len(txs)} transaction(s) -> {path.relative_to(ROOT)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset (default: all US CIK holdings)")
    ap.add_argument("--offline", action="store_true", help="Use cached CSV only")
    args = ap.parse_args()
    targets = [t.upper() for t in args.tickers] if args.tickers else registry_us_tickers()
    if not targets:
        print("No US CIK tickers found.", file=sys.stderr)
        return 1
    for tk in targets:
        print(fetch_ticker(tk, offline=args.offline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
