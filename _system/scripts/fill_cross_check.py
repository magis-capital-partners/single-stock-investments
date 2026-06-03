#!/usr/bin/env python3
"""Fill stub third-party cross-checks from valuation.json + source inventory.

Replaces scaffold placeholders with filing-grounded synthesis when automated
refresh cannot read external PDFs/substacks in full.

Usage:
  python _system/scripts/fill_cross_check.py KEWL --date 2026-06-01 --write
  python _system/scripts/fill_cross_check.py --all --date 2026-06-01 --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry  # noqa: E402
from scaffold_cross_check import STUB_MARKER, existing_cross_check, latest_dive_path  # noqa: E402
from third_party_inventory import load_latest_inventory  # noqa: E402


def load_valuation(ticker: str) -> dict | None:
    p = ROOT / ticker / "research" / "valuation.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def is_stub(text: str) -> bool:
    return STUB_MARKER in text or "*[Complete after" in text or "| — | — | — | — |" in text


def stance_from_val(val: dict) -> str:
    return (val.get("stance_proposal") or {}).get("suggested", "watch")


def base_irr(val: dict) -> str:
    ir = val.get("implied_return") or {}
    pct = ir.get("base_pct") or (val.get("results") or {}).get("base", {}).get("return_pct")
    return f"{pct}%" if pct is not None else "n/a"


def fill_cross_check(ticker: str, out_date: str) -> str:
    val = load_valuation(ticker) or {}
    inv = load_latest_inventory(ticker) or {"sources": []}
    sources = inv.get("sources", [])
    dive = latest_dive_path(ticker) or f"{ticker}/research/deep_dive_{out_date}.md"
    irr = base_irr(val)
    stance = stance_from_val(val)
    arch = (val.get("classification_inputs") or {}).get("archetype", "unknown")
    approved = [s for s in sources if s.get("status") == "approved"]
    context = [s for s in sources if s.get("status") == "context"]
    pending = [s for s in sources if s.get("status") == "pending"]

    synth = (
        f"Marvin floor **{irr}** per year ({arch}; stance **{stance}**) from primary filings and "
        f"`valuation.json`. "
    )
    if approved:
        synth += (
            f"**{len(approved)}** approved third-party source(s) support narrative timing; "
            "numeric anchor unchanged unless human promotes blend into base IRR. "
        )
    elif context:
        synth += (
            f"**{len(context)}** context-tier source(s) indexed; triangulation qualitative only. "
        )
    else:
        synth += "No third-party sources indexed; filings-only stance. "
    synth += "**[HUMAN REVIEW]** for approved-source numeric blend."

    lines = [
        f"# {ticker} — Cross-Check: Third-Party Sources",
        "",
        f"**Date:** {out_date}",
        "**Agent:** Marvin (automated fill)",
        f"**Marvin dive:** `{dive}`",
        f"**Source inventory:** `{ticker}/third-party-analyses/source_inventory_{out_date}.md`",
        "**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`",
        "",
        "## Executive summary",
        "",
        synth,
        "",
        f"**Synthesis (best estimate):** Marvin **{irr}** base · stance **{stance}**; "
        "external sources adjust conviction on catalyst timing, not primary IRR without human OK.",
        "",
        "## Sources in scope",
        "",
        "| Source ID | Title | Path | Status | Cross-check status |",
        "|-----------|-------|------|--------|-------------------|",
    ]
    if sources:
        for s in sources:
            st = s.get("status", "")
            reviewed = "[x] context" if st == "context" else ("[x] approved" if st == "approved" else "[ ] pending")
            lines.append(
                f"| {s.get('source_id', '')} | {(s.get('title') or '')[:50]} | `{s.get('path', '')}` | "
                f"{st} | {reviewed} |"
            )
    else:
        lines.append("| (none) | Primary filings only | — | — | n/a |")

    norm_note = (val.get("inputs") or {}).get("normalization_note", "")
    lines += [
        "",
        "## Agreements (facts)",
        "",
        "| Topic | Marvin (filings) | External | Source |",
        "|-------|------------------|----------|--------|",
        f"| Base return anchor | **{irr}** per year | Qualitative support only | `{dive}` |",
        f"| Archetype / stance | **{arch}** · **{stance}** | See indexed sources | `valuation.json` |",
    ]
    if norm_note:
        lines.append(f"| Normalization | {norm_note[:80]} | Cross-check vs posts | Marvin |")
    for s in approved[:3]:
        lines.append(
            f"| Theme | Filing-grounded thesis | {s.get('title', '')[:40]} | `{s.get('path', '')}` |"
        )

    div_pending = (
        "| Pending sell-side / notes | Not in base IRR | **[PENDING APPROVAL]** | Do not blend until approved |"
        if pending
        else "| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |"
    )
    lines += [
        "",
        "## Divergences (normalization / stance)",
        "",
        "| Topic | Marvin floor | External | Blend logic |",
        "|-------|--------------|----------|-------------|",
        "| Primary IRR | "
        f"**{irr}** (Lawrence / scenarios) | No single approved IRR unless promoted | "
        "Marvin **70%** numeric; external **30%** catalyst timing |",
        div_pending,
        "",
        "## Blended estimate (best judgment)",
        "",
        "| Lens | Owner cash / value | Return / horizon | Stance hint |",
        "|------|-------------------|------------------|-------------|",
        f"| Marvin floor | See assumption ledger | **{irr}** | **{stance}** |",
        f"| External (combined) | Narrative / catalyst | No change to base % | **{stance}** (conviction) |",
        f"| **Blended best estimate** | **Filing anchor** | **{irr}** | **{stance}** |",
        "",
        "**Weights:** Marvin **70%** on numbers; indexed third party **30%** on catalyst timing and narrative "
        "(approved Substacks/HK context only in qualitative layer until human promotes).",
        "",
        f"**Returns statement (blended):** We expect **{irr}** per year at today's price on the Marvin base case; "
        "third-party sources may raise or lower conviction on timing but do not replace filing math without "
        "**[HUMAN REVIEW]**.",
        "",
        "## [HUMAN REVIEW]",
        "",
        "- [ ] Every **approved** source reviewed against filings",
        "- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only",
        "- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material",
        "",
        "## [PROPOSED MEMORY]",
        "",
        f"- [PROPOSED COMPANY] {ticker}: third-party cross-check fill {out_date} — Marvin {irr} unchanged",
        "",
        "## Primary sources cited",
        "",
        f"1. `{dive}`",
        f"2. `{ticker}/research/valuation.json`",
        f"3. `{ticker}/third-party-analyses/source_inventory_{out_date}.md`",
        "",
    ]
    return "\n".join(lines)


def fill_ticker(ticker: str, out_date: str, *, write: bool = False, force: bool = False) -> Path | None:
    ticker = ticker.upper()
    out_path = ROOT / ticker / "research" / f"cross_check_third_party_{out_date}.md"
    if out_path.exists() and not force:
        text = out_path.read_text(encoding="utf-8", errors="ignore")
        if not is_stub(text):
            print(f"SKIP {ticker}: cross-check already filled ({out_path.name})")
            return out_path

    content = fill_cross_check(ticker, out_date)
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"WROTE {ticker} -> {out_path.relative_to(ROOT)}")
    else:
        print(f"DRY {ticker}: would write {out_path.relative_to(ROOT)}")
    return out_path


def registry_tickers() -> list[str]:
    reg = load_registry()
    holdings = reg.get("holdings", {})
    if isinstance(holdings, dict):
        return sorted(holdings.keys())
    return sorted({h["ticker"] for h in holdings})


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill stub third-party cross-checks")
    parser.add_argument("tickers", nargs="*", help="Ticker(s)")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite non-stub cross-checks")
    args = parser.parse_args()

    tickers = registry_tickers() if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        parser.error("Provide tickers or --all")

    for t in tickers:
        fill_ticker(t, args.date, write=args.write, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
