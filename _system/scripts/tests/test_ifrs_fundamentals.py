"""IFRS companyfacts extraction. No network."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_fundamental_series import drop_discontinued_series, extract_metric_series  # noqa: E402


def _fact(start: str, end: str, val: float, form: str = "40-F", filed: str = "2026-03-01") -> dict:
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed, "fy": 2025, "fp": "FY"}


class IfrsExtractionTests(unittest.TestCase):
    def test_ifrs_filers_without_us_gaap_get_a_series(self) -> None:
        facts = {
            "facts": {
                "ifrs-full": {
                    "Revenue": {
                        "units": {
                            "USD": [
                                _fact("2025-01-01", "2025-03-31", 100.0, form="6-K", filed="2025-05-01"),
                                _fact("2025-04-01", "2025-06-30", 120.0, form="6-K", filed="2025-08-01"),
                            ]
                        }
                    }
                }
            }
        }
        series = extract_metric_series(facts, "revenues")
        self.assertEqual([row["period"] for row in series], ["2025-03-31", "2025-06-30"])
        self.assertEqual(series[-1]["value"], 120.0)
        self.assertEqual(series[-1]["taxonomy"], "ifrs-full")
        self.assertNotIn("currency", series[-1])

    def test_newer_ifrs_series_beats_a_stale_us_gaap_tag(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [_fact("2017-01-01", "2017-03-31", 1.0, form="40-F", filed="2018-03-01")]}}
                },
                "ifrs-full": {
                    "RevenueFromContractsWithCustomers": {
                        "units": {"USD": [_fact("2025-10-01", "2025-12-31", 50.0)]}
                    }
                },
            }
        }
        series = extract_metric_series(facts, "revenues")
        self.assertEqual(series[-1]["period"], "2025-12-31")
        self.assertEqual(series[-1]["value"], 50.0)

    def test_newer_us_gaap_still_wins(self) -> None:
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [_fact("2026-01-01", "2026-03-31", 9.0, form="10-Q", filed="2026-05-01")]}}
                },
                "ifrs-full": {
                    "Revenue": {"units": {"USD": [_fact("2024-01-01", "2024-12-31", 1.0)]}}
                },
            }
        }
        series = extract_metric_series(facts, "revenues")
        self.assertEqual(series[-1]["value"], 9.0)
        self.assertNotIn("taxonomy", series[-1])

    def test_ifrs_prefers_usd_over_cad(self) -> None:
        facts = {
            "facts": {
                "ifrs-full": {
                    "Revenue": {
                        "units": {
                            "CAD": [_fact("2025-01-01", "2025-03-31", 999.0, form="6-K", filed="2025-05-01"),
                                    _fact("2025-04-01", "2025-06-30", 999.0, form="6-K", filed="2025-08-01")],
                            "USD": [_fact("2025-01-01", "2025-03-31", 10.0, form="6-K", filed="2025-05-01"),
                                    _fact("2025-04-01", "2025-06-30", 12.0, form="6-K", filed="2025-08-01")],
                        }
                    }
                }
            }
        }
        series = extract_metric_series(facts, "revenues")
        self.assertEqual(series[-1]["value"], 12.0)
        self.assertNotIn("currency", series[-1])

    def test_cad_only_series_records_currency(self) -> None:
        facts = {
            "facts": {
                "ifrs-full": {
                    "CashAndCashEquivalents": {
                        "units": {
                            "CAD": [
                                {"end": "2025-12-31", "val": 80.0, "form": "40-F", "filed": "2026-03-01"},
                                {"end": "2024-12-31", "val": 70.0, "form": "40-F", "filed": "2025-03-01"},
                            ]
                        }
                    }
                }
            }
        }
        series = extract_metric_series(facts, "cash")
        self.assertEqual(series[-1]["currency"], "CAD")
        self.assertEqual(series[-1]["value"], 80.0)

    def test_discontinued_tag_is_dropped_and_a_recent_quarter_is_kept(self) -> None:
        metrics = {
            "cash": [{"period": "2025-12-31", "value": 1.0}],
            "revenues": [{"period": "2025-06-30", "value": 2.0}],
            "long_term_debt": [{"period": "2019-12-31", "value": 80.0}],
        }
        kept = drop_discontinued_series(metrics)
        self.assertNotIn("long_term_debt", kept)
        self.assertIn("revenues", kept)


if __name__ == "__main__":
    unittest.main()
