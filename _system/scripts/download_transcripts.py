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


def process_ticker(
    ticker: str,
    holding: dict,
    portfolio_events: list[dict],
    *,
    since: date | None,
    register_legacy: bool,
    dry_run: bool,
) -> dict:
    market = holding.get("market") or "US"
    ticker_dir = ROOT / ticker
    log_file = ticker_dir / "_download_log.txt"
    summary = {"ticker": ticker, "downloaded": 0, "legacy_registered": 0, "vicki_brief": False}

    if register_legacy and not dry_run:
        summary["legacy_registered"] = scan_legacy_transcripts(ticker, market)

    ir_roots = _ir_roots(ticker, holding)
    summary["downloaded"] = _download_ir_transcripts(
        ticker, market, ir_roots, log_file, since=since, dry_run=dry_run
    )

    if not dry_run:
        _save_ticker_earnings(ticker, portfolio_events)
        manifest = load_manifest(ticker)
        summary["vicki_brief"] = _maybe_vicki_brief(
            ticker, holding, portfolio_events, manifest, log_file, dry_run=dry_run
        )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Download portfolio earnings transcripts")
    parser.add_argument("tickers", nargs="*", help="Portfolio tickers (default: all holdings)")
    parser.add_argument("--since", help="Only ingest transcripts on/after YYYY-MM-DD")
    parser.add_argument("--register-legacy", action="store_true", help="Register existing transcript PDFs in manifest")
    parser.add_argument("--skip-earnings-fetch", action="store_true", help="Use cached earnings calendar only")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reg = load_registry()
    holdings = reg.get("holdings") or {}
    tickers = args.tickers or sorted(holdings.keys())
    since = date.fromisoformat(args.since) if args.since else None

    if args.skip_earnings_fetch:
        cache = load_earnings_cache()
        portfolio_events = cache.get("events") or []
    else:
        payload = fetch_portfolio_earnings(tickers=tickers if args.tickers else None)
        portfolio_events = payload.get("events") or []
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
                register_legacy=args.register_legacy or True,
                dry_run=args.dry_run,
            )
        )

    out_path = ROOT / "_system" / "data" / "transcript_sync_summary.json"
    if not args.dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "as_of": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "tickers": summaries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    total_dl = sum(s["downloaded"] for s in summaries)
    total_legacy = sum(s["legacy_registered"] for s in summaries)
    print(f"\nTranscript sync done: {total_dl} new downloads, {total_legacy} legacy registered")


if __name__ == "__main__":
    main()
