#!/usr/bin/env python3
"""Orchestrate activist source scanning for portfolio tickers.

Usage:
  python scan_activist_sources.py
  python scan_activist_sources.py --ticker APLD
  python scan_activist_sources.py --dry-run
  python scan_activist_sources.py --sec-only
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from activist_common import (
    activist_index_path,
    activist_reports_dir,
    load_global_scan,
    load_ticker_index,
    now_iso,
    portfolio_tickers,
    save_global_scan,
    save_ticker_index,
    upsert_report,
)
from activist_date_parse import parse_local_report_metadata
from sec_filer_parse import is_sec_filing_relpath
from build_activist_feed import build_feed
from extract_activist_text import extract_ticker_activist_text
from milly_activist_reconcile import reconcile_ticker
from sec_activist_scan import scan_portfolio_sec
from site_activist_scan import scan_publisher_sites
from third_party_inventory import write_inventory

ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = ROOT / "_system" / "research"
PENDING_DIR = ROOT / "_system" / "reviews" / "pending"


def collect_local_reports(ticker: str) -> list[dict]:
    out: list[dict] = []
    for side in ("long", "short"):
        base = activist_reports_dir(ticker, side)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel_path = str(path.relative_to(ROOT)).replace("\\", "/")
            if is_sec_filing_relpath(rel_path):
                continue
            if path.suffix.lower() not in {".pdf", ".html", ".htm"}:
                continue
            meta = parse_local_report_metadata(path, side)
            meta["local_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            if meta.get("local_pdf"):
                meta["local_pdf"] = meta["local_file"]
            out.append(
                {
                    "ticker": ticker,
                    **meta,
                    "source": "local",
                    "status": "cached",
                }
            )
    return out


def write_review_queue(all_hits: list[dict], scan_date: str) -> Path | None:
    new_hits = [h for h in all_hits if h.get("status") == "new" or h.get("confidence", 1) < 0.7]
    if not new_hits:
        return None
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    out = PENDING_DIR / f"activist_scan_{scan_date}.md"
    lines = [
        f"# Activist scan review queue",
        "",
        f"**Date:** {scan_date}",
        f"**Hits:** {len(new_hits)} new or low-confidence",
        "",
        "| Ticker | Side | Firm | Date | Source | Confidence |",
        "|--------|------|------|------|--------|------------|",
    ]
    for hit in new_hits[:200]:
        lines.append(
            f"| {hit.get('ticker', '—')} | {hit.get('side', '—')} | {hit.get('firm_id', '—')} | "
            f"{hit.get('report_date', '—')} | {hit.get('source', '—')} | {hit.get('confidence', '—')} |"
        )
    lines.extend(["", "Reconcile in `{TICKER}/research/adversarial_{date}.md`.", ""])
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_portfolio_scan_md(all_hits: list[dict], scan_date: str, tickers: list[str]) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / f"activist_scan_{scan_date}.md"
    by_ticker: dict[str, list[dict]] = {t: [] for t in tickers}
    for hit in all_hits:
        t = hit.get("ticker")
        if t in by_ticker:
            by_ticker[t].append(hit)
    lines = [
        f"# Portfolio activist scan",
        "",
        f"**Date:** {scan_date}",
        f"**Registry:** `_system/frameworks/activist_firm_registry.json`",
        "",
        "| Ticker | Long | Short | Latest | Notes |",
        "|--------|------|-------|--------|-------|",
    ]
    for ticker in tickers:
        index = load_ticker_index(ticker)
        reports = [r for r in (index.get("reports") or []) if r.get("include_in_feed", True)]
        long_n = sum(1 for r in reports if r.get("side") == "long")
        short_n = sum(1 for r in reports if r.get("side") == "short")
        latest = max((r.get("report_date") or "" for r in reports), default="")
        note = f"{len(reports)} indexed" if reports else "no hits"
        lines.append(f"| {ticker} | {long_n} | {short_n} | {latest or '—'} | {note} |")
    lines.extend(
        [
            "",
            "Run: `python _system/scripts/scan_activist_sources.py`",
            "Drive drop: `Admin/Activist/Long/{TICKER}/` or `Admin/Activist/Short/{TICKER}/`",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan activist long/short sources for portfolio tickers.")
    parser.add_argument("--ticker", action="append", help="Restrict to ticker (repeatable)")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sec-only", action="store_true")
    parser.add_argument("--site-only", action="store_true")
    parser.add_argument("--skip-feed", action="store_true")
    parser.add_argument("--include-passive", action="store_true", help="Index passive SC 13G filings")
    parser.add_argument("--reindex-local", action="store_true", help="Re-parse local SEC files without re-download")
    parser.add_argument("--reconcile", action="store_true", help="Run Milly activist mechanical reconcile after scan")
    args = parser.parse_args()

    tickers = [t.upper() for t in args.ticker] if args.ticker else portfolio_tickers()
    all_hits: list[dict] = []

    if not args.site_only:
        sec = scan_portfolio_sec(
            tickers,
            dry_run=args.dry_run,
            include_passive=args.include_passive,
            reindex_local=args.reindex_local,
        )
        all_hits.extend(sec.get("hits") or [])

    if not args.sec_only:
        site = scan_publisher_sites(tickers, dry_run=args.dry_run)
        all_hits.extend(site.get("hits") or [])

    for ticker in tickers:
        local = collect_local_reports(ticker)
        if not args.dry_run:
            index = load_ticker_index(ticker)
            changed = False
            for hit in local:
                entry = {k: v for k, v in hit.items() if k != "ticker"}
                entry.setdefault("status", "cached")
                entry.setdefault("tier", "context")
                if upsert_report(index, entry):
                    changed = True
            if changed:
                save_ticker_index(ticker, index)
        all_hits.extend(local)
        if not args.dry_run:
            extract_ticker_activist_text(ticker)
            write_inventory(ticker)

    payload = {
        "generated_at": now_iso(),
        "scan_date": args.date,
        "dry_run": args.dry_run,
        "ticker_count": len(tickers),
        "hit_count": len(all_hits),
        "hits": all_hits,
    }
    if not args.dry_run:
        save_global_scan(payload)

    write_portfolio_scan_md(all_hits, args.date, tickers)
    write_review_queue(all_hits, args.date)

    if not args.dry_run:
        from cleanup_activist_false_positives import cleanup_ticker

        for ticker in tickers:
            index_path = activist_index_path(ticker)
            if index_path.exists():
                cleanup_ticker(ticker, apply=True)

    if not args.skip_feed and not args.dry_run:
        build_feed()

    if args.reconcile and not args.dry_run:
        for ticker in tickers:
            index = load_ticker_index(ticker)
            pending = [
                r
                for r in (index.get("reports") or [])
                if r.get("status") in ("new", "cached") and r.get("include_in_feed", True)
            ]
            if pending:
                reconcile_ticker(ticker, args.date, write=True)

    print(f"Activist scan complete: {len(tickers)} tickers, {len(all_hits)} hits")
    for ticker in tickers:
        idx = activist_index_path(ticker)
        if idx.exists():
            count = len(load_ticker_index(ticker).get("reports") or [])
            print(f"  {ticker}: {count} indexed -> {idx.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
