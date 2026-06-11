#!/usr/bin/env python3
"""Print JSON array of tickers for batch Vicki IR harvest (GitHub Actions matrix)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = ROOT / "_system" / "data" / "vicki_dispatch_queue.json"


def resolve_tickers(*, queue_path: Path, use_queue: bool, cli_csv: str | None) -> list[str]:
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
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ticker list for Vicki IR harvest matrix")
    parser.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--use-queue", action="store_true")
    parser.add_argument("--tickers", help="Comma-separated override")
    args = parser.parse_args()
    tickers = resolve_tickers(
        queue_path=args.queue_file,
        use_queue=args.use_queue or args.tickers is None,
        cli_csv=args.tickers,
    )
    print(json.dumps(tickers) if tickers else "[]")


if __name__ == "__main__":
    main()
