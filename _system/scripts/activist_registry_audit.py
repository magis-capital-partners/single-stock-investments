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


def _ingest_methods(firm: dict) -> list[str]:
    methods = firm.get("ingest_methods")
    if isinstance(methods, list) and methods:
        return [str(m) for m in methods]
    legacy = firm.get("ingest_method")
    return [str(legacy)] if legacy else []


def audit_ingest_config(firms: list[dict]) -> list[str]:
    """Return human-readable problems with site_index / press_wire configuration."""
    problems: list[str] = []
    for firm in firms:
        if not firm.get("active", True):
            continue
        fid = firm.get("id") or "?"
        methods = _ingest_methods(firm)
        if "site_index" in methods:
            if not (firm.get("domains") or firm.get("rss_urls")):
                problems.append(f"`{fid}` has site_index but no domains/rss_urls")
        if "press_wire" in methods:
            aliases = firm.get("press_aliases") or firm.get("aliases") or []
            if not aliases and not firm.get("name"):
                problems.append(f"`{fid}` has press_wire but no press_aliases/name")
    return problems


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
    parser.add_argument(
        "--fail-on-ingest",
        action="store_true",
        help="Exit non-zero when site_index/press_wire config is incomplete",
    )
    args = parser.parse_args()
    registry_ids = load_registry_ids()
    unknown_counts, samples = scan_indexes()
    inactive_hits = inactive_with_hits(registry_ids)
    doc = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    ingest_problems = audit_ingest_config(doc.get("firms") or [])
    out = ROOT / "_system" / "research" / f"activist_registry_candidates_{args.date}.md"
    lines = [
        "# Activist registry candidates",
        "",
        f"**Date:** {args.date}",
        f"**Registry path:** `_system/frameworks/activist_firm_registry.json`",
        "",
        "## Ingest config audit",
        "",
    ]
    if ingest_problems:
        for problem in ingest_problems:
            lines.append(f"- {problem}")
    else:
        lines.append("- OK — site_index/press_wire firms have domains or aliases.")
    lines.extend(
        [
            "",
            "## Unknown / SEC filer IDs (top counts)",
            "",
            "| Firm ID | Hits |",
            "|---------|------|",
        ]
    )
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
            '{ "id": "new_firm_id", "name": "Publisher Name", "side": "short", "active": true, "ingest_methods": ["site_index"], "ingest_method": "site_index" }',
            "```",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(unknown_counts)} unknown IDs, {len(ingest_problems)} ingest issues)")
    if args.fail_on_ingest and ingest_problems:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
