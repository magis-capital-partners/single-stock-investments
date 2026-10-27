from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.safeties import check_safeties, kill_path  # noqa: E402
from _system.trading.sleeves.config_loader import load_config  # noqa: E402


def _quote(last=100.0, age_s=1):
    now = datetime.now(timezone.utc)
    return {
        "last": last,
        "as_of": (now - timedelta(seconds=age_s)).isoformat().replace("+00:00", "Z"),
        "account": "TEST_ACCOUNT",
        "qualified_name": "CSU",
        "currency": "USD",
        "exchange": "SMART",
    }


def test_dry_run_ok_for_drew_residual():
    result = check_safeties(
        owner="drew",
        ticker="CSU",
        side="BUY",
        qty=10,
        limit_price=100,
        quote=_quote(),
        proposal={"proposal_id": "abc", "snapshot_last": 100},
        typed_ticker="CSU",
    )
    assert result.ok, result.failures


def test_drew_cannot_trade_letf_or_blacklist_family():
    tqqq = check_safeties(owner="drew", ticker="TQQQ", side="BUY", qty=10, limit_price=40, quote=_quote(40), proposal={"snapshot_last": 40})
    assert not tqqq.ok
    apld = check_safeties(owner="drew", ticker="APLD", side="BUY", qty=10, limit_price=10, quote=_quote(10), proposal={"snapshot_last": 10})
    assert not apld.ok
    assert any("systematic" in f.lower() for f in apld.failures)


def test_michael_can_trade_residual_but_not_ls_universe():
    csu = check_safeties(owner="michael", ticker="CSU", side="BUY", qty=10, limit_price=20, quote=_quote(20), proposal={"snapshot_last": 20})
    assert csu.ok, csu.failures
    aplz = check_safeties(owner="michael", ticker="APLZ", side="BUY", qty=10, limit_price=20, quote=_quote(20), proposal={"snapshot_last": 20})
    assert not aplz.ok
    tqqq = check_safeties(owner="michael", ticker="TQQQ", side="BUY", qty=10, limit_price=40, quote=_quote(40), proposal={"snapshot_last": 40})
    assert not tqqq.ok
    nvda = check_safeties(owner="michael", ticker="NVDA", side="BUY", qty=10, limit_price=100, quote=_quote(100), proposal={"snapshot_last": 100})
    assert not nvda.ok


def test_proposal_id_one_shot_and_stale_quote():
    used = check_safeties(
        owner="drew", ticker="CSU", side="BUY", qty=10, limit_price=100,
        quote=_quote(), proposal={"proposal_id": "x", "snapshot_last": 100},
        used_proposal_ids={"x"},
    )
    assert not used.ok
    stale = check_safeties(
        owner="drew", ticker="CSU", side="BUY", qty=10, limit_price=100,
        quote=_quote(age_s=90), proposal={"snapshot_last": 100},
    )
    assert not stale.ok


def test_kill_file(tmp_path, monkeypatch):
    cfg = load_config()
    path = kill_path(cfg)
    created = False
    if not path.exists():
        path.write_text("stop\n", encoding="utf-8")
        created = True
    try:
        result = check_safeties(owner="drew", ticker="CSU", side="BUY", qty=1, limit_price=100, quote=_quote(), proposal={"snapshot_last": 100})
        assert not result.ok
        assert any("KILL" in f for f in result.failures)
    finally:
        if created and path.exists():
            path.unlink()


def test_option_notional_uses_multiplier():
    import copy
    cfg = copy.deepcopy(load_config())
    cfg["operators"]["drew"]["max_notional_per_order"] = 200
    quote = _quote(last=1.5)
    quote.update({"secType": "OPT", "underlying": "CSU", "multiplier": 100})
    too_big = check_safeties(
        owner="drew", ticker="CSU", side="BUY", qty=2, limit_price=1.5,
        quote=quote, proposal={"snapshot_last": 1.5}, cfg=cfg,
    )
    assert not too_big.ok
    assert any("notional" in f for f in too_big.failures)
    ok = check_safeties(
        owner="drew", ticker="CSU", side="BUY", qty=1, limit_price=1.5,
        quote=quote, proposal={"snapshot_last": 1.5}, cfg=cfg,
    )
    assert ok.ok, ok.failures


def test_spx_option_blocked_for_sleeves():
    quote = _quote(last=5)
    quote.update({"secType": "OPT", "underlying": "SPX", "multiplier": 100})
    result = check_safeties(
        owner="michael", ticker="SPX", side="BUY", qty=1, limit_price=5,
        quote=quote, proposal={"snapshot_last": 5},
    )
    assert not result.ok
    assert any("SPX" in f for f in result.failures)


def test_etf_0dte_options_and_shares_blocked_for_both_sleeves():
    # A sleeve SELL of SPY would sell etf-0dte's overnight delivery out from
    # under its 09:30 unwind; a BUY would net against it. Neither owner may.
    for owner in ("drew", "michael"):
        for root in ("SPY", "QQQ"):
            for side in ("BUY", "SELL"):
                shares = check_safeties(
                    owner=owner, ticker=root, side=side, qty=10, limit_price=500,
                    quote=_quote(last=500), proposal={"snapshot_last": 500},
                )
                assert not shares.ok
                assert any("etf-0dte" in f for f in shares.failures), (owner, root, side, shares.failures)

                quote = _quote(last=2)
                quote.update({"secType": "OPT", "underlying": root, "multiplier": 100})
                option = check_safeties(
                    owner=owner, ticker=root, side=side, qty=1, limit_price=2,
                    quote=quote, proposal={"snapshot_last": 2},
                )
                assert not option.ok
                assert any("etf-0dte" in f for f in option.failures), (owner, root, side, option.failures)


def test_etf_0dte_rows_never_count_toward_a_sleeves_gross():
    # The delivery sits in the shared account; it is nobody's exposure here.
    # Counted, 1.4M of it would breach Drew's 200k gross on a 1k buy.
    delivered = [
        {"symbol": "SPY", "secType": "STK", "qty": 2000, "marketValue": 1_160_000,
         "classification": {"bucket": "etf_0dte_delivery", "reason": "expected_delivery", "owner": None}},
        {"symbol": "QQQ", "secType": "STK", "qty": 500, "marketValue": 250_000},   # unclassified: classified here
    ]
    result = check_safeties(
        owner="drew", ticker="CSU", side="BUY", qty=10, limit_price=100,
        quote=_quote(), proposal={"snapshot_last": 100}, current_positions=delivered,
    )
    assert result.ok, result.failures
