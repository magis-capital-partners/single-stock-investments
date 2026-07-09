#!/usr/bin/env python3
"""Build non-CEO insider buy scores for biotech quant (Verdad-style)."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    INSIDER_SCORES_PATH,
    SIGNALS_PATH,
    assign_quintiles,
    load_json,
    now_iso,
    save_json,
)

INSIDER_DIR = ROOT / "_system" / "reference" / "market-data" / "insider"
MANIFEST = INSIDER_DIR / "manifest.json"


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def is_ceo_title(title: str) -> bool:
    t = (title or "").lower()
    if "ceo" in t or "chief executive" in t:
        return True
    if "president" in t and "vice" not in t and "cfo" not in t:
        # ambiguous; treat as CEO-like only if exact-ish
        return "president & ceo" in t or t.strip() in {"president", "chief executive officer"}
    return False


def is_cfo_title(title: str) -> bool:
    t = (title or "").lower()
    return "cfo" in t or "chief financial" in t


def score_ticker(csv_path: Path, as_of: datetime) -> dict:
    cutoff = as_of - timedelta(days=90)
    buys = 0
    cfo_buys = 0
    non_ceo_buys = 0
    if not csv_path.exists():
        return {"insider_buy_count_90d": 0, "insider_cfo_buys": 0, "insider_score": 0}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("transaction_code") or "").upper().strip()
            acquired = (row.get("acquired_disposed") or "").upper().strip()
            # Open-market purchases only (Form 4 code P). Grants (A) do not count.
            if code != "P":
                continue
            if acquired == "D":
                continue
            dt = parse_date(row.get("transaction_date") or row.get("filing_date"))
            if not dt or dt < cutoff:
                continue
            title = row.get("title") or ""
            if is_ceo_title(title):
                continue
            buys += 1
            non_ceo_buys += 1
            if is_cfo_title(title):
                cfo_buys += 1
    # count-based score; CFO buys weighted
    score = min(100, non_ceo_buys * 12 + cfo_buys * 18)
    return {
        "insider_buy_count_90d": non_ceo_buys,
        "insider_cfo_buys": cfo_buys,
        "insider_score": score,
    }


def main() -> int:
    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    manifest = load_json(MANIFEST, {"tickers": {}})
    quant = {
        t
        for t, row in (signals.get("by_ticker") or {}).items()
        if row.get("in_biotech_quant_universe")
    }
    tickers = set(quant) | set((manifest.get("tickers") or {}).keys()) | set(signals.get("by_ticker") or {})
    as_of = datetime.now(timezone.utc)
    by_ticker: dict[str, dict] = {}
    for ticker in sorted(tickers):
        meta = (manifest.get("tickers") or {}).get(ticker) or {}
        csv_ref = meta.get("csv") or f"insider/{ticker}_transactions.csv"
        csv_path = ROOT / "_system" / "reference" / "market-data" / csv_ref.replace("\\", "/")
        if not csv_path.exists():
            csv_path = INSIDER_DIR / f"{ticker}_transactions.csv"
        if csv_path.exists():
            scored = score_ticker(csv_path, as_of)
        elif ticker in quant:
            # Live factor keys must exist on universe even before Form 4 harvest
            scored = {"insider_buy_count_90d": 0, "insider_cfo_buys": 0, "insider_score": 0}
        else:
            continue
        by_ticker[ticker] = {"ticker": ticker, **scored}

    # Universe quintiles among quant names with scores
    score_inputs = {
        t: float(row.get("insider_score") or 0)
        for t, row in by_ticker.items()
        if t in quant
    }
    quintiles = assign_quintiles(score_inputs, higher_is_better=True)
    for ticker, row in by_ticker.items():
        row["insider_quintile"] = quintiles.get(ticker)

    payload = {
        "generated_at": now_iso(),
        "ticker_count": len(by_ticker),
        "quant_scored": len(score_inputs),
        "by_ticker": by_ticker,
    }
    save_json(INSIDER_SCORES_PATH, payload)

    if signals.get("by_ticker"):
        for ticker, row in by_ticker.items():
            if ticker in signals["by_ticker"]:
                signals["by_ticker"][ticker]["insider_score"] = row.get("insider_score")
                signals["by_ticker"][ticker]["insider_buy_count_90d"] = row.get("insider_buy_count_90d")
                signals["by_ticker"][ticker]["insider_cfo_buys"] = row.get("insider_cfo_buys")
                signals["by_ticker"][ticker]["insider_quintile"] = row.get("insider_quintile")
        save_json(SIGNALS_PATH, signals)
    print(f"Wrote insider scores for {len(by_ticker)} tickers ({len(score_inputs)} quant quintiled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
