import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_thesis_card


DIVE = """# TEST: Company Deep Dive

## What this business is

Test Co runs toll-road exchanges. It earns fees on every trade.

## Why the market might be wrong

The market prices it as a cyclical. Volumes are structurally rising.

## Valuation & IRR (assumption ledger)

### Assumption ledger (base case)

| Input | Value | Source |
| --- | --- | --- |
| Price today | $100 | `TEST/investor-documents/10K_2025.pdf` p. 3 |
| Starting free cash flow per share | $6 | `TEST/investor-documents/10K_2025.pdf` p. 41 |
| Growth years 1-5 | 8% | [Assumption] |

#### IRR arithmetic (show your work)

1. Step one.

## Classification

| archetype | croupier |

## [HUMAN REVIEW]

- Confirm the fee schedule holds after the 2027 contract reset.
- Validate segment margins against the Q2 filing.

## [PROPOSED MEMORY]

- [PROPOSED STAHL] Croupiers win in volatility.
"""

VALUATION = {
    "ticker": "TEST",
    "as_of": "2026-07-01",
    "lawrence_bucket": "multi_sided",
    "classification_inputs": {"archetype": "croupier", "moat": "stable"},
    "results": {
        "bear": {"return_pct": 3.0},
        "base": {"return_pct": 12.5},
        "bull": {"return_pct": 18.0},
    },
    "implied_return": {"base_pct": 12.5, "label": "7yr IRR"},
    "approved_stance": "hold",
    "human_review": {"approved": True, "approved_date": "2026-07-02"},
}


class ThesisCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        research = root / "TEST" / "research"
        (research / "evidence").mkdir(parents=True)
        (research / "valuation.json").write_text(json.dumps(VALUATION), encoding="utf-8")
        (research / "deep_dive_2026-07-01.md").write_text(DIVE, encoding="utf-8")
        (research / "evidence" / "filing_digest_2026-06-30.md").write_text("digest", encoding="utf-8")
        self.root_patch = patch.object(build_thesis_card, "ROOT", root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_card_carries_thesis_irr_assumptions_and_citations(self):
        card = build_thesis_card.build_card("TEST")
        self.assertIn("toll-road exchanges", card["thesis"])
        self.assertIn("structurally rising", card["why_market_wrong"])
        self.assertEqual(card["base_irr_pct"], 12.5)
        self.assertEqual(card["stance"], "hold")
        self.assertEqual(card["scenarios"], {"bear": 3.0, "base": 12.5, "bull": 18.0})
        self.assertEqual(card["classification"]["lawrence_bucket"], "multi_sided")
        inputs = [row["input"] for row in card["key_assumptions"]]
        self.assertEqual(inputs, ["Price today", "Starting free cash flow per share", "Growth years 1-5"])
        self.assertEqual(len(card["open_questions"]), 2)
        self.assertIn("fee schedule", card["open_questions"][0])
        self.assertEqual(card["evidence_citations"], ["TEST/investor-documents/10K_2025.pdf"])
        self.assertEqual(card["last_verified"]["deep_dive"], "2026-07-01")
        self.assertEqual(card["last_verified"]["human_approved"], "2026-07-02")
        self.assertEqual(card["filing_digest"], "TEST/research/evidence/filing_digest_2026-06-30.md")

    def test_write_card_emits_json_file(self):
        self.assertTrue(build_thesis_card.write_card("TEST"))
        out = build_thesis_card.ROOT / "TEST" / "research" / "thesis_card.json"
        card = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(card["ticker"], "TEST")

    def test_missing_ticker_is_skipped(self):
        self.assertIsNone(build_thesis_card.build_card("NOPE"))


if __name__ == "__main__":
    unittest.main()
