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

# Explicit registry: only tickers that use copper / Copperwood royalty math.
TICKER_SYMBOLS: dict[str, list[str]] = {
    "KEWL": ["copper"],
    "MSB": ["copper"],
}

COPPER_INPUT_KEYS = (
    "copper_spot_usd_per_lb",
    "copper_spot_as_of",
    "copper_spot_source",
    "copperwood_royalty_est_usd",
    "copperwood_royalty_est_usd_ssi_ref",
    "copperwood_royalty_est_usd_at_spot",
    "copperwood_royalty_note",
)


def commodities_for_ticker(ticker: str, val: dict | None = None) -> list[str]:
    """Return commodity ids to merge into valuation.json for this ticker."""
    t = ticker.upper()
    if t in TICKER_SYMBOLS:
        return list(TICKER_SYMBOLS[t])
    if val and ticker_needs_commodity_inputs(val):
        er = val.get("evidence_refresh") or {}
        return [str(er.get("commodity") or "copper")]
    return []


def strip_copper_from_valuation(val: dict) -> bool:
    """Remove erroneous copper / Copperwood fields from a valuation dict. Returns True if changed."""
    changed = False
    inputs = val.get("inputs")
    if isinstance(inputs, dict):
        for key in list(inputs):
            if key in COPPER_INPUT_KEYS or "copper" in key.lower():
                del inputs[key]
                changed = True
    mi = val.get("market_inputs")
    if isinstance(mi, dict) and "copper" in mi:
        del val["market_inputs"]
        changed = True
        val.pop("market_inputs_as_of", None)
    gate = val.get("optionality_gate")
    if isinstance(gate, dict) and "copperwood_option_yield_pct" in gate:
        del gate["copperwood_option_yield_pct"]
        changed = True
    return changed


COPPER_ONLY_MI_KEYS = frozenset({"copper", "scenario_grid"})


def is_copper_only_market_inputs(mi: dict) -> bool:
    """True when market_inputs block is only copper spot + scenario grid (pipeline leak)."""
    if not mi:
        return False
    keys = set(mi.keys())
    return keys <= COPPER_ONLY_MI_KEYS and "copper" in keys


def strip_copper_market_inputs_file(ticker: str) -> bool:
    """Delete market_inputs.json when it only held leaked copper data."""
    path = ROOT / ticker / "research" / "market_inputs.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    mi = payload.get("market_inputs") or {}
    if is_copper_only_market_inputs(mi):
        path.unlink()
        return True
    return False


def tickers_for_market_merge(explicit: list[str] | None = None) -> list[str]:
    """Tickers that should receive commodity merge (not every holding with valuation.json)."""
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
        if commodities_for_ticker(td.name, val):
            out.add(td.name.upper())
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


def merge_ticker(ticker: str, fetched: dict[str, dict], commodities: list[str]) -> None:
    research = ROOT / ticker / "research"
    research.mkdir(parents=True, exist_ok=True)
    val_path = research / "valuation.json"

    if not commodities:
        if val_path.exists():
            val = json.loads(val_path.read_text(encoding="utf-8"))
            if strip_copper_from_valuation(val):
                val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
                print(f"  stripped leaked copper from {ticker}/research/valuation.json")
        if strip_copper_market_inputs_file(ticker):
            print(f"  removed {ticker}/research/market_inputs.json (copper-only leak)")
        return

    mi: dict = {}
    for cid in commodities:
        row = fetched.get(cid) or {}
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
    payload = {"ticker": ticker, "as_of": TODAY, "market_inputs": mi, "staleness_max_days": 7}
    (research / "market_inputs.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not val_path.exists():
        return
    val = json.loads(val_path.read_text(encoding="utf-8"))
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
            if not sh and inputs.get("shares_millions"):
                sh = float(inputs["shares_millions"]) * 1_000_000
            price = inputs.get("price")
            if price and sh:
                mcap = float(price) * float(sh)
                if mcap > 0:
                    roy_spot = inputs["copperwood_royalty_est_usd_at_spot"]
                    val.setdefault("optionality_gate", {})["copperwood_option_yield_pct"] = round(
                        100.0 * roy_spot / mcap, 2
                    )
    val_path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")


def strip_copper_from_history_snapshot(val: dict) -> bool:
    """Strip leaked copper fields from a valuation_history snapshot dict."""
    return strip_copper_from_valuation(val)


def strip_all_leaks() -> list[str]:
    """Scan portfolio files and strip copper where ticker is not commodity-nav eligible."""
    cleaned: list[str] = []

    def note(ticker: str, suffix: str = "") -> None:
        label = f"{ticker}{suffix}"
        if label not in cleaned:
            cleaned.append(label)

    for vp in sorted(ROOT.glob("*/research/valuation.json")):
        ticker = vp.parts[-3]
        try:
            val = json.loads(vp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if commodities_for_ticker(ticker, val):
            continue
        has_copper = any(k in (val.get("inputs") or {}) for k in COPPER_INPUT_KEYS) or any(
            "copper" in k.lower() for k in (val.get("inputs") or {})
        ) or (val.get("market_inputs") or {}).get("copper") or (
            (val.get("optionality_gate") or {}).get("copperwood_option_yield_pct") is not None
        )
        if has_copper and strip_copper_from_valuation(val):
            vp.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
            note(ticker)
        if strip_copper_market_inputs_file(ticker):
            note(ticker, " (market_inputs.json)")

    for hp in sorted(ROOT.glob("*/research/valuation_history/valuation_*.json")):
        ticker = hp.parts[-4]
        try:
            snap = json.loads(hp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if commodities_for_ticker(ticker, snap):
            continue
        has_copper = any(k in (snap.get("inputs") or {}) for k in COPPER_INPUT_KEYS) or any(
            "copper" in k.lower() for k in (snap.get("inputs") or {})
        ) or (snap.get("market_inputs") or {}).get("copper") or (
            (snap.get("optionality_gate") or {}).get("copperwood_option_yield_pct") is not None
        )
        if has_copper and strip_copper_from_history_snapshot(snap):
            hp.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
            note(ticker, f" ({hp.name})")

    for mp in sorted(ROOT.glob("*/research/market_inputs.json")):
        ticker = mp.parts[-3]
        val = None
        vp = ROOT / ticker / "research" / "valuation.json"
        if vp.exists():
            try:
                val = json.loads(vp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        if commodities_for_ticker(ticker, val):
            continue
        if strip_copper_market_inputs_file(ticker):
            note(ticker, " (market_inputs.json)")

    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*", help="Tickers to merge into valuation.json")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument(
        "--strip-leaks",
        action="store_true",
        help="Remove copper/Copperwood fields from tickers that are not commodity-nav eligible",
    )
    args = parser.parse_args()

    if args.strip_leaks:
        cleaned = strip_all_leaks()
        for t in cleaned:
            print(f"stripped: {t}")
        print(f"Done. {len(cleaned)} ticker(s) cleaned.")
        return 0

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
        val = None
        vp = ROOT / t / "research" / "valuation.json"
        if vp.exists():
            val = json.loads(vp.read_text(encoding="utf-8"))
        commodities = commodities_for_ticker(t, val)
        subset = {k: v for k, v in fetched.items() if k in commodities}
        merge_ticker(t, subset, commodities)
        if commodities:
            print(f"OK merged {t} ({','.join(commodities)})")
        else:
            print(f"OK skipped commodity merge for {t} (not eligible)")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
