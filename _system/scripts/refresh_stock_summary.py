"""Refresh covered stock descriptions and completed-session closes over HTTPS."""

from __future__ import annotations

import argparse
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from private_storage import PrivateStorage
from publish_stock_summary import publish, published_release
from stock_research_explorer import read_explorer_json
from stock_summary import (
    NO_COMMON_PRICE,
    SOURCE_FILE,
    audit,
    build,
    read,
    symbol_for,
    write,
)
from stock_valuation_aliases import research_aliases

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
MAX_SOURCE_BYTES = 5 * 1024 * 1024
_LOCK = Lock()
_NEXT = {}


def request(url, lane):
    for attempt in range(3):
        with _LOCK:
            now = time.monotonic()
            slot = max(now, _NEXT.get(lane, now))
            _NEXT[lane] = slot + 0.6
        time.sleep(max(0, slot - now))
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json,text/html,*/*",
                    "Accept-Encoding": "gzip",
                },
            )
            with urlopen(req, timeout=25) as response:
                if not response.url.startswith(
                    ("https://query1.finance.yahoo.com/", "https://finance.yahoo.com/")
                ):
                    return None
                raw = response.read(MAX_SOURCE_BYTES + 1)
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw if len(raw) <= MAX_SOURCE_BYTES else None
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504}:
                return None
        except (OSError, ValueError):
            pass
        time.sleep(2**attempt)
    return None


def capture_price(symbol, start, as_of):
    midnight = lambda day: int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end = midnight(as_of + timedelta(days=1))
    start = midnight(start)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + quote(symbol, safe="")
        + f"?period1={start}&period2={end}&interval=1d&events=div%2Csplits"
    )
    raw = request(url, "price")
    if not raw:
        return None
    try:
        data = json.loads(raw)["chart"]["result"][0]
        if data["meta"].get("dataGranularity") != "1d" or data["meta"].get("symbol") != symbol:
            return None
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return json.dumps({"data": data, "symbol": symbol, "source_url": url}, separators=(",", ":")).encode()


def capture(cache, ticker, row, previous, override, as_of):
    if override.get("identity_exception") or override.get("ended") or ticker.endswith(NO_COMMON_PRICE):
        return
    path = quote(ticker, safe="") + ".gz"
    symbol = symbol_for(ticker, row, override)
    prior = previous.get("price", {})
    last = prior.get("last")
    start = (
        (date.fromisoformat(last) - timedelta(days=45))
        if last
        else date.fromisoformat(override.get("first_session", "1960-01-01"))
    )
    raw = capture_price(symbol, start, as_of)
    if raw:
        (cache / "daily" / path).write_bytes(gzip.compress(raw, mtime=0))
    description = previous.get("description", {})
    observed = description.get("observed")
    if not override.get("description") and (
        not observed
        or date.fromisoformat(observed) < as_of - timedelta(days=90)
        or description.get("status") != "sourced"
    ):
        url = "https://finance.yahoo.com/quote/" + quote(symbol, safe="") + "/profile/"
        raw = request(url, "profile")
        if raw:
            (cache / "profiles" / path).write_bytes(gzip.compress(raw, compresslevel=3, mtime=0))


def refresh(root, cache, *, do_publish=False):
    as_of = datetime.now(timezone.utc).date() - timedelta(days=1)
    store = PrivateStorage(root=root)
    previous = published_release(store, listings=True)["listings"]
    registry = read(root / "_system/portfolio/registry.json")["holdings"]
    core = read_explorer_json(root, "dashboard/data/core.json", store)
    rows = {r["ticker"]: r for r in core.get("tickers", [])}
    aliases = research_aliases(root)
    overrides = read(SOURCE_FILE)
    for k in ("daily", "profiles"):
        (cache / k).mkdir(parents=True, exist_ok=True)
    tickers = sorted(set(registry) - set(aliases))
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = [
            pool.submit(
                capture,
                cache,
                t,
                {**registry[t], **rows.get(t, {})},
                previous.get(t, {}),
                overrides.get(t, {}),
                as_of,
            )
            for t in tickers
        ]
        for task in tasks:
            task.result()
    core_path = cache / "resolved-core.json"
    write(
        core_path,
        {
            "tickers": [
                {
                    k: v
                    for k, v in row.items()
                    if k in {"ticker", "market", "exchange", "quote_ticker", "company", "listing_status"}
                }
                for row in rows.values()
            ]
        },
    )
    document = build(root, cache, None, as_of.isoformat(), core_path, previous)
    report = audit(document)
    write(cache / "coverage.json", report)
    if do_publish:
        publish(document, store)
    return report["counts"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refresh(args.root, args.cache, do_publish=args.publish)), flush=True)
