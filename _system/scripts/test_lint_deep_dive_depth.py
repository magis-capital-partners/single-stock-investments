#!/usr/bin/env python3
"""Tests for deep_dive_depth_common scoring."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deep_dive_depth_common import PASS_SCORE, score_dive

GOLD_SNIPPET = """
## Executive summary

We expect **12.5%** per year from owner cash at today's price over seven years.

## Primary sources reviewed

| Tier | Period / type | Path | Role in this report |
|------|---------------|------|---------------------|
| full | FY2025 10-K | CO/10-K_2025.pdf | Revenue and segments |
| partial | Q1 10-Q | CO/10-Q_2026.pdf | Latest quarter |

## Business & moat

Run-rate owner cash excludes one-off restructuring charges from FY2024.

#### Operating snapshot

| Metric | Latest | Prior | Path |
|--------|--------|-------|------|
| Revenue | $100M | $90M | 10-K |
| Op income | $40M | $35M | 10-K |
| FCF | $30M | $28M | 10-K |
| Cash | $50M | $45M | 10-K |
| Debt | $10M | $12M | 10-K |
| Shares | 10M | 10M | 10-K |
| Margin | 40% | 39% | 10-K |
| ROIC | 15% | 14% | 10-K |

### Mental models

| Model | Source | Application |
|-------|--------|-------------|
| Munger moat | CO/10-K_2025.pdf | Pricing power |
| Lawrence IRR | research/valuation.json | Base case |
| Pabrai dhando | approved list | Downside |

#### Option scan

| Question | Answer |
|----------|--------|
| Q1 | Yes — land option |
| Q2 | No |
| Q3 | Partial |
| Q4 | No |
| Q5 | Yes |
| Q6 | No |
| Q7 | Watch |
| Q8 | N/A |

#### Thesis pillars

| Pillar | Mechanism | Evidence |
|--------|-----------|----------|
| Growth | Reinvest at high ROIC | 10-K segment note |
| Moat | Switching costs | 10-K |
| Capital | Buybacks | 10-Q |

No fieldwork visit yet; management call would upgrade conviction.

## Risks & inversion

**Primary risk:** Regulation on water disposal (10-K risk factors).

- Permit delays could slow growth (10-K)
- Cycle downturn in Permian (10-Q)
- Special dividend may not repeat (10-K)

## Valuation & IRR (assumption ledger)

### Assumption ledger (base case)

| Input | Value | Source |
|-------|-------|--------|
| Price | $50 | market |
| FCF/sh | $2 | 10-K |
| g1 | 8% | Assumption |
| g2 | 5% | Assumption |
| Years | 7 | framework |
| Exit | 20x | Assumption |
| Tax | 21% | Assumption |
| Shares | 10M | 10-K |

#### IRR arithmetic (show your work)

1. Start FCF per share $2.
2. Grow years 1–5 at 8%.
3. Terminal value at year 7.
4. Sum to payoff per share.
5. IRR vs price $50.

**Returns statement:** **12.5%** per year (base Lawrence).

## Classification

| Field | Value |
|-------|-------|
| Implied 7yr IRR | 12.5% |
"""


class DepthScoreTests(unittest.TestCase):
    def test_gold_snippet_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "TST" / "research"
            research.mkdir(parents=True)
            dive = research / "deep_dive_2026-06-04.md"
            dive.write_text(
                "---\nAdversarial: adversarial_2026-06-04.md\n---\n" + GOLD_SNIPPET,
                encoding="utf-8",
            )
            (research / "adversarial_2026-06-04.md").write_text("# Milly\n", encoding="utf-8")
            # score_dive uses ROOT from common module — patch path parent for ticker extraction only
            result = score_dive(dive)
            self.assertGreaterEqual(result.total, PASS_SCORE)
            self.assertIn(result.grade, ("gold", "adequate"))


if __name__ == "__main__":
    unittest.main()
