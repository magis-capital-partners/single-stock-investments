#!/usr/bin/env python3
"""Unit tests for advantaged banks screener (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_advantaged_banks_screener as mod


class AdvantagedBanksScreenerTests(unittest.TestCase):
    def test_load_seed_uppercases_and_dedupes(self):
        csv_text = (
            "ticker,company,market,cap_tier,edge_type,notes\n"
            "tbbk,The Bancorp,US,small,baas_fintech,note a\n"
            "TBBK,Dup,US,small,baas_fintech,dup\n"
            "MCHB,Mechanics,US,micro,low_cost_deposits,cheap\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.csv"
            path.write_text(csv_text, encoding="utf-8")
            with mock.patch.object(mod, "SEED_PATH", path):
                rows = mod.load_seed_rows()
        self.assertEqual([r["ticker"] for r in rows], ["TBBK", "MCHB"])
        self.assertEqual(rows[0]["edge_type"], "baas_fintech")
        self.assertEqual(rows[0]["edge_label"], "BaaS / fintech")
        self.assertEqual(rows[1]["edge_type"], "low_cost_deposits")

    def test_compute_bank_metrics_math(self):
        sec = {
            "deposits_total_usd": 1_000_000_000,
            "deposits_noninterest_usd": 400_000_000,
            "interest_expense_deposits_usd": 10_000_000,
            "equity_usd": 200_000_000,
            "tangible_equity_usd": 180_000_000,
            "net_income_usd": 40_000_000,
            "shares_outstanding": 20_000_000,
        }
        metrics = mod.compute_bank_metrics(sec, price=18.0, mcap=360_000_000)
        self.assertEqual(metrics["dda_share_pct"], 40.0)
        self.assertEqual(metrics["cost_of_deposits_pct"], 1.0)
        self.assertEqual(metrics["tbv_per_share_usd"], 9.0)
        self.assertEqual(metrics["p_tbv"], 2.0)
        self.assertEqual(metrics["roe_pct"], 20.0)
        self.assertTrue(metrics["is_low_cost"])

    def test_is_low_cost_boundaries(self):
        # Cost just under threshold
        m1 = mod.compute_bank_metrics(
            {
                "deposits_total_usd": 100,
                "deposits_noninterest_usd": 10,
                "interest_expense_deposits_usd": 1.49,
                "equity_usd": 50,
                "tangible_equity_usd": 50,
                "net_income_usd": 5,
                "shares_outstanding": 10,
            },
            price=5.0,
            mcap=50,
        )
        self.assertTrue(m1["is_low_cost"])

        # High cost, high DDA still flags
        m2 = mod.compute_bank_metrics(
            {
                "deposits_total_usd": 100,
                "deposits_noninterest_usd": 35,
                "interest_expense_deposits_usd": 3.0,
                "equity_usd": 50,
                "tangible_equity_usd": 50,
                "net_income_usd": 5,
                "shares_outstanding": 10,
            },
            price=5.0,
            mcap=50,
        )
        self.assertTrue(m2["is_low_cost"])
        self.assertEqual(m2["dda_share_pct"], 35.0)

        # Neither flag
        m3 = mod.compute_bank_metrics(
            {
                "deposits_total_usd": 100,
                "deposits_noninterest_usd": 20,
                "interest_expense_deposits_usd": 2.5,
                "equity_usd": 50,
                "tangible_equity_usd": 50,
                "net_income_usd": 5,
                "shares_outstanding": 10,
            },
            price=5.0,
            mcap=50,
        )
        self.assertFalse(m3["is_low_cost"])

    def test_sort_puts_low_cost_before_others_and_keeps_holdings(self):
        rows = [
            {
                "ticker": "HOLD",
                "in_holdings": True,
                "is_low_cost": True,
                "cost_of_deposits_pct": 0.5,
                "roe_pct": 30,
                "cap_bucket": "small",
            },
            {
                "ticker": "EXP",
                "in_holdings": False,
                "is_low_cost": False,
                "cost_of_deposits_pct": 2.5,
                "roe_pct": 15,
                "cap_bucket": "small",
            },
            {
                "ticker": "CHEAP",
                "in_holdings": False,
                "is_low_cost": True,
                "cost_of_deposits_pct": 0.8,
                "roe_pct": 12,
                "cap_bucket": "micro",
            },
            {
                "ticker": "CHEAP2",
                "in_holdings": False,
                "is_low_cost": True,
                "cost_of_deposits_pct": 0.4,
                "roe_pct": 10,
                "cap_bucket": "micro",
            },
        ]
        bucket_rank = {"micro": 0, "small": 1, "mid": 2, "large": 3}
        rows.sort(
            key=lambda r: (
                1 if r.get("in_holdings") else 0,
                0 if r.get("is_low_cost") else 1,
                r.get("cost_of_deposits_pct") if r.get("cost_of_deposits_pct") is not None else 999.0,
                -(r.get("roe_pct") or 0),
                bucket_rank.get(r.get("cap_bucket") or "", 9),
                r["ticker"],
            ),
        )
        self.assertEqual([r["ticker"] for r in rows], ["CHEAP2", "CHEAP", "EXP", "HOLD"])

    def test_payload_envelope_keys(self):
        fake_rows = [
            {
                "ticker": "TBBK",
                "company": "The Bancorp",
                "market": "US",
                "edge_type": "baas_fintech",
                "is_low_cost": True,
                "in_holdings": False,
                "in_watchlist": False,
            }
        ]
        payload = mod.build_payload(fake_rows)
        for key in ("built_at", "criteria", "seed_path", "row_count", "low_cost_count", "rows"):
            self.assertIn(key, payload)
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["low_cost_count"], 1)
        self.assertEqual(payload["rows"][0]["ticker"], "TBBK")


if __name__ == "__main__":
    unittest.main()
