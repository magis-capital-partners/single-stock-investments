#!/usr/bin/env python3
"""Run bounded deterministic collection for the evidence recovery queue."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from onboard_ticker import lookup_cik
from portfolio_registry import ROOT, load_registry, save_registry

QUEUE = ROOT / "_system" / "data" / "evidence_recovery_queue.json"


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evidence_refs(ticker: str) -> list[str]:
    base = ROOT / ticker
    refs = []
    for pattern in ("investor-documents/DOWNLOAD_MANIFEST.json", "investor-documents/sec-edgar/*", "research/evidence/*.json"):
        refs.extend(path.relative_to(ROOT).as_posix() for path in base.glob(pattern) if path.is_file())
    return sorted(set(refs))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    aggregate = read(QUEUE)
    selected = [
        row for row in (aggregate.get("items") or [])
        if int(row.get("ready_count") or 0) < int(row.get("task_count") or row.get("critical_count") or 1)
    ][: max(args.limit, 0)]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for item in selected:
        ticker = item["ticker"]
        path = ROOT / item["task_ref"]
        packet = read(path)
        before = evidence_refs(ticker)
        registry = load_registry()
        holding = (registry.get("holdings") or {}).get(ticker) or {}
        if str(holding.get("market") or "US") == "US" and not ((holding.get("download") or {}).get("cik")):
            cik = lookup_cik(ticker)
            if cik:
                holding.setdefault("download", {})["cik"] = cik
                save_registry(registry)
                subprocess.run([sys.executable, "_system/scripts/sync_portfolio_from_registry.py"], cwd=ROOT, check=False, timeout=120)
        try:
            subprocess.run(
                [sys.executable, "_system/scripts/automate_valuation_readiness.py", "--tickers", ticker,
                 "--date", now[:10], "--collect", "--full-rerun"],
                cwd=ROOT, check=False, timeout=900,
            )
        except subprocess.TimeoutExpired:
            pass
        after = evidence_refs(ticker)
        packet = read(path)
        for task in packet.get("tasks") or []:
            task["attempts"] = int(task.get("attempts") or 0) + 1
            task["last_attempt_at"] = now
        path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        refresh = {
            "schema_version": "1.0", "ticker": ticker, "updated_at": now,
            "status": "evidence_ready" if packet.get("ready_count") == packet.get("task_count") else "retry_pending",
            "new_artifact_count": len(set(after) - set(before)), "evidence_refs": after,
        }
        refresh_path = ROOT / ticker / "research" / "evidence_refresh.json"
        refresh_path.write_text(json.dumps(refresh, indent=2) + "\n", encoding="utf-8")
        item["ready_count"] = sum(task.get("status") == "evidence_ready" for task in packet.get("tasks") or [])
    aggregate["generated_at"] = now
    QUEUE.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    print(f"evidence collection attempted for {len(selected)} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
