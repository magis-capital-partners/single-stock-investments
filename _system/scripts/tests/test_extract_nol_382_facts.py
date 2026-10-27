"""Locator and limit rules for the Section 382 fact extractor. No network."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import extract_nol_382_facts as facts  # noqa: E402


def test_nearest_section_is_the_income_tax_note() -> None:
    text = (
        "Item 1A. Risk Factors. "
        + ("boilerplate " * 40)
        + "Note 11. Income Taxes. The Company experienced an ownership change in 2019."
    )
    index = text.lower().rfind("ownership change")
    section = facts.nearest_section(text, index)
    assert section is not None
    assert "Income Taxes" in section
    assert "Risk Factors" not in section


def test_page_stays_null_when_the_html_has_no_marker() -> None:
    text = "Note 11. Income Taxes. An ownership change occurred."
    index = text.lower().find("ownership")
    assert facts.nearest_page(text, index) is None


def test_page_uses_a_marker_just_before_the_heading() -> None:
    text = "F-12 Note 11. Income Taxes. An ownership change occurred."
    index = text.lower().find("ownership")
    assert facts.nearest_page(text, index) == "F-12"


def test_stated_limit_ignores_an_unrelated_dollar_amount() -> None:
    passage = (
        "The Company recorded a valuation allowance of $113.7 million. "
        "An ownership change occurred. The filing states no annual limitation amount."
    )
    assert facts.stated_limit_usd(passage) is None


def test_stated_limit_reads_only_a_stated_annual_limitation() -> None:
    passage = "As a result of the ownership change, the annual limitation is $4.2 million."
    assert facts.stated_limit_usd(passage) == 4_200_000


def test_income_tax_heading_accepts_comma_parens_and_numbered_captions() -> None:
    samples = {
        "See Note 15, Income Taxes, to the statements. Note 15, Income Taxes. Deferred.": "note 15, income taxes",
        "Table. (16) Income Taxes Current federal income tax.": "(16) income taxes",
        "11. Income Taxes The Company assesses the allowance.": "11. income taxes",
    }
    for text, expect in samples.items():
        found = facts.find_income_tax_section(text)
        assert found is not None, text
        assert found["section"].lower() == expect
    assert facts.find_income_tax_section("Total income taxes paid $156. 507 Income taxes paid.") is None
    mixed = "(24) Income tax expense. Later (16) Income Taxes Current federal. Year ended 2025. Income Tax."
    found = facts.find_income_tax_section(mixed)
    assert found is not None and found["section"].lower() == "(16) income taxes"


def test_income_tax_heading_is_the_note_not_item_1() -> None:
    text = (
        "Item 1. Financial Statements. Income taxes are discussed later. "
        "Note 11. Income Taxes. The Company maintained a valuation allowance."
    )
    found = facts.find_income_tax_section(text)
    assert found is not None
    assert found["section"].lower().startswith("note 11")
    assert "financial statement" not in found["section"].lower()
    assert found["page"] is None


def test_trigger_prefers_4_99_over_a_round_5() -> None:
    passage = "A person who becomes a 5% stockholder, or who crosses 4.99%, triggers the plan."
    triggers = [float(t) for t in facts.TRIGGER_RE.findall(passage)]
    under_10 = [t for t in triggers if t <= 10.0]
    pill_band = [t for t in under_10 if 4.5 <= t <= 5.0]
    chosen = min(pill_band, key=lambda t: abs(t - 4.99))
    assert chosen == 4.99


def test_income_tax_heading_is_found_without_inventing_a_page() -> None:
    text = "Cover. Note 7 - Income Taxes. Deferred tax assets are described here."
    found = facts.find_income_tax_section(text)
    assert found is not None
    assert "Income Taxes" in found["section"]
    assert found["page"] is None


def test_eight_k_tax_filter_keeps_a_rights_plan_item() -> None:
    assert facts._eight_k_is_tax_or_rights({"items": "1.01,3.03", "description": "Entry"})
    assert facts._eight_k_is_tax_or_rights({"items": "8.01", "description": "Tax Benefits Preservation Plan"})
    assert not facts._eight_k_is_tax_or_rights({"items": "2.02", "description": "Results of Operations"})
