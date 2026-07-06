#!/usr/bin/env python3
"""Build portfolio activist scan index from activist_reports_index.json + short_reports/."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def tickers() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if reg.exists():
        data = json.loads(reg.read_text(encoding="utf-8"))
        h = data.get("holdings") or {}
        if isinstance(h, dict):
            return sorted(h.keys())
    return []


def activist_status(ticker: str) -> dict:
    index_path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
    long_n = short_n = feed_short = 0
    latest = ""
    indexed_md: set[str] = set()
    if index_path.exists():
        data = json.loads(index_path.read_text(encoding="utf-8"))
        reports = data.get("reports") or []
        long_n = sum(1 for r in reports if r.get("side") == "long")
        short_n = sum(1 for r in reports if r.get("side") == "short")
        feed_short = sum(
            1
            for r in reports
            if r.get("side") == "short" and r.get("include_in_feed", True) and r.get("triage_verdict") != "auto_passive"
        )
        latest = max((r.get("report_date") or "" for r in reports), default="")
        indexed_md = {
            str(r.get("local_file") or "").replace("\\", "/")
            for r in reports
            if r.get("source") == "short_reports_md"
        }
    sr = ROOT / ticker / "third-party-analyses" / "short_reports"
    md_files = sorted(sr.glob("*.md")) if sr.is_dir() else []
    md_count = len(md_files)
    md_unindexed = [
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in md_files
        if str(p.relative_to(ROOT)).replace("\\", "/") not in indexed_md
    ]
    if long_n or short_n:
        status = "indexed"
        note = f"{long_n} long, {short_n} short indexed; {feed_short} short feed-eligible"
        if md_count:
            note += f"; {md_count} MD cache"
        if md_unindexed:
            note += f"; {len(md_unindexed)} MD not indexed"
        return {
            "ticker": ticker,
            "status": status,
            "badge": f"L{long_n}/S{short_n}",
            "note": note,
            "latest": latest or "—",
            "gaps": md_unindexed,
        }
    if md_count:
        return {
            "ticker": ticker,
            "status": "local_cache",
            "badge": f"md:{md_count}",
            "note": f"{md_count} file(s) in short_reports/ (not indexed)",
            "latest": "—",
            "gaps": md_unindexed,
        }
    return {
        "ticker": ticker,
        "status": "no_hit",
        "badge": "—",
        "note": "No activist index hits",
        "latest": "—",
        "gaps": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    rows = [activist_status(t) for t in tickers()]
    out = ROOT / "_system" / "research" / f"short_scan_{args.date}.md"
    lines = [
        "# Portfolio activist scan (long + short)",
        "",
        f"**Date:** {args.date}  ",
        f"**Agent:** `short_scan_batch.py`  ",
        f"**Registry:** `_system/frameworks/activist_firm_registry.json`",
        "",
        "**Method:** `activist_reports_index.json` + local `short_reports/` markdown cache.",
        "",
        "## Summary",
        "",
        "| Ticker | Status | L/S | Latest | Notes |",
        "|--------|--------|-----|--------|-------|",
    ]

    gap_lines: list[str] = []
    for row in rows:
        lines.append(
            f"| {row['ticker']} | {row['status']} | {row['badge']} | {row['latest']} | {row['note']} |"
        )
        for gap in row.get("gaps") or []:
            gap_lines.append(f"- `{gap}`")

    if gap_lines:
        lines.extend(["", "## Gaps (short MD not in index)", ""])
        lines.extend(gap_lines)

    lines.extend(
        [
            "",
            "## Maintenance",
            "",
            "- Re-run scan: `python _system/scripts/scan_activist_sources.py --reconcile --fetch-sec`",
            "- Re-run gap report: `python _system/scripts/short_scan_batch.py`",
            "- Save markdown summaries: `{TICKER}/third-party-analyses/short_reports/{firm}_{date}.md`",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(rows)} rows, {len(gap_lines)} gaps)")


if __name__ == "__main__":
    main()
