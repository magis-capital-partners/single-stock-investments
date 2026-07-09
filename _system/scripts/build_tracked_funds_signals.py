#!/usr/bin/env python3
"""Build light ownership signals from tracked great-fund 13F book overlay."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import OWNERSHIP_DIR, load_json, now_iso, portfolio_universe, save_json  # noqa: E402

RECORDS_DIR = OWNERSHIP_DIR / "tracked_funds" / "records"
SIGNALS_PATH = OWNERSHIP_DIR / "tracked_funds" / "signals_latest.json"
FUNDS_PATH = OWNERSHIP_DIR / "tracked_funds.json"

CORE_FUNDS = {
    "ruane-cunniff",
    "dodge-cox",
    "harris-associates",
    "first-eagle",
    "tweedy-browne",
    "capital-research-global",
}


def load_latest_book_records() -> tuple[str, list[dict]]:
    latest = RECORDS_DIR / "latest.json"
    if not latest.exists():
        return "", []
    doc = load_json(latest, {"records": []})
    return doc.get("quarter") or latest.stem, doc.get("records") or []


def build_signals(book_records: list[dict], quarter: str) -> dict:
    funds_doc = load_json(FUNDS_PATH, {"funds": []})
    fund_meta = {f.get("fund_id"): f for f in funds_doc.get("funds") or []}
    tickers, _ = portfolio_universe()

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in book_records:
        ticker = (row.get("ticker") or "").upper()
        if not ticker:
            continue
        by_ticker[ticker].append(row)

    ticker_signals: dict[str, dict] = {}
    for ticker, rows in by_ticker.items():
        holders = sorted({r.get("fund_id") for r in rows if r.get("fund_id")})
        changes = [r.get("change_type") for r in rows if r.get("change_type") and r.get("change_type") != "unchanged"]
        new_or_add = sum(1 for c in changes if c in {"new", "add"})
        trim_or_exit = sum(1 for c in changes if c in {"trim", "exit"})
        core_holders = [h for h in holders if h in CORE_FUNDS]
        direction = "neutral"
        if new_or_add > trim_or_exit:
            direction = "bullish"
        elif trim_or_exit > new_or_add:
            direction = "bearish"
        meta = tickers.get(ticker) or {}
        ticker_signals[ticker] = {
            "ticker": ticker,
            "company": meta.get("company"),
            "quarter": quarter,
            "holder_count": len(holders),
            "core_holder_count": len(core_holders),
            "holders": holders,
            "core_holders": core_holders,
            "new_or_add": new_or_add,
            "trim_or_exit": trim_or_exit,
            "direction": direction,
            "changes": [
                {
                    "fund_id": r.get("fund_id"),
                    "fund": r.get("fund") or (fund_meta.get(r.get("fund_id")) or {}).get("fund"),
                    "change_type": r.get("change_type"),
                    "change_shares_pct": r.get("change_shares_pct"),
                    "shares": r.get("shares"),
                    "market_value_usd": r.get("market_value_usd"),
                }
                for r in rows
                if r.get("change_type") and r.get("change_type") != "unchanged"
            ],
        }

    return {
        "generated_at": now_iso(),
        "quarter": quarter,
        "ticker_count": len(ticker_signals),
        "by_ticker": dict(sorted(ticker_signals.items())),
        "notes": "Light QoQ ownership signals for curated great funds vs portfolio/watchlist.",
    }


def main() -> int:
    quarter, records = load_latest_book_records()
    if not records:
        save_json(
            SIGNALS_PATH,
            {
                "generated_at": now_iso(),
                "quarter": quarter or None,
                "ticker_count": 0,
                "by_ticker": {},
                "status": "empty",
                "notes": "No tracked-fund book records yet.",
            },
        )
        print(f"Wrote empty signals to {SIGNALS_PATH}")
        return 0
    payload = build_signals(records, quarter or "unknown")
    save_json(SIGNALS_PATH, payload)
    print(f"Wrote {SIGNALS_PATH} ({payload['ticker_count']} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
