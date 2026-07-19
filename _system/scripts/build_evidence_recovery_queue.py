#!/usr/bin/env python3
"""Compile valuation blockers into executable, persistent evidence tasks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from portfolio_registry import ROOT, load_registry

OUT = ROOT / "_system" / "data" / "evidence_recovery_queue.json"


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def collector_for(text: str) -> str:
    value = text.lower()
    if any(word in value for word in ("filing", "contract", "maturity", "debt", "shares", "tax", "legal")):
        return "sec_primary_documents"
    if any(word in value for word in ("price", "market", "capacity", "utilization", "margin")):
        return "market_and_filing_facts"
    return "primary_documents_then_model"


def build() -> dict:
    registry = load_registry()
    rows = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for ticker, holding in sorted((registry.get("holdings") or {}).items()):
        sleeve = holding.get("investment_sleeve") or (holding.get("classification") or {}).get("investment_sleeve")
        if sleeve != "ls_algo_underlying":
            continue
        research = ROOT / ticker / "research"
        wb = read(research / "valuation_workbench.json")
        gaps = ((wb.get("evidence") or {}).get("gaps") or [])
        if not gaps and not (research / "valuation.json").exists():
            gaps = [{
                "id": "complete_component_model_required", "priority": "critical",
                "question": "Build a complete primary-sourced component valuation.",
                "evidence_required": "; ".join(((wb.get("method_fit") or {}).get("required_evidence") or [])),
                "acceptance_test": "Every material economic claim is valued exactly once using primary evidence.",
                "status": "open",
            }]
        if str(holding.get("market") or "US") == "US" and not ((holding.get("download") or {}).get("cik")):
            gaps = [
                {
                    "id": "sec_identity_required", "priority": "critical",
                    "question": "Resolve the issuer SEC CIK before primary filing collection.",
                    "evidence_required": "Committed SEC ticker/CIK mapping or verified SEC submissions identity.",
                    "acceptance_test": "Registry download.cik is a ten-digit verified CIK.",
                    "status": "open",
                },
                *gaps,
            ]
        prior = read(research / "evidence_task_queue.json")
        prior_by_id = {row.get("id"): row for row in prior.get("tasks") or []}
        tasks = []
        for gap in gaps:
            if str(gap.get("status") or "open").lower() in {"closed", "complete", "resolved"}:
                continue
            task_id = str(gap.get("id") or f"gap_{len(tasks)+1}")
            text = " ".join(str(gap.get(key) or "") for key in ("question", "evidence_required", "acceptance_test"))
            previous = prior_by_id.get(task_id) or {}
            tasks.append({
                "id": task_id,
                "priority": gap.get("priority") or "critical",
                "question": gap.get("question"),
                "evidence_required": gap.get("evidence_required"),
                "acceptance_test": gap.get("acceptance_test"),
                "collector": collector_for(text),
                "status": previous.get("status") or "pending_collection",
                "attempts": int(previous.get("attempts") or 0),
                "last_attempt_at": previous.get("last_attempt_at"),
                "evidence_refs": previous.get("evidence_refs") or [],
            })
        if not tasks:
            continue
        trigger = read(research / "committee_trigger.json")
        packet = {"schema_version": "1.0", "ticker": ticker, "updated_at": now, "tasks": tasks}
        (research / "evidence_task_queue.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        rows.append({
            "ticker": ticker,
            "triggered": str(trigger.get("status") or "").lower() == "open",
            "critical_count": sum(task["priority"] == "critical" for task in tasks),
            "ready_count": sum(task["status"] == "evidence_ready" for task in tasks),
            "task_ref": f"{ticker}/research/evidence_task_queue.json",
        })
    rows.sort(key=lambda row: (not row["triggered"], -row["critical_count"], row["ticker"]))
    payload = {"schema_version": "1.0", "generated_at": now, "ticker_count": len(rows), "items": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"evidence recovery queue: {len(rows)} tickers")
    return payload


if __name__ == "__main__":
    build()
