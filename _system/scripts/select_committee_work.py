#!/usr/bin/env python3
"""Select one pending committee and deterministically advance its state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from committee_task_queue import next_tasks, read_json, ROOT
from investment_committee_pipeline import file_reference, initialize, packet_hash, write_json


def packet_is_current(manifest: dict) -> bool:
    try:
        refs = [file_reference(ROOT / row["path"]) for row in manifest.get("evidence") or []]
    except FileNotFoundError:
        return False
    return packet_hash(refs) == manifest.get("packet_hash")


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
        if not packet_is_current(manifest):
            return {
                "ticker": ticker,
                "committee_date": committee_date,
                "action": "refresh",
                "tasks": [],
            }
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


def refresh(ticker: str, committee_date: str) -> Path:
    work = ROOT / ticker / "research" / "committee_work" / committee_date
    manifest = read_json(work / "manifest.json")
    suffix = str(manifest.get("packet_hash") or "unknown")[:8]
    archive = work.with_name(f"{committee_date}-superseded-{suffix}")
    if archive.exists():
        raise FileExistsError(f"stale committee archive already exists: {archive}")
    manifest["stage"] = "superseded"
    manifest["superseded_reason"] = "frozen_evidence_changed"
    write_json(work / "manifest.json", manifest)
    work.rename(archive)
    return initialize(ticker, committee_date)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--refresh-ticker")
    parser.add_argument("--refresh-date")
    args = parser.parse_args()
    if bool(args.refresh_ticker) != bool(args.refresh_date):
        parser.error("--refresh-ticker and --refresh-date must be used together")
    if args.refresh_ticker:
        path = refresh(args.refresh_ticker.upper(), args.refresh_date)
        print(path.relative_to(ROOT).as_posix())
        return 0
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
