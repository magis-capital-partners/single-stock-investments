#!/usr/bin/env python3
"""Warn on stale macro panels and placeholder equity prices."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES_MANIFEST = ROOT / "_system" / "reference" / "market-data" / "themes" / "manifest.json"
PLACEHOLDER_RE = re.compile(r"placeholder|confirm via fetch_market", re.I)


def check_macro(manifest: dict) -> list[str]:
    issues: list[str] = []
    theme = (manifest.get("themes") or {}).get("macro_regime") or {}
    for sid, s in (theme.get("series") or {}).items():
        if s.get("optional"):
            continue
        if s.get("latest") is None:
            issues.append(f"macro_regime.{sid}: null ({s.get('error')})")
    return issues


def check_ticker_price(ticker: str) -> list[str]:
    issues: list[str] = []
    vp = ROOT / ticker / "research" / "valuation.json"
    if not vp.exists():
        return issues
    val = json.loads(vp.read_text(encoding="utf-8"))
    inputs = val.get("inputs") or {}
    ps = str(inputs.get("price_source") or "")
    if PLACEHOLDER_RE.search(ps):
        issues.append(f"{ticker}: placeholder price_source")
    pas = inputs.get("price_as_of")
    if pas:
        try:
            age = (date.today() - date.fromisoformat(str(pas)[:10])).days
            if age > 7:
                issues.append(f"{ticker}: price_as_of {pas} ({age}d stale)")
        except ValueError:
            pass
    elif inputs.get("price") is not None and not PLACEHOLDER_RE.search(ps):
        issues.append(f"{ticker}: missing price_as_of")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Optional ticker subset")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on placeholder prices")
    args = ap.parse_args()
    issues: list[str] = []
    if THEMES_MANIFEST.exists():
        manifest = json.loads(THEMES_MANIFEST.read_text(encoding="utf-8"))
        issues.extend(check_macro(manifest))
    tickers = args.tickers or []
    if not tickers:
        for td in sorted(ROOT.iterdir()):
            if (td / "research" / "valuation.json").exists() and not td.name.startswith("_"):
                tickers.append(td.name.upper())
    for t in tickers:
        issues.extend(check_ticker_price(t))
    for i in issues:
        print(i)
    if not issues:
        print("OK market freshness")
        return 0
    if args.strict and any("placeholder" in i for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
