#!/usr/bin/env python3
"""Fetch fresh commodity / macro spot inputs for valuation overlays."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import ticker_needs_commodity_inputs  # noqa: E402

COMMODITY_DIR = ROOT / "_system" / "reference" / "market-data" / "commodities"
UA = "MarvinResearch/1.0 (market-inputs)"
STOOQ_URL = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
TODAY = date.today().isoformat()

DEFAULT_SYMBOLS = {
    "copper": {"stooq": "hg.f", "cents_if_close_gt": 50},
}

TICKER_SYMBOLS: dict[str, list[str]] = {
    "KEWL": ["copper"],
    "MSB": ["copper"],
}


def tickers_for_market_merge(explicit: list[str] | None = None) -> list[str]:
    """Registry tickers that need commodity market_inputs merge."""
    if explicit:
        return [t.upper() for t in explicit]
    out: set[str] = set(TICKER_SYMBOLS.keys())
    for td in ROOT.iterdir():
        if not td.is_dir() or td.name.startswith(("_", ".")):
            continue
        vp = td / "research" / "valuation.json"
        if not vp.exists():
            continue
        try:
            val = json.loads(vp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        er = val.get("evidence_refresh") or {}
        if er.get("type") == "commodity_nav":
            out.add(td.name.upper())
            commodity = er.get("commodity", "copper")
            TICKER_SYMBOLS.setdefault(td.name.upper(), [commodity])
    return sorted(out)


def fetch_stooq(symbol: str) -> tuple[float | None, str | None, str | None]:
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
    quote_date = parts[1] if len(parts) > 1 else TODAY
    try:
        close = float(parts[6].strip())
    except ValueError:
        return None, None, "no close"
    return close, quote_date, None


def spot_usd_per_lb(cid: str, close: float, meta: dict) -> float:
    if cid == "copper" and close > meta.get("cents_if_close_gt", 50):
        return round(close / 100.0, 4)
    return round(close, 4)


def scenario_grid(spot: float) -> dict:
    return {
        "bear": {"copper_usd_per_lb": round(spot * 0.72, 2), "label": "trough (~28% below spot)"},
        "base": {"copper_usd_per_lb": None, "label": "spot at compute"},
        "bull": {"copper_usd_per_lb": round(spot * 1.08, 2), "label": "cycle high (~8% above spot)"},
    }


def royalty_at_price(base_usd: float, base_lb: float, spot_lb: float) -> float:
    if base_lb <= 0:
        return base_usd
    return round(base_usd * (spot_lb / base_lb), 0)


def _load_valuation(ticker: str) -> dict | None:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        return None
    return json.loads(val_path.read_text(encoding="utf-8"))


def commodity_ids_for_ticker(ticker: str, val: dict | None = None) -> list[str]:
    """Commodities to merge for this ticker; empty for operating names without overlays."""
    t = ticker.upper()
    if t in TICKER_SYMBOLS:
        return list(TICKER_SYMBOLS[t])
    val = val if val is not None else _load_valuation(t)
    if val is None:
        return []
    if not ticker_needs_commodity_inputs(val):
        return []
    er = val.get("evidence_refresh") or {}
    return [str(er.get("commodity") or "copper")]


COPPER_VALUATION_INPUT_KEYS = (
    "copper_spot_usd_per_lb",
    "copper_spot_as_of",
    "copper_spot_source",
    "copperwood_royalty_est_usd",
    "copperwood_royalty_est_usd_ssi_ref",
    "copperwood_royalty_est_usd_at_spot",
    "copperwood_royalty_note",
)


def strip_commodity_pollution(val: dict) -> dict:
    """Remove mistaken copper / copperwood keys from non-commodity valuations."""
    inputs = val.get("inputs") or {}
    for key in list(inputs):
        if "copper" in key.lower():
            inputs.pop(key, None)
    for key in COPPER_VALUATION_INPUT_KEYS:
        inputs.pop(key, None)
    val["inputs"] = inputs
    og = val.get("optionality_gate")
    if isinstance(og, dict):
        og.pop("copperwood_option_yield_pct", None)
    val.pop("market_inputs", None)
    val.pop("market_inputs_as_of", None)
    return val


def merge_ticker(ticker: str, fetched: dict[str, dict], *, val: dict | None = None) -> None:
    research = ROOT / ticker / "research"
    research.mkdir(parents=True, exist_ok=True)
    mi: dict = {}
    for cid, row in fetched.items():
        if row.get("spot") is None:
            continue
        mi[cid] = {
            "spot": row["spot"],
            "as_of": row.get("as_of"),
            "source": row.get("source"),
            "fetched_at": row.get("fetched_at"),
            "stooq_symbol": row.get("stooq_symbol"),
        }
        if cid == "copper":
            mi["scenario_grid"] = scenario_grid(row["spot"])
    if not mi:
        payload = {
            "ticker": ticker,
            "as_of": TODAY,
            "market_inputs": {},
            "note": "No commodity overlay for this ticker",
            "staleness_max_days": 7,
        }
    else:
        payload = {"ticker": ticker, "as_of": TODAY, "market_inputs": mi, "staleness_max_days": 7}
    (research / "market_inputs.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    val_path = research / "valuation.json"
    if not val_path.exists():
        return
    val = val if val is not None else json.loads(val_path.read_text(encoding="utf-8"))
    if not mi:
        val = strip_commodity_pollution(val)
        val_path.write_text(json.dumps(val, indent=2), encoding="utf-8")
        return
    val["market_inputs"] = mi
    val["market_inputs_as_of"] = TODAY
    inputs = val.setdefault("inputs", {})
    if "copper" in mi:
        spot = mi["copper"]["spot"]
        inputs["copper_spot_usd_per_lb"] = spot
        inputs["copper_spot_as_of"] = mi["copper"].get("as_of")
        inputs["copper_spot_source"] = mi["copper"].get("source")
        royalty_base = inputs.get("copperwood_royalty_est_usd")
        if royalty_base is not None:
            ssi_ref = 4.0
            ssi_royalty = float(royalty_base)
            inputs["copperwood_royalty_est_usd_ssi_ref"] = ssi_royalty
            inputs["copperwood_royalty_est_usd_at_spot"] = royalty_at_price(ssi_royalty, ssi_ref, spot)
            inputs["copperwood_royalty_note"] = (
                f"SSI ~${ssi_royalty/1e6:.1f}M/yr @ ${ssi_ref}/lb scaled linearly to spot ${spot}/lb [Assumption]"
            )
            sh = inputs.get("shares_outstanding")
            price = inputs.get("price")
            if royalty_base is not None and price and sh:
                mcap = float(price) * float(sh)
                if mcap > 0:
                    roy_spot = inputs["copperwood_royalty_est_usd_at_spot"]
                    val.setdefault("optionality_gate", {})["copperwood_option_yield_pct"] = round(
                        100.0 * roy_spot / mcap, 2
                    )
    val_path.write_text(json.dumps(val, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*", help="Tickers to merge into valuation.json")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    COMMODITY_DIR.mkdir(parents=True, exist_ok=True)
    fetched: dict[str, dict] = {}
    ok = True
    for cid, meta in DEFAULT_SYMBOLS.items():
        close, qd, err = fetch_stooq(meta["stooq"])
        row = {
            "id": cid,
            "stooq_symbol": meta["stooq"],
            "as_of": qd,
            "source": STOOQ_URL.format(symbol=meta["stooq"]),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "error": err,
        }
        if close is not None:
            row["raw_close"] = close
            row["spot"] = spot_usd_per_lb(cid, close, meta)
        else:
            ok = False
        fetched[cid] = row
        (COMMODITY_DIR / f"{cid}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        print(f"  {cid}: spot={row.get('spot')} as_of={qd} err={err}")

    manifest = {"as_of": TODAY, "commodities": {k: {"spot": v.get("spot"), "as_of": v.get("as_of")} for k, v in fetched.items()}}
    (COMMODITY_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.merge:
        tickers = tickers_for_market_merge()
    else:
        tickers = []
    for t in tickers:
        val = _load_valuation(t)
        cids = commodity_ids_for_ticker(t, val)
        subset = {k: v for k, v in fetched.items() if k in cids}
        merge_ticker(t, subset, val=val)
        if subset:
            print(f"OK merged {t} commodities={list(subset)}")
        else:
            print(f"OK cleared commodity inputs for {t} (not applicable)")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
