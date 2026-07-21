#!/usr/bin/env python3
"""Print a JSON matrix for batch Marvin dispatch (GitHub Actions).

Supports either:
  - deep_dive_dispatch_queue.json → reason batch_onboard_pending
  - contract_backfill_queue.json → reason contract_backfill

When both queues have tickers, prefer the queue file passed via --queue-file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from marvin_pick_ticker import onboard_pending_holdings  # noqa: E402

DEFAULT_QUEUE = ROOT / "_system" / "data" / "deep_dive_dispatch_queue.json"
BACKFILL_QUEUE = ROOT / "_system" / "data" / "contract_backfill_queue.json"


def load_queue(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def resolve_jobs(
    *,
    queue_path: Path,
    use_queue: bool,
    cli_csv: str | None,
    reason_override: str | None,
) -> list[dict]:
    if cli_csv:
        reason = reason_override or "batch_onboard_pending"
        consumer = "marvin_contract_backfill" if reason == "contract_backfill" else "marvin_research"
        return [
            {"ticker": t.strip().upper(), "reason": reason, "consumer": consumer}
            for t in cli_csv.split(",")
            if t.strip()
        ]

    if use_queue:
        if queue_path != DEFAULT_QUEUE:
            candidates = [queue_path]
        else:
            backfill = load_queue(BACKFILL_QUEUE)
            deep = load_queue(DEFAULT_QUEUE)
            # Prefer whichever queue has tickers and the newer updated stamp.
            ranked = []
            if backfill.get("tickers"):
                ranked.append((str(backfill.get("updated") or ""), BACKFILL_QUEUE, backfill))
            if deep.get("tickers"):
                ranked.append((str(deep.get("updated") or ""), DEFAULT_QUEUE, deep))
            ranked.sort(reverse=True)
            candidates = [path for _, path, _ in ranked] or [DEFAULT_QUEUE]
        for path in candidates:
            payload = load_queue(path)
            tickers = [str(t).upper() for t in (payload.get("tickers") or []) if t]
            if not tickers:
                continue
            reason = reason_override or payload.get("reason") or (
                "contract_backfill" if path == BACKFILL_QUEUE else "batch_onboard_pending"
            )
            consumer = "marvin_contract_backfill" if reason == "contract_backfill" else "marvin_research"
            return [{"ticker": t, "reason": reason, "consumer": consumer} for t in tickers]

    return [
        {"ticker": t, "reason": "onboard_pending", "consumer": "marvin_research"}
        for _, t in onboard_pending_holdings()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ticker matrix for Marvin batch dispatch")
    parser.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--use-queue", action="store_true")
    parser.add_argument("--tickers", help="Comma-separated override")
    parser.add_argument("--reason", help="Force reason for all jobs")
    parser.add_argument("--tickers-only", action="store_true", help="Emit a flat ticker JSON array")
    args = parser.parse_args()
    jobs = resolve_jobs(
        queue_path=args.queue_file,
        use_queue=args.use_queue or args.tickers is None,
        cli_csv=args.tickers,
        reason_override=args.reason,
    )
    if args.tickers_only:
        print(json.dumps([job["ticker"] for job in jobs]))
        return
    print(json.dumps(jobs))


if __name__ == "__main__":
    main()
