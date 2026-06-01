#!/usr/bin/env python3
"""Scaffold third-party cross-check files for universe tickers.

Usage:
  python _system/scripts/scaffold_cross_check.py GOOGL --date 2026-06-01
  python _system/scripts/scaffold_cross_check.py --all --date 2026-06-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry
from third_party_inventory import collect_third_party_sources, load_latest_inventory

STUB_MARKER = "<!-- THIRD_PARTY_CROSS_CHECK_STUB -->"


def latest_dive_path(ticker: str) -> str | None:
    research = ROOT / ticker / "research"
    dives = sorted(research.glob("deep_dive_*.md")) if research.is_dir() else []
    if not dives:
        return None
    return str(dives[-1].relative_to(ROOT)).replace("\\", "/")


def existing_cross_check(ticker: str) -> Path | None:
    research = ROOT / ticker / "research"
    if not research.is_dir():
        return None
    checks = sorted(research.glob("cross_check*.md"))
    return checks[-1] if checks else None


def render_cross_check(ticker: str, inv: dict, out_date: str) -> str:
    dive = latest_dive_path(ticker) or f"{ticker}/research/deep_dive_{out_date}.md"
    sources = inv.get("sources", [])
    lines = [
        f"# {ticker} — Cross-Check: Third-Party Sources",
        "",
        f"**Date:** {out_date}",
        f"**Agent:** Marvin",
        f"**Marvin dive:** `{dive}`",
        f"**Source inventory:** `{ticker}/third-party-analyses/source_inventory_{out_date}.md`",
        "**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`",
        STUB_MARKER,
        "",
        "## Executive summary",
        "",
    ]
    if not sources:
        lines.extend(
            [
                "No third-party sources are indexed for this ticker as of this scan. "
                "Marvin stance rests on **primary filings only** (10-K, 10-Q, IR). "
                "Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.",
                "",
                "**Synthesis:** Marvin floor only; no external blend.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"This cross-check triangulates **{len(sources)}** third-party source(s) against primary filings. "
                "**[HUMAN REVIEW]** Complete agreements, divergences, and blended synthesis below.",
                "",
                "**Synthesis (best estimate):** *[Complete after reading each source against filings]*",
                "",
            ]
        )

    lines.extend(["## Sources in scope", ""])
    if sources:
        lines.extend(
            [
                "| Source ID | Title | Path | Status | Cross-check status |",
                "|-----------|-------|------|--------|-------------------|",
            ]
        )
        for s in sources:
            st = "**PENDING APPROVAL**" if s.get("status") == "pending" else s.get("status", "")
            lines.append(
                f"| {s.get('source_id', '')} | {s.get('title', '')[:50]} | `{s.get('path', '')}` | "
                f"{st} | [ ] reviewed |"
            )
    else:
        lines.append("| (none) | Primary filings only | — | — | n/a |")

    lines.extend(
        [
            "",
            "## Agreements (facts)",
            "",
            "| Topic | Marvin (filings) | External | Source |",
            "|-------|------------------|----------|--------|",
            "| — | — | — | — |",
            "",
            "## Divergences (normalization / stance)",
            "",
            "| Topic | Marvin floor | External | Blend logic |",
            "|-------|--------------|----------|-------------|",
            "| — | — | — | — |",
            "",
            "## Blended estimate (best judgment)",
            "",
            "| Lens | Owner cash / value | Return / horizon | Stance hint |",
            "|------|-------------------|------------------|-------------|",
            "| Marvin floor | — | — | — |",
            "| External (combined) | — | — | — |",
            "| **Blended best estimate** | **—** | **—** | **—** |",
            "",
            "**Weights:** *[Document why]*",
            "",
            "**Returns statement (blended):** *[One sentence; pending sources not in base IRR]*",
            "",
            "## [HUMAN REVIEW]",
            "",
            "- [ ] Every **approved** source reviewed against filings",
            "- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only",
            "- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material",
            "",
            "## [PROPOSED MEMORY]",
            "",
            f"- [PROPOSED COMPANY] {ticker}: third-party cross-check {out_date}",
            "",
            "## Primary sources cited",
            "",
            f"1. `{dive}`",
            f"2. `{ticker}/third-party-analyses/source_inventory_{out_date}.md`",
        ]
    )
    for i, s in enumerate(sources[:15], start=3):
        lines.append(f"{i}. `{s.get('path', '')}`")
    lines.append("")
    return "\n".join(lines)


def scaffold_ticker(ticker: str, out_date: str, *, force: bool = False) -> Path | None:
    ticker = ticker.upper()
    out_path = ROOT / ticker / "research" / f"cross_check_third_party_{out_date}.md"
    existing = existing_cross_check(ticker)
    if existing and not force:
        print(f"SKIP {ticker}: existing {existing.relative_to(ROOT)}")
        return existing

    inv = load_latest_inventory(ticker) or collect_third_party_sources(ticker)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_cross_check(ticker, inv, out_date), encoding="utf-8")
    print(f"OK {ticker} -> {out_path.relative_to(ROOT)}")
    return out_path


def registry_tickers() -> list[str]:
    reg = load_registry()
    holdings = reg.get("holdings", {})
    if isinstance(holdings, dict):
        return sorted(holdings.keys())
    return sorted({h["ticker"] for h in holdings})


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold third-party cross-check markdown")
    parser.add_argument("tickers", nargs="*", help="Ticker(s)")
    parser.add_argument("--all", action="store_true", help="All registry holdings")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--force", action="store_true", help="Overwrite existing cross-check")
    args = parser.parse_args()

    tickers = registry_tickers() if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        parser.error("Provide tickers or --all")

    for t in tickers:
        scaffold_ticker(t, args.date, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
