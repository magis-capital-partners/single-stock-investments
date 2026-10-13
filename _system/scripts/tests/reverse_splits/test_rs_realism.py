"""Worked examples for nominal prices, fills, and the shared book."""

from __future__ import annotations

from datetime import datetime, timezone

from reverse_splits.adjust import PriceFrame, path_blocked, to_nominal
from reverse_splits.book import Candidate, Settings, build_candidates, simulate
from reverse_splits.execute import entry_index, full_spread, short_fills, trade_pnl
from reverse_splits.filings import parse_accept_time, parse_announcement, vote_path_from_form


def _frame(rows: list[tuple]) -> PriceFrame:
    return PriceFrame(
        dates=[r[0] for r in rows],
        open=[r[1] for r in rows],
        high=[r[2] for r in rows],
        low=[r[3] for r in rows],
        close=[r[4] for r in rows],
        volume=[r[5] for r in rows],
    )


def test_raw_one_for_ten_stays_nominal_and_flags_the_jump():
    # Printed prices gap from 0.40 to 4.00 on the ex-date.
    frame = _frame(
        [
            ("2024-01-16", 0.50, 0.55, 0.45, 0.50, 100_000),
            ("2024-01-17", 0.42, 0.48, 0.38, 0.40, 100_000),
            ("2024-01-18", 4.10, 4.40, 3.80, 4.00, 10_000),
            ("2024-01-19", 3.70, 3.90, 3.40, 3.60, 12_000),
        ]
    )
    nominal = to_nominal(frame, [("2024-01-18", 0.1)])
    assert nominal.splits[0].status == "raw"
    assert nominal.frame.close == [0.50, 0.40, 4.00, 3.60]
    assert nominal.frame.volume[1] == 100_000


def test_continuous_one_for_ten_rebuilds_the_printed_price():
    # Vendor series is already in post-split dollars. Volume was shrunk 10x.
    frame = _frame(
        [
            ("2024-01-16", 5.0, 5.5, 4.5, 5.0, 10_000),
            ("2024-01-17", 4.2, 4.8, 3.8, 4.0, 10_000),
            ("2024-01-18", 4.1, 4.4, 3.8, 4.0, 10_000),
            ("2024-01-19", 3.7, 3.9, 3.4, 3.6, 12_000),
        ]
    )
    nominal = to_nominal(frame, [("2024-01-18", 0.1)])
    assert nominal.splits[0].status == "continuous"
    assert abs(nominal.frame.close[1] - 0.40) < 1e-9
    assert abs(nominal.frame.close[2] - 4.00) < 1e-9
    assert abs(nominal.frame.volume[1] - 100_000) < 1e-6
    assert nominal.frame.volume[2] == 10_000


def test_jump_one_session_late_is_still_raw():
    frame = _frame(
        [
            ("2024-01-17", 0.4, 0.5, 0.3, 0.40, 1),
            ("2024-01-18", 0.4, 0.5, 0.3, 0.42, 1),
            ("2024-01-19", 4.0, 4.2, 3.8, 4.00, 1),
        ]
    )
    nominal = to_nominal(frame, [("2024-01-18", 0.1)], window=3)
    assert nominal.splits[0].status == "raw"
    assert nominal.splits[0].post_index == 2


def test_news_gap_on_a_continuous_series_is_not_called_a_split():
    # 1-for-10 would be a 10x jump. A 2x move is news, and the series is continuous.
    frame = _frame(
        [
            ("2024-01-17", 2.0, 2.1, 1.9, 2.0, 1),
            ("2024-01-18", 4.0, 4.2, 3.8, 4.0, 1),
        ]
    )
    nominal = to_nominal(frame, [("2024-01-18", 0.1)])
    assert nominal.splits[0].status == "continuous"
    assert abs(nominal.frame.close[0] - 0.2) < 1e-9


