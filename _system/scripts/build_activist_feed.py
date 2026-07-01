#!/usr/bin/env python3
"""Build dashboard/data/activist_feed.json from per-ticker activist indexes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from activist_common import (
    firm_name,
    load_global_scan,
    load_ticker_index,
    portfolio_tickers,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "activist_feed.json"
GITHUB_REPO = "GoldmanDrew/single-stock-investments"


def github_blob(path: str | None) -> str | None:
    if not path:
        return None
    return f"https://github.com/{GITHUB_REPO}/blob/main/{path.replace(chr(92), '/')}"


def feed_eligible(report: dict) -> bool:
    if report.get("include_in_feed") is False:
        return False
    if report.get("filing_class") == "passive_13g":
        return False
    return True


def build_feed() -> dict:
    tickers = portfolio_tickers()
    feed_rows: list[dict] = []
    summary = {
        "portfolio_hits": 0,
        "long_count": 0,
        "short_count": 0,
        "tickers_with_hits": 0,
        "unreconciled_count": 0,
        "passive_excluded_count": 0,
    }
    per_ticker: dict[str, dict] = {}

    for ticker in tickers:
        index = load_ticker_index(ticker)
        reports = list(index.get("reports") or [])
        sr_dir = ROOT / ticker / "third-party-analyses" / "short_reports"
        if sr_dir.is_dir():
            for md in sorted(sr_dir.glob("*.md")):
                firm_id = md.stem.split("_")[0] if "_" in md.stem else md.stem
                reports.append(
                    {
                        "firm_id": firm_id,
                        "firm_name": firm_name(firm_id),
                        "side": "short",
                        "report_date": md.stem.split("_")[-1] if "_" in md.stem else "",
                        "title": md.stem.replace("_", " "),
                        "source": "short_reports_md",
                        "local_file": str(md.relative_to(ROOT)).replace("\\", "/"),
                        "status": "cached",
                        "tier": "context",
                        "include_in_feed": True,
                        "filing_class": "short_markdown",
                    }
                )
        visible = [r for r in reports if feed_eligible(r)]
        summary["passive_excluded_count"] += sum(
            1 for r in reports if r.get("filing_class") == "passive_13g" or r.get("include_in_feed") is False
        )
        if not visible:
            per_ticker[ticker] = {
                "long_count": 0,
                "short_count": 0,
                "latest": None,
                "has_unreconciled": False,
            }
            continue
        long_count = sum(1 for r in visible if r.get("side") == "long")
        short_count = sum(1 for r in visible if r.get("side") == "short")
        unreconciled = any(r.get("status") in ("new", "cached") for r in visible)
        latest = max(visible, key=lambda r: r.get("report_date") or "")
        per_ticker[ticker] = {
            "long_count": long_count,
            "short_count": short_count,
            "latest": {
                "firm_id": latest.get("firm_id"),
                "firm_name": latest.get("firm_name") or firm_name(latest.get("firm_id") or ""),
                "date": latest.get("report_date"),
                "side": latest.get("side"),
                "title": latest.get("title"),
            },
            "has_unreconciled": unreconciled,
        }
        summary["portfolio_hits"] += len(visible)
        summary["long_count"] += long_count
        summary["short_count"] += short_count
        summary["tickers_with_hits"] += 1
        if unreconciled:
            summary["unreconciled_count"] += 1
        for report in visible:
            local = report.get("local_pdf") or report.get("local_file")
            feed_rows.append(
                {
                    "ticker": ticker,
                    "firm_id": report.get("firm_id"),
                    "firm_name": report.get("firm_name") or firm_name(report.get("firm_id") or ""),
                    "side": report.get("side"),
                    "report_date": report.get("report_date"),
                    "title": report.get("title"),
                    "source": report.get("source"),
                    "source_url": report.get("source_url"),
                    "local_pdf": local,
                    "github_url": github_blob(local),
                    "status": report.get("status"),
                    "tier": report.get("tier", "context"),
                    "confidence": report.get("confidence"),
                    "form": report.get("form"),
                    "filing_class": report.get("filing_class"),
                    "milly_verdict": report.get("milly_verdict"),
                }
            )

    feed_rows.sort(key=lambda r: (r.get("report_date") or "", r.get("ticker") or ""), reverse=True)
    global_scan = load_global_scan()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_scan": global_scan.get("generated_at"),
        "summary": summary,
        "by_ticker": per_ticker,
        "feed": feed_rows,
        "firms_active": len({r.get("firm_id") for r in feed_rows if r.get("firm_id")}),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = build_feed()
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} "
        f"({payload['summary']['portfolio_hits']} feed reports, "
        f"{payload['summary']['tickers_with_hits']} tickers, "
        f"{payload['summary']['passive_excluded_count']} passive excluded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
