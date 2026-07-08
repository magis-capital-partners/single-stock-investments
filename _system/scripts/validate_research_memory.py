#!/usr/bin/env python3
"""Validate research memory artifacts and freshness vs insights."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEMORY_PATH = ROOT / "dashboard" / "data" / "research_memory.json"
EVIDENCE_PATH = ROOT / "dashboard" / "data" / "research_memory_evidence.json"
INSIGHTS_PATH = ROOT / "dashboard" / "data" / "insights.json"
FUNDS_PATH = ROOT / "_system" / "reference" / "market-data" / "ownership" / "biotech_specialist_funds.json"
CIK_PATH = ROOT / "_system" / "reference" / "market-data" / "ownership" / "fund_cik_registry.json"
WARN_MB = 40
HARD_MB = 95


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not MEMORY_PATH.exists():
        errors.append("missing dashboard/data/research_memory.json")
    if not FUNDS_PATH.exists():
        errors.append("missing biotech_specialist_funds.json")
    if not CIK_PATH.exists():
        warnings.append("missing fund_cik_registry.json")

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    size_mb = MEMORY_PATH.stat().st_size / (1024 * 1024)
    if size_mb > HARD_MB:
        errors.append(f"research_memory.json is {size_mb:.1f}MB (hard limit {HARD_MB}MB)")
    elif size_mb > WARN_MB:
        warnings.append(f"research_memory.json is {size_mb:.1f}MB (recommend < {WARN_MB}MB)")

    summary = memory.get("summary") or {}
    for key in ("claim_count", "ticker_count", "review_queue_count"):
        if key not in summary:
            errors.append(f"summary missing {key}")

    if memory.get("schema_version", 1) < 2:
        warnings.append("research_memory schema_version < 2")

    if INSIGHTS_PATH.exists() and MEMORY_PATH.exists():
        insights_mtime = INSIGHTS_PATH.stat().st_mtime
        memory_mtime = MEMORY_PATH.stat().st_mtime
        if insights_mtime > memory_mtime + 60:
            warnings.append("research_memory older than insights.json; run make research-memory")

    funds = json.loads(FUNDS_PATH.read_text(encoding="utf-8")).get("funds") or []
    if len(funds) < 20:
        warnings.append(f"biotech fund registry only has {len(funds)} funds")

    cik_doc = json.loads(CIK_PATH.read_text(encoding="utf-8")) if CIK_PATH.exists() else {"funds": {}}
    cik_count = len(cik_doc.get("funds") or {})
    specialist = [f for f in funds if f.get("signal_role") == "specialist_13f"]
    if cik_count < len(specialist) // 2:
        warnings.append(f"only {cik_count}/{len(specialist)} specialist funds have CIKs")

    if not EVIDENCE_PATH.exists():
        warnings.append("missing research_memory_evidence.json")

    for msg in warnings:
        print(f"WARN: {msg}", file=sys.stderr)
    for msg in errors:
        print(f"ERROR: {msg}", file=sys.stderr)
    if errors:
        return 1
    print(
        f"OK: research memory ({summary.get('claim_count', 0)} claims, "
        f"{summary.get('ownership_record_count', 0)} 13F records)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
