#!/usr/bin/env python3
"""Tests for commodity merge eligibility (no copper leak on brokers)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from fetch_market_inputs import (  # noqa: E402
    commodities_for_ticker,
    strip_copper_from_valuation,
    strip_copper_market_inputs_file,
)


def test_mrsh_not_copper_eligible():
    val = {"ticker": "MRSH", "method": "full", "classification_inputs": {"payoff_lens": "operating"}}
    assert commodities_for_ticker("MRSH", val) == []


def test_kewl_copper_eligible():
    val = {"evidence_refresh": {"type": "commodity_nav", "commodity": "copper"}}
    assert commodities_for_ticker("KEWL", val) == ["copper"]


def test_msb_is_iron_ore_royalty_not_copperwood():
    val = {"ticker": "MSB", "classification_inputs": {"archetype": "resource"}}
    assert commodities_for_ticker("MSB", val) == []


def test_strip_copper():
    val = {
        "inputs": {"price": 100, "copper_spot_usd_per_lb": 6.5},
        "market_inputs": {"copper": {"spot": 6.5}},
        "optionality_gate": {"copperwood_option_yield_pct": 7.0, "primary_metric": "lawrence_base"},
    }
    assert strip_copper_from_valuation(val) is True
    assert "copper_spot_usd_per_lb" not in val["inputs"]
    assert "market_inputs" not in val
    assert "copperwood_option_yield_pct" not in val["optionality_gate"]


def test_strip_orphan_market_inputs():
    import tempfile

    import fetch_market_inputs as mod

    ticker = "MRSH"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        research = root / ticker / "research"
        research.mkdir(parents=True)
        mi = research / "market_inputs.json"
        mi.write_text(
            '{"market_inputs":{"copper":{"spot":6.5},"scenario_grid":{"base":{}}}}',
            encoding="utf-8",
        )
        (research / "valuation.json").write_text(
            '{"ticker":"MRSH","inputs":{"price":100}}',
            encoding="utf-8",
        )
        old_root = mod.ROOT
        mod.ROOT = root
        try:
            assert strip_copper_market_inputs_file(ticker) is True
            assert not mi.exists()
        finally:
            mod.ROOT = old_root


if __name__ == "__main__":
    test_mrsh_not_copper_eligible()
    test_kewl_copper_eligible()
    test_msb_is_iron_ore_royalty_not_copperwood()
    test_strip_copper()
    test_strip_orphan_market_inputs()
    print("OK test_fetch_market_inputs")
