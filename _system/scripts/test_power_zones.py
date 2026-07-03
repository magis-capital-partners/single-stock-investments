#!/usr/bin/env python3
"""Tests for persona power-zone scoring."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_power_zones import blended_score, score_ticker_zone  # noqa: E402

HOHN_ZONE = {
    "rules": {
        "archetype": ["compounder", "croupier", "platform", "infrastructure"],
        "moat": ["stable", "widening"],
        "investment_sleeve": ["exchanges_markets", "software_platforms", "financial_services"],
    },
    "exclude": {"dhando": ["full"]},
    "min_matches": 2,
}

PABRAI_ZONE = {
    "rules": {
        "dhando": ["full", "partial"],
        "archetype": ["optionality", "turnaround", "commodity_cyclical"],
        "investment_sleeve": ["real_assets_land", "real_assets_lt", "energy_infrastructure"],
        "cycle": ["trough", "transition"],
    },
    "min_matches": 2,
}


class PowerZoneTests(unittest.TestCase):
    def test_quality_large_cap_is_in_hohn_zone(self) -> None:
        classification = {
            "archetype": "croupier",
            "moat": "stable",
            "dhando": "none",
            "investment_sleeve": "exchanges_markets",
        }
        result = score_ticker_zone(classification, HOHN_ZONE)
        self.assertTrue(result["in_power_zone"])
        self.assertEqual(result["matched"], 3)
        self.assertEqual(result["fit"], 1.0)

    def test_deep_value_bet_is_in_pabrai_zone_not_hohn(self) -> None:
        classification = {
            "archetype": "optionality",
            "moat": "unproven",
            "dhando": "full",
            "investment_sleeve": "real_assets_land",
            "cycle": "trough",
        }
        pabrai = score_ticker_zone(classification, PABRAI_ZONE)
        hohn = score_ticker_zone(classification, HOHN_ZONE)
        self.assertTrue(pabrai["in_power_zone"])
        self.assertFalse(hohn["in_power_zone"])
        self.assertEqual(hohn["excluded_by"], "dhando")

    def test_unknown_classification_matches_nothing(self) -> None:
        classification = {"archetype": "unknown", "moat": "unproven", "dhando": "pending", "investment_sleeve": "-"}
        result = score_ticker_zone(classification, HOHN_ZONE)
        self.assertFalse(result["in_power_zone"])
        self.assertEqual(result["matched"], 0)
        # "unproven" moat is a real assessment (known), the rest are unknown.
        self.assertEqual(result["known_fields"], 1)

    def test_single_match_below_min_is_out_of_zone(self) -> None:
        classification = {"archetype": "compounder", "moat": "unproven", "investment_sleeve": "-"}
        result = score_ticker_zone(classification, HOHN_ZONE)
        self.assertFalse(result["in_power_zone"])
        self.assertEqual(result["matched"], 1)

    def test_blended_score_uses_neutral_prior_without_calibration(self) -> None:
        self.assertEqual(blended_score(1.0, None), 85)
        self.assertEqual(blended_score(1.0, 1.0), 100)
        self.assertEqual(blended_score(1.0, 0.0), 70)
        self.assertEqual(blended_score(0.0, 1.0), 0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
