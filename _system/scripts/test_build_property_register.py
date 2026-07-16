#!/usr/bin/env python3
"""Unit tests for property register validation and reconciliation."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_property_register as mod  # noqa: E402


def _sample_reg() -> dict:
    return {
        "schema_version": 1,
        "ticker": "DEMO",
        "as_of": "2026-03-31",
        "properties": [
            {
                "id": "parcel-a",
                "name": "Parcel A",
                "type": "land",
                "status": "held",
                "nav_overlay_line": "land_bucket",
                "carrying_value_usd": 40_000_000,
                "estimated_fair_value_usd": {"low": 35_000_000, "base": 40_000_000, "high": 45_000_000},
            },
            {
                "id": "parcel-b",
                "name": "Parcel B",
                "type": "land",
                "status": "held",
                "nav_overlay_line": "land_bucket",
                "carrying_value_usd": 60_000_000,
                "estimated_fair_value_usd": {"base": 60_000_000},
            },
        ],
    }


def _sample_val() -> dict:
    return {
        "inputs": {"shares_outstanding": 10_000_000},
        "nav_overlay": {
            "lines": [
                {"id": "land_bucket", "carrying_value_m": 100.0, "per_share": 10.0},
            ],
            "segments_or_options": [
                {"id": "water", "nav_per_share": 1.5},
            ],
            "gaap_vs_fair_value": {
                "real_estate_investment_net_m": 250.0,
                "acres_disclosed": 1000,
            },
        },
    }


def test_schema_ok():
    errors = mod.validate_schema(_sample_reg(), "DEMO")
    assert errors == []


def test_schema_rejects_bad_type():
    reg = _sample_reg()
    reg["properties"][0]["type"] = "spaceship"
    errors = mod.validate_schema(reg, "DEMO")
    assert any("invalid type" in e for e in errors)


def test_reconcile_match():
    recon = mod.reconcile(_sample_reg(), _sample_val())
    assert recon["ok"] is True
    assert recon["total_fair_value_usd"] == 100_000_000
    assert recon["lines"][0]["status"] == "ok"


def test_reconcile_mismatch():
    reg = _sample_reg()
    reg["properties"][0]["estimated_fair_value_usd"]["base"] = 10_000_000
    recon = mod.reconcile(reg, _sample_val())
    assert recon["ok"] is False
    assert recon["lines"][0]["status"] == "mismatch"


def test_gaap_and_segment_targets():
    targets = mod.build_targets(_sample_val())
    assert "land_bucket" in targets
    assert targets["gaap:real_estate_investment_net_m"]["target_usd"] == 250_000_000
    assert "acres_disclosed" not in "".join(targets)
    assert targets["water"]["target_usd"] == 15_000_000  # 1.5 × 10M shares


def test_process_ticker_writes_summary():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        research = root / "DEMO" / "research"
        research.mkdir(parents=True)
        (research / "properties.json").write_text(json.dumps(_sample_reg()), encoding="utf-8")
        (research / "valuation.json").write_text(json.dumps(_sample_val()), encoding="utf-8")
        old = mod.ROOT
        mod.ROOT = root
        try:
            result = mod.process_ticker("DEMO", write=True)
        finally:
            mod.ROOT = old
        assert result["ok"] is True
        val = json.loads((research / "valuation.json").read_text(encoding="utf-8"))
        assert val["property_register"]["property_count"] == 2
        assert val["property_register"]["status"] == "ok"


if __name__ == "__main__":
    test_schema_ok()
    test_schema_rejects_bad_type()
    test_reconcile_match()
    test_reconcile_mismatch()
    test_gaap_and_segment_targets()
    test_process_ticker_writes_summary()
    print("ok")
