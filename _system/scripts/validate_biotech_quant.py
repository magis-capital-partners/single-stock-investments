#!/usr/bin/env python3
"""Lightweight validation gates for biotech quant pipeline artifacts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "_system" / "reference" / "biotech-quant" / "FACTOR_SPEC.json"
SIGNALS = ROOT / "_system" / "reference" / "market-data" / "ownership" / "signals_latest.json"
PAPER = ROOT / "_system" / "reference" / "market-data" / "ownership" / "paper_book_latest.json"
FULL = ROOT / "_system" / "reference" / "market-data" / "ownership" / "records" / "full"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not SPEC.exists():
        errors.append("missing FACTOR_SPEC.json")
    if not SIGNALS.exists():
        errors.append("missing signals_latest.json")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    signals = json.loads(SIGNALS.read_text(encoding="utf-8"))
    by_ticker = signals.get("by_ticker") or {}

    for factor in spec.get("factors") or []:
        status = factor.get("status")
        fid = factor.get("id")
        keys = factor.get("signal_keys") or []
        if status != "live":
            continue
        present = any(row.get(k) is not None for row in by_ticker.values() for k in keys)
        if not present:
            # Online-harvest factors: warn in offline CI; consensus/spend must be present
            if fid in {"insider_non_ceo", "short_interest", "peer_momentum"}:
                warnings.append(
                    f"factor {fid} status=live but no signal keys populated "
                    f"(run online harvest: biotech-insider-fetch / biotech-short / biotech-clinical)"
                )
            else:
                errors.append(f"factor {fid} status=live but no signal keys populated")

    if (spec.get("composite") or {}).get("status") == "live" and PAPER.exists():
        paper = json.loads(PAPER.read_text(encoding="utf-8"))
        if not paper.get("long") and not paper.get("short"):
            warnings.append("paper_book_latest.json exists but long/short empty")
    elif (spec.get("composite") or {}).get("status") == "live":
        warnings.append("paper_book_latest.json missing — run build_biotech_paper_book.py")

    # Multi-quarter history stub: need ≥4 distinct quarters across full records
    quarters: set[str] = set()
    if FULL.exists():
        for path in FULL.glob("*/*.json"):
            if path.name in {"latest.json"}:
                continue
            stem = path.stem
            if len(stem) == 6 and stem[4] == "Q":
                quarters.add(stem)
    if len(quarters) < 4:
        warnings.append(
            f"only {len(quarters)} full-table quarter(s) - forward-return validation needs >=4 "
            "(run ingest_specialist_13f.py --backfill-quarters 8)"
        )
    else:
        print(f"OK: {len(quarters)} quarters available for future forward-return stub")

    if len(by_ticker) < 50:
        warnings.append(f"universe only {len(by_ticker)} names")

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK: biotech quant ({len(by_ticker)} universe, {len(spec.get('factors') or [])} factors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
