#!/usr/bin/env python3
"""Roll forward filed book value to a current mark-to-market estimate.

Usage:
  python _system/scripts/current_book_estimate.py FRMO
  python _system/scripts/current_book_estimate.py CMSG --write
  python _system/scripts/current_book_estimate.py --all --write
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_NAME = "book_estimate_config.json"
OUTPUT_NAME = "book_estimate.json"
STOOQ_URL = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
)
UA = "Mozilla/5.0 (compatible; MarvinBookEstimate/1.0)"
YAHOO_UA = "Mozilla/5.0 (compatible; MarvinBookEstimate/1.0)"


def yahoo_ticker(symbol: str) -> str:
    sym = symbol.upper().replace(".US", "")
    return sym


def measurement_date_for_period_end(period_end: str) -> str:
    """Last calendar day on or before period_end that is Mon–Fri (NYSE proxy)."""
    d = datetime.strptime(period_end, "%Y-%m-%d").date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def fetch_yahoo_close(symbol: str, on_date: str) -> tuple[float | None, str | None]:
    ysym = yahoo_ticker(symbol)
    dt = datetime.strptime(on_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = int(dt.timestamp())
    end = start + 86400 * 7
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}"
        f"?period1={start}&period2={end}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if d >= on_date:
                return float(close), None
        return None, f"no close on or after {on_date}"
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return None, str(exc)


def enrich_line_for_measurement(
    line: dict,
    measurement_date: str,
    hist_cache: dict[str, tuple[float | None, str | None]],
) -> tuple[dict, dict | None]:
    """Resolve filing_price on measurement_date; compute implied shares when needed."""
    enriched = dict(line)
    alignment: dict | None = None
    method = line.get("method", "static")
    symbol = line.get("symbol")

    if symbol and method in ("listed_shares", "fund_weight_proxy", "ownership_market_value"):
        key = f"{symbol}|{measurement_date}"
        if key not in hist_cache:
            hist_cache[key] = fetch_yahoo_close(symbol, measurement_date)
        fetched, err = hist_cache[key]
        manual = line.get("filing_price")
        use_auto = line.get("filing_price_auto", True)
        if fetched is not None and (use_auto or manual is None):
            enriched["filing_price"] = round(fetched, 4)
            enriched["filing_price_source"] = f"Yahoo {yahoo_ticker(symbol)} {measurement_date}"
        elif manual is not None:
            enriched["filing_price_source"] = line.get(
                "filing_price_source", f"manual (config); verify {measurement_date}"
            )
        if fetched is not None and manual is not None:
            diff_pct = abs(fetched - manual) / manual * 100 if manual else 0
            if diff_pct > 2:
                alignment = {
                    "id": line.get("id"),
                    "symbol": symbol,
                    "measurement_date": measurement_date,
                    "config_filing_price": manual,
                    "fetched_filing_price": round(fetched, 4),
                    "diff_pct": round(diff_pct, 1),
                    "severity": "warning" if diff_pct < 10 else "error",
                    "note": "filing_price must match measurement_date per mark_date_alignment.md",
                }
        if err and fetched is None and manual is None:
            alignment = {
                "id": line.get("id"),
                "symbol": symbol,
                "measurement_date": measurement_date,
                "severity": "error",
                "note": f"could not fetch filing price: {err}",
            }

    if method == "listed_shares" and enriched.get("filing_value_m") and not enriched.get("shares"):
        fp = enriched.get("filing_price")
        if fp:
            implied = float(enriched["filing_value_m"]) * 1_000_000 / float(fp)
            enriched["shares"] = int(round(implied))
            enriched["shares_implied_from_filing"] = True

    enriched["filing_price_date"] = measurement_date
    return enriched, alignment


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def round_m(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def round_sh(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def fetch_stooq_close(symbol: str) -> tuple[float | None, str | None]:
    sym = symbol.upper()
    if not sym.endswith(".US") and "." not in sym:
        sym = f"{sym}.US"
    url = STOOQ_URL.format(symbol=sym.lower())
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError) as exc:
        return None, str(exc)
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return None, "empty response"
    parts = lines[1].split(",")
    if len(parts) < 7:
        return None, "unexpected csv shape"
    close = parts[6].strip()
    if close in ("", "N/D", "N/A"):
        return None, "no quote"
    try:
        return float(close), None
    except ValueError:
        return None, f"bad close: {close}"


def fetch_coingecko_usd(coin_id: str) -> tuple[float | None, str | None]:
    url = COINGECKO_URL.format(ids=coin_id)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)
    price = (data.get(coin_id) or {}).get("usd")
    if price is None:
        return None, "missing coin id"
    return float(price), None


def filing_value_from_line(line: dict) -> float | None:
    if line.get("filing_value_m") is not None:
        return float(line["filing_value_m"])
    method = line.get("method", "static")
    if method == "listed_shares":
        shares = line.get("shares")
        price = line.get("filing_price")
        if shares is not None and price is not None:
            return shares * float(price) / 1_000_000
    if method == "crypto_units":
        units = line.get("units")
        price = line.get("filing_unit_price")
        if units is not None and price is not None:
            return units * float(price) / 1_000_000
    if method == "fund_weight_proxy":
        parent = line.get("parent_filing_value_m")
        weight = line.get("weight_pct")
        if parent is not None and weight is not None:
            return float(parent) * float(weight) / 100.0
    return None


def resolve_price(line: dict, cache: dict[str, float | None]) -> tuple[float | None, str, str | None]:
    method = line.get("method", "static")
    if method == "static":
        return None, "static", None
    if method == "manual_price":
        mp = line.get("current_price")
        if mp is not None:
            return float(mp), "manual", None
        return None, "manual", "current_price missing"

    if method == "crypto_units":
        coin_id = line.get("coingecko_id")
        if not coin_id:
            return None, "coingecko", "coingecko_id missing"
        if coin_id not in cache:
            cache[coin_id], err = fetch_coingecko_usd(coin_id)
            if err:
                cache[f"{coin_id}__err"] = err
        return cache.get(coin_id), "coingecko", cache.get(f"{coin_id}__err")

    symbol = line.get("symbol")
    if not symbol:
        return None, "none", "symbol missing"
    key = symbol.upper()
    if key not in cache:
        cache[key], err = fetch_stooq_close(symbol)
        if err:
            cache[f"{key}__err"] = err
    return cache.get(key), "stooq", cache.get(f"{key}__err")


def current_value_from_line(line: dict, current_price: float | None) -> float | None:
    method = line.get("method", "static")
    filing_val = filing_value_from_line(line)

    if method == "static":
        return filing_val

    if method in ("listed_shares", "manual_price"):
        shares = line.get("shares")
        filing_price = line.get("filing_price")
        if shares is None:
            return filing_val
        if current_price is not None:
            return float(shares) * current_price / 1_000_000
        if filing_val is not None and filing_price:
            return filing_val
        return filing_val

    if method == "crypto_units":
        units = line.get("units")
        filing_unit_price = line.get("filing_unit_price")
        if units is None:
            return filing_val
        if current_price is not None:
            return float(units) * current_price / 1_000_000
        if filing_val is not None and filing_unit_price:
            return filing_val
        return filing_val

    if method == "fund_weight_proxy":
        parent = line.get("parent_filing_value_m")
        weight = line.get("weight_pct")
        filing_price = line.get("filing_price")
        if parent is None or weight is None or filing_price in (None, 0):
            return filing_val
        filing_slice = float(parent) * float(weight) / 100.0
        if current_price is None:
            return filing_slice
        ratio = current_price / float(filing_price)
        return filing_slice * ratio

    if method == "ownership_market_value":
        pct = line.get("ownership_pct")
        shares_out = line.get("shares_outstanding")
        filing_price = line.get("filing_price")
        carrying = line.get("filing_carrying_value_m")
        if pct is None or shares_out is None:
            return line.get("filing_carrying_value_m") or filing_val
        if current_price is not None and filing_price:
            current_mcap_m = float(shares_out) * current_price / 1_000_000
            return current_mcap_m * float(pct) / 100.0
        return carrying or filing_val

    return filing_val


def delta_for_line(line: dict, filing_value_m: float | None, current_value_m: float | None) -> float | None:
    method = line.get("method", "static")
    if filing_value_m is None or current_value_m is None:
        if method == "ownership_market_value" and line.get("filing_carrying_value_m") is not None:
            if current_value_m is not None:
                return current_value_m - float(line["filing_carrying_value_m"])
        return None
    return current_value_m - filing_value_m


def compute_line(line: dict, cache: dict[str, float | None]) -> dict[str, Any]:
    method = line.get("method", "static")
    filing_value_m = filing_value_from_line(line)
    current_price, price_source, price_error = resolve_price(line, cache)
    current_value_m = current_value_from_line(line, current_price)

    delta_m = delta_for_line(line, filing_value_m, current_value_m)

    out: dict[str, Any] = {
        "id": line.get("id"),
        "label": line.get("label"),
        "method": method,
        "source": line.get("source"),
        "filing_value_m": round_m(filing_value_m),
        "current_value_m": round_m(current_value_m),
        "delta_m": round_m(delta_m),
        "price_source": price_source,
    }
    if line.get("symbol"):
        out["symbol"] = line["symbol"]
    if line.get("coingecko_id"):
        out["coingecko_id"] = line["coingecko_id"]
    if current_price is not None:
        out["current_price"] = round(current_price, 4)
        out["current_price_date"] = str(date.today())
    if line.get("filing_price") is not None:
        out["filing_price"] = line["filing_price"]
    if line.get("filing_price_date"):
        out["filing_price_date"] = line["filing_price_date"]
    if line.get("filing_price_source"):
        out["filing_price_source"] = line["filing_price_source"]
    if line.get("shares_implied_from_filing"):
        out["shares_implied_from_filing"] = True
    if line.get("shares") is not None:
        out["shares"] = line["shares"]
    if line.get("units") is not None:
        out["units"] = line["units"]
    if line.get("weight_pct") is not None:
        out["weight_pct"] = line["weight_pct"]
    if price_error:
        out["price_error"] = price_error
    if method == "ownership_market_value" and line.get("filing_carrying_value_m") is not None:
        out["filing_carrying_value_m"] = line["filing_carrying_value_m"]
        if out.get("filing_value_m") is None:
            out["filing_value_m"] = round_m(float(line["filing_carrying_value_m"]))
    if line.get("human_review"):
        out["human_review"] = True
    return out


def compute_book_estimate(config: dict, as_of: str | None = None) -> dict:
    anchor = config["filing_anchor"]
    period_end = anchor.get("period_end", "")
    measurement_date = anchor.get("measurement_date") or measurement_date_for_period_end(period_end)

    hist_cache: dict[str, tuple[float | None, str | None]] = {}
    price_alignment: list[dict] = []
    enriched_lines: list[dict] = []
    for line in config.get("lines", []):
        enriched, align = enrich_line_for_measurement(line, measurement_date, hist_cache)
        enriched_lines.append(enriched)
        if align:
            price_alignment.append(align)

    shares = float(anchor["shares"])
    filed_equity_m = float(anchor["book_equity_m"])
    filed_book_ps = filed_equity_m * 1_000_000 / shares

    cache: dict[str, float | None] = {}
    computed_lines = [compute_line(line, cache) for line in enriched_lines]

    delta_sum_m = sum(
        ln["delta_m"] for ln in computed_lines if ln.get("delta_m") is not None
    )
    current_equity_m = filed_equity_m + delta_sum_m
    current_book_ps = current_equity_m * 1_000_000 / shares
    delta_ps = current_book_ps - filed_book_ps

    markable_filing_m = sum(
        ln["filing_value_m"] for ln in computed_lines if ln.get("filing_value_m") is not None
    )
    static_residual_m = round_m(filed_equity_m - markable_filing_m)

    staleness: list[str] = []
    for ln in computed_lines:
        if ln.get("price_error"):
            staleness.append(f"{ln['id']}: {ln['price_error']}")
        if ln.get("human_review"):
            staleness.append(f"{ln['id']}: [HUMAN REVIEW]")
    for pa in price_alignment:
        if pa.get("severity") == "error":
            staleness.append(
                f"{pa.get('id')}: price alignment — {pa.get('note', pa)}"
            )

    price = config.get("market_price")
    price_source = config.get("market_price_source")
    comparisons: dict[str, Any] = {}
    if price is not None:
        price = float(price)
        comparisons = {
            "market_price": price,
            "market_price_source": price_source,
            "discount_to_filed_book_pct": round((filed_book_ps - price) / filed_book_ps * 100, 1)
            if filed_book_ps
            else None,
            "discount_to_current_estimate_pct": round(
                (current_book_ps - price) / current_book_ps * 100, 1
            )
            if current_book_ps
            else None,
            "premium_to_filed_book_pct": round((price - filed_book_ps) / filed_book_ps * 100, 1)
            if filed_book_ps and price > filed_book_ps
            else None,
        }

    return {
        "ticker": config.get("ticker"),
        "as_of": as_of or str(date.today()),
        "framework": "current_book_estimate.md",
        "mark_date_framework": "mark_date_alignment.md",
        "filing_anchor": {
            "period_end": anchor.get("period_end"),
            "measurement_date": measurement_date,
            "source": anchor.get("source"),
            "scope": anchor.get("scope"),
            "book_equity_m": filed_equity_m,
            "shares": int(shares) if shares == int(shares) else shares,
            "filed_book_per_share": round_sh(filed_book_ps),
        },
        "lines": computed_lines,
        "price_alignment": price_alignment,
        "tie_out": {
            "markable_filing_sum_m": round_m(markable_filing_m),
            "static_residual_m": static_residual_m,
            "note": "static_residual = filed equity minus sum of line filing values; should be >= 0",
        },
        "summary": {
            "delta_equity_m": round_m(delta_sum_m),
            "delta_per_share": round_sh(delta_ps),
            "delta_pct_of_filed_book": round(delta_ps / filed_book_ps * 100, 2)
            if filed_book_ps
            else None,
            "current_book_equity_m": round_m(current_equity_m),
            "current_book_per_share": round_sh(current_book_ps),
        },
        "price_comparison": comparisons,
        "staleness_flags": staleness,
    }


def sync_valuation_json(ticker: str, result: dict) -> None:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        return
    val = load_json(val_path)
    summary = result["summary"]
    anchor = result["filing_anchor"]
    comp = result.get("price_comparison") or {}

    val["book_estimate"] = {
        "as_of": result["as_of"],
        "filing_period_end": anchor["period_end"],
        "filing_source": anchor["source"],
        "filed_book_per_share": anchor["filed_book_per_share"],
        "current_book_per_share": summary["current_book_per_share"],
        "delta_per_share": summary["delta_per_share"],
        "delta_pct_of_filed_book": summary["delta_pct_of_filed_book"],
        "discount_to_filed_book_pct": comp.get("discount_to_filed_book_pct"),
        "discount_to_current_estimate_pct": comp.get("discount_to_current_estimate_pct"),
        "config_path": f"{ticker}/research/book_estimate_config.json",
        "output_path": f"{ticker}/research/book_estimate.json",
    }

    inputs = val.setdefault("inputs", {})
    gate = val.get("optionality_gate")
    if gate and gate.get("floor_metric") == "book_per_share":
        gate["floor_value_filed"] = anchor["filed_book_per_share"]
        gate["floor_value_current"] = summary["current_book_per_share"]
        gate["floor_value"] = summary["current_book_per_share"]
        inputs["book_per_share_filed"] = anchor["filed_book_per_share"]
        inputs["book_per_share_current"] = summary["current_book_per_share"]
        inputs["book_per_share"] = summary["current_book_per_share"]
        if comp.get("discount_to_current_estimate_pct") is not None:
            gate["discount_to_current_book_pct"] = comp["discount_to_current_estimate_pct"]

    write_json(val_path, val)


def config_path_for(ticker: str) -> Path:
    return ROOT / ticker / "research" / CONFIG_NAME


def output_path_for(ticker: str) -> Path:
    return ROOT / ticker / "research" / OUTPUT_NAME


def tickers_with_config() -> list[str]:
    out: list[str] = []
    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith(("_", ".")):
            continue
        if (p / "research" / CONFIG_NAME).exists():
            out.append(p.name)
    return sorted(out)


def run_ticker(ticker: str, *, write: bool, sync_valuation: bool) -> dict | None:
    cfg_path = config_path_for(ticker)
    if not cfg_path.exists():
        print(f"SKIP {ticker}: no {CONFIG_NAME}", file=sys.stderr)
        return None
    config = load_json(cfg_path)
    if not config.get("enabled", True):
        print(f"SKIP {ticker}: disabled in config", file=sys.stderr)
        return None

    val_path = ROOT / ticker / "research" / "valuation.json"
    if config.get("market_price") is None and val_path.exists():
        val = load_json(val_path)
        inputs = val.get("inputs") or {}
        if inputs.get("price") is not None:
            config["market_price"] = inputs["price"]
            config["market_price_source"] = inputs.get("price_source")

    result = compute_book_estimate(config)
    out_path = output_path_for(ticker)

    if write:
        write_json(out_path, result)
        print(f"Wrote {out_path.relative_to(ROOT)}")
        if sync_valuation:
            sync_valuation_json(ticker, result)
            if val_path.exists():
                print(f"Updated {val_path.relative_to(ROOT)} book_estimate section")
    else:
        print(json.dumps(result, indent=2))

    s = result["summary"]
    a = result["filing_anchor"]
    print(
        f"{ticker}: filed ${a['filed_book_per_share']}/sh "
        f"→ current ${s['current_book_per_share']}/sh "
        f"(Δ ${s['delta_per_share']}/sh, {s['delta_pct_of_filed_book']}%)"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Current book value mark-to-market estimate")
    parser.add_argument("ticker", nargs="?", help="Ticker symbol")
    parser.add_argument("--all", action="store_true", help="Run all tickers with config")
    parser.add_argument("--write", action="store_true", help="Write book_estimate.json")
    parser.add_argument(
        "--no-sync-valuation",
        action="store_true",
        help="Do not update valuation.json book_estimate section",
    )
    args = parser.parse_args()

    if args.all:
        tickers = tickers_with_config()
        if not tickers:
            print("No tickers with book_estimate_config.json found", file=sys.stderr)
            return 1
        rc = 0
        for t in tickers:
            if run_ticker(t, write=args.write, sync_valuation=not args.no_sync_valuation) is None:
                rc = 1
        return rc

    if not args.ticker:
        parser.error("Provide TICKER or --all")

    ticker = args.ticker.upper()
    if run_ticker(ticker, write=args.write, sync_valuation=not args.no_sync_valuation) is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
