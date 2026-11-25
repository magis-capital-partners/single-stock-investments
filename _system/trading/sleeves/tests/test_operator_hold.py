"""Assigned TPL stock stays on Drew when the LS universe still lists it."""

from _system.trading.sleeves.classify_positions import classify_position


def test_assigned_tpl_stock_stays_on_drew_inside_the_universe():
    stock = classify_position(
        {
            "symbol": "TPL",
            "secType": "STK",
            "position": 505,
            "orderRef": "ETF_LS|MANUAL|BUY|TPL|att1|att1|ADAPTIVE",
            "_ownership": {"owner": "excluded", "reason": "ls_universe"},
        },
        blacklist_family=[],
        etf_ls_symbols=["TPL", "TPLX"],
        drew_symbols=["TPL"],
    )
    assert (stock.bucket, stock.owner, stock.reason, stock.ticker) == (
        "drew",
        "drew",
        "operator_hold",
        "TPL",
    )


def test_tpl_put_is_drew_and_tplx_wrapper_stays_systematic():
    put = classify_position(
        {
            "symbol": "TPL",
            "underlyingSymbol": "TPL",
            "secType": "OPT",
            "localSymbol": "TPL   261120P00300000",
            "orderRef": "ETF_LS|MANUAL|SELLPUT|TPL|20261120|300P|2026-10-28|att1",
        },
        blacklist_family=[],
        etf_ls_symbols=["TPL", "TPLX"],
        drew_symbols=["TPL"],
    )
    assert put.bucket == "drew" and put.ticker == "TPL" and put.reason == "operator_hold"

    wrapper = classify_position(
        {"symbol": "TPLX", "secType": "STK", "position": -10},
        blacklist_family=[],
        etf_ls_symbols=["TPL", "TPLX"],
        drew_symbols=["TPL"],
    )
    assert wrapper.bucket == "etf_ls" and wrapper.reason == "etf_ls_universe"


def test_empty_operator_list_does_not_pull_tpl_or_nvda_off_their_books():
    tpl = classify_position(
        {
            "symbol": "TPL",
            "secType": "STK",
            "orderRef": "ETF_LS|MANUAL|BUY|TPL",
            "_ownership": {"owner": "excluded", "reason": "ls_universe"},
        },
        blacklist_family=[],
        etf_ls_symbols=["TPL"],
        drew_symbols=[],
    )
    assert tpl.bucket == "etf_ls"

    nvda = classify_position(
        {"symbol": "NVDA", "secType": "STK", "position": 11},
        blacklist_family=[],
        etf_ls_symbols=["NVDA"],
        drew_symbols=["TPL"],
    )
    assert nvda.bucket == "etf_0dte_delivery_unattributed"
