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
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from activist_common import (
    activist_index_path,
    activist_reports_dir,
    firms_for_ingest,
    load_global_scan,
    load_ticker_index,
    now_iso,
    portfolio_tickers,
    save_global_scan,
    save_ticker_index,
    upsert_report,
    write_json,
)
from activist_date_parse import parse_local_report_metadata
from sec_filer_parse import is_sec_filing_relpath
from build_activist_feed import build_feed
from extract_activist_text import extract_ticker_activist_text
from milly_activist_reconcile import reconcile_ticker
from activist_triage import triage_portfolio
from activist_short_md import collect_short_markdown_reports
from press_activist_digest import scan_press_wires
from sec_filer_discovery import OUTPUT_PATH as DISCOVERY_OUTPUT
from sec_filer_discovery import discover as discover_filers
from sec_activist_scan import scan_portfolio_sec, scan_ticker_sec  # noqa: F401 - scan_portfolio_sec kept for importers
from site_activist_scan import scan_firm_site, scan_publisher_sites  # noqa: F401
from third_party_inventory import write_inventory
from verify_activist_reports import verify_ticker

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
    """Legacy queue — kept for compatibility; triage queue is authoritative."""
    return None


def collect_human_review_rows(tickers: list[str]) -> list[dict]:
    rows: list[dict] = []
    for ticker in tickers:
        index = load_ticker_index(ticker)
        for report in index.get("reports") or []:
            if report.get("triage_verdict") == "human_review":
                rows.append({**report, "ticker": ticker})
    return rows


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


# --- Phases -------------------------------------------------------------------
# The scheduled job ran every lane (SEC, publisher sites, press wires, filer
# discovery, triage) in one silent command, and it hit the 90-minute job limit
# on every run from 2026-08-03 onward. GitHub reports a timed-out job as
# "cancelled", so nothing went red, and the "activist scan sync" commit last
# landed 2026-08-02. Each phase now runs on its own (``--phase``) with its own
# budget, prints progress, and records what it covered in STATE_PATH, so a
# partial run is committed and the next run resumes with the stalest names.
STATE_PATH = ROOT / "_system" / "data" / "activist_scan_state.json"
PHASES = ("all", "sec", "sites", "wires", "discovery", "finalize")
FETCH_PHASES = ("sec", "sites", "wires", "discovery")
PROGRESS_EVERY = 25


class Budget:
    """Minutes a phase may keep STARTING work; ``None`` is unlimited."""

    def __init__(self, minutes: float | None, clock=time.monotonic) -> None:
        self._clock = clock
        self.minutes = minutes
        self.start = clock()

    def elapsed(self) -> float:
        return self._clock() - self.start

    def exhausted(self) -> bool:
        return self.minutes is not None and self.elapsed() >= self.minutes * 60.0


def load_state(path: Path = STATE_PATH) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    state.setdefault("created_at", now_iso())
    return state


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    state["updated_at"] = now_iso()
    write_json(path, state)


def rotation_order(keys: list[str], last_done: dict[str, str]) -> list[str]:
    """Never-scanned first, then the stalest scan first (ties by name)."""
    return sorted(dict.fromkeys(keys), key=lambda key: (last_done.get(key) or "", key))


def _progress(phase: str, done: int, total: int, hits: int, budget: Budget) -> None:
    print(f"[activist:{phase}] {done}/{total} done, {hits} hits, {budget.elapsed():.0f}s", flush=True)


def _rotation_summary(scanned: int, total: int, hits: int, budget: Budget) -> dict:
    return {
        "at": now_iso(),
        "scanned": scanned,
        "total": total,
        "remaining": total - scanned,
        "budget_hit": scanned < total,
        "hits": hits,
        "elapsed_sec": round(budget.elapsed(), 1),
    }


def run_sec_phase(tickers: list[str], state: dict, budget: Budget, *, dry_run: bool = False,
                  include_passive: bool = False, reindex_local: bool = False,
                  fetch_xml: bool = False) -> list[dict]:
    """SEC activist filings per ticker, stalest first, until the budget runs out."""
    phase = state.setdefault("sec", {})
    last = phase.setdefault("last_scanned", {})
    order = rotation_order(tickers, last)
    hits: list[dict] = []
    scanned = 0
    for ticker in order:
        if budget.exhausted():
            break
        ticker_hits = scan_ticker_sec(
            ticker,
            dry_run=dry_run,
            include_passive=include_passive,
            reindex_local=reindex_local,
            fetch_xml=fetch_xml,
        )
        for hit in ticker_hits:
            hit["ticker"] = ticker
        hits.extend(ticker_hits)
        last[ticker] = now_iso()
        scanned += 1
        if scanned % PROGRESS_EVERY == 0:
            _progress("sec", scanned, len(order), len(hits), budget)
    _progress("sec", scanned, len(order), len(hits), budget)
    phase["last_run"] = _rotation_summary(scanned, len(order), len(hits), budget)
    return hits


