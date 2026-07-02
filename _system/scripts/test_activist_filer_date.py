#!/usr/bin/env python3
"""Regression tests for activist filer resolution and report dating."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_date_parse import (  # noqa: E402
    parse_date_from_stem,
    parse_local_report_metadata,
    resolve_sec_filing_date,
)
from sec_filer_parse import (  # noqa: E402
    UNRESOLVED_FIRM_ID,
    analyze_sec_filing,
    build_activist_title,
    extract_proxy_filing_persons,
    form_from_filing_path,
    is_sec_filing_relpath,
)

FRMI_SAMPLE = ROOT / "FRMI/third-party-analyses/activist_reports/long/DFAN14A_20260701_acc0001213900_26_073999.htm"
QDEL_SC13DA = ROOT / "QDEL/third-party-analyses/activist_reports/long/SC-13D/A_20240514_acc0001193125_24_138290.htm"
FEED_PATH = ROOT / "dashboard/data/activist_feed.json"


class ActivistFilerDateTests(unittest.TestCase):
    def test_proxy_filer_extraction_frmi(self) -> None:
        if not FRMI_SAMPLE.exists():
            self.skipTest("FRMI sample filing missing")
        text = FRMI_SAMPLE.read_text(encoding="utf-8", errors="ignore")
        persons = extract_proxy_filing_persons(text)
        self.assertTrue(any("vicksburg" in p.lower() for p in persons))
        analysis = analyze_sec_filing("DFAN14A", text)
        self.assertNotEqual(analysis["firm_id"], UNRESOLVED_FIRM_ID)
        self.assertIn("vicksburg", analysis["firm_name"].lower())

    def test_build_title_for_resolved_proxy(self) -> None:
        analysis = {
            "firm_id": "vicksburg",
            "firm_name": "Vicksburg Investments Management",
            "reporting_persons": ["Vicksburg Investments Management LLC", "Toby R. Neugebauer"],
        }
        title = build_activist_title(analysis, "DFAN14A", ticker="FRMI", report_date="2026-07-01")
        self.assertIn("Vicksburg", title)
        self.assertIn("proxy solicitation", title)

    def test_local_filename_date(self) -> None:
        iso, precision, source = parse_date_from_stem("hindenburg_2024-01-01_pacs")
        self.assertEqual(iso, "2024-01-01")
        self.assertEqual(precision, "day")
        self.assertEqual(source, "filename")

    def test_local_report_metadata(self) -> None:
        path = Path("X.TO/third-party-analyses/activist_reports/short/hindenburg_2024-01-01_pacs.html")
        meta = parse_local_report_metadata(path, "short")
        self.assertEqual(meta["report_date"], "2024-01-01")
        self.assertEqual(meta["firm_id"], "hindenburg")
        self.assertTrue(meta.get("title"))

    def test_sec_date_from_filename_not_today(self) -> None:
        if not FRMI_SAMPLE.exists():
            self.skipTest("FRMI sample filing missing")
        text = FRMI_SAMPLE.read_text(encoding="utf-8", errors="ignore")
        meta = resolve_sec_filing_date(FRMI_SAMPLE, text, filing_date=None)
        self.assertEqual(meta["report_date"], "2026-07-01")
        self.assertEqual(meta["date_source"], "filename")

    def test_sc13da_subdirectory_path_detection(self) -> None:
        rel = "QDEL/third-party-analyses/activist_reports/long/SC-13D/A_20240514_acc0001193125_24_138290.htm"
        self.assertTrue(is_sec_filing_relpath(rel))
        self.assertEqual(form_from_filing_path(rel), "SC 13D/A")
        if not QDEL_SC13DA.exists():
            self.skipTest("QDEL SC 13D/A sample missing")
        text = QDEL_SC13DA.read_text(encoding="utf-8", errors="ignore")
        analysis = analyze_sec_filing("SC 13D/A", text)
        self.assertEqual(analysis["firm_id"], "carlyle")

    def test_feed_has_low_unknown_filer_count(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        rows = feed.get("feed") or []
        unknown = [r for r in rows if r.get("firm_id") == UNRESOLVED_FIRM_ID]
        missing_dates = [r for r in rows if not r.get("report_date")]
        self.assertLessEqual(len(unknown), 5, msg=f"unknown filers: {len(unknown)}")
        self.assertEqual(len(missing_dates), 0, msg=f"missing dates: {len(missing_dates)}")

    def test_frmi_feed_rows_name_vicksburg(self) -> None:
        if not FEED_PATH.exists():
            self.skipTest("activist_feed.json missing")
        feed = json.loads(FEED_PATH.read_text(encoding="utf-8"))
        frmi = [r for r in feed.get("feed") or [] if r.get("ticker") == "FRMI"]
        self.assertTrue(frmi)
        self.assertTrue(any("Vicksburg" in (r.get("firm_name") or "") for r in frmi))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
