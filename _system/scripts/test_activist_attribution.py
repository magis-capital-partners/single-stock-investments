#!/usr/bin/env python3
"""Regression tests for activist report -> ticker attribution (2026-10-12 audit).

Every case here is a report that was filed under the wrong ticker: Viceroy's
Abaxx posts under OPEN and FAST, Spruce Point's American Battery Metals report
under five "American" issuers, Bleecker Street's NextNav / LL Flooring and
Spruce Point's WD-40 reports under LRCX, Henry Schein's long report as a short,
and RSS rows dated YYYY-01-01. The positive cases pin what must still match.
No network: every input is an inline string or a temp file.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import activist_common  # noqa: E402
import verify_activist_reports  # noqa: E402
from activist_common import (  # noqa: E402
    match_report_to_ticker,
    publisher_match_allowed,
    report_key,
    upsert_report,
    url_target_mismatch,
)
from activist_site_fetchers import (  # noqa: E402
    parse_html_links,
    parse_position_marker,
    parse_rss,
    spruce_card_details,
)
from short_scan_batch import is_feed_short  # noqa: E402
from site_activist_scan import _dest_name, _guess_date  # noqa: E402


def meta(ticker: str, company: str | None = None) -> dict:
    """Registry-independent ticker meta (company == ticker means "no name on file")."""
    return {"ticker": ticker, "company": company or ticker, "cik": None, "aliases": []}


ABAXX_GLUED = (
    "Abaxx - ATB Investor Call - Liquidity Explosion at the Plumbing Factory "
    "Published 6 days ago: Jun 30, 2026 June 30, 2026 - Viceroy Research "
    "Abaxx appear to have announced that Open Interest is incentivized!"
)
ABAXX_URL = "https://viceroyresearch.org/publications/liquidity-explosion-at-the-plumbing-factory"


class WordTickerTests(unittest.TestCase):
    def test_open_does_not_match_glued_abaxx_card(self) -> None:
        for company in (None, "Opendoor Technologies Inc."):
            m = meta("OPEN", company)
            matched, _conf, reason = match_report_to_ticker(f"{ABAXX_GLUED} {ABAXX_URL}", m)
            self.assertFalse(matched, msg=f"{company}: {reason}")
            self.assertTrue(url_target_mismatch(ABAXX_URL, ABAXX_GLUED, m))
            ok, _conf, reason = publisher_match_allowed(
                ABAXX_URL, ABAXX_GLUED, f"{ABAXX_GLUED} {ABAXX_URL}", m
            )
            self.assertFalse(ok, msg=reason)

    def test_open_does_not_match_open_letters_even_in_capitals(self) -> None:
        m = meta("OPEN")
        url = "https://carlicahn.com/open-letter-to-shareholders-of-illumina-inc-13/"
        for title in ("Open Letter to Shareholders of Illumina, Inc.", "OPEN LETTER TO SHAREHOLDERS"):
            matched, _conf, reason = match_report_to_ticker(f"{title} {url}", m)
            self.assertFalse(matched, msg=f"{title}: {reason}")
            self.assertTrue(url_target_mismatch(url, title, m))

    def test_fast_does_not_match_fast_growing(self) -> None:
        m = meta("FAST", "Fastenal")
        text = "Abaxx - Letter to the OSC and CIRO. Abaxx claims to run a fast-growing exchange."
        url = "https://viceroyresearch.org/publications/osc-and-ciro"
        matched, _conf, reason = match_report_to_ticker(f"{text} {url}", m)
        self.assertFalse(matched, msg=reason)
        ok, _conf, reason = publisher_match_allowed(url, text, f"{text} {url}", m)
        self.assertFalse(ok, msg=reason)

    def test_word_ticker_needs_explicit_notation(self) -> None:
        m = meta("OPEN")
        for text in (
            "Opendoor Technologies (NASDAQ: OPEN) is an iBuyer",
            "We are short $OPEN",
            "Opendoor (OPEN): the iBuying model is broken",
            "Opendoor, Nasdaq-OPEN, reported",
        ):
            matched, conf, reason = match_report_to_ticker(text, m)
            self.assertTrue(matched, msg=text)
            self.assertEqual(reason, "ticker_explicit", msg=text)
            self.assertGreaterEqual(conf, 0.99)
        # Lower-case "open" is prose even next to an exchange-looking token.
        self.assertFalse(match_report_to_ticker("the nasdaq - open to all", m)[0])

    def test_real_company_name_still_matches(self) -> None:
        m = meta("OPEN", "Opendoor Technologies Inc.")
        matched, _conf, reason = match_report_to_ticker("Why Opendoor Technologies is a short", m)
        self.assertTrue(matched)
        self.assertEqual(reason, "company_name")
        matched, _conf, reason = match_report_to_ticker("Opendoor's iBuying math does not work", m)
        self.assertTrue(matched)
        self.assertEqual(reason, "company_brand")

    def test_upper_case_symbol_matches_but_lower_case_does_not(self) -> None:
        m = meta("SOLV", "Solventum")
        url = "https://trianpartners.com/wp-content/uploads/2025/01/2025-01-08-SOLV-Shareholder-Letter-Release.pdf"
        matched, _conf, reason = match_report_to_ticker(url, m)
        self.assertTrue(matched)
        self.assertEqual(reason, "ticker_symbol")
        self.assertFalse(match_report_to_ticker("we will solv this", meta("SOLV"))[0])

    def test_lower_case_symbol_as_url_path_token_still_matches(self) -> None:
        m = meta("SMCI", "Supermicro")
        url = "https://hindenburgresearch.com/smci/"
        self.assertFalse(url_target_mismatch(url, "Super Micro: Fresh Evidence", m))
        ok, _conf, reason = publisher_match_allowed(url, "", url, m)
        self.assertTrue(ok, msg=reason)
        # ...and a one-word registry name written as two words is the name.
        self.assertEqual(match_report_to_ticker("Super Micro Computer Inc. is a server maker", m)[2], "company_name")


class BrandWordTests(unittest.TestCase):
    ABML_URL = "https://sprucepointcap.com/research/american-battery-metals-corp-comstock-mining-inc"
    ABML_TITLE = "American Battery Metals Corp. | Comstock Mining Inc."

    def test_american_does_not_match_american_issuers(self) -> None:
        for ticker, company in (
            ("AEP", "American Electric Power"),
            ("AIG", "American International Group"),
            ("AMT", "American Tower"),
            ("AWK", "American Water Works"),
            ("AXP", "American Express"),
        ):
            m = meta(ticker, company)
            text = f"{self.ABML_TITLE} {self.ABML_URL}"
            matched, _conf, reason = match_report_to_ticker(text, m)
            self.assertFalse(matched, msg=f"{ticker}: {reason}")
            self.assertTrue(url_target_mismatch(self.ABML_URL, self.ABML_TITLE, m), msg=ticker)

    def test_other_common_leading_words(self) -> None:
        cases = (
            ("BAC", "Bank of America", "Healthcare Trust of America, Inc."),
            ("HCA", "HCA Healthcare", "Prestige Consumer Healthcare, Inc."),
            ("CVS", "CVS Health", "Hims & Hers Health, Inc."),
            ("ULTA", "Ulta Beauty", "e.l.f. Beauty"),
            ("HST", "Host Hotels & Resorts", "LuxUrban Hotels (LUXH): The Bed Sheets Should Be Made Out Of Red Flags"),
            ("PEG", "Public Service Enterprise Group", "academic studies find that public companies stocks perform worse"),
            ("GD", "General Dynamics", "Trian and General Catalyst Affirm Commitment"),
            ("SWK", "Stanley Black & Decker", "ValueAct Capital's Bet on Morgan Stanley"),
            ("MFBP", "M&F Bancorp Optus merger - ECIP redemption", "Trian General Catalyst Amended Merger Agreement"),
        )
        for ticker, company, text in cases:
            matched, _conf, reason = match_report_to_ticker(text, meta(ticker, company))
            self.assertFalse(matched, msg=f"{ticker}: {reason}")

    def test_brand_phrases_and_distinctive_tokens_still_match(self) -> None:
        cases = (
            ("HST", "Host Hotels & Resorts", "Host Hotels: a REIT with a problem"),
            ("MS", "Morgan Stanley", "ValueAct Capital's Bet on Morgan Stanley"),
            ("CSGP", "CoStar Group", "D.E. Shaw Group Letter to CoStar Board"),
            ("GD", "General Dynamics", "General Dynamics' Gulfstream backlog"),
        )
        for ticker, company, text in cases:
            matched, conf, reason = match_report_to_ticker(text, meta(ticker, company))
            self.assertTrue(matched, msg=f"{ticker}: {reason}")
            self.assertIn(reason, {"company_brand", "company_name"})
            self.assertGreaterEqual(conf, 0.9)


class ResearchPathTests(unittest.TestCase):
    def test_lrcx_research_path_and_short_slugs(self) -> None:
        m = meta("LRCX", "Lam Research")
        for url, title in (
            ("https://sprucepointcap.com/research/wd-40", "Oct 18, 2022"),
            ("https://bleeckerstreetresearch.com/research/nn", "Chris Drose 12/6/23"),
            ("https://bleeckerstreetresearch.com/research/ll", "Chris Drose 10/17/23"),
        ):
            self.assertTrue(url_target_mismatch(url, title, m), msg=url)
            ok, _conf, reason = publisher_match_allowed(url, title, f"{title} {url}", m)
            self.assertFalse(ok, msg=f"{url}: {reason}")
        # The real company still resolves, through the URL as well as prose.
        self.assertFalse(url_target_mismatch("https://example.com/research/lam-research-corp", "", m))
        self.assertEqual(match_report_to_ticker("Lam Research Corporation (LRCX)", m)[2], "company_name")

    def test_two_letter_slug_matching_its_own_ticker_is_not_a_mismatch(self) -> None:
        self.assertFalse(
            url_target_mismatch("https://bleeckerstreetresearch.com/research/nn", "", meta("NN", "NextNav Inc."))
        )

    def test_sequence_numbered_pdf_still_names_its_symbol(self) -> None:
        url = "https://scorpioncapital.s3.us-east-2.amazonaws.com/reports/QS1.pdf"
        self.assertFalse(url_target_mismatch(url, "", meta("QS", "QuantumScape Corporation")))
        self.assertTrue(url_target_mismatch(url, "A Failed One-Trick Pony", meta("PONY")))


class LinkParserTests(unittest.TestCase):
    def test_text_after_the_anchor_is_not_glued_onto_the_title(self) -> None:
        html = (
            '<div class="card"><a href="/publications/liquidity-explosion">Abaxx - ATB Investor Call</a>'
            "<p>Published 6 days ago: Jun 30, 2026</p>"
            "<p>Abaxx appear to have announced that Open Interest is incentivized!</p></div>"
            '<div class="card"><a href="/publications/osc-and-ciro">Abaxx - Letter to the OSC</a>'
            "<p>a fast-growing exchange</p></div>"
        )
        links = parse_html_links("https://viceroyresearch.org/", html)
        self.assertEqual(
            [(link["url"], link["title"]) for link in links],
            [
                ("https://viceroyresearch.org/publications/liquidity-explosion", "Abaxx - ATB Investor Call"),
                ("https://viceroyresearch.org/publications/osc-and-ciro", "Abaxx - Letter to the OSC"),
            ],
        )

    def test_headline_wins_over_an_empty_thumbnail_link(self) -> None:
        html = (
            '<a href="/research/henry-schein-inc"><img src="x.jpg"/></a>'
            '<div class="research-date">Sep 26, 2018</div>'
            '<a href="/research/henry-schein-inc"><h3>Henry Schein, Inc.</h3></a>'
        )
        links = parse_html_links("https://sprucepointcap.com/research/", html)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["title"], "Henry Schein, Inc.")


class SprucePositionTests(unittest.TestCase):
    CARD = (
        '<div role="listitem" class="research-wrap w-dyn-item">'
        '<a href="/research/henry-schein-inc" class="block"><img alt="Henry Schein, Inc."/></a>'
        '<div class="research-list-wrap"><div class="research-date">Sep 26, 2018</div>'
        '<a href="/research/henry-schein-inc"><h3 class="research-h3">Henry Schein, Inc.</h3></a>'
        '<div class="stock-designation"><div>NASDAQ:</div><div class="uppercase">HSIC</div></div>'
        '<div class="industry-position"><div class="font-bold">Position:</div><div>Long</div></div>'
        '<a href="/research/henry-schein-inc" class="button">View Report</a></div></div>'
        '<div role="listitem" class="research-wrap w-dyn-item">'
        '<a href="/research/e-l-f-beauty"><h3 class="research-h3">e.l.f. Beauty</h3></a>'
        '<div class="research-date">Nov 9, 2023</div>'
        '<div class="industry-position"><div class="font-bold">Position:</div><div>Short</div></div></div>'
    )

    def test_card_details_carry_position_date_and_symbol(self) -> None:
        details = spruce_card_details("https://sprucepointcap.com/research/", self.CARD)
        hsic = details["https://sprucepointcap.com/research/henry-schein-inc"]
        self.assertEqual(hsic["position"], "long")
        self.assertEqual(hsic["published"], "Sep 26, 2018")
        self.assertEqual(hsic["ticker_hint"], "NASDAQ: HSIC")
        self.assertEqual(hsic["heading"], "Henry Schein, Inc.")
        self.assertEqual(details["https://sprucepointcap.com/research/e-l-f-beauty"]["position"], "short")

    def test_report_page_position_marker(self) -> None:
        page = '<div class="font-black">Position:</div><div>Long</div><div>Date:</div><div>Sep 26, 2018</div>'
        self.assertEqual(parse_position_marker(page), "long")
        self.assertIsNone(parse_position_marker('<input style="opacity:0;position:absolute"/>'))


class DateTests(unittest.TestCase):
    def test_rss_pubdate_is_parsed_not_truncated(self) -> None:
        xml = (
            "<rss><channel><item><title>Carvana: A Father-Son Accounting Grift</title>"
            "<link>https://hindenburgresearch.com/carvana/</link>"
            "<pubDate>Mon, 06 Oct 2025 14:00:00 +0000</pubDate></item></channel></rss>"
        )
        items = parse_rss(xml, "https://hindenburgresearch.com/")
        self.assertEqual(items[0]["published"], "Mon, 06 Oct 2025 14:00:00 +0000")
        self.assertEqual(_guess_date(items[0]), ("2025-10-06", "day", "publisher"))

    def test_ordinal_dates(self) -> None:
        link = {"title": "Download PDF > January 7th, 2021 Nevro (NYSE: NVRO)", "url": "https://x.com/r.pdf"}
        self.assertEqual(_guess_date(link)[:2], ("2021-01-07", "day"))
        self.assertEqual(_guess_date({"title": "Published on 21st March 2024", "url": ""})[:2], ("2024-03-21", "day"))

    def test_byline_numeric_date(self) -> None:
        link = {"title": "Chris Drose 1/17/24", "url": "https://bleeckerstreetresearch.com/research/luxurban"}
        self.assertEqual(_guess_date(link)[:2], ("2024-01-17", "day"))

    def test_a_bare_year_is_not_a_date(self) -> None:
        link = {"title": "Our 2021 report", "url": "https://example.com/reports/2021-annual-short"}
        self.assertEqual(_guess_date(link), (None, "unknown", None))
        self.assertEqual(_guess_date({"title": "", "url": "", "published": ""}), (None, "unknown", None))

    def test_undated_files_are_named_undated_and_stable(self) -> None:
        url = "https://bleeckerstreetresearch.com/research/nn"
        name = _dest_name("bleecker_street", url, None, ".html")
        self.assertTrue(name.startswith("bleecker_street_undated_nn-"), name)
        self.assertEqual(name, _dest_name("bleecker_street", url, None, ".html"))
        self.assertFalse(any(ch.isdigit() for ch in name.split("_undated_")[1]), name)
        self.assertEqual(_dest_name("spruce_point", "https://s.com/research/msci", "2024-01-17", ".html"),
                         "spruce_point_2024-01-17_msci.html")


class DedupeTests(unittest.TestCase):
    def test_publisher_rows_dedupe_on_source_url(self) -> None:
        first = {
            "firm_id": "bleecker_street",
            "source": "publisher_site",
            "source_url": "https://bleeckerstreetresearch.com/research/nn",
            "report_date": "2023-12-06",
            "canonical_file": "_system/reference/activist-reports/bleecker_street/bleecker_street_2026-09-26_nn.html",
        }
        refetch = {
            **first,
            "source_url": "https://bleeckerstreetresearch.com/research/nn/",
            "report_date": None,
            "canonical_file": "_system/reference/activist-reports/bleecker_street/bleecker_street_undated_nn-abcdefgh.html",
        }
        self.assertEqual(report_key(first), report_key(refetch))
        index = {"reports": [dict(first)]}
        self.assertTrue(upsert_report(index, refetch))
        self.assertEqual(len(index["reports"]), 1)
        self.assertEqual(index["reports"][0]["report_date"], "2023-12-06")
        self.assertEqual(index["reports"][0]["canonical_file"], refetch["canonical_file"])


class FeedShortTests(unittest.TestCase):
    BASE = {"side": "short", "source": "publisher_site", "include_in_feed": True}

    def test_unverified_publisher_short_is_not_a_lead(self) -> None:
        self.assertFalse(is_feed_short({**self.BASE, "match_reason": "ticker_symbol"}))

    def test_brand_only_verification_is_not_a_lead(self) -> None:
        row = {**self.BASE, "match_reason": "company_brand", "target_verified": True,
               "target_match_evidence": "company_brand"}
        self.assertFalse(is_feed_short(row))

    def test_strongly_verified_short_is_a_lead(self) -> None:
        for evidence in ("ticker_explicit", "company_name", "ticker_symbol"):
            row = {**self.BASE, "match_reason": "ticker_symbol", "target_verified": True,
                   "target_match_evidence": evidence}
            self.assertTrue(is_feed_short(row), msg=evidence)

    def test_curated_markdown_short_needs_no_body_verification(self) -> None:
        self.assertTrue(is_feed_short({"side": "short", "source": "short_reports_md"}))
        self.assertFalse(is_feed_short({**self.BASE, "side": "long", "target_verified": True,
                                        "target_match_evidence": "company_name"}))


class VerifyTests(unittest.TestCase):
    def _verify(self, html: str, m: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "page.html").write_text(html, encoding="utf-8")
            report = {"source": "publisher_site", "canonical_file": "page.html"}
            with mock.patch.object(activist_common, "ROOT", root), mock.patch.object(
                verify_activist_reports, "ROOT", root
            ):
                verify_activist_reports.verify_report(report, m)
            return report

    def test_sidebar_mentions_beyond_the_lead_do_not_verify(self) -> None:
        html = (
            "<html><head><title>American Battery Metals Corp. - Spruce Point</title></head><body>"
            + "<p>" + ("Battery metals recycling claims. " * 120) + "</p>"
            + "<aside>Other reports: American Electric Power Company (NASDAQ: AEP)</aside>"
            + "<p>Appendix: American Electric Power Company</p></body></html>"
        )
        report = self._verify(html, meta("AEP", "American Electric Power Company"))
        self.assertFalse(report["body_verified"])
        self.assertFalse(report["target_verified"])

    def test_brand_word_alone_does_not_verify(self) -> None:
        html = "<html><head><title>Letter to the CoStar board</title></head><body>CoStar</body></html>"
        report = self._verify(html, meta("CSGP", "CoStar Group"))
        self.assertEqual(report["body_match_reason"], "company_brand")
        self.assertFalse(report["target_verified"])

    def test_title_and_lead_verify(self) -> None:
        html = (
            '<html><head><meta property="og:title" content="Eos Energy (EOSE): Former Execs Speak"/>'
            "<title>Eos Energy (EOSE)</title></head><body><nav>Home About</nav>"
            "<p>Eos Energy Enterprises is a battery maker.</p></body></html>"
        )
        report = self._verify(html, meta("EOSE"))
        self.assertTrue(report["target_verified"])
        self.assertEqual(report["target_match_evidence"], "ticker_explicit")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
