#!/usr/bin/env python3
"""Special-situations joiner: Greenblatt lanes, and the noise that stays out."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_special_situations as book  # noqa: E402


def _news(category: str, title: str, ticker: str = "AAA", confidence: float = 0.9) -> dict:
    return {
        "items": [
            {
                "id": f"{ticker}:{title[:24]}",
                "tickers": [ticker],
                "company": f"{ticker} Co",
                "category": category,
                "confidence": confidence,
                "published_utc": "2026-10-01T00:00:00+00:00",
                "title": title,
                "summary": title,
                "url": "https://example.test/item",
                "publisher": "Example",
            }
        ]
    }


class SpecialSituationTests(unittest.TestCase):
    def test_spinoff_headlines_collapse_to_one_row_per_ticker(self):
        payload = book.build_book(
            news={
                "items": [
                    {
                        "id": "1",
                        "tickers": ["CTVA"],
                        "company": "Corteva",
                        "category": "spinoff",
                        "confidence": 0.88,
                        "published_utc": "2026-10-01T00:00:00+00:00",
                        "title": "Corteva plans a seed spinoff",
                        "url": "https://example.test/1",
                        "publisher": "Wire",
                    },
                    {
                        "id": "2",
                        "tickers": ["CTVA"],
                        "company": "Corteva",
                        "category": "spinoff",
                        "confidence": 0.9,
                        "published_utc": "2026-10-06T00:00:00+00:00",
                        "title": "Corteva completes the seed spin-off",
                        "url": "https://example.test/2",
                        "publisher": "Wire",
                    },
                ]
            }
        )
        # A headline alone never ranks: it stays in discovery until a Form 10 is on the register.
        self.assertEqual([row for row in payload["rows"] if row["lane"] == "spinoffs"], [])
        rows = [row for row in payload["discovery"] if row["lane"] == "spinoffs"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["headline_count"], 2)
        self.assertIn("completes", rows[0]["what"])
        self.assertIn("Terms are not extracted", rows[0]["what"])
        self.assertFalse(rows[0]["inbox"])
        self.assertEqual(rows[0]["ends_label"], "Orphan window after the distribution")

    def test_generic_deal_headline_is_not_a_merger_security(self):
        payload = book.build_book(
            news=_news("m_and_a", "Amazon acquired a former headquarters campus")
        )
        self.assertEqual(payload["rows"], [])

    def test_cvr_headline_is_a_merger_security(self):
        payload = book.build_book(
            news=_news("m_and_a", "Buyer adds a contingent value right to the merger")
        )
        self.assertEqual(payload["rows"][0]["lane"], "mergers")

    def test_dividend_declaration_is_not_a_forced_seller(self):
        payload = book.build_book(
            news=_news("dividend_policy", "Carrier declares a $0.24 quarterly dividend")
        )
        self.assertEqual(payload["rows"], [])

    def test_dividend_cut_opinion_is_not_a_forced_seller(self):
        payload = book.build_book(
            news=_news("dividend_policy", "Sabine Royalty Trust: Dividend Cut Risk")
        )
        self.assertEqual(payload["rows"], [])

    def test_announced_dividend_suspension_is_a_forced_seller(self):
        payload = book.build_book(
            news=_news("dividend_policy", "Issuer suspended its dividend after the quarter")
        )
        self.assertEqual(payload["rows"][0]["lane"], "forced_sellers")

    def test_index_add_is_ignored_and_delete_is_kept(self):
        payload = book.build_book(
            index_doc={
                "by_ticker": {
                    "GOOGL": {
                        "confirmed_events": [
                            {"ticker": "GOOGL", "index": "djia", "action": "add", "announced": "2026-07-01"}
                        ]
                    },
                    "TAP": {
                        "confirmed_events": [
                            {
                                "ticker": "TAP",
                                "index": "sp500",
                                "action": "delete",
                                "announced": "2026-09-21",
                                "confidence": "news_unconfirmed",
                                "title": "dropped from the index",
                            }
                        ]
                    },
                }
            }
        )
        self.assertEqual([row["ticker"] for row in payload["rows"]], ["TAP"])
        self.assertIn("headline", payload["rows"][0]["what"])

    def test_chapter_11_warrant_sits_in_both_lanes(self):
        payload = book.build_book(
            warrants={
                "rows": [
                    {
                        "warrant_ticker": "CORE.W",
                        "common_ticker": "CORE",
                        "issuer": "Core",
                        "lane": "chapter_11",
                        "lifecycle": "active",
                        "terms": {"strike": 1.5, "expiry": "2027-01-01"},
                        "source": {"url": "https://www.sec.gov/example"},
                        "warrant_id": "core",
                    },
                    {
                        "warrant_ticker": "OLD.W",
                        "common_ticker": "OLD",
                        "issuer": "Old",
                        "lane": "despac",
                        "lifecycle": "redeemed",
                        "terms": {"expiry": "2024-01-01"},
                        "warrant_id": "old",
                    },
                ]
            }
        )
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["lanes"], ["restructurings", "warrants"])
        self.assertEqual(payload["history"][0]["ticker"], "OLD.W")
        self.assertEqual(payload["history"][0]["status"], "ended")

    def test_tender_is_ranked_and_ordinary_13d_is_not(self):
        payload = book.build_book(
            activist={
                "feed": [
                    {
                        "ticker": "INCY",
                        "form": "SC TO-C",
                        "filing_class": "tender_offer",
                        "firm_name": "Baker Bros",
                        "target_company": "Incyte",
                        "source_url": "https://www.sec.gov/tender",
                        "report_date": "2026-05-01",
                        "report_id": "t1",
                    },
                    {
                        "ticker": "INCY",
                        "form": "SC 13D/A",
                        "filing_class": "activist_13d",
                        "firm_name": "Someone",
                        "report_id": "d1",
                    },
                ]
            }
        )
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["lane"], "mergers")
        self.assertEqual(payload["rows"][0]["evidence_kind"], "filing")

    def test_priced_cvr_is_ranked_and_bare_text_match_is_discovery(self):
        payload = book.build_book(
            cvr={
                "as_of": "2026-10-07",
                "post_close_universe": [
                    {
                        "id": "ABMD.CVR",
                        "ticker": "ABMD.CVR",
                        "acquirer": "JNJ",
                        "max_payout_usd": 35,
                        "outside_date": "2029-12-31",
                    }
                ],
                "pre_close_opportunities": [
                    {
                        "id": "MFBP.CONTINGENT",
                        "ticker": "MFBP",
                        "max_contingent_usd": 6.73,
                        "catalyst": "ECIP preferred redemption",
                        "expected_close": "2026-Q4",
                    },
                    {
                        "id": "JSPR.CVR_CANDIDATE",
                        "ticker": "JSPR",
                        "form": "8-K",
                        "query_family": "primary_cvr",
                        "sec_hint": "https://www.sec.gov/jspr",
                        "entity_name": "Jasper Therapeutics, Inc.  (JSPR)",
                    },
                    {
                        "id": "DEAL.S4",
                        "ticker": "DEAL",
                        "form": "S-4",
                        "sec_hint": "https://www.sec.gov/deal",
                        "entity_name": "Deal Co",
                    },
                ],
            }
        )
        ranked = {row["ticker"]: row for row in payload["rows"]}
        self.assertEqual(ranked["ABMD.CVR"]["ends"], "2029-12-31")
        self.assertIn("35", ranked["ABMD.CVR"]["what"])
        self.assertIn("ECIP", ranked["MFBP"]["what"])
        self.assertEqual(ranked["DEAL"]["lane"], "mergers")
        self.assertFalse(ranked["DEAL"]["inbox"])
        self.assertTrue(ranked["ABMD.CVR"]["inbox"])
        self.assertNotIn("JSPR", ranked)
        discovery = [row["ticker"] for row in payload["discovery"]]
        self.assertEqual(discovery, ["JSPR"])

    def test_nol_appears_only_with_a_bankruptcy_or_a_live_deal(self):
        nol = {
            "rows": [
                {
                    "ticker": "REI",
                    "prior_ownership_change": {"occurred": True, "evidence": {"url": "https://www.sec.gov/rei", "filed": "2026-03-04"}},
                    "bankruptcy_382_exception": {"mentioned": False},
                },
                {
                    "ticker": "ECHO",
                    "prior_ownership_change": {"occurred": False},
                    "bankruptcy_382_exception": {
                        "mentioned": True,
                        "evidence": {"url": "https://www.sec.gov/echo", "filed": "2026-09-01"},
                    },
                },
            ]
        }
        alone = book.build_book(nol=nol)
        self.assertEqual([row["ticker"] for row in alone["rows"]], ["ECHO"])
        with_deal = book.build_book(
            news=_news("m_and_a", "REI holders receive a contingent value right", ticker="REI"),
            nol=nol,
        )
        tickers = [row["ticker"] for row in with_deal["rows"] if row["source_feed"] == "nol_382_facts"]
        self.assertEqual(sorted(tickers), ["ECHO", "REI"])

    def test_segment_reshuffle_is_not_a_restructuring(self):
        payload = book.build_book(
            news=_news("restructuring", "Boston Scientific restructures segments starting 2027")
        )
        self.assertEqual(payload["rows"], [])

    def test_schema_names_every_lane(self):
        payload = book.build_book()
        self.assertEqual(payload["schema_version"], "special_situations.v1")
        self.assertEqual(
            [lane["id"] for lane in payload["lanes"]],
            ["spinoffs", "split_offs", "mergers", "warrants", "restructurings", "forced_sellers", "buyback_events"],
        )
        self.assertIsNone(payload["rows"][0]["annualized_spread"] if payload["rows"] else None)




def _separations(**overrides) -> dict:
    row = {
        "separation_id": "sep:par-spn-2026",
        "kind": "split_off",
        "kind_label": "Split-off exchange offer",
        "status": "offer_open",
        "lifecycle": "active",
        "parent_ticker": "PAR",
        "spinco_ticker": "SPN",
        "spinco_name": "SpinCo Inc.",
        "dates": {"expiration": "2026-10-09", "filed": "2026-09-14"},
        "ends": "2026-10-09",
        "ends_label": "Expires 2026-10-09",
        "gates": {"identity": {"pass": True, "missing": []}, "terms": {"pass": True, "missing": []}, "status": "ranked"},
        "terms_summary": "Exchange at a 7% discount, upper limit 4.5939, odd-lot priority, 3-session valuation period.",
        "spread": {
            "basis": "filing_formula", "implied_ratio": 4.5939, "realized_discount_pct": 5.1,
            "annualized_spread_pct": 240.0, "odd_lot_payoff_per_99": {"gain_usd": 450.0, "gain_pct": 5.0},
            "proration": {"low": 0.15, "base": 0.25, "high": 0.4, "basis": "reference_set"},
        },
        "flows": {"parent": None, "spinco": {"status": "ok", "pct_of_float_base": -22.2, "pct_of_adv_days": 3.1,
                                              "window_start": "2026-10-14", "window_end": "2026-10-28", "legs": []}},
        "sources": [{"form": "SC TO-I", "url": "https://www.sec.gov/x", "filed": "2026-09-14"}],
        "next": "Read the final-results 8-K.",
    }
    row.update(overrides)
    return {
        "caption": "Forced selling is a research trigger.",
        "rows": [row],
        "forced_seller_rows": [
            {"separation_id": "sep:par-spn-2026", "ticker": "SPN", "side": "spinco", "kind": "split_off",
             "what": "Split-off: modelled selling of 22.20% of float, 3.1 days of volume",
             "window_start": "2026-10-14", "window_end": "2026-10-28", "pct_of_float_base": -22.2,
             "pct_of_adv_days": 3.1, "confidence": "estimate", "evidence_url": "https://www.sec.gov/x", "as_of": "2026-10-11"}
        ],
    }


class SeparationDeskTests(unittest.TestCase):
    def test_bare_spin_word_is_not_a_spinoff(self):
        payload = book.build_book(
            news=_news("spinoff", "GE Vernova (GEV) Dips More Than Broader Market: What You Should Know", ticker="GEV")
        )
        self.assertEqual([r for r in payload["rows"] + payload["discovery"] if r["lane"] == "spinoffs"], [])

    def test_registered_split_off_ranks_with_spread_and_flow(self):
        payload = book.build_book(separations=_separations())
        rows = [r for r in payload["rows"] if r["lane"] == "split_offs"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["ticker"], "PAR")
        self.assertEqual(row["spread"]["basis"], "filing_formula")
        self.assertIn("annualized", row["annualized_spread"])
        self.assertEqual(row["flow"]["pct_of_float_base"], -22.2)
        self.assertEqual(row["ends"], "2026-10-09")
        self.assertTrue(row["inbox"])
        self.assertEqual(payload["caption"], "Forced selling is a research trigger.")
        forced = [r for r in payload["rows"] if r["lane"] == "forced_sellers"]
        self.assertEqual(len(forced), 1)
        self.assertEqual(forced[0]["ticker"], "SPN")
        self.assertEqual(forced[0]["ends"], "2026-10-28")
        self.assertEqual(payload["counts"]["ranked"]["split_offs"], 1)

    def test_split_off_without_terms_is_discovery_without_spread(self):
        gates = {"identity": {"pass": True, "missing": []}, "terms": {"pass": False, "missing": ["exchange.upper_limit_ratio"]}, "status": "discovery"}
        payload = book.build_book(separations=_separations(gates=gates, terms_summary="Terms are not extracted."))
        self.assertEqual([r for r in payload["rows"] if r["lane"] == "split_offs"], [])
        rows = [r for r in payload["discovery"] if r["lane"] == "split_offs"]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["spread"])
        self.assertIsNone(rows[0]["annualized_spread"])
        self.assertIn("Terms are not extracted", rows[0]["what"])

    def test_registered_spin_ranks_and_its_headlines_do_not_duplicate(self):
        seps = _separations(kind="spin_off", kind_label="Spin-off", spread=None, dates={"distribution": "2026-11-01"},
                            ends="2026-11-01", ends_label="Distribution 2026-11-01")
        seps["forced_seller_rows"] = []
        payload = book.build_book(news=_news("spinoff", "PAR plans a spin-off of SpinCo", ticker="PAR"), separations=seps)
        spins = [r for r in payload["rows"] + payload["discovery"] if r["lane"] == "spinoffs"]
        self.assertEqual(len(spins), 1)
        self.assertEqual(spins[0]["book"], "ranked")
        self.assertEqual(spins[0]["source_feed"], "separations")

    def test_closed_separation_goes_to_history(self):
        seps = _separations(lifecycle="closed", status="completed")
        seps["forced_seller_rows"] = []
        payload = book.build_book(separations=seps)
        self.assertEqual([r for r in payload["rows"] if r["lane"] == "split_offs"], [])
        self.assertEqual(len([r for r in payload["history"] if r["lane"] == "split_offs"]), 1)


if __name__ == "__main__":
    unittest.main()
