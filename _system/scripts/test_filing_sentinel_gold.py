#!/usr/bin/env python3
"""Tests for Filing Sentinel gold-set validation, mining rules, and evaluation."""
from __future__ import annotations

import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from filing_sentinel_gold import (  # noqa: E402
    DEFAULT_GOLD,
    _metric_proposal,
    evaluate,
    load_taxonomy,
    read_jsonl,
    validate_dataset,
)

PERFECT = ROOT / "_system" / "scripts" / "fixtures" / "filing_sentinel_perfect_predictions.jsonl"


class FilingSentinelGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.taxonomy = load_taxonomy()
        cls.gold = read_jsonl(DEFAULT_GOLD)

    def test_locked_gold_set_validates(self) -> None:
        self.assertEqual(validate_dataset(self.gold, self.taxonomy, require_gold=True), [])

    def test_source_lock_does_not_depend_on_checkout_line_endings(self) -> None:
        # Run 32165718813: locks taken on a Windows checkout (autocrlf, CRLF)
        # failed on Linux CI (LF) for all four cases, filings untouched.
        import filing_sentinel_gold as fsg

        lf = b"<html>\nItem 7. Liquidity\n</html>\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ABC").mkdir()
            (root / "ABC" / "lf.htm").write_bytes(lf)
            (root / "ABC" / "crlf.htm").write_bytes(lf.replace(b"\n", b"\r\n"))
            case = copy.deepcopy(self.gold[0])
            case["filing"]["source_sha256"] = hashlib.sha256(lf).hexdigest()
            case["filing"]["extract_ref"] = None
            case["filing"]["extract_sha256"] = None
            with mock.patch.object(fsg, "ROOT", root):
                for name in ("lf.htm", "crlf.htm"):
                    case["filing"]["source_ref"] = f"ABC/{name}"
                    errors = fsg.validate_case(case, self.taxonomy, require_gold=True)
                    self.assertEqual([e for e in errors if "source_sha256" in e], [], name)
                # A real change to the filing is still caught.
                (root / "ABC" / "crlf.htm").write_bytes(lf.replace(b"Liquidity", b"Solvency"))
                errors = fsg.validate_case(case, self.taxonomy, require_gold=True)
                self.assertTrue(any("source_sha256 does not match" in e for e in errors), errors)

    def test_miners_lock_the_same_hash_on_every_platform(self) -> None:
        import filing_sentinel_gold as fsg

        with tempfile.TemporaryDirectory() as tmp:
            lf, crlf = Path(tmp) / "lf.htm", Path(tmp) / "crlf.htm"
            lf.write_bytes(b"a\nb\n")
            crlf.write_bytes(b"a\r\nb\r\n")
            self.assertEqual(fsg.filing_file_sha256(lf), fsg.filing_file_sha256(crlf))
            self.assertEqual(fsg.filing_file_sha256(lf), hashlib.sha256(b"a\nb\n").hexdigest())

    def test_excerpt_tampering_is_detected(self) -> None:
        rows = copy.deepcopy(self.gold)
        rows[0]["evidence"][0]["excerpt"] += " altered"
        errors = validate_dataset(rows, self.taxonomy, require_gold=True)
        self.assertTrue(any("hash mismatch" in error for error in errors))

    def test_ticker_leakage_is_detected(self) -> None:
        rows = copy.deepcopy(self.gold)
        duplicate = copy.deepcopy(rows[0])
        duplicate["case_id"] = "fs-qdel-leakage-check"
        duplicate["split"] = "train"
        duplicate["filing"]["source_ref"] += "?duplicate"
        rows.append(duplicate)
        errors = validate_dataset(rows, self.taxonomy, require_gold=True)
        self.assertTrue(any("ticker leakage" in error for error in errors))

    def test_non_comparable_prior_period_is_detected(self) -> None:
        rows = copy.deepcopy(self.gold)
        rows[0]["filing"]["comparison_period_end"] = "2025-09-30"
        errors = validate_dataset(rows, self.taxonomy, require_gold=True)
        self.assertTrue(any("roughly one year" in error for error in errors))

    def test_perfect_predictions_pass_all_gates(self) -> None:
        report = evaluate(self.gold, read_jsonl(PERFECT), self.taxonomy)
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["precision"], 1.0)
        self.assertEqual(report["metrics"]["recall"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)

    def test_false_alert_and_miss_fail_quality_gates(self) -> None:
        predictions = read_jsonl(PERFECT)
        predictions[0]["events"] = [{
            "category": "transaction", "tags": ["wind_down"], "direction": "strengthens",
            "evidence_ids": ["not-real"],
        }]
        report = evaluate(self.gold, predictions, self.taxonomy)
        self.assertFalse(report["passed"])
        self.assertGreater(report["metrics"]["false_positives"], 0)
        self.assertGreater(report["metrics"]["false_negatives"], 0)

    def test_forbidden_extra_tag_fails_even_when_event_matches(self) -> None:
        predictions = read_jsonl(PERFECT)
        predictions[0]["events"][0]["tags"].append("restatement")
        report = evaluate(self.gold, predictions, self.taxonomy)
        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["forbidden_tag_violations"], 1)

    def test_hard_negative_parser_flag_never_becomes_proposal(self) -> None:
        config = self.taxonomy["metric_proposals"]["revenues"]
        proposal, reason = _metric_proposal(
            "revenues",
            {"current": 0, "prior": 16313, "parser_confidence": "high", "parser_flags": ["segment_context"]},
            config,
        )
        self.assertIsNone(proposal)
        self.assertIn("parser_hard_negative", reason)

    def test_material_high_confidence_change_becomes_candidate_proposal(self) -> None:
        config = self.taxonomy["metric_proposals"]["operating_income"]
        proposal, reason = _metric_proposal(
            "operating_income",
            {"current": 919.2, "prior": 1960.9, "parser_confidence": "high", "parser_flags": []},
            config,
        )
        self.assertIsNone(reason)
        self.assertEqual(proposal["tags"], ["margin_contraction"])
        self.assertEqual(proposal["direction"], "strengthens")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
