"""Build the bounded private one-pager input snapshot from existing research.

Prices use HTTPS vendor history only when --refresh-performance is explicitly
selected. This tool never connects to a broker or a market-data terminal.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import gzip
import math
from pathlib import Path
import threading
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from build_total_return_panel import build_wealth_series, load_event_ledger
from fetch_equity_prices import yahoo_symbol_for
from stock_one_pagers import build_one_pager, company_profile, read_json, PERFORMANCE_METHOD

ROOT = Path(__file__).resolve().parents[2]
_request_lock = threading.Lock()
_next_request = 0.0
METHOD_VERSION = PERFORMANCE_METHOD


def fetch_performance(ticker: str, row: dict, source_cache: Path | None = None) -> dict:
    if ticker.endswith((".CVR", ".DB")):
        return {"status": "unavailable", "ticker": ticker,
                "reason": "This claim requires its own verified history; underlying common-share prices are not comparable"}
    symbol = yahoo_symbol_for(row.get("quote_ticker") or ticker, row.get("market") or "US", row.get("exchange") or "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?period1=-2208988800&period2={int(time.time())}&interval=1d&events=div%2Csplits"
    cached_source = source_cache / (quote(ticker, safe='') + ".json.gz") if source_cache else None
    data = None
    retrieved_at = datetime.now(timezone.utc).isoformat()
    if cached_source and cached_source.is_file():
        try:
            saved = json.loads(gzip.decompress(cached_source.read_bytes()))
            if saved.get("symbol") == symbol:
                data, retrieved_at = saved["data"], saved["retrieved_at"]
        except (OSError, EOFError, ValueError, KeyError):
            pass  # A stopped refresh can leave an unfinished temporary input.
    global _next_request
    for attempt in range(3):
        if data is not None:
            break
        try:
            with _request_lock:
                time.sleep(max(0, _next_request - time.monotonic()))
                _next_request = time.monotonic() + 0.8
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 stock-research-history", "Accept-Encoding": "gzip"}), timeout=30) as response:
                raw = response.read()
                if getattr(response, "headers", {}).get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                data = json.loads(raw)["chart"]["result"][0]
            if cached_source:
                cached_source.parent.mkdir(parents=True, exist_ok=True)
                temporary = cached_source.with_suffix(".tmp")
                temporary.write_bytes(gzip.compress(json.dumps({"symbol": symbol, "retrieved_at": retrieved_at, "data": data}, separators=(",", ":")).encode(), mtime=0))
                temporary.replace(cached_source)
            break
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            if attempt == 2:
                return {"status": "unavailable", "reason": "Vendor history unavailable for this listing", "ticker": ticker}
            time.sleep(2 ** (attempt + 1))
    meta = data.get("meta") or {}
    currency = meta.get("currency")
    if not isinstance(currency, str) or len(currency) != 3:
        return {"status": "unavailable", "ticker": ticker, "reason": "A reporting currency was not supplied for this listing"}
    try:
        zone = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
    except (KeyError, ValueError):
        zone = timezone.utc
    # Windows' C runtime rejects negative Unix timestamps. Arithmetic from the
    # UTC epoch supports pre-1970 listings without changing the exchange date.
    day = lambda ts: (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=int(ts))).astimezone(zone).date().isoformat()
    cutoff = datetime.now(zone).date().isoformat()
    bars = {day(ts): float(p) for ts, p in zip(data.get("timestamp") or [], data["indicators"]["quote"][0]["close"])
            if p is not None and math.isfinite(p) and p >= 0 and day(ts) < cutoff}
    dates = sorted(bars)
    if len(dates) < 2 or bars[dates[0]] <= 0:
        return {"status": "unavailable", "ticker": ticker, "reason": "Insufficient completed trading sessions"}
    events = []
    for p in (data.get("events", {}).get("dividends") or {}).values():
        events.append({"ex_date": day(p["date"]), "amount_per_share": p["amount"], "amount_basis": "split_adjusted", "type": "regular_dividend", "source": f"yahoo:{symbol}", "source_tier": "vendor"})
    for p in (data.get("events", {}).get("splits") or {}).values():
        if p.get("denominator") and p.get("numerator"):
            events.append({"ex_date": day(p["date"]), "split_factor": p["numerator"] / p["denominator"], "type": "split", "source": f"yahoo:{symbol}", "source_tier": "vendor"})
    events, coverage = load_event_ledger(ticker, events)
    events = [p for p in events if p.get("ex_date", "") <= cutoff]
    wealth = build_wealth_series(dates, [bars[d] for d in dates], events)
    return {"schema_version": "stock-performance.v1", "method_version": METHOD_VERSION, "ticker": ticker,
            "retrieved_at": retrieved_at, "currency": currency,
            "instrument_type": meta.get("instrumentType"),
            "source_url": f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/", "source": f"yahoo:{symbol}",
            "coverage": coverage, "status": "partial", "columns": ["date", "price_index", "total_return_index"],
            "basis": "Split-adjusted prices; cash distributions reinvested at the ex-date close, with share-basis adjustment applied once. Vendor dividend amounts already reflect subsequent splits. Pre-tax nominal listing currency. Distribution completeness is reported separately. Current exchange-day observations are excluded.",
            "as_of": dates[-1], "benchmark_ref": "SPY" if meta.get("currency") == "USD" else None,
            "points": [[d, round(p, 6), round(t, 6)] for d, p, t in zip(dates, wealth["price_index"], wealth["total_return_index"])]}


def reconcile_performance(record: dict, source: Path) -> dict:
    """Do not publish materially conflicting vendor-only total-return histories."""
    if not record.get("points") or not source.is_file():
        return record
    data = json.loads(gzip.decompress(source.read_bytes()))["data"]
    adjusted = ((data.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or [])
    try:
        zone = ZoneInfo((data.get("meta") or {}).get("exchangeTimezoneName") or "UTC")
    except (KeyError, ValueError):
        zone = timezone.utc
    day = lambda ts: (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=int(ts))).astimezone(zone).date().isoformat()
    values = {day(ts): float(value) for ts, value in zip(data.get("timestamp") or [], adjusted)
              if isinstance(value, (int, float)) and math.isfinite(value) and value > 0}
    first, last = record["points"][0], record["points"][-1]
    if first[0] not in values or last[0] not in values or first[2] <= 0:
        return record
    reference = values[last[0]] / values[first[0]]
    difference = (last[2] / first[2]) / reference - 1
    check = {"method": "vendor_adjusted_close_endpoint", "difference_pct": round(difference * 100, 4),
             "status": "requires_review" if abs(difference) > 0.10 else "consistent"}
    if check["status"] == "requires_review" and record.get("coverage", {}).get("status") == "vendor_only":
        return {**record, "points": [], "status": "evidence_blocked", "reconciliation": check,
                "reason": "Distributions and adjusted prices do not reconcile; this history needs source review."}
    return {**record, "reconciliation": check}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh-performance", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=8)
    args = parser.parse_args()
    core = json.loads(args.core.read_text(encoding="utf-8"))
    checkpoint = args.output.parent / "performance-checkpoints"
    checkpoint.mkdir(parents=True, exist_ok=True)
    rows = {}
    for stub in core["tickers"]:
        ticker = stub["ticker"]
        path = args.shards / Path(stub.get("detail_shard") or ticker + ".json").name
        if not path.is_file():
            path = args.shards / (ticker + ".json")
        rows[ticker] = json.loads(path.read_text(encoding="utf-8"))
        if rows[ticker].get("ticker") != ticker:
            raise ValueError(f"Ticker identity mismatch: {ticker}")
    rows.setdefault("SPY", {"ticker": "SPY", "market": "US"})
    if args.refresh_performance:
        todo = {t: r for t, r in rows.items() if read_json(checkpoint / (quote(t, safe='') + ".json")).get("method_version") != METHOD_VERSION}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_performance, t, r, args.output.parent / "performance-inputs"): t for t, r in todo.items()}
            for i, future in enumerate(as_completed(futures), 1):
                ticker = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"History needs review: {ticker}: {type(exc).__name__}: {exc}", flush=True)
                    result = {"ticker": ticker, "status": "unavailable", "reason": "History transformation requires review"}
                result["method_version"] = METHOD_VERSION
                (checkpoint / (quote(ticker, safe='') + ".json")).write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                if i <= 4 or i % 25 == 0:
                    print(f"Return histories checked: {i}/{len(todo)}", flush=True)
    companies = {}
    for i, (ticker, row) in enumerate(rows.items(), 1):
        brief = build_one_pager(ROOT, ticker, row)
        perf = checkpoint / (quote(ticker, safe='') + ".json")
        if perf.is_file():
            incoming = json.loads(perf.read_text(encoding="utf-8"))
            if incoming.get("points") or brief.get("performance", {}).get("method_version") != METHOD_VERSION:
                brief["performance"] = incoming
        brief["performance"] = reconcile_performance(brief["performance"], args.output.parent / "performance-inputs" / (quote(ticker, safe='') + ".json.gz"))
        if brief["performance"].get("instrument_type") in {"ETF", "MUTUALFUND"}:
            brief["profile"] = company_profile(ticker, {**row, "instrument_type": brief["performance"]["instrument_type"]}, read_json(ROOT / ticker / "research/valuation_contract.json"))
        brief["performance"].pop("benchmark", None)
        companies[ticker] = brief
        if i % 100 == 0:
            print(f"Company briefs assembled: {i}/{len(rows)}", flush=True)
    snapshot = {"schema_version": "stock-research-universe.v1", "as_of": datetime.now(timezone.utc).isoformat(), "companies": companies}
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"stocks": len(core["tickers"]), "histories": sum(bool(c["financials"]["series"]) for c in companies.values()),
                      "return_histories": sum(bool(c["performance"].get("points")) for c in companies.values()), "snapshot_bytes": args.output.stat().st_size}), flush=True)


if __name__ == "__main__":
    main()
