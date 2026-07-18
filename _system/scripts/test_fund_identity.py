#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from fund_identity import consolidate_letter_funds, consolidate_letter_funds_stable, identity_core  # noqa: E402


def letter(fund_id: str, fund: str, quarter: str) -> dict:
    return {"fund_id": fund_id, "fund": fund, "quarter": quarter, "positions": []}


class FundIdentityTests(unittest.TestCase):
    def test_bounded_fixed_point_keeps_unique_result(self):
        rows = [
            {"fund_id": "jpmorgan-asset", "fund": "JPMorgan Asset", "quarter": "2020Q1"},
            {"fund_id": "jpmorgan-asset", "fund": "JPMorgan Asset", "quarter": "2020Q2"},
            {"fund_id": "jpmorgan-asset-guide", "fund": "JPMorgan Asset Guide", "quarter": "2020Q1"},
            {"fund_id": "jpmorgan-asset-guide", "fund": "JPMorgan Asset Guide", "quarter": "2020Q2"},
            {"fund_id": "jpmorgan-asset-guide-to", "fund": "JPMorgan Asset Guide To", "quarter": "2020Q3"},
        ]
        bounded_audit = {
            "canonical_profiles": 3,
            "profiles_consolidated": 2,
            "residual_redundancy_groups": 0,
            "idempotent": False,
        }
        with patch("fund_identity.consolidate_letter_funds", return_value=(rows, bounded_audit)):
            merged, audit = consolidate_letter_funds_stable(rows, max_passes=1)
        self.assertEqual(audit["residual_redundancy_groups"], 0)
        self.assertTrue(audit.get("convergence_limit_reached"))
        self.assertEqual(len(merged), len(rows))

    def test_period_date_hash_and_ordinal_noise(self) -> None:
        variants = [
            "Breach Inlet 1q18",
            "Breach Inlet Q120",
            "Breach Inlet 2018Q3 30b89e2c7e",
            "Breach Inlet Fourth Quarter Letter",
            "Breach Inlet Dec-2024 Final",
        ]
        self.assertEqual({identity_core(value, value) for value in variants}, {"breach-inlet"})

    def test_repeated_prefix_absorbs_titled_letters(self) -> None:
        rows = [
            letter("kedm", "KEDM", "2024Q1"),
            letter("kedm", "KEDM", "2024Q2"),
            letter("kedm", "KEDM", "2024Q3"),
            letter("kedm-trading-ipos", "KEDM Trading IPOs", "2025Q1"),
            letter("kedm-energy", "KEDM Reflections on Energy", "2025Q2"),
        ]
        merged, audit = consolidate_letter_funds(rows)
        self.assertEqual({row["fund_id"] for row in merged}, {"kedm"})
        self.assertEqual(audit["canonical_profiles"], 1)

    def test_generic_single_word_does_not_merge_distinct_funds(self) -> None:
        rows = [
            letter("north", "North", "2023Q1"),
            letter("north", "North", "2023Q2"),
            letter("north", "North", "2023Q3"),
            letter("north-tide", "North Tide", "2023Q1"),
            letter("north-peak", "North Peak", "2023Q2"),
        ]
        merged, _audit = consolidate_letter_funds(rows)
        self.assertEqual({row["fund_id"] for row in merged}, {"north", "north-tide", "north-peak"})

    def test_spacing_and_safe_spelling_variants_merge(self) -> None:
        rows = [
            letter("longcast", "Longcast", "2022Q1"),
            letter("longcast", "Longcast", "2022Q2"),
            letter("longcast", "Longcast", "2022Q3"),
            letter("long-cast", "Long Cast", "2022Q4"),
            letter("curreen", "Curreen", "2023Q1"),
            letter("curreen", "Curreen", "2023Q2"),
            letter("curreen", "Curreen", "2023Q3"),
            letter("cureen", "Cureen", "2023Q4"),
        ]
        merged, audit = consolidate_letter_funds(rows)
        self.assertEqual(len({row["fund_id"] for row in merged}), 2)
        self.assertEqual(audit["residual_redundancy_groups"], 0)

    def test_roman_numbered_products_do_not_fuzzy_merge(self) -> None:
        rows = [
            letter("contrarian-cof-ii", "Contrarian COF II", "2023Q1"),
            letter("contrarian-cof-ii", "Contrarian COF II", "2023Q2"),
            letter("contrarian-cof-ii", "Contrarian COF II", "2023Q3"),
            letter("contrarian-cof-iii", "Contrarian COF III", "2023Q4"),
        ]
        merged, _audit = consolidate_letter_funds(rows)
        self.assertEqual(len({row["fund_id"] for row in merged}), 2)

    def test_version_named_fund_is_not_erased(self) -> None:
        self.assertEqual(identity_core("v3-ni", "V3 NI"), "v3-ni")

    def test_clean_display_name_never_keeps_period_debris(self) -> None:
        rows = [
            letter("braeside-q120", "Braeside Q120", "2020Q1"),
            letter("braeside-l-p-to", "Braeside L.p. To", "2020Q2"),
        ]
        merged, audit = consolidate_letter_funds(rows)
        self.assertEqual({row["fund"] for row in merged}, {"Braeside"})
        self.assertTrue(audit["idempotent"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
