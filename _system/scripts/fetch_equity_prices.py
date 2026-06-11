#!/usr/bin/env python3
"""Fetch live equity close into valuation.json inputs.price before marvin_valuation --write."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from darwin.prices import stooq_symbol  # noqa: E402
from portfolio_registry import load_registry  # noqa: E402

UA = "MarvinResearch/1.0 (equity-prices)"
STOOQ_URL = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
TODAY = date.today().isoformat()

PLACEHOLDER_RE = re.compile(r"placeholder|confirm via fetch_market", re.I)


def fetch_stooq_close(symbol: str) -> tuple[float | None, str | None, str | None]:
    url = STOOQ_URL.format(symbol=symbol.lower())
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return None, None, str(exc)
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return None, None, "empty"
    parts = lines[1].split(",")
    if len(parts) < 7:
        return None, None, "bad csv"
    quote_date = parts[1].strip() if len(parts) > 1 else TODAY
    try:
        close = float(parts[6].strip())
    except ValueError:
        return None, None, "no close"
    return close, quote_date, None


def fetch_yahoo_close(symbol: str) -> tuple[float | None, str | None, str | None]:
    end = datetime.now(timezone.utc)
    start = end.replace(day=max(1, end.day - 14))
    url = (
        f"{YAHOO_CHART_URL}/{symbol}?period1={int(start.timestamp())}"
        f"&period2={int(end.timestamp())}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=25).read())
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception as exc:
        return None, None, str(exc)
    for ts, close in zip(reversed(timestamps), reversed(closes)):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return float(close), d, None
    return None, None, "no close"


def registry_row(ticker: str) -> dict | None:
    holdings = (load_registry().get("holdings") or {})
    return holdings.get(ticker.upper())


def yahoo_symbol_for(ticker: str, market: str, exchange: str) -> str:
    t = ticker.upper()
    m = (market or "US").upper()
    if m == "JP" and t.endswith(".T"):
        return t.replace(".T", ".T")
    if m == "SE" and t.endswith(".ST"):
        return t.replace(".ST", ".ST")
    if m == "CA" and t.endswith(".TO"):
        return t
    if m in ("AU",) and t.endswith(".AX"):
        return t
    if m in ("IN",) and t.endswith(".NS"):
        return t
    if t.endswith(".SA"):
        return t
    if m in ("UK", "GB") or t.endswith(".L"):
        base = t.replace(".L", "")
        return f"{base}.L"
    if exchange and "TSX" in exchange.upper() and ".TO" not in t:
        return f"{t}.TO"
    if exchange and exchange.upper() == "CSE" and ".CN" not in t:
        return f"{t.split('.')[0]}.CN"
    return t.split(".")[0]


def fetch_price(ticker: str) -> tuple[float | None, str | None, str]:
    row = registry_row(ticker)
    market = (row or {}).get("market", "US")
    exchange = (row or {}).get("exchange", "")
    sym = stooq_symbol(ticker, market)
    if sym:
        close, qd, err = fetch_stooq_close(sym)
        if close is not None:
            return close, qd, f"Stooq {sym.upper()} close {qd}"
    ysym = yahoo_symbol_for(ticker, market, exchange)
    close, qd, err = fetch_yahoo_close(ysym)
    if close is not None:
        return close, qd, f"Yahoo {ysym} close {qd}"
    return None, None, f"fetch failed (stooq={sym}, yahoo={ysym}, err={err})"


def merge_ticker(ticker: str, *, force: bool = False) -> bool:
    t = ticker.upper()
    vpath = ROOT / t / "research" / "valuation.json"
    if not vpath.exists():
        print(f"SKIP {t}: no valuation.json")
        return False
    val = json.loads(vpath.read_text(encoding="utf-8"))
    inputs = val.setdefault("inputs", {})
    ps = str(inputs.get("price_source") or "")
    if not force and ps and not PLACEHOLDER_RE.search(ps):
        # refresh if source looks stale (>7 days) or missing price_as_of
        pas = inputs.get("price_as_of") or ""
        if pas:
            try:
                age = (date.today() - date.fromisoformat(pas[:10])).days
                if age <= 7:
                    print(f"SKIP {t}: price fresh ({pas})")
                    return True
            except ValueError:
                pass
    price, qd, source = fetch_price(t)
    if price is None:
        print(f"WARN {t}: {source}")
        return False
    inputs["price"] = round(price, 4)
    inputs["price_as_of"] = qd or TODAY
    inputs["price_source"] = source
    hr = val.setdefault("human_review", {})
    if not isinstance(hr, dict):
        hr = {}
        val["human_review"] = hr
    hr["live_price_confirmed"] = False
    val["as_of"] = TODAY
    vpath.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    print(f"OK {t}: ${inputs['price']} ({source})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Ticker(s); omit with --all")
    ap.add_argument("--all", action="store_true", help="All registry holdings with valuation.json")
    ap.add_argument("--merge", action="store_true", help="Write into valuation.json (default)")
    ap.add_argument("--force", action="store_true", help="Overwrite even when price_source is not placeholder")
    args = ap.parse_args()
    tickers: list[str] = []
    if args.all:
        for td in sorted(ROOT.iterdir()):
            if td.is_dir() and (td / "research" / "valuation.json").exists():
                if not td.name.startswith("_") and not td.name.startswith("."):
                    tickers.append(td.name.upper())
    else:
        tickers = [t.upper() for t in args.tickers]
    if not tickers:
        ap.error("provide tickers or --all")
    ok = True
    for t in tickers:
        if not merge_ticker(t, force=args.force):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
