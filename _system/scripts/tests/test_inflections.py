"""Offline contracts for the company-first Inflections projection."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_inflections as builder
from kpi_signal_enhancements import earnings_revision_signal
from build_kpi_trends import enrich_analysis

TODAY = date(2026, 11, 10)


def metric(name="revenues", **extra):
    return {"metric": name, "source": "sec_fundamentals", "tier": "primary", "direction": "accelerating", "signal_tier": "confirmed", "display": True, "material": True, "latest_period": "2026-09-30", "growth_prior": .1, "growth_latest": .2, **extra}


def source(metrics, **extra):
    return {"generated_at": "2026-11-09T00:00:00Z", "coverage": {"stale_max_days": 200}, "by_ticker": {"ABC": {"metrics": metrics}}, **extra}


def project(metrics, previous=None, **kwargs):
    return builder.build_assets(source(metrics), [{"ticker": "ABC", "company": "Example"}], previous, as_of=kwargs.get("as_of", TODAY))


class InflectionsTests(unittest.TestCase):
    def test_one_company_per_tracked_ticker_and_no_cached_strays(self):
        payload = source([metric()])
        payload["by_ticker"]["UNTRACKED"] = {"metrics": [metric()]}
        overview, signals, buckets, _ = builder.build_assets(payload, [{"ticker": "ABC", "company": "Example", "in_holdings": True, "position": 100}], as_of=TODAY)
        self.assertEqual([c["ticker"] for c in overview["companies"]], ["ABC"])
        self.assertEqual(len(buckets), 32)
        self.assertNotIn("in_holdings", overview["companies"][0])
        self.assertNotIn("position", json.dumps(overview))
        self.assertEqual(signals["signals"][0]["ticker"], "ABC")

    def test_unknown_reporting_period_cannot_support_headline(self):
        m = metric(latest_period=None)
        overview, index, _, _ = project([m])
        self.assertEqual(overview["companies"][0]["signals"], [])
        self.assertIn("period_unavailable", index["signals"][0]["reasons"])

    def test_stale_artifact_proxy_and_suppressed_metrics_stay_out_of_overview(self):
        overview, index, _, _ = project([metric(stale=True), metric("cfo", artifact=True), metric("operating_income", display=False), metric(revenue_proxy=True)])
        self.assertEqual(overview["companies"][0]["signals"], [])
        self.assertEqual(len(index["signals"]), 4)
        self.assertIn("revenue_proxy", index["signals"][-1]["reasons"])

    def test_viewing_date_recomputes_age_and_rejects_future_periods(self):
        signal = builder.normalize_metric("ABC", metric(latest_period="2026-03-31"), 0, 200)
        self.assertFalse(builder.eligible(signal, TODAY))
        self.assertTrue(builder.eligible(signal, date(2026, 4, 1)))
        self.assertFalse(builder.eligible(signal, date(2026, 3, 1)))

    def test_mixed_evidence_is_not_averaged_away(self):
        metrics = [metric(), metric("cfo", direction="decelerating")]
        signals = [builder.normalize_metric("ABC", m, i, 200) for i, m in enumerate(metrics)]
        direction, active = builder.assess(signals, TODAY, "2026-09-30")
        self.assertEqual(direction, "mixed")
        self.assertEqual(len(active), 2)

    def test_composite_and_same_direction_components_count_once(self):
        metrics = [metric("core_business", composite=True, composite_members=["operating_income", "cfo"]), metric("operating_income"), metric("cfo")]
        signals = [builder.normalize_metric("ABC", m, i, 200) for i, m in enumerate(metrics)]
        direction, active = builder.assess(signals, TODAY, "2026-09-30")
        self.assertEqual(direction, "improving")
        self.assertEqual(len(active), 1)
        self.assertNotIn("Prior YoY", active[0]["comparison"])

    def test_peer_and_surprise_context_does_not_change_company_direction(self):
        overview, index, _, _ = project([metric(), metric("revenues.peer_relative", signal_type="peer_relative", source="peer_relative", direction="downshift", peer_median=.3), metric("eps_revision", source="earnings_revision", signal_type="estimate_revision", direction="decelerating")])
        self.assertEqual(len(overview["companies"][0]["signals"]), 1)
        self.assertEqual([s["kind"] for s in index["signals"]], ["business", "peers", "expectations"])
        self.assertNotIn("→", index["signals"][1]["summary"])
        self.assertIn("reported earnings surprises", index["signals"][2]["comparison"])

    def test_zero_peer_median_is_preserved(self):
        normalized = builder.normalize_metric("ABC", metric("revenues.peer_relative", signal_type="peer_relative", peer_median=0), 0, 200)
        self.assertIn("peer median +0.0%", normalized["summary"])

    def test_operating_units_do_not_borrow_quarterly_support(self):
        normalized = builder.normalize_metric("ABC", metric("market_share", source="issuer_operating", tier="operating", mode="level", unit="share_pct", yoy_basis="percentage_points", level_latest=6, growth_latest=-.5), 0, 200)
        self.assertEqual(normalized["support"], "observation")
        self.assertFalse(normalized["candidate"])
        self.assertIn("6.00%", normalized["summary"])
        self.assertIn("-0.50 percentage points", normalized["comparison"])

    def test_loss_narrowing_and_inverse_polarity(self):
        m = metric("eps_basic", level_prior=-3.77, level_latest=-1.36)
        normalized = builder.normalize_metric("ABC", m, 0, 200)
        self.assertIn("Loss narrowed", normalized["summary"])
        self.assertIn("remains negative", normalized["summary"])
        burn = builder.normalize_metric("ABC", metric("burn_rate"), 0, 200)
        self.assertEqual(burn["effect"], "weakening")

    def test_sign_changes_are_excluded_even_if_source_missed_artifact(self):
        m = metric("net_income", level_prior=-1, level_latest=2)
        normalized = builder.normalize_metric("ABC", m, 0, 200)
        self.assertIn("turned positive", normalized["summary"])
        self.assertIn("volatile_base", normalized["reasons"])
        self.assertFalse(builder.eligible(normalized, TODAY))

    def test_smoothed_direction_disagreement_is_explained(self):
        normalized = builder.normalize_metric("ABC", metric(growth_prior=.3, growth_latest=.2), 0, 200)
        self.assertIn("Smoothed", normalized["summary"])
        self.assertIn("different directions", normalized["comparison"])

    def test_margin_levels_and_percentage_points_are_not_growth_rates(self):
        normalized = builder.normalize_metric("ABC", metric("op_margin", level_prior=.2, level_latest=.25), 0, 200)
        self.assertIn("25.0%", normalized["summary"])
        self.assertIn("+5.0 percentage points", normalized["comparison"])

    def test_confirmation_basis_is_explicit_and_never_invented_for_legacy_metrics(self):
        legacy = builder.normalize_metric("ABC", metric(), 0, 200)
        self.assertEqual(legacy["support_basis"], "unspecified")
        trailing = builder.normalize_metric("ABC", metric(confirmation_basis="trailing_year"), 0, 200)
        self.assertEqual(trailing["support_basis"], "trailing_year")
        regime = builder.normalize_metric("ABC", metric(signal_type="regime"), 0, 200)
        self.assertEqual(regime["support_basis"], "two_quarters")

    def test_engine_distinguishes_persistence_from_trailing_year_confirmation(self):
        analysis = {"direction": "accelerating", "threshold": .05, "accel": .1, "growth_latest": .2, "growth_prior": .1, "basis": "yoy"}
        trailing = enrich_analysis(analysis, metric_key="revenues", raw_accels=[0, .1], ttm_analysis={"direction": "accelerating"})
        self.assertEqual(trailing["signal_tier"], "confirmed")
        self.assertEqual(trailing["confirmation_basis"], "trailing_year")
        persistent = enrich_analysis(analysis, metric_key="revenues", raw_accels=[.1, .1])
        self.assertEqual(persistent["confirmation_basis"], "two_quarters")

    def test_initial_baseline_and_identical_rebuild_never_create_new_labels(self):
        overview, _, _, history = project([metric()])
        rebuilt, _, _, next_history = project([metric()], history)
        self.assertIsNone(overview["companies"][0]["change"])
        self.assertEqual(overview, rebuilt)
        self.assertEqual(history, next_history)

    def test_new_report_creates_change_but_timestamp_alone_does_not(self):
        _, _, _, history = project([metric()])
        data = source([metric()])
        data["generated_at"] = "2026-11-10T00:00:00Z"
        unchanged, _, _, _ = builder.build_assets(data, [{"ticker": "ABC"}], history, as_of=TODAY)
        self.assertIsNone(unchanged["companies"][0]["change"])
        changed, _, _, _ = project([metric(growth_latest=.3)], history)
        self.assertEqual(changed["companies"][0]["change"]["kind"], "changed")

    def test_newly_tracked_company_is_new_only_after_baseline_exists(self):
        _, _, _, history = project([metric()])
        data = source([metric()])
        data["by_ticker"]["NEW"] = {"metrics": [metric()]}
        overview, _, _, _ = builder.build_assets(data, [{"ticker": "ABC"}, {"ticker": "NEW"}], history, as_of=TODAY)
        self.assertEqual(overview["companies"][1]["change"]["kind"], "new")

    def test_aging_or_missing_coverage_is_not_resolution(self):
        _, _, _, history = project([metric()])
        later, _, _, _ = project([metric()], history, as_of=date(2027, 8, 1))
        self.assertIsNone(later["companies"][0]["change"])
        missing, _, _, _ = project([], history)
        self.assertIsNone(missing["companies"][0]["change"])

    def test_resolved_requires_a_new_report_without_a_qualifying_change(self):
        _, _, _, history = project([metric(latest_period="2026-06-30")])
        overview, _, _, _ = project([metric(direction="steady", signal_tier="steady", display=False)], history)
        self.assertEqual(overview["companies"][0]["change"]["kind"], "resolved")

    def test_older_or_missing_snapshot_fails_closed(self):
        _, _, _, history = project([metric()])
        with self.assertRaises(ValueError):
            builder.build_assets({"generated_at": "2020-01-01", "by_ticker": {"ABC": {"metrics": []}}}, [{"ticker": "ABC"}], history, as_of=TODAY)
        with self.assertRaises(ValueError):
            builder.build_assets({}, [{"ticker": "ABC"}], as_of=TODAY)
        with self.assertRaises(ValueError):
            builder.build_assets(source([metric()]), [], as_of=TODAY)
        history["source_generated_at"] = "2026-11-09T17:00:00Z"
        with self.assertRaises(ValueError):
            builder.build_assets(source([metric()]), [{"ticker": "ABC"}], history, as_of=TODAY)

    def test_evidence_and_index_share_the_overview_snapshot_and_preserve_points(self):
        m = metric(points=[{"period": "2026-09-30", "value": 12}])
        overview, index, buckets, _ = project([m])
        self.assertNotIn("points", json.dumps(overview))
        self.assertNotIn("points", json.dumps(index))
        bucket = next(doc for doc in buckets.values() if doc["by_ticker"])
        self.assertEqual(bucket["snapshot_id"], overview["snapshot_id"])
        self.assertEqual(bucket["by_ticker"]["ABC"][0]["raw"]["points"], m["points"])
        before = copy.deepcopy(m)
        project([m])
        self.assertEqual(m, before)

    def test_earnings_surprises_keep_dates_and_never_claim_forward_revisions(self):
        result = earnings_revision_signal([{"date": "2026-06-01", "reported": True, "actual_eps": 1, "estimated_eps": 1}, {"date": "2026-09-01", "reported": True, "actual_eps": 1.2, "estimated_eps": 1}])
        self.assertEqual(result["latest_period"], "2026-09-01")
        self.assertEqual(result["prior_period"], "2026-06-01")
        self.assertNotIn("revision", result["label"].lower())

    def test_writes_are_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            builder.write_inflection_assets(source([metric()]), [{"ticker": "ABC"}], root, as_of=TODAY)
            path = root / "inflection_overview.json"
            stamp = path.stat().st_mtime_ns
            builder.write_inflection_assets(source([metric()]), [{"ticker": "ABC"}], root, as_of=TODAY)
            self.assertEqual(path.stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
