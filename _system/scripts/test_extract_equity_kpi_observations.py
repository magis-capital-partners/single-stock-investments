#!/usr/bin/env python3
"""Tests for equity KPI observation extraction."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from extract_equity_kpi_observations import parse_metric_csv  # noqa: E402


class ParseMetricCsvTests(unittest.TestCase):
    def test_panel_halfyear_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "panel_halfyear.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["period_end", "revenue", "net_income"],
                )
                writer.writeheader()
                writer.writerow({"period_end": "2024-03-31", "revenue": "100", "net_income": "10"})
                writer.writerow({"period_end": "2024-09-30", "revenue": "120", "net_income": "12"})
            metrics = parse_metric_csv(path)
            self.assertIn("revenue", metrics)
            self.assertEqual(len(metrics["revenue"]), 2)
            self.assertEqual(metrics["revenue"][0]["period"], "2024-03-31")


if __name__ == "__main__":
    unittest.main()
