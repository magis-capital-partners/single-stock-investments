#!/usr/bin/env python3
"""Summarize append-only LLM admission ledgers for cost and suppression review."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_events(paths: list[Path]) -> list[dict]:
    events: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def summarize(events: list[dict]) -> dict:
    by_consumer: dict[str, Counter] = defaultdict(Counter)
    suppression_reasons: Counter = Counter()
    for event in events:
        consumer = str(event.get("consumer") or "unknown")
        status = str(event.get("status") or "unknown")
        by_consumer[consumer][status] += 1
        if status in {"denied", "suppressed"}:
            suppression_reasons[str(event.get("reason") or "unspecified")] += 1
    return {
        "schema_version": "1.0",
        "event_count": len(events),
        "by_consumer": {key: dict(sorted(value.items())) for key, value in sorted(by_consumer.items())},
        "suppression_reasons": dict(suppression_reasons.most_common()),
    }


def markdown(summary: dict) -> str:
    lines = ["# LLM usage audit", "", f"Ledger events: {summary['event_count']}", ""]
    lines += ["| Consumer | Reserved | Completed | Failed | Suppressed/denied |", "|---|---:|---:|---:|---:|"]
    for consumer, counts in summary["by_consumer"].items():
        denied = counts.get("denied", 0) + counts.get("suppressed", 0)
        lines.append(
            f"| {consumer} | {counts.get('reserved', 0)} | {counts.get('completed', 0)} | "
            f"{counts.get('failed', 0)} | {denied} |"
        )
    if summary["suppression_reasons"]:
        lines += ["", "## Suppression reasons", ""]
        lines += [f"- {reason}: {count}" for reason, count in summary["suppression_reasons"].items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledgers", nargs="+", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()
    result = summarize(load_events(args.ledgers))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown(result), encoding="utf-8")
    if not args.json_out and not args.markdown_out:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
