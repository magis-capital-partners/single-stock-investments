#!/usr/bin/env python3
"""Roll up comp-based land marks for CPRT yard registry.

Fair land = sum(owned acres × local comp $/acre). GAAP historical cost is
never used as a mark input; it appears only in reconciliation output.

Usage:
  python CPRT/_scripts/roll_up_land_marks.py
  python CPRT/_scripts/roll_up_land_marks.py --write
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CPRT = ROOT / "CPRT"
PILOT_CSV = CPRT / "research" / "yard_land_marks_pilot.csv"
ANCHORS_JSON = CPRT / "research" / "land_valuation" / "transaction_anchors.json"
SUMMARY_JSON = CPRT / "research" / "land_valuation" / "fair_land_summary.json"
GAAP_LAND_M = 2394.553
FILED_EQUITY_M = 9187.033
SHARES = 977_600_000


def load_pilot_marks() -> list[dict]:
    rows: list[dict] = []
    with PILOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            base = row.get("fair_land_value_usd_base", "").strip()
            if not base:
                continue
            rows.append(
                {
                    "yard_id": row["yard_id"],
                    "name": row["name"],
                    "mark_status": row.get("mark_status", ""),
                    "fair_land_usd": float(base),
                    "ownership_status": row.get("ownership_status", ""),
                }
            )
    return rows


def weighted_per_acre(transactions: list[dict], exclude_outlier_ids: set[str]) -> dict:
    total_price = 0.0
    total_acres = 0.0
    for tx in transactions:
        if tx["id"] in exclude_outlier_ids:
            continue
        total_price += float(tx["price_usd"])
        total_acres += float(tx["acres"])
    per_acre = total_price / total_acres if total_acres else 0.0
    return {
        "weighted_per_acre_usd": round(per_acre),
        "transaction_count": len(transactions) - len(exclude_outlier_ids),
        "total_acres_in_sample": round(total_acres, 1),
        "total_price_usd": round(total_price),
    }


def extrapolate_network(model: dict, per_acre: float, per_acre_low: float, per_acre_high: float) -> dict:
    def fair(acres: float, rate: float) -> float:
        return round(acres * rate / 1_000_000, 3)

    low_ac = model["owned_acres_low"]
    base_ac = model["owned_acres_base"]
    high_ac = model["owned_acres_high"]
    return {
        "low_m": fair(low_ac, per_acre_low),
        "base_m": fair(base_ac, per_acre),
        "high_m": fair(high_ac, per_acre_high),
        "owned_acres": {
            "low": low_ac,
            "base": base_ac,
            "high": high_ac,
        },
        "implied_per_acre_usd": {
            "low": round(per_acre_low),
            "base": round(per_acre),
            "high": round(per_acre_high),
        },
    }


def build_summary() -> dict:
    anchors = json.loads(ANCHORS_JSON.read_text(encoding="utf-8"))
    pilot = load_pilot_marks()
    pilot_sum_m = sum(r["fair_land_usd"] for r in pilot) / 1_000_000

    core = weighted_per_acre(anchors["transactions"], exclude_outlier_ids={"palm_beach_2025"})
    all_tx = weighted_per_acre(anchors["transactions"], exclude_outlier_ids=set())

    base_rate = core["weighted_per_acre_usd"]
    low_rate = round(base_rate * 0.65)
    high_rate = round(base_rate * 1.35)

    network = extrapolate_network(anchors["owned_acreage_model"], base_rate, low_rate, high_rate)
    gaap_land_ps = GAAP_LAND_M * 1_000_000 / SHARES
    filed_book_ps = FILED_EQUITY_M * 1_000_000 / SHARES

    def book_ps(fair_land_m: float) -> float:
        equity_m = FILED_EQUITY_M + (fair_land_m - GAAP_LAND_M)
        return round(equity_m * 1_000_000 / SHARES, 2)

    return {
        "ticker": "CPRT",
        "as_of": str(date.today()),
        "method": "comp_based_land_roll_up",
        "rule": "Fair land = owned acres × comp $/acre. GAAP historical cost is reconciliation only.",
        "gaap_land_m": GAAP_LAND_M,
        "gaap_land_source": "FY2025 10-K PP&E note — historical cost, display only",
        "pilot_marks": {
            "yard_count": len(pilot),
            "fair_land_sum_m": round(pilot_sum_m, 3),
            "yards": pilot,
        },
        "transaction_anchor_sample": core,
        "transaction_anchor_including_outliers": all_tx,
        "network_fair_land_m": network,
        "book_estimate_bridge": {
            "filed_equity_m": FILED_EQUITY_M,
            "filed_book_per_share": round(filed_book_ps, 2),
            "gaap_land_per_share": round(gaap_land_ps, 2),
            "current_book_per_share": {
                "low": book_ps(network["low_m"]),
                "base": book_ps(network["base_m"]),
                "high": book_ps(network["high_m"]),
            },
            "land_uplift_per_share": {
                "low": round(book_ps(network["low_m"]) - filed_book_ps, 2),
                "base": round(book_ps(network["base_m"]) - filed_book_ps, 2),
                "high": round(book_ps(network["high_m"]) - filed_book_ps, 2),
            },
            "delta_equity_m": {
                "low": round(network["low_m"] - GAAP_LAND_M, 3),
                "base": round(network["base_m"] - GAAP_LAND_M, 3),
                "high": round(network["high_m"] - GAAP_LAND_M, 3),
            },
        },
        "coverage_gaps": [
            "Registry 231/281 yards — assessor ownership and acres pending on most rows",
            "Pilot: 7 of 20 yards with numeric marks; 13 pending comp packets",
            "International yards need country land-registry comps",
            "Palm Beach 2025 outlier excluded from base $/acre; included in high scenario",
        ],
        "human_review": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write fair_land_summary.json")
    args = parser.parse_args()
    summary = build_summary()
    text = json.dumps(summary, indent=2)
    print(text)
    if args.write:
        SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_JSON.write_text(text + "\n", encoding="utf-8")
        print(f"\nWrote {SUMMARY_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