def test_unmatched_gap_is_ambiguous_and_blocks_the_path():
    # 4.5x is neither a clean 10x raw jump nor a continuous print.
    frame = _frame(
        [
            ("2024-01-17", 1.0, 1.1, 0.9, 1.0, 1),
            ("2024-01-18", 4.5, 4.6, 4.4, 4.5, 1),
            ("2024-01-19", 4.4, 4.5, 4.3, 4.4, 1),
        ]
    )
    nominal = to_nominal(frame, [("2024-01-18", 0.1)])
    assert nominal.splits[0].status == "ambiguous"
    assert path_blocked(0, 1, nominal)


def test_two_continuous_splits_compound_the_nominal_scale():
    # Final continuous price is 40 before the first split (0.40 * 10 * 10).
    frame = _frame(
        [
            ("2024-01-02", 40, 40, 40, 40, 1_000),
            ("2024-02-02", 40, 40, 40, 40, 1_000),
            ("2024-03-04", 4, 4, 4, 4, 10_000),
        ]
    )
    nominal = to_nominal(frame, [("2024-02-02", 0.1), ("2024-03-04", 0.1)])
    assert nominal.splits[0].status == "continuous"
    assert nominal.splits[1].status == "continuous"
    assert abs(nominal.frame.close[0] - 0.40) < 1e-9
    assert abs(nominal.frame.close[1] - 4.0) < 1e-9
    assert abs(nominal.frame.close[2] - 4.0) < 1e-9


def test_next_open_respects_the_clock_and_date_only_filings():
    dates = ["2024-01-04", "2024-01-05", "2024-01-08"]
    before_open = datetime(2024, 1, 5, 8, 0, tzinfo=timezone.utc)  # 03:00 ET
    assert entry_index(dates, accept=before_open) == 1
    after_close = datetime(2024, 1, 5, 22, 0, tzinfo=timezone.utc)  # 17:00 ET
    assert entry_index(dates, accept=after_close) == 2
    assert entry_index(dates, filed="2024-01-05") == 2


def test_accept_time_parsing_handles_edgar_zulu_offsets_and_date_only():
    zulu = parse_accept_time("2022-10-06T21:16:59.000Z")
    assert zulu is not None and zulu.tzinfo is not None and zulu.hour == 21
    offset = parse_accept_time("2024-01-05T08:00:00-05:00")
    assert offset is not None and offset.utcoffset().total_seconds() == -5 * 3600
    assert parse_accept_time("2024-01-05").tzinfo is None  # a date-only print is not a clock
    assert parse_accept_time("not a time") is None
    assert parse_accept_time(None) is None


def test_spread_uses_the_penny_floor_or_the_prior_range():
    assert full_spread(1.02, 1.01, floor=0.01, range_fraction=0.25) == 0.01
    assert abs(full_spread(1.50, 1.00, floor=0.01, range_fraction=0.25) - 0.125) < 1e-9
    assert full_spread(None, None, floor=0.01, range_fraction=0.25) == 0.01


def test_short_pnl_matches_a_worked_fill():
    fills = short_fills(entry_px=2.00, exit_px=1.80, spread_entry=0.02, spread_exit=0.02)
    assert fills is not None
    sold, bought = fills
    gross, fee, net = trade_pnl(shares=100, entry_fill=sold, exit_fill=bought, fee_annual=1.0, hold_days=7)
    # Sold at 1.99, covered at 1.81. Gross = 18. Fee = 100 * 1.99 * 7/365.
    assert abs(gross - 18.0) < 1e-9
    assert abs(fee - (199 * 7 / 365)) < 1e-9
    assert abs(net - (gross - fee)) < 1e-9


def test_held_through_split_share_count_is_not_a_tenfold_loss():
    # 1,000 shares at $0.40, 1-for-10, cover 100 shares at $3.60.
    gross, fee, net = trade_pnl(
        shares=1000, entry_fill=0.40, exit_fill=3.60, fee_annual=0.0, hold_days=2, share_factor=0.1
    )
    assert abs(gross - (400 - 360)) < 1e-9
    assert fee == 0
    assert abs(net - 40) < 1e-9


