#!/usr/bin/env python3
"""Milly mechanical reconciliation pass for activist / short report hits.

Usage:
  python milly_activist_reconcile.py
  python milly_activist_reconcile.py --ticker APLD
  python milly_activist_reconcile.py --date 2026-07-01
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from activist_common import (
    activist_index_path,
    activist_reports_dir,
    load_ticker_index,
    portfolio_tickers,
    save_ticker_index,
)

ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: Path, limit: int = 8000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _report_text(report: dict) -> str:
    rel_path = report.get("local_file") or report.get("local_pdf")
    if not rel_path:
        return ""
    path = ROOT / rel_path
    text = _read_text(path)
    if text:
        return text
    text_path = path.parent / "_text" / f"{path.stem}.txt"
    return _read_text(text_path)


def _short_md_claims(ticker: str) -> list[dict]:
    sr = ROOT / ticker / "third-party-analyses" / "short_reports"
    if not sr.is_dir():
        return []
    out = []
    for md in sorted(sr.glob("*.md")):
        body = _read_text(md, 6000)
        claims = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith(("-", "*", "•")) and len(line) > 10:
                claims.append(line.lstrip("-*• ").strip())
        out.append({"path": str(md.relative_to(ROOT)).replace("\\", "/"), "claims": claims[:8]})
    return out


def _verdict_for_report(report: dict, ticker: str) -> str:
    side = report.get("side")
    source = report.get("source")
    if source == "sec_edgar":
        fc = report.get("filing_class") or ""
        if fc == "passive_13g":
            return "passive_institutional"
        if fc in {"activist_13d", "activist_proxy", "registry_13g", "activist_13g"}:
            return "needs_human"
        return "needs_human"
    if side == "short":
        return "needs_human"
    return "needs_human"


def reconcile_ticker(ticker: str, scan_date: str, *, write: bool = True) -> dict:
    index = load_ticker_index(ticker)
    reports = index.get("reports") or []
    pending = [r for r in reports if r.get("status") in ("new", "cached") and r.get("include_in_feed", True)]
    short_md = _short_md_claims(ticker)
    rows = []
    for report in pending:
        verdict = _verdict_for_report(report, ticker)
        excerpt = _report_text(report)[:1200]
        rows.append(
            {
                "firm": report.get("firm_name") or report.get("firm_id"),
                "side": report.get("side"),
                "date": report.get("report_date"),
                "source": report.get("source"),
                "filing_class": report.get("filing_class"),
                "path": report.get("local_file") or report.get("local_pdf"),
                "verdict": verdict,
                "excerpt": excerpt[:400],
            }
        )
        report["milly_verdict"] = verdict
        report["status"] = "reconciled_milly"

    if write and pending:
        save_ticker_index(ticker, index)

    out_path = ROOT / ticker / "research" / f"activist_reconcile_{scan_date}.md"
    lines = [
        f"# {ticker} — Activist reconciliation (Milly mechanical)",
        "",
        f"**Date:** {scan_date}",
        f"**Pending reports reconciled:** {len(rows)}",
        "",
        "## Summary",
        "",
        "| Firm | Side | Date | Class | Verdict | Path |",
        "|------|------|------|-------|---------|------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['firm']} | {row['side']} | {row['date']} | {row.get('filing_class') or '—'} | "
            f"{row['verdict']} | `{row.get('path') or '—'}` |"
        )
    if short_md:
        lines.extend(["", "## Short markdown cache", ""])
        for block in short_md:
            lines.append(f"### `{block['path']}`")
            for claim in block["claims"]:
                lines.append(f"- {claim}")
            lines.append("")
    if rows:
        lines.extend(["", "## Notes", ""])
        for row in rows:
            if row.get("excerpt"):
                lines.append(f"**{row['firm']}** ({row['date']}): {row['excerpt'][:280]}…")
                lines.append("")
    lines.extend(
        [
            "## [HUMAN REVIEW]",
            "",
            "- Confirm activist 13D intent vs passive 13G before stance changes.",
            "- Short claims require filing cross-check per `short_activist_registry.md`.",
            "",
        ]
    )
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")

    return {"ticker": ticker, "reconciled": len(rows), "path": str(out_path.relative_to(ROOT)) if write else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", action="append")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tickers = [t.upper() for t in args.ticker] if args.ticker else portfolio_tickers()
    total = 0
    touched = []
    for ticker in tickers:
        index = load_ticker_index(ticker)
        pending = [
            r
            for r in (index.get("reports") or [])
            if r.get("status") in ("new", "cached") and r.get("include_in_feed", True)
        ]
        if not pending and not _short_md_claims(ticker):
            continue
        result = reconcile_ticker(ticker, args.date, write=not args.dry_run)
        total += result["reconciled"]
        touched.append(ticker)
    print(f"Milly activist reconcile: {total} reports across {len(touched)} tickers")
    for t in touched:
        print(f"  {t}: {activist_index_path(t).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
