#!/usr/bin/env python3
"""Synthetic cases for the daily volume residual. No network."""

from __future__ import annotations

import math
import random
import statistics
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import volume_residual as vr  # noqa: E402


def rows_from(returns, volumes, start=date(2018, 1, 1)):
    price = 100.0
    out = []
    for index, (ret, volume) in enumerate(zip(returns, volumes)):
        price *= math.exp(ret)
        out.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "adj_close": price,
                "volume": volume,
            }
        )
    return out


class SyntheticCases(unittest.TestCase):
    def test_constant_volume_gap_is_near_zero(self):
        rng = random.Random(7)
        returns = [rng.gauss(0, 0.01) for _ in range(400)]
        volumes = [1_000_000] * 400
        point = vr.series(rows_from(returns, volumes))[-1]
        self.assertIsNone(point["withheld_reason"])
        self.assertIsNotNone(point["gap"])
        self.assertLess(abs(point["gap"]), 1e-4)

    def test_busy_days_keep_the_absolute_gap_inside_calendar_vol(self):
        rng = random.Random(3)
        returns = []
        volumes = []
        for index in range(500):
            if index % 5 == 4:
                volumes.append(200)
                returns.append(rng.gauss(0, 0.02))
            else:
                volumes.append(20)
                returns.append(0.0)
        point = vr.series(rows_from(returns, volumes))[-1]
        self.assertIsNone(point["withheld_reason"], point["withheld_reason"])
        self.assertGreater(point["calendar_vol"], 0)
        self.assertGreater(point["volume_time_vol"], 0)
        self.assertLess(abs(point["gap"]), point["calendar_vol"])

    def test_alternating_size_unrelated_to_volume_leaves_a_gap(self):
        rng = random.Random(11)
        returns = []
        volumes = []
        for index in range(500):
            if index % 2 == 0:
                volumes.append(10.0)
                returns.append(rng.gauss(0, 0.02))
            else:
                volumes.append(100.0)
                returns.append(rng.gauss(0, 0.001))
        point = vr.series(rows_from(returns, volumes))[-1]
        self.assertIsNone(point["withheld_reason"], point["withheld_reason"])
        self.assertGreater(abs(point["gap"]), 0.5)

    def test_oversized_day_is_one_bucket(self):
        returns = [0.001] * 280
        volumes = [100.0] * 280
        volumes[-1] = 500.0
        buckets = vr.equal_volume_buckets(rows_from(returns, volumes))
        oversized = [bucket for bucket in buckets if bucket["accumulated"] >= 500]
        self.assertEqual(len(oversized), 1)
        self.assertEqual(oversized[0]["sessions"], 1)
        self.assertTrue(oversized[0]["oversized"])
        self.assertTrue(all(bucket["sessions"] >= 1 for bucket in buckets))

    def test_quota_ignores_volume_appended_later(self):
        base = rows_from([0.001] * 300, [100.0] * 300)
        first = vr.equal_volume_buckets(base)[0]["quota"]
        extra = rows_from([0.001] * 40, [50_000_000.0] * 40, start=date(2019, 6, 1))
        again = vr.equal_volume_buckets(base + extra)[0]["quota"]
        self.assertEqual(first, 100.0)
        self.assertEqual(again, first)


class WithholdTests(unittest.TestCase):
    def test_fewer_than_20_buckets_withholds_the_gap_and_keeps_calendar(self):
        point = vr.series(rows_from([0.001] * 262, [100.0] * 262))[-1]
        # 252 sessions freeze the quota, then only the remaining sessions can close buckets.
        self.assertLess(point["buckets_in_window"], 20)
        self.assertEqual(point["withheld_reason"], vr.WITHHOLD_BUCKETS)
        self.assertIsNotNone(point["calendar_vol"])
        self.assertIsNone(point["gap"])
        self.assertIsNone(point["volume_time_vol"])

    def test_too_many_oversized_buckets_withhold_the_gap(self):
        returns = [0.001] * 320
        volumes = [100.0] * 252 + [400.0] * 30
        point = vr.series(rows_from(returns, volumes))[-1]
        self.assertEqual(point["withheld_reason"], vr.WITHHOLD_OVERSIZE)
        self.assertIsNotNone(point["calendar_vol"])
        self.assertIsNone(point["gap"])
        self.assertGreater(point["oversized_share"], 0.20)

    def test_missing_volume_does_not_emit_a_bucket(self):
        returns = [0.0] * 320
        volumes = [100.0] * 320
        hole = 300
        volumes[hole] = None
        built = rows_from(returns, volumes)
        built[hole]["volume"] = None
        buckets = vr.equal_volume_buckets(built)
        self.assertNotIn(built[hole]["date"], {bucket["end_date"] for bucket in buckets})
        without = [row for index, row in enumerate(built) if index != hole]
        self.assertEqual(len(buckets), len(vr.equal_volume_buckets(without)))

    def test_missing_volume_share_withholds(self):
        returns = [0.001] * 400
        volumes = [100.0] * 400
        for index in range(200, 220):
            volumes[index] = None
        point = vr.latest_point(rows_from(returns, volumes))
        self.assertEqual(point["withheld_reason"], vr.WITHHOLD_MISSING)
        self.assertIsNone(point["gap"])


class CalendarTests(unittest.TestCase):
    def test_calendar_vol_uses_20_returns_and_sqrt_252(self):
        rng = random.Random(5)
        returns = [rng.gauss(0, 0.01) for _ in range(80)]
        built = rows_from(returns, [1_000_000.0] * 80)
        point = vr.series(built)[-1]
        last = [math.log(built[index]["adj_close"] / built[index - 1]["adj_close"]) for index in range(60, 80)]
        expected = statistics.stdev(last) * math.sqrt(252) * 100.0
        self.assertAlmostEqual(point["calendar_vol"], expected, places=4)

    def test_caption_names_daily_bars_and_refuses_a_forecast(self):
        document = vr.market_document(rows_from([0.001] * 40, [100.0] * 40))
        caption = document["caption"]
        self.assertIn("daily bars", caption.lower())
        self.assertIn("not a forecast", caption)
        self.assertNotIn("tick data shows", caption)
        self.assertTrue(document["research_only"])
        self.assertFalse(document["in_base_irr"])
        self.assertEqual(document["authority"], "none")
        self.assertTrue(document["latest"]["research_only"])


if __name__ == "__main__":
    unittest.main()
