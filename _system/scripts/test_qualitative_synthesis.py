#!/usr/bin/env python3
"""Tests for qualitative synthesis ladder and primary path rebuild."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from valuation_synthesis import (  # noqa: E402
    AUTO_QUAL_PP_CAP,
    _default_qualitative,
    _needs_primary_path_rebuild,
    compute_synthesis,
)


def _base_data() -> dict:
    return {
        "ticker": "TEST",
        "method": "full",
        "classification_inputs": {
            "dhando": "partial",
            "moat": "stable",
            "predictive_attribute": "none",
        },
        "implied_return": {"falsifier_adjusted_pct": 3.2},
        "results_lawrence_legacy": {
            "bear": {"return_pct": -2.0},
            "bull": {"return_pct": 8.0},
        },
        "synthesis": {
            "paths": [
                {
                    "id": "scenario_bear",
                    "return_pct": -2.0,
                    "weight": 0.05,
                    "type": "numeric",
                },
                {
                    "id": "scenario_bull",
                    "return_pct": 8.0,
                    "weight": 0.12,
                    "type": "numeric",
                },
            ],
        },
    }


def test_no_hk_no_partial_dhando_pp():
    qual = _default_qualitative(_base_data(), "TEST", _base_data()["synthesis"]["paths"])
    ids = {q["id"] for q in qual}
    assert "partial_dhando_hk_nav" not in ids
    assert "no_predictive_attribute" in ids


def test_needs_primary_rebuild():
    assert _needs_primary_path_rebuild(_base_data()["synthesis"]["paths"], _base_data())


def test_positive_pp_requires_anchor():
    data = _base_data()
    paths = [
        {
            "id": "filing_falsifier",
            "return_pct": 3.2,
            "weight": 0.3,
            "type": "numeric",
        }
    ]
    qual = _default_qualitative(data, "TEST", paths)
    assert all(q["id"] != "partial_dhando_hk_nav" for q in qual)


def test_8697_recompute():
    path = ROOT / "8697.T" / "research" / "valuation.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    compute_synthesis(data)
    qual = data["synthesis"].get("qualitative_adjustments") or []
    ids = {q.get("id") for q in qual}
    assert "partial_dhando_hk_nav" not in ids
    path_ids = {p.get("id") for p in data["synthesis"].get("paths") or []}
    assert "filing_falsifier" in path_ids
    assert abs(data["synthesis"]["qualitative_pp"]) <= AUTO_QUAL_PP_CAP + 0.01


def main() -> int:
    test_no_hk_no_partial_dhando_pp()
    test_needs_primary_rebuild()
    test_positive_pp_requires_anchor()
    test_8697_recompute()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
