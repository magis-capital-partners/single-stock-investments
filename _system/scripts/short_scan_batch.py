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


def activist_status(ticker: str) -> tuple[str, str, str]:
    index_path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
    long_n = short_n = 0
    latest = ""
    if index_path.exists():
        data = json.loads(index_path.read_text(encoding="utf-8"))
        reports = data.get("reports") or []
        long_n = sum(1 for r in reports if r.get("side") == "long")
        short_n = sum(1 for r in reports if r.get("side") == "short")
        latest = max((r.get("report_date") or "" for r in reports), default="")
    sr = ROOT / ticker / "third-party-analyses" / "short_reports"
    md_count = len(list(sr.glob("*.md"))) if sr.is_dir() else 0
    if long_n or short_n:
        status = "indexed"
        note = f"{long_n} long, {short_n} short in activist index"
        if md_count:
            note += f"; {md_count} short markdown cache"
        return status, f"L{long_n}/S{short_n}", note
    if md_count:
        return "local_cache", f"md:{md_count}", f"{md_count} file(s) in short_reports/"
    return "no_hit", "—", "No activist index hits"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

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
        "| Ticker | Status | L/S | Notes |",
        "|--------|--------|-----|-------|",
    ]

    for t in tickers():
        status, badge, note = activist_status(t)
        lines.append(f"| {t} | {status} | {badge} | {note} |")

    lines.extend(
        [
            "",
            "## Maintenance",
            "",
            "- Re-run scan: `python _system/scripts/scan_activist_sources.py`",
            "- Re-run index: `python _system/scripts/short_scan_batch.py`",
            "- Save markdown summaries: `{TICKER}/third-party-analyses/short_reports/{firm}_{date}.md`",
            "- Reconcile in `{TICKER}/research/adversarial_{date}.md`",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(tickers())} rows)")


if __name__ == "__main__":
    main()
