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
from urllib.parse import quote, urlencode
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


PSE_CHART = "https://edge.pse.com.ph/common/DisclosureCht.ax"
FT_HISTORY = "https://markets.ft.markitdigital.com/data/equities/ajax/get-historical-prices"


def request(url, lane, *, payload=None):
    for attempt in range(3):
        with _LOCK:
            now = time.monotonic()
            slot = max(now, _NEXT.get(lane, now))
            _NEXT[lane] = slot + 0.6
        time.sleep(max(0, slot - now))
        try:
            req = Request(
                url,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json,text/html,*/*",
                    "Accept-Encoding": "gzip",
                    **({"Content-Type": "application/json"} if payload is not None else {}),
                },
            )
            with urlopen(req, timeout=25) as response:
                allowed = (
                    response.url == PSE_CHART
                    or response.url.startswith(("https://query1.finance.yahoo.com/", "https://finance.yahoo.com/"))
                    or url.startswith(FT_HISTORY + "?") and response.url == url
                )
                if not allowed:
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


def capture_pse_history(archive, start, as_of):
    data = request(
        PSE_CHART,
        "pse-history",
        payload={
            "cmpy_id": archive["company_id"],
            "security_id": archive["security_id"],
            "startDate": start.strftime("%m-%d-%Y"),
            "endDate": as_of.strftime("%m-%d-%Y"),
        },
    )
    if not data:
        return
    try:
        return [
            [row["CHART_DATE"].removesuffix(" 00:00:00"), str(row["CLOSE"])]
            for row in json.loads(data)["chartData"]
        ]
    except (ValueError, KeyError, TypeError, AttributeError):
        return


def capture_ft_history(archive, start, as_of):
    from bs4 import BeautifulSoup

    params = urlencode({
        "startDate": max(start, as_of - timedelta(days=365)).isoformat(),
        "endDate": as_of.isoformat(),
        "symbol": archive["ft_symbol"],
    })
    raw = request(FT_HISTORY + "?" + params, "ft-history")
    if not raw:
        return
    prices = []
    try:
        table = BeautifulSoup(json.loads(raw)["html"], "html.parser")
        for tr in table.select("tr"):
            cells = tr.select("td")
            if len(cells) == 6 and (label := cells[0].select_one("span")):
                day = datetime.strptime(label.get_text(strip=True), "%A, %B %d, %Y").date()
                prices.append([day.strftime("%b %d, %Y"), cells[4].get_text(strip=True)])
    except (ValueError, KeyError, TypeError):
        return
    return prices


def capture(cache, ticker, row, previous, override, as_of, *, full_history=False):
    if override.get("identity_exception") or override.get("ended"):
        return
    archive = override.get("price_archive") or {}
    if ticker.endswith(NO_COMMON_PRICE) and not archive:
        return
    path = quote(ticker, safe="") + ".gz"
    symbol = symbol_for(ticker, row, override)
    prior = previous.get("price", {})
    last = prior.get("last")
    start = (
        (date.fromisoformat(last) - timedelta(days=45))
        if last and prior.get("status") == "complete" and not full_history
        else date.fromisoformat(override.get("first_session", "1960-01-01"))
    )
    prices = None
    if archive.get("company_id"):
        # The exchange provides the full available archive in one request.
        start = date.fromisoformat(override["first_session"])
        prices = capture_pse_history(archive, start, as_of)
    elif archive.get("ft_symbol"):
        start = date.fromisoformat(last) - timedelta(days=45) if last else start
        prices = capture_ft_history(archive, start, as_of)
    else:
        raw = capture_price(symbol, start, as_of)
        if raw:
            (cache / "daily" / path).write_bytes(gzip.compress(raw, mtime=0))
    if prices:
        write(
            cache / "alternate" / (ticker + "-price.json"),
            {"source": archive["source"], "headers": ["Date", "Close"], "rows": prices},
        )
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


def refresh(root, cache, *, do_publish=False, selected=None):
    store = PrivateStorage(root=root)
    release = published_release(store, listings=True)
    previous = release["listings"]
    as_of = (
        date.fromisoformat(release["as_of"])
        if selected
        else datetime.now(timezone.utc).date() - timedelta(days=1)
    )
    registry = read(root / "_system/portfolio/registry.json")["holdings"]
    core = read_explorer_json(root, "dashboard/data/core.json", store)
    rows = {r["ticker"]: r for r in core.get("tickers", [])}
    aliases = research_aliases(root)
    overrides = read(SOURCE_FILE)
    for k in ("daily", "profiles"):
        (cache / k).mkdir(parents=True, exist_ok=True)
    tickers = sorted(set(registry) - set(aliases))
    if selected:
        unknown = set(selected) - set(tickers)
        if unknown:
            raise ValueError("Unknown canonical Summary ticker(s): " + ", ".join(sorted(unknown)))
        tickers = sorted(set(selected))
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
                full_history=bool(selected),
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
    document = build(root, cache, None, as_of.isoformat(), core_path, previous, tickers=selected)
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
    parser.add_argument("--ticker", action="append", help="Backfill this listing at the published cutoff; repeat as needed")
    args = parser.parse_args()
    print(json.dumps(refresh(args.root, args.cache, do_publish=args.publish, selected=args.ticker)), flush=True)