def test_parse_board_announcement_and_a_cancellation():
    text = (
        "On January 5, 2024, the Board of Directors approved a one-for-ten reverse stock split "
        "of the Company's common stock, to be effective on January 22, 2024."
    )
    parsed = parse_announcement(text)
    assert parsed["ratio"] == 0.1
    assert parsed["announced_ex_date"] == "2024-01-22"
    assert parsed["vote_path"] == "board"
    assert parsed["cancelled"] is False
    assert vote_path_from_form("DEF 14A") == "shareholder"
    assert vote_path_from_form("DEF 14C") == "consent"

    cancelled = parse_announcement(
        "The Company determined not to proceed with the proposed reverse stock split."
    )
    assert cancelled["cancelled"] is True
    numeric = parse_announcement("A 1-for-25 reverse split effective 03/15/2024.")
    assert numeric["ratio"] == 0.04 and numeric["announced_ex_date"] == "2024-03-15"


def _settings(**overrides) -> Settings:
    base = dict(
        signal="announce",
        horizon=5,
        min_price=1.0,
        spread_floor=0.01,
        spread_range_fraction=0.25,
        force_cover=True,
        max_book=50_000,
        max_names=10,
        target_notional=5_000,
        max_participation=0.25,
        fee_annual=1.0,
        borrow_policy="assumed_fee",
        listed_only=True,
        require_filing_text=False,
        jump_window=3,
        cohorts=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_book_forces_cover_before_ex_and_drops_subdollar_prints():
    # Warmup sessions so ADV exists, then a raw 1-for-10. The 7-session hold
    # would include the ex-date, so the short is covered the session before.
    rows = []
    for day, px in (
        ("2024-01-02", 2.20),
        ("2024-01-03", 2.15),
        ("2024-01-04", 2.10),
        ("2024-01-05", 2.05),
        ("2024-01-08", 2.00),
        ("2024-01-09", 1.95),
        ("2024-01-10", 1.90),
        ("2024-01-11", 1.85),
        ("2024-01-12", 1.80),
        ("2024-01-16", 1.75),
        ("2024-01-17", 1.70),
    ):
        rows.append((day, px, px + 0.05, px - 0.05, px, 80_000))
    rows.append(("2024-01-18", 18.0, 19.0, 17.0, 18.0, 8_000))
    frame = _frame(rows)
    events = [
        {
            "id": 1,
            "ticker": "RS",
            "cohort": "first",
            "exchange_class": "listed",
            "outcome": "effective",
            "ex_date": "2024-01-18",
            "ratio": 0.1,
            "announce_date": "2024-01-08",
            "accept_time": "2024-01-08T13:00:00+00:00",  # 08:00 ET
            "date_quality": "acceptance_time",
            "name": "Example",
        }
    ]
    eligible, funnel = build_candidates(events, {"RS": frame}, _settings(horizon=7, fee_annual=0.0))
    assert funnel["taken_pool"] == 1
    trade = eligible[0]
    assert trade.entry_date == "2024-01-08"
    assert trade.exit_date == "2024-01-17"
    assert trade.forced_cover is True
    assert trade.exit_fill < 3

    cheap = _frame(
        [
            ("2024-01-08", 0.40, 0.45, 0.35, 0.40, 80_000),
            ("2024-01-09", 0.38, 0.42, 0.34, 0.38, 80_000),
            ("2024-01-10", 0.36, 0.40, 0.32, 0.36, 80_000),
        ]
    )
    _, cheap_funnel = build_candidates(
        [
            {
                "id": 2,
                "ticker": "PENNY",
                "cohort": "first",
                "exchange_class": "listed",
                "outcome": "announced_only",
                "ex_date": "2024-01-08",
                "ratio": 1,
                "announce_date": "2024-01-05",
                "accept_time": None,
                "date_quality": "search_hit",
                "name": "Penny",
            }
        ],
        {"PENNY": cheap},
        _settings(horizon=1),
    )
    assert cheap_funnel["below_min_price"] == 1
    assert cheap_funnel["taken_pool"] == 0


def test_shared_book_respects_cash_and_name_cap():
    def candidate(ticker: str, pnl_per_share: float) -> Candidate:
        return Candidate(
            event_id=1,
            ticker=ticker,
            name=ticker,
            cohort="first",
            exchange_class="listed",
            outcome="effective",
            signal="announce",
            entry_date="2024-01-08",
            exit_date="2024-01-12",
            entry_fill=10.0,
            exit_fill=10.0 - pnl_per_share,
            shares=100,
            hold_days=4,
            forced_cover=False,
            jump_status="raw",
            adv_shares=10_000,
            exit_volume=10_000,
            share_factor=1.0,
            marks={"2024-01-08": 10.0, "2024-01-12": 10.0 - pnl_per_share},
        )

    taken, skipped, equity = simulate(
        [candidate("AAA", 1.0), candidate("BBB", 1.0)],
        max_book=1_500,
        max_names=10,
        fee_annual=0.0,
    )
    assert [t.ticker for t in taken] == ["AAA"]
    assert skipped["cash"] == 1
    assert abs(taken[0].net_pnl - 100) < 1e-9
    assert abs(equity[-1]["equity"] - 1_600) < 1e-6

    taken_one, skipped_one, _ = simulate(
        [candidate("AAA", 1.0), candidate("BBB", 1.0)],
        max_book=50_000,
        max_names=1,
        fee_annual=0.0,
    )
    assert len(taken_one) == 1
    assert skipped_one["max_names"] == 1


def test_strict_borrow_drops_a_name_without_a_locate():
    frame = _frame(
        [
            ("2024-01-05", 5, 5.2, 4.8, 5, 50_000),
            ("2024-01-08", 5, 5.2, 4.8, 5, 50_000),
            ("2024-01-09", 4.8, 5.0, 4.6, 4.8, 50_000),
            ("2024-01-10", 4.6, 4.8, 4.4, 4.6, 50_000),
        ]
    )
    event = {
        "id": 1,
        "ticker": "LOC",
        "cohort": "second",
        "exchange_class": "listed",
        "outcome": "announced_only",
        "ex_date": "2024-02-01",
        "ratio": 1,
        "announce_date": "2024-01-05",
        "accept_time": "2024-01-05T21:00:00+00:00",
        "date_quality": "acceptance_time",
        "name": "Locate",
    }
    _, funnel = build_candidates([event], {"LOC": frame}, _settings(borrow_policy="strict", horizon=1))
    assert funnel["no_locate"] == 1
    eligible, ok = build_candidates([event], {"LOC": frame}, _settings(borrow_policy="assumed_fee", horizon=1))
    assert ok["taken_pool"] == 1
    assert eligible[0].entry_date == "2024-01-08"


def test_outcomes_filter_keeps_completed_splits_only():
    frame = _frame(
        [
            ("2024-01-05", 5, 5.2, 4.8, 5, 50_000),
            ("2024-01-08", 5, 5.2, 4.8, 5, 50_000),
            ("2024-01-09", 4.8, 5.0, 4.6, 4.8, 50_000),
        ]
    )
    shared = {
        "cohort": "first",
        "exchange_class": "listed",
        "ex_date": "2024-02-01",
        "ratio": 1,
        "announce_date": "2024-01-05",
        "accept_time": "2024-01-05T21:00:00+00:00",
        "date_quality": "acceptance_time",
        "name": "Name",
    }
    events = [
        {"id": 1, "ticker": "DONE", "outcome": "effective", **shared},
        {"id": 2, "ticker": "PHRASE", "outcome": "announced_only", **shared},
    ]
    frames = {"DONE": frame, "PHRASE": frame}
    kept, funnel = build_candidates(events, frames, _settings(horizon=1, outcomes=("effective",)))
    assert [row.ticker for row in kept] == ["DONE"]
    assert funnel["outcome"] == 1


def test_finra_short_interest_does_not_set_the_share_count():
    from reverse_splits.borrow import position_cap_shares

    shares, source, _ = position_cap_shares(
        price=5.0,
        target_notional=5_000,
        shortable_shares=None,
        max_participation=0.25,
        finra_si=10,
        adv=100_000,
    )
    assert shares == 1_000  # $5,000 / $5, not 25% of the 10-share short-interest print
    assert source == "target_notional"