def run_sites_phase(tickers: list[str], state: dict, budget: Budget, *,
                    dry_run: bool = False) -> list[dict]:
    """Publisher-site scrape per firm, stalest firm first, until the budget runs out."""
    firms = {str(firm.get("id") or ""): firm for firm in firms_for_ingest("site_index")}
    phase = state.setdefault("sites", {})
    last = phase.setdefault("last_scanned", {})
    order = rotation_order([key for key in firms if key], last)
    hits: list[dict] = []
    scanned = 0
    for firm_id in order:
        if budget.exhausted():
            break
        try:
            hits.extend(scan_firm_site(firms[firm_id], tickers, dry_run=dry_run))
        except Exception as exc:  # noqa: BLE001 - one publisher never sinks the phase
            print(f"[activist:sites] {firm_id} failed: {type(exc).__name__}: {str(exc)[:160]}")
        last[firm_id] = now_iso()
        scanned += 1
        if scanned % PROGRESS_EVERY == 0:
            _progress("sites", scanned, len(order), len(hits), budget)
    _progress("sites", scanned, len(order), len(hits), budget)
    phase["last_run"] = _rotation_summary(scanned, len(order), len(hits), budget)
    return hits


def run_wires_phase(tickers: list[str], state: dict, budget: Budget, *, dry_run: bool = False,
                    backfill_days: int | None = None, scan_date: str | None = None) -> list[dict]:
    print("[activist:wires] polling press wires and curated seeds", flush=True)
    wire = scan_press_wires(
        tickers, dry_run=dry_run, backfill_days=backfill_days, scan_date=scan_date
    )
    hits = wire.get("hits") or []
    _progress("wires", 1, 1, len(hits), budget)
    state.setdefault("wires", {})["last_run"] = {
        "at": now_iso(),
        "hits": len(hits),
        "elapsed_sec": round(budget.elapsed(), 1),
    }
    return hits


