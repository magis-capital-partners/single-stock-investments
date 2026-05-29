#!/usr/bin/env python3
"""Seed ai_overlay + segment_build on hyperscaler valuation.json, then recompute.

Usage:
  python _system/scripts/seed_hyperscaler_overlays.py AMZN
  python _system/scripts/seed_hyperscaler_overlays.py --all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable

# FY2025 segment operating income ($B) — Amazon 10-K Note 10
AMZN_SEGMENTS = {
    "segments": [
        {
            "id": "aws",
            "label": "Amazon Web Services (AWS)",
            "owner_cash_y0_bn": 33.4,
            "owner_cash_y0_per_share": 3.05,
            "owner_cash_y0_source": "Normalized FCF allocated 57.1% by FY2025 segment OI [Assumption]",
            "growth_y1_5": 0.14,
            "growth_y6_10": 0.09,
            "exit_pfcf_y10": 22,
            "notes": "FY2025 OI $45.6B; Q1 2026 +28% sales",
        },
        {
            "id": "north_america",
            "label": "North America stores",
            "owner_cash_y0_bn": 21.7,
            "owner_cash_y0_per_share": 1.98,
            "owner_cash_y0_source": "Normalized FCF allocated 37.0% by segment OI [Assumption]",
            "growth_y1_5": 0.08,
            "growth_y6_10": 0.06,
            "exit_pfcf_y10": 18,
            "notes": "FY2025 OI $29.6B",
        },
        {
            "id": "international",
            "label": "International stores",
            "owner_cash_y0_bn": 3.5,
            "owner_cash_y0_per_share": 0.32,
            "owner_cash_y0_source": "Normalized FCF allocated 5.9% by segment OI [Assumption]",
            "growth_y1_5": 0.10,
            "growth_y6_10": 0.07,
            "exit_pfcf_y10": 16,
            "notes": "FY2025 OI $4.8B",
        },
    ],
    "options": [
        {
            "id": "advertising_overlay",
            "label": "Advertising (> $70B TTM, inside segments)",
            "annual_drag_per_share": 0.0,
            "base_terminal_value_bn": 0,
            "notes": "Not split out; embedded in NA/Intl/AWS growth [Assumption]",
        }
    ],
    "corporate_drag": {
        "alphabet_level_drag_per_share": 0.0,
        "notes": "Segment OI sums to consolidated; capex drag in Lawrence FCF₀ normalization",
    },
}


def seed_amzn(data: dict) -> dict:
    data["valuation_overlay"] = "segment_cashflow"
    data["ai_overlay"] = {
        "as_of": data.get("as_of", "2026-05-29"),
        "status": "partial — normalized FCF vs TTM capex spike",
        "in_model": {
            "consolidated_fcf_y0": "$5.35/sh normalized (not TTM $1.2B FCF)",
            "aws_growth_in_segment_build": "14% / 9% Y1-5 / Y6-10",
            "capex_ttm_bn": "147.3B purchases vs 148.5B OCF",
            "custom_silicon": "Trainium/Graviton in narrative; not separate revenue line",
        },
        "not_in_model_requires_refresh": [
            "Advertising as separate owner-cash segment",
            "Trainium external sales schedule",
            "Agentic AI capex ROI per workload",
            "Anthropic mark-to-market in GAAP NI",
            "RPO / backlog for AWS (if disclosed)",
        ],
        "capex_stress_2026": {
            "ocf_bn_assumption": 148.5,
            "ocf_assumption_note": "TTM operating cash flow Q1 2026 supplemental",
            "capex_bn": 147.3,
            "capex_source": "TTM capital expenditures (purchases)",
            "implied_fcf_bn": 1.2,
            "implied_fcf_per_share": 0.11,
        },
        "ai_inflection_bull": {
            "fcf_per_share_y0": 9.0,
            "fcf_y0_note": "[Assumption] capex ~$90B sustainable vs $147B TTM; needs mgmt guide",
            "growth_y1_5": 0.12,
            "growth_y6_10": 0.08,
            "exit_pfcf_y10": 30,
            "drivers": "AWS AI share, ads, silicon, FCF inflection",
        },
    }
    build = {
        "framework": "speedwell_reverse_dcf",
        "as_of": data.get("as_of", "2026-05-29"),
        "horizon_years": 10,
        "discount_rate_explicit": 0.1,
        **AMZN_SEGMENTS,
    }
    data["segment_build"] = build
    return data


def seed_ticker(ticker: str) -> None:
    path = ROOT / ticker / "research" / "valuation.json"
    if not path.exists():
        print(f"SKIP {ticker}: no valuation.json")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if ticker == "AMZN":
        data = seed_amzn(data)
    elif ticker == "GOOGL":
        print(f"SKIP {ticker}: overlays already present")
        return
    else:
        print(f"SKIP {ticker}: no seed template")
        return
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Seeded {ticker} overlays -> {path.relative_to(ROOT)}")
    subprocess.check_call([PY, str(SCRIPTS / "marvin_valuation.py"), "--ticker", ticker, "--write"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", help="AMZN or GOOGL")
    parser.add_argument("--all", action="store_true", help="Seed all registry hyperscalers")
    args = parser.parse_args()
    if args.all:
        for t in ("GOOGL", "AMZN"):
            seed_ticker(t)
    elif args.ticker:
        seed_ticker(args.ticker.upper())
    else:
        parser.error("Provide TICKER or --all")


if __name__ == "__main__":
    main()
