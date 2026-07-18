#!/usr/bin/env python3
"""Print JSON array of tickers for batch Vicki IR harvest (GitHub Actions matrix)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ir_adapter_gate import evaluate as evaluate_ir_adapter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = ROOT / "_system" / "data" / "vicki_dispatch_queue.json"


def resolve_tickers(*, queue_path: Path, use_queue: bool, cli_csv: str | None, force: bool = False) -> list[str]:
    if cli_csv:
        requested = [t.strip() for t in cli_csv.split(",") if t.strip()]
        return [ticker for ticker in requested if evaluate_ir_adapter(ticker, force=force)["eligible"]]
    if use_queue and queue_path.is_file():
        try:
            payload = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        tickers = payload.get("tickers") or []
        if tickers:
            return [ticker for ticker in tickers if evaluate_ir_adapter(ticker, force=force)["eligible"]]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ticker list for Vicki IR harvest matrix")
    parser.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--use-queue", action="store_true")
    parser.add_argument("--tickers", help="Comma-separated override")
    parser.add_argument("--force", action="store_true", help="Bypass adapter and active-gap checks")
    args = parser.parse_args()
    tickers = resolve_tickers(
        queue_path=args.queue_file,
        use_queue=args.use_queue or args.tickers is None,
        cli_csv=args.tickers,
        force=args.force,
    )
    print(json.dumps(tickers) if tickers else "[]")


if __name__ == "__main__":
    main()
