#!/usr/bin/env python3
"""Guards against sparse CI rebuilds clobbering holdings infra stats."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_dashboard_data as bdd  # noqa: E402


class SparseInfraGuardTests(unittest.TestCase):
    def test_preserve_infra_from_prior(self):
        rows = [
            {
                "ticker": "AAPL",
                "pdf_count": 0,
                "readme": False,
                "research_dir": False,
                "completeness": 0,
            }
        ]
        prior = {
            "AAPL": {
                "ticker": "AAPL",
                "pdf_count": 12,
                "readme": True,
                "research_dir": True,
                "completeness": 90,
                "sec_filings": 3,
            }
        }
        restored = bdd.preserve_infra_from_prior(rows, prior)
        self.assertEqual(restored, 1)
        self.assertEqual(rows[0]["pdf_count"], 12)
        self.assertTrue(rows[0]["readme"])
        self.assertTrue(rows[0]["research_dir"])
        self.assertEqual(rows[0]["completeness"], 90)

    def test_refuse_infra_collapse(self):
        payload = {
            "summary": {
                "ticker_count": 100,
                "total_pdfs": 0,
                "with_research": 0,
            }
        }
        prior = {
            f"T{i}": {"pdf_count": 5, "research_dir": True} for i in range(80)
        }
        with self.assertRaises(SystemExit):
            bdd.refuse_infra_collapse(payload, prior)

    def test_preserves_pdf_count_when_research_metadata_is_present(self):
        rows = [
            {
                "ticker": "AAPL",
                "pdf_count": 0,
                "readme": "AAPL/README.md",
                "research_dir": "AAPL/research",
                "completeness": 80,
            }
        ]
        prior = {
            "AAPL": {
                "ticker": "AAPL",
                "pdf_count": 12,
                "readme": "old-readme",
                "research_dir": "old-research",
                "completeness": 90,
            }
        }
        restored = bdd.preserve_infra_from_prior(rows, prior)
        self.assertEqual(restored, 1)
        self.assertEqual(rows[0]["pdf_count"], 12)
        self.assertEqual(rows[0]["readme"], "AAPL/README.md")
        self.assertEqual(rows[0]["research_dir"], "AAPL/research")
        self.assertEqual(rows[0]["completeness"], 90)

    def test_refuse_allows_healthy_payload(self):
        # The guard judges each infra column over the ROWS (since 2026-08-11),
        # so a healthy payload must carry its rows, not just a summary.
        payload = {
            "summary": {
                "ticker_count": 100,
                "total_pdfs": 500,
                "with_research": 80,
            },
            "tickers": [
                {"ticker": f"T{i}", "pdf_count": 5, "research_dir": True} for i in range(100)
            ],
        }
        prior = {f"T{i}": {"pdf_count": 5, "research_dir": True} for i in range(80)}
        bdd.refuse_infra_collapse(payload, prior)  # no raise

    def test_sparse_payload_updates_present_rows_without_deleting_absent_rows(self):
        prior = {
            "generated_at": "old",
            "summary": {"ticker_count": 60},
            "tickers": [{"ticker": f"T{i}", "pdf_count": 1, "completeness": 50} for i in range(60)],
        }
        current = {
            "generated_at": "new",
            "summary": {"ticker_count": 1},
            "tickers": [{"ticker": "T1", "pdf_count": 3, "completeness": 100}],
        }
        merged = bdd.merge_sparse_payload(current, prior)
        self.assertEqual(merged["generated_at"], "new")
        self.assertEqual(len(merged["tickers"]), 60)
        self.assertEqual(next(row for row in merged["tickers"] if row["ticker"] == "T1")["pdf_count"], 3)
        self.assertEqual(merged["summary"]["total_pdfs"], 62)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class SparseCiCheckoutTests(unittest.TestCase):
    """Simulate the ls-algo intake checkout: shards committed, monolith absent.

    dashboard_data.json is gitignored, so a fresh CI checkout never has it.
    The committed core.json + per-ticker shards are the only prior. Ticker
    trees are absent (sparse), so every freshly built row is thin.
    """

    TICKERS = [f"T{i:03d}" for i in range(120)]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "dashboard" / "data"
        core_rows = []
        for ticker in self.TICKERS:
            core_rows.append(
                {
                    "ticker": ticker,
                    "pdf_count": 70,
                    "readme": f"{ticker}/README.md",
                    "research_dir": f"{ticker}/research",
                    "completeness": 80,
                    "index_file": f"{ticker}/INDEX.md",
                    "download_script": True,
                    "download_script_path": f"{ticker}/download.py",
                    "last_download": "2026-09-01",
                    "sec_filings": 12,
                }
            )
            _write_json(
                data_dir / "tickers" / f"{ticker}.json",
                {"ticker": ticker, "recent_files": [f"{ticker}/research/a.md"]},
            )
        _write_json(data_dir / "core.json", {"tickers": core_rows})
        self.root, self.data_dir = root, data_dir
        patches = {
            "ROOT": root,
            "DATA_DIR": data_dir,
            "OUTPUT": data_dir / "dashboard_data.json",  # absent, as in CI
            "RESEARCH_MEMORY_PATH": data_dir / "research_memory.json",
            "DOCUMENT_REGISTRY_PATH": data_dir / "document_registry.json",
            "load_registry": lambda: {"watchlist": {}},
            "parse_holdings": lambda: {},
            "load_classification": lambda: {},
            "list_tickers": lambda: list(self.TICKERS),
            "load_insights_document": lambda: None,
            "build_ticker_row": self._thin_row,
            "build_watchlist_rows": lambda _watchlist: [],
            "build_portfolio_macro_regime": lambda: None,
            "build_portfolio_macro": lambda _insights: None,
            "valuation_queue_summary": lambda _rows: {"counts": {}},
            "load_valuation_universe_tiers": lambda: {},
        }
        self._patchers = [mock.patch.object(bdd, name, value) for name, value in patches.items()]
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._tmp.cleanup()

    @staticmethod
    def _thin_row(ticker, *_args, **_kwargs):
        # What build_ticker_row yields without the ticker tree on disk.
        return {
            "ticker": ticker,
            "market": "US",
            "pdf_count": 0,
            "readme": False,
            "research_dir": False,
            "completeness": 0,
            "index_file": None,
            "download_script": False,
            "download_script_path": None,
            "last_download": None,
            "sec_filings": 0,
            "classification": {},
        }

    def test_prior_for_restore_is_reconstructed_from_shards(self):
        self.assertFalse(bdd.OUTPUT.exists())
        prior = bdd.load_prior_dashboard_rows()
        self.assertEqual(len(prior), len(self.TICKERS))
        self.assertEqual(prior["T000"]["pdf_count"], 70)

    def test_sparse_ci_build_restores_infra_and_passes_the_guard(self):
        payload = bdd.build()
        # The guard sees the same shard-reconstructed prior main() gives it.
        bdd.refuse_infra_collapse(payload, bdd.load_prior_rows())  # must not raise
        self.assertEqual(payload["summary"]["total_pdfs"], 70 * len(self.TICKERS))
        self.assertEqual(payload["summary"]["with_readme"], len(self.TICKERS))
        row = next(r for r in payload["tickers"] if r["ticker"] == "T005")
        self.assertEqual(row["download_script_path"], "T005/download.py")
        self.assertEqual(row["recent_files"], ["T005/research/a.md"])

    def test_build_uses_the_prior_it_is_given(self):
        prior = bdd.load_prior_rows()
        payload = bdd.build(prior)
        self.assertEqual(payload["summary"]["total_pdfs"], 70 * len(self.TICKERS))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
