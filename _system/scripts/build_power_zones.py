#!/usr/bin/env python3
"""Build dashboard/data/power_zones.json - persona power-zone fit per ticker.

Scores every registry holding against the persona applicability rules in
_system/frameworks/power_zones.json. A persona is "in its power zone" on a
ticker when the company's classification (archetype, moat, dhando, sleeve,
cycle) matches enough of the persona's demonstrated-alpha criteria. Rule fit
is blended with persona_calibration.json match rates so personas with
demonstrated letter/book overlap carry extra weight.

The output defines which persona lens IRRs the dashboard shows by default and
which framework future agent runs should apply to each company.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "_system" / "frameworks" / "power_zones.json"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
CALIBRATION_PATH = ROOT / "dashboard" / "data" / "persona_calibration.json"
OUTPUT = ROOT / "dashboard" / "data" / "power_zones.json"

UNKNOWN_VALUES = {"", "-", "unknown", "pending", "n/a", "none", None}


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def known(value) -> bool:
    return str(value).strip().lower() not in UNKNOWN_VALUES if value is not None else False


def score_ticker_zone(classification: dict, zone: dict) -> dict:
    """Score one ticker against one persona's rules."""
    rules: dict = zone.get("rules") or {}
    exclude: dict = zone.get("exclude") or {}
    min_matches = int(zone.get("min_matches") or 1)

    for field, banned in exclude.items():
        value = classification.get(field)
        if known(value) and str(value) in set(banned):
            return {
                "in_power_zone": False,
                "fit": 0.0,
                "matched": 0,
                "known_fields": 0,
                "matched_fields": [],
                "excluded_by": field,
            }

    matched_fields: list[str] = []
    known_fields = 0
    for field, allowed in rules.items():
        value = classification.get(field)
        if not known(value):
            continue
        known_fields += 1
        if str(value) in set(allowed):
            matched_fields.append(field)

    matched = len(matched_fields)
    fit = round(matched / len(rules), 3) if rules else 0.0
    return {
        "in_power_zone": matched >= min_matches,
        "fit": fit,
        "matched": matched,
        "known_fields": known_fields,
        "matched_fields": matched_fields,
        "excluded_by": None,
    }


def calibration_rates() -> dict[str, float | None]:
    doc = load_json(CALIBRATION_PATH, {})
    out: dict[str, float | None] = {}
    for row in doc.get("personas") or []:
        out[str(row.get("persona"))] = row.get("match_rate")
    return out


def blended_score(fit: float, match_rate: float | None) -> int:
    """0-100 fit blended with demonstrated calibration overlap.

    Personas without calibration data get a neutral 0.5 prior instead of
    being zeroed out (absence of letter holdings is not evidence of absence
    of skill).
    """
    prior = 0.5 if match_rate is None else float(match_rate)
    return max(0, min(100, round(100 * fit * (0.7 + 0.3 * prior))))


def build() -> dict:
    config = load_json(CONFIG_PATH, {})
    zones: dict = config.get("zones") or {}
    registry = load_json(REGISTRY_PATH, {})
    holdings: dict = registry.get("holdings") or {}
    watchlist: dict = registry.get("watchlist") or {}
    rates = calibration_rates()

    by_ticker: dict[str, dict] = {}
    for ticker, holding in sorted({**watchlist, **holdings}.items()):
        classification = (holding or {}).get("classification") or {}
        zone_results: dict[str, dict] = {}
        in_zone: list[str] = []
        for persona, zone in zones.items():
            result = score_ticker_zone(classification, zone)
            if result["fit"] <= 0 and not result["in_power_zone"]:
                continue
            result["match_rate"] = rates.get(persona)
            result["score"] = blended_score(result["fit"], rates.get(persona))
            zone_results[persona] = result
            if result["in_power_zone"]:
                in_zone.append(persona)
        classified = any(known(classification.get(f)) for f in ("archetype", "moat", "dhando", "investment_sleeve"))
        by_ticker[ticker] = {
            "in_zone": sorted(in_zone, key=lambda p: -zone_results[p]["score"]),
            "zones": zone_results,
            "classified": classified,
        }

    tickers_with_zone = sum(1 for entry in by_ticker.values() if entry["in_zone"])
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_updated": config.get("updated"),
        "personas": {
            pid: {"label": z.get("label"), "framework": z.get("framework"), "rules": z.get("rules"), "min_matches": z.get("min_matches")}
            for pid, z in zones.items()
        },
        "ticker_count": len(by_ticker),
        "tickers_in_zone": tickers_with_zone,
        "by_ticker": by_ticker,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build persona power-zone fit JSON.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output.relative_to(ROOT)} "
        f"({payload['ticker_count']} tickers, {payload['tickers_in_zone']} with a power zone)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
