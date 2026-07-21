from __future__ import annotations

import unittest

from validate_research_pr_provenance import validate


MANIFEST = {
    "ticker": "AAA",
    "evidence_hash": "a" * 64,
    "primary_evidence_ready": True,
}
STATE = {
    "ticker": "AAA",
    "consumer": "marvin_research",
    "evidence_hash": "a" * 64,
    "completed_at": "2026-07-20T12:00:00+00:00",
}


class ResearchPrProvenanceTests(unittest.TestCase):
    def test_matching_provenance_is_valid(self):
        self.assertEqual(validate(MANIFEST, STATE, "AAA"), [])

    def test_mismatched_hash_is_rejected(self):
        state = {**STATE, "evidence_hash": "b" * 64}
        self.assertIn("agent state evidence_hash does not match manifest", validate(MANIFEST, state, "AAA"))

    def test_non_primary_manifest_is_rejected(self):
        manifest = {**MANIFEST, "primary_evidence_ready": False}
        self.assertIn("manifest does not authorize primary evidence", validate(manifest, STATE, "AAA"))

    def test_contract_backfill_consumer_is_accepted(self):
        state = {**STATE, "consumer": "marvin_contract_backfill"}
        self.assertEqual(validate(MANIFEST, state, "AAA"), [])


if __name__ == "__main__":
    unittest.main()
