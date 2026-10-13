"""SEC filing checks for price-detected splits, without the network.

EDGAR display names carry today's tickers, so a delisted or renamed issuer is
found through the ticker in its own filings' text. That route counts only the
issuer's own forms (a prospectus mentions other companies' tickers), skips
two-letter tickers, and needs two filings from a company that lists a different
live ticker. EDGAR errors raise and are never cached as "not found".
"""
from __future__ import annotations

from datetime import date

import pytest

from reverse_splits import filing_check as fc


def src(name, cik, form="8-K", filed="2020-08-07", adsh="0000000000-20-000001"):
    return {"display_names": [name], "ciks": [cik], "root_forms": [form], "file_date": filed, "adsh": adsh}


class FakeHttp:
    def __init__(self, by_query, fail=False):
        self.by_query, self.fail, self.calls = by_query, fail, []

    def get(self, url, params):
        self.calls.append(params)
        if self.fail:
            raise RuntimeError("500 Server Error")
        hits = self.by_query.get(params["q"], [])
        return type("R", (), {"json": lambda self: {"hits": {"hits": [{"_source": h} for h in hits]}}})()


def search(by_query, **kw):
    return fc.FilingSearch(FakeHttp(by_query, **kw), backoff=0)


def test_display_names_parse_to_tickers():
    assert fc.tickers_in(["Workhorse Group Inc.  (WKHS, WKHSW)  (CIK 0001425287)"]) == {"WKHS", "WKHSW"}
    assert fc.tickers_in(["Callon Petroleum Co  (CIK 0000928022)"]) == set()


def test_a_live_ticker_in_the_display_name_confirms():
    fs = search({'"reverse stock split" "WKHS"': [src("Workhorse Group Inc.  (WKHS)  (CIK 0001425287)", "1425287")]})
    res = fs.confirm("WKHS", date(2025, 3, 17))
    assert res["status"] == "filing_confirmed" and res["method"] == "display_ticker" and res["cik"] == "0001425287"


def test_a_delisted_issuer_is_found_through_its_own_filing_text():
    fs = search({'"reverse stock split" "CPE"': [src("Callon Petroleum Co  (CIK 0000928022)", "928022")]})
    res = fs.confirm("CPE", date(2020, 8, 10))
    assert (res["status"], res["method"], res["form"], res["cik"]) == ("filing_confirmed", "ticker_text", "8-K", "0000928022")


def test_a_prospectus_mention_is_not_the_issuer():
    fs = search({'"reverse stock split" "ERNA"': [src("INSPIRE VETERINARY PARTNERS, INC.  (IVP)  (CIK 0001939365)", "1939365", form="S-1")]})
    assert fs.confirm("ERNA", date(2023, 12, 14))["status"] == "not_found"


def test_a_company_with_another_live_ticker_needs_two_of_its_own_filings():
    one = {'"reverse stock split" "KOOL"': [src("CESCA THERAPEUTICS INC.  (THMO)  (CIK 0000811212)", "811212")]}
    assert search(one).confirm("KOOL", date(2019, 6, 14))["status"] == "not_found"
    two = {'"reverse stock split" "KOOL"': [src("CESCA THERAPEUTICS INC.  (THMO)  (CIK 0000811212)", "811212"),
                                             src("CESCA THERAPEUTICS INC.  (THMO)  (CIK 0000811212)", "811212", form="DEF 14A")]}
    assert search(two).confirm("KOOL", date(2019, 6, 14))["cik"] == "0000811212"


def test_two_letter_tickers_never_use_the_text_route():
    fs = search({'"reverse stock split" "ON"': [src("Some Issuer  (CIK 0000000001)", "1")]})
    assert fs.confirm("ON", date(2024, 1, 2))["status"] == "not_found"


def test_edgar_errors_raise_and_are_not_cached_as_negative():
    fs = search({}, fail=True)
    with pytest.raises(fc.SearchError):
        fs.confirm("WKHS", date(2025, 3, 17))
    assert fs.cache == {}
    assert len(fs.http.calls) == fs.retries


def test_results_are_cached_per_ticker_and_day():
    fs = search({'"reverse stock split" "WKHS"': [src("Workhorse Group Inc.  (WKHS)  (CIK 0001425287)", "1425287")]})
    fs.confirm("WKHS", date(2025, 3, 17))
    calls = len(fs.http.calls)
    fs.confirm("wkhs", date(2025, 3, 17))
    assert len(fs.http.calls) == calls


def test_rename_candidates_are_near_in_time_and_ratio():
    event = {"ticker": "DCOY", "ex_date": "2022-10-17", "ratio": 0.04}  # 1:25
    dets = [
        {"symbol": "SLRX", "day": date(2022, 10, 17), "ratio_inferred": 25},
        {"symbol": "ABCD", "day": date(2022, 10, 18), "ratio_inferred": 5},     # wrong ratio
        {"symbol": "EFGH", "day": date(2022, 11, 30), "ratio_inferred": 25},    # too far
        {"symbol": "DCOY", "day": date(2022, 10, 17), "ratio_inferred": 25},    # same ticker: not a rename
    ]
    assert [d["symbol"] for d in fc.rename_matches(event, dets)] == ["SLRX"]
