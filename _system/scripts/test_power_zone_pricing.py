import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_power_zone_pricing import (
    build_economic_value_bridge,
    can_seed,
    entry_price_for_hurdle,
    implied_constant_growth,
)


class PowerZonePricingTests(unittest.TestCase):
    def test_entry_price_declines_as_hurdle_rises(self):
        scenario = {"growth_y1_5": 0.08, "growth_y6_10": 0.04, "exit_pfcf_y10": 15}
        prices = [entry_price_for_hurdle(2.0, scenario, hurdle, 7) for hurdle in (0.10, 0.12, 0.15, 0.20)]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_implied_growth_reprices_to_observed_price(self):
        growth = implied_constant_growth(100, 5, 15, 7)
        self.assertIsNotNone(growth)
        self.assertGreater(growth, -25)
        self.assertLess(growth, 100)

    def test_can_seed_requires_complete_model_inputs(self):
        complete = {
            "inputs": {"price": 50, "fcf_per_share": 3},
            "scenarios": {"base": {"growth_y1_5": 0.05, "growth_y6_10": 0.03, "exit_pfcf_y10": 14}},
        }
        self.assertTrue(can_seed(complete))
        self.assertFalse(
            can_seed(
                {
                    "inputs": {"price": 50},
                    "scenarios": {"base": {"growth_y1_5": 0.05, "exit_pfcf_y10": 14}},
                }
            )
        )
        self.assertFalse(
            can_seed(
                {
                    "inputs": {"price": 50, "fcf_per_share": 3},
                    "scenarios": {"base": {"exit_pfcf_y10": 14}},
                }
            )
        )
        self.assertFalse(
            can_seed(
                {
                    "inputs": {"price": 50, "fcf_per_share": -1},
                    "scenarios": {"base": {"growth_y1_5": 0.05, "exit_pfcf_y10": 14}},
                }
            )
        )

    def test_economic_bridge_requires_complete_non_overlapping_coverage(self):
        data = {
            "inputs": {"price": 10},
            "component_valuation_results": {
                "total_equity_value_per_share": {"low": 4, "base": 5, "high": 6},
                "additive_components": [
                    {"id": "asset", "low_per_share": 4, "base_per_share": 5, "high_per_share": 6}
                ],
            },
        }
        config = {"economic_value_bridge": {
            "component_groups": [{"label": "Asset", "component_ids": ["asset"]}],
            "gross_comparable_nav_per_share": {"low": 8, "base": 10, "high": 12},
        }}
        bridge = build_economic_value_bridge(data, config)
        self.assertTrue(bridge["complete_component_coverage"])
        self.assertEqual(bridge["gross_to_risked_discount_pct"]["base"], 50.0)


if __name__ == "__main__":
    unittest.main()
