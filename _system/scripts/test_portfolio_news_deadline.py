#!/usr/bin/env python3
"""Portfolio news: bounded concurrency, a run deadline, and a partial write.

From 2026-09-08 to 09-24, 58 of 65 news runs hit the 45-minute job timeout
(reported as "cancelled", so nothing was written and nothing went red): the
Google phase fetched 843 holdings one at a time (~26 min) after an 11-16
minute Polygon phase. No test here touches the network.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest_portfolio_news as ingest  # noqa: E402
from portfolio_news_common import HoldingNewsConfig  # noqa: E402


def config(ticker: str) -> HoldingNewsConfig:
    return HoldingNewsConfig(
        ticker=ticker,
        company=f"{ticker} Holdings",
        market="US",
        exchange="NYSE",
        search_names=[f"{ticker} Holdings"],
        ticker_tokens=[ticker],
        polygon_ticker=None,
        exclude_patterns=[],
        google_locale={"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ir_domains=[],
        explicit_only=False,
    )


def configs(count: int) -> dict[str, HoldingNewsConfig]:
    return {f"T{i:02d}": config(f"T{i:02d}") for i in range(count)}


def recent(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


class GooglePhaseConcurrencyTests(unittest.TestCase):
    def test_holdings_are_fetched_concurrently_by_default(self) -> None:
        lock = threading.Lock()
        state = {"now": 0, "peak": 0}

        def fake_fetch(_session, _query, _locale):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return []

        holdings = configs(24)
        with mock.patch.object(ingest, "_fetch_google_news_rss", side_effect=fake_fetch):
            ingest.phase_google_news(None, holdings, tickers=sorted(holdings))
        self.assertGreaterEqual(state["peak"], 4)
        self.assertLessEqual(state["peak"], ingest.GOOGLE_WORKERS)

    def test_deadline_stops_new_requests_and_reports_coverage(self) -> None:
        clock = {"t": 0.0}

        def fake_fetch(_session, _query, _locale):
            clock["t"] += 1.0  # each request "takes" one second
            return []

        deadline = ingest.Deadline(5.0, clock=lambda: clock["t"])
        holdings = configs(20)
        coverage: dict = {}
        with mock.patch.object(ingest, "_fetch_google_news_rss", side_effect=fake_fetch):
            ingest.phase_google_news(
                None, holdings, tickers=sorted(holdings), workers=1,
                deadline=deadline, coverage=coverage,
            )
        google = coverage["google"]
        self.assertEqual(google["tickers_total"], 20)
        self.assertGreater(google["not_attempted"], 0)
        self.assertLess(google["refreshed"], 20)
        self.assertEqual(google["refreshed"] + google["failed"] + google["not_attempted"], 20)

    def test_a_failed_fetch_is_not_counted_as_refreshed(self) -> None:
        def fake_fetch(_session, query, _locale):
            return None if "T01" in query else []

        holdings = configs(3)
        coverage: dict = {}
        with mock.patch.object(ingest, "_fetch_google_news_rss", side_effect=fake_fetch):
            ingest.phase_google_news(None, holdings, tickers=sorted(holdings), coverage=coverage)
        self.assertEqual(coverage["google"]["failed"], 1)
        self.assertEqual(coverage["google"]["failed_tickers"], ["T01"])
        self.assertNotIn("T01", coverage["google"]["refreshed_tickers"])


class _Response:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content


class FetchFailureVersusEmptyTests(unittest.TestCase):
    RSS = (
        b"<rss><channel><item><title>T00 Holdings raises guidance</title>"
        b"<link>https://example.test/a</link><pubDate>Mon, 21 Sep 2026 10:00:00 GMT</pubDate>"
        b"<description>d</description><source>Wire</source></item></channel></rss>"
    )

    def _fetch(self, *responses: _Response):
        session = mock.Mock()
        session.get.side_effect = list(responses)
        with mock.patch.object(ingest.time, "sleep"):
            return ingest._fetch_google_news_rss(session, "q", {})

    def test_http_failure_is_none_after_one_retry(self) -> None:
        self.assertIsNone(self._fetch(_Response(503), _Response(503)))

    def test_retry_recovers(self) -> None:
        rows = self._fetch(_Response(429), _Response(200, self.RSS))
        self.assertEqual(len(rows), 1)

    def test_empty_feed_is_an_empty_list(self) -> None:
        self.assertEqual(self._fetch(_Response(200, b"")), [])


class CarryOverTests(unittest.TestCase):
    def _item(self, ticker: str, source: str, published: str) -> dict:
        return {
            "id": f"{source}:{ticker}:{published[:10]}",
            "tickers": [ticker],
            "source": source,
            "published_utc": published,
            "url": f"https://example.test/{source}/{ticker}",
            "confidence": 0.8,
        }

    def test_unrefreshed_holdings_keep_their_items(self) -> None:
        previous = [
            self._item("T1", "google_news", recent()),  # refreshed -> replaced
            self._item("T2", "google_news", recent()),  # not refreshed -> kept
            self._item("T3", "google_news", recent(45)),  # outside the window
            self._item("T4", "polygon", recent()),  # polygon complete -> replaced
            self._item("GONE", "google_news", recent()),  # no longer held
        ]
        kwargs = dict(
            known_tickers={"T1", "T2", "T3", "T4"},
            google_refreshed={"T1"},
            polygon_universe={"T1", "T2", "T3", "T4"},
            cutoff=datetime.now(UTC) - timedelta(days=30),
        )
        kept = ingest.carry_over_previous(previous, polygon_complete=True, **kwargs)
        self.assertEqual([item.tickers[0] for item in kept], ["T2"])
        kept = ingest.carry_over_previous(previous, polygon_complete=False, **kwargs)
        self.assertEqual(sorted(item.tickers[0] for item in kept), ["T2", "T4"])


class MainPartialWriteTests(unittest.TestCase):
    def _run_main(self, holdings: dict, failing: set[str], prior_items: list[dict]):
        def fake_fetch(_session, query, _locale):
            return None if any(ticker in query for ticker in failing) else []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feed = root / "dashboard" / "data" / "portfolio_news.json"
            feed.parent.mkdir(parents=True)
            feed.write_text(json.dumps({"items": prior_items}), encoding="utf-8")
            with mock.patch.object(ingest, "ROOT", root), \
                    mock.patch.object(ingest, "PORTFOLIO_NEWS_PATH", feed), \
                    mock.patch.object(ingest, "NEWS_SEEN_PATH", root / "news_seen.json"), \
                    mock.patch.object(ingest, "load_holding_configs", return_value=holdings), \
                    mock.patch.object(ingest, "_fetch_google_news_rss", side_effect=fake_fetch), \
                    mock.patch.object(ingest, "phase_two_phase_theme_news", return_value=[]), \
                    mock.patch.object(ingest, "_load_filing_urls", return_value={}), \
                    mock.patch.object(sys, "argv", ["ingest", "--skip-polygon", "--no-review"]), \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                status = ingest.main()
            payload = json.loads(feed.read_text(encoding="utf-8"))
        return status, payload, out.getvalue()

    @staticmethod
    def _prior(ticker: str) -> dict:
        return {"id": f"gnews:{ticker.lower()}", "tickers": [ticker], "source": "google_news",
                "published_utc": recent(), "url": f"https://example.test/{ticker}", "confidence": 0.8}

    def test_a_partial_run_keeps_prior_items_and_records_coverage(self) -> None:
        holdings = {"T1": config("T1"), "T2": config("T2")}
        status, payload, _ = self._run_main(holdings, {"T2"}, [self._prior("T1"), self._prior("T2")])
        self.assertEqual(status, 0)  # half the book refreshed: partial, not failed
        ids = [item["id"] for item in payload["items"]]
        self.assertEqual(ids, ["gnews:t2"])  # T1 refreshed (no news now); T2 kept
        coverage = payload["coverage"]
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["google"]["failed_tickers"], ["T2"])
        self.assertEqual(coverage["carried_over_items"], 1)
        self.assertNotIn("refreshed_tickers", coverage["google"])

    def test_a_mostly_failed_run_writes_its_feed_then_fails(self) -> None:
        holdings = {ticker: config(ticker) for ticker in ("T1", "T2", "T3", "T4")}
        status, payload, out = self._run_main(
            holdings, {"T2", "T3", "T4"}, [self._prior(t) for t in ("T2", "T3")]
        )
        self.assertEqual(status, 1)
        self.assertIn("::error", out)
        self.assertIn("1/4 holdings refreshed", out)
        # ...but only after the partial feed, with prior items, was written.
        self.assertEqual(sorted(item["id"] for item in payload["items"]), ["gnews:t2", "gnews:t3"])
        self.assertEqual(payload["coverage"]["google"]["refreshed"], 1)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
