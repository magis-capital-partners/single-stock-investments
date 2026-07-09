#!/usr/bin/env python3
"""Build quant signals from specialist 13F ownership records."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from memory_common import is_biotech_quant_universe_ticker  # noqa: E402
from ownership_common import FUNDS_PATH, RECORDS_DIR, SIGNALS_PATH, load_json, now_iso, portfolio_universe, save_json  # noqa: E402


CORE_FUNDS = {
    "baker-bros",
    "ra-capital",
    "orbimed",
    "perceptive-advisors",
    "ikarian-capital",
    "rtw-investments",
    "avoro-capital",
    "deep-track-capital",
}


def load_latest_records() -> tuple[str, list[dict]]:
    latest = RECORDS_DIR / "latest.json"
    if not latest.exists():
        quarters = sorted(RECORDS_DIR.glob("*.json")) if RECORDS_DIR.exists() else []
        quarters = [p for p in quarters if p.name != "latest.json"]
        if not quarters:
            return "", []
        latest = quarters[-1]
    doc = load_json(latest, {"records": []})
    return doc.get("quarter") or latest.stem, doc.get("records") or []


def load_biotech_watchlist(tickers: dict[str, dict]) -> set[str]:
    return {t.upper() for t, meta in tickers.items() if meta.get("biotech_watchlist")}


def entity_for_ticker(ticker: str, tickers: dict[str, dict]) -> dict:
    meta = tickers.get(ticker) or {}
    return {
        "company": meta.get("company"),
        "investment_sleeve": meta.get("investment_sleeve"),
    }


def build_signals(records: list[dict], quarter: str) -> dict:
    funds_doc = load_json(FUNDS_PATH, {"funds": []})
    fund_meta = {f.get("fund_id"): f for f in funds_doc.get("funds") or []}
    tickers, _ = portfolio_universe()
    biotech_watchlist = load_biotech_watchlist(tickers)

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        by_ticker[row.get("ticker") or ""].append(row)

    ticker_signals: dict[str, dict] = {}
    for ticker in sorted(by_ticker):
        rows = by_ticker[ticker]
        entity = entity_for_ticker(ticker, tickers)
        registry_meta = tickers.get(ticker)
        if not is_biotech_quant_universe_ticker(
            ticker,
            entity,
            registry_meta,
            biotech_watchlist=biotech_watchlist,
            ownership_records=rows,
        ):
            continue
        core_rows = [r for r in rows if r.get("fund_id") in CORE_FUNDS]
        adds = sum(1 for r in rows if r.get("change_type") in {"new", "add"})
        trims = sum(1 for r in rows if r.get("change_type") in {"trim", "exit"})
        core_count = len({r.get("fund_id") for r in core_rows})
        specialist_count = len({r.get("fund_id") for r in rows})
        total_value = sum(r.get("market_value_usd") or 0 for r in rows)
        initiations = [r for r in rows if r.get("change_type") == "new" and r.get("fund_id") in CORE_FUNDS]
        exits = [r for r in rows if r.get("change_type") == "exit"]
        concentration = [
            r for r in rows if (r.get("market_value_usd") or 0) >= 100_000_000 and r.get("fund_id") in CORE_FUNDS
        ]
        consensus = min(100, core_count * 18 + specialist_count * 6 + adds * 4 - trims * 3 - len(exits) * 8)
        ticker_signals[ticker] = {
            "ticker": ticker,
            "company": (tickers.get(ticker) or {}).get("company"),
            "in_biotech_quant_universe": True,
            "quarter": quarter,
            "specialist_holder_count": specialist_count,
            "core_fund_holder_count": core_count,
            "net_quarterly_change": adds - trims - len(exits),
            "net_adds": adds,
            "net_trims": trims,
            "exit_count": len(exits),
            "consensus_score": max(0, consensus),
            "total_market_value_usd": total_value,
            "initiation_signal": len(initiations) >= 2,
            "exit_signal": any(r.get("fund_id") in CORE_FUNDS for r in exits),
            "concentration_flag": bool(concentration),
            "holders": sorted(
                rows,
                key=lambda r: (r.get("fund_id") in CORE_FUNDS, r.get("market_value_usd") or 0),
                reverse=True,
            )[:12],
        }

    history: dict[str, list[dict]] = defaultdict(list)
    if RECORDS_DIR.exists():
        for path in sorted(RECORDS_DIR.glob("*.json")):
            if path.name == "latest.json":
                continue
            doc = load_json(path, {})
            q = doc.get("quarter") or path.stem
            counts: dict[str, int] = defaultdict(int)
            for row in doc.get("records") or []:
                counts[row.get("ticker") or ""] += 1
            for ticker, count in counts.items():
                if ticker:
                    history[ticker].append({"quarter": q, "specialist_holder_count": count})

    return {
        "generated_at": now_iso(),
        "quarter": quarter,
        "record_count": len(records),
        "ticker_count": len(ticker_signals),
        "by_ticker": ticker_signals,
        "history": {k: v[-8:] for k, v in history.items()},
        "fund_registry": [
            {
                "fund_id": fid,
                "fund": (fund_meta.get(fid) or {}).get("fund"),
                "priority": (fund_meta.get(fid) or {}).get("priority"),
                "specialty": (fund_meta.get(fid) or {}).get("specialty"),
            }
            for fid in sorted({r.get("fund_id") for r in records if r.get("fund_id")})
        ],
    }


def main() -> int:
    quarter, records = load_latest_records()
    payload = build_signals(records, quarter)
    save_json(SIGNALS_PATH, payload)
    print(f"Wrote signals for {payload['ticker_count']} tickers ({quarter})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
