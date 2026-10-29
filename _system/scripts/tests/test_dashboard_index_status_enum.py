#!/usr/bin/env python3
"""The dashboard publisher must accept every index status the builder emits."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_index_membership import STATUS_ENUM  # noqa: E402
from validate_dashboard_data import INDEX_STATUS_ENUM  # noqa: E402


class DashboardIndexStatusEnumTests(unittest.TestCase):
    def test_publisher_accepts_builder_statuses(self):
        self.assertEqual(set(), STATUS_ENUM - INDEX_STATUS_ENUM)


if __name__ == "__main__":
    unittest.main()
