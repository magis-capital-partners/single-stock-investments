"""Shared helpers for Marvin mechanical pipelines."""
from __future__ import annotations

import re
import json
from pathlib import Path


def latest_deep_dive_date(research_dir: Path) -> str | None:
    """Return YYYY-MM-DD from newest deep_dive_*.md, or None."""
    dives = sorted(research_dir.glob("deep_dive_*.md"), reverse=True)
    for p in dives:
        m = re.match(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$", p.name)
        if m:
            return m.group(1)
    return None


def has_evidence_refresh_config(val: dict) -> bool:
    er = val.get("evidence_refresh") or {}
    return bool(er.get("type"))


def ticker_has_crypto_tag(ticker: str) -> bool:
    path = Path(__file__).resolve().parents[2] / "_system" / "portfolio" / "holdings_crypto.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return ticker.upper() in (data.get("holdings") or {})


def ticker_needs_commodity_inputs(val: dict) -> bool:
    """True when valuation should merge commodity spot / royalty overlays (not all tickers)."""
    inp = val.get("inputs") or {}
    # Do not key off copper_spot_* alone — fetch_market_inputs may have injected it by mistake.
    if inp.get("copperwood_royalty_est_usd"):
        return True
    er = val.get("evidence_refresh") or {}
    if er.get("type") == "commodity_nav":
        return True
    return False
