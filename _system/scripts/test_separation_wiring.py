"""Pipeline wiring for the separations register (proposal 2026-10-09).

One place to check that the lane, the feed, the rebuild profile, the shard
map, the downloader forms, the sentinel tags and the onboarding linkage all
point at the same names. An undeclared lane is invisible to the supervisor,
and a lane whose job name drifts from the workflow fails P3 (hard).
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_dashboard_shards as shards  # noqa: E402
import build_feed_status as feeds  # noqa: E402
import ci_rebuild_profile as profile  # noqa: E402
import download_us_investor_docs as downloader  # noqa: E402
import filing_sentinel_workflow as sentinel  # noqa: E402
import onboard_ticker as onboard  # noqa: E402

LANE = "data-pipeline-separation-discover"
JOB = "separation-discover"
WORKFLOW = ROOT / ".github/workflows/data-pipeline.yml"
GRAPH = json.loads((ROOT / "_system/graph/graph_sources.json").read_text(encoding="utf-8"))


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.text)

    def test_job_exists_with_the_per_job_concurrency_group(self):
        job = self.doc["jobs"][JOB]
        self.assertEqual(job["if"], "needs.decide.outputs.separation_discover == 'true'")
        self.assertEqual(job["concurrency"]["group"], "data-commit-main-separation-discover")
        self.assertFalse(job["concurrency"]["cancel-in-progress"])
        self.assertIn("decide", job["needs"] if isinstance(job["needs"], list) else [job["needs"]])
        self.assertIn(JOB, self.doc["jobs"]["pipeline-summary"]["needs"])

    def test_decide_selects_it_on_monday_and_on_heal_dispatch(self):
        self.assertIn("heal-separations", self.doc[True]["repository_dispatch"]["types"])
        self.assertIn("separation_discover", self.doc["jobs"]["decide"]["outputs"])
        run = self.doc["jobs"]["decide"]["steps"][0]["run"]
        self.assertRegex(run, r'"13 15 \* \* 1"\) cvr_discover=true; warrant_discover=true; separation_discover=true; reverse_splits=true; buyback_radar=true ;;')
        self.assertIn('"dispatch:heal-separations") separation_discover=true ;;', run)
        self.assertIn('echo "separation_discover=$separation_discover"', run)

    def test_steps_run_the_five_scripts_in_order_and_commit_the_register(self):
        steps = self.doc["jobs"][JOB]["steps"]
        runs = "\n".join(step.get("run", "") for step in steps)
        order = [
            "refresh_separation_universe.py", "build_separation_flows.py", "resolve_separation_outcomes.py",
            "build_separations_dashboard.py", "check_separation_universe.py --strict",
        ]
        positions = [runs.index(name) for name in order]
        self.assertEqual(positions, sorted(positions), runs)
        self.assertIn("--discover --discover-days 14 --discover-limit 25", " ".join(runs.split()))
        commit = next(step for step in steps if step.get("uses") == "./.github/actions/commit-main")
        self.assertEqual(commit["with"]["message"], "chore: separation weekly discovery $(date -u +%Y-%m-%d)")
        self.assertEqual(commit["with"]["git_add"].split(), ["_system/data/separations/", "dashboard/data/separations.json"])
        self.assertEqual(commit["if"], "always()")
        self.assertTrue(any("ci_checkout_workspace.sh minimal" in step.get("run", "") for step in steps))


class GraphAndFeedTests(unittest.TestCase):
    def lane(self) -> dict:
        return next(row for row in GRAPH["lanes"] if row["name"] == LANE)

    def test_lane_matches_the_workflow_job_name_exactly(self):
        lane = self.lane()
        self.assertEqual(lane["workflow_file"], "data-pipeline.yml")
        self.assertEqual(lane["job"], JOB)
        self.assertIn(JOB, yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"])
        self.assertEqual(lane["cadence_cron"], ["13 15 * * 1"])
        self.assertEqual(lane["freshness_hours"], 342)
        self.assertTrue(re.match(lane["subject_regex"], "chore: separation weekly discovery 2026-10-13"))

    def test_feed_is_declared_with_health_assertions(self):
        feed = GRAPH["data_feeds"]["separations"]
        self.assertEqual(feed["path"], "dashboard/data/separations.json")
        self.assertEqual(feed["stamp_field"], "generated_at")
        self.assertEqual(feed["max_age_hours"], 100)
        self.assertIn("build_separations_dashboard.py", feed["healer"])
        self.assertEqual(feed["assert_fields"]["health.status"]["not_in"], ["unhealthy"])
        self.assertEqual(feed["assert_fields"]["health.structural_errors"]["max_count"], 0)

    def test_feed_status_surface_and_shard_map_point_at_the_feed(self):
        surface = next(row for row in feeds.surface_specs() if row["id"] == "separations")
        self.assertEqual(surface["data_feed"], "separations")
        self.assertEqual(surface["lane"], LANE)
        self.assertEqual(surface["hash"], "#/ideas/situations/split-offs")
        self.assertEqual(surface["kind"], "file")
        self.assertEqual(feeds.FEED_LANES["separations"], LANE)
        core = shards.build_core({"tickers": []}) if hasattr(shards, "build_core") else None
        if core is not None:
            self.assertEqual(core["shards"]["separations"], "data/separations.json")
        source = (SCRIPTS / "build_dashboard_shards.py").read_text(encoding="utf-8")
        self.assertIn('"separations": "data/separations.json"', source)


class RebuildProfileTests(unittest.TestCase):
    def test_nightly_rebuild_models_and_checks_separations_before_the_desk(self):
        steps = profile.expand_steps([["_system/scripts/build_dashboard_data.py"]])
        names = [" ".join(step).replace("_system/scripts/", "") for step in steps]
        flows = names.index("build_separation_flows.py")
        dashboard = names.index("build_separations_dashboard.py")
        check = names.index("check_separation_universe.py --warn-only")
        desk = names.index("build_special_situations.py")
        self.assertLess(flows, dashboard)
        self.assertLess(dashboard, check)
        self.assertLess(check, desk)
        self.assertLess(desk, names.index("build_dashboard_data.py"))
        self.assertNotIn("check_separation_universe.py --strict", names)


class DownloaderTests(unittest.TestCase):
    def test_only_registered_tickers_get_the_separation_forms(self):
        base = downloader.form_limits_for("ACME", registered={"PRNT", "SPIN"})
        self.assertEqual(base, downloader.FORM_LIMITS)
        extra = downloader.form_limits_for("prnt", registered={"PRNT", "SPIN"})
        self.assertEqual(extra[: len(downloader.FORM_LIMITS)], downloader.FORM_LIMITS)
        self.assertEqual(extra[len(downloader.FORM_LIMITS):],
                         [("10-12B", 2), ("10-12B/A", 2), ("SC TO-I", 3), ("424B3", 3)])
        self.assertEqual(downloader.form_limits_for(None, registered={"PRNT"}), downloader.FORM_LIMITS)

    def test_default_form_limits_are_unchanged(self):
        self.assertEqual(dict(downloader.FORM_LIMITS)["8-K"], 25)
        self.assertNotIn("10-12B", dict(downloader.FORM_LIMITS))
        self.assertNotIn("SC TO-I", dict(downloader.FORM_LIMITS))

    def test_register_tickers_come_from_separation_common(self):
        import separation_common

        rows = [{"separation_id": "sep:x", "version": 1, "parent_ticker": "PRNT", "spinco_ticker": "spin"}]
        tickers = {t for row in separation_common.latest_registry(rows) for t in separation_common.tickers_of(row)}
        self.assertEqual(tickers, {"PRNT", "SPIN"})
        self.assertIsInstance(downloader.separation_tickers(), set)

    def test_download_sec_picks_from_the_supplied_limits(self):
        # The picker is exercised through its inner loop shape: supplied limits, not the module constant.
        source = (SCRIPTS / "download_us_investor_docs.py").read_text(encoding="utf-8")
        self.assertIn("for form, limit in form_limits:", source)
        self.assertNotIn("for form, limit in FORM_LIMITS:", source)
        self.assertIn("form_limits=form_limits", source)


class SentinelTests(unittest.TestCase):
    def test_transaction_patterns_catch_separation_language(self):
        patterns = sentinel.SECTION_PATTERNS["transaction"]
        phrases = [
            "announced a tax-free spin-off of its consumer health business",
            "the Spinoff is expected to be completed",
            "a split-off exchange offer for shares of",
            "the distribution ratio will be 1 share for every 8",
            "will retain a retained stake of 9.5%",
            "its retained interest in SpinCo",
            "filed a registration statement on Form 10",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(any(re.search(p, phrase, re.I) for p in patterns), phrase)
        self.assertFalse(any(re.search(p, "quarterly revenue grew 4%", re.I) for p in patterns))

    def test_taxonomy_carries_the_four_separation_tags(self):
        taxonomy = json.loads((ROOT / "_system/data/filing_sentinel_taxonomy.json").read_text(encoding="utf-8"))
        tags = taxonomy["categories"]["transaction"] if "categories" in taxonomy else None
        if tags is None:
            tags = next(v for k, v in taxonomy.items() if isinstance(v, dict) and "transaction" in v)["transaction"]
        for tag in ("separation_announced", "exchange_offer", "distribution_ratio", "retained_stake"):
            self.assertIn(tag, tags)
        self.assertEqual(len(tags), len(set(tags)))
        self.assertNotIn("separation_announced", taxonomy["always_human_review_tags"])


class OnboardTests(unittest.TestCase):
    def test_no_arguments_means_no_linkage(self):
        self.assertEqual(onboard.separation_link(None, None), ({}, []))

    def test_linkage_records_fields_and_warns_against_the_register(self):
        import separation_common

        real = separation_common.latest_registry
        try:
            separation_common.latest_registry = lambda rows=None: []
            fields, warnings = onboard.separation_link("jnj", "sep:jnj-kvue-2023")
            self.assertEqual(fields, {"parent_ticker": "JNJ", "separation_id": "sep:jnj-kvue-2023"})
            self.assertTrue(any("empty" in w for w in warnings))

            registry = [{"separation_id": "sep:jnj-kvue-2023", "version": 1, "kind": "split_off",
                         "parent_ticker": "JNJ", "lifecycle": "closed", "dates": {}}]
            separation_common.latest_registry = lambda rows=None: registry
            fields, warnings = onboard.separation_link(None, "sep:jnj-kvue-2023")
            self.assertEqual(fields["parent_ticker"], "JNJ")
            self.assertEqual(fields["separation_kind"], "split_off")
            self.assertEqual(warnings, [])
            _fields, warnings = onboard.separation_link("PFE", "sep:jnj-kvue-2023")
            self.assertTrue(any("disagrees" in w for w in warnings))
            _fields, warnings = onboard.separation_link("JNJ", "sep:missing")
            self.assertTrue(any("not in the separation register" in w for w in warnings))
        finally:
            separation_common.latest_registry = real

    def test_cli_accepts_parent_and_separation_id(self):
        source = (SCRIPTS / "onboard_ticker.py").read_text(encoding="utf-8")
        self.assertIn('"--parent"', source)
        self.assertIn('"--separation-id"', source)
        self.assertIn('classification["payoff_lens"] = "event"', source)
        self.assertIn('entry["parent_ticker"]', source)
        self.assertIn('entry["separation_id"]', source)

    def test_thesis_template_notes_the_separation(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            real_root = onboard.ROOT
            try:
                onboard.ROOT = Path(tmp)
                onboard.write_thesis("SPIN", "SpinCo Inc.", {"payoff_lens": "event"},
                                     {"parent_ticker": "PRNT", "separation_id": "sep:prnt-spin-2026", "separation_kind": "spin_off"})
                text = (Path(tmp) / "SPIN/research/thesis.md").read_text(encoding="utf-8")
            finally:
                onboard.ROOT = real_root
        self.assertIn("| **Payoff lens** | event |", text)
        self.assertIn("| **Separation** | SpinCo of PRNT (spin_off, sep:prnt-spin-2026) |", text)
        self.assertIn("separated from PRNT", text)
        self.assertIn("special_situation_lens.md", text)


if __name__ == "__main__":
    unittest.main()
