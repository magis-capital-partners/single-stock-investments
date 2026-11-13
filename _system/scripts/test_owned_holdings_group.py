#!/usr/bin/env python3
"""Owned holdings group: tracking membership, not a research stance."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_valuation_universe_tiers as tiers
import sync_portfolio_from_registry as sync
from portfolio_registry import (
    load_registry,
    owned_long_tickers,
    stamp_owned_tracking_groups,
    validate_owned_group,
)
from power_zone_router import _priority_holding

# Long equities from the 2026-11-13 broker snapshot. Broker symbols that
# already have a registry folder stay on that folder.
EXPECTED_LONGS = [
    "0700.HK",
    "AMZN",
    "BN",
    "CBOE",
    "CPRT",
    "CSGP",
    "CSU",
    "GOOGL",
    "GYRO",
    "HE",
    "HGBL",
    "MBGL",
    "MIAX",
    "MSFT",
    "NVDA",
    "OTCM",
    "PURR",
    "QDEL",
    "RGLD",
    "RMV.L",
    "SEVN",
    "SNOW",
    "SPGI",
    "STHO",
    "TIPT",
    "WHK",
]
EXPECTED_ALIASES = {"RMVEY": "RMV.L", "TCEHY": "0700.HK", "CNSWF": "CSU"}
EXPECTED_HEDGES = {
    "AAQZ",
    "AMZO",
    "AXTQ",
    "CBRZ",
    "CORD",
    "MSTZ",
    "NBIZ",
    "SNDQ",
    "SOXS",
    "SPXU",
    "SQQQ",
    "SSPC",
    "TSLQ",
}


def _group(members, **extra):
    base = {
        "schema": "owned_holdings_group_v1",
        "as_of": "2026-11-13",
        "accounts": {
            "client_sma_a_traditional": {"label": "Client SMA A, Traditional IRA"},
        },
        "members": members,
        "symbol_aliases": {},
        "short_hedges": [],
    }
    base.update(extra)
    return {"holdings": {ticker: {"classification": {"stance": "watch"}} for ticker in members}, "groups": {"owned": base}}


class OwnedGroupSchemaTests(unittest.TestCase):
    def test_priority_flag_does_not_replace_stance(self):
        self.assertTrue(_priority_holding({"classification": {"stance": "hold"}}))
        self.assertTrue(
            _priority_holding({"classification": {"stance": "watch"}, "tracking_groups": ["owned"]})
        )
        self.assertFalse(_priority_holding({"classification": {"stance": "watch"}}))

    def test_size_and_private_name_are_rejected(self):
        reg = _group({"RGLD": {"role": "long", "accounts": ["client_sma_a_traditional"], "shares": 200}})
        stamp_owned_tracking_groups(reg)
        errors = validate_owned_group(reg)
        self.assertTrue(any("shares" in error for error in errors))

    def test_short_hedge_cannot_be_a_holding(self):
        reg = _group({"RGLD": {"role": "long", "accounts": ["client_sma_a_traditional"]}})
        reg["groups"]["owned"]["short_hedges"] = [
            {"account": "client_sma_a_traditional", "broker_symbol": "TSLQ", "role": "short_hedge", "onboard": False}
        ]
        stamp_owned_tracking_groups(reg)
        self.assertEqual(validate_owned_group(reg), [])
        reg["holdings"]["TSLQ"] = {"classification": {"stance": "watch"}}
        errors = validate_owned_group(reg)
        self.assertTrue(any("TSLQ" in error for error in errors))

    def test_owned_long_is_tier_two_and_not_a_paper_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = {
                "holdings": {
                    "OWNED": {"classification": {"stance": "watch"}, "tracking_groups": ["owned"]},
                    "STANCE": {"classification": {"stance": "hold"}},
                    "PLAIN": {"classification": {"stance": "watch"}},
                },
                "watchlist": {},
                "groups": {
                    "owned": {
                        "schema": "owned_holdings_group_v1",
                        "members": {"OWNED": {"role": "long", "accounts": ["client_sma_a_traditional"]}},
                    }
                },
            }
            path = root / "_system/portfolio/registry.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(registry), encoding="utf-8")
            policy = json.loads((tiers.ROOT / tiers.POLICY_REL).read_text(encoding="utf-8"))
            (root / "_system/portfolio/valuation_universe_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            manifest = tiers.build("2026-11-13", root)
            self.assertEqual(manifest["assignments"]["OWNED"]["tier"], 2)
            reasons = {row["code"] for row in manifest["assignments"]["OWNED"]["assignment_reasons"]}
            self.assertIn("owned_long", reasons)
            self.assertNotIn("positive_paper_position", reasons)
            self.assertEqual(manifest["assignments"]["STANCE"]["tier"], 2)
            self.assertEqual(manifest["assignments"]["PLAIN"]["tier"], 3)
            self.assertFalse(manifest["assignments"]["OWNED"]["workflow_policy"].get("committee_auto_start"))


class PublishedOwnedBookTests(unittest.TestCase):
    def test_live_book_matches_the_nov_13_snapshot(self):
        reg = load_registry()
        self.assertEqual(validate_owned_group(reg), [])
        self.assertEqual(owned_long_tickers(reg), EXPECTED_LONGS)
        group = reg["groups"]["owned"]
        self.assertEqual(group["symbol_aliases"], EXPECTED_ALIASES)
        hedges = {row["broker_symbol"] for row in group["short_hedges"]}
        self.assertEqual(hedges, EXPECTED_HEDGES)
        self.assertEqual(reg["holdings"]["RGLD"]["classification"]["stance"], "watch")
        self.assertEqual(reg["holdings"]["CSU"]["classification"]["stance"], "core")
        self.assertEqual(reg["holdings"]["AMZN"]["classification"]["stance"], "hold")
        self.assertIn("owned", reg["holdings"]["NVDA"]["tracking_groups"])
        self.assertNotIn("owned", reg["holdings"]["APLD"].get("tracking_groups") or [])
        text = "\n".join(sync.owned_section_lines(reg))
        self.assertIn("Client SMA A, Traditional IRA", text)
        self.assertIn("Client SMA A, Roth IRA", text)
        self.assertIn("individual (owner TBD)", text)
        for symbol in EXPECTED_HEDGES:
            self.assertNotIn(symbol, reg["holdings"])


if __name__ == "__main__":
    unittest.main()
