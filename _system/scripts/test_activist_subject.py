#!/usr/bin/env python3
"""Regression tests for three activist-feed mis-tags (2026-10-29).

PBT: a DEFN14A cover must name the SoftVest group, not "Unresolved SEC filer".
BEN: Franklin's 13D on Clarion must not be stored under BEN.
SATS: Strive's 13D must not become SATS because company_tickers says so.

Fixtures are trimmed covers. No network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_common import (  # noqa: E402
    portfolio_ticker_for_subject_cik,
    subject_cik_matches_ticker,
)
from sec_activist_scan import _entry_from_analysis  # noqa: E402
from sec_filer_parse import (  # noqa: E402
    UNRESOLVED_FIRM_NAME,
    analyze_sec_filing,
    parse_schedule_13_xml,
)

FIXTURES = ROOT / "_system" / "scripts" / "fixtures" / "activism"
# Strive, Inc. is CIK 1920406. EDGAR's ticker list leads with ASST and also
# carries SATS and SATA. EchoStar is CIK 1415404, EDGAR ticker ECHO.
# The desk's mistake was to follow the SATS symbol onto this filing.
STRIVE_CIK = "1920406"
ECHOSTAR_CIK = "1415404"
COMPANY_TICKERS_SAYS_SATS = {STRIVE_CIK: "SATS", "0001920406": "SATS"}


class SoftVestProxyFilerTests(unittest.TestCase):
    def test_defn14a_names_the_softvest_group(self) -> None:
        text = (FIXTURES / "pbt_defn14a_cover.html").read_text(encoding="utf-8")
        analysis = analyze_sec_filing("DEFN14A", text)
        self.assertNotEqual(analysis["firm_name"], UNRESOLVED_FIRM_NAME)
        self.assertNotEqual(analysis["firm_id"], "unknown_activist")
        found = {name.casefold().rstrip(" .") for name in analysis["reporting_persons"]}
        for person in (
            "pbt land and minerals, inc",
            "softvest, l.p",
            "softvest advisors, llc",
            "softvest gp i, llc",
            "eric l. oliver",
        ):
            self.assertIn(person, found, analysis["reporting_persons"])


class FilerIsNotTheSubjectTests(unittest.TestCase):
    def test_franklin_13d_on_clarion_does_not_map_to_ben(self) -> None:
        facts = parse_schedule_13_xml((FIXTURES / "ben_clarion_13da.xml").read_text(encoding="utf-8"))
        self.assertEqual(facts["issuer_name"], "CLARION PARTNERS REAL ESTATE INCOME FUND INC.")
        self.assertIn("38777", facts["reporting_person_ciks"])
        # The filer CIK is BEN. The subject CIK is not.
        self.assertTrue(subject_cik_matches_ticker("38777", "BEN"))
        self.assertFalse(subject_cik_matches_ticker(facts["issuer_cik"], "BEN"))
        self.assertIsNone(portfolio_ticker_for_subject_cik(facts["issuer_cik"]))
        entry = _entry_from_analysis(
            "BEN",
            "SC 13D/A",
            Path("BEN/third-party-analyses/activist_reports/long/clarion.htm"),
            "<html>Franklin Templeton, Inc. SC 13D/A</html>",
            source_url=None,
            accession="0000038777-26-000271",
            filing_date="2026-10-23",
            xml_facts=facts,
        )
        self.assertIsNone(entry)

    def test_strive_13d_does_not_map_to_sats_via_company_tickers(self) -> None:
        facts = parse_schedule_13_xml((FIXTURES / "sats_strive_13da.xml").read_text(encoding="utf-8"))
        self.assertEqual(facts["issuer_name"], "Strive, Inc.")
        self.assertEqual(facts["issuer_cik"], STRIVE_CIK)
        # EDGAR ticker ASST. Not EchoStar, whose EDGAR ticker is ECHO.
        self.assertFalse(subject_cik_matches_ticker(facts["issuer_cik"], "ECHO"))
        self.assertTrue(subject_cik_matches_ticker(ECHOSTAR_CIK, "ECHO"))
        # The collision the desk followed. The registry must win.
        self.assertEqual(COMPANY_TICKERS_SAYS_SATS[STRIVE_CIK], "SATS")
        self.assertFalse(
            subject_cik_matches_ticker(
                facts["issuer_cik"],
                "SATS",
                external_cik_to_ticker=COMPANY_TICKERS_SAYS_SATS,
            )
        )
        self.assertIsNone(
            portfolio_ticker_for_subject_cik(
                facts["issuer_cik"],
                external_cik_to_ticker=COMPANY_TICKERS_SAYS_SATS,
            )
        )
        self.assertNotEqual(
            portfolio_ticker_for_subject_cik(
                facts["issuer_cik"],
                external_cik_to_ticker=COMPANY_TICKERS_SAYS_SATS,
            ),
            "SATS",
        )
        entry = _entry_from_analysis(
            "SATS",
            "SC 13D/A",
            Path("SATS/third-party-analyses/activist_reports/long/strive.htm"),
            "<html>Vivek Ramaswamy Strive, Inc. SC 13D/A</html>",
            source_url=None,
            accession="0000950103-26-016309",
            filing_date="2026-10-28",
            xml_facts=facts,
        )
        self.assertIsNone(entry)

    def test_mgm_subject_cik_still_maps_to_mgm(self) -> None:
        """The subject check drops a filer/ticker collision. It keeps a real one."""
        facts = parse_schedule_13_xml((FIXTURES / "mgm_people_13da.xml").read_text(encoding="utf-8"))
        self.assertTrue(subject_cik_matches_ticker(facts["issuer_cik"], "MGM"))
        entry = _entry_from_analysis(
            "MGM",
            "SC 13D/A",
            ROOT / "MGM/third-party-analyses/activist_reports/long/people.htm",
            "<html>PEOPLE INCORPORATED MGM RESORTS INTERNATIONAL</html>",
            source_url=None,
            accession="0001104659-26-119439",
            filing_date="2026-10-28",
            xml_facts=facts,
        )
        self.assertIsNotNone(entry)
        self.assertIn("PEOPLE INCORPORATED", entry["reporting_persons"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
