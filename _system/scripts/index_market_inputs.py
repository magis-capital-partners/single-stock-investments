#!/usr/bin/env python3
"""Market inputs for index membership scorecards (offline-first)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FUNDAMENTALS_PATH = (
    ROOT / "_system" / "reference" / "market-data" / "ownership" / "biotech_fundamentals.json"
)
INDEX_FLOAT_ADV_PATH = (
    ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "index_float_adv.json"
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_index_float_adv_cache() -> dict[str, dict]:
    """Secondary cache: float_pct / ADV for index float-impact math (never invent)."""
    doc = _load_json(INDEX_FLOAT_ADV_PATH)
    return dict(doc.get("by_ticker") or {})


def _security_type(ticker: str, exchange: str | None, company: str | None) -> str | None:
    t = (ticker or "").upper()
    ex = (exchange or "").upper()
    name = (company or "").lower()
    if t.endswith(".CVR") or " cvr" in name or "(cvr" in name:
        return "cvr"
    if t.endswith(".DB") or "debenture" in name:
        return "debenture"
    if t.endswith("R") and "rights" in name:
        return "rights"
    if any(x in t for x in ("FNMA", "FMCC", ".PS")) or "preferred" in name:
        return "preferred"
    if ex in {"OTC PINK", "OTC"} and "pink" in ex.lower():
        return "otc_pink"
    if ex == "OTC PINK":
        return "otc_pink"
    if ex == "PRIVATE":
        return "private"
    if ex == "OTC" and any(x in t for x in ("FNMA", "FMCC", "GKTX", "CORBF", "GDRZF")):
        return "preferred" if "preferred" in name or t.startswith(("FNMA", "FMCC")) else None
    return None


def load_fundamentals_cache() -> dict[str, dict]:
    """Merge biotech ownership cache with index float/ADV cache (index wins on overlap)."""
    doc = _load_json(FUNDAMENTALS_PATH)
    merged = dict(doc.get("by_ticker") or {})
    for t, row in load_index_float_adv_cache().items():
        key = str(t).upper()
        base = dict(merged.get(key) or {})
        base.update({k: v for k, v in row.items() if v is not None})
        merged[key] = base
    return merged


def market_inputs_for_ticker(
    ticker: str,
    *,
    holdings_meta: dict | None = None,
    fundamentals_cache: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Return mcap/shares/float/ADV/earnings inputs without inventing values."""
    meta = holdings_meta or {}
    ticker_dir = ROOT / ticker
    valuation = _load_json(ticker_dir / "research" / "valuation.json")
    panel = _load_json(ticker_dir / "research" / "total_return_panel.json")
    inputs = valuation.get("inputs") or {}
    tr = valuation.get("total_return_panel") or {}

    price = inputs.get("price") or panel.get("price_for_market_cap") or tr.get("price")
    shares_m = inputs.get("shares_millions")
    shares = None
    if shares_m is not None:
        try:
            shares = float(shares_m) * 1_000_000.0
        except (TypeError, ValueError):
            shares = None
    if shares is None and panel.get("shares_outstanding"):
        try:
            shares = float(panel["shares_outstanding"])
        except (TypeError, ValueError):
            shares = None

    mcap = None
    for candidate in (
        valuation.get("equity_market_cap_m"),
        tr.get("market_cap_m"),
        panel.get("market_cap_m"),
    ):
        if candidate is not None:
            try:
                mcap = float(candidate) * 1_000_000.0
                break
            except (TypeError, ValueError):
                pass
    if mcap is None and price is not None and shares is not None:
        try:
            mcap = float(price) * float(shares)
        except (TypeError, ValueError):
            mcap = None

    cache = (fundamentals_cache or {}).get(ticker.upper()) or {}
    if mcap is None and cache.get("issuer_market_cap"):
        try:
            mcap = float(cache["issuer_market_cap"])
        except (TypeError, ValueError):
            pass
    if shares is None and cache.get("shares_outstanding"):
        try:
            shares = float(cache["shares_outstanding"])
        except (TypeError, ValueError):
            pass
    if price is None and cache.get("price"):
        try:
            price = float(cache["price"])
        except (TypeError, ValueError):
            pass

    # Prefer index_float_adv / cache float when valuation lacks it (Phase 4 coverage)
    float_pct = None
    for src in (valuation, panel, cache, meta):
        for key in ("float_pct", "float_percent", "iwf", "free_float"):
            if src.get(key) is not None:
                try:
                    float_pct = float(src[key])
                    if float_pct > 1.5:
                        float_pct = float_pct / 100.0
                    break
                except (TypeError, ValueError):
                    pass
        if float_pct is not None:
            break
    if float_pct is None and cache.get("float_shares") and shares:
        try:
            float_pct = float(cache["float_shares"]) / float(shares)
            if float_pct > 1.0:
                float_pct = None
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    adv_shares = None
    adv_dollar = None
    for src in (valuation, panel, cache):
        for key in ("adv_shares", "average_volume", "avg_volume"):
            if src.get(key) is not None:
                try:
                    adv_shares = float(src[key])
                    break
                except (TypeError, ValueError):
                    pass
        for key in ("adv_dollar", "dollar_volume", "avg_dollar_volume"):
            if src.get(key) is not None:
                try:
                    adv_dollar = float(src[key])
                    break
                except (TypeError, ValueError):
                    pass
        if adv_shares is not None or adv_dollar is not None:
            break
    if adv_dollar is None and adv_shares is not None and price is not None:
        try:
            adv_dollar = float(adv_shares) * float(price)
        except (TypeError, ValueError):
            pass
    # Fill shares from float/ADV cache when valuation omits them (never invent float_pct)
    if shares is None and cache.get("shares_outstanding") is not None:
        try:
            shares = float(cache["shares_outstanding"])
            if mcap is None and price is not None:
                mcap = float(price) * shares
        except (TypeError, ValueError):
            pass

    earnings_positive = None
    earnings_note = None
    facts_dir = ticker_dir / "research" / "evidence"
    fact_files = sorted(facts_dir.glob("filing_facts_*.json")) if facts_dir.is_dir() else []
    if fact_files:
        facts = _load_json(fact_files[-1])
        metrics = facts.get("metrics") or facts
        ni = metrics.get("net_income") or {}
        current = ni.get("current")
        prior = ni.get("prior")
        if current is not None:
            try:
                cur_f = float(current)
                # prior may be one quarter; treat current>0 and (prior is None or prior+current>0) as weak TTM proxy
                if prior is not None:
                    pri_f = float(prior)
                    earnings_positive = cur_f > 0 and (cur_f + pri_f) > 0
                    earnings_note = f"filing_facts net_income current={cur_f} prior={pri_f}"
                else:
                    earnings_positive = cur_f > 0
                    earnings_note = f"filing_facts net_income current={cur_f} (no prior)"
            except (TypeError, ValueError):
                earnings_note = "filing_facts net_income unreadable"
        else:
            earnings_note = "filing_facts missing net_income"
    else:
        earnings_note = "no filing_facts"

    exchange = meta.get("exchange")
    market = meta.get("market")
    company = meta.get("company")
    sec_type = _security_type(ticker, exchange, company)
    if exchange and str(exchange).upper() == "OTC PINK":
        sec_type = sec_type or "otc_pink"

    missing: list[str] = []
    if mcap is None:
        missing.append("market_cap")
    if shares is None:
        missing.append("shares")
    if float_pct is None:
        missing.append("float_pct")
    if adv_shares is None and adv_dollar is None:
        missing.append("adv")
    if earnings_positive is None:
        missing.append("earnings")

    return {
        "ticker": ticker,
        "market": market,
        "exchange": exchange,
        "company": company,
        "security_type": sec_type,
        "price": price,
        "shares": shares,
        "market_cap_usd": mcap,
        "float_pct": float_pct,
        "adv_shares": adv_shares,
        "adv_dollar": adv_dollar,
        "earnings_positive": earnings_positive,
        "earnings_note": earnings_note,
        "missing": missing,
        "mcap_source": "valuation_or_price_x_shares" if mcap is not None else None,
    }
