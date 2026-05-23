#!/usr/bin/env python3
"""Regenerate holdings.md, classification.json, and us_ticker_config.json from registry.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import (
    CLASS_PATH,
    HOLDINGS_PATH,
    REGISTRY_PATH,
    ROOT,
    US_CONFIG_PATH,
    DEFAULT_CLASSIFICATION,
    load_registry,
)

SKIP_DIRS = {"_system", "dashboard", ".git", ".github", ".cursor"}


def folder_mtime_field(ticker: str, kind: str) -> str:
    ticker_dir = ROOT / ticker
    if kind == "download":
        log = ticker_dir / "_download_log.txt"
        if not log.exists():
            return "—"
        lines = [ln for ln in log.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
        if not lines:
            return "—"
        m = __import__("re").match(r"(\d{4}-\d{2}-\d{2})", lines[-1])
        return m.group(1) if m else "—"
    research = ticker_dir / "research"
    if not research.exists():
        return "—"
    files = [f for f in research.rglob("*") if f.is_file()]
    if not files:
        return "—"
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def write_holdings_md(holdings: dict[str, dict]) -> None:
    tickers = sorted(holdings.keys())
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Holdings",
        "",
        f"Synced from `_system/portfolio/registry.json`. Last sync: {today}.",
        "",
        "**Classification schema:** `_system/frameworks/classification.md` · source map: `_system/portfolio/classification.json`",
        "",
        "| Ticker | Folder | Company | Market | Last download | Last research | Archetype | Stance |",
        "|--------|--------|---------|--------|---------------|---------------|-----------|--------|",
    ]
    for ticker in tickers:
        h = holdings[ticker]
        cls = h.get("classification") or {}
        lines.append(
            f"| {ticker} | {ticker}/ | {h['company']} | {h['market']} | "
            f"{folder_mtime_field(ticker, 'download')} | {folder_mtime_field(ticker, 'research')} | "
            f"{cls.get('archetype', 'unknown')} | {cls.get('stance', 'watch')} |"
        )
    lines.extend(
        [
            "",
            f"**{len(tickers)} holdings total.** Registry: `_system/portfolio/registry.json`",
            "",
        ]
    )
    HOLDINGS_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_classification_json(holdings: dict[str, dict]) -> None:
    out: dict[str, dict] = {}
    for ticker, h in sorted(holdings.items()):
        cls = {**DEFAULT_CLASSIFICATION, **(h.get("classification") or {})}
        if h.get("predictive_attribute"):
            cls["predictive_attribute"] = h["predictive_attribute"]
        out[ticker] = cls
    CLASS_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def write_us_ticker_config(holdings: dict[str, dict]) -> None:
    out: dict[str, dict] = {}
    for ticker, h in sorted(holdings.items()):
        dl = h.get("download") or {}
        if dl.get("type") not in {"us_shared", "us_dedicated"}:
            continue
        if dl.get("type") == "us_dedicated":
            continue
        entry: dict = {}
        if dl.get("cik"):
            entry["cik"] = dl["cik"]
        else:
            entry["cik"] = None
        entry["ir_roots"] = dl.get("ir_roots") or []
        opts = dl.get("options") or {}
        entry.update(opts)
        out[ticker] = entry
    US_CONFIG_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    write_holdings_md(holdings)
    write_classification_json(holdings)
    write_us_ticker_config(holdings)
    print(f"Synced {len(holdings)} holdings -> holdings.md, classification.json, us_ticker_config.json")


if __name__ == "__main__":
    main()
