#!/usr/bin/env python3
"""Audit activist firm registry vs index hits — weekly maintenance report."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "frameworks" / "activist_firm_registry.json"


def portfolio_tickers() -> list[str]:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    data = json.loads(reg.read_text(encoding="utf-8"))
    return sorted((data.get("holdings") or {}).keys())


def load_registry_ids() -> set[str]:
    doc = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    firms = doc.get("firms") or []
    return {f.get("id") for f in firms if f.get("id")}


def scan_indexes() -> tuple[dict[str, int], list[dict]]:
    unknown_counts: dict[str, int] = {}
    samples: list[dict] = []
    for ticker in portfolio_tickers():
        path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
        if not path.exists():
            continue
        reports = json.loads(path.read_text(encoding="utf-8")).get("reports") or []
        for report in reports:
            firm_id = report.get("firm_id") or ""
            if not firm_id or firm_id.startswith("sec_filer:") or firm_id == "unresolved":
                key = firm_id or "missing"
                unknown_counts[key] = unknown_counts.get(key, 0) + 1
                if len(samples) < 40:
                    samples.append(
                        {
                            "ticker": ticker,
                            "firm_id": firm_id,
                            "firm_name": report.get("firm_name"),
                            "source": report.get("source"),
                            "report_date": report.get("report_date"),
                        }
                    )
    return unknown_counts, samples


def inactive_with_hits(registry_ids: set[str], stale_days: int = 180) -> list[str]:
    doc = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=stale_days)
    stale: list[str] = []
    for firm in doc.get("firms") or []:
        fid = firm.get("id")
        if not fid or firm.get("active", True):
            continue
        # flag inactive firms still present in any index
        for ticker in portfolio_tickers():
            path = ROOT / ticker / "third-party-analyses" / "activist_reports_index.json"
            if not path.exists():
                continue
            reports = json.loads(path.read_text(encoding="utf-8")).get("reports") or []
            if any(r.get("firm_id") == fid for r in reports):
                stale.append(fid)
                break
    return sorted(set(stale))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    registry_ids = load_registry_ids()
    unknown_counts, samples = scan_indexes()
    inactive_hits = inactive_with_hits(registry_ids)
    out = ROOT / "_system" / "research" / f"activist_registry_candidates_{args.date}.md"
    lines = [
        "# Activist registry candidates",
        "",
        f"**Date:** {args.date}",
        f"**Registry path:** `_system/frameworks/activist_firm_registry.json`",
        "",
        "## Unknown / SEC filer IDs (top counts)",
        "",
        "| Firm ID | Hits |",
        "|---------|------|",
    ]
    for firm_id, count in sorted(unknown_counts.items(), key=lambda x: -x[1])[:30]:
        lines.append(f"| `{firm_id}` | {count} |")
    lines.extend(["", "## Sample unresolved rows", ""])
    for row in samples[:20]:
        lines.append(
            f"- **{row['ticker']}** `{row['firm_id']}` ({row.get('source')}) {row.get('report_date') or '—'}"
        )
    if inactive_hits:
        lines.extend(["", "## Inactive registry firms still indexed", ""])
        for fid in inactive_hits:
            lines.append(f"- `{fid}` — review or remove from indexes")
    lines.extend(
        [
            "",
            "## Suggested JSON stub (human applies)",
            "",
            "```json",
            '{ "id": "new_firm_id", "name": "Publisher Name", "side": "short", "active": true, "ingest_method": "site_index" }',
            "```",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(unknown_counts)} unknown IDs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
