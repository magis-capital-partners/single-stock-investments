#!/usr/bin/env python3
"""Audit letter_index / vault letters for date-quarter consistency."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from vault_paths import letters_root  # noqa: E402

INSIGHTS_PATH = ROOT / "dashboard" / "data" / "insights.json"
DEFAULT_REPORT = ROOT / "dashboard" / "data" / "letter_date_audit.json"


def audit_rows(rows: list[dict], *, max_year: int) -> dict:
    issues = {
        "year_at_or_beyond_max": [],
        "quarter_year_delta_ge_2": [],
        "date_source_mtime": [],
        "low_confidence": [],
    }
    for r in rows:
        q = r.get("quarter") or ""
        d = r.get("letter_date") or ""
        fund = r.get("fund") or r.get("fund_id") or ""
        if len(d) >= 4 and d[:4].isdigit() and int(d[:4]) >= max_year:
            issues["year_at_or_beyond_max"].append({"fund": fund, "quarter": q, "letter_date": d})
        if len(q) >= 4 and len(d) >= 4 and q[:4].isdigit() and d[:4].isdigit():
            if abs(int(d[:4]) - int(q[:4])) >= 2:
                issues["quarter_year_delta_ge_2"].append({"fund": fund, "quarter": q, "letter_date": d})
        if r.get("date_source") == "mtime":
            issues["date_source_mtime"].append({"fund": fund, "quarter": q, "letter_date": d})
        conf = r.get("date_confidence")
        if conf is not None and int(conf) < 50:
            issues["low_confidence"].append({"fund": fund, "quarter": q, "letter_date": d, "confidence": conf})

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "row_count": len(rows),
        "issue_counts": {k: len(v) for k, v in issues.items()},
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--insights", type=Path, default=INSIGHTS_PATH)
    args = parser.parse_args()

    max_year = datetime.now(timezone.utc).year + 1
    rows: list[dict] = []
    if args.insights.exists():
        doc = json.loads(args.insights.read_text(encoding="utf-8"))
        rows = doc.get("letter_index") or []

    report = audit_rows(rows, max_year=max_year)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["issue_counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
