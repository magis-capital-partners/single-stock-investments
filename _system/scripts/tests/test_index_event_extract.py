#!/usr/bin/env python3
"""Golden tests for subject-gated index event extraction."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from index_event_extract import extract_index_events  # noqa: E402


class TestIndexEventExtract(unittest.TestCase):
    def test_spacex_comention_amzn_empty(self):
        ev = extract_index_events(
            "SpaceX Joins the Nasdaq-100 on July 7. Here Is What This Means for QQQ and QQQM Investors.",
            "",
            ["AMZN", "GOOGL", "META"],
        )
        self.assertEqual(ev, [])

    def test_coreweave_comention_empty(self):
        ev = extract_index_events(
            "CoreWeave is Joining the Nasdaq-100. Is the Stock a Buy?",
            "",
            ["AMZN", "NVDA"],
        )
        self.assertEqual(ev, [])

    def test_marvell_joining_sp500_not_nvda(self):
        ev = extract_index_events(
            "After Being Called the Next Trillion-Dollar AI Stock and Joining the S&P 500, Marvell's CFO Just Filed to Dump $65 Million of Stock.",
            "",
            ["NVDA", "AMZN"],
        )
        self.assertEqual(ev, [])

    def test_cathie_wood_no_index_event(self):
        ev = extract_index_events(
            "Cathie Wood Goes Bargain Hunting: 3 Stocks She Just Bought",
            "",
            ["META"],
        )
        self.assertEqual(ev, [])

    def test_apld_joins_russell_1000(self):
        ev = extract_index_events(
            "Applied Digital (APLD) Joins Russell 1000 As Its Market Profile Shifts - Yahoo Finance",
            "",
            ["APLD"],
            {"APLD": "Applied Digital"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "APLD")
        self.assertEqual(ev[0]["index"], "russell_1000")
        self.assertEqual(ev[0]["action"], "add")

    def test_echo_added_to_russell(self):
        ev = extract_index_events(
            "EchoStar Corporation(NasdaqGS: ECHO) added to Russell 3000E Growth Benchmark - marketscreener.com",
            "",
            ["ECHO"],
            {"ECHO": "EchoStar Corporation"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "ECHO")
        self.assertEqual(ev[0]["action"], "add")

    def test_he_joins_russell_defensive(self):
        ev = extract_index_events(
            "Is Hawaiian Electric Industries (HE) Fairly Valued As It Joins The Russell Defensive Indexes?",
            "",
            ["HE"],
            {"HE": "Hawaiian Electric Industries"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "HE")
        self.assertEqual(ev[0]["action"], "add")

    def test_spacex_summary_not_or(self):
        ev = extract_index_events(
            "Millions of Investors Are About to Own SpaceX Stock Indirectly -- Whether They Want to or Not",
            "SpaceX has been added to the Russell 1000 and will join the Nasdaq-100, forcing millions of index fund investors to own the stock automatically.",
            ["OR"],
            {"OR": "Osisko Gold Royalties"},
        )
        self.assertEqual(ev, [])

    def test_cprt_index_reclassification(self):
        ev = extract_index_events(
            "What Copart (CPRT)'s CEO Transition and Index Reclassification Means For Shareholders",
            "",
            ["CPRT"],
            {"CPRT": "Copart"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "CPRT")
        self.assertEqual(ev[0]["action"], "reclassify")
        self.assertEqual(ev[0]["index"], "russell_1000")

    def test_cprt_russell_reclassification_impact(self):
        ev = extract_index_events(
            "How CEO Transition and Russell Reclassification Will Impact Copart (CPRT) Investors",
            "",
            ["CPRT"],
            {"CPRT": "Copart"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "CPRT")
        self.assertEqual(ev[0]["action"], "reclassify")
        self.assertEqual(ev[0]["index"], "russell_1000")

    def test_cprt_index_moves(self):
        ev = extract_index_events(
            "Copart (CPRT) Following CEO Changes And Index Moves With Valuation In Focus",
            "",
            ["CPRT"],
            {"CPRT": "Copart"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["action"], "reclassify")

    def test_cprt_index_shift_for_copart(self):
        ev = extract_index_events(
            "Jay Adair's CEO Return and Index Shift Could Be A Game Changer For Copart (CPRT)",
            "",
            ["CPRT"],
            {"CPRT": "Copart"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "CPRT")
        self.assertEqual(ev[0]["action"], "reclassify")

    def test_cprt_russell_reshuffle(self):
        ev = extract_index_events(
            "Copart (NASDAQ:CPRT) drops as CEO departure lands during Russell reshuffle",
            "",
            ["CPRT"],
            {"CPRT": "Copart"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "CPRT")
        self.assertEqual(ev[0]["action"], "reclassify")

    def test_reclass_comention_not_amzn(self):
        ev = extract_index_events(
            "What Copart (CPRT)'s CEO Transition and Index Reclassification Means For Shareholders",
            "",
            ["AMZN", "META"],
            {"AMZN": "Amazon", "META": "Meta Platforms"},
        )
        self.assertEqual(ev, [])

    def test_amd_russell_top_50_reclassify(self):
        ev = extract_index_events(
            "Advanced Micro Devices (AMD) Launches 30 MW Rackspace AI Deal And Joins Russell Top 50",
            "",
            ["AMD"],
            {"AMD": "Advanced Micro Devices"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "AMD")
        self.assertEqual(ev[0]["action"], "reclassify")

    def test_west_russell_2500_add(self):
        ev = extract_index_events(
            "Westrock Coffee Company(NasdaqGM: WEST) added to Russell 2500 Value Benchmark",
            "",
            ["WEST"],
            {"WEST": "Westrock Coffee Company"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "WEST")
        self.assertEqual(ev[0]["index"], "russell_2000")
        self.assertEqual(ev[0]["action"], "add")

    def test_als_tsx_add(self):
        ev = extract_index_events(
            "Altius Minerals Corporation(TSX: ALS) added to S&P/TSX Composite Index",
            "",
            ["ALS.TO"],
            {"ALS.TO": "Altius Minerals Corporation"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "ALS.TO")
        self.assertEqual(ev[0]["index"], "tsx_composite")
        self.assertEqual(ev[0]["action"], "add")

    def test_googl_dow_add(self):
        ev = extract_index_events(
            "Alphabet Just Replaced Verizon in the Dow. Could Nike Be the Next Dow Stock to Be Deleted?",
            "",
            ["GOOGL"],
            {"GOOGL": "Alphabet"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "GOOGL")
        self.assertEqual(ev[0]["index"], "djia")
        self.assertEqual(ev[0]["action"], "add")

    def test_spacex_not_googl(self):
        ev = extract_index_events(
            "SpaceX Will Join the Nasdaq-100 on July 7. Here's What a $10,000 Investment Could Be Worth in December, According to History.",
            "SpaceX will be added to the Nasdaq-100 on July 7.",
            ["GOOGL"],
            {"GOOGL": "Alphabet"},
        )
        self.assertEqual(ev, [])

    def test_csgp_nasdaq_exit_delete(self):
        ev = extract_index_events(
            "Why CoStar Group (CSGP) Is Down 7.4% After Nasdaq-100 Exit And Reaffirmed 2026 Guidance",
            "",
            ["CSGP"],
            {"CSGP": "CoStar Group"},
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["ticker"], "CSGP")
        self.assertEqual(ev[0]["index"], "nasdaq_100")
        self.assertEqual(ev[0]["action"], "delete")


if __name__ == "__main__":
    unittest.main()
