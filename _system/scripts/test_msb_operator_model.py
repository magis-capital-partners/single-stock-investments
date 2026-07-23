#!/usr/bin/env python3
"""Offline tests for MSB royalty parse + operator model."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import parse_msb_royalty_report as parse  # noqa: E402
import build_msb_operator_model as build  # noqa: E402

FIXTURE = """
<html><body>
<p>On April 30, 2026, the Trustees of Mesabi Trust received the quarterly royalty report
of iron ore shipments from Silver Bay, Minnesota during the quarter ended March 31, 2026
from Cleveland-Cliffs Inc.</p>
<p>Mesabi Trust was credited with a base royalty of $1,201,501. For the three months ended
March 31, 2026, Mesabi Trust was also credited with a bonus royalty in the amount of $0 (zero).
Cliffs reported that all deemed shipments were below the 2026 adjusted bonus royalty
threshold of $71.70 per ton.</p>
<p>In the first calendar quarter of 2026, Cliffs credited Mesabi Trust with 938,572 tons of
iron ore shipped, as compared to 457,728 tons shipped during the first calendar quarter of 2025.</p>
</body></html>
"""


def test_parse_fixture():
    row = parse.parse_royalty_html(FIXTURE, source_path="fixture.htm")
    assert row["tons_shipped"] == 938572
    assert row["base_royalty_usd"] == 1201501.0
    assert row["bonus_royalty_usd"] == 0.0
    assert row["bonus_threshold_usd"] == 71.70
    assert row["period_end"] == "2026-03-31"
    assert row["bonus_on"] is False
    assert row["in_base_irr"] is False


def test_find_live_exhibit_if_present():
    path = parse.find_latest_royalty_exhibit()
    if path is None:
        return
    row = parse.parse_royalty_html(
        path.read_text(encoding="utf-8", errors="ignore"),
        source_path=str(path.relative_to(ROOT)),
    )
    assert row["tons_shipped"] > 0
    assert row["bonus_threshold_usd"] > 0


def test_theme_config_has_iron_ore_steel():
    cfg = Path(ROOT / "_system" / "scripts" / "theme_panel_config.json")
    text = cfg.read_text(encoding="utf-8")
    assert "iron_ore_steel" in text
    assert "iron_ore_spot_usd" in text
    assert "clf_steel_shipments_q_mtons" in text


def test_holdings_theme_tags_msb():
    import json

    ht = json.loads(
        (ROOT / "_system" / "portfolio" / "holdings_themes.json").read_text(encoding="utf-8")
    )
    tickers = ((ht.get("themes") or {}).get("iron_ore_steel") or {}).get("tickers") or []
    assert "MSB" in tickers


def test_build_model_smoke():
    import subprocess

    subprocess.run(
        [sys.executable, str(ROOT / "_system" / "scripts" / "parse_msb_royalty_report.py"), "--write"],
        cwd=ROOT,
        check=False,
    )
    model = build.build_model()
    assert model["ticker"] == "MSB"
    assert model["in_base_irr"] is False
    assert model["royalty"]["tons_shipped"] == 938572
    assert model["transmission"]["bonus_switch"] == "off"


if __name__ == "__main__":
    test_parse_fixture()
    test_find_live_exhibit_if_present()
    test_theme_config_has_iron_ore_steel()
    test_holdings_theme_tags_msb()
    test_build_model_smoke()
    print("test_msb_operator_model: ok")
