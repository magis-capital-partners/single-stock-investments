"""etf-0dte: spx-0dte's SPY / QQQ 0DTE executors (clients 50/51, watchdogs 130/131).

Their options, the shares an assignment delivers into this shared account, and
the 09:30 unwind of those shares belong to no SSI book. These tests pin each
branch of that rule and its order against the XSP, SPX, LETF-overlay, LETF
universe and owner rules.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.classify_positions import (  # noqa: E402
    ETF_0DTE,
    ETF_0DTE_BUCKETS,
    ETF_0DTE_DELIVERY,
    ETF_0DTE_DELIVERY_UNATTRIBUTED,
    OTHER_SYSTEM_BUCKETS,
    classify_position,
    classify_positions,
    etf_0dte_root,
    has_etf_0dte_ref,
    split_etf_0dte_shares,
)
from _system.trading.sleeves.config_loader import load_etf_ls_universe  # noqa: E402

# The real universe snapshot lists SPY and QQQ (it predates ls-algo's
# 2026-09-10 blacklist), so every test runs with them in it.
LETF = {"SPY", "QQQ", "TQQQ", "NVDA", "APLD"}


def cls(pos, **kw):
    kw.setdefault("blacklist_family", {"APLD"})
    kw.setdefault("etf_ls_symbols", LETF)
    return classify_position(pos, **kw)


def spy_opt(**overrides):
    base = {"symbol": "SPY", "secType": "OPT", "underlyingSymbol": "SPY",
            "localSymbol": "SPY   261027C00580000", "tradingClass": "SPY", "qty": -5}
    return {**base, **overrides}


def shares(symbol="SPY", qty=100, **overrides):
    return {"symbol": symbol, "secType": "STK", "conId": 756733, "qty": qty,
            "marketValue": qty * 580.0, "costUsd": qty * 575.0, **overrides}


# ------------------------------------------------------------------ the stamp

def test_the_prefixes_are_the_executors_and_their_watchdogs():
    for ref in ("SPY0DTE|ORB|2026-10-27|t1", "QQQ0DTE|CLOSEOUT|x", "SPY0DTE|WATCHDOG|y", "spy0dte|lower"):
        assert has_etf_0dte_ref(ref)
    for ref in ("", "MAGIS|single_stock|drew|1", "ETF_LS|ESTABLISH|NVDA", "B5P|XSP", "SPX0DTE|x", "XSPY0DTE|x"):
        assert not has_etf_0dte_ref(ref)


def test_a_stamped_option_order_is_etf_0dte_whatever_else_would_claim_it():
    for ref in ("SPY0DTE|ORB|t1", "QQQ0DTE|ORB|t1"):
        root = ref[:3]
        got = cls(spy_opt(symbol=root, underlyingSymbol=root, orderRef=ref), drew_symbols={root})
        assert (got.bucket, got.reason, got.ticker, got.owner) == (ETF_0DTE, "order_ref", root, None)


def test_the_morning_unwind_order_is_the_delivery_not_ls_algo():
    got = cls(shares(orderRef="SPY0DTE|UNWIND|2026-10-27"), drew_symbols={"SPY"})
    assert (got.bucket, got.reason) == (ETF_0DTE_DELIVERY, "order_ref")


def test_the_stamp_is_checked_before_the_index_rules():
    # Rule 7: a stamp is positive ownership. An etf-0dte stamp on anything is
    # etf-0dte's; the XSP and SPX symbol rules never see it.
    xsp = cls({"symbol": "XSP   270129P00540000", "secType": "OPT", "orderRef": "SPY0DTE|x"})
    assert xsp.bucket == ETF_0DTE


# ----------------------------------------------------------- ref-less options

@pytest.mark.parametrize("pos", [
    spy_opt(),                                                                  # IB API row
    {"symbol": "SPY   261027P00570000", "localSymbol": "SPY   261027P00570000",
     "secType": "OPT", "tradingClass": "", "underlyingSymbol": ""},            # Flex: OCC, no underlying
    {"symbol": "SPY---261027P00570000", "secType": "OPT"},                     # norm_sym'd OCC (policy path)
    {"symbol": "SPY", "secType": "OPT"},                                        # bare root
    {"symbol": "X", "secType": "OPT", "tradingClass": "SPY"},                  # trading class only
    spy_opt(localSymbol="SPY   271217C00700000"),                              # not 0DTE: still theirs
])
def test_refless_spy_options_are_etf_0dte_by_root(pos):
    got = cls(pos)
    assert (got.bucket, got.reason, got.ticker, got.owner) == (ETF_0DTE, "etf_0dte_root", "SPY", None)


def test_refless_qqq_options_are_etf_0dte_by_root():
    got = cls({"symbol": "QQQ   261027C00500000", "secType": "OPT"})
    assert (got.bucket, got.ticker) == (ETF_0DTE, "QQQ")


def test_the_root_rule_runs_before_the_ls_overlay_rule():
    # Before this rule, SPY / QQQ being in the universe snapshot made every
    # etf-0dte contract a Drew overlay.
    assert cls(spy_opt()).bucket == ETF_0DTE
    assert cls(spy_opt(), etf_ls_symbols=set()).bucket == ETF_0DTE      # and not Michael's residual
    nvda = cls({"symbol": "NVDA  260821C00100000", "secType": "OPT", "underlyingSymbol": "NVDA"})
    assert (nvda.bucket, nvda.reason) == ("drew", "ls_algo_option_overlay")


def test_index_rules_still_win_for_index_contracts():
    xsp = cls({"symbol": "XSP   270129P00540000", "secType": "OPT", "underlyingSymbol": "XSP"})
    assert xsp.bucket == "index_put_hedge"
    spxw = cls({"symbol": "SPX", "secType": "OPT", "tradingClass": "SPXW", "localSymbol": "SPXW  260813C05000000"})
    assert spxw.bucket == "spx_0dte"


def test_lookalike_roots_are_not_captured():
    for root in ("SPYG", "SPYV", "QQQM", "QQQJ", "SPXL"):
        occ = f"{root:<6}261120C00080000"
        got = cls({"symbol": occ, "localSymbol": occ, "secType": "OPT", "underlyingSymbol": root})
        assert got.bucket not in ETF_0DTE_BUCKETS, root
        assert etf_0dte_root({"symbol": root, "secType": "STK"}) == ""


def test_another_systems_stamp_keeps_that_systems_classification():
    # Algorithmic option stamps are excluded; documented manual overlays keep Drew.
    got = cls(spy_opt(orderRef="ETF_LS|HEDGE|SPY"))
    assert (got.bucket, got.reason) == ("etf_ls", "executed_ls_order_reference")
    stock = cls(shares(orderRef="ETF_LS|ESTABLISH|SPY"))
    assert (stock.bucket, stock.reason) == ("etf_ls", "executed_ls_order_reference")


# ---------------------------------------------------------- delivered shares

def test_forecast_delivery_is_etf_0dte_delivery():
    got = cls(shares(qty=-100), etf_0dte_delivery={"SPY": -100})
    assert (got.bucket, got.reason, got.owner) == (ETF_0DTE_DELIVERY, "expected_delivery", None)
    qqq = cls(shares("QQQ", 200), etf_0dte_delivery={"QQQ": 200.0, "SPY": 0})
    assert qqq.bucket == ETF_0DTE_DELIVERY


def test_without_a_forecast_spy_shares_are_unattributed_not_ls_or_drew():
    # Before: the universe snapshot made these etf_ls, and a Drew tag or an
    # absent universe entry would have made them Drew's or Michael's.
    got = cls(shares(qty=100), drew_symbols={"SPY"})
    assert (got.bucket, got.reason, got.owner) == (ETF_0DTE_DELIVERY_UNATTRIBUTED, "no_forecast", None)
    assert cls(shares(qty=100), etf_ls_symbols=set()).bucket == ETF_0DTE_DELIVERY_UNATTRIBUTED


@pytest.mark.parametrize("qty,forecast,reason", [
    (100, {"QQQ": 100}, "no_forecast"),          # a forecast, but not for SPY
    (100, {"SPY": 0}, "beyond_forecast"),         # the forecast said nothing would come
    (100, {"SPY": -100}, "beyond_forecast"),      # wrong sign: a put delivered, a call was forecast
    (150, {"SPY": 100}, "beyond_forecast"),       # more than forecast: the row holds unexplained shares
])
def test_shares_the_forecast_does_not_explain_are_unattributed(qty, forecast, reason):
    got = cls(shares(qty=qty), etf_0dte_delivery=forecast)
    assert (got.bucket, got.reason) == (ETF_0DTE_DELIVERY_UNATTRIBUTED, reason)


def test_a_partly_unwound_delivery_is_still_the_delivery():
    got = cls(shares(qty=40), etf_0dte_delivery={"SPY": 100})
    assert got.bucket == ETF_0DTE_DELIVERY


def test_a_row_with_no_quantity_fails_closed():
    # This is the sleeve desk's name gate: no position, just a ticker.
    got = cls({"symbol": "SPY", "secType": "STK", "orderRef": ""})
    assert (got.bucket, got.reason) == (ETF_0DTE_DELIVERY_UNATTRIBUTED, "quantity_unknown")
    flat = cls(shares(qty=0))
    assert (flat.bucket, flat.reason) == (ETF_0DTE_DELIVERY_UNATTRIBUTED, "flat")


def test_a_known_holding_keeps_its_current_bucket():
    # No book holds SPY or QQQ today. If one ever does, the caller declares it
    # and those shares keep whatever bucket they had before this rule existed.
    held = cls(shares(qty=500), etf_0dte_known_holdings={"SPY": 500})
    assert (held.bucket, held.reason) == ("etf_ls", "etf_ls_universe")
    residual = cls(shares(qty=500), etf_ls_symbols=set(), etf_0dte_known_holdings={"SPY": 500})
    assert (residual.bucket, residual.owner) == ("michael", "michael")
    # A known holding never absorbs shares beyond it: the row fails closed.
    mixed = cls(shares(qty=600), etf_0dte_known_holdings={"SPY": 500}, etf_0dte_delivery={"SPY": 100})
    assert mixed.bucket == ETF_0DTE_DELIVERY
    over = cls(shares(qty=650), etf_0dte_known_holdings={"SPY": 500}, etf_0dte_delivery={"SPY": 100})
    assert over.bucket == ETF_0DTE_DELIVERY_UNATTRIBUTED


def test_other_shares_are_untouched():
    assert cls(shares("TQQQ", 10)).bucket == "etf_ls"
    assert cls(shares("CSU", 10), etf_ls_symbols=set()).bucket == "michael"
    assert cls(shares("SPYG", 10), etf_ls_symbols=set()).bucket == "michael"


# ------------------------------------------------------------- list splitting

def test_a_mixed_row_is_split_once_per_bucket_with_values_pro_rata():
    rows = classify_positions(
        [shares(qty=650)],
        blacklist_family=set(), etf_ls_symbols=LETF,
        etf_0dte_delivery={"SPY": 100}, etf_0dte_known_holdings={"SPY": 500},
    )
    got = [(r["qty"], r["classification"]["bucket"], r["classification"]["reason"]) for r in rows]
    assert got == [
        (500.0, "etf_ls", "etf_ls_universe"),
        (100.0, ETF_0DTE_DELIVERY, "expected_delivery"),
        (50.0, ETF_0DTE_DELIVERY_UNATTRIBUTED, "beyond_forecast"),
    ]
    assert [r["marketValue"] for r in rows] == [500 * 580.0, 100 * 580.0, 50 * 580.0]
    assert [r["costUsd"] for r in rows] == [500 * 575.0, 100 * 575.0, 50 * 575.0]
    assert sum(r["qty"] for r in rows) == 650
    assert {r["conId"] for r in rows} == {756733}
    assert [r["etf_0dte_split"]["part"] for r in rows] == [1, 2, 3]


def test_flex_lots_share_one_forecast_and_one_known_holding():
    # Flex reports one row per tax lot. The forecast must not be counted once per lot.
    rows = classify_positions(
        [shares(qty=60), shares(qty=60)],
        blacklist_family=set(), etf_ls_symbols=LETF, etf_0dte_delivery={"SPY": 100},
    )
    got = [(r["qty"], r["classification"]["bucket"]) for r in rows]
    assert got == [(60, ETF_0DTE_DELIVERY), (40.0, ETF_0DTE_DELIVERY), (20.0, ETF_0DTE_DELIVERY_UNATTRIBUTED)]

    rows = classify_positions(
        [shares(qty=300), shares(qty=300)],
        blacklist_family=set(), etf_ls_symbols=LETF, etf_0dte_known_holdings={"SPY": 500},
    )
    got = [(r["qty"], r["classification"]["bucket"]) for r in rows]
    assert got == [(300, "etf_ls"), (200.0, "etf_ls"), (100.0, ETF_0DTE_DELIVERY_UNATTRIBUTED)]


def test_an_unsplit_row_is_passed_through_unchanged():
    rows = classify_positions(
        [shares(qty=-100), spy_opt(), {"symbol": "CSU", "qty": 3}],
        blacklist_family=set(), etf_ls_symbols=LETF, etf_0dte_delivery={"SPY": -100},
    )
    assert [r["classification"]["bucket"] for r in rows] == [ETF_0DTE_DELIVERY, ETF_0DTE, "michael"]
    assert rows[0]["qty"] == -100 and "etf_0dte_split" not in rows[0]


def test_split_parts_sum_to_the_shares_and_keep_their_sign():
    parts = split_etf_0dte_shares("SPY", -150, {"SPY": -100})
    assert [(str(q), b, r) for q, b, r in parts] == [
        ("-100", ETF_0DTE_DELIVERY, "expected_delivery"),
        ("-50", ETF_0DTE_DELIVERY_UNATTRIBUTED, "beyond_forecast"),
    ]
    assert split_etf_0dte_shares("SPY", 0, {"SPY": 100}) == []
    assert split_etf_0dte_shares("spy", "100", None) == [(100, ETF_0DTE_DELIVERY_UNATTRIBUTED, "no_forecast")]


# ---------------------------------------------------------- shared constants

def test_every_etf_0dte_bucket_is_another_systems():
    assert ETF_0DTE_BUCKETS <= OTHER_SYSTEM_BUCKETS
    assert {"etf_ls", "spx_0dte", "index_put_hedge"} <= OTHER_SYSTEM_BUCKETS
    assert not {"michael", "drew", "ignored"} & OTHER_SYSTEM_BUCKETS


def test_the_committed_universe_snapshot_still_lists_spy_and_qqq():
    # Why the rules above must run before the universe rule. ls-algo has
    # blacklisted both since 2026-09-10, but this mirror is a 2026-08-13 snapshot.
    letf = load_etf_ls_universe()
    assert {"SPY", "QQQ"} <= letf
    assert cls(spy_opt(), etf_ls_symbols=letf).bucket == ETF_0DTE
    assert cls(shares(), etf_ls_symbols=letf).bucket == ETF_0DTE_DELIVERY_UNATTRIBUTED
