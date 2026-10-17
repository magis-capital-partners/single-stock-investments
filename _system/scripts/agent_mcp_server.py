#!/usr/bin/env python3
"""Minimal stdio MCP server exposing the agent data layer as typed tools.

Read-only by construction: there is no tool that writes research, memory, or
valuation files, and no tool that touches any broker gateway. Agents with
filesystem access may use the files directly; Grok Bot, Muse, and other
external agents use these six tools instead.

Tools:
  get_portfolio_summary()                  L0 active-book rows
  get_ticker(ticker, level=shard|pack)     L1 shard or context pack manifest
  get_valuation(ticker)                    canonical returns + stance proposal
  get_claims(ticker, status?)              unified claim rows for a ticker
  search(query, ticker?, kind?, limit?)    hybrid cited chunks
  get_context_pack(ticker, task?)          token-budgeted pack (builds on demand)

Run:  python _system/scripts/agent_mcp_server.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SERVER_INFO = {"name": "magis-agent-data", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS: list[dict[str, Any]] = [
    {"name": "get_portfolio_summary", "description": "L0 active-book portfolio rows (ticker, stance, archetype, base IRR in percent per year).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_ticker", "description": "L1 agent shard for a ticker, or its context pack manifest when level=pack.", "inputSchema": {"type": "object", "required": ["ticker"], "properties": {"ticker": {"type": "string"}, "level": {"type": "string", "enum": ["shard", "pack"], "default": "shard"}}}},
    {"name": "get_valuation", "description": "Canonical returns block (percent per year), stance proposal, and classification inputs from valuation.json.", "inputSchema": {"type": "object", "required": ["ticker"], "properties": {"ticker": {"type": "string"}}}},
    {"name": "get_claims", "description": "Unified claim rows for a ticker from _system/data/claims.jsonl, optionally filtered by status.", "inputSchema": {"type": "object", "required": ["ticker"], "properties": {"ticker": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer", "default": 25}}}},
    {"name": "search", "description": "Hybrid BM25 + vector search returning cited chunks with source paths.", "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "ticker": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer", "default": 10}}}},
    {"name": "get_context_pack", "description": "Token-budgeted context pack markdown for a ticker and task (built on demand).", "inputSchema": {"type": "object", "required": ["ticker"], "properties": {"ticker": {"type": "string"}, "task": {"type": "string", "enum": ["deep-dive", "cross-check", "triage", "general"], "default": "general"}}}},
]


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def call_tool(name: str, arguments: dict[str, Any] | None = None, *, root: Path = ROOT) -> Any:
    args = arguments or {}
    if name == "get_portfolio_summary":
        summary = _load(root / "dashboard" / "data" / "portfolio_summary.json")
        return {"counts": summary.get("counts"), "rows": summary.get("rows") or []}
    if name == "get_ticker":
        ticker = str(args.get("ticker") or "").upper()
        if str(args.get("level") or "shard") == "pack":
            pack = root / "dashboard" / "data" / "context_packs" / f"{ticker}.json"
            if not pack.is_file():
                from build_agent_context import write_pack

                write_pack(ticker, root=root)
            return _load(pack)
        shard = _load(root / "dashboard" / "data" / "agent_shards" / f"{ticker}.json")
        if shard:
            return shard
        latest = _load(root / ticker / "research" / "latest.json")
        return {"ticker": ticker, "shard_status": "not_built", "latest": latest}
    if name == "get_valuation":
        ticker = str(args.get("ticker") or "").upper()
        valuation = _load(root / ticker / "research" / "valuation.json")
        return {
            "ticker": ticker,
            "schema_version": valuation.get("schema_version"),
            "as_of": valuation.get("as_of"),
            "returns": valuation.get("returns"),
            "stance_proposal": valuation.get("stance_proposal"),
            "approved_stance": valuation.get("approved_stance"),
            "classification_inputs": valuation.get("classification_inputs"),
        }
    if name == "get_claims":
        ticker = str(args.get("ticker") or "").upper()
        status = args.get("status")
        limit = int(args.get("limit") or 25)
        claims_path = root / "_system" / "data" / "claims.jsonl"
        out: list[dict[str, Any]] = []
        if claims_path.is_file():
            for line in claims_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if str(row.get("ticker", "")).upper() == ticker and (not status or row.get("status") == status):
                    out.append(row)
                    if len(out) >= limit:
                        break
        return {"ticker": ticker, "count": len(out), "claims": out}
    if name == "search":
        from agent_search import search as hybrid_search

        return hybrid_search(str(args.get("query") or ""), ticker=args.get("ticker"), kind=args.get("kind"), limit=int(args.get("limit") or 10), root=root)
    if name == "get_context_pack":
        ticker = str(args.get("ticker") or "").upper()
        from build_agent_context import write_pack

        manifest = write_pack(ticker, task=str(args.get("task") or "general"), root=root)
        pack_path = root / "dashboard" / "data" / "context_packs" / f"{ticker}.md"
        return {"manifest": manifest, "markdown": pack_path.read_text(encoding="utf-8") if pack_path.is_file() else ""}
    raise ValueError(f"unknown tool: {name}")


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        try:
            result = call_tool(str(params.get("name") or ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}}
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
