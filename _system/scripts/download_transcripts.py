#!/usr/bin/env python3
"""Download earnings/conference transcripts into ticker transcripts folders.

Sources (waterfall):
  1. Company IR / Q4 JSON feeds (PDF)
  2. Polygon Benzinga earnings calendar (timing + gap detection only)
  3. Vicki shopbot brief when reported earnings lack transcript after grace period

Writes:
  {TICKER}/investor-documents/transcripts/  (US/CA/OTC)
  {TICKER}/03_Events/Transcripts/           (Japan)
  {TICKER}/investor-documents/TRANSCRIPT_MANIFEST.json
  {TICKER}/research/evidence/earnings_calendar.json  (per-ticker verified subset)
  _system/data/earnings_calendar.json                (portfolio cache)

Usage:
  python download_transcripts.py
  python download_transcripts.py ICE META --since 2025-01-01
  python download_transcripts.py --register-legacy
  python download_transcripts.py --dry-run ICE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import load_registry, US_CONFIG_PATH  # noqa: E402
from polygon_earnings import (  # noqa: E402
    earnings_needing_transcript,
    fetch_portfolio_earnings,
    load_earnings_cache,
    save_earnings_cache,
    verified_display_events,
)
from transcript_common import (  # noqa: E402
    ROOT,
    add_manifest_entry,
    canonical_filename,
    download_file,
    earnings_calendar_path,
    file_sha256,
    harvest_transcript_urls,
    load_manifest,
    log,
    make_period_checker,
    parse_event_metadata,
    save_manifest,
    scan_legacy_transcripts,
    transcripts_dir,
    write_vicki_brief,
)

POST_EARNINGS_DAYS = int(__import__("os").getenv("TRANSCRIPT_POST_EARNINGS_DAYS", "14"))
VICKI_GRACE_DAYS = int(__import__("os").getenv("TRANSCRIPT_VICKI_GRACE_DAYS", "3"))
SYNC_SUMMARY_PATH = ROOT / "_system" / "data" / "transcript_sync_summary.json"


def _ir_roots(ticker: str, holding: dict) -> list[str]:
    dl = holding.get("download") or {}
    roots = list(dl.get("ir_roots") or [])
    if roots:
        return roots
    us_cfg = json.loads(US_CONFIG_PATH.read_text(encoding="utf-8"))
    return list((us_cfg.get(ticker) or {}).get("ir_roots") or [])


def _save_ticker_earnings(ticker: str, portfolio_events: list[dict]) -> None:
    subset = [e for e in portfolio_events if e.get("portfolio_ticker") == ticker]
    verified = verified_display_events(subset)
    path = earnings_calendar_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ticker": ticker,
                "as_of": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "verified_only": True,
                "events": verified,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _download_ir_transcripts(
    ticker: str,
    market: str,
    ir_roots: list[str],
    log_file: Path,
    *,
    since: date | None,
    dry_run: bool,
) -> int:
    if not ir_roots:
        return 0
    urls = harvest_transcript_urls(ir_roots, log_file)
    dest_dir = transcripts_dir(ticker, market)
    manifest = load_manifest(ticker)
    added = 0

    for url in sorted(urls):
        orig_name = url.rsplit("/", 1)[-1]
        if any(e.get("original_url") == url for e in manifest.get("entries") or []):
            continue
        meta = parse_event_metadata(url, orig_name)
        if since and meta.get("call_date"):
            try:
                if date.fromisoformat(meta["call_date"]) < since:
                    continue
            except ValueError:
                pass

        source_hash = hashlib.sha256(url.encode()).hexdigest()
        ext = ".pdf" if url.lower().endswith(".pdf") else ".pdf"
        fname = canonical_filename(
            call_date=meta.get("call_date"),
            event_type=meta.get("event_type", "other"),
            fiscal_period=meta.get("fiscal_period"),
            source_hash=source_hash,
            ext=ext,
        )
        dest = dest_dir / fname
        rel = str(dest.relative_to(ROOT / ticker)).replace("\\", "/")

        if dry_run:
            log(log_file, f"DRY-RUN would download {url} -> {dest}")
            continue

        if not download_file(url, dest, log_file):
            continue

        file_id = f"sha256:{file_sha256(dest)}"
        if add_manifest_entry(
            manifest,
            canonical_path=rel,
            original_url=url,
            original_filename=orig_name,
            meta=meta,
            source="q4_event_feed",
            bytes_count=dest.stat().st_size,
            file_id=file_id,
        ):
            added += 1

    if added and not dry_run:
        save_manifest(ticker, manifest)
    return added


def _maybe_vicki_brief(
    ticker: str,
    holding: dict,
    events: list[dict],
    manifest: dict,
    log_file: Path,
    *,
    dry_run: bool,
) -> bool:
    ir_roots = _ir_roots(ticker, holding)
    checker = make_period_checker(manifest)
    missing = earnings_needing_transcript(
        events,
        portfolio_ticker=ticker,
        has_transcript_for_period=checker,
        post_earnings_days=POST_EARNINGS_DAYS,
    )
    if not missing:
        return False

    ev = missing[0]
    d_str = ev.get("date")
    if not d_str:
        return False
    try:
        ed = date.fromisoformat(d_str[:10])
    except ValueError:
        return False
    age = (date.today() - ed).days
    if age < VICKI_GRACE_DAYS:
        log(log_file, f"VICKI wait T+{age} < grace {VICKI_GRACE_DAYS} for {ticker}")
        return False

    if dry_run:
        log(log_file, f"DRY-RUN would write Vicki brief for {ticker} ({ev.get('fiscal_period')} {d_str})")
        return True

    path = write_vicki_brief(
        ticker,
        earnings_event=ev,
        ir_roots=ir_roots,
        reason=f"No local transcript {age} days after verified reported earnings",
    )
    log(log_file, f"VICKI brief -> {path}")
    return True


def _manifest_entry_count(ticker: str) -> int:
    return len(load_manifest(ticker).get("entries") or [])


def merge_sync_summaries(existing: dict | None, new_rows: list[dict]) -> list[dict]:
    """Merge per-ticker rows by ticker key; new_rows win on conflict."""
    by_ticker: dict[str, dict] = {}
    for row in (existing or {}).get("tickers") or []:
        t = row.get("ticker")
        if t:
            by_ticker[t] = row
    for row in new_rows:
        t = row.get("ticker")
        if t:
            by_ticker[t] = row
    return [by_ticker[t] for t in sorted(by_ticker)]


def build_sync_summary_payload(
    ticker_rows: list[dict],
    *,
    run_mode: str,
    tickers_processed: int,
    polygon_enabled: bool,
) -> dict:
    totals = {
        "downloaded": sum(r.get("downloaded") or 0 for r in ticker_rows),
        "legacy_registered": sum(r.get("legacy_registered") or 0 for r in ticker_rows),
        "manifest_entries": sum(r.get("manifest_entries") or 0 for r in ticker_rows),
        "errors": sum(1 for r in ticker_rows if r.get("error")),
        "vicki_briefs": sum(1 for r in ticker_rows if r.get("vicki_brief")),
    }
    return {
        "as_of": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_mode": run_mode,
        "tickers_processed": tickers_processed,
        "tickers_in_summary": len(ticker_rows),
        "polygon_enabled": polygon_enabled,
        "totals": totals,
        "tickers": ticker_rows,
    }


def write_sync_summary(
    new_rows: list[dict],
    *,
    merge: bool,
    run_mode: str,
    tickers_processed: int,
    polygon_enabled: bool,
) -> Path:
    existing = None
    if merge and SYNC_SUMMARY_PATH.exists():
        try:
            existing = json.loads(SYNC_SUMMARY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
    merged_rows = merge_sync_summaries(existing, new_rows) if merge else new_rows
    payload = build_sync_summary_payload(
        merged_rows,
        run_mode=run_mode,
        tickers_processed=tickers_processed,
        polygon_enabled=polygon_enabled,
    )
    SYNC_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_SUMMARY_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return SYNC_SUMMARY_PATH


def process_ticker(
    ticker: str,
    holding: dict,
    portfolio_events: list[dict],
    *,
    since: date | None,
    register_legacy: bool,
    legacy_only: bool,
    dry_run: bool,
) -> dict:
    market = holding.get("market") or "US"
    ticker_dir = ROOT / ticker
    log_file = ticker_dir / "_download_log.txt"
    ir_roots = _ir_roots(ticker, holding)
    summary = {
        "ticker": ticker,
        "downloaded": 0,
        "legacy_registered": 0,
        "vicki_brief": False,
        "manifest_entries": 0,
        "ir_roots_count": len(ir_roots),
        "error": None,
    }

    try:
        if register_legacy and not dry_run:
            summary["legacy_registered"] = scan_legacy_transcripts(ticker, market)

        if not legacy_only:
            summary["downloaded"] = _download_ir_transcripts(
                ticker, market, ir_roots, log_file, since=since, dry_run=dry_run
            )

        if not dry_run and not legacy_only:
            _save_ticker_earnings(ticker, portfolio_events)
            manifest = load_manifest(ticker)
            summary["vicki_brief"] = _maybe_vicki_brief(
                ticker, holding, portfolio_events, manifest, log_file, dry_run=dry_run
            )

        summary["manifest_entries"] = _manifest_entry_count(ticker)
    except Exception as exc:  # noqa: BLE001 — continue portfolio run on single-ticker failure
        summary["error"] = f"{type(exc).__name__}: {exc}"
        log(log_file, f"TRANSCRIPT ERROR {summary['error']}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Download portfolio earnings transcripts")
    parser.add_argument("tickers", nargs="*", help="Portfolio tickers (default: all holdings)")
    parser.add_argument("--since", help="Only ingest transcripts on/after YYYY-MM-DD")
    parser.add_argument(
        "--register-legacy",
        action="store_true",
        help="Register existing transcript PDFs in manifest (default: on)",
    )
    parser.add_argument(
        "--no-register-legacy",
        action="store_true",
        help="Skip legacy PDF registration",
    )
    parser.add_argument(
        "--legacy-only",
        action="store_true",
        help="Only register legacy PDFs; skip IR harvest and Vicki briefs",
    )
    parser.add_argument("--skip-earnings-fetch", action="store_true", help="Use cached earnings calendar only")
    parser.add_argument(
        "--no-summary-merge",
        action="store_true",
        help="Replace transcript_sync_summary.json instead of merging partial runs",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reg = load_registry()
    holdings = reg.get("holdings") or {}
    all_holdings = sorted(holdings.keys())
    tickers = args.tickers or all_holdings
    since = date.fromisoformat(args.since) if args.since else None
    register_legacy = not args.no_register_legacy
    partial_run = bool(args.tickers)
    run_mode = "partial" if partial_run else "full"

    if args.skip_earnings_fetch or args.legacy_only:
        cache = load_earnings_cache()
        portfolio_events = cache.get("events") or []
        polygon_enabled = bool(cache.get("polygon_enabled"))
    else:
        payload = fetch_portfolio_earnings(tickers=tickers if partial_run else None)
        portfolio_events = payload.get("events") or []
        polygon_enabled = bool(payload.get("polygon_enabled"))
        if not args.dry_run:
            save_earnings_cache(payload)

    summaries = []
    for ticker in tickers:
        holding = holdings.get(ticker)
        if not holding:
            print(f"SKIP unknown ticker {ticker}")
            continue
        if not (ROOT / ticker).is_dir():
            print(f"SKIP no folder {ticker}")
            continue
        summaries.append(
            process_ticker(
                ticker,
                holding,
                portfolio_events,
                since=since,
                register_legacy=register_legacy,
                legacy_only=args.legacy_only,
                dry_run=args.dry_run,
            )
        )

    if not args.dry_run:
        out_path = write_sync_summary(
            summaries,
            merge=partial_run and not args.no_summary_merge,
            run_mode=run_mode,
            tickers_processed=len(summaries),
            polygon_enabled=polygon_enabled,
        )
        print(f"Summary -> {out_path}")

    total_dl = sum(s["downloaded"] for s in summaries)
    total_legacy = sum(s["legacy_registered"] for s in summaries)
    total_manifest = sum(s.get("manifest_entries") or 0 for s in summaries)
    total_errors = sum(1 for s in summaries if s.get("error"))
    print(
        f"\nTranscript sync done: {total_dl} new downloads, "
        f"{total_legacy} legacy registered, {total_manifest} manifest entries, "
        f"{total_errors} errors"
    )


if __name__ == "__main__":
    main()
