"""Error-diagram arithmetic. No price history and no optimizer."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from criticality.error_diagram import (  # noqa: E402
    evaluate,
    is_positive_alarm,
    select_threshold,
    window_dates,
)


def sample(day, positive, concentration=80, status="ready"):
    return {
        "date": day,
        "positive": positive,
        "negative": 0,
        "status": status,
        "concentration": concentration,
    }


class ErrorDiagramTest(unittest.TestCase):
    def test_window_excludes_the_peak_session(self):
        calendar = [f"2020-01-{day:02d}" for day in range(1, 21)]
        window = window_dates(calendar, "2020-01-20", 5)
        self.assertEqual(window, [f"2020-01-{day:02d}" for day in range(15, 20)])

    def test_alarm_requires_confidence_and_concentration(self):
        self.assertTrue(is_positive_alarm(sample("2020-01-02", 30), 20))
        self.assertFalse(is_positive_alarm(sample("2020-01-02", 30, concentration=10), 20))
        self.assertFalse(is_positive_alarm(sample("2020-01-02", 10), 20))
        self.assertFalse(is_positive_alarm(sample("2020-01-02", 40, status="failed"), 20))

    def test_threshold_that_catches_crashes_and_stays_quiet_is_enabled(self):
        calendar = [f"d{index:02d}" for index in range(30)]
        samples = [sample(day, 0) for day in calendar]
        samples[8]["positive"] = 50
        samples[18]["positive"] = 50
        events = (
            {"id": "a", "kind": "crash", "peak_date": "d10", "label": "a"},
            {"id": "b", "kind": "crash", "peak_date": "d12", "label": "b"},
            {"id": "c", "kind": "crash", "peak_date": "d14", "label": "c"},
            {"id": "d", "kind": "crash", "peak_date": "d20", "label": "d"},
            {"id": "e", "kind": "crash", "peak_date": "d22", "label": "e"},
            {"id": "calm", "kind": "calm", "peak_date": "d28", "label": "calm"},
        )
        diagram = evaluate(
            samples,
            events,
            calendar,
            thresholds=(20,),
            lead_sessions=5,
            calm_sessions=5,
        )
        row = diagram["curve"][0]
        self.assertEqual(row["crashes_tested"], 5)
        self.assertEqual(row["crashes_caught"], 4)
        self.assertEqual(row["calm_false_alarms"], 0)
        self.assertLessEqual(row["time_in_alarm"], 0.25)
        self.assertTrue(diagram["selection"]["demotion_enabled"])
        self.assertEqual(diagram["selection"]["confidence_threshold"], 20)

    def test_no_separating_threshold_leaves_demotion_off(self):
        curve = [{
            "threshold": 20,
            "time_in_alarm": 0.8,
            "miss_rate": 0.1,
            "crashes_tested": 8,
            "crashes_caught": 7,
        }]
        selection = select_threshold(curve)
        self.assertFalse(selection["demotion_enabled"])
        self.assertIsNone(selection["confidence_threshold"])

    def test_tie_takes_the_higher_threshold(self):
        curve = [
            {"threshold": 10, "time_in_alarm": 0.1, "miss_rate": 0.2, "crashes_tested": 6, "crashes_caught": 5},
            {"threshold": 30, "time_in_alarm": 0.1, "miss_rate": 0.2, "crashes_tested": 6, "crashes_caught": 5},
        ]
        selection = select_threshold(curve)
        self.assertTrue(selection["demotion_enabled"])
        self.assertEqual(selection["confidence_threshold"], 30)


if __name__ == "__main__":
    unittest.main()
