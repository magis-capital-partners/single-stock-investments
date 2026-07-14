#!/usr/bin/env python3
"""Adversarial regression tests for cross-tab classification precision."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_superinvestor_insights as bsi  # noqa: E402
import letter_matching as lm  # noqa: E402
from letter_date_parser import pick_letter_date  # noqa: E402
from portfolio_news_common import load_holding_configs, match_holding  # noqa: E402


class ClassificationPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data = json.loads(
            (ROOT / "_system" / "reference" / "securities" / "security_master.json").read_text(
                encoding="utf-8"
            )
        )
        cls.master = lm.SecurityMaster.from_dict(data)

    def emitted(self, text: str) -> set[str]:
        return {m["ticker"] for m in lm.emitted_mentions(lm.match_letter(text, self.master))}

    def test_lowercase_money_unit_is_not_bn(self) -> None:
        self.assertNotIn("BN", self.emitted("Market capitalization was $bn $bn and GDP reached US$500bn."))

    def test_uppercase_dollar_bn_remains_true_positive(self) -> None:
        self.assertIn("BN", self.emitted("We added to our position in $BN during the quarter."))

    def test_academic_degree_is_not_one_letter_b(self) -> None:
        text = "The analyst earned a B.S. in economics. Another director earned a B.S. in accounting."
        self.assertNotIn("B", self.emitted(text))

    def test_goldman_administrator_boilerplate_is_not_position(self) -> None:
        text = (
            "Goldman Sachs Administration Services calculated these returns. "
            "Contact Goldman Sachs Administration Services for account questions."
        )
        self.assertNotIn("GS", self.emitted(text))

    def test_goldman_position_context_remains_true_positive(self) -> None:
        text = "Our portfolio position in Goldman Sachs Group was 5.5% and contributed 120 basis points."
        self.assertIn("GS", self.emitted(text))

    def test_bare_acronym_without_investment_context_stays_excluded(self) -> None:
        text = "ESG Credit Macro Event Fund LP (CME) publishes this CME monthly update."
        self.assertNotIn("CME", self.emitted(text))

    def test_msci_benchmark_is_not_msci_inc(self) -> None:
        text = (
            "The fund returned 4.0% versus the MSCI China Index at 3.0%. "
            "MSCI World Index performance was 2.0% and long/short exposure was stable."
        )
        self.assertNotIn("MSCI", self.emitted(text))

    def test_msci_inc_position_remains_true_positive(self) -> None:
        text = (
            "We initiated a new position in MSCI Inc. during the quarter. "
            "MSCI Inc. provides investment decision support tools and recurring data services."
        )
        mentions = {m["ticker"]: m for m in lm.emitted_mentions(lm.match_letter(text, self.master))}
        self.assertIn("MSCI", mentions)
        self.assertEqual(mentions["MSCI"]["action"], "new")

    def test_officer_title_is_not_cooper_companies(self) -> None:
        text = (
            "Our portfolio manager met Jane Smith (COO) during diligence. "
            "The COO discussed operations and revenue with the investment team."
        )
        self.assertNotIn("COO", self.emitted(text))

    def test_cooper_companies_position_remains_true_positive(self) -> None:
        text = "We added to our position in The Cooper Companies (COO) during the quarter."
        mentions = {m["ticker"]: m for m in lm.emitted_mentions(lm.match_letter(text, self.master))}
        self.assertIn("COO", mentions)
        self.assertEqual(mentions["COO"]["action"], "add")

    def test_generic_southern_is_not_southern_company(self) -> None:
        self.assertNotIn(
            "SO",
            self.emitted("Our portfolio companies expanded across southern regional markets."),
        )

    def test_southern_company_position_remains_true_positive(self) -> None:
        text = "We initiated a new position in Southern Company during the quarter."
        self.assertIn("SO", self.emitted(text))

    def test_operating_ratio_is_not_osisko(self) -> None:
        text = "The railroad improved its Operating Ratio (OR), a key portfolio operating metric."
        self.assertNotIn("OR", self.emitted(text))

    def test_historical_l_brands_does_not_map_to_landbridge(self) -> None:
        text = "We initiated a new position in L Brands (LB), owner of Victoria's Secret."
        emitted = {
            m["ticker"]
            for m in lm.emitted_mentions(lm.match_letter(text, self.master, as_of="2021-03-31"))
        }
        self.assertNotIn("LB", emitted)

    def test_company_action_requires_fund_entity_relation(self) -> None:
        text = (
            "Our portfolio holding Ibotta added Kroger to its retailer network. "
            "Kroger remains an important commercial partner."
        )
        mentions = {m["ticker"]: m for m in lm.emitted_mentions(lm.match_letter(text, self.master))}
        if "KR" in mentions:
            self.assertEqual(mentions["KR"]["action"], "discuss")

    def test_single_generic_theme_keyword_does_not_tag_document(self) -> None:
        self.assertEqual(bsi.extract_themes("The bank mailed a notice.", []), [])

    def test_recurrent_theme_with_multiple_signals_is_retained(self) -> None:
        themes = bsi.extract_themes(
            "Interest rates rose as the Federal Reserve tightened.\n\nTreasury yields rose again.", []
        )
        self.assertIn("Rates", {row["theme"] for row in themes})

    def test_document_type_rejects_conference_and_product_decks(self) -> None:
        kind, eligible, _ = bsi.classify_document(Path("Sohn Investment Conference 2026.txt"), "LONG: ABC")
        self.assertEqual(kind, "conference_idea")
        self.assertFalse(eligible)
        kind, eligible, _ = bsi.classify_document(Path("ADP Presentation compact.txt"), "Product terms")
        self.assertEqual(kind, "product_marketing")
        self.assertFalse(eligible)

    def test_document_type_keeps_investor_letter(self) -> None:
        kind, eligible, _ = bsi.classify_document(
            Path("Maran Partners 2026 Q1 Letter.txt"),
            "Dear Partners, the fund returned 4% and our portfolio gained value.",
        )
        self.assertEqual(kind, "investor_letter")
        self.assertTrue(eligible)

    def test_future_body_date_does_not_beat_filename(self) -> None:
        iso, source, _ = pick_letter_date(
            "VU_MR_202604",
            "Chart period September 30 2026. Published data through April 2026.",
            "2026Q1",
        )
        self.assertEqual(iso, "2026-04-30")
        self.assertEqual(source, "filename_compact_month")

    def test_provider_tag_cannot_override_explicit_subject(self) -> None:
        configs = load_holding_configs()
        ticker, tier = match_holding(
            "GDDY Investor News: GoDaddy Inc. (NYSE: GDDY) faces a securities lawsuit",
            "https://example.com/gddy-lawsuit",
            configs,
            polygon_tickers=["A", "GDDY"],
        )
        self.assertEqual(ticker, "GDDY")
        self.assertEqual(tier, "explicit")

    def test_provider_only_one_letter_tag_is_quarantined(self) -> None:
        configs = load_holding_configs()
        ticker, tier = match_holding(
            "Unrelated issuer announces a material acquisition",
            "https://example.com/unrelated",
            configs,
            polygon_tickers=["A"],
        )
        self.assertIsNone(ticker)
        self.assertIsNone(tier)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
