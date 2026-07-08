#!/usr/bin/env python3
"""Precision gate for letter date parsing against letter_date_gold.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from letter_date_parser import pick_letter_date  # noqa: E402

GOLD_PATH = Path(__file__).resolve().parent / "_eval" / "letter_date_gold.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", action="store_true", help="Run gold corpus gate (CI)")
    args = parser.parse_args()
    if not args.gold:
        parser.print_help()
        return 0

    if not GOLD_PATH.exists():
        print(f"ERROR: missing gold file {GOLD_PATH}", file=sys.stderr)
        return 1

    rows = [json.loads(line) for line in GOLD_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    misses = 0
    for row in rows:
        iso, source, confidence = pick_letter_date(row["stem"], None, row.get("folder_q"))
        if iso != row["expect_date"]:
            misses += 1
            print(
                f"MISS date: {row['stem'][:70]} -> {iso} (expected {row['expect_date']})",
                file=sys.stderr,
            )
            continue
        if row.get("expect_source") and source != row["expect_source"]:
            misses += 1
            print(
                f"MISS source: {row['stem'][:70]} -> {source} (expected {row['expect_source']})",
                file=sys.stderr,
            )
        if confidence < 40:
            misses += 1
            print(f"LOW confidence ({confidence}): {row['stem'][:70]}", file=sys.stderr)

    if misses:
        print(f"FAIL: {misses}/{len(rows)} gold rows missed", file=sys.stderr)
        return 1
    print(f"PASS: letter date gold {len(rows)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
