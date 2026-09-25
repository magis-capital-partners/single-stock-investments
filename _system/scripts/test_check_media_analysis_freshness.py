#!/usr/bin/env python3
"""The check that would have caught the 2026-09-11..25 analysis outage.

Every test here is a shape the real outage actually took, or a shape that must
NOT fire: a check that cries wolf on an ordinary backlog gets ignored, and then
it is worth nothing on the day it matters.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import check_media_analysis_freshness as chk  # noqa: E402

DAY = date(2026, 9, 25)


def state(name: str, analysed: int, last_change: str) -> dict:
    return {"sources": {name: {"analysed": analysed, "corpus": 4627,
                               "last_change_at": last_change}}}


class ObserveTests(unittest.TestCase):
    def test_depth_is_read_from_source_health(self):
        got = chk.observe({"source_health": {
            "videos": {"items": 95, "with_analysis": 16},
            "podcasts": {"transcript_count": 4222, "with_analysis": 413},
        }})
        self.assertEqual(got["videos"], {"analysed": 16, "corpus": 95})
        self.assertEqual(got["podcasts"], {"analysed": 413, "corpus": 4222})

    def test_a_missing_depth_field_is_not_zero(self):
        """The committed manifest carried five counts of videos and no count of
        videos read, because the rebuild dropped what the publisher wrote.
        Reading that as 0 would look like a collapse instead of a blind spot."""
        got = chk.observe({"source_health": {"videos": {"items": 95}}})
        self.assertIsNone(got["videos"]["analysed"])
        problems, _ = chk.evaluate(got, {}, today=DAY)
        self.assertTrue(any("no with_analysis" in p for p in problems), problems)

    def test_sources_the_manifest_does_not_describe_are_skipped(self):
        self.assertEqual(chk.observe({"source_health": {}}), {})
        self.assertEqual(chk.observe({}), {})


class StallTests(unittest.TestCase):
    def test_the_real_outage_is_caught(self):
        """413 of 4,222, unmoved since the 11th, on the 25th."""
        observed = {"podcasts": {"analysed": 413, "corpus": 4222}}
        problems, _ = chk.evaluate(observed, state("podcasts", 413, "2026-09-11"), today=DAY)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("stuck at 413 for 14 days", problems[0])
        self.assertIn("3809 unanalysed", problems[0])

    def test_a_lane_that_is_merely_slow_resets_its_own_clock(self):
        """23 items on a bad day is a slow lane, not a stopped one."""
        observed = {"podcasts": {"analysed": 436, "corpus": 4222}}
        problems, nxt = chk.evaluate(observed, state("podcasts", 413, "2026-09-11"), today=DAY)
        self.assertEqual(problems, [])
        self.assertEqual(nxt["sources"]["podcasts"]["last_change_at"], "2026-09-25")

    def test_just_inside_the_window_is_quiet_and_just_outside_is_not(self):
        observed = {"podcasts": {"analysed": 413, "corpus": 4222}}
        quiet, _ = chk.evaluate(observed, state("podcasts", 413, "2026-09-22"), today=DAY)
        self.assertEqual(quiet, [])
        loud, _ = chk.evaluate(observed, state("podcasts", 413, "2026-09-21"), today=DAY)
        self.assertEqual(len(loud), 1, loud)

    def test_an_empty_backlog_may_stand_still_forever(self):
        """Whisper finished its queue on 09-17 and stopped. That is correct, and
        a check that called it dead would have to be muted, which is how the
        next real outage gets missed."""
        observed = {"podcasts": {"analysed": 4222, "corpus": 4222}}
        problems, _ = chk.evaluate(observed, state("podcasts", 4222, "2026-08-01"), today=DAY)
        self.assertEqual(problems, [])

    def test_a_first_run_baselines_rather_than_firing(self):
        """A fresh clone has no history. Firing on day one trains the reader to
        ignore it; the very next run has a real baseline to compare against."""
        observed = {"videos": {"analysed": 16, "corpus": 95}}
        problems, nxt = chk.evaluate(observed, {}, today=DAY)
        self.assertEqual(problems, [])
        self.assertEqual(nxt["sources"]["videos"],
                         {"analysed": 16, "corpus": 95, "last_change_at": "2026-09-25"})

    def test_a_count_that_went_backwards_still_counts_as_movement(self):
        """A corpus rebuild can drop rows. That is a different fault, and not
        this check's to report -- but it is emphatically not a stall."""
        observed = {"videos": {"analysed": 9, "corpus": 95}}
        problems, nxt = chk.evaluate(observed, state("videos", 16, "2026-09-01"), today=DAY)
        self.assertEqual(problems, [])
        self.assertEqual(nxt["sources"]["videos"]["last_change_at"], "2026-09-25")

    def test_both_sources_are_reported_independently(self):
        observed = {"podcasts": {"analysed": 413, "corpus": 4222},
                    "videos": {"analysed": 16, "corpus": 95}}
        prior = {"sources": {
            "podcasts": {"analysed": 413, "corpus": 4222, "last_change_at": "2026-09-11"},
            "videos": {"analysed": 16, "corpus": 95, "last_change_at": "2026-09-12"},
        }}
        problems, _ = chk.evaluate(observed, prior, today=DAY)
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(problems[0].startswith("podcasts:"))
        self.assertTrue(problems[1].startswith("videos:"))

    def test_an_unparseable_date_does_not_crash_the_check(self):
        observed = {"videos": {"analysed": 16, "corpus": 95}}
        problems, _ = chk.evaluate(observed, state("videos", 16, "not-a-date"), today=DAY)
        self.assertEqual(problems, [])

    def test_an_unknown_corpus_size_cannot_manufacture_a_backlog(self):
        observed = {"videos": {"analysed": 16, "corpus": None}}
        problems, _ = chk.evaluate(observed, state("videos", 16, "2026-09-01"), today=DAY)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
