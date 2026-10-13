"""Reg SHO 201 at the open, and event windows for the Databento price loader.

The state at the open is the last explicit Y/N at or before 09:30 New York
time, carried across days; the book's "exclude" policy drops a restricted entry,
"delay" moves it to the next unrestricted session (at most two), and "ignore"
leaves every existing book unchanged. A renamed ledger ticker is priced under
the symbol it carried at the split.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from reverse_splits.adjust import PriceFrame
from reverse_splits.book import Settings, build_candidates, ssr_entry
from reverse_splits.databento_prices import event_windows, open_states


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_open_state_is_the_last_explicit_flag_by_nine_thirty_new_york():
    messages = [
        (utc("2025-02-10T15:00:00"), "Y"),   # 10:00 ET Monday: triggered intraday
        (utc("2025-02-11T09:00:00"), "Y"),   # 04:00 ET Tuesday: carried over
        (utc("2025-02-11T18:00:00"), "~"),   # no information
        (utc("2025-02-12T09:00:00"), "N"),   # 04:00 ET Wednesday: lapsed
        (utc("2025-02-13T15:00:00"), "Y"),   # 10:00 ET Thursday: after the open
    ]
    days = [date(2025, 2, d) for d in (10, 11, 12, 13, 14)]
    assert open_states(messages, days) == {
        date(2025, 2, 10): False, date(2025, 2, 11): True, date(2025, 2, 12): False,
        date(2025, 2, 13): False, date(2025, 2, 14): True,
    }


def _frame():
    rows = [("2024-01-%02d" % d, p, p * 1.05, p * 0.95, p, v) for d, p, v in
            [(8, 0.5, 1e5), (9, 0.5, 1e5), (10, 0.5, 1e5), (11, 0.5, 1e5), (12, 0.45, 1e5), (16, 0.42, 1e5), (17, 0.40, 1e5),
             (18, 4.0, 1e4), (19, 3.8, 1e4), (22, 3.6, 1e4), (23, 3.5, 1e4), (24, 3.4, 1e4), (25, 3.3, 1e4), (26, 3.2, 1e4)]]
    return PriceFrame(dates=[r[0] for r in rows], open=[r[1] for r in rows], high=[r[2] for r in rows],
                      low=[r[3] for r in rows], close=[r[4] for r in rows], volume=[r[5] for r in rows])


EVENT = {"id": 1, "ticker": "AAA", "ex_date": "2024-01-18", "ratio": 0.1, "split_from": 10.0, "split_to": 1.0,
         "outcome": "effective", "exchange_class": "listed", "cohort": "first"}


def _run(policy, flags):
    settings = Settings(signal="ex_plus_1", horizon=2, min_price=1.0, ssr_policy=policy, ssr_flags=frozenset(flags))
    return build_candidates([EVENT], {"AAA": _frame()}, settings)


def test_ignore_leaves_the_book_unchanged():
    eligible, funnel = _run("ignore", {("AAA", "2024-01-19")})
    assert len(eligible) == 1 and "ssr_restricted" not in funnel


def test_exclude_drops_a_restricted_entry():
    eligible, funnel = _run("exclude", {("AAA", "2024-01-19")})
    assert eligible == [] and funnel["ssr_restricted"] == 1


def test_delay_moves_to_the_next_unrestricted_session_but_not_forever():
    dates = _frame().dates
    settings = Settings(ssr_policy="delay", ssr_flags=frozenset({("AAA", "2024-01-19"), ("AAA", "2024-01-22")}))
    assert dates[ssr_entry("AAA", dates, 8, settings)] == "2024-01-23"
    settings3 = Settings(ssr_policy="delay", ssr_flags=frozenset({("AAA", d) for d in ("2024-01-19", "2024-01-22", "2024-01-23")}))
    assert ssr_entry("AAA", dates, 8, settings3) is None, "three restricted sessions exceed the two-session delay"
    eligible, funnel = _run("delay", {("AAA", "2024-01-19")})
    assert len(eligible) == 1 and "ssr_restricted" not in funnel


def test_windows_price_a_renamed_ticker_under_its_filing_time_symbol():
    events = [EVENT, dict(EVENT, ticker="DCOY", ex_date="2022-10-17"), dict(EVENT, ticker="OTCX", exchange_class="otc")]
    joins = [{"ticker": "DCOY", "ex_date": "2022-10-17", "filing_time_symbol": "SLRX"}]
    wins = event_windows(events, joins)
    assert [(w["ticker"], w["norm"]) for w in wins] == [("AAA", "AAA"), ("DCOY", "SLRX")]
    assert wins[0]["lo"] == date(2023, 9, 20) and wins[0]["hi"] == date(2024, 3, 18)
