#!/usr/bin/env python3
"""Build S&P 500 options-liquidity proxy file from Yahoo ADV$.

Phase A screen (Dan/Tom-style liquidity pre-filter for covered calls):
  ADV$ = average daily share volume × last close (≈60 trading days)
  Buckets: A (≥$50M), B (≥$10M), C (≥$2M), D (below / fetch fail)

Output:
  _system/reference/market-data/index/sp500_options_liquidity.json

Usage:
  python _system/scripts/darwin/refresh_sp500_liquidity.py
  python _system/scripts/darwin/refresh_sp500_liquidity.py --limit 25
  python _system/scripts/darwin/refresh_sp500_liquidity.py --offline
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.symbols import yahoo_for_ticker  # noqa: E402
from darwin.universe import SP500_PATH, load_sp500_tickers  # noqa: E402

OUT_PATH = ROOT / "_system" / "reference" / "market-data" / "index" / "sp500_options_liquidity.json"
UA = "Mozilla/5.0 (compatible; DarwinPortfolio/1.0; research)"

# Dollar ADV thresholds for call-writing liquidity proxies
BUCKET_A_ADV = 50_000_000.0
BUCKET_B_ADV = 10_000_000.0
BUCKET_C_ADV = 2_000_000.0

# SPX names where listed options are routinely unavailable / thin enough to flag
KNOWN_NO_OPTIONS: set[str] = set()


def _bucket(adv: float | None) -> str:
    if adv is None or adv <= 0:
        return "D"
    if adv >= BUCKET_A_ADV:
        return "A"
    if adv >= BUCKET_B_ADV:
        return "B"
    if adv >= BUCKET_C_ADV:
        return "C"
    return "D"


def fetch_adv_dollar(yahoo_sym: str, lookback_days: int = 90) -> dict:
    """Return adv_shares, last_price, adv_dollar from Yahoo daily chart."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
        f"?range=3mo&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=25).read())
        result = payload["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        volumes = quote.get("volume") or []
        closes = quote.get("close") or []
        meta = result.get("meta") or {}
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return {"error": str(exc), "adv_shares": None, "last_price": None, "adv_dollar": None}

    pairs = [(v, c) for v, c in zip(volumes, closes) if v is not None and c is not None and v > 0 and c > 0]
    # Prefer last ~60 sessions
    pairs = pairs[-60:] if len(pairs) > 60 else pairs
    if not pairs:
        return {"error": "no_volume_bars", "adv_shares": None, "last_price": None, "adv_dollar": None}

    adv_shares = sum(v for v, _ in pairs) / len(pairs)
    last_price = float(pairs[-1][1])
    # Prefer meta price when present
    mpx = meta.get("regularMarketPrice")
    if isinstance(mpx, (int, float)) and mpx > 0:
        last_price = float(mpx)
    adv_dollar = adv_shares * last_price
    mcap = meta.get("marketCap")
    return {
        "error": None,
        "adv_shares": round(adv_shares, 2),
        "last_price": round(last_price, 4),
        "adv_dollar": round(adv_dollar, 2),
        "market_cap_usd": float(mcap) if isinstance(mcap, (int, float)) else None,
        "bars": len(pairs),
    }


def build_liquidity_map(
    tickers: list[str],
    sleep_s: float = 0.12,
    limit: int | None = None,
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    work = tickers[:limit] if limit else tickers
    for i, t in enumerate(work):
        ysym = yahoo_for_ticker(t, "US")
        # Yahoo wants BRK-B not BRK.B
        if "." in ysym and ysym.count(".") == 1 and not ysym.endswith((".TO", ".L", ".T", ".ST", ".HK", ".AX")):
            ysym = ysym.replace(".", "-")
        row = fetch_adv_dollar(ysym)
        adv = row.get("adv_dollar")
        bucket = _bucket(adv if isinstance(adv, (int, float)) else None)
        has_options = bucket in ("A", "B", "C") and t.upper() not in KNOWN_NO_OPTIONS
        if t.upper() in KNOWN_NO_OPTIONS:
            has_options = False
        out[t] = {
            "yahoo_symbol": ysym,
            "adv_shares": row.get("adv_shares"),
            "last_price": row.get("last_price"),
            "adv_dollar": row.get("adv_dollar"),
            "market_cap_usd": row.get("market_cap_usd"),
            "liquidity_bucket": bucket,
            "has_options": has_options,
            "bars": row.get("bars"),
            "error": row.get("error"),
        }
        if (i + 1) % 25 == 0 or i + 1 == len(work):
            print(f"  liquidity {i + 1}/{len(work)} …", flush=True)
        if sleep_s > 0:
            time.sleep(sleep_s)
    return out


def summarize(tickers_map: dict[str, dict]) -> dict:
    buckets = {"A": 0, "B": 0, "C": 0, "D": 0}
    errors = 0
    for row in tickers_map.values():
        buckets[row.get("liquidity_bucket") or "D"] = buckets.get(row.get("liquidity_bucket") or "D", 0) + 1
        if row.get("error"):
            errors += 1
    return {
        "bucket_counts": buckets,
        "eligible_ab": buckets.get("A", 0) + buckets.get("B", 0),
        "fetch_errors": errors,
        "ticker_count": len(tickers_map),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="Print summary of existing file only")
    ap.add_argument("--limit", type=int, default=None, help="Fetch only first N SPX tickers (dev)")
    ap.add_argument("--sleep", type=float, default=0.12, help="Seconds between Yahoo calls")
    args = ap.parse_args()

    if args.offline:
        if not OUT_PATH.exists():
            print(f"Missing {OUT_PATH}", file=sys.stderr)
            return 1
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        print(json.dumps({"as_of": data.get("as_of"), "summary": data.get("summary"), "path": str(OUT_PATH)}, indent=2))
        return 0

    if not SP500_PATH.exists():
        print(f"Missing constituents file {SP500_PATH}; run refresh_sp500_constituents.py first", file=sys.stderr)
        return 1

    spx = sorted(t for t in json.loads(SP500_PATH.read_text(encoding="utf-8")).get("tickers") or [])
    # Prefer canonical list order from file; aliases handled in universe loader
    print(f"Fetching ADV$ for {len(spx) if not args.limit else min(args.limit, len(spx))} S&P names…")
    tickers_map = build_liquidity_map(spx, sleep_s=args.sleep, limit=args.limit)
    summary = summarize(tickers_map)
    payload = {
        "as_of": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yahoo_chart_adv_proxy",
        "method": "ADV$ = mean(volume[-60:]) * last_close; buckets A/B/C/D",
        "thresholds_usd": {
            "A": BUCKET_A_ADV,
            "B": BUCKET_B_ADV,
            "C": BUCKET_C_ADV,
        },
        "eligible_buckets": ["A", "B"],
        "stale_after_days": 30,
        "summary": summary,
        "tickers": tickers_map,
    }
    # If --limit, merge into existing file when present so we don't wipe production
    if args.limit and OUT_PATH.exists():
        prior = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        merged = dict(prior.get("tickers") or {})
        merged.update(tickers_map)
        payload["tickers"] = merged
        payload["summary"] = summarize(merged)
        payload["note"] = f"partial_refresh_limit_{args.limit}"

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(json.dumps(payload["summary"], indent=2))
    print(f"Eligible A+B: {payload['summary']['eligible_ab']}")
    _ = load_sp500_tickers  # keep import used for API stability
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
