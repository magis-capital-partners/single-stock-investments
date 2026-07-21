#!/usr/bin/env python3
"""Tests for press/letter digest ingest and long-site registry wiring."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_common import (  # noqa: E402
    firm_has_ingest,
    firm_ingest_methods,
    load_firm_registry,
    match_report_to_ticker,
    publisher_match_allowed,
    ticker_meta,
)
from activist_materiality import filing_base_weight, materiality_score, materiality_tier  # noqa: E402
from press_activist_digest import classify_press_item, scan_press_wires  # noqa: E402


class RegistryIngestMethodsTests(unittest.TestCase):
    def test_third_point_and_de_shaw_have_site_and_wire(self) -> None:
        firms = {f["id"]: f for f in load_firm_registry().get("firms") or []}
        for fid in ("third_point", "de_shaw", "elliott"):
            self.assertIn(fid, firms)
            methods = firm_ingest_methods(firms[fid])
            self.assertIn("sec_13d", methods)
            self.assertIn("press_wire", methods)
            self.assertTrue(firm_has_ingest(firms[fid], "press_wire"))
        self.assertIn("site_index", firm_ingest_methods(firms["third_point"]))
        self.assertIn("site_index", firm_ingest_methods(firms["de_shaw"]))
        self.assertTrue(firms["de_shaw"].get("domains"))

    def test_short_firms_still_site_index(self) -> None:
        firms = {f["id"]: f for f in load_firm_registry().get("firms") or []}
        self.assertEqual(firm_ingest_methods(firms["hindenburg"]), ["site_index"])


class BrandMatchTests(unittest.TestCase):
    def test_costar_board_letter_matches_csgp(self) -> None:
        meta = ticker_meta("CSGP")
        title = "D.E. Shaw Group Letter to CoStar Board"
        url = "https://mma.prnewswire.com/media/2929958/DE_Shaw_Group_Letter_to_CoStar_Board.pdf"
        ok, confidence, reason = publisher_match_allowed(url, title, f"{title} {url}", meta)
        self.assertTrue(ok, msg=reason)
        self.assertGreaterEqual(confidence, 0.9)
        self.assertIn(reason, {"company_brand", "company_name", "ticker_symbol", "ticker_explicit"})

    def test_company_brand_reason_is_not_alias(self) -> None:
        matched, _confidence, reason = match_report_to_ticker(
            "Open letter to the CoStar board regarding Homes.com",
            ticker_meta("CSGP"),
        )
        self.assertTrue(matched)
        self.assertEqual(reason, "company_brand")


class PressClassifyTests(unittest.TestCase):
    def test_open_letter_classified(self) -> None:
        self.assertEqual(
            classify_press_item("Third Point Sends Letter to Board of Directors of CoStar Group"),
            "open_letter",
        )

    def test_fund_launch_excluded(self) -> None:
        self.assertIsNone(classify_press_item("Third Point closes new fund", "AUM update and fund launch"))


class PressIngestIntegrationTests(unittest.TestCase):
    def test_csgp_seeds_index_under_temp_root(self) -> None:
        # Run digest for CSGP only; downloads may use fixtures or seed_body fallback.
        result = scan_press_wires(["CSGP"], dry_run=False, backfill_days=400, scan_date="2026-07-21")
        self.assertGreaterEqual(result["hit_count"], 2)
        firm_ids = {h["firm_id"] for h in result["hits"]}
        self.assertIn("third_point", firm_ids)
        self.assertIn("de_shaw", firm_ids)
        index_path = ROOT / "CSGP" / "third-party-analyses" / "activist_reports_index.json"
        self.assertTrue(index_path.exists())
        reports = json.loads(index_path.read_text(encoding="utf-8")).get("reports") or []
        wire = [r for r in reports if r.get("source") == "press_wire"]
        self.assertGreaterEqual(len(wire), 2)


class MaterialityOpenLetterTests(unittest.TestCase):
    def test_open_letter_base_near_proxy(self) -> None:
        letter = filing_base_weight({"filing_class": "open_letter"})
        pub = filing_base_weight({"filing_class": "publisher_report"})
        self.assertGreater(letter, pub)

    def test_verified_press_wire_not_noise(self) -> None:
        row = {
            "firm_id": "de_shaw",
            "filing_class": "open_letter",
            "report_date": "2026-03-10",
            "source": "press_wire",
            "body_verified": True,
            "target_verified": True,
            "file_exists": True,
            "triage_verdict": "auto_signal",
        }
        score, _ = materiality_score(row, in_holdings=True)
        self.assertNotEqual(materiality_tier(score, row), "noise")


if __name__ == "__main__":
    unittest.main()
