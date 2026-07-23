#!/usr/bin/env python3
"""Build MSB operator transmission model (Cliffs + commodities + royalty 8-K).

  python _system/scripts/build_msb_operator_model.py
  python _system/scripts/build_msb_operator_model.py --write

Pulls theme-panel series (iron ore, SLX, CLF shipments) and Mesabi royalty facts.
Context only — never edits valuation.json IRR / component proofs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
THEMES_MANIFEST = ROOT / "_system" / "reference" / "market-data" / "themes" / "manifest.json"
ROYALTY_EVIDENCE = ROOT / "MSB" / "research" / "evidence" / "royalty_report_latest.json"
OUT = ROOT / "MSB" / "research" / "operator_model.json"
PY = sys.executable

SERIES_IDS = (
    "iron_ore_spot_usd",
    "steel_producer_etf",
    "clf_steel_shipments_q_mtons",
    "clf_fy_shipment_guide_mid_mtons",
    "msb_northshore_tons",
    "msb_bonus_royalty_usd",
)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def theme_lookup(series_id: str) -> dict | None:
    themes = (load_json(THEMES_MANIFEST).get("themes") or {})
    for theme in themes.values():
        series = (theme or {}).get("series") or {}
        if series_id in series:
            return series[series_id]
    return None


def ensure_royalty_parsed() -> dict:
    if ROYALTY_EVIDENCE.exists():
        return load_json(ROYALTY_EVIDENCE)
    subprocess.run(
        [PY, str(SCRIPTS / "parse_msb_royalty_report.py"), "--write"],
        cwd=ROOT,
        check=False,
    )
    return load_json(ROYALTY_EVIDENCE)


def volume_signal(clf_q: float | None, prior_q: float | None, tons: float | None) -> str:
    """Northshore tons dominate; CLF steel QoQ is secondary orientation only."""
    if tons is not None and tons <= 0:
        return "bearish"
    if tons is not None and tons >= 700_000:
        return "constructive"
    if tons is not None and tons < 300_000:
        return "bearish"
    if clf_q is not None and prior_q is not None and clf_q > prior_q + 0.05:
        return "constructive"
    return "neutral"


def build_model() -> dict:
    royalty = ensure_royalty_parsed()
    commodities = {}
    operator = {}
    for sid in SERIES_IDS:
        row = theme_lookup(sid) or {}
        entry = {
            "latest": row.get("latest"),
            "as_of": row.get("as_of"),
            "source": row.get("source"),
            "stale": bool(row.get("stale")),
            "direction": row.get("direction"),
        }
        if sid.startswith(("iron_ore", "steel_")):
            commodities[sid] = entry
        else:
            operator[sid] = entry

    tons = royalty.get("tons_shipped")
    bonus = royalty.get("bonus_royalty_usd")
    threshold = royalty.get("bonus_threshold_usd")
    clf_q = (operator.get("clf_steel_shipments_q_mtons") or {}).get("latest")
    # Prior quarter from filing panel is not in theme latest; use seeded Q1 if present via note only.
    signal = volume_signal(
        float(clf_q) if clf_q is not None else None,
        4.108,  # Q1 2026 from clf_operating_panel seed; orientation only
        float(tons) if tons is not None else None,
    )

    return {
        "ticker": "MSB",
        "operator_ticker": "CLF",
        "as_of": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "in_base_irr": False,
        "disclaimer": (
            "Context only. Commodity prices and CLF steel shipments orient stance; "
            "MSB distributions are driven by Northshore tons and deemed pellet price "
            "vs the bonus threshold from Mesabi royalty 8-Ks. Do not auto-edit "
            "valuation.json component proofs or implied_return from this file."
        ),
        "commodities": commodities,
        "operator": operator,
        "royalty": {
            "period_end": royalty.get("period_end"),
            "tons_shipped": tons,
            "base_royalty_usd": royalty.get("base_royalty_usd"),
            "bonus_royalty_usd": bonus,
            "bonus_threshold_usd": threshold,
            "bonus_on": bool(royalty.get("bonus_on")),
            "source_path": royalty.get("source_path"),
        },
        "transmission": {
            "bonus_switch": "on" if royalty.get("bonus_on") else "off",
            "volume_signal": signal,
            "watch_next": [
                "Next Mesabi quarterly royalty 8-K (tons, deemed price, bonus vs threshold)",
                "CLF earnings for Northshore / idle / pellet commentary (not consolidated EPS alone)",
            ],
            "notes": [
                "Iron ore spot and SLX are orientation for pellet/steel regime — not the contractual deemed price.",
                "CLF quarterly steel tons ≠ Northshore tons; use royalty exhibit for MSB cash.",
            ],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--refresh-themes",
        action="store_true",
        help="Run fetch_theme_panel.py --theme iron_ore_steel before building",
    )
    args = ap.parse_args()

    if args.refresh_themes:
        subprocess.run(
            [PY, str(SCRIPTS / "fetch_theme_panel.py"), "--theme", "iron_ore_steel"],
            cwd=ROOT,
            check=False,
        )

    model = build_model()
    print(
        f"MSB operator model: bonus={model['transmission']['bonus_switch']} "
        f"volume={model['transmission']['volume_signal']} "
        f"tons={model['royalty'].get('tons_shipped')}"
    )
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    else:
        print(json.dumps(model, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
