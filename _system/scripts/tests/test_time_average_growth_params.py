"""Canned FX conversion for the time-average parameter builder. No network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_time_average_growth import simple_returns, usd_series  # noqa: E402


class UsdConversionTest(unittest.TestCase):
    def test_a_flat_fx_rate_preserves_the_local_return(self):
        local = [("2026-01-02", 100.0), ("2026-01-05", 110.0)]
        fx = [("2026-01-02", 1.25), ("2026-01-05", 1.25)]
        usd = usd_series(local, fx)
        self.assertAlmostEqual(usd[0][1], 80.0)
        self.assertAlmostEqual(usd[1][1], 88.0)
        returns = simple_returns(usd)
        self.assertAlmostEqual(returns[0]["r"], 0.10)

    def test_a_moving_fx_rate_changes_the_dollar_return(self):
        local = [("2026-01-02", 100.0), ("2026-01-05", 110.0)]
        fx = [("2026-01-02", 1.25), ("2026-01-05", 1.10)]
        usd = usd_series(local, fx)
        self.assertAlmostEqual(usd[1][1], 100.0)
        self.assertAlmostEqual(simple_returns(usd)[0]["r"], 0.25)


if __name__ == "__main__":
    unittest.main()
