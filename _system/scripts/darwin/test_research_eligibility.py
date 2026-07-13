"""Regression checks for the versioned deep-dive-only IRA policy."""
from __future__ import annotations

import unittest

from darwin.policies import ira_marvin_ineligible, policy_ira_marvin
from darwin.research_eligibility import research_status
from darwin.constraints import apply_research_freshness_caps


MANDATE = {
    "min_irr_pct_for_weight": 6.0,
    "current_deep_dive_days": 120,
    "stale_deep_dive_days": 180,
    "max_names": 12,
}


def row(ticker: str, *, irr: float | None, days: int | None, stance: str = "watch") -> dict:
    return {
        "ticker": ticker,
        "irr_falsifier_pct": irr,
        "deep_dive_date": "2026-06-01" if days is not None else None,
        "days_since_deep_dive": days,
        "classification": {"stance": stance},
    }


class ResearchEligibilityTests(unittest.TestCase):
    def test_stance_does_not_change_eligibility_or_rank(self) -> None:
        rows = [
            row("WATCH", irr=12.0, days=30, stance="watch"),
            row("EXIT", irr=10.0, days=30, stance="exit"),
        ]
        self.assertEqual(policy_ira_marvin(rows, MANDATE), {"WATCH": 12.0 / 22.0, "EXIT": 10.0 / 22.0})

    def test_no_deep_dive_or_adjusted_irr_cannot_allocate(self) -> None:
        rows = [row("NO_DIVE", irr=12.0, days=None), row("NO_IRR", irr=None, days=30)]
        self.assertEqual(ira_marvin_ineligible(rows, MANDATE), ["NO_DIVE", "NO_IRR"])
        self.assertEqual(policy_ira_marvin(rows, MANDATE), {})

    def test_freshness_and_minimum_irr_states_are_deterministic(self) -> None:
        self.assertEqual(research_status(row("CURRENT", irr=8.0, days=120), MANDATE), "current")
        self.assertEqual(research_status(row("AGING", irr=8.0, days=121), MANDATE), "aging")
        self.assertEqual(research_status(row("STALE", irr=8.0, days=181), MANDATE), "research_stale")
        self.assertEqual(research_status(row("LOW", irr=5.99, days=30), MANDATE), "irr_below_minimum")

    def test_research_caps_leave_cash_instead_of_overweighting_thin_book(self) -> None:
        rows = [row(f"T{i}", irr=10.0, days=30) for i in range(4)]
        weights, cash = apply_research_freshness_caps(
            {r["ticker"]: 0.25 for r in rows},
            {r["ticker"]: r for r in rows},
            {"mandate": MANDATE},
        )
        self.assertEqual(weights, {r["ticker"]: 0.15 for r in rows})
        self.assertAlmostEqual(cash, 0.40)


if __name__ == "__main__":
    unittest.main()
