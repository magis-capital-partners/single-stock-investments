#!/usr/bin/env python3
"""Tests for the separation checks in lint_deep_dive (special_situation_lens.md § Separations).

Fixtures live in a temp tree shaped like {TICKER}/research/, so lint_file reads the
fixture's own valuation.json rather than a repo ticker.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deep_dive_depth_common import score_dive
from lint_deep_dive import EVENT_WINDOW_END_ERROR_FROM, lint_file

CLASSIFICATION_FOOTER = """
## Classification

| Field | Value |
|-------|-------|
| **Archetype** (Stahl) | {archetype} |
| **Payoff lens** | event |
| Implied 7yr IRR | 12.0% |

## [HUMAN REVIEW]
"""

WHO_MUST_SELL = """
#### Who must sell

| Seller class | Shares or % float | Window | Source | Confidence |
|--------------|-------------------|--------|--------|------------|
| Arbitrageurs unwinding (SpinCo) | 3.4% of float | 2026-11-02 to 2026-11-20 | flow sepflow:x | estimate |
"""

CATALYST_PATH = """
#### Catalyst path

| Date | Step |
|------|------|
| 2026-11-02 | Settlement |
"""


def dive_text(*, why_extra: str = "", body_extra: str = "", archetype: str = "holding_co") -> str:
    return (
        "## What this business is\n\nA parent mid split-off.\n\n"
        "## Why the market might be wrong\n\nForced sellers.\n" + why_extra + "\n"
        "## Executive summary\n\nWe expect **12.0%** per year.\n\n"
        "## Business & moat\n\n### Mental models\n\n| Model | Finding | Source |\n|---|---|---|\n| x | y | z |\n\n"
        + body_extra
        + "\n## Payoff & return\n\nGates.\n\n"
        "## Risks & inversion\n\n**Primary risk:** terms change.\n\n"
        "## Valuation & IRR (assumption ledger)\n\n### Assumption ledger (base case)\n\n"
        "| Input | Value | Source |\n|---|---|---|\n| Price | $10 | market |\n\n"
        "#### IRR arithmetic (show your work)\n\n1. Step.\n\n"
        "**Upside / downside from price:** +10% / -5%\n"
        + CLASSIFICATION_FOOTER.format(archetype=archetype)
    )


class _Fixture:
    def __init__(self, tmp: str, *, date: str, text: str, valuation: dict | None) -> None:
        self.research = Path(tmp) / "TST" / "research"
        self.research.mkdir(parents=True)
        self.dive = self.research / f"deep_dive_{date}.md"
        self.dive.write_text(text, encoding="utf-8")
        if valuation is not None:
            (self.research / "valuation.json").write_text(
                json.dumps(valuation), encoding="utf-8"
            )

    def lint(self, *, strict: bool = False) -> tuple[list[str], list[str]]:
        return lint_file(self.dive, legacy=False, strict=strict)


def _has(messages: list[str], needle: str) -> bool:
    return any(needle in m for m in messages)


EVENT_VAL = {"classification_inputs": {"archetype": "holding_co", "payoff_lens": "event"}}


class EventWindowEndTests(unittest.TestCase):
    def test_event_lens_without_dated_end_errors_on_new_dive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(), valuation=EVENT_VAL)
            errors, warnings = fx.lint()
            self.assertTrue(_has(errors, "event lens without a dated end"))
            self.assertFalse(_has(warnings, "event lens without a dated end"))

    def test_event_lens_without_dated_end_warns_on_pre_cutoff_dive(self) -> None:
        self.assertEqual(EVENT_WINDOW_END_ERROR_FROM, "2026-10-11")
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-07-24", text=dive_text(), valuation=EVENT_VAL)
            errors, warnings = fx.lint()
            self.assertTrue(_has(warnings, "event lens without a dated end"))
            self.assertFalse(_has(errors, "event lens without a dated end"))

    def test_event_window_end_in_classification_inputs_passes(self) -> None:
        val = {"classification_inputs": {**EVENT_VAL["classification_inputs"], "event_window_end": "2026-11-20"}}
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(), valuation=val)
            errors, warnings = fx.lint()
            self.assertFalse(_has(errors + warnings, "event lens without a dated end"))

    def test_event_window_end_in_separation_block_passes(self) -> None:
        val = {
            **EVENT_VAL,
            "separation": {"separation_id": "sep:x", "role": "parent", "kind": "split_off",
                           "event_window_end": "2026-11-20"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(why_extra=WHO_MUST_SELL), valuation=val)
            errors, warnings = fx.lint()
            self.assertFalse(_has(errors + warnings, "event lens without a dated end"))

    def test_operating_lens_is_untouched(self) -> None:
        val = {"classification_inputs": {"archetype": "compounder", "payoff_lens": "operating"}}
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(archetype="compounder"), valuation=val)
            errors, warnings = fx.lint()
            self.assertFalse(_has(errors + warnings, "event lens without a dated end"))


SEP_VAL = {
    **EVENT_VAL,
    "separation": {"separation_id": "sep:x", "role": "spinco", "kind": "spin_off",
                   "event_window_end": "2026-12-15", "research_only": True,
                   "in_base_irr": False, "authority": "none"},
}


class WhoMustSellTests(unittest.TestCase):
    def test_separation_block_requires_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(), valuation=SEP_VAL)
            errors, _ = fx.lint()
            self.assertTrue(_has(errors, "missing #### Who must sell"))

    def test_table_present_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(why_extra=WHO_MUST_SELL), valuation=SEP_VAL)
            errors, _ = fx.lint()
            self.assertFalse(_has(errors, "Who must sell"))

    def test_no_separation_block_no_requirement(self) -> None:
        val = {"classification_inputs": {**EVENT_VAL["classification_inputs"], "event_window_end": "2026-11-20"}}
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(), valuation=val)
            errors, _ = fx.lint()
            self.assertFalse(_has(errors, "Who must sell"))

    def test_depth_common_mirrors_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(), valuation=SEP_VAL)
            result = score_dive(fx.dive, archetype_strict=True)
            self.assertTrue(_has(result.archetype_errors, "Who must sell"))


class SpreadBasisTests(unittest.TestCase):
    SPREAD_LINE = "\nThe offer carries an annualized spread of 14.2% to settlement.\n"
    SPREAD_LINE_ALT = "\nA 9% annualised exchange spread remains.\n"

    def test_spread_without_filed_formula_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12",
                          text=dive_text(why_extra=WHO_MUST_SELL + self.SPREAD_LINE), valuation=SEP_VAL)
            errors, _ = fx.lint()
            self.assertTrue(_has(errors, "spread without a filed formula"))

    def test_percent_before_phrase_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12",
                          text=dive_text(why_extra=WHO_MUST_SELL + self.SPREAD_LINE_ALT), valuation=SEP_VAL)
            errors, _ = fx.lint()
            self.assertTrue(_has(errors, "spread without a filed formula"))

    def test_spread_with_no_valuation_block_at_all_errors(self) -> None:
        val = {"classification_inputs": {**EVENT_VAL["classification_inputs"], "event_window_end": "2026-11-20"}}
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(why_extra=self.SPREAD_LINE), valuation=val)
            errors, _ = fx.lint()
            self.assertTrue(_has(errors, "spread without a filed formula"))

    def test_filed_basis_allows_spread(self) -> None:
        for basis in ("filing_formula", "final_filed"):
            val = {**SEP_VAL, "separation": {**SEP_VAL["separation"], "spread_basis": basis}}
            with tempfile.TemporaryDirectory() as tmp:
                fx = _Fixture(tmp, date="2026-10-12",
                              text=dive_text(why_extra=WHO_MUST_SELL + self.SPREAD_LINE), valuation=val)
                errors, _ = fx.lint()
                self.assertFalse(_has(errors, "spread without a filed formula"), basis)

    def test_annualized_return_is_not_a_spread(self) -> None:
        line = "\n**Low/base/high annualized return at price:** -9.78% / 14.54% / 32.66%\n"
        val = {"classification_inputs": {**EVENT_VAL["classification_inputs"], "event_window_end": "2026-11-20"}}
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(body_extra=line), valuation=val)
            errors, _ = fx.lint()
            self.assertFalse(_has(errors, "spread without a filed formula"))

    def test_phrase_without_percent_is_not_flagged(self) -> None:
        line = "\nThe annualized spread is not shown until the formula is filed.\n"
        val = {"classification_inputs": {**EVENT_VAL["classification_inputs"], "event_window_end": "2026-11-20"}}
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(body_extra=line), valuation=val)
            errors, _ = fx.lint()
            self.assertFalse(_has(errors, "spread without a filed formula"))


class SpecialSituationArchetypeTests(unittest.TestCase):
    VAL = {"classification_inputs": {"archetype": "special_situation", "payoff_lens": "event",
                                     "event_window_end": "2026-11-20"}}

    def test_footer_archetype_requires_catalyst_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(archetype="special_situation"),
                          valuation=self.VAL)
            errors, _ = fx.lint()
            self.assertTrue(_has(errors, "special_situation — missing #### Catalyst path"))

    def test_valuation_archetype_alone_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(archetype="holding_co"), valuation=self.VAL)
            errors, _ = fx.lint()
            self.assertTrue(_has(errors, "special_situation — missing #### Catalyst path"))

    def test_catalyst_path_satisfies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12",
                          text=dive_text(archetype="special_situation", body_extra=CATALYST_PATH),
                          valuation=self.VAL)
            errors, _ = fx.lint()
            self.assertFalse(_has(errors, "special_situation — missing"))

    def test_depth_common_strict_mirrors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(archetype="special_situation"),
                          valuation=self.VAL)
            result = score_dive(fx.dive, archetype_strict=True)
            self.assertTrue(_has(result.archetype_errors, "special_situation: missing #### Catalyst path"))
            relaxed = score_dive(fx.dive)
            self.assertEqual(relaxed.archetype_errors, [])


class FixtureOutsideRootTests(unittest.TestCase):
    def test_lint_file_accepts_paths_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = _Fixture(tmp, date="2026-10-12", text=dive_text(), valuation=None)
            errors, warnings = fx.lint()
            self.assertIsInstance(errors, list)
            self.assertIsInstance(warnings, list)


if __name__ == "__main__":
    unittest.main()
