#!/usr/bin/env python3
"""Index-change insight direction follows the modelled float flow, not the verb.

Horizon Kinetics: a Russell 2000 -> Russell 1000 graduation is net SELLING
(APLD, June 2026: -6.4% of float base), so ``action == "add"`` must not read
bullish when ``float_impact`` says otherwise.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_insights as bi  # noqa: E402


def _ev(index: str, action: str = "add", **extra) -> dict:
    row = {
        "ticker": "APLD",
        "index": index,
        "action": action,
        "announced": "2026-07-02",
        "effective": "2026-06-26",
        "source_url": "https://example.test/apld",
        "confidence": "news_unconfirmed",
        "quality_gated": True,
        "title": f"APLD {action} {index}",
    }
    row.update(extra)
    return row


def _fi_event(index: str, pct: float, action: str = "add", source: str = "confirmed", **extra) -> dict:
    ev = {
        "ticker": "APLD",
        "primary_index": index,
        "action": action,
        "status": "ok",
        "pct_of_float_base": pct,
        "event_source": source,
    }
    ev.update(extra)
    return ev


class IndexEventDirectionTests(unittest.TestCase):
    def _doc(self, row: dict) -> dict:
        return {"as_of": "2026-10-09", "by_ticker": {"APLD": row}}

    def test_r1000_graduation_is_bearish(self):
        graduation = _fi_event("russell_1000", -6.436, is_russell_breakpoint_migration=True)
        row = {
            "confirmed_events": [_ev("russell_1000")],
            "float_impact": {"events": [graduation, _fi_event("sp400", 5.0, source="candidate")], "primary": graduation},
        }
        recs = bi.from_index_membership(self._doc(row))
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["direction"], "bearish")
        self.assertEqual(rec["index_action"], "add")
        self.assertAlmostEqual(rec["float_pct_of_float_base"], -6.436)
        self.assertIn("-6.44% of float", rec["claim"])

    def test_positive_flow_add_is_bullish(self):
        sp400 = _fi_event("sp400", 5.0)
        row = {
            "confirmed_events": [_ev("sp400", confidence="provider_confirmed")],
            "float_impact": {"events": [sp400], "primary": sp400},
        }
        rec = bi.from_index_membership(self._doc(row))[0]
        self.assertEqual(rec["direction"], "bullish")
        self.assertEqual(rec["confidence"], "high")

    def test_zero_flow_is_neutral(self):
        row = {
            "confirmed_events": [_ev("sp600", action="delete")],
            "float_impact": {"events": [_fi_event("sp600", 0.0, action="delete")], "primary": None},
        }
        self.assertEqual(bi.from_index_membership(self._doc(row))[0]["direction"], "neutral")

    def test_matches_event_on_same_index_not_primary(self):
        # primary is the (negative) R1000 graduation, but the confirmed event is
        # the S&P 400 add, whose own stack is positive.
        graduation = _fi_event("russell_1000", -6.436)
        row = {
            "confirmed_events": [_ev("sp400")],
            "float_impact": {
                "events": [graduation, _fi_event("sp400", 5.0, source="candidate")],
                "primary": graduation,
            },
        }
        rec = bi.from_index_membership(self._doc(row))[0]
        self.assertEqual(rec["direction"], "bullish")
        self.assertAlmostEqual(rec["float_pct_of_float_base"], 5.0)

    def test_fallback_to_action_without_float_impact(self):
        row = {"confirmed_events": [_ev("russell_1000"), _ev("sp600", action="delete"), _ev("sp400", action="change")]}
        recs = bi.from_index_membership(self._doc(row))
        self.assertEqual([r["direction"] for r in recs], ["bullish", "bearish", "neutral"])
        self.assertTrue(all(r["float_pct_of_float_base"] is None for r in recs))
        self.assertNotIn("modelled net flow", recs[0]["claim"])

    def test_fallback_when_float_impact_is_for_other_index_or_n_a(self):
        row = {
            "confirmed_events": [_ev("russell_1000")],
            "float_impact": {
                "events": [
                    _fi_event("sp400", -9.0),
                    _fi_event("russell_1000", -6.0, status="n_a"),
                    {"primary_index": "russell_1000", "action": "add", "status": "ok", "pct_of_float_base": None},
                ],
                "primary": _fi_event("sp400", -9.0),
            },
        }
        rec = bi.from_index_membership(self._doc(row))[0]
        self.assertEqual(rec["direction"], "bullish")
        self.assertIsNone(rec["float_pct_of_float_base"])

    def test_live_payload_apld_if_present(self):
        path = ROOT / "dashboard" / "data" / "index_membership.json"
        if not path.exists():
            self.skipTest("dashboard/data/index_membership.json not built")
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        apld = (doc.get("by_ticker") or {}).get("APLD")
        if not apld or not apld.get("confirmed_events"):
            self.skipTest("APLD has no confirmed index events in the committed payload")
        recs = [r for r in bi.from_index_membership({"by_ticker": {"APLD": apld}}) if r["index_id"] == "russell_1000"]
        if not recs:
            self.skipTest("no APLD russell_1000 event")
        self.assertEqual(recs[0]["direction"], "bearish")


if __name__ == "__main__":
    unittest.main()
