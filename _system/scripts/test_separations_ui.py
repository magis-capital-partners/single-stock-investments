#!/usr/bin/env python3
"""Separations UI: the split-offs lane, the ticker card, the odd-lot badge.

Node-backed checks on dashboard/separations-viz.js and the split-off detail row
in dashboard/special-situations-viz.js, plus string checks on the lane wiring in
dashboard/index.html. Payload shapes follow _system/data/separations/README.md
("Dashboard payload", "Per-ticker attach").
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_system" / "scripts" / "separations_node_runner.cjs"
INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def run_node(action: str) -> dict:
    proc = subprocess.run(
        ["node", str(RUNNER), action], cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8"
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


class SeparationsVizTests(unittest.TestCase):
    def test_ticker_card_shows_role_kind_status_counterparty_ends_and_flow(self) -> None:
        html = run_node("card")["html"]
        self.assertIn('class="detail-section separation-card"', html)
        for needle in ("Parent", "Split-off", "Offer open", ">KVUE<", "Settlement 2023-08-23",
                       "-3.4% of float", "1.8 days ADV", "through 2023-09-08", "estimate"):
            self.assertIn(needle, html, needle)
        # the counterparty link lands on the split-offs lane with the ticker in focus
        self.assertIn('href="#/ideas/situations/split-offs/KVUE"', html)
        # the card carries the odd-lot badge when a sleeve is eligible
        self.assertIn("Odd-lot · expires 2023-08-18", html)
        self.assertIn("does not change intrinsic value", html)

    def test_ticker_card_is_empty_without_roles(self) -> None:
        result = run_node("card-empty")
        self.assertEqual(result["none"], "")
        self.assertEqual(result["empty"], "")
        self.assertEqual(result["noroles"], "", "odd-lot alone does not make a card")

    def test_odd_lot_badge_only_when_an_owner_is_eligible(self) -> None:
        result = run_node("badge")
        self.assertIn("Odd-lot · expires 2023-08-18", result["eligible"])
        self.assertIn("odd-lot-badge", result["eligible"])
        self.assertIn("never prefills an order", result["eligible"])
        self.assertEqual(result["none"], "")
        self.assertEqual(result["missing"], "")
        self.assertIn("expiry not stated", result["no_expiry"])

    def test_flow_legs_mirror_the_index_watch_bridge(self) -> None:
        result = run_node("legs")
        full = result["full"]
        self.assertIn('<table class="insights-table"', full)
        self.assertIn("Who must sell · SpinCo KVUE", full)
        self.assertIn("low -2.1% · base -3.4% · high -4.9% of float", full)
        self.assertIn("1.80 days ADV", full)
        self.assertIn("Arb unwind sale", full)
        self.assertIn("-51.0M", full)
        self.assertIn("2023-08-23 → 2023-09-08", full)
        # an n_a leg shows its reason and no invented number
        self.assertIn("Mandate mismatch sale", full)
        self.assertIn("no passive share per name", full)
        self.assertIn("Negative % float = net forced selling", full)
        self.assertIn("no float", result["na"])
        self.assertIn("No flow legs.", result["empty"])
        self.assertIn("no separation flow modelled", result["missing"])

    def test_every_string_field_is_escaped(self) -> None:
        result = run_node("escape")
        for key, html in result.items():
            self.assertNotIn("<img", html, key)
            self.assertNotIn("onerror=", html.replace("onerror=alert(1)&gt;", ""), key)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html, key)


class SpecialSituationsDeskTests(unittest.TestCase):
    def test_split_offs_lane_renders_terms_and_who_must_sell_in_the_open_row(self) -> None:
        result = run_node("desk")
        closed, opened = result["closed"], result["open"]
        self.assertIn("Split-offs and exchange offers · 1", closed)
        self.assertIn("Forced selling is a research trigger", closed, "caption shows on the split-offs lane")
        self.assertNotIn("Exchange terms.", closed, "terms live in the detail row, not the table")
        self.assertIn("Exchange terms.", opened)
        self.assertIn("Exchange at a 7% discount", opened, "terms_summary sits under what")
        for needle in ("Implied ratio", "7.9412", "Realized discount", "+7.00%", "Upper limit binding", ">no<",
                       "Days to settlement", ">12<", "Annualized spread", "+212.9%",
                       "Odd-lot payoff / 99 sh", "$1,177", "Proration (low / base / high)", "15% / 25% / 40% (reference set)",
                       "Who must sell.", "% of float (base)", "-3.4%", "Days of ADV", "2023-08-23 → 2023-09-08", "estimate"):
            self.assertIn(needle, opened, needle)
        self.assertIn("212.9% (7.0% over 12 days)", opened, "annualized_spread string still shown")
        # the existing six columns survive
        self.assertEqual(opened.count("<th>"), 6)
        # an unrelated lane carries neither block, and escapes its company name
        mergers = result["mergers"]
        self.assertNotIn("Exchange terms.", mergers)
        self.assertNotIn("Who must sell.", mergers)
        self.assertIn("&lt;script&gt;", mergers)
        self.assertNotIn("<script>alert", mergers)

    def test_missing_payload_degrades_to_an_empty_state(self) -> None:
        html = run_node("desk-empty")["html"]
        self.assertIn("Nothing ranked in this lane", html)
        self.assertIn("Special situations data 404", html)
        self.assertNotIn("Exchange terms.", html)


class IndexWiringTests(unittest.TestCase):
    def test_split_offs_lane_is_wired_into_ids_slugs_and_route(self) -> None:
        self.assertIn("'split-offs': 'split_offs',", INDEX)
        self.assertIn("split_offs: 'split-offs',", INDEX)
        route = re.search(r"\^#\\/ideas\\/situations\(\?:\\/\(([^)]+)\)\)", INDEX)
        self.assertIsNotNone(route, "situations route regex")
        lanes = route.group(1).split("|")
        self.assertEqual(lanes, ["spinoffs", "split-offs", "mergers", "warrants", "restructurings", "forced-sellers"])
        self.assertIn("forced_sellers: 'forced-sellers',", INDEX)

    def test_separations_script_loads_beside_special_situations(self) -> None:
        tags = re.findall(r'<script src="((?:special-situations|separations)-viz\.js\?v=[^"]+)"></script>', INDEX)
        self.assertEqual(len(tags), 2, tags)
        self.assertTrue(tags[0].startswith("special-situations-viz.js?v="))
        self.assertTrue(tags[1].startswith("separations-viz.js?v="))

    def test_ticker_card_and_odd_lot_badge_are_mounted(self) -> None:
        self.assertIn("SeparationsViz.renderTickerCard(t.separation, { escapeHtml })", INDEX)
        self.assertIn("t.separation?.odd_lot?.eligible_owners?.length", INDEX)
        self.assertIn("SeparationsViz.renderOddLotBadge(t.separation, { escapeHtml })", INDEX)

    def test_separations_payload_is_optional(self) -> None:
        self.assertIn("function loadSeparations()", INDEX)
        self.assertIn("fetch('data/separations.json?'", INDEX)
        self.assertIn(".catch(() => null)", INDEX)
        self.assertIn("value.caption = separations.caption", INDEX)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
