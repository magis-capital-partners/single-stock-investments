#!/usr/bin/env python3
"""Regenerate the short-activist prose registry from activist_firm_registry.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"
OUTPUT = ROOT / "_system" / "frameworks" / "short_activist_registry.md"


def _style(firm: dict) -> str:
    notes = str(firm.get("notes") or "").replace("|", "/")
    hints = [str(hint) for hint in (firm.get("search_hints") or [])]
    ops = any(token in notes.lower() for token in ("waf", "tls", "parked", "verified", "cannot fetch", "certifi", "hugedomains"))
    if notes and not ops:
        return notes
    if hints:
        return "; ".join(hints)
    return notes or "—"


def _rows(firms: list[dict], tier: int) -> list[str]:
    chosen = [
        firm for firm in firms
        if firm.get("side") in {"short", "both"} and int(firm.get("tier") or 0) == tier
    ]
    chosen.sort(key=lambda firm: str(firm.get("name") or "").lower())
    lines = [
        "| Firm | Active | Ingest | What it is for |",
        "|------|--------|--------|----------------|",
    ]
    for firm in chosen:
        active = "yes" if firm.get("active", True) else "no"
        methods = ", ".join(firm.get("ingest_methods") or [firm.get("ingest_method") or "manual"])
        lines.append(f"| **{firm.get('name')}** | {active} | {methods} | {_style(firm)} |")
    return lines


def render_markdown(doc: dict | None = None) -> str:
    if doc is None:
        doc = json.loads(SOURCE.read_text(encoding="utf-8"))
    firms = list(doc.get("firms") or [])
    updated = doc.get("updated") or "—"
    lines = [
        "# Short activist / forensic research registry",
        "",
        f"**Generated from:** `_system/frameworks/activist_firm_registry.json` ({updated}).",
        "**Do not edit the firm tables by hand.** Change the JSON, then run `python _system/scripts/render_short_activist_registry.py`.",
        "",
        "Long and press campaigns stay in `_system/frameworks/activist_press_ingest.md`.",
        "",
        "**Purpose:** Milly (adversarial reviewer) scans these publishers for reports on portfolio tickers. Not every name has coverage on every holding.",
        "",
        "**Use:** Cross-reference only. A short report is **evidence to reconcile**, not a veto. Goal = **truth**, not bearishness for its own sake. Firms with side `both` are included because they publish shorts as well as longs.",
        "",
        "---",
        "",
        "## Tier 1 — Forensic short specialists (priority scan)",
        "",
        *_rows(firms, 1),
        "",
        "## Tier 2 — Activist shorts / hedge letters (secondary)",
        "",
        *_rows(firms, 2),
        "",
        "---",
        "",
        "## Non-short bears (Milly disclosure scan)",
        "",
        "| Type | Search hints | Verdict in adversarial |",
        "|------|--------------|------------------------|",
        "| **SEC securities litigation** | `{company} class action 10b-5` | `litigation`. Not an automatic bear case. |",
        "| **Late filing (OTC)** | `NT 10-K` `Notification of Late Filing` | `disclosure: hit` |",
        "| **Restatement / non-reliance** | `should no longer be relied upon` Item 4.02 | `disclosure: hit` |",
        "| **Auditor change** | `8-K` auditor resignation | `needs_human` |",
        "",
        "---",
        "",
        "## Scan universe",
        "",
        "The scan universe is every holding in `_system/portfolio/registry.json`. A feed-eligible short in `{TICKER}/third-party-analyses/activist_reports_index.json` becomes a **lead** on the Shorts tab. It does not become a position.",
        "",
        "Milly logs **hit / no hit / unclear** per ticker per refresh.",
        "",
        "---",
        "",
        "## Reconciliation rules (Milly)",
        "",
        "1. **If short report exists:** Summarize **falsifiable claims** (numbers, accounting, legal).",
        "2. **Check each claim** against latest 10-K/10-Q or local equivalent in `{TICKER}/investor-documents/`.",
        "3. **Map to Marvin dive:** Did the deep dive address it? If not, record a **gap**. That is not an automatic downgrade.",
        "4. **Verdict types:** `refuted_by_filing` | `partially_valid` | `unaddressed` | `stale` | `needs_human`",
        "5. **Do not** change stance or IRR without human review unless there is a **factual error** in Marvin numbers (lint-level).",
        "",
        "---",
        "",
        "## Maintenance",
        "",
        "- Add new firms in `activist_firm_registry.json`, then regenerate this file.",
        "- Mark **inactive** firms; keep them for historical tickers.",
        "- Store found reports in `{TICKER}/third-party-analyses/activist_reports/{long|short}/` with metadata in `activist_reports_index.json`.",
        "- Markdown summaries may also live in `{TICKER}/third-party-analyses/short_reports/` with `source`, `date`, `url`, `summary.md`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    text = render_markdown()
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
