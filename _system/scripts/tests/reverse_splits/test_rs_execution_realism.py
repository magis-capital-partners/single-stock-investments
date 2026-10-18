"""Workstream A: the data cost gate, the Rule 201 queue model, participation pricing, commissions, sealing."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from conftest import ROOT

import check_reverse_splits
from reverse_splits import execution_realism as er
from reverse_splits import execution_realism_build as b
from reverse_splits import hypotheses as hyp
from reverse_splits.config import Config
from reverse_splits.ledger import load_jsonl, write_json, write_jsonl

LEDGER = ROOT / "_system" / "data" / "reverse_splits"
S = 10**9  # nanoseconds per second
T0 = 1_700_000_000 * S


def _book(records, *, flags=b.F_LAST):
    """records: (seconds, action, side, price, size, bid, ask, bid_sz, ask_sz)."""
    cols = list(zip(*records))
    return {"ts": np.array([T0 + int(c * S) for c in cols[0]], dtype="int64"),
            "action": np.array(cols[1]), "side": np.array(cols[2]),
            "price": np.array(cols[3], dtype=float), "size": np.array(cols[4], dtype="int64"),
            "flags": np.full(len(records), flags, dtype="int64"),
            "bid": np.array(cols[5], dtype=float), "ask": np.array(cols[6], dtype=float),
            "bid_sz": np.array(cols[7], dtype="int64"), "ask_sz": np.array(cols[8], dtype="int64")}


def _event(**over):
    base = {"key": "event/x", "event_id": "event/x", "ticker": "AAA", "symbol": "AAA", "dataset": "XNAS.ITCH", "issuer": "cik/1",
            "entry_date": "2023-06-01", "year": "2023", "split": "validate", "ex_date": "2023-05-31", "ratio": 0.1,
            "open": 5.0, "close": 4.5, "opened": "2023-06-01T13:30:00+00:00", "closed": "2023-06-01T20:00:00+00:00",
            "ret": 0.1, "exchange_class": "listed", "ssr_state": "restricted", "prior_sessions": 20, "adv_shares": 50_000.0}
    base.update(over)
    return base


# --- sizing and commissions ---------------------------------------------------------------

def test_whole_shares_bands_and_ticks():
    assert er.whole_shares(1250, 5.0) == 250 and er.whole_shares(1250, 7.0) == 178 and er.whole_shares(1250, 0) == 0
    assert er.price_band(0.5) == "under_1" and er.price_band(1.0) == "1_to_2" and er.price_band(4.99) == "2_to_5" and er.price_band(5.0) == "5_and_over"
    assert b.tick_size(1.0) == 0.01 and b.tick_size(0.99) == 0.0001


def test_commission_schedules():
    fixed = er.commission_leg("fixed", 100, 5.0, passive=False, sell=True)
    assert fixed["commission"] == 1.0 and fixed["venue"] == 0 and fixed["clearing"] == 0        # $0.50 lifts to the $1 minimum
    assert er.commission_leg("fixed", 1000, 5.0, passive=False, sell=False)["commission"] == 5.0
    assert er.commission_leg("fixed", 1000, 0.05, passive=False, sell=False)["commission"] == pytest.approx(0.5)  # 1% of $50 notional
    tiered = er.commission_leg("tiered", 100, 5.0, passive=False, sell=True)
    assert tiered["commission"] == pytest.approx(0.35) and tiered["venue"] == pytest.approx(0.30) and tiered["clearing"] == pytest.approx(0.02)
    passive = er.commission_leg("tiered", 1000, 5.0, passive=True, sell=True)
    assert passive["commission"] == pytest.approx(3.5) and passive["venue"] == pytest.approx(-2.0)
    assert fixed["regulatory"] == pytest.approx(er.SEC_FEE_PER_DOLLAR * 500 + 100 * er.FINRA_TAF_PER_SHARE)
    assert er.commission_leg("fixed", 100, 5.0, passive=False, sell=False)["regulatory"] == 0
    assert er.commission_leg("fixed", 100_000, 5.0, passive=False, sell=True)["regulatory"] == pytest.approx(er.SEC_FEE_PER_DOLLAR * 500_000 + er.FINRA_TAF_MAX)
    assert er.commission_leg("fixed", 0, 5.0, passive=False, sell=True)["total"] == 0
    rt = b._round_trip("tiered", 100, 5.0, 4.5, passive_entry=True)
    assert rt["usd"] == pytest.approx(0.35 - 0.2 + 0.02 + 0.35 + 0.30 + 0.02) and rt["fraction"] == pytest.approx(rt["usd"] / 500)


# --- requests and the cost gate -------------------------------------------------------------

def test_requests_group_symbols_per_venue_session_and_flag_the_alternative():
    rows = [_event(key="event/a", symbol="AAA"), _event(key="event/b", symbol="BBB", issuer="cik/2"),
            _event(key="event/c", symbol="CCC", issuer="cik/3", entry_date="2025-02-03", year="2025", split="holdout",
                   opened="2025-02-03T14:30:00+00:00", closed="2025-02-03T21:00:00+00:00")]
    items = er.requests_for(rows)
    assert len(items) == 8 and sum(i["planned"] for i in items) == 6
    same_day = [i for i in items if i["date"] == "2023-06-01" and i["schema"] == "trades"]
    assert len(same_day) == 1 and same_day[0]["request"]["symbols"] == ["AAA", "BBB"] and same_day[0]["events"] == 2
    assert same_day[0]["splits"] == ["validate"]
    opens = {i["window"]: i for i in items if i["date"] == "2023-06-01" and i["schema"] == "mbp-1"}
    assert opens["open"]["request"]["start"] == "2023-06-01T13:29:55+00:00"
    assert opens["open"]["request"]["end"] == "2023-06-01T14:35:05+00:00"
    assert opens["close"]["request"]["end"] == "2023-06-01T20:00:02+00:00" and opens["close"]["request"]["start"] == "2023-06-01T18:54:55+00:00"
    assert opens["session_alternative"]["planned"] is False
    assert all(i["id"] == er._request_id(i["request"]) for i in items)
    assert er.requests_for(rows) == items  # deterministic


def test_quote_summary_separates_planned_splits_and_alternatives():
    quotes = [{"planned": True, "schema": "trades", "window": "session", "splits": ["train"], "events": 2, "quoted_usd": 0.01, "status": "quoted"},
              {"planned": True, "schema": "mbp-1", "window": "open", "splits": ["holdout"], "events": 1, "quoted_usd": 0.02, "status": "quoted"},
              {"planned": False, "schema": "mbp-1", "window": "session_alternative", "splits": ["train"], "events": 2, "quoted_usd": 0.5, "status": "quoted"},
              {"planned": True, "schema": "mbp-1", "window": "close", "splits": ["train"], "events": 2, "quoted_usd": None, "status": "error"}]
    s = er.quote_summary(quotes)
    assert s["planned_total"] == {"requests": 2, "usd": pytest.approx(0.03), "events": 3}
    assert s["planned_by_split"]["holdout"]["usd"] == pytest.approx(0.02) and s["planned_train_validate_only"]["usd"] == pytest.approx(0.01)
    assert s["alternative_full_session_mbp1"]["usd"] == pytest.approx(0.5) and s["errors"] == 1
    assert s["max_single_request_usd"] == pytest.approx(0.5)


def test_download_refuses_without_quotes_or_above_the_approved_amount(tmp_path, monkeypatch):
    cfg = Config(raw={}, root=tmp_path)
    with pytest.raises(SystemExit, match="quote"):
        er.download(cfg, approved_usd=100.0, client=object())
    item = {"id": "abc", "planned": True, "schema": "trades", "window": "session", "splits": ["train"], "events": 1, "status": "quoted",
            "quoted_usd": 0.25, "request": {"dataset": "XNAS.ITCH", "schema": "trades", "symbols": ["AAA"], "start": "s", "end": "e"}}
    er.work_dir(cfg).mkdir(parents=True)
    write_json(er.work_dir(cfg) / "quotes.json", {"requests": [item], "summary": {}})
    with pytest.raises(SystemExit, match="exceeds the approved"):
        er.download(cfg, approved_usd=0.10, client=object())
    seen = []

    def fake_fetch(client, path, max_cost=0.0, *, quoted_cost=None, **request):
        seen.append((path, max_cost, quoted_cost))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        path.with_name(path.name.replace(".dbn.zst", ".ok.json")).write_text(json.dumps({"quoted_usd": quoted_cost, "bytes": 1}))
        return {"quoted_usd": quoted_cost, "bytes": 1}

    monkeypatch.setattr(er, "fetch", fake_fetch)
    done = er.download(cfg, approved_usd=0.25, client=object())
    assert done["files"] == 1 and done["quoted_usd"] == pytest.approx(0.25)
    assert seen[0][2] == 0.25 and seen[0][1] <= 0.25 + 1e-5
    assert er.raw_path(cfg, item).exists() and "sessions" in str(er.raw_path(cfg, item))
    again = er.download(cfg, approved_usd=0.0, client=object())  # nothing left to fetch, nothing spent
    assert again["files"] == 0 and len(seen) == 1
    approvals = json.loads((er.work_dir(cfg) / "approvals.json").read_text())
    assert [a["approved_usd"] for a in approvals] == [0.25, 0.0]
    big = {**item, "id": "big", "quoted_usd": er.MAX_QUOTE_PER_REQUEST + 1}
    write_json(er.work_dir(cfg) / "quotes.json", {"requests": [big], "summary": {}})
    with pytest.raises(SystemExit, match="ceiling"):
        er.download(cfg, approved_usd=1000.0, client=object())


# --- the passive offer under Rule 201 -----------------------------------------------------------

def test_passive_offer_needs_buyer_prints_after_the_queue_ahead():
    recs = [(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 300),   # arrival: offer 5.00 with 300 displayed ahead
            (10, "T", "B", 5.00, 200, 4.90, 5.00, 100, 100),  # buyer takes 200 of the 300 ahead
            (20, "T", "A", 4.90, 50, 4.90, 5.00, 50, 100),    # seller hits the bid: nothing for us
            (30, "T", "B", 5.00, 150, 4.90, 5.00, 50, 0),     # 100 more ahead consumed, then 50 of ours
            (40, "T", "B", 5.00, 100, 4.90, 5.05, 50, 500),   # fills the rest of our 100
            (400, "A", "B", 4.95, 100, 4.95, 5.05, 100, 500),
            (1000, "A", "B", 4.95, 100, 4.95, 5.15, 100, 500)]
    book = _book(recs)
    s = b.simulate_passive_offer(book, T0, 100, horizon_ns=900 * S)
    assert s["status"] == "simulated" and s["fully_filled"] and s["filled_shares"] == 100 and s["fill_vwap"] == 5.0
    assert s["time_to_fill_seconds"] == pytest.approx(40) and s["fills"] == 2 and s["repriced"] == 0
    assert s["initial_offer"] > s["arrival_bid"]
    assert s["filled_shares"] <= s["buyer_volume_at_or_above_offer"] == 450
    assert s["improvement_vs_arrival_mid"] == pytest.approx((5.0 - 4.95) / 4.95)
    assert s["markout_300s"] == pytest.approx((4.975 - 5.0) / 4.95)    # last book by +300s (t=340) is 4.90/5.05: favourable
    assert s["markout_900s"] == pytest.approx((5.0 - 5.0) / 4.95)      # last book by +900s (t=940) is 4.95/5.05
    assert s["mid_change_from_arrival_900s"] == pytest.approx((5.0 - 4.95) / 4.95)
    partial = b.simulate_passive_offer(book, T0, 100, horizon_ns=35 * S)
    assert not partial["fully_filled"] and partial["filled_shares"] == 50 and partial["fill_fraction"] == 0.5
    none = b.simulate_passive_offer(book, T0, 1000, horizon_ns=900 * S)
    assert none["filled_shares"] == 150 and none["unfilled_drift"] == pytest.approx((5.0 - 4.95) / 4.95)   # last book by the deadline (t=400)


def test_cancellations_behind_us_unless_the_display_shrinks_or_pro_rata():
    recs = [(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 300),   # 300 displayed ahead of us
            (5, "T", "B", 5.00, 200, 4.90, 5.00, 100, 300),   # a 200 buy; the trade record shows the pre-fill book
            (6, "C", "A", 5.00, 200, 4.90, 5.00, 100, 100),   # the execution leaves the display: 100 ahead, not a cancel
            (7, "A", "A", 5.00, 400, 4.90, 5.00, 100, 500),   # 400 new shares join behind us
            (8, "C", "A", 5.00, 250, 4.90, 5.00, 100, 250),   # 250 cancelled: behind us (conservative) or pro rata
            (9, "T", "B", 5.00, 120, 4.90, 5.00, 100, 250)]   # a 120 buy
    book = _book(recs)
    cons = b.simulate_passive_offer(book, T0, 100, horizon_ns=900 * S, cancel_model="conservative")
    pro = b.simulate_passive_offer(book, T0, 100, horizon_ns=900 * S, cancel_model="pro_rata")
    assert cons["filled_shares"] == 20      # 100 still ahead
    assert pro["filled_shares"] == 70       # 100 - 250 x 100/500 = 50 ahead
    shrink = _book([(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 300),
                    (5, "C", "A", 5.00, 250, 4.90, 5.00, 100, 50),    # the display falls below the queue ahead
                    (10, "T", "B", 5.00, 60, 4.90, 5.00, 100, 0)])
    assert b.simulate_passive_offer(shrink, T0, 100, horizon_ns=900 * S)["filled_shares"] == 10   # at most 50 ahead
    alone = _book([(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 300),
                   (5, "C", "A", 5.00, 300, 4.90, 5.10, 100, 300),    # our level emptied by cancels: we are the best offer
                   (10, "T", "B", 5.10, 60, 4.90, 5.10, 100, 240)])   # a buy at or above our price fills us first
    assert b.simulate_passive_offer(alone, T0, 100, horizon_ns=900 * S)["filled_shares"] == 60


def test_ssr_reprices_the_offer_above_a_rising_bid():
    recs = [(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100),
            (5, "A", "B", 5.00, 500, 5.00, 5.10, 500, 200),    # bid rises to our price: slide to 5.10 behind 200
            (10, "T", "A", 5.00, 100, 5.00, 5.10, 400, 200),   # a seller hits the 5.00 bid: not our fill
            (20, "T", "B", 5.10, 250, 5.00, 5.10, 400, 0)]     # 200 ahead at 5.10, then 50 of ours
    book = _book(recs)
    s = b.simulate_passive_offer(book, T0, 50, horizon_ns=900 * S, ssr=True)
    assert s["repriced"] == 1 and s["final_offer"] == pytest.approx(5.10) and s["fully_filled"] and s["fill_vwap"] == pytest.approx(5.10)
    assert s["final_offer"] > 5.00  # never at or below the bid that reached it
    locked = _book([(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100), (5, "A", "B", 5.00, 500, 5.00, 5.00, 500, 200)])
    # A locked book is not a valid book record, so no re-pricing happens on it and nothing fills.
    s2 = b.simulate_passive_offer(locked, T0, 50, horizon_ns=900 * S)
    assert s2["repriced"] == 0 and s2["filled_shares"] == 0
    recs3 = [(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100), (5, "T", "B", 5.00, 100, 4.90, 5.00, 100, 0), (6, "A", "B", 5.00, 10, 5.00, 5.02, 10, 10)]
    s3 = b.simulate_passive_offer(_book(recs3), T0, 50, horizon_ns=900 * S)
    assert s3["filled_shares"] == 0 and s3["repriced"] == 1 and s3["final_offer"] == pytest.approx(5.02)


def test_arrival_requires_a_valid_book_and_an_order():
    bad = _book([(0, "A", "B", 5.00, 100, 5.00, 5.00, 100, 100), (70, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100)])
    assert b.simulate_passive_offer(bad, T0, 100, horizon_ns=900 * S)["status"] == "no_valid_book_at_arrival"
    ok = _book([(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100)])
    assert b.simulate_passive_offer(ok, T0, 0, horizon_ns=900 * S)["status"] == "order_below_one_share"
    flagged = _book([(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100)], flags=b.F_LAST | b.F_BAD_BOOK)
    assert b.simulate_passive_offer(flagged, T0, 10, horizon_ns=900 * S)["status"] == "no_valid_book_at_arrival"
    intermediate = _book([(0, "A", "B", 4.90, 100, 4.90, 5.00, 100, 100)], flags=0)   # not F_LAST: a transient state
    assert b.simulate_passive_offer(intermediate, T0, 10, horizon_ns=900 * S)["status"] == "no_valid_book_at_arrival"


# --- participation ------------------------------------------------------------------------------

def _prints(records):
    cols = list(zip(*records))
    return {"ts": np.array([T0 + int(c * S) for c in cols[0]], dtype="int64"), "price": np.array(cols[1], dtype=float),
            "size": np.array(cols[2], dtype="int64"), "side": np.array(cols[3])}


def test_participation_takes_a_constant_share_of_prints_until_done():
    prints = _prints([(1, 5.00, 1000, "B"), (2, 4.90, 1000, "A"), (3, 4.80, 2000, "B"), (4000, 4.70, 1000, "A")])
    book = _book([(0, "A", "B", 4.95, 100, 4.95, 5.05, 100, 100), (2.5, "A", "B", 4.75, 100, 4.75, 4.85, 100, 100)])
    cap = b.participation_leg(prints, book, T0, T0 + 3600 * S, 0.01, order_shares=None, arrival_mid=5.0)
    assert cap["status"] == "priced" and cap["window_volume"] == 4000 and cap["taken_shares"] == pytest.approx(40)
    assert cap["vwap"] == pytest.approx((5.0 * 1000 + 4.9 * 1000 + 4.8 * 2000) / 4000) and cap["completed"]
    # half-spread: 0.05 for the first two prints (book at t=0), 0.05 for the third (book at 2.5s), over the arrival mid
    assert cap["half_spread_vw"] == pytest.approx(0.05 / 5.0) and cap["fills_with_book"] == 1.0
    fixed = b.participation_leg(prints, book, T0, T0 + 3600 * S, 0.01, order_shares=15, arrival_mid=5.0)
    assert fixed["taken_shares"] == pytest.approx(15) and fixed["completed"] and fixed["time_to_complete_seconds"] == pytest.approx(2)
    assert fixed["vwap"] == pytest.approx((5.0 * 10 + 4.9 * 5) / 15)
    short = b.participation_leg(prints, book, T0, T0 + 3600 * S, 0.01, order_shares=100, arrival_mid=5.0)
    assert not short["completed"] and short["residual_shares"] == pytest.approx(60) and short["taken_shares"] == pytest.approx(40)
    assert b.participation_leg(prints, book, T0 + 5000 * S, T0 + 6000 * S, 0.01, order_shares=None, arrival_mid=5.0)["status"] == "no_prints_in_window"
    assert b.participation_leg(None, book, T0, T0 + 60 * S, 0.01, order_shares=None, arrival_mid=5.0)["status"] == "no_prints"
    assert b.participation_leg(prints, None, T0, T0 + 3600 * S, 0.02, order_shares=None, arrival_mid=5.0)["half_spread_vw"] is None


def test_print_arrays_drop_crosses_and_book_arrays_select_the_symbol():
    import pandas as pd

    idx = pd.Index([T0 + S, T0 + 2 * S, T0 + 3 * S], name="ts_recv")
    frame = pd.DataFrame({"symbol": ["AAA", "AAA", "BBB"], "side": ["N", "B", "B"], "price": [5.0, 5.1, 9.0], "size": [1000, 100, 100]}, index=idx)
    p = b._print_arrays(frame, "AAA")
    assert list(p["size"]) == [100] and b._print_arrays(frame, "ZZZ") is None
    cols = {"symbol": ["AAA", "BBB"], "action": ["A", "A"], "side": ["B", "B"], "price": [4.9, 9.0], "size": [1, 1], "flags": [128, 128],
            "bid_px_00": [4.9, 8.9], "ask_px_00": [5.0, 9.1], "bid_sz_00": [1, 1], "ask_sz_00": [2, 2]}
    bk = b._book_arrays(pd.DataFrame(cols, index=pd.Index([T0, T0 + S], name="ts_recv")), "BBB")
    assert bk["ask"].tolist() == [9.1] and b.valid_book_mask(bk).tolist() == [True]


# --- H4 arithmetic ------------------------------------------------------------------------------

def test_h4_rows_and_feasibility_shares():
    rows = [_event(key="event/a", open=5.0, adv_shares=50_000.0),                 # 250 shares; replay cap 50 -> both below 5% of 20,000
            _event(key="event/b", open=5.0, adv_shares=50_000.0, issuer="cik/2", ssr_state="unrestricted"),
            _event(key="event/c", open=50.0, adv_shares=1_000.0, issuer="cik/3"),   # 25 shares; replay cap 1 share = $50 < $100 minimum
            _event(key="event/d", open=5.0, adv_shares=None, issuer="cik/4"),
            _event(key="event/e", open=5.0, adv_shares=50_000.0, issuer="cik/5", split="holdout", year="2025")]
    crosses = {"event/a": {"open_cross_price": 5.0, "open_cross_shares": 20_000, "close_cross_price": 4.5, "close_cross_shares": 100},
               "event/b": {"open_cross_price": 5.0, "open_cross_shares": 1_000},
               "event/c": {"open_cross_price": 50.0, "open_cross_shares": 1_000},
               "event/e": {"open_cross_price": 5.0, "open_cross_shares": 20_000}}
    h4r = b.h4_rows(rows, crosses)
    by = {r["key"]: r for r in h4r}
    assert by["event/a"]["order_account_shares"] == 250 and by["event/a"]["account_feasible"] and by["event/a"]["account_order_to_cross"] == pytest.approx(0.0125)
    assert by["event/a"]["order_replay_shares"] == 50 and by["event/a"]["replay_feasible"] and not by["event/a"]["account_close_feasible"]
    assert by["event/b"]["account_feasible"] is False and by["event/b"]["account_order_to_cross"] == pytest.approx(0.25)
    assert by["event/c"]["order_replay_shares"] == 1 and by["event/c"]["replay_below_minimum_notional"] and by["event/c"]["replay_feasible"]
    assert by["event/d"]["cross_available"] is False and by["event/d"]["account_feasible"] is None and by["event/d"]["order_replay_shares"] is None
    res = b.h4_results(h4r)
    v = res["by_split"]["validate"]["all"]
    assert v["events"] == 4 and v["events_with_cross"] == 3 and v["account"]["feasible"]["share"] == pytest.approx(2 / 3)
    assert v["account"]["feasible"]["issuer_interval"]["low"] is None   # too few clusters
    assert res["by_split"]["validate"]["restricted"]["account"]["feasible"]["share"] == pytest.approx(1.0)   # a and c; d has no cross
    assert res["by_split"]["validate"]["unrestricted"]["account"]["feasible"]["share"] == pytest.approx(0.0)  # b alone
    assert v["replay"]["below_minimum_notional"] == 1 and v["open_cross_usd"]["median"] == pytest.approx(50_000)
    assert "holdout" in res["by_split"] and "2025" in res["by_year"]
    sealed = b.seal(res)
    assert "holdout" not in sealed["by_split"] and "2025" not in sealed["by_year"]


def test_h2_results_handle_missing_windows_and_count_fills():
    sim = {"status": "simulated", "fully_filled": True, "fill_fraction": 1.0, "repriced": 0, "shares": 100, "arrival_half_spread": 0.01,
           "time_to_fill_seconds": 30.0, "improvement_vs_arrival_mid": 0.01, "markout_60s": 0.0, "markout_300s": 0.002, "markout_900s": 0.0,
           "fill_vwap": 5.0}
    key = f"{b.PRIMARY_ORDER}/{b.PRIMARY_CANCEL_MODEL}"
    rows = [{**_event(key="event/a"), "price_band": "5_and_over", "status": "simulated", "sims": {key: sim}},
            {**_event(key="event/b", issuer="cik/2"), "price_band": "5_and_over", "status": "simulated",
             "sims": {key: {**sim, "fully_filled": False, "fill_fraction": 0.2, "unfilled_drift": 0.03, "time_to_fill_seconds": None}}},
            {**_event(key="event/c", issuer="cik/3"), "price_band": "5_and_over", "status": "no_window"}]
    res = b.h2_results(rows)
    blk = res["by_ssr_state"]["restricted"]["by_split"]["validate"][key]
    assert blk["events"] == 3 and blk["simulated"] == 2 and blk["not_simulated"] == {"no_window": 1}
    assert blk["fill_rate"]["share"] == 0.5 and blk["partially_filled"] == 1 and blk["adverse_selection_5m"]["mean"] == pytest.approx(0.002)
    assert blk["unfilled_drift_to_deadline"]["mean"] == pytest.approx(0.03)
    assert blk["realized_short_return_fill_to_official_close"]["mean"] == pytest.approx((5.0 - 4.5) / 5.0)
    assert res["by_ssr_state"]["unrestricted"]["by_split"]["validate"] == {key: res["by_ssr_state"]["unrestricted"]["by_split"]["validate"][key]}


def test_h3_results_cost_and_kill_reading():
    def leg(cost, net):
        return {"status": "priced", "entry": {"completed": True, "time_to_complete_seconds": 100.0}, "exit": {"vwap": 4.6, "taken_shares": 10},
                "position_shares": 10, "position_usd": 50.0, "residual_at_close_share": 0.0, "entry_shortfall": 0.002, "exit_shortfall": 0.003,
                "entry_half_spread": 0.005, "exit_half_spread": 0.005, "realized_gross_short_return": 0.09,
                "round_trip_cost_c1.0": cost, "round_trip_cost_c0.5": cost / 2, "realized_short_return_c1.0": net, "realized_short_return_c0.5": net}
    rows = [{**_event(key=f"event/{i}", issuer=f"cik/{i}", ret=0.05), "price_band": "5_and_over", "status": "priced",
             "legs": {"capacity/0.01": leg(0.012, 0.03), "capacity/0.02": leg(0.012, 0.03)}} for i in range(6)]
    rows.append({**_event(key="event/z", issuer="cik/z"), "price_band": "5_and_over", "status": "no_window"})
    res = b.h3_results(rows)
    blk = res["by_split"]["validate"]["capacity/0.01"]
    assert blk["priced"] == 6 and blk["not_priced"] == {"no_window": 1} and blk["round_trip_cost_c1.0"]["mean"] == pytest.approx(0.012)
    assert blk["benchmark_minus_cost"]["mean"] == pytest.approx(0.05 - 0.012) and blk["round_trip_cost_c1.0"]["issuer_interval"]["clusters"] == 6
    h4 = {"by_split": {s: {"all": {"account": {"feasible": {"events": 10, "share": 0.9, "issuer_interval": {}}}, "replay": {"feasible": {"events": 10, "share": 1.0}}},
                           "restricted": {"account": {"feasible": {"events": 5, "share": 0.8}}}} for s in ("train", "validate")}}
    h2 = {"by_ssr_state": {"restricted": {"by_split": {s: {f"{b.PRIMARY_ORDER}/{b.PRIMARY_CANCEL_MODEL}": {"simulated": 4, "fill_rate": {"share": 0.6},
                                                                                                           "adverse_selection_5m": {"mean": 0.001},
                                                                                                           "time_to_fill_seconds": {}}} for s in ("train", "validate")}}}}
    a = b.assessments(h4, h2, res)
    assert a["H4"]["assessment"].startswith("Success") and a["H2"]["assessment"].startswith("Success") and a["H3"]["assessment"].startswith("Success")
    h2["by_ssr_state"]["restricted"]["by_split"]["validate"][f"{b.PRIMARY_ORDER}/{b.PRIMARY_CANCEL_MODEL}"]["fill_rate"]["share"] = 0.2
    h4["by_split"]["validate"]["all"]["account"]["feasible"]["share"] = 0.3
    rows_kill = [{**r, "legs": {"capacity/0.01": leg(0.06, -0.01)}} for r in rows if r.get("legs")]
    a = b.assessments(h4, h2, b.h3_results(rows_kill))
    assert a["H4"]["assessment"].startswith("Kill") and a["H2"]["assessment"].startswith("Kill") and a["H3"]["assessment"].startswith("Kill")
    empty = b.assessments(h4, h2, b.h3_results([]))
    assert empty["H3"]["assessment"].startswith("Not measured") and empty["H3"]["validate"] is None


# --- sealing, registry, publication ------------------------------------------------------------------

def test_holdout_view_is_the_complement_of_seal():
    doc = {"h4": {"by_split": {"train": {"a": 1}, "holdout": {"a": 2}}, "by_year": {"2024": 1, "2025": 2}},
           "data": {"events": 3}, "assessments": {"H4": {"assessment": "x"}}}
    view = b._holdout_view(doc)
    assert view == {"h4": {"by_split": {"holdout": {"a": 2}}, "by_year": {"2025": 2}}}
    sealed = b.seal(doc)
    assert sealed["h4"] == {"by_split": {"train": {"a": 1}}, "by_year": {"2024": 1}} and sealed["data"] == {"events": 3}


def test_mark_measured_updates_status_and_result_ref_only(fixture_ledger):
    declared = "2026-10-18T12:00:00+00:00"
    rows = []
    for hid, status in (("H2", "registered"), ("H3", "validated"), ("H4", "registered")):
        row = {k: "fixture" for k in hyp.REQUIRED}
        row.update(id=hid, status=status, declared_at=declared, result_ref=None)
        rows.append(row)
    write_jsonl(fixture_ledger / hyp.REGISTRY_NAME, rows)
    assert hyp.mark_measured(fixture_ledger, ["H2", "H3", "H4"], "study.json") == 2
    after = {r["id"]: r for r in load_jsonl(fixture_ledger / hyp.REGISTRY_NAME)}
    assert after["H2"]["status"] == "measured" and after["H2"]["result_ref"] == "study.json" and after["H2"]["declared_at"] == declared
    assert after["H3"]["status"] == "validated" and after["H3"]["result_ref"] is None
    assert hyp.mark_measured(fixture_ledger, ["H2", "H4"], "study.json") == 0
    assert hyp.registry_errors(load_jsonl(fixture_ledger / hyp.REGISTRY_NAME)) == []


def test_registry_still_has_seventeen_rows_and_workstream_a_cites_registered_ids():
    rows = load_jsonl(LEDGER / hyp.REGISTRY_NAME)
    assert [r["id"] for r in rows] == [f"H{i}" for i in range(1, 18)]
    assert hyp.registry_errors(rows) == []
    assert hyp.declared_before(rows, list(er.HYPOTHESES), datetime.now(timezone.utc))


def test_published_workstream_a_is_sealed_registered_and_hashed():
    path = LEDGER / "execution_realism.json"
    if not path.exists():
        pytest.skip("execution_realism.json not published")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["hypothesis_ids"] == list(er.HYPOTHESES) and doc["aggregate_only"] is True and doc["schema_version"] == er.VERSION
    for block in ("h4_opening_cross", "h2_passive_offer_under_ssr", "h3_participation_cost", "commissions"):
        text = json.dumps(doc[block])
        assert '"holdout"' not in text and '"2025"' not in text and '"2026"' not in text
    assert hyp.detail_keys(doc) == set()
    assert {"H2", "H3", "H4"} <= set(doc["assessments"])
    assert doc["data"]["data_cost_incurred_usd"] is not None
    manifest = json.loads((LEDGER / "execution_realism_manifest.json").read_text(encoding="utf-8"))
    assert manifest["output"]["sha256"] and manifest["holdout"]["sealed"] is True and manifest["raw_market_data_public"] is False
    assert manifest["data_cost_incurred_usd"] == doc["data"]["data_cost_incurred_usd"]
    registry = {r["id"]: r for r in load_jsonl(LEDGER / hyp.REGISTRY_NAME)}
    measured = set(manifest["hypotheses_measured"])
    assert measured <= set(er.HYPOTHESES) and "H4" in measured
    for h in er.HYPOTHESES:
        if h in measured:
            assert registry[h]["status"] in ("measured", "validated", "killed") and registry[h]["result_ref"] == path.name
            assert not doc["assessments"][h]["assessment"].startswith("Not measured")
        else:
            assert doc["assessments"][h]["assessment"].startswith("Not measured")
    assert check_reverse_splits.structural_errors() == []
