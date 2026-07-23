#!/usr/bin/env python3
"""Unit tests for CVR discovery helpers (Parts 2–4)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cvr_common
import refresh_cvr_universe as rcu


class CvrCommonTests(unittest.TestCase):
    def test_pick_target_prefers_non_acquirer(self):
        t = cvr_common.pick_target_ticker(["JNJ", "ABMD"], filing_cik=None)
        self.assertEqual(t, "ABMD")

    def test_pick_target_prefers_filing_cik(self):
        with mock.patch.object(
            cvr_common, "resolve_ticker_for_cik", return_value="JNJ"
        ):
            t = cvr_common.pick_target_ticker(["JNJ", "ABMD"], filing_cik="200406")
            self.assertEqual(t, "JNJ")

    def test_terms_complete_rejects_stub(self):
        self.assertFalse(
            cvr_common.terms_are_complete(
                {"stub": True, "max_payout_usd": 5, "milestones": [{"id": "x"}]}
            )
        )
        self.assertTrue(
            cvr_common.terms_are_complete(
                {"stub": False, "terms_complete": True, "max_payout_usd": 5}
            )
        )

    def test_form_filters(self):
        self.assertTrue(cvr_common.form_is_preferred("8-K"))
        self.assertTrue(cvr_common.form_is_preferred("DEFM14A"))
        self.assertFalse(cvr_common.form_is_preferred("10-K"))
        self.assertTrue(
            cvr_common.hit_looks_risk_factor_only({"form": "10-Q", "display_title": "x"})
        )

    def test_milestone_infer(self):
        self.assertEqual(
            cvr_common.infer_milestone_status_from_text("CVR payment was made"),
            "paid",
        )
        self.assertEqual(
            cvr_common.infer_milestone_status_from_text("milestone not achieved; expired"),
            "failed",
        )


class CvrRefreshTests(unittest.TestCase):
    def test_csv_rejects_missing_ticker(self):
        doc = {"pre_close_opportunities": [], "post_close_universe": []}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            p.write_text("company,consideration\nFoo,CVR\n", encoding="utf-8")
            n, rows = rcu.ingest_screener_csv(doc, p)
            self.assertEqual(n, 0)
            self.assertEqual(rows, [])

    def test_csv_accepts_ecip_row(self):
        doc = {"pre_close_opportunities": [], "post_close_universe": []}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            p.write_text(
                "ticker,company,notes\nZZZZ,Test Bank,ECIP contingent cash\n",
                encoding="utf-8",
            )
            n, rows = rcu.ingest_screener_csv(doc, p)
            self.assertEqual(n, 1)
            self.assertEqual(rows[0]["ticker"], "ZZZZ")

    def test_dedupe_accession_cik(self):
        doc = {
            "pre_close_opportunities": [
                {"ticker": "AAAA", "accession": "0001", "cik": "0000000001"}
            ],
            "post_close_universe": [],
        }
        keys = rcu._existing_accession_cik(doc)
        self.assertIn(("0001", "0000000001"), keys)


class CheckCvrTests(unittest.TestCase):
    def test_check_imports(self):
        import check_cvr_universe as chk

        self.assertTrue(callable(chk.check))


if __name__ == "__main__":
    unittest.main()
