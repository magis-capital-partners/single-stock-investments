#!/usr/bin/env python3
"""USD return blocks for Michael's sleeve time-average panel.

Reads no Gateway. Uses fetch_yahoo_history from the technicals builder.
Writes dashboard/data/time_average_growth_params.json. Does not write the panel.
A failed fetch keeps the previous block for that symbol and marks it stale.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_technical_signals import fetch_yahoo_history  # noqa: E402

OUT = ROOT / "dashboard" / "data" / "time_average_growth_params.json"
WINDOW = 252
# A foreign listing can enter the mix short of a full US year. The panel
# still withholds the scale until the shared window is 252 sessions.
MIN_SESSIONS = 200

# Michael sleeve symbols as of the 2026-10-07 book. The live weights come
# from the sleeve API; this list is only what we estimate.
DEFAULT_TICKERS = [
    "GTX", "JPM", "HEI-A", "CSU", "QDEL", "MCO", "TBBK", "POST", "SHC", "MCHB",
    "MEHCQ.ESC", "COLD", "FTRE", "ASPN", "3905.T", "TOI", "GPGI", "CORBF", "FIHO12",
    "WEST", "BRBR", "BUR", "LMN", "EQPT", "GS", "FNMAP", "CSU.DB", "FLXN.CVR", "INV",
    "FMCCK", "WATR", "FMCCL", "FNMAO", "HL", "JL80", "FLUX", "GDRZF", "EFOR", "ECHO",
    "AXTQ", "MRTX.CVR", "XTIA", "SKHQ", "B", "COHQ", "CHTR", "ECHX", "MACK", "NAN",
    "ABMD.CVR", "GKTX.PS1", "GKTX.PS2", "GKTX.PS3", "PRVL.CVR", "CSU.WTS", "AKUS.CNT",
    "BFFI.ESC", "LENS.MRG",
]

CANDIDATES = {
    "CSU": ["CSU.TO"],
    "TOI": ["TOI.V", "TOI.TO", "TOI"],
    "FIHO12": ["FIHO12.MX"],
    "LMN": ["LMN.V", "LMN.TO"],
    "3905.T": ["3905.T"],
    "HEI-A": ["HEI-A"],
}


def structural_reason(ticker: str) -> str | None:
    upper = ticker.upper()
    if upper.endswith((".ESC", ".CVR", ".WTS", ".DB", ".CNT", ".MRG")):
        return "not_stock"
    if ".PS" in upper:
        return "not_stock"
    return None


def fx_symbol(yahoo: str) -> str | None:
    if yahoo.endswith((".TO", ".V")):
        return "CAD=X"
    if yahoo.endswith(".T"):
        return "JPY=X"
    if yahoo.endswith(".MX"):
        return "MXN=X"
    return None


def usd_series(local_rows: list[tuple[str, float]], fx_rows: list[tuple[str, float]] | None) -> list[tuple[str, float]]:
    """Convert local adjusted closes to USD. FX is units of local currency per dollar."""
    if not fx_rows:
        return list(local_rows)
    fx = {day: price for day, price in fx_rows if price and price > 0}
    ordered = sorted(fx)
    out = []
    for day, price in local_rows:
        rate = fx.get(day)
        if rate is None:
            prior = [item for item in ordered if item <= day]
            if not prior:
                continue
            last = prior[-1]
            gap = (datetime.fromisoformat(day) - datetime.fromisoformat(last)).days
            if gap > 5:
                continue
            rate = fx[last]
        out.append((day, price / rate))
    return out


def simple_returns(prices: list[tuple[str, float]]) -> list[dict]:
    rows = []
    previous = None
    for day, price in prices:
        if previous and previous > 0 and price > 0:
            rows.append({"date": day, "r": price / previous - 1.0})
        previous = price
    return rows[-WINDOW:]


def asset_moments(returns: list[dict]) -> tuple[float | None, float | None]:
    logs = []
    for row in returns:
        value = row["r"]
        if value > -0.999:
            logs.append(math.log1p(value))
    if len(logs) < 2:
        return None, None
    center = sum(logs) / len(logs)
    var = sum((item - center) ** 2 for item in logs) / (len(logs) - 1)
    sigma = math.sqrt(var) * math.sqrt(WINDOW)
    growth = center * WINDOW
    return growth + 0.5 * sigma * sigma, sigma


def _closes(symbol: str) -> list[tuple[str, float]]:
    rows, _source = fetch_yahoo_history(symbol)
    return [(row["date"], float(row["close"])) for row in rows if row.get("close")]


def fred_bill() -> tuple[str, float, float]:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
    request = urllib.request.Request(url, headers={"User-Agent": "magis-research/time-average"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    last = None
    for line in text.splitlines()[1:]:
        day, raw = (line.split(",") + [""])[:2]
        raw = raw.strip()
        if not day or raw in {"", "."}:
            continue
        last = (day, float(raw))
    if last is None:
        raise RuntimeError("DGS3MO returned no yield")
    day, percent = last
    return day, percent / 100.0, math.log1p(percent / 100.0)


def estimate_symbol(ticker: str, fx_cache: dict) -> dict:
    reason = structural_reason(ticker)
    if reason:
        return {"ok": False, "reason": "not_stock"}
    errors = []
    for symbol in CANDIDATES.get(ticker, [ticker]):
        try:
            local = _closes(symbol)
        except Exception as error:  # network or a short chart
            errors.append(f"{symbol}: {error}")
            continue
        fx_name = fx_symbol(symbol)
        fx_rows = None
        if fx_name:
            if fx_name not in fx_cache:
                try:
                    fx_cache[fx_name] = _closes(fx_name)
                except Exception as error:
                    return {"ok": False, "reason": "missing_fx", "detail": f"{fx_name}: {error}"}
            fx_rows = fx_cache[fx_name]
        usd = usd_series(local, fx_rows)
        returns = simple_returns(usd)
        if len(returns) < MIN_SESSIONS:
            errors.append(f"{symbol}: {len(returns)} sessions")
            continue
        mu, sigma = asset_moments(returns)
        return {
            "ok": True,
            "yahoo": symbol,
            "currency": "USD",
            "fx": fx_name,
            "start": returns[0]["date"],
            "end": returns[-1]["date"],
            "n": len(returns),
            "mu": mu,
            "sigma": sigma,
            "stale": False,
            "returns": returns,
        }
    detail = "; ".join(errors) or "no candidate"
    if "missing_fx" in detail:
        return {"ok": False, "reason": "missing_fx", "detail": detail}
    return {"ok": False, "reason": "short_history", "detail": detail}


def load_previous() -> dict:
    if not OUT.exists():
        return {}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build(tickers: list[str]) -> dict:
    previous = load_previous()
    old_symbols = previous.get("symbols") or {}
    try:
        as_of, annual, continuous = fred_bill()
        riskless = {"series": "DGS3MO", "as_of": as_of, "yield": annual, "continuous": continuous}
    except Exception:
        riskless = previous.get("riskless") or {"series": "DGS3MO", "as_of": None, "yield": None, "continuous": None}
    fx_cache: dict = {}
    symbols = {}
    for ticker in tickers:
        try:
            block = estimate_symbol(ticker, fx_cache)
        except Exception as error:
            block = {"ok": False, "reason": "short_history", "detail": str(error)}
        if block.get("ok"):
            symbols[ticker] = block
            print(f"ok {ticker} via {block['yahoo']} n={block['n']}")
            continue
        old = old_symbols.get(ticker)
        if old and old.get("ok") and old.get("returns"):
            kept = dict(old)
            kept["stale"] = True
            symbols[ticker] = kept
            print(f"stale {ticker} ({block.get('reason')})")
            continue
        symbols[ticker] = block
        print(f"omit {ticker} {block.get('reason')}")
    return {
        "schema_version": 1,
        "owner": "michael",
        "research_only": True,
        "in_base_irr": False,
        "authority": "none",
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "riskless": riskless,
        "symbols": symbols,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", default=None)
    args = parser.parse_args()
    payload = build(args.tickers or DEFAULT_TICKERS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
