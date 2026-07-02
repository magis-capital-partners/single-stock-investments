#!/usr/bin/env python3
"""Sanitize dashboard/data/activist_feed.json without requiring local index files."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEED_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"

import sys

sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_activist_feed import GITHUB_REPO, dedupe_proxy_amendments, github_blob  # noqa: E402
from build_activist_feed import WEAK_MATCH_TICKER_THRESHOLD  # noqa: E402


def clean_feed_payload(payload: dict) -> dict:
    rows = payload.get("feed") or []
    stem_counts: Counter[tuple[str, str]] = Counter()
    kept_rows: list[dict] = []

    for row in rows:
        ref = row.get("canonical_file") or row.get("local_pdf") or row.get("local_file")
        stem = Path(str(ref or "")).name
        if stem:
            stem_counts[(row.get("firm_id") or "", stem)] += 1

    removed_ghost = 0
    for row in rows:
        ref = row.get("canonical_file") or row.get("local_pdf") or row.get("local_file")
        exists = bool(ref) and (ROOT / str(ref).replace("\\", "/")).exists()
        source_url = row.get("source_url")
        if not exists and not source_url:
            removed_ghost += 1
            continue
        stem = Path(str(ref or "")).name
        weak_match = stem_counts.get((row.get("firm_id") or "", stem), 0) >= WEAK_MATCH_TICKER_THRESHOLD
        local_is_pdf = bool(row.get("local_pdf")) or str(ref or "").lower().endswith(".pdf")
        cleaned = {
            **row,
            "local_file": ref,
            "local_is_pdf": local_is_pdf,
            "file_exists": exists,
            "github_url": github_blob(str(ref)) if exists and ref else None,
            "weak_match": weak_match or bool(row.get("weak_match")),
            "needs_file": not exists and bool(source_url),
        }
        kept_rows.append(cleaned)

    kept_rows = dedupe_proxy_amendments(kept_rows)
    summary = dict(payload.get("summary") or {})
    summary.update(
        {
            "portfolio_hits": len(kept_rows),
            "long_count": sum(1 for r in kept_rows if r.get("side") == "long"),
            "short_count": sum(1 for r in kept_rows if r.get("side") == "short"),
            "tickers_with_hits": len({r.get("ticker") for r in kept_rows if r.get("ticker")}),
            "missing_file_count": sum(1 for r in kept_rows if not r.get("file_exists")),
            "weak_match_count": sum(1 for r in kept_rows if r.get("weak_match")),
            "ghost_pruned_count": removed_ghost,
            "missing_date_count": sum(1 for r in kept_rows if not r.get("report_date")),
            "unresolved_filer_count": sum(
                1 for r in kept_rows if r.get("needs_filer_review") or r.get("firm_id") == "unknown_activist"
            ),
        }
    )
    by_ticker: dict[str, dict] = {}
    for row in kept_rows:
        ticker = row.get("ticker") or ""
        bucket = by_ticker.setdefault(
            ticker,
            {"long_count": 0, "short_count": 0, "latest": None, "has_unreconciled": False},
        )
        if row.get("side") == "long":
            bucket["long_count"] += 1
        elif row.get("side") == "short":
            bucket["short_count"] += 1
        if row.get("status") in ("new", "cached"):
            bucket["has_unreconciled"] = True
        latest = bucket["latest"]
        if not latest or (row.get("report_date") or "") > (latest.get("date") or ""):
            bucket["latest"] = {
                "firm_id": row.get("firm_id"),
                "firm_name": row.get("firm_name"),
                "date": row.get("report_date"),
                "side": row.get("side"),
                "title": row.get("title"),
            }

    return {
        **payload,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "github_repo": GITHUB_REPO,
        "summary": summary,
        "by_ticker": by_ticker,
        "feed": kept_rows,
        "firms_active": len({r.get("firm_id") for r in kept_rows if r.get("firm_id")}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean activist feed JSON in place.")
    parser.add_argument("--input", type=Path, default=FEED_PATH)
    parser.add_argument("--output", type=Path, default=FEED_PATH)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    cleaned = clean_feed_payload(payload)
    args.output.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output.relative_to(ROOT)} "
        f"({cleaned['summary']['portfolio_hits']} rows, "
        f"removed {cleaned['summary'].get('ghost_pruned_count', 0)} ghosts)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
