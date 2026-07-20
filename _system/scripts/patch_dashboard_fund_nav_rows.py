#!/usr/bin/env python3
"""Patch fund NAV-discount tickers into dashboard_data.json without a full rebuild."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from build_dashboard_data import (  # noqa: E402
    OUTPUT,
    build_ticker_row,
    load_investment_sleeve_index,
    load_registry,
)
from portfolio_registry import CLASS_PATH  # noqa: E402


def main() -> int:
    tickers = sys.argv[1:] or ["CEE", "URB.A.TO", "PSH", "NAN"]
    if not OUTPUT.exists():
        print(f"Missing {OUTPUT}; run build_dashboard_data.py first", file=sys.stderr)
        return 1
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    portfolio_class = {}
    if CLASS_PATH.exists():
        portfolio_class = json.loads(CLASS_PATH.read_text(encoding="utf-8"))

    by_ticker = {r["ticker"]: i for i, r in enumerate(data.get("tickers") or [])}
    for ticker in tickers:
        row = build_ticker_row(
            ticker,
            holdings=holdings,
            portfolio_class=portfolio_class,
            insights_doc=data.get("insights_embed") or {},
            memory_doc=None,
            watchlist=reg.get("watchlist") or {},
            registry_docs=[],
        )
        if ticker in by_ticker:
            data["tickers"][by_ticker[ticker]] = row
        else:
            data["tickers"].append(row)
            by_ticker[ticker] = len(data["tickers"]) - 1
        print(
            f"patched {ticker}: sleeve={row.get('classification', {}).get('investment_sleeve')} "
            f"fund_nav={bool(row.get('fund_nav'))} "
            f"disc={((row.get('fund_nav') or {}).get('discount_to_reported_nav_pct'))}"
        )

    # Refresh sleeve filter counts for fund sleeve
    ticker_to_sleeve, labels = load_investment_sleeve_index()
    fund_tickers = {t for t, sid in ticker_to_sleeve.items() if sid == "fund_nav_discounts"}
    rows = data.get("tickers") or []
    fund_count = sum(1 for r in rows if r.get("ticker") in fund_tickers or r.get("fund_nav"))
    filters = data.setdefault("summary", {}).setdefault("sleeve_filters", [])
    # Ensure fund_nav_all / fund_nav_discounts entries exist with fresh counts
    seen = {f.get("id") for f in filters}
    if "fund_nav_all" not in seen:
        filters.insert(
            1,
            {"id": "fund_nav_all", "label": "NAV discounts", "count": fund_count},
        )
    for f in filters:
        if f.get("id") in ("fund_nav_all", "fund_nav_discounts"):
            f["count"] = fund_count
            f["label"] = labels.get("fund_nav_discounts", "NAV discounts") if f["id"] == "fund_nav_discounts" else "NAV discounts"

    data["summary"]["ticker_count"] = len(rows)
    OUTPUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(rows)} tickers, fund sleeve count={fund_count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