def run_discovery_phase(state: dict, budget: Budget, *, scan_date: str, dry_run: bool = False,
                        min_date: str | None = None,
                        min_interval_days: float | None = None) -> bool:
    """Filer-driven discovery (what registry firms filed, anywhere). Returns True if it ran.

    It surfaces campaigns at companies we do not hold, so its rows never enter
    a ticker index; they land in activist_filer_discovery.json for review.
    ``min_interval_days`` makes a daily job run it weekly.
    """
    phase = state.setdefault("discovery", {})
    last_done = phase.get("last_completed_at")
    if min_interval_days is not None and last_done:
        try:
            age_days = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(str(last_done).replace("Z", "+00:00"))
            ).total_seconds() / 86400
        except ValueError:
            age_days = None
        if age_days is not None and age_days < min_interval_days:
            print(
                f"[activist:discovery] skipped: last pass {age_days:.1f} days ago "
                f"(interval {min_interval_days} days)"
            )
            return False
    min_date = min_date or (date.fromisoformat(scan_date) - timedelta(days=548)).isoformat()
    print(f"[activist:discovery] filer discovery since {min_date}", flush=True)
    try:
        found = discover_filers(min_date=min_date, write_registry_ciks=not dry_run)
    except Exception as exc:  # never let discovery break the other phases
        print(f"filer discovery skipped: {type(exc).__name__}: {exc}")
        phase["last_error"] = {"at": now_iso(), "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        return False
    if not dry_run:
        write_json(DISCOVERY_OUTPUT, found)
    print(
        f"filer discovery: {found['row_count']} filings from "
        f"{found['resolved_firm_count']}/{found['firm_count']} firms "
        f"({found['off_book_count']} outside the book) in {budget.elapsed():.0f}s"
    )
    phase["last_completed_at"] = now_iso()
    phase["last_run"] = {
        "at": now_iso(),
        "rows": found.get("row_count"),
        "elapsed_sec": round(budget.elapsed(), 1),
    }
    return True


def run_finalize_phase(tickers: list[str], state: dict, fetched_hits: list[dict], *,
                       scan_date: str, dry_run: bool = False, fetch_sec: bool = False,
                       skip_feed: bool = False, reconcile: bool = False) -> list[dict]:
    """Local collection, triage, the feed and reconcile -- no new reports are fetched."""
    budget = Budget(None)
    all_hits = list(fetched_hits)
    for done, ticker in enumerate(tickers, 1):
        local = collect_local_reports(ticker)
        short_md = collect_short_markdown_reports(ticker)
        if not dry_run:
            index = load_ticker_index(ticker)
            changed = False
            for hit in local + short_md:
                entry = {k: v for k, v in hit.items() if k != "ticker"}
                entry.setdefault("status", "cached")
                entry.setdefault("tier", "context")
                if upsert_report(index, entry):
                    changed = True
            if changed:
                save_ticker_index(ticker, index)
        all_hits.extend(local)
        all_hits.extend(short_md)
        if not dry_run:
            extract_ticker_activist_text(ticker)
            verify_ticker(ticker)
            write_inventory(ticker)
        if done % (PROGRESS_EVERY * 4) == 0:
            _progress("finalize:collect", done, len(tickers), len(all_hits), budget)
    _progress("finalize:collect", len(tickers), len(tickers), len(all_hits), budget)

    payload = {
        "generated_at": now_iso(),
        "scan_date": scan_date,
        "dry_run": dry_run,
        "ticker_count": len(tickers),
        "hit_count": len(all_hits),
        "hits": all_hits,
        "phases": {name: (state.get(name) or {}).get("last_run") for name in FETCH_PHASES},
    }
    if not dry_run:
        save_global_scan(payload)

    write_portfolio_scan_md(all_hits, scan_date, tickers)

    if not dry_run:
        from cleanup_activist_false_positives import cleanup_ticker

        for ticker in tickers:
            index_path = activist_index_path(ticker)
            if index_path.exists():
                cleanup_ticker(ticker, apply=True)
        print(f"[activist:finalize] cleanup done at {budget.elapsed():.0f}s", flush=True)

        triage_summary = triage_portfolio(
            tickers=tickers,
            apply=True,
            fetch_sec=fetch_sec,
            scan_date=scan_date,
        )
        print(
            f"Triage: {triage_summary.get('total_reports', 0)} reports "
            f"({triage_summary.get('counts', {})}) at {budget.elapsed():.0f}s"
        )
        if triage_summary.get("human_count"):
            print(f"  Human queue: {triage_summary.get('queue_path')}")

    write_review_queue(all_hits, scan_date)

    if not skip_feed and not dry_run:
        build_feed()
        print(f"[activist:finalize] feed rebuilt at {budget.elapsed():.0f}s", flush=True)

    if reconcile and not dry_run:
        for ticker in tickers:
            index = load_ticker_index(ticker)
            pending = [
                r
                for r in (index.get("reports") or [])
                if r.get("include_in_feed", True)
                and (
                    r.get("triage_verdict") == "human_review"
                    or r.get("status") in ("new", "cached")
                    or (r.get("status") == "triaged_auto" and not r.get("milly_verdict"))
                )
            ]
            if pending:
                reconcile_ticker(ticker, scan_date, write=True)
        print(f"[activist:finalize] reconcile done at {budget.elapsed():.0f}s", flush=True)

    state.setdefault("finalize", {})["last_run"] = {
        "at": now_iso(),
        "tickers": len(tickers),
        "hits": len(all_hits),
        "elapsed_sec": round(budget.elapsed(), 1),
    }
    return all_hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan activist long/short sources for portfolio tickers.")
    parser.add_argument("--ticker", action="append", help="Restrict to ticker (repeatable)")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sec-only", action="store_true")
    parser.add_argument("--site-only", action="store_true")
    parser.add_argument("--wire-only", action="store_true", help="Only run press/letter digest ingest")
    parser.add_argument("--skip-feed", action="store_true")
    parser.add_argument("--skip-wire", action="store_true", help="Skip press/letter digest lane")
    parser.add_argument("--skip-site", action="store_true", help="Skip publisher site scrape")
    parser.add_argument("--include-passive", action="store_true", help="Index passive SC 13G filings")
    parser.add_argument("--reindex-local", action="store_true", help="Re-parse local SEC files without re-download")
    parser.add_argument(
        "--reindex-fetch-xml",
        action="store_true",
        help="During --reindex-local, also pull primary_doc.xml for post-2024-12-18 Schedules",
    )
    parser.add_argument("--reconcile", action="store_true", help="Run Milly activist mechanical reconcile after scan")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=None,
        help="Limit press-wire seeds to this many trailing days (default: all seeds)",
    )
    parser.add_argument(
        "--fetch-sec",
        action="store_true",
        help="Fetch SEC metadata during triage when local file missing",
    )
    parser.add_argument(
        "--discover-filers",
        action="store_true",
        help="Also run filer-driven discovery (what registry firms filed, anywhere)",
    )
    parser.add_argument(
        "--discover-min-date",
        default=None,
        help="Earliest filing date for filer-driven discovery (default: last 18 months)",
    )
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default="all",
        help="Run one phase (sec, sites, wires, discovery, finalize) or all of them in order",
    )
    parser.add_argument(
        "--budget-min",
        type=float,
        default=None,
        help="sec/sites: stop starting new tickers/firms after N minutes; the next run resumes",
    )
    parser.add_argument(
        "--min-interval-days",
        type=float,
        default=None,
        help="discovery: skip when the last completed pass is younger than this (weekly: 6.5)",
    )
    parser.add_argument("--state", default=str(STATE_PATH), help="Phase coverage/rotation state file")
    args = parser.parse_args(argv)

    tickers = [t.upper() for t in args.ticker] if args.ticker else portfolio_tickers()
    state_path = Path(args.state)
    state = load_state(state_path)

    def persist_state() -> None:
        if not args.dry_run:
            save_state(state, state_path)

    if args.phase == "sec":
        run_sec_phase(
            tickers, state, Budget(args.budget_min), dry_run=args.dry_run,
            include_passive=args.include_passive, reindex_local=args.reindex_local,
            fetch_xml=args.reindex_fetch_xml,
        )
        persist_state()
        return 0
    if args.phase == "sites":
        run_sites_phase(tickers, state, Budget(args.budget_min), dry_run=args.dry_run)
        persist_state()
        return 0
    if args.phase == "wires":
        run_wires_phase(
            tickers, state, Budget(None), dry_run=args.dry_run,
            backfill_days=args.backfill_days, scan_date=args.date,
        )
        persist_state()
        return 0
    if args.phase == "discovery":
        run_discovery_phase(
            state, Budget(None), scan_date=args.date, dry_run=args.dry_run,
            min_date=args.discover_min_date, min_interval_days=args.min_interval_days,
        )
        persist_state()
        return 0

    fetched: list[dict] = []
    if args.phase == "all":
        # The same lanes, flags and order as before the phases existed.
        if not args.site_only and not args.wire_only:
            fetched.extend(run_sec_phase(
                tickers, state, Budget(args.budget_min), dry_run=args.dry_run,
                include_passive=args.include_passive, reindex_local=args.reindex_local,
                fetch_xml=args.reindex_fetch_xml,
            ))
        if not args.sec_only and not args.wire_only and not args.skip_site:
            fetched.extend(
                run_sites_phase(tickers, state, Budget(args.budget_min), dry_run=args.dry_run)
            )
        if args.discover_filers:
            run_discovery_phase(
                state, Budget(None), scan_date=args.date, dry_run=args.dry_run,
                min_date=args.discover_min_date, min_interval_days=args.min_interval_days,
            )
        if not args.sec_only and not args.site_only and not args.skip_wire:
            fetched.extend(run_wires_phase(
                tickers, state, Budget(None), dry_run=args.dry_run,
                backfill_days=args.backfill_days, scan_date=args.date,
            ))

    all_hits = run_finalize_phase(
        tickers, state, fetched, scan_date=args.date, dry_run=args.dry_run,
        fetch_sec=args.fetch_sec, skip_feed=args.skip_feed, reconcile=args.reconcile,
    )
    persist_state()

    print(f"Activist scan complete: {len(tickers)} tickers, {len(all_hits)} hits")
    for ticker in tickers:
        idx = activist_index_path(ticker)
        if idx.exists():
            count = len(load_ticker_index(ticker).get("reports") or [])
            print(f"  {ticker}: {count} indexed -> {idx.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
