"""technical-fear-v3: context features, descriptive phases and the outlook post-pass."""
from __future__ import annotations

import importlib.util
import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_technical_signals", SCRIPTS / "build_technical_signals.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def series(n=1000, drift=0.0004, amp=0.004, shock=None, seed_shift=0.0, start=date(2022, 1, 3)):
    rows = []
    close = 100.0
    for i in range(n):
        prior = close
        step = drift + amp * math.sin(i / 9.0 + seed_shift)
        if shock and i >= n - shock[0]:
            step = shock[1]
        close = prior * (1.0 + step)
        open_px = prior * (1.0 + 0.0004 * math.sin(i + seed_shift))
        rows.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "open": open_px,
            "high": max(open_px, close) * 1.006,
            "low": min(open_px, close) * 0.994,
            "close": close,
            "volume": 1_000_000.0 * (1.0 + 0.1 * math.sin(i / 5.0)),
        })
    return rows


class ContextFeatureTests(unittest.TestCase):
    def test_beta_tracks_a_levered_copy_of_the_benchmark(self):
        bench = series()
        stock = [dict(row) for row in bench]
        # stock returns = 2x benchmark returns
        close = 50.0
        for i, row in enumerate(stock):
            if i:
                r = bench[i]["close"] / bench[i - 1]["close"] - 1.0
                close *= 1.0 + 2.0 * r
            row.update(close=close, open=close, high=close * 1.004, low=close * 0.996)
        snap = MODULE.calculate_snapshot("LEV", stock, benchmark_rows=bench, benchmark="SPY", source="t")
        self.assertAlmostEqual(snap["context"]["beta_252d"], 2.0, delta=0.05)
        # a 2x copy has (almost) no company-specific move
        self.assertLess(abs(snap["context"]["company_move_20d_pct"]), 0.5)

    def test_company_specific_selloff_is_labelled(self):
        bench = series()
        stock = series(shock=(6, -0.07), seed_shift=1.3)
        snap = MODULE.calculate_snapshot("DROP", stock, benchmark_rows=bench, benchmark="SPY", source="t")
        self.assertEqual(snap["context"]["selloff_type"], "company_specific")
        if snap["capitulation"]["state"] in MODULE.PANIC_STATES:
            self.assertEqual(snap["setup"]["phase"], "company_selloff")
        self.assertNotIn(snap["setup"]["phase"], {"falling_knife", "stabilizing"})

    def test_market_driven_selloff_is_labelled(self):
        bench = series(shock=(6, -0.05))
        stock = [dict(row) for row in bench]
        snap = MODULE.calculate_snapshot("BETA1", stock, benchmark_rows=bench, benchmark="SPY", source="t")
        self.assertEqual(snap["context"]["selloff_type"], "market_driven")
        if snap["capitulation"]["state"] in MODULE.PANIC_STATES:
            self.assertEqual(snap["setup"]["phase"], "market_selloff")

    def test_spread_and_dollar_volume_are_estimated(self):
        snap = MODULE.calculate_snapshot("SPRD", series(), benchmark_rows=series(), benchmark="SPY", source="t")
        self.assertIsNotNone(snap["context"]["spread_estimate_pct"])
        self.assertGreaterEqual(snap["context"]["spread_estimate_pct"], 0.0)
        self.assertGreater(snap["context"]["dollar_volume_20d"], 0)

    def test_private_inputs_are_stripped(self):
        snap = MODULE.calculate_snapshot("PRIV", series(), benchmark_rows=series(), benchmark="SPY", source="t")
        self.assertIn("_model_inputs", snap)
        self.assertIn("_raw", snap["capitulation"])
        MODULE.strip_private(snap)
        self.assertNotIn("_model_inputs", snap)
        self.assertNotIn("_raw", snap["capitulation"])
        json.dumps(snap)  # publishable


class OutlookTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((SCRIPTS / "technical_model_v3.json").read_text(encoding="utf-8"))
        bench = series()
        self.current = {}
        for k in range(12):
            shock = (5, -0.05) if k % 3 == 0 else None
            rows = series(drift=0.0002 + 0.0001 * k, seed_shift=0.4 * k, shock=shock)
            self.current[f"S{k}"] = MODULE.calculate_snapshot(f"S{k}", rows, benchmark_rows=bench, benchmark="SPY", source="t")
        self.current["FOREIGN"] = MODULE.calculate_snapshot("FOREIGN", series(seed_shift=2.0), benchmark_rows=bench,
                                                            benchmark="XIC.TO", source="t")
        self.market = {"internal": {"scores": {"panic": 62.0}, "state": "stress_building"}}

    def test_config_has_every_feature_the_model_uses(self):
        reb = self.config["rebound21"]
        names = set(reb["transform"]["stock_features"]) | {"spy_panic", "spy_state", "breadth_panic",
                                                          "panic_x_spy", "idio20_x_spy", "panic_x_breadth"}
        self.assertEqual(set(reb["coef"]), names)
        self.assertEqual(set(self.config["vol21"]["coef"]), set(self.config["risk_features"]))
        self.assertEqual(set(self.config["drop15_63d"]["coef"]), set(self.config["risk_features"]))
        snap = next(iter(self.current.values()))
        for feature in reb["transform"]["stock_features"]:
            self.assertIn(feature, snap["_model_inputs"])

    def test_outlook_scores_risk_and_ranks_us_stocks(self):
        meta = MODULE.apply_outlook(self.current, self.market, self.config)
        self.assertEqual(meta["status"], "ready")
        self.assertEqual(meta["us_universe"], 12)
        scores = []
        for ticker, snap in self.current.items():
            risk = snap["outlook"]["risk"]
            self.assertGreater(risk["expected_vol_21d_pct"], 0)
            self.assertTrue(0.0 < risk["p_drop15_63d"] < 1.0)
            self.assertIn(risk["band"], {"low", "normal", "elevated", "high"})
            if ticker == "FOREIGN":
                self.assertNotIn("rebound", snap["outlook"])  # the rebound model is US-only
            else:
                scores.append(snap["outlook"]["rebound"]["score"])
        self.assertEqual(len(scores), 12)
        self.assertTrue(all(0 < s <= 100 for s in scores))
        self.assertAlmostEqual(max(scores), 100.0)
        self.assertIsNotNone(self.market["internal"]["breadth_panic"])

    def test_stale_snapshots_are_never_scored_or_ranked(self):
        self.current["S1"]["fetch_status"] = "preserved_after_fetch_failure"
        meta = MODULE.apply_outlook(self.current, self.market, self.config)
        self.assertNotIn("outlook", self.current["S1"])
        self.assertEqual(meta["us_universe"], 11)

    def test_missing_market_context_leaves_outlook_unavailable(self):
        meta = MODULE.apply_outlook(self.current, {"internal": None}, self.config)
        self.assertEqual(meta["status"], "unavailable")
        self.assertTrue(all("outlook" not in snap for snap in self.current.values()))

    def test_percentile_ranks_match_pandas_average_ties(self):
        ranks = MODULE._percentile_ranks([3.0, 1.0, None, 3.0, 2.0])
        # pandas: rank(pct=True) -> [0.875, 0.25, nan, 0.875, 0.5]
        self.assertEqual(ranks[2], None)
        self.assertAlmostEqual(ranks[0], 0.875 - 0.5)
        self.assertAlmostEqual(ranks[1], 0.25 - 0.5)
        self.assertAlmostEqual(ranks[4], 0.5 - 0.5)


if __name__ == "__main__":
    unittest.main()
