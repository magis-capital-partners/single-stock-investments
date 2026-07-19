#!/usr/bin/env python3
"""Fail only when an evidence blocker has no autonomous recovery task."""
from __future__ import annotations

import json
from pathlib import Path

from portfolio_registry import ROOT, load_registry


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    errors = []
    registry = load_registry()
    for ticker, holding in sorted((registry.get("holdings") or {}).items()):
        sleeve = holding.get("investment_sleeve") or (holding.get("classification") or {}).get("investment_sleeve")
        if sleeve != "ls_algo_underlying":
            continue
        research = ROOT / ticker / "research"
        workbench = read(research / "valuation_workbench.json")
        task_doc = read(research / "evidence_task_queue.json")
        identity = read(research / "security_identity.json")
        task_ids = {str(row.get("id")) for row in task_doc.get("tasks") or []}
        for gap in ((workbench.get("evidence") or {}).get("gaps") or []):
            if str(gap.get("status") or "open").lower() not in {"closed", "complete", "resolved"}:
                gap_id = str(gap.get("id") or "")
                if gap_id and gap_id not in task_ids:
                    errors.append(f"{ticker}: blocker {gap_id} has no recovery task")
        if (str(holding.get("market") or "US") == "US"
                and identity.get("security_type") != "exchange_traded_fund"
                and not ((holding.get("download") or {}).get("cik"))
                and "sec_identity_required" not in task_ids):
            errors.append(f"{ticker}: missing CIK has no identity recovery task")
    if errors:
        for error in errors[:50]:
            print(f"ERROR: {error}")
        return 1
    print("OK: every LS-algo blocker has an autonomous recovery task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
