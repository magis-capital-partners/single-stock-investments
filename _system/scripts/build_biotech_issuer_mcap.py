#!/usr/bin/env python3
"""Populate issuer_market_cap + issuer_size_bucket for biotech quant universe."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    FUNDAMENTALS_PATH,
    SIGNALS_PATH,
    fetch_issuer_market_cap,
    issuer_size_bucket,
    load_json,
    now_iso,
    save_json,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--max-fetch", type=int, default=60)
    args = ap.parse_args()

    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    funda = load_json(FUNDAMENTALS_PATH, {"by_ticker": {}})
    by_f = funda.setdefault("by_ticker", {})
    fetched = 0
    updated = 0
    for ticker, row in sorted((signals.get("by_ticker") or {}).items()):
        if not row.get("in_biotech_quant_universe") or ":" in ticker:
            continue
        offline = args.offline or fetched >= args.max_fetch
        result = fetch_issuer_market_cap(ticker, offline=offline)
        if not offline and result.get("issuer_market_cap"):
            fetched += 1
        mcap = result.get("issuer_market_cap")
        if mcap:
            bucket = issuer_size_bucket(mcap)
            by_f[ticker] = {
                **(by_f.get(ticker) or {}),
                "ticker": ticker,
                "issuer_market_cap": mcap,
                "market_cap_source": result.get("market_cap_source"),
                "shares_outstanding": result.get("shares_outstanding"),
                "price": result.get("price"),
                "issuer_size_bucket": bucket,
                "updated_at": now_iso(),
            }
            row["issuer_market_cap"] = mcap
            row["issuer_size_bucket"] = bucket
            updated += 1
        elif by_f.get(ticker, {}).get("issuer_market_cap"):
            row["issuer_market_cap"] = by_f[ticker]["issuer_market_cap"]
            row["issuer_size_bucket"] = by_f[ticker].get("issuer_size_bucket") or issuer_size_bucket(
                by_f[ticker]["issuer_market_cap"]
            )
            updated += 1

    funda["generated_at"] = now_iso()
    save_json(FUNDAMENTALS_PATH, funda)
    save_json(SIGNALS_PATH, signals)
    print(f"Issuer mcap updated for {updated} tickers (fetched {fetched})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
