#!/usr/bin/env python3
"""Tests for SEC fundamental series extraction."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_fundamental_series import extract_metric_series, series_for_tag  # noqa: E402


class TagSelectionTests(unittest.TestCase):
    def test_picks_latest_tag_not_first_stale_tag(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2020-07-31",
                                    "start": "2020-05-01",
                                    "val": 500.0,
                                    "form": "10-Q",
                                    "filed": "2020-09-01",
                                }
                            ]
                        }
                    },
                    "RevenueFromContractWithCustomerIncludingAssessedTax": {
                        "units": {
                            "USD": [
                                {
                                    "end": "2026-04-30",
                                    "start": "2026-02-01",
                                    "val": 1200.0,
                                    "form": "10-Q",
                                    "filed": "2026-05-29",
                                }
                            ]
                        }
                    },
                }
            }
        }
        series = extract_metric_series(facts, "revenues")
        self.assertEqual(series[-1]["period"], "2026-04-30")
        self.assertEqual(series[-1]["value"], 1200.0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
