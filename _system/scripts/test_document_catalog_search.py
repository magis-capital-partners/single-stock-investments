#!/usr/bin/env python3
"""Regression tests for PDF library / Insights search matching."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "dashboard" / "data" / "document_catalog.json"
NODE_RUNNER = ROOT / "_system" / "scripts" / "search_match_node_runner.cjs"


def run_node(action: str, query: str = "") -> dict | list:
    proc = subprocess.run(
        ["node", str(NODE_RUNNER), action, query],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "node runner failed")
    return json.loads(proc.stdout)


class DocumentCatalogSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CATALOG_PATH.exists():
            raise unittest.SkipTest("document_catalog.json not built")
        if not NODE_RUNNER.exists():
            raise unittest.SkipTest("search_match_node_runner.js missing")

    def test_tpl_excludes_jpx_itplan_false_positive(self) -> None:
        result = run_node("count", "tpl")
        # Hits must be genuine TPL documents (ticker TPL or untagged docs
        # naming TPL); the JPX "IT-plan" pages that used to substring-match
        # "tpl" must stay excluded.
        self.assertGreaterEqual(result["tpl"], 1)
        self.assertEqual(result["tickers"], ["TPL"])
        self.assertEqual(result["jpx_false_positive"], 0)

    def test_short_ticker_queries_drop_substring_noise(self) -> None:
        for query, max_total in [("he", 10), ("xp", 5), ("amd", 10)]:
            result = run_node("count", query)
            self.assertLessEqual(
                result["total"],
                max_total,
                msg=f"{query} returned {result['total']} matches: {result['tickers'][:8]}",
            )

    def test_free_text_queries_still_work(self) -> None:
        annual = run_node("count", "annual report")
        self.assertGreaterEqual(annual["total"], 100)
        jpx = run_node("count", "jpx")
        self.assertGreaterEqual(jpx["total"], 100)

    def test_partial_ticker_prefix(self) -> None:
        result = run_node("count", "8697")
        self.assertGreaterEqual(result["total"], 100)
        self.assertIn("8697.T", result["tickers"])

    def test_known_tickers_embedded_or_derived(self) -> None:
        known = run_node("known")
        self.assertIn("TPL", known)
        self.assertIn("8697.T", known)

    def test_search_ranking_prefers_exact_ticker(self) -> None:
        result = run_node("rank", "ice")
        self.assertEqual(result["top_ticker"], "ICE")
        self.assertGreaterEqual(result["top_score"], 80)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
