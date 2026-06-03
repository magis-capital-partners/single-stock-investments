#!/usr/bin/env python3
"""Print a JSON array of tickers for batch Marvin deep dive (GitHub Actions matrix)."""
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


def resolve_tickers(
    *,
    queue_path: Path,
    use_queue: bool,
    cli_csv: str | None,
) -> list[str]:
    if cli_csv:
        return [t.strip() for t in cli_csv.split(",") if t.strip()]
    if use_queue and queue_path.is_file():
        try:
            payload = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        tickers = payload.get("tickers") or []
        if tickers:
            return list(tickers)
    return [t for _, t in onboard_pending_holdings()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ticker list for batch deep dive matrix")
    parser.add_argument(
        "--queue-file",
        type=Path,
        default=DEFAULT_QUEUE,
        help="Optional queue JSON (tickers array)",
    )
    parser.add_argument(
        "--use-queue",
        action="store_true",
        help="Prefer tickers from queue file when present",
    )
    parser.add_argument(
        "--tickers",
        help="Comma-separated override (workflow_dispatch input)",
    )
    args = parser.parse_args()
    tickers = resolve_tickers(
        queue_path=args.queue_file,
        use_queue=args.use_queue or bool(args.tickers is None),
        cli_csv=args.tickers,
    )
    if not tickers:
        print("[]")
        return
    print(json.dumps(tickers))


if __name__ == "__main__":
    main()
