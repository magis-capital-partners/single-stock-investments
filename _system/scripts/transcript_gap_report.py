#!/usr/bin/env python3
"""Report transcript coverage gaps for portfolio holdings.

Writes: _system/reviews/pending/transcript_coverage_{date}.md
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from polygon_earnings import latest_reported_earnings, load_earnings_cache, verified_display_events
from portfolio_registry import load_registry
from transcript_common import (
    ROOT,
    load_manifest,
    make_period_checker,
    manifest_path,
)

REVIEWS_DIR = ROOT / "_system" / "reviews" / "pending"


def _latest_transcript(manifest: dict) -> dict | None:
    entries = [e for e in manifest.get("entries") or [] if e.get("event_type") in ("earnings", "other")]
    if not entries:
        return None
    entries.sort(key=lambda e: (e.get("call_date") or "", e.get("downloaded_at") or ""), reverse=True)
    return entries[0]


def build_report() -> str:
    today = date.today().isoformat()
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    cache = load_earnings_cache()
    events = cache.get("events") or []

    rows: list[dict] = []
    covered = 0
    for ticker in sorted(holdings.keys()):
        manifest = load_manifest(ticker)
        latest_tx = _latest_transcript(manifest)
        latest_er = latest_reported_earnings(events, ticker)
        checker = make_period_checker(manifest)

        gap = False
        gap_reason = ""
        if latest_er:
            fp = latest_er.get("fiscal_period")
            fy = latest_er.get("fiscal_year")
            ed = latest_er.get("date")
            if not checker(fp, fy, ed):
                gap = True
                gap_reason = f"Missing transcript for reported {fp} ({ed})"
            else:
                covered += 1
        elif not latest_tx:
            gap = True
            gap_reason = "No transcripts in manifest; no verified reported earnings in cache"

        rows.append({
            "ticker": ticker,
            "latest_transcript_date": latest_tx.get("call_date") if latest_tx else None,
            "latest_transcript_path": latest_tx.get("canonical_path") if latest_tx else None,
            "latest_reported_earnings": latest_er.get("date") if latest_er else None,
            "latest_reported_period": latest_er.get("fiscal_period") if latest_er else None,
            "gap": gap,
            "gap_reason": gap_reason,
            "manifest_entries": len(manifest.get("entries") or []),
        })

    gaps = [r for r in rows if r["gap"]]
    lines = [
        f"# Transcript coverage — {today}",
        "",
        f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Earnings cache:** `_system/data/earnings_calendar.json` (verified Polygon Benzinga only)  ",
        "",
        "## Summary",
        "",
        f"- Holdings with latest reported earnings covered: **{covered}/{len(rows)}**",
        f"- Gaps: **{len(gaps)}**",
        "",
        "## Per-ticker",
        "",
        "| Ticker | Latest transcript | Latest reported earnings | Gap | Reason |",
        "|--------|-------------------|--------------------------|-----|--------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['ticker']} | {r['latest_transcript_date'] or '—'} | "
            f"{r['latest_reported_period'] or '—'} {r['latest_reported_earnings'] or ''} | "
            f"{'yes' if r['gap'] else 'no'} | {r['gap_reason'] or '—'} |"
        )

    if gaps:
        lines.extend(["", "## Action items", ""])
        for r in gaps:
            brief = ROOT / r["ticker"] / "research" / "shopbot" / f"transcript_harvest_{today}.md"
            vicki = "Vicki brief exists" if brief.exists() else "Run download_transcripts (Vicki brief after T+3)"
            lines.append(f"- **{r['ticker']}**: {r['gap_reason']} — {vicki}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path = REVIEWS_DIR / f"transcript_coverage_{today}.md"
    path.write_text(build_report(), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
