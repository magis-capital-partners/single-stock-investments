#!/usr/bin/env python3
"""Fixtures for the reusable feed row-age check."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import feed_row_staleness as stale  # noqa: E402

# 2026-10-23 is a Friday. Tuesday the 27th is two business days later.
FRIDAY = date(2026, 10, 23)
TUESDAY = date(2026, 10, 27)
WEDNESDAY = date(2026, 10, 28)
THURSDAY = date(2026, 10, 29)


def write_feed(directory: Path, *, newest: str, generated: str, envelope: str | None, rows_key: str = "feed", date_key: str = "report_date") -> Path:
    document = {
        "generated_at": generated,
        rows_key: [{date_key: newest, "ticker": "EX"}],
    }
    if envelope is not None:
        document["_envelope"] = {"generated_at": envelope, "health": {"status": "healthy"}}
    path = directory / "feed.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class BusinessDayTests(unittest.TestCase):
    def test_friday_to_tuesday_is_two_business_days(self) -> None:
        self.assertEqual(stale.business_days_between(FRIDAY, TUESDAY), 2)

    def test_friday_to_wednesday_is_three(self) -> None:
        self.assertEqual(stale.business_days_between(FRIDAY, WEDNESDAY), 3)

    def test_same_day_is_zero(self) -> None:
        self.assertEqual(stale.business_days_between(TUESDAY, TUESDAY), 0)


class FeedStalenessTests(unittest.TestCase):
    def test_exactly_two_business_days_is_healthy(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_feed(
                Path(tmp),
                newest="2026-10-23",
                generated="2026-10-27T13:55:22Z",
                envelope="2026-10-27T13:55:22Z",
            )
            result = stale.check_feed_row_staleness(path, 2, today=TUESDAY)
        self.assertEqual(result["health"], "healthy", result)
        self.assertEqual(result["business_days_vs_clock"], 2)
        self.assertEqual(result["business_days_vs_today"], 2)
        self.assertEqual(result["warnings"], [])

    def test_three_business_days_behind_the_build_clock_is_stale(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_feed(
                Path(tmp),
                newest="2026-10-23",
                generated="2026-10-28T13:00:00Z",
                envelope="2026-10-28T13:00:00Z",
            )
            result = stale.check_feed_row_staleness(path, 2, today=WEDNESDAY)
        self.assertEqual(result["health"], "stale")
        self.assertEqual(result["business_days_vs_clock"], 3)
        self.assertTrue(any("build clock" in warning for warning in result["warnings"]))

    def test_fresh_versus_the_clock_but_old_versus_today_is_stale(self) -> None:
        """The Oct 27 rebuild case: two business days behind the clock, four behind Thursday."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_feed(
                Path(tmp),
                newest="2026-10-23",
                generated="2026-10-27T13:55:22Z",
                envelope="2026-10-27T13:55:22Z",
            )
            result = stale.check_feed_row_staleness(path, 2, today=THURSDAY)
        self.assertEqual(result["health"], "stale")
        self.assertEqual(result["business_days_vs_clock"], 2)
        self.assertEqual(result["business_days_vs_today"], 4)
        self.assertTrue(any("today" in warning for warning in result["warnings"]))

    def test_envelope_clock_wins_over_the_top_level_stamp(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_feed(
                Path(tmp),
                newest="2026-10-27",
                generated="2026-10-01T00:00:00Z",
                envelope="2026-10-27T13:55:22Z",
            )
            result = stale.check_feed_row_staleness(path, 2, today=TUESDAY)
        self.assertEqual(result["health"], "healthy", result)
        self.assertEqual(result["clock_date"], "2026-10-27")

    def test_missing_envelope_falls_back_to_generated_at(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_feed(
                Path(tmp),
                newest="2026-10-23",
                generated="2026-10-28T00:00:00Z",
                envelope=None,
            )
            result = stale.check_feed_row_staleness(path, 2, today=WEDNESDAY)
        self.assertIsNone(result["envelope_generated_at"])
        self.assertEqual(result["health"], "stale")
        self.assertEqual(result["business_days_vs_clock"], 3)

    def test_another_feed_shape_uses_path_and_age_only(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_feed(
                Path(tmp),
                newest="2026-10-20",
                generated="2026-10-27T00:00:00Z",
                envelope="2026-10-27T00:00:00Z",
                rows_key="rows",
                date_key="filing_date",
            )
            result = stale.check_feed_row_staleness(
                path, 5, today=TUESDAY, rows_key="rows", date_key="filing_date"
            )
        self.assertEqual(result["newest_row_date"], "2026-10-20")
        self.assertEqual(result["health"], "healthy", result)
        self.assertEqual(result["max_business_days"], 5)

    def test_missing_file_is_unknown(self) -> None:
        result = stale.check_feed_row_staleness("/tmp/no-such-activist-feed.json", 2, today=THURSDAY)
        self.assertEqual(result["health"], "unknown")
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
