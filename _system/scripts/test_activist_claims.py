#!/usr/bin/env python3
"""Tests for activist filing -> pending claim proposals."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import activist_claims  # noqa: E402
import agent_proposals  # noqa: E402

URL = "https://www.sec.gov/Archives/edgar/data/789570/000110465926119439/0001104659-26-119439-index.html"
ACCESSION = "0001104659-26-119439"


def filing(**overrides):
    base = {
        "subject_ticker": "mgm",
        "subject_cik": "789570",
        "filer_name": "People Incorporated",
        "filer_cik": "1800227",
        "form": "SC 13D/A",
        "accession": ACCESSION,
        "filing_date": "2026-10-28",
        "percent_of_class": 26.5,
        "shares": 66822350,
        "label": "governance agreement",
        "source_url": URL,
    }
    base.update(overrides)
    return base


class ActivistClaimTests(unittest.TestCase):
    def test_one_filing_becomes_one_pending_proposal(self) -> None:
        proposals = activist_claims.proposals_from_filing(filing())
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal["agent"], "activism-desk")
        self.assertEqual(proposal["kind"], "claim")
        self.assertEqual(proposal["ticker"], "MGM")
        self.assertNotIn("status", proposal)
        self.assertEqual(proposal["payload"]["status"], "pending")
        self.assertEqual(proposal["payload"]["claim_type"], "fact")
        self.assertEqual(proposal["payload"]["percent_of_class"], 26.5)
        self.assertEqual(proposal["payload"]["shares"], 66822350)
        self.assertEqual(proposal["payload"]["source_path"], URL)
        self.assertEqual(proposal["payload"]["source_locator"], ACCESSION)
        self.assertEqual(proposal["provenance"]["source_paths"], [URL, ACCESSION])
        self.assertEqual(proposal["payload"]["subject_cik"], "0000789570")
        self.assertEqual(proposal["payload"]["filer_cik"], "0001800227")
        self.assertNotIn("percent_per_year", json.dumps(proposal))

    def test_submit_stays_pending_and_accepts_sec_provenance(self) -> None:
        import tempfile

        proposal = activist_claims.proposals_from_filing(filing())[0]
        self.assertEqual(agent_proposals.validate_proposal(proposal, root=ROOT), [])
        with tempfile.TemporaryDirectory() as tmp:
            submitted = agent_proposals.submit(proposal, inbox=Path(tmp) / "inbox.jsonl", root=ROOT)
        self.assertEqual(submitted["status"], "pending_human_review")
        self.assertNotEqual(submitted["status"], "approved")
        self.assertFalse(submitted.get("duplicate"))

    def test_a_missing_local_path_still_fails(self) -> None:
        proposal = activist_claims.proposals_from_filing(filing())[0]
        proposal["provenance"]["source_paths"] = ["NOPE/missing.json"]
        errors = agent_proposals.validate_proposal(proposal, root=ROOT)
        self.assertTrue(any("does not exist" in error for error in errors), errors)

    def test_label_and_url_are_checked(self) -> None:
        with self.assertRaises(ValueError):
            activist_claims.proposals_from_filing(filing(label="approved"))
        with self.assertRaises(ValueError):
            activist_claims.proposals_from_filing(filing(source_url="https://example.com/filing"))
        with self.assertRaises(ValueError):
            activist_claims.proposals_from_filing(filing(accession="not-an-accession"))

    def test_percent_of_class_is_not_rescaled(self) -> None:
        proposal = activist_claims.proposals_from_filing(filing(percent_of_class=4.6, shares=5693897))[0]
        self.assertEqual(proposal["payload"]["percent_of_class"], 4.6)
        self.assertEqual(proposal["payload"]["shares"], 5693897)
        self.assertNotEqual(proposal["payload"]["percent_of_class"], 0.046)

    def test_ticker_is_the_subject_passed_in(self) -> None:
        proposal = activist_claims.proposals_from_filing(
            filing(subject_ticker="ASST", subject_cik="1920406")
        )[0]
        self.assertEqual(proposal["ticker"], "ASST")
        self.assertNotEqual(proposal["ticker"], "SATS")

    def test_several_filings_stay_separate(self) -> None:
        proposals = activist_claims.proposals_from_filings(
            [filing(), filing(subject_ticker="META", accession="0001628280-26-066710", label="control filing")]
        )
        self.assertEqual([row["ticker"] for row in proposals], ["MGM", "META"])


if __name__ == "__main__":
    unittest.main()
