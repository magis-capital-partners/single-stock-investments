#!/usr/bin/env python3
"""Feed status catalog: every nav hash, real lanes, and three stamp states."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_feed_status as feeds  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class ClassifyTests(unittest.TestCase):
    NOW = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)

    def test_missing_unreadable_and_stale_are_different_labels(self):
        missing = feeds.classify_feed(False, None, 24, self.NOW)
        unreadable = feeds.classify_feed(True, "not-a-date", 24, self.NOW)
        stale = feeds.classify_feed(True, "2026-09-01T00:00:00Z", 24, self.NOW)
        fresh = feeds.classify_feed(True, "2026-10-06T12:00:00Z", 24, self.NOW)
        self.assertEqual(
            [feeds.feed_label(state) for state in (missing, unreadable, stale, fresh)],
            ["Missing file", "Unreadable stamp", "Stale", "Fresh"],
        )
        self.assertEqual(len({missing, unreadable, stale}), 3)

    def test_fresh_file_with_no_actionable_rows_is_empty(self):
        status = feeds.classify_feed(True, "2026-10-06T12:00:00Z", 48, self.NOW, empty=True)
        self.assertEqual(status, "empty")
        self.assertEqual(feeds.feed_label(status), "Current, no actionable rows")

    def test_date_only_stamp_is_readable(self):
        status = feeds.classify_feed(True, "2026-10-06", 48, self.NOW)
        self.assertEqual(status, "fresh")


class CatalogTests(unittest.TestCase):
    def test_every_nav_hash_has_a_row_and_every_lane_exists(self):
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        hashes = feeds.nav_hashes(html)
        self.assertGreaterEqual(len(hashes), 14)
        covered = {row["hash"] for row in feeds.surface_specs()}
        self.assertTrue(set(hashes) <= covered, sorted(set(hashes) - covered))
        config = json.loads((ROOT / feeds.GRAPH_REL).read_text(encoding="utf-8"))
        lane_names = {lane["name"] for lane in config["lanes"]}
        for row in feeds.surface_specs():
            self.assertIn(row["lane"], lane_names, row["id"])

    def test_registered_feeds_keep_the_registry_age_and_lane(self):
        config = json.loads((ROOT / feeds.GRAPH_REL).read_text(encoding="utf-8"))
        data_feeds = config["data_feeds"]
        by_id = {row["id"]: row for row in feeds.build_feed_status(ROOT, ClassifyTests.NOW)["surfaces"]}
        for row in feeds.surface_specs():
            feed_id = row.get("data_feed")
            if not feed_id:
                continue
            built = by_id[row["id"]]
            self.assertEqual(built["max_age_hours"], float(data_feeds[feed_id]["max_age_hours"]))
            self.assertEqual(built["lane"], feeds.FEED_LANES[feed_id])
            self.assertEqual(built["healer"], data_feeds[feed_id]["healer"])

    def test_feed_lanes_match_the_supervisor(self):
        import supervise_repository_health as supervisor

        self.assertEqual(feeds.FEED_LANES, supervisor.P6_FEED_LANES)


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.id().replace(".", "_"))
        # Isolated tree so a missing core.json is really missing.
        base = Path(__file__).resolve().parent / "_feed_status_fixtures" / self.id().split(".")[-1]
        if base.exists():
            shutil.rmtree(base)
        self.root = base
        self.root.mkdir(parents=True)
        graph = {
            "lanes": [
                {"name": "data-pipeline-intake-full", "freshness_hours": 54},
                {"name": "valuation", "freshness_hours": 56},
                {"name": "deploy", "freshness_hours": 54},
                {"name": "data-pipeline-technicals", "freshness_hours": 102},
                {"name": "ls-algo", "freshness_hours": 54},
                {"name": "data-pipeline-activist", "freshness_hours": 54},
                {"name": "data-pipeline-warrant-discover", "freshness_hours": 342},
                {"name": "letters", "freshness_hours": 174},
                {"name": "podcasts", "freshness_hours": 342},
                {"name": "market-risk", "freshness_hours": 102},
            ],
            "data_feeds": {},
        }
        graph_path = self.root / feeds.GRAPH_REL
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(json.dumps(graph), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_open_issue_is_named_and_a_stale_lane_says_retry(self):
        supervisor = {
            "lanes": {
                "data-pipeline-intake-full": {"stale": True, "persistent": False, "held": None},
                "valuation": {"stale": False, "persistent": True, "held": None},
            },
            "issues": {
                "fp": {"state": "open", "lanes": {"valuation": {"fp": "fp"}}},
            },
        }
        path = self.root / feeds.SUPERVISOR_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(supervisor), encoding="utf-8")
        core = self.root / "dashboard" / "data" / "core.json"
        core.parent.mkdir(parents=True, exist_ok=True)
        core.write_text(json.dumps({
            "generated_at": "2026-10-06T12:00:00Z",
            "nol_screener": {"rows": [], "actionable_count": 0},
            "advantaged_banks_screener": {"rows": [{"is_low_cost": True}]},
        }), encoding="utf-8")
        built = {row["id"]: row for row in feeds.build_feed_status(self.root, ClassifyTests.NOW)["surfaces"]}
        self.assertIn("The supervisor will retry this lane", built["coverage"]["next_action"])
        self.assertIn("A lane-failure issue is open.", built["valuation"]["next_action"])
        self.assertEqual(built["nol"]["status"], "empty")
        self.assertEqual(built["banks"]["status"], "fresh")
        self.assertEqual(built["rock"]["status"], "missing")
        self.assertNotIn("repository_dispatch", built["coverage"]["next_action"])


class PageCopyTests(unittest.TestCase):
    def test_empty_states_do_not_say_data_health_owns(self):
        for rel in ("dashboard/index.html", "dashboard/insights-viz.js"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("Data Health owns", text, rel)

    def test_index_watch_does_not_print_a_local_python_command(self):
        text = (ROOT / "dashboard" / "insights-viz.js").read_text(encoding="utf-8")
        self.assertNotIn("build_index_membership.py", text)

    def test_ui_format_exposes_the_three_labels(self):
        text = (ROOT / "dashboard" / "ui-format.js").read_text(encoding="utf-8")
        for label in ("Missing file", "Unreadable stamp", "Stale"):
            self.assertIn(label, text)
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = textwrap.dedent("""
            const fs = require('fs');
            const vm = require('vm');
            const context = { window: {}, console, navigator: { language: 'en-US', languages: ['en-US'] } };
            vm.createContext(context);
            vm.runInContext(fs.readFileSync('dashboard/ui-format.js', 'utf8'), context);
            const format = context.window.DashboardFormat;
            const now = Date.parse('2026-10-06T18:00:00Z');
            const missing = format.feedState(null, 24, { exists: false, now });
            const unreadable = format.feedState('not-a-date', 24, { exists: true, now });
            const stale = format.feedState('2026-09-01T00:00:00Z', 24, { exists: true, now });
            const fresh = format.feedState('2026-10-06T12:00:00Z', 24, { exists: true, now });
            if (format.feedLabel(missing) !== 'Missing file') process.exit(2);
            if (format.feedLabel(unreadable) !== 'Unreadable stamp') process.exit(3);
            if (format.feedLabel(stale) !== 'Stale') process.exit(4);
            if (format.feedLabel(fresh) !== 'Fresh') process.exit(5);
            if (new Set([missing, unreadable, stale]).size !== 3) process.exit(6);
        """)
        result = subprocess.run(
            [node, "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
