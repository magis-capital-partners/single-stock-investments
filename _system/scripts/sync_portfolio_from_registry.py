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
    owned_dashboard_overlay,
    owned_group,
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


OWNED_OVERLAY_PATH = ROOT / "dashboard" / "data" / "owned_holdings.json"


def _account_labels(group: dict, account_ids: list) -> str:
    accounts = group.get("accounts") or {}
    labels = []
    for account_id in account_ids:
        account = accounts.get(account_id) or {}
        labels.append(str(account.get("label") or account_id))
    return "; ".join(labels)


def owned_section_lines(reg: dict) -> list[str]:
    """Public Owned section. Account labels and contract flags. No sizes."""
    group = owned_group(reg)
    if not group:
        return []
    holdings = reg.get("holdings") or {}
    members = group.get("members") or {}
    lines = [
        "## Owned",
        "",
        "Actual positions as of "
        f"{group.get('as_of') or 'an unstated date'}. "
        "This is a tracking group. It does not change Stance. "
        "Stance stays the research action: core, accumulate, hold, watch, trim, or exit. "
        "Hold still means the research book wants to keep the name. "
        "It does not mean an account owns the shares. "
        "Share counts and market values are omitted.",
        "",
    ]
    for note in group.get("coverage_notes") or []:
        lines.append(f"- {note}")
    if group.get("coverage_notes"):
        lines.append("")
    lines.extend(
        [
            "| Ticker | Company | Accounts | Broker symbols |",
            "|--------|---------|----------|----------------|",
        ]
    )
    for ticker in sorted(members):
        member = members[ticker]
        if not isinstance(member, dict) or member.get("role") != "long":
            continue
        company = (holdings.get(ticker) or {}).get("company") or ticker
        brokers = ", ".join(member.get("broker_symbols") or []) or ticker
        lines.append(
            f"| {ticker} | {company} | {_account_labels(group, member.get('accounts') or [])} | {brokers} |"
        )
    lines.extend(
        [
            "",
            "### Short option flags",
            "",
            "Open short puts and calls. Contract counts are omitted. "
            "A flag on a name that is not a long does not make that name a holding.",
            "",
            "| Ticker | Account | Contract |",
            "|--------|---------|----------|",
        ]
    )
    option_rows = []
    for ticker in sorted(members):
        member = members[ticker]
        if not isinstance(member, dict):
            continue
        for opt in member.get("short_options") or []:
            if not isinstance(opt, dict):
                continue
            option_rows.append(
                (
                    ticker,
                    _account_labels(group, [opt.get("account")]),
                    f"short {opt.get('right')}, strike {opt.get('strike')}, expiry {opt.get('expiry')}",
                )
            )
    for ticker, account, contract in option_rows:
        lines.append(f"| {ticker} | {account} | {contract} |")
    if not option_rows:
        lines.append("| — | — | none |")
    lines.extend(
        [
            "",
            "### Short hedges",
            "",
            "Leveraged or inverse ETF shorts. Recorded in the group and not given ticker folders.",
            "",
            "| Broker symbol | Account |",
            "|---------------|---------|",
        ]
    )
    hedges = group.get("short_hedges") or []
    if not hedges:
        lines.append("| — | none |")
    for row in sorted(hedges, key=lambda item: str((item or {}).get("broker_symbol") or "")):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('broker_symbol')} | {_account_labels(group, [row.get('account')])} |"
        )
    aliases = group.get("symbol_aliases") or {}
    lines.extend(
        [
            "",
            "### Symbol aliases",
            "",
            "Broker symbols that point at an existing registry ticker. No second folder is created.",
            "",
            "| Broker symbol | Registry ticker |",
            "|---------------|-----------------|",
        ]
    )
    if not aliases:
        lines.append("| — | — |")
    for broker in sorted(aliases):
        lines.append(f"| {broker} | {aliases[broker]} |")
    lines.append("")
    return lines


def write_owned_overlay(reg: dict) -> None:
    overlay = owned_dashboard_overlay(reg)
    OWNED_OVERLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    OWNED_OVERLAY_PATH.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")


def write_holdings_md(holdings: dict[str, dict], reg: dict | None = None) -> None:
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
    if reg is not None:
        lines.extend(owned_section_lines(reg))
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
    write_holdings_md(holdings, reg)
    write_classification_json(holdings)
    write_us_ticker_config(holdings)
    write_owned_overlay(reg)
    print(
        f"Synced {len(holdings)} holdings -> holdings.md, classification.json, "
        "us_ticker_config.json, dashboard/data/owned_holdings.json"
    )


if __name__ == "__main__":
    main()
