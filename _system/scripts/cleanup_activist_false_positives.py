#!/usr/bin/env python3
"""Remove activist index false positives (site slug mismatches, weak alias matches)."""
from __future__ import annotations

import argparse
from pathlib import Path

from activist_common import (
    load_ticker_index,
    match_report_to_ticker,
    portfolio_tickers,
    save_ticker_index,
    ticker_meta,
    url_target_mismatch,
)

ROOT = Path(__file__).resolve().parents[2]


def report_blob(report: dict) -> str:
    parts = [
        report.get("title") or "",
        report.get("source_url") or "",
        report.get("local_file") or "",
        report.get("local_pdf") or "",
        report.get("firm_name") or "",
    ]
    return " ".join(p for p in parts if p)


def should_keep(report: dict, meta: dict) -> tuple[bool, str]:
    source = report.get("source") or ""
    if source == "sec_edgar":
        return True, "sec_filing"
    if source == "short_reports_md":
        return True, "short_md_cache"
    if report.get("status") == "rejected_false_positive":
        return False, "already_rejected"

    blob = report_blob(report)
    url = report.get("source_url") or report.get("local_file") or ""
    title = report.get("title") or ""

    if source in {"publisher_site", "local"} and url_target_mismatch(url, title, meta):
        return False, "url_slug_mismatch"

    if source in {"publisher_site", "local"}:
        matched, confidence, reason = match_report_to_ticker(blob, meta)
        if not matched or confidence < 0.9:
            return False, f"weak_match:{reason}:{confidence:.2f}"

    if source == "local" and not report.get("title") and not report.get("source_url"):
        # Duplicate stub rows from pre-SEC local collector
        if report.get("firm_id") in {"spruce", "SC-13D", "SC-13G"}:
            return False, "stale_local_stub"

    return True, "ok"


def cleanup_ticker(ticker: str, *, apply: bool) -> dict:
    meta = ticker_meta(ticker)
    index = load_ticker_index(ticker)
    kept: list[dict] = []
    removed: list[dict] = []
    deleted_files: list[str] = []

    for report in index.get("reports") or []:
        keep, reason = should_keep(report, meta)
        if keep:
            kept.append(report)
            continue
        removed.append({**report, "reject_reason": reason})
        if apply:
            for key in ("local_file", "local_pdf"):
                rel_path = report.get(key)
                if not rel_path:
                    continue
                path = ROOT / rel_path
                if path.exists() and path.suffix.lower() in {".html", ".htm"}:
                    path.unlink()
                    deleted_files.append(rel_path)

    if apply and removed:
        index["reports"] = kept
        save_ticker_index(ticker, index)

    return {
        "ticker": ticker,
        "kept": len(kept),
        "removed": len(removed),
        "deleted_files": deleted_files,
        "removed_samples": removed[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", action="append")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tickers = [t.upper() for t in args.ticker] if args.ticker else portfolio_tickers()
    total_removed = 0
    total_deleted = 0
    for ticker in tickers:
        index_path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
        if not index_path.exists():
            continue
        result = cleanup_ticker(ticker, apply=not args.dry_run)
        if result["removed"]:
            total_removed += result["removed"]
            total_deleted += len(result["deleted_files"])
            print(
                f"{ticker}: removed {result['removed']} false positives "
                f"(kept {result['kept']})"
            )
    print(f"Cleanup complete: {total_removed} removed, {total_deleted} html files deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
