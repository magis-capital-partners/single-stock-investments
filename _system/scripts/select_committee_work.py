#!/usr/bin/env python3
"""Select one pending committee and deterministically advance its state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from committee_task_queue import next_tasks, read_json, ROOT


def select() -> dict:
    manifests = sorted(ROOT.glob("*/research/committee_work/*/manifest.json"))
    for manifest_path in manifests:
        manifest = read_json(manifest_path)
        stage = str(manifest.get("stage") or "")
        if stage in {"assembled", "complete", "superseded"}:
            continue
        ticker = manifest_path.parts[-5].upper()
        committee_date = manifest_path.parent.name
        assembled = ROOT / ticker / "research" / f"committee_{committee_date}.json"
        if assembled.exists():
            continue
        tasks = next_tasks(ticker, committee_date)
        current = read_json(manifest_path)
        if tasks:
            return {
                "ticker": ticker,
                "committee_date": committee_date,
                "action": "advance",
                "tasks": tasks,
            }
        if current.get("stage") == "ready_to_assemble":
            return {
                "ticker": ticker,
                "committee_date": committee_date,
                "action": "assemble",
                "tasks": [],
            }
    return {"ticker": "", "committee_date": "", "action": "none", "tasks": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    result = select()
    print(json.dumps(result, separators=(",", ":")))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            for key in ("ticker", "committee_date", "action"):
                handle.write(f"{key}={result[key]}\n")
            handle.write("tasks=" + json.dumps(result["tasks"], separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
