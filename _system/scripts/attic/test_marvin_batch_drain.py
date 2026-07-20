#!/usr/bin/env python3
"""Unit tests for Marvin batch drain PR wait helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from marvin_batch_drain import (  # noqa: E402
    check_conclusion,
    format_research_check_status,
    research_checks_passed,
)


class MarvinBatchDrainTests(unittest.TestCase):
    def test_check_conclusion_exact_name(self) -> None:
        checks = [{"name": "research-lint", "conclusion": "SUCCESS"}]
        self.assertEqual(check_conclusion(checks, "research-lint"), "SUCCESS")

    def test_check_conclusion_workflow_prefixed_name(self) -> None:
        checks = [
            {"name": "Research quality (PR) / research-lint", "conclusion": "SUCCESS"},
            {"name": "Research quality (PR) / cloud-prompt-sync", "status": "IN_PROGRESS"},
        ]
        self.assertEqual(check_conclusion(checks, "research-lint"), "SUCCESS")
        self.assertEqual(check_conclusion(checks, "cloud-prompt-sync"), "IN_PROGRESS")

    def test_research_checks_passed_requires_both_success(self) -> None:
        checks = [
            {"name": "Research quality (PR) / research-lint", "conclusion": "SUCCESS"},
            {"name": "Research quality (PR) / cloud-prompt-sync", "conclusion": "SUCCESS"},
        ]
        self.assertTrue(research_checks_passed(checks))

    def test_research_checks_passed_accepts_skipped(self) -> None:
        checks = [
            {"name": "research-lint", "conclusion": "SKIPPED"},
            {"name": "cloud-prompt-sync", "conclusion": "SUCCESS"},
        ]
        self.assertTrue(research_checks_passed(checks))

    def test_research_checks_passed_rejects_pending(self) -> None:
        checks = [
            {"name": "Research quality (PR) / research-lint", "conclusion": "SUCCESS"},
            {"name": "Research quality (PR) / cloud-prompt-sync", "status": "IN_PROGRESS"},
        ]
        self.assertFalse(research_checks_passed(checks))

    def test_format_research_check_status(self) -> None:
        checks = [
            {"name": "Research quality (PR) / research-lint", "conclusion": "FAILURE"},
            {"name": "Research quality (PR) / cloud-prompt-sync", "conclusion": "SUCCESS"},
        ]
        self.assertEqual(
            format_research_check_status(checks),
            "research-lint=FAILURE, cloud-prompt-sync=SUCCESS",
        )


if __name__ == "__main__":
    unittest.main()
