#!/usr/bin/env python3
"""Refresh the local TerminalValue.io data-source candidate registry."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "_system" / "reference" / "data-sources" / "terminalvalue_candidates.json"
API_URL = "https://terminalvalue.io/api/tools"

SELECTED_TOOL_DEFAULTS = {
    "Financial Datasets": {
        "dashboard_role": "fundamentals, prices, financial statements",
        "priority": "high",
        "credential_required": True,
        "target_pipeline": "_system/reference/market-data/fundamentals/",
    },
    "Daloopa": {
        "dashboard_role": "normalized KPIs and model-ready company data",
        "priority": "high",
        "credential_required": True,
        "target_pipeline": "_system/reference/market-data/fundamentals/",
    },
    "Earnings API": {
        "dashboard_role": "earnings calendar and reported earnings coverage",
        "priority": "high",
        "credential_required": True,
        "target_pipeline": "_system/data/earnings_calendar.json",
    },
    "FRED MCP": {
        "dashboard_role": "macro series for rates, spreads, inflation, liquidity and commodities",
        "priority": "high",
        "credential_required": False,
        "target_pipeline": "_system/reference/market-data/themes/",
    },
    "Quartr": {
        "dashboard_role": "earnings call transcripts, investor events and presentation coverage",
        "priority": "high",
        "credential_required": True,
        "target_pipeline": "*/research/evidence/transcripts/",
    },
    "Better EDGAR": {
        "dashboard_role": "SEC filing retrieval and cleaner document discovery",
        "priority": "high",
        "credential_required": False,
        "target_pipeline": "*/investor-documents/sec-edgar/",
    },
    "EDGAR Analyst": {
        "dashboard_role": "filing analysis and metric extraction",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "*/research/evidence/filing_facts_*.json",
    },
    "WhaleWisdom": {
        "dashboard_role": "13F ownership and superinvestor overlap",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "_system/reference/market-data/ownership/",
    },
    "Unusual Whales": {
        "dashboard_role": "options flow, unusual volume and insider/trading context",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "_system/reference/market-data/flow/",
    },
    "Stock Titan": {
        "dashboard_role": "company news and press release monitoring",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "dashboard/data/portfolio_news.json",
    },
    "Fiscal AI": {
        "dashboard_role": "fundamental research and company model enrichment",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "*/third-party-analyses/source_inventory_*.json",
    },
    "ROIC AI": {
        "dashboard_role": "quality, returns on capital and valuation context",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "*/research/valuation.json",
    },
    "ValueInvesting.io": {
        "dashboard_role": "DCF and valuation cross-checks",
        "priority": "medium",
        "credential_required": True,
        "target_pipeline": "*/research/valuation.json",
    },
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {"selected_tools": []}
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_tools(url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "single-stock-investments/terminalvalue-refresh"})
    with urlopen(req, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tools", "data", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("TerminalValue response did not contain a tools list.")


def tool_name(tool: dict) -> str:
    return str(tool.get("name") or tool.get("title") or "").strip()


def merge_selected(existing: dict, fetched: list[dict]) -> dict:
    existing_by_name = {tool.get("name"): tool for tool in existing.get("selected_tools") or []}
    fetched_by_name = {tool_name(tool): tool for tool in fetched if tool_name(tool)}
    selected = []
    for name in sorted(SELECTED_TOOL_DEFAULTS):
        base = {
            "name": name,
            "integration_status": "candidate",
            **SELECTED_TOOL_DEFAULTS[name],
            **dict(existing_by_name.get(name) or {}),
        }
        fetched_tool = fetched_by_name.get(name)
        if fetched_tool:
            base["terminalvalue"] = fetched_tool
            base["category"] = fetched_tool.get("category") or fetched_tool.get("group") or base.get("category")
        selected.append(base)
    return {
        "source": API_URL,
        "source_label": "TerminalValue.io tools index",
        "reviewed_at": datetime.now(timezone.utc).date().isoformat(),
        "total_tools_reported": len(fetched),
        "data_api_tools_reported": sum(
            1
            for tool in fetched
            if "data" in str(tool.get("category") or tool.get("group") or "").lower()
            and "api" in str(tool.get("category") or tool.get("group") or "").lower()
        ),
        "selected_tools": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--api-url", default=API_URL)
    args = parser.parse_args()

    existing = load_json(args.output)
    fetched = fetch_tools(args.api_url)
    doc = merge_selected(existing, fetched)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({doc['total_tools_reported']} tools, {len(doc['selected_tools'])} selected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
