#!/usr/bin/env python3
"""Measure where GitHub Actions time actually goes: queue lag vs execution.

Scheduled jobs here start late and sleeping runners burn minutes, but those
are different problems with different fixes. This splits them per workflow:

  queue lag   = started_at - created_at   (GitHub's scheduler, not our code)
  execution   = updated_at - started_at   (a runner was allocated and burning)

Input is `gh run list --json` output, either from a file or fetched live:

  gh run list --limit 1000 --json databaseId,workflowName,conclusion,status,createdAt,startedAt,updatedAt > runs.json
  python _system/scripts/measure_workflow_load.py --input runs.json
  python _system/scripts/measure_workflow_load.py --repo owner/name --days 5
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TERMINAL = {"completed"}


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def run_timing(run: dict[str, Any]) -> dict[str, float | None]:
    created = _parse(run.get("createdAt") or run.get("created_at"))
    started = _parse(run.get("startedAt") or run.get("started_at")) or created
    updated = _parse(run.get("updatedAt") or run.get("updated_at"))
    queue = (started - created).total_seconds() if created and started else None
    execution = (updated - started).total_seconds() if started and updated else None
    return {"queue_seconds": queue, "execution_seconds": execution}


def summarise(runs: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_workflow[str(run.get("workflowName") or run.get("workflow_name") or "?")].append(run)

    out: dict[str, dict[str, Any]] = {}
    for name, items in sorted(by_workflow.items()):
        queues = [t["queue_seconds"] for t in (run_timing(r) for r in items) if t["queue_seconds"] is not None]
        timings = [run_timing(r) for r in items]
        execs = [t["execution_seconds"] for t in timings if t["execution_seconds"] is not None]
        conclusions = Counter(str(r.get("conclusion") or "pending") for r in items)
        cancelled = conclusions.get("cancelled", 0)
        out[name] = {
            "runs": len(items),
            "conclusions": dict(conclusions),
            "cancelled_share": round(cancelled / len(items), 3) if items else 0.0,
            "queue_median_seconds": round(statistics.median(queues), 1) if queues else None,
            "queue_max_seconds": round(max(queues), 1) if queues else None,
            "execution_median_seconds": round(statistics.median(execs), 1) if execs else None,
            "execution_total_minutes": round(sum(execs) / 60, 1) if execs else 0.0,
        }
    return out


def fetch_runs(repo: str, days: int, limit: int = 1000) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc).timestamp() - days * 86400
    proc = subprocess.run(
        ["gh", "run", "list", "--repo", repo, "--limit", str(limit),
         "--json", "databaseId,workflowName,conclusion,status,createdAt,startedAt,updatedAt"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "gh run list failed")
    runs = json.loads(proc.stdout or "[]")
    return [r for r in runs if (_parse(r.get("createdAt")) or datetime.fromtimestamp(since, timezone.utc)).timestamp() >= since]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, help="JSON file from `gh run list --json ...`")
    parser.add_argument("--repo", help="owner/name; fetch runs live with gh")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)

    if args.input:
        runs = json.loads(args.input.read_text(encoding="utf-8"))
    elif args.repo:
        runs = fetch_runs(args.repo, args.days)
    else:
        parser.error("give --input or --repo")

    summary = summarise(runs)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    total_minutes = sum(w["execution_total_minutes"] for w in summary.values())
    print(f"{'workflow':45} {'runs':>5} {'cancel%':>8} {'queue med':>10} {'queue max':>10} {'exec med':>9} {'exec min':>9}")
    for name, w in summary.items():
        print(f"{name:45} {w['runs']:>5} {w['cancelled_share'] * 100:>7.0f}% "
              f"{(w['queue_median_seconds'] or 0) / 60:>9.1f}m {(w['queue_max_seconds'] or 0) / 60:>9.1f}m "
              f"{(w['execution_median_seconds'] or 0) / 60:>8.1f}m {w['execution_total_minutes']:>9.1f}")
    print(f"total execution: {total_minutes:.1f} runner-minutes across {sum(w['runs'] for w in summary.values())} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
