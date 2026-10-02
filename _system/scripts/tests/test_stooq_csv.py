"""Stooq answers scripted requests with HTML and HTTP 200; nothing may store or parse it."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_market_data_csvs  # noqa: E402
from stooq_csv import DAILY_HEADER, QUOTE_HEADER, StooqNotCsvError, check_stooq_csv  # noqa: E402

BOT_CHECK = (
    b'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><noscript>This site requires '
    b"JavaScript to verify your browser. Please enable JavaScript and reload.</noscript><script>"
    b'(async()=>{const c="AAAA",d=4;const r=await fetch("/__verify",{method:"POST"})})();'
    b"</script></body></html>\n"
)
NOT_FOUND = b"<meta charset=utf-8><title>Stooq</title><p>The page you requested does not exist\n"
APIKEY = b"Get your apikey:\n\n1. Open https://stooq.com/q/d/?s=spy.us&get_apikey\n"
DAILY = b"Date,Open,High,Low,Close,Volume\n2026-09-30,600,601,599,600.5,1000\n"
QUOTE = b"Symbol,Date,Time,Open,High,Low,Close,Volume\nSPY.US,2026-09-30,22:00:00,600,601,599,600.5,1000\n"


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_bot_check_is_named():
    with pytest.raises(StooqNotCsvError, match="bot-check"):
        check_stooq_csv(BOT_CHECK)


@pytest.mark.parametrize("body", [NOT_FOUND, APIKEY, b"", b"Symbol,Date\n"])
def test_other_non_csv_bodies_fail(body):
    with pytest.raises(StooqNotCsvError):
        check_stooq_csv(body, DAILY_HEADER)


def test_valid_bodies_pass():
    assert check_stooq_csv(DAILY, DAILY_HEADER).startswith("Date,")
    assert check_stooq_csv(QUOTE, QUOTE_HEADER).startswith("Symbol,")
    assert check_stooq_csv(b"\xef\xbb\xbf" + DAILY).startswith("Date,")
    with pytest.raises(StooqNotCsvError):
        check_stooq_csv(DAILY, QUOTE_HEADER)


def test_download_never_writes_html(tmp_path):
    import download_ira_research as ira

    dest = tmp_path / "benchmarks" / "spy_us.csv"
    dest.parent.mkdir()
    dest.write_bytes(DAILY)
    for body in (BOT_CHECK, APIKEY):
        with patch.object(ira.urllib.request, "urlopen", return_value=_Response(body)):
            ok, msg = ira.fetch_url("https://stooq.com/q/d/l/?s=spy.us&i=d", dest)
        assert not ok and "not written" in msg
        assert dest.read_bytes() == DAILY
    with patch.object(ira.urllib.request, "urlopen", return_value=_Response(b"<html>oops</html>")):
        ok, _ = ira.fetch_url("https://fred.stlouisfed.org/graph/fredgraph.csv?id=X", dest)
    assert not ok and dest.read_bytes() == DAILY


def test_ira_benchmarks_no_longer_come_from_stooq():
    import download_ira_research as ira

    assert not any("stooq" in (url or "") for url in ira.TIER_B_URLS.values())
    assert ira.TIER_B_YAHOO_DAILY["benchmarks/spy_us.csv"] == "SPY"


def test_technical_signals_stooq_fallback_names_the_bot_check():
    import build_technical_signals as bts

    with patch.object(bts, "_request", return_value=BOT_CHECK):
        with pytest.raises(StooqNotCsvError, match="bot-check"):
            bts.fetch_stooq_history("spy.us")


def test_equity_price_stooq_html_is_an_error_and_yahoo_is_tried_first():
    import fetch_equity_prices as prices

    with patch.object(prices.urllib.request, "urlopen", return_value=_Response(NOT_FOUND)):
        close, _, err = prices.fetch_stooq_close("spy.us")
    assert close is None and "HTML" in err

    with patch.object(prices, "registry_row", return_value={"market": "US"}), patch.object(
        prices, "fetch_yahoo_close", return_value=(600.5, "2026-09-30", None)
    ), patch.object(prices, "fetch_stooq_close") as stooq:
        close, _, source = prices.fetch_price("SPY")
    assert close == 600.5 and source.startswith("Yahoo")
    stooq.assert_not_called()


def test_book_estimate_falls_back_to_yahoo():
    import current_book_estimate as cbe

    with patch.object(cbe.urllib.request, "urlopen", return_value=_Response(NOT_FOUND)):
        assert cbe.fetch_stooq_close("MIAX.US")[0] is None
    cache: dict = {}
    line = {"method": "listed_shares", "symbol": "MIAX.US"}
    with patch.object(cbe, "fetch_yahoo_latest_close", return_value=(40.0, None)):
        assert cbe.resolve_price(line, cache) == (40.0, "yahoo", None)


def test_checker_flags_html_csv(tmp_path):
    (tmp_path / "ok.csv").write_bytes(DAILY)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "bad.csv").write_bytes(BOT_CHECK)
    (tmp_path / "apikey.csv").write_bytes(APIKEY)
    bad = {p.name for p, _ in check_market_data_csvs.scan(tmp_path)}
    assert bad == {"bad.csv", "apikey.csv"}
    assert check_market_data_csvs.main([str(tmp_path)]) == 1


def test_committed_market_data_csvs_are_csv():
    """The CI unit-test checkout excludes the reference corpus; the
    market-data-csvs job in python-tests.yml runs the checker there."""
    if not check_market_data_csvs.MARKET_DATA.is_dir():
        pytest.skip("market-data not checked out")
    bad = check_market_data_csvs.scan(check_market_data_csvs.MARKET_DATA)
    assert not bad, [f"{p.relative_to(ROOT)}: {why}" for p, why in bad]
