#!/usr/bin/env python3
"""Upsert a Cleveland-Cliffs earnings row into the iron_ore_steel filing panel.

  python _system/scripts/update_clf_operating_panel.py \
    --as-of 2026-06-30 --shipments 4.025 --fy-guide-mid 16.75 --asp 1124 \
    --source 'https://www.clevelandcliffs.com/.../cleveland-cliffs-reports-second-quarter-2026-results' \
    --note 'Q2 2026 earnings'

Context only. Does not edit MSB valuation.json.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "_system" / "reference" / "market-data" / "themes" / "filing_panels" / "clf_operating_panel.csv"
FIELDS = [
    "as_of",
    "ticker",
    "steel_shipments_mtons",
    "fy_guide_mid_mtons",
    "asp_usd",
    "source_path",
    "note",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", required=True, help="Quarter end YYYY-MM-DD")
    ap.add_argument("--shipments", type=float, required=True, help="Steel shipments million net tons")
    ap.add_argument("--fy-guide-mid", type=float, default=None, help="FY shipment guide midpoint m tons")
    ap.add_argument("--asp", type=float, default=None, help="Average selling price USD/net ton")
    ap.add_argument("--source", required=True, help="URL or local path to CLF release")
    ap.add_argument("--note", default="", help="Short note (e.g. Q2 2026 earnings)")
    args = ap.parse_args()

    PANEL.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if PANEL.exists():
        with PANEL.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if (r.get("as_of") or "")[:10] != args.as_of[:10]]
    rows.append(
        {
            "as_of": args.as_of[:10],
            "ticker": "CLF",
            "steel_shipments_mtons": args.shipments,
            "fy_guide_mid_mtons": args.fy_guide_mid if args.fy_guide_mid is not None else "",
            "asp_usd": args.asp if args.asp is not None else "",
            "source_path": args.source,
            "note": args.note,
        }
    )
    rows.sort(key=lambda r: r.get("as_of") or "")
    with PANEL.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {PANEL.relative_to(ROOT)} ({len(rows)} rows); latest as_of={rows[-1].get('as_of')}")
    print("Next: python _system/scripts/fetch_theme_panel.py --theme iron_ore_steel")
    print("      python _system/scripts/build_msb_operator_model.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
