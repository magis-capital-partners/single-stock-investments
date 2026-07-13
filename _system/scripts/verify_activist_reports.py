#!/usr/bin/env python3
"""Verify activist report ticker assignments against the document body text.

Publisher-site and local rows are matched to tickers from title/URL only at
ingest time, which produces false positives. This pass reads the actual
document (HTML directly, PDFs via the extracted _text/*.txt sidecar) and
records whether the ticker or a distinctive company token appears in the body:

  body_verified: true / false, or absent when no text is available
  body_match_reason / body_hits: diagnostics for review

SEC EDGAR rows are exempt: they are CIK-scoped and already reliable.

Usage:
  python verify_activist_reports.py TICKER
  python verify_activist_reports.py --all
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from activist_common import (
    load_ticker_index,
    match_report_to_ticker,
    portfolio_tickers,
    resolve_report_file,
    save_ticker_index,
    ticker_meta,
)
from sec_filer_parse import strip_html

ROOT = Path(__file__).resolve().parents[2]
TEXT_LIMIT = 200_000


def _read_text(path: Path, limit: int = TEXT_LIMIT) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def load_body_text(report: dict) -> str | None:
    """Best-effort document body text for an index row, or None when unavailable."""
    ref, is_pdf, exists = resolve_report_file(report)
    if not ref or not exists:
        return None
    path = ROOT / ref
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        raw = _read_text(path)
        return strip_html(raw) if raw else None
    if suffix in (".md", ".txt"):
        return _read_text(path) or None
    if is_pdf or suffix == ".pdf":
        sidecar = path.parent / "_text" / f"{path.stem}.txt"
        text = _read_text(sidecar)
        if text:
            return text
        try:
            from extract_activist_text import extract_pdf

            out = extract_pdf(path, path.parent / "_text")
        except Exception:
            return None
        if out:
            return _read_text(out) or None
    return None


def _count_hits(text: str, meta: dict) -> int:
    hay = text.lower()
    hits = len(re.findall(rf"\b{re.escape(meta['ticker'].lower())}\b", hay))
    company = (meta.get("company") or "").lower()
    if company and len(company) >= 6:
        hits += hay.count(company)
    return hits


def verify_report(report: dict, meta: dict) -> bool:
    """Update body verification fields on the report in place. Returns True if changed."""
    if report.get("source") == "sec_edgar":
        return False
    text = load_body_text(report)
    if text is None:
        # No document body available: leave any prior verdict untouched.
        changed = report.get("body_match_reason") != "no_text" and "body_verified" not in report
        if "body_verified" not in report:
            report["body_match_reason"] = "no_text"
        return changed
    matched, confidence, reason = match_report_to_ticker(text, meta)
    if reason.startswith("alias:"):
        matched = False
    hits = _count_hits(text, meta)
    updates = {
        "body_verified": bool(matched),
        "body_match_reason": reason,
        "body_match_confidence": confidence,
        "body_hits": hits,
        "target_verified": bool(matched),
        "target_match_evidence": reason,
        "target_match_confidence": confidence,
    }
    changed = any(report.get(k) != v for k, v in updates.items())
    report.update(updates)
    return changed


def verify_ticker(ticker: str, *, write: bool = True) -> dict:
    meta = ticker_meta(ticker)
    index = load_ticker_index(ticker)
    verified = 0
    failed = 0
    no_text = 0
    changed = False
    for report in index.get("reports") or []:
        if report.get("source") == "sec_edgar":
            continue
        if verify_report(report, meta):
            changed = True
        state = report.get("body_verified")
        if state is True:
            verified += 1
        elif state is False:
            failed += 1
        else:
            no_text += 1
    if changed and write:
        save_ticker_index(ticker, index)
    return {"ticker": ticker, "verified": verified, "failed": failed, "no_text": no_text}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify activist report ticker matches against body text.")
    parser.add_argument("ticker", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tickers = portfolio_tickers() if args.all else ([args.ticker.upper()] if args.ticker else None)
    if not tickers:
        parser.error("Provide TICKER or --all")
    totals = {"verified": 0, "failed": 0, "no_text": 0}
    for ticker in tickers:
        result = verify_ticker(ticker, write=not args.dry_run)
        for key in totals:
            totals[key] += result[key]
        if result["failed"]:
            print(f"  {ticker}: {result['failed']} body-unverified rows")
    print(
        f"Body verification: {totals['verified']} verified, "
        f"{totals['failed']} failed, {totals['no_text']} without text"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
