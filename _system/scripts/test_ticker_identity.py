#!/usr/bin/env python3
"""Tests for cross-exchange ticker identity filtering."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
import ticker_identity as ti  # noqa: E402
from portfolio_news_common import load_holding_configs, match_holding  # noqa: E402


MESOBLAST = (
    "Investment Review: Mesoblast Limited 4 In June, we covered our short "
    "position in Mesoblast Limited (ASX: MSB) after 12 long years at a very "
    "modest loss."
)
MESABI = "Mesabi Trust (NYSE: MSB) declares a quarterly distribution of $0.21."


class TickerIdentityTests(unittest.TestCase):
    def test_asx_msb_incompatible_with_us_book(self):
        self.assertFalse(
            ti.identity_match_ok(
                MESOBLAST,
                "MSB",
                company="Mesabi Trust",
                market="US",
                exchange="NYSE",
            )
        )

    def test_nyse_msb_compatible(self):
        self.assertTrue(
            ti.identity_match_ok(
                MESABI,
                "MSB",
                company="Mesabi Trust",
                market="US",
                exchange="NYSE",
            )
        )

    def test_asx_royalty_keeps_dotted_ticker(self):
        self.assertTrue(
            ti.identity_match_ok(
                "Deterra Royalties (ASX: DRR) lifts iron ore guidance",
                "DRR.AX",
                company="Deterra Royalties Limited",
                market="AU",
                exchange="ASX",
            )
        )

    def test_letter_matcher_rejects_mesoblast_for_msb(self):
        master = lm.SecurityMaster.from_dict(
            {
                "MSB": {
                    "name": "Mesabi Trust",
                    "market": "US",
                    "exchange": "NYSE",
                    "in_book": True,
                    "source": "book",
                    "entity_type": "equity",
                    "validation_status": "manual",
                }
            }
        )
        mentions = lm.emitted_mentions(lm.match_letter(MESOBLAST, master))
        self.assertFalse(any(m["ticker"] == "MSB" for m in mentions))

    def test_letter_matcher_keeps_mesabi(self):
        master = lm.SecurityMaster.from_dict(
            {
                "MSB": {
                    "name": "Mesabi Trust",
                    "market": "US",
                    "exchange": "NYSE",
                    "in_book": True,
                    "source": "book",
                    "entity_type": "equity",
                    "validation_status": "manual",
                }
            }
        )
        mentions = lm.emitted_mentions(lm.match_letter(MESABI, master))
        self.assertTrue(any(m["ticker"] == "MSB" for m in mentions))

    def test_news_matcher_rejects_mesoblast(self):
        configs = load_holding_configs()
        ticker, tier = match_holding(MESOBLAST, "", configs)
        self.assertIsNone(ticker)
        self.assertIsNone(tier)

    def test_news_matcher_keeps_mesabi(self):
        configs = load_holding_configs()
        ticker, tier = match_holding(MESABI, "", configs)
        self.assertEqual(ticker, "MSB")
        self.assertEqual(tier, "explicit")

    def test_registry_overlay_fills_us_market(self):
        master = lm.SecurityMaster.from_dict(
            {"MSB": {"name": "Mesabi Trust", "in_book": True, "source": "book"}},
            registry={
                "holdings": {
                    "MSB": {
                        "company": "Mesabi Trust",
                        "market": "US",
                        "exchange": "NYSE",
                    }
                }
            },
        )
        self.assertEqual(master.by_ticker["MSB"]["market"], "US")
        self.assertIsNone(master.resolve_symbol("MSB", exchange_token="ASX"))
        self.assertEqual(master.resolve_symbol("MSB", exchange_token="NYSE"), "MSB")


if __name__ == "__main__":
    unittest.main()
