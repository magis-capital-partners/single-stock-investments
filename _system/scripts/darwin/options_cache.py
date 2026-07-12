"""Darwin options marks — cache-first, champion-only, zero-waste API usage.

Strategy (do not burn Polygon/Tradier quota):
1. Read SSI local cache `_system/reference/market-data/options/options_cache.json`
2. Overlay free reads from etf-dashboard `data/options_cache.json` for overlapping tickers
3. Fall back to realized-vol synthetic IV (returns CSV) — no API
4. Optional live refresh ONLY for champion / top liquid names via
   `refresh_darwin_options_cache.py` with tight budgets + shard + merge

Never pull full SPX options chains into SSI.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ROOT
from .external_sources import etf_data_path

OPTIONS_DIR = ROOT / "_system" / "reference" / "market-data" / "options"
LOCAL_CACHE = OPTIONS_DIR / "options_cache.json"
META_PATH = OPTIONS_DIR / "options_cache_meta.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_local_cache() -> dict:
    return _load_json(LOCAL_CACHE)


def load_etf_dashboard_cache() -> dict:
    p = etf_data_path("options_cache.json")
    if not p:
        return {}
    return _load_json(p)


def merge_symbol_maps(*caches: dict) -> dict[str, dict]:
    """Later caches override earlier for same ticker (local wins over etf if passed last)."""
    out: dict[str, dict] = {}
    for cache in caches:
        syms = (cache or {}).get("symbols") or {}
        for k, v in syms.items():
            if isinstance(v, dict):
                out[str(k).upper()] = v
    return out


def load_merged_symbol_map() -> dict[str, dict]:
    """ETF dashboard (free) then local SSI champion cache (overrides)."""
    return merge_symbol_maps(load_etf_dashboard_cache(), load_local_cache())


def atm_call_iv(symbol_payload: dict, max_days: int = 21) -> float | None:
    """Nearest short-dated ATM call IV from a Polygon/Tradier-style chain payload."""
    rows = symbol_payload.get("options") or []
    spot = symbol_payload.get("spot")
    if not rows or not isinstance(spot, (int, float)) or spot <= 0:
        # Any positive IV on short calls
        ivs = [
            float(r["iv"])
            for r in rows
            if isinstance(r, dict)
            and str(r.get("contract_type", "")).lower() in ("call", "c")
            and isinstance(r.get("iv"), (int, float))
            and float(r["iv"]) > 0
        ]
        return sum(ivs) / len(ivs) if ivs else None

    today = datetime.now(timezone.utc).date()
    best = None
    best_score = 1e18
    for r in rows:
        if not isinstance(r, dict):
            continue
        ctype = str(r.get("contract_type", "")).lower()
        if ctype not in ("call", "c"):
            continue
        iv = r.get("iv")
        strike = r.get("strike_price")
        exp = str(r.get("expiration_date") or "")[:10]
        if not isinstance(iv, (int, float)) or iv <= 0:
            continue
        if not isinstance(strike, (int, float)):
            continue
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except ValueError:
            continue
        days = (ed - today).days
        if days < 0 or days > max_days:
            continue
        moneyness = abs(float(strike) / float(spot) - 1.0)
        score = moneyness * 100 + days * 0.01
        if score < best_score:
            best_score = score
            best = float(iv)
    return best


def iv_by_ticker(tickers: list[str] | None = None) -> dict[str, float]:
    """Map ticker → annualized IV (fraction) from merged caches."""
    syms = load_merged_symbol_map()
    want = {t.upper() for t in tickers} if tickers else None
    out: dict[str, float] = {}
    for t, payload in syms.items():
        if want is not None and t not in want:
            continue
        iv = atm_call_iv(payload)
        if iv is not None and iv > 0:
            # Tradier/Polygon IV often already annualized decimal
            out[t] = float(iv) if iv < 5 else float(iv) / 100.0
    return out


def cache_coverage_report(tickers: list[str]) -> dict[str, Any]:
    local = load_local_cache()
    etf = load_etf_dashboard_cache()
    merged = load_merged_symbol_map()
    ivs = iv_by_ticker(tickers)
    return {
        "requested": len(tickers),
        "local_symbols": len((local.get("symbols") or {})),
        "etf_dashboard_symbols": len((etf.get("symbols") or {})),
        "merged_hit": sum(1 for t in tickers if t.upper() in merged),
        "iv_hit": len(ivs),
        "iv_by_ticker": {k: round(v, 4) for k, v in sorted(ivs.items())},
        "etf_dashboard_available": bool(etf),
        "local_cache_path": str(LOCAL_CACHE),
        "source_priority": ["etf_dashboard_options_cache", "ssi_local_options_cache", "realized_vol_synthetic"],
    }


def save_local_cache(payload: dict) -> Path:
    OPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_CACHE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    meta = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbol_count": len(payload.get("symbols") or {}),
        "source": payload.get("source"),
        "polygon_requests_used": payload.get("polygon_requests_used"),
        "tradier_requests_used": payload.get("tradier_requests_used"),
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return LOCAL_CACHE
