#!/usr/bin/env python3
"""Write human review queue for filing metrics the parser cannot auto-resolve."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PENDING = ROOT / "_system" / "reviews" / "pending"
sys_path = ROOT / "_system" / "scripts"
import sys

sys.path.insert(0, str(sys_path))
from filing_review import auto_resolve_verdict, pct_change  # noqa: E402

METRIC_LABELS = {
    "revenues": "Revenue",
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "eps_basic": "EPS (basic)",
    "eps_diluted": "EPS (diluted)",
    "long_term_debt": "Long-term debt",
}


def portfolio_tickers() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if not reg.exists():
        return []
    data = json.loads(reg.read_text(encoding="utf-8"))
    holdings = data.get("holdings") or {}
    watch = data.get("watchlist") or {}
    return sorted(set(holdings.keys()) | set(watch.keys()))


def scan_ticker(ticker: str) -> list[dict]:
    evidence = ROOT / ticker / "research" / "evidence"
    if not evidence.is_dir():
        return []
    files = sorted(evidence.glob("filing_facts_*.json"), reverse=True)
    if not files:
        return []
    try:
        doc = json.loads(files[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows: list[dict] = []
    for name, metric in (doc.get("metrics") or {}).items():
        if not isinstance(metric, dict):
            continue
        change = pct_change(metric.get("prior"), metric.get("current"))
        verdict, reason = auto_resolve_verdict(name, metric, change)
        if verdict == "needs_human":
            rows.append(
                {
                    "ticker": ticker,
                    "metric": name,
                    "label": METRIC_LABELS.get(name, name),
                    "change": change,
                    "parser_confidence": metric.get("parser_confidence"),
                    "parser_flags": metric.get("parser_flags") or [],
                    "reason": reason,
                    "filing": files[0].name,
                }
            )
    return rows


def write_queue(rows: list[dict], scan_date: str) -> Path | None:
    if not rows:
        return None
    PENDING.mkdir(parents=True, exist_ok=True)
    out = PENDING / f"filing_insights_{scan_date}.md"
    lines = [
        "# Filing insights — human review queue",
        "",
        f"**Date:** {scan_date}",
        f"**Rows:** {len(rows)}",
        "",
        "| Ticker | Metric | Change | Confidence | Flags | Reason |",
        "|--------|--------|--------|------------|-------|--------|",
    ]
    for row in rows[:200]:
        flags = ", ".join(row.get("parser_flags") or [])[:60]
        ch = row.get("change")
        ch_text = f"{ch:+.1f}%" if ch is not None else "—"
        lines.append(
            f"| {row['ticker']} | {row['label']} | {ch_text} | "
            f"{row.get('parser_confidence') or '—'} | {flags or '—'} | {row.get('reason')} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    all_rows: list[dict] = []
    for ticker in portfolio_tickers():
        all_rows.extend(scan_ticker(ticker))
    path = write_queue(all_rows, args.date)
    print(f"Filing auto-resolve: {len(all_rows)} need human review -> {path or '(none)'}")
    summary = ROOT / "_system" / "research" / f"filing_insights_summary_{args.date}.json"
    summary.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "human_count": len(all_rows),
                "queue_path": str(path.relative_to(ROOT)) if path else None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
