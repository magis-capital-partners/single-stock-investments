"""Partition a generated stock-history snapshot before private preservation.

Output parts contain private research. Publish them through the existing private
snapshot process; commit only their metadata counterparts and the small index.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_PART_BYTES = 8 * 1024 * 1024
PREFIX = "_system/reference/stock-research/"


def partition(document: dict, output: Path, max_bytes: int = DEFAULT_PART_BYTES) -> dict:
    if document.get("schema_version") != "stock-research-universe.v1" or not document.get("companies"):
        raise ValueError("A complete stock research snapshot is required")
    output.mkdir(parents=True, exist_ok=True)
    (output / "parts").mkdir(exist_ok=True)
    parts, current, size, largest = [], {}, 128, 0

    def flush():
        nonlocal current, size, largest
        relative = f"parts/part-{len(parts):03d}.json"
        raw = json.dumps({"schema_version": "stock-research-universe.v1", "companies": current}, ensure_ascii=False, separators=(",", ":")).encode()
        if len(raw) > max_bytes:
            raise ValueError("An individual stock exceeds the private part size limit")
        (output / relative).write_bytes(raw)
        parts.append(PREFIX + relative)
        largest = max(largest, len(raw))
        current, size = {}, 128

    for ticker, brief in document["companies"].items():
        if brief.get("ticker") != ticker:
            raise ValueError("Stock identity does not match its snapshot key")
        amount = len(json.dumps({ticker: brief}, ensure_ascii=False, separators=(",", ":")).encode())
        if current and size + amount > max_bytes:
            flush()
        current[ticker] = brief
        size += amount
    if current:
        flush()
    index = {"schema_version": "stock-research-universe-parts.v1", "stock_count": len(document["companies"]), "parts": parts}
    (output / "universe.json").write_text(json.dumps(index, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"stocks": index["stock_count"], "parts": len(parts), "largest_part_bytes": largest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(partition(json.loads(args.input.read_text(encoding="utf-8")), args.output)))
