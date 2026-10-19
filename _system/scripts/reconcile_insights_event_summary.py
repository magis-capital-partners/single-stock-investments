"""Rebuild derived manifest counts from the canonical committed event shard.

Media-only publishers can carry an older manifest while preserving the current
event shard. Reconcile metadata before strict validation; never alter events,
raw intake counts, classifications or evidence.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def reconciled_manifest(manifest: dict, events: list[dict]) -> dict:
    if not isinstance(manifest, dict) or not isinstance(events, list):
        raise ValueError("Manifest must be an object and events must be a list")
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Each retained event must be an object")
    result = copy.deepcopy(manifest)
    summary = result.setdefault("provenance", {}).setdefault("event_triage_summary", {})
    dates = sorted(e["observed_at"] for e in events if e.get("observed_at"))
    # Keep the same retained-feed definitions as build_insights.finalize_events.
    summary.update({
        "signal": sum(e.get("tier") == "signal" and bool(e.get("feed_eligible")) for e in events),
        "context": sum(e.get("tier") == "context" and bool(e.get("feed_eligible")) for e in events),
        "noise": sum(e.get("tier") == "noise" or not e.get("feed_eligible") for e in events),
        "human_review": sum(e.get("triage_verdict") == "human_review" for e in events),
        "scheduled": sum(e.get("event_kind") == "scheduled" for e in events),
        "missing_evidence": sum(e.get("evidence_status") == "missing" for e in events),
        "retained_event_count": len(events),
        "history_start": dates[0] if dates else None,
        "history_end": dates[-1] if dates else None,
    })
    result["event_count"] = len(events)
    return result


def reconcile(data_dir: Path) -> bool:
    path = data_dir / "insights/manifest.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    shard = json.loads((data_dir / "insights/events.json").read_text(encoding="utf-8"))
    updated = reconciled_manifest(original, shard.get("events"))
    if updated == original:
        return False
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        json.dump(updated, out, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        out.write("\n")
        temporary = Path(out.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dashboard/data")
    args = parser.parse_args()
    changed = reconcile(args.data_dir)
    print("Reconciled event summary from retained events" if changed else "Event summary already consistent")


if __name__ == "__main__":
    main()
