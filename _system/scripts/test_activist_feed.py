#!/usr/bin/env python3
"""Tests for activist feed integrity (ghost links, weak matches, publisher guards)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_common import (  # noqa: E402
    publisher_match_allowed,
    resolve_report_file,
    ticker_meta,
    url_target_mismatch,
)
from build_activist_feed import build_feed, feed_eligible, github_blob  # noqa: E402
from sec_filer_parse import _add_name  # noqa: E402

FEED_PATH = ROOT / "dashboard" / "data" / "activist_feed.json"


class ActivistFeedTests(unittest.TestCase):
    def test_viceroy_osc_ciro_does_not_match_azlcz(self) -> None:
        meta = ticker_meta("AZLCZ")
        url = "https://viceroyresearch.org/osc-and-ciro/"
        title = "OSC and CIRO"
        blob = f"{title} {url}"
        self.assertTrue(url_target_mismatch(url, title, meta))
        ok, _confidence, reason = publisher_match_allowed(url, title, blob, meta)
        self.assertFalse(ok)
        self.assertIn(reason, ("url_mismatch", "no_match", "alias:azlcz"))

    def test_missing_local_file_excluded_without_source_url(self) -> None:
        report = {
            "firm_id": "viceroy",
            "side": "short",
            "local_file": "AZLCZ/third-party-analyses/activist_reports/short/viceroy_2026-01-01_osc-and-ciro.html",
            "include_in_feed": True,
        }
        _ref, _is_pdf, exists = resolve_report_file(report)
        self.assertFalse(exists)
        self.assertFalse(feed_eligible(report))

    def test_missing_file_with_source_url_stays_eligible(self) -> None:
        report = {
            "firm_id": "viceroy",
            "side": "short",
            "local_file": "missing/path.html",
            "source_url": "https://viceroyresearch.org/example/",
            "include_in_feed": True,
        }
        self.assertTrue(feed_eligible(report))

    def test_github_blob_only_when_file_exists_in_feed(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        for row in feed.get("feed") or []:
            if row.get("github_url"):
                self.assertTrue(row.get("file_exists"), msg=f"ghost github_url on {row.get('ticker')}")
            if row.get("file_exists") is False:
                self.assertIsNone(row.get("github_url"), msg=f"github_url on missing file {row.get('local_file')}")

    def test_no_viceroy_osc_ciro_rows_in_feed(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        bad = [
            r
            for r in feed.get("feed") or []
            if "osc-and-ciro" in (r.get("local_file") or "") or "osc and ciro" in (r.get("title") or "").lower()
        ]
        self.assertEqual(bad, [], msg=f"spurious viceroy rows remain: {len(bad)}")

    def test_strip_leading_paren_from_filer_names(self) -> None:
        names: list[str] = []
        seen: set[str] = set()
        _add_name(names, seen, ") DANAHER CORPORATION")
        self.assertEqual(names, ["DANAHER CORPORATION"])

    def test_github_repo_uses_org_default(self) -> None:
        url = github_blob("README.md")
        self.assertIn("magis-capital-partners/single-stock-investments", url or "")

    def test_spruce_uranium_does_not_match_nvda(self) -> None:
        meta = ticker_meta("NVDA")
        url = "https://sprucepointcap.com/research/uranium-energy-corporation"
        title = "Sep 18, 2025"
        blob = f"{title} {url}"
        self.assertTrue(url_target_mismatch(url, title, meta))
        ok, _confidence, reason = publisher_match_allowed(url, title, blob, meta)
        self.assertFalse(ok)
        self.assertIn(reason, ("url_mismatch", "no_match", "alias:corporation", "alias:nvidia"))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
