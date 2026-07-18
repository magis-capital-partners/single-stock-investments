#!/usr/bin/env python3
"""Run a local Marvin cloud dispatch through the same evidence and budget gate as CI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from build_research_agent_manifest import build_manifest
from llm_call_gate import DEFAULT_POLICY, append_ledger, evaluate, now_utc, read_json, read_ledger

ROOT = Path(__file__).resolve().parents[2]


def ledger_event(ticker: str, manifest: dict, status: str, gate_reason: str | None = None) -> dict:
    value = {
        "timestamp": now_utc().isoformat(),
        "consumer": "marvin_research",
        "subject": ticker,
        "reason": "manual_material_change",
        "evidence_hash": manifest["evidence_hash"],
        "status": status,
        "run_id": "local",
    }
    if gate_reason:
        value["gate_reason"] = gate_reason
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True, type=str.upper)
    parser.add_argument("--force", action="store_true", help="Audited recovery override")
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()

    if not os.environ.get("CURSOR_API_KEY"):
        print("CURSOR_API_KEY not set — deterministic research remains available, cloud dispatch skipped", file=sys.stderr)
        return 1

    manifest = build_manifest(ticker, "manual_material_change")
    if not manifest["ready"]:
        print(f"No research evidence is ready for {ticker}; no Cursor call.")
        return 0

    state_path = ROOT / ticker / "research" / "agent_run_state.json"
    manifest_path = ROOT / ticker / "research" / "research_agent_manifest.json"
    ledger_path = ROOT / ".llm-state" / "marvin_research" / "ledger.jsonl"
    decision = evaluate(
        consumer="marvin_research",
        subject=ticker,
        reason="manual_material_change",
        evidence_hash=manifest["evidence_hash"],
        policy_doc=read_json(DEFAULT_POLICY),
        ledger=read_ledger(ledger_path),
        state=read_json(state_path),
        force=args.force,
    )
    append_ledger(
        ledger_path,
        ledger_event(ticker, manifest, "reserved" if decision["approved"] else "suppressed", decision["gate_reason"]),
    )
    if not decision["approved"]:
        print(f"No Cursor call for {ticker}: {decision['gate_reason']}.")
        return 0

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    repo = os.environ.get("GITHUB_REPOSITORY", "magis-capital-partners/single-stock-investments")
    env = {
        **os.environ,
        "TICKER": ticker,
        "PICK_REASON": "manual_material_change",
        "RESEARCH_EVIDENCE_HASH": manifest["evidence_hash"],
        "RESEARCH_EVIDENCE_MANIFEST": manifest_path.relative_to(ROOT).as_posix(),
        "RESEARCH_EVIDENCE_MANIFEST_JSON": json.dumps(manifest, separators=(",", ":")),
        "GITHUB_REPOSITORY": repo,
    }
    scripts_dir = ROOT / "_system" / "scripts"
    install = subprocess.run(["npm", "ci", "--ignore-scripts"], cwd=scripts_dir, check=False)
    if install.returncode:
        append_ledger(ledger_path, ledger_event(ticker, manifest, "failed"))
        return install.returncode
    result = subprocess.run(["node", str(scripts_dir / "marvin_deep_dive.mjs")], cwd=ROOT, env=env, check=False)
    append_ledger(ledger_path, ledger_event(ticker, manifest, "completed" if result.returncode == 0 else "failed"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
