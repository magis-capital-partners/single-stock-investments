#!/usr/bin/env python3
"""Onboard a bounded, deterministic batch from the LS-algo gap queue."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import ROOT, load_registry, save_registry

QUEUE = ROOT / "_system" / "data" / "ls_algo_underlying_gap.json"
EVIDENCE_QUEUE = ROOT / "_system" / "data" / "evidence_recovery_queue.json"
SLEEVE = "ls_algo_underlying"


def tag_sleeve(ticker: str) -> None:
    registry = load_registry()
    holding = (registry.get("holdings") or {}).get(ticker)
    if holding is None:
        return
    classification = holding.setdefault("classification", {})
    classification["investment_sleeve"] = SLEEVE
    holding["investment_sleeve"] = SLEEVE
    save_registry(registry)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-evidence-backlog", type=int, default=24)
    args = parser.parse_args()
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    candidates = queue.get("candidates") or []
    registry = load_registry()
    known = set((registry.get("holdings") or {})) | set((registry.get("watchlist") or {}))
    for row in candidates:
        if row["ticker"] in known:
            tag_sleeve(row["ticker"])
    pending = [row for row in candidates if row["ticker"] not in known and row.get("status") == "pending_onboard"]
    try:
        backlog = int(json.loads(EVIDENCE_QUEUE.read_text(encoding="utf-8")).get("ticker_count") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        backlog = 0
    capacity = max(args.max_evidence_backlog - backlog, 0)
    batch = pending[: min(max(args.batch_size, 0), capacity)]
    for row in batch:
        command = [
            sys.executable, "_system/scripts/onboard_ticker.py", "--ticker", row["ticker"],
            "--company", row.get("company") or row["ticker"], "--market", "US",
            "--skip-download", "--skip-indexes", "--skip-dashboard", "--no-deep-dive",
        ]
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode == 0:
            tag_sleeve(row["ticker"])
    print(f"ls-algo onboarding: tagged {len(candidates) - len(pending)} registered; evidence backlog={backlog}; attempted {len(batch)} new names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
