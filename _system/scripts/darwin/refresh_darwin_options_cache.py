#!/usr/bin/env python3
"""Champion-only Darwin options cache refresh (quota-safe).

Does NOT scrape full SPX. Pattern copied from etf-dashboard:
  cache-first · tiny symbol set · hard request budgets · merge prior.

Default behavior with no API keys:
  - Import overlapping symbols from etf-dashboard options_cache.json (free)
  - Write SSI local cache stub + coverage report
  - Synthetic IV remains available via realized vol in covered_call.py

With POLYGON_API_KEY / TRADIER_TOKEN:
  - Refresh ONLY --symbols (or current roth target weights / top liquid A names)
  - Caps: max 8 symbols/run, max ~20 Polygon + ~40 Tradier requests

Usage:
  python _system/scripts/darwin/refresh_darwin_options_cache.py
  python _system/scripts/darwin/refresh_darwin_options_cache.py --symbols AAPL,MSFT,NVDA
  python _system/scripts/darwin/refresh_darwin_options_cache.py --from-weights
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from darwin.options_cache import (  # noqa: E402
    LOCAL_CACHE,
    cache_coverage_report,
    load_etf_dashboard_cache,
    load_local_cache,
    save_local_cache,
)
from darwin.universe import load_liquidity_map  # noqa: E402

UA = "Mozilla/5.0 (compatible; DarwinOptions/1.0; research)"
POLYGON_KEY = (os.environ.get("POLYGON_API_KEY") or os.environ.get("POLYGON_IO_API_KEY") or "").strip()
TRADIER_TOKEN = (os.environ.get("TRADIER_TOKEN") or "").strip()
TRADIER_BASE = (os.environ.get("TRADIER_BASE_URL") or "https://api.tradier.com/v1").rstrip("/")

# Hard caps — never compete with etf-dashboard nightly budgets
MAX_SYMBOLS = int(os.environ.get("DARWIN_OPTIONS_MAX_SYMBOLS", "8"))
MAX_POLYGON = int(os.environ.get("DARWIN_OPTIONS_MAX_POLYGON", "20"))
MAX_TRADIER = int(os.environ.get("DARWIN_OPTIONS_MAX_TRADIER", "40"))


def _weights_symbols() -> list[str]:
    path = ROOT / "_system" / "portfolio" / "roth_target_weights.json"
    if not path.exists():
        path = ROOT / "dashboard" / "data" / "darwin_portfolio_roth.json"
        if path.exists():
            port = json.loads(path.read_text(encoding="utf-8"))
            return [w["ticker"] for w in (port.get("weights") or []) if w.get("ticker")]
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("weights") or data.get("targets") or []
    if isinstance(rows, dict):
        return sorted(rows.keys(), key=lambda t: -float(rows[t]))[:MAX_SYMBOLS]
    out = []
    for r in rows:
        if isinstance(r, dict) and r.get("ticker"):
            out.append(r["ticker"])
        elif isinstance(r, str):
            out.append(r)
    return out[:MAX_SYMBOLS]


def _top_liquid_a(n: int = 8) -> list[str]:
    m = load_liquidity_map()
    a_names = [t for t, row in m.items() if str(row.get("liquidity_bucket")).upper() == "A" and "." not in t]
    # Prefer shorter tickers already in cache order; stable sort by adv
    a_names = sorted(
        set(a_names),
        key=lambda t: -float((m.get(t) or {}).get("adv_dollar") or 0),
    )
    return a_names[:n]


def _http_json(url: str, headers: dict | None = None) -> dict | None:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=25).read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def fetch_polygon_snapshot(sym: str, counters: dict) -> dict | None:
    if not POLYGON_KEY or counters["polygon"] >= MAX_POLYGON:
        return None
    url = (
        f"https://api.polygon.io/v3/snapshot/options/{urllib.parse.quote(sym)}"
        f"?apiKey={POLYGON_KEY}&limit=250"
    )
    counters["polygon"] += 1
    data = _http_json(url)
    if not data:
        return None
    results = data.get("results") or []
    options = []
    spot = None
    for r in results:
        details = r.get("details") or {}
        greeks = r.get("greeks") or {}
        day = r.get("day") or {}
        quote = r.get("last_quote") or {}
        bid = quote.get("bid")
        ask = quote.get("ask")
        mid = None
        if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask >= bid > 0:
            mid = (bid + ask) / 2.0
        elif isinstance(day.get("close"), (int, float)):
            mid = float(day["close"])
        iv = greeks.get("iv") or r.get("implied_volatility")
        options.append(
            {
                "ticker": details.get("ticker") or r.get("ticker"),
                "expiration_date": details.get("expiration_date"),
                "strike_price": details.get("strike_price"),
                "contract_type": details.get("contract_type"),
                "mid": mid,
                "iv": float(iv) if isinstance(iv, (int, float)) else None,
                "delta": greeks.get("delta"),
            }
        )
        und = r.get("underlying_asset") or {}
        if spot is None and isinstance(und.get("price"), (int, float)):
            spot = float(und["price"])
    return {
        "spot": spot,
        "options": options,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "polygon_snapshot",
    }


def fetch_tradier_chain(sym: str, counters: dict) -> dict | None:
    if not TRADIER_TOKEN or counters["tradier"] >= MAX_TRADIER:
        return None
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json", "User-Agent": UA}
    exp_url = f"{TRADIER_BASE}/markets/options/expirations?symbol={urllib.parse.quote(sym)}"
    counters["tradier"] += 1
    exp_data = _http_json(exp_url, headers)
    if not exp_data:
        return None
    exps = ((exp_data.get("expirations") or {}).get("date")) or []
    if isinstance(exps, str):
        exps = [exps]
    exps = list(exps)[:4]
    options = []
    spot = None
    # spot quote
    if counters["tradier"] < MAX_TRADIER:
        q = _http_json(f"{TRADIER_BASE}/markets/quotes?symbols={urllib.parse.quote(sym)}", headers)
        counters["tradier"] += 1
        if q:
            quote = ((q.get("quotes") or {}).get("quote")) or {}
            if isinstance(quote, list):
                quote = quote[0] if quote else {}
            last = quote.get("last") or quote.get("close")
            if isinstance(last, (int, float)):
                spot = float(last)
    for exp in exps:
        if counters["tradier"] >= MAX_TRADIER:
            break
        chain_url = (
            f"{TRADIER_BASE}/markets/options/chains?symbol={urllib.parse.quote(sym)}"
            f"&expiration={exp}&greeks=true"
        )
        counters["tradier"] += 1
        chain = _http_json(chain_url, headers)
        if not chain:
            continue
        opts = ((chain.get("options") or {}).get("option")) or []
        if isinstance(opts, dict):
            opts = [opts]
        for o in opts:
            bid, ask = o.get("bid"), o.get("ask")
            mid = None
            if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask >= bid > 0:
                mid = (bid + ask) / 2.0
            greeks = o.get("greeks") or {}
            options.append(
                {
                    "ticker": o.get("symbol"),
                    "expiration_date": o.get("expiration_date"),
                    "strike_price": o.get("strike"),
                    "contract_type": o.get("option_type"),
                    "mid": mid,
                    "iv": greeks.get("mid_iv") or greeks.get("smv_vol"),
                    "delta": greeks.get("delta"),
                }
            )
        time.sleep(0.15)
    if not options:
        return None
    return {
        "spot": spot,
        "options": options,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "tradier_chain",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default="", help="Comma-separated tickers")
    ap.add_argument("--from-weights", action="store_true", help="Use roth target weights")
    ap.add_argument("--import-etf-only", action="store_true", help="No live API; copy overlaps from etf-dashboard")
    args = ap.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.from_weights:
        symbols = [s.upper() for s in _weights_symbols()]
    else:
        symbols = [s.upper() for s in _weights_symbols()] or _top_liquid_a(MAX_SYMBOLS)
    symbols = symbols[:MAX_SYMBOLS]

    prior_local = load_local_cache()
    prior_syms = dict(prior_local.get("symbols") or {})
    etf = load_etf_dashboard_cache()
    etf_syms = dict(etf.get("symbols") or {})

    # Free import: any requested symbol already in etf-dashboard cache
    for t in symbols:
        if t in etf_syms and t not in prior_syms:
            prior_syms[t] = {**etf_syms[t], "imported_from": "etf_dashboard"}

    counters = {"polygon": 0, "tradier": 0}
    errors: dict[str, str] = {}
    live = bool(POLYGON_KEY or TRADIER_TOKEN) and not args.import_etf_only

    if live:
        print(f"Live refresh for {symbols} (polygon_cap={MAX_POLYGON}, tradier_cap={MAX_TRADIER})")
        for t in symbols:
            payload = fetch_tradier_chain(t, counters) if TRADIER_TOKEN else None
            if not payload and POLYGON_KEY:
                payload = fetch_polygon_snapshot(t, counters)
            if payload and (payload.get("options") or []):
                prior_syms[t] = payload
                print(f"  {t}: {len(payload['options'])} contracts via {payload.get('source')}")
            else:
                errors[t] = "fetch_failed_kept_prior" if t in prior_syms else "fetch_failed"
                print(f"  {t}: {errors[t]}")
            time.sleep(0.2)
    else:
        print("No API keys or --import-etf-only: writing cache from etf-dashboard overlaps + prior local")

    # Also keep any etf overlaps for symbols we care about even if not in refresh list
    for t, row in etf_syms.items():
        if t in symbols and t not in prior_syms:
            prior_syms[t] = {**row, "imported_from": "etf_dashboard"}

    payload = {
        "build_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "darwin_champion_cache",
        "polygon_api_configured": bool(POLYGON_KEY),
        "tradier_api_configured": bool(TRADIER_TOKEN),
        "requested_symbols": symbols,
        "refresh_symbols": symbols if live else [],
        "polygon_requests_used": counters["polygon"],
        "tradier_requests_used": counters["tradier"],
        "errors_by_symbol": errors,
        "quota_note": (
            "Champion-only cache. Prefer etf-dashboard overlaps (free). "
            "Live fetch uses hard caps; never full SPX."
        ),
        "symbols": prior_syms,
    }
    path = save_local_cache(payload)
    report = cache_coverage_report(symbols)
    print(f"Wrote {path}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
