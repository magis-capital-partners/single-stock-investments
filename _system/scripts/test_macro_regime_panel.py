"""Tests for macro_regime_panel signed interpretation + regime object."""
from __future__ import annotations

import unittest

from macro_regime_panel import (
    build_portfolio_macro_regime,
    build_series_rows,
    regime_to_compat_macro_list,
    signed_direction,
)


class SignedDirectionTests(unittest.TestCase):
    def test_hy_oas_up_is_risk_off(self):
        self.assertEqual(signed_direction("hy_oas", "up"), "risk_off")

    def test_hy_oas_down_is_risk_on(self):
        self.assertEqual(signed_direction("hy_oas", "down"), "risk_on")

    def test_ust_10y_up_is_risk_off(self):
        self.assertEqual(signed_direction("ust_10y", "up"), "risk_off")

    def test_vix_up_is_risk_off(self):
        self.assertEqual(signed_direction("vix_level", "up"), "risk_off")

    def test_credit_impulse_up_is_risk_on(self):
        self.assertEqual(signed_direction("credit_impulse_1m", "up"), "risk_on")

    def test_dxy_up_is_neutral(self):
        self.assertEqual(signed_direction("dxy_broad", "up"), "neutral")


class BuildRegimeTests(unittest.TestCase):
    def sample_manifest(self) -> dict:
        return {
            "as_of": "2026-07-10",
            "themes": {
                "macro_regime": {
                    "series": {
                        "hy_oas": {
                            "label": "High-yield OAS",
                            "latest": 3.2,
                            "as_of": "2026-07-10",
                            "yoy_pct": 20.0,
                            "direction": "up",
                            "optional": False,
                        },
                        "ust_10y": {
                            "label": "UST 10Y",
                            "latest": 4.5,
                            "as_of": "2026-07-10",
                            "yoy_pct": 5.0,
                            "direction": "up",
                            "optional": False,
                        },
                        "dxy_broad": {
                            "label": "DXY broad",
                            "latest": 101.0,
                            "as_of": "2026-07-10",
                            "yoy_pct": 3.0,
                            "direction": "up",
                            "optional": True,
                        },
                        "vix_level": {
                            "label": "VIX",
                            "latest": 15.0,
                            "as_of": "2026-07-10",
                            "yoy_pct": -5.0,
                            "direction": "down",
                            "optional": False,
                        },
                        # Duplicate-ish second dollar series should not double-spam
                        "dxy_narrow": {
                            "label": "DXY narrow",
                            "latest": 102.0,
                            "as_of": "2026-07-10",
                            "yoy_pct": 2.0,
                            "direction": "up",
                            "optional": True,
                        },
                    }
                }
            },
        }

    def test_dedupe_by_series_id(self):
        rows = build_series_rows(self.sample_manifest(), limit=5)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("hy_oas", ids)
        self.assertIn("ust_10y", ids)

    def test_hy_oas_not_bullish_compat(self):
        regime = build_portfolio_macro_regime(self.sample_manifest())
        self.assertIn(regime["label"], {"calm", "adapting", "stressed"})
        self.assertTrue(regime["series"])
        hy = next(s for s in regime["series"] if s["id"] == "hy_oas")
        self.assertEqual(hy["signed_direction"], "risk_off")
        compat = regime_to_compat_macro_list(regime)
        hy_card = next(c for c in compat if c.get("series_id") == "hy_oas")
        self.assertEqual(hy_card["direction"], "bearish")


if __name__ == "__main__":
    unittest.main()
