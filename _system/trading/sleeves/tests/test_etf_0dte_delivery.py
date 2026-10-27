"""Reading spx-0dte's SPY / QQQ delivery forecast, and what sync does with it."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.config_loader import (  # noqa: E402
    load_config,
    load_etf_0dte_expected_delivery,
    load_etf_0dte_known_holdings,
)
from _system.trading.sleeves.etf_0dte_delivery import forecast_path, read_expected_delivery  # noqa: E402
from _system.trading.sleeves.store import SleeveStore  # noqa: E402
from _system.trading.sleeves.sync_ib import sync_holdings  # noqa: E402

ACCOUNT = "U805366"
TODAY = date(2026, 10, 28)


def write_forecast(live_dir: Path, product: str, session: str, shares, *, account=ACCOUNT, raw=None):
    path = forecast_path(live_dir, product, session, account)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The shape spx-0dte's exercise_control.write_expected_delivery writes.
    payload = {"written_at": f"{session}T20:14:30Z", "shares": shares, "detail": []}
    path.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
    return path


def test_path_matches_spx_0dte_live_paths(tmp_path):
    # live_paths.expected_delivery_path: day_dir(session, product) / expected_delivery_<acct>.json
    assert forecast_path(tmp_path, "spy", "2026-10-27", " U805366 ") == (
        tmp_path / "spy" / "2026-10-27" / "expected_delivery_U805366.json"
    )


def test_reads_each_products_newest_forecast(tmp_path):
    write_forecast(tmp_path, "spy", "2026-10-26", {"SPY": 100})
    write_forecast(tmp_path, "spy", "2026-10-27", {"SPY": -200})
    write_forecast(tmp_path, "qqq", "2026-10-27", {})      # written, nothing expected
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY) == {"SPY": -200.0, "QQQ": 0.0}


def test_no_forecast_is_none_never_zero(tmp_path):
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY) is None
    assert read_expected_delivery(None, ACCOUNT, today=TODAY) is None
    write_forecast(tmp_path, "spy", "2026-10-27", {"SPY": 100})
    assert read_expected_delivery(tmp_path, "", today=TODAY) is None
    assert read_expected_delivery(tmp_path, "DU999", today=TODAY) is None      # another account's file


def test_a_session_without_a_forecast_does_not_hide_the_previous_one(tmp_path):
    # Today's executor creates its day directory long before its close writes
    # the forecast. Yesterday's delivery is still the one in the account.
    write_forecast(tmp_path, "spy", "2026-10-27", {"SPY": 100})
    (tmp_path / "spy" / "2026-10-28").mkdir()
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY) == {"SPY": 100.0}


def test_stale_future_and_dry_run_forecasts_are_ignored(tmp_path):
    write_forecast(tmp_path, "spy", "2026-10-20", {"SPY": 100})               # 8 days old
    write_forecast(tmp_path, "qqq", "2026-10-29", {"QQQ": 100})               # after today
    write_forecast(tmp_path / "dry_run", "spy", "2026-10-27", {"SPY": 100})   # a simulated book
    write_forecast(tmp_path, "spy", "not-a-date", {"SPY": 100})
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY) is None
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY, max_age_days=8) == {"SPY": 100.0}


def test_an_unreadable_newest_forecast_is_not_replaced_by_an_older_one(tmp_path):
    write_forecast(tmp_path, "spy", "2026-10-26", {"SPY": 100})
    write_forecast(tmp_path, "spy", "2026-10-27", None, raw="{not json")
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY) is None
    write_forecast(tmp_path, "spy", "2026-10-27", None, raw=json.dumps({"shares": ["SPY", 100]}))
    assert read_expected_delivery(tmp_path, ACCOUNT, today=TODAY) is None


def test_config_loader_reads_the_configured_live_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("ETF_0DTE_LIVE_DIR", raising=False)
    write_forecast(tmp_path, "spy", "2026-10-27", {"SPY": -100})
    cfg = {"ibkr": {"account_id": ACCOUNT}, "etf_0dte": {"live_dir": str(tmp_path)}}
    assert load_etf_0dte_expected_delivery(cfg, today=TODAY) == {"SPY": -100.0}
    assert load_etf_0dte_expected_delivery({**cfg, "etf_0dte": {}}, today=TODAY) is None
    assert load_etf_0dte_expected_delivery({**cfg, "ibkr": {}}, today=TODAY) is None
    stale = {**cfg, "etf_0dte": {"live_dir": str(tmp_path), "forecast_max_age_days": 0}}
    assert load_etf_0dte_expected_delivery(stale, today=TODAY) is None

    other = tmp_path / "elsewhere"
    write_forecast(other, "qqq", "2026-10-27", {"QQQ": 300})
    monkeypatch.setenv("ETF_0DTE_LIVE_DIR", str(other))
    assert load_etf_0dte_expected_delivery(cfg, today=TODAY) == {"QQQ": 300.0}


def test_the_committed_config_has_no_forecast_and_no_known_holdings(monkeypatch):
    monkeypatch.delenv("ETF_0DTE_LIVE_DIR", raising=False)
    cfg = load_config()
    assert cfg["etf_0dte"]["live_dir"] is None
    assert load_etf_0dte_known_holdings(cfg) == {}
    assert load_etf_0dte_known_holdings({"etf_0dte": {"known_share_holdings": {"spy": 300}}}) == {"SPY": 300.0}


# --------------------------------------------------------------------- sync

def _rows():
    return [
        {"account": ACCOUNT, "symbol": "CSU", "localSymbol": "CSU", "secType": "STK", "conId": 1,
         "qty": 10.0, "mark": 3000.0, "marketValue": 30000.0, "avgCost": 2900.0, "orderRef": ""},
        {"account": ACCOUNT, "symbol": "SPY", "localSymbol": "SPY", "secType": "STK", "conId": 756733,
         "qty": -100.0, "mark": 580.0, "marketValue": -58000.0, "avgCost": 580.0, "orderRef": ""},
        {"account": ACCOUNT, "symbol": "QQQ", "localSymbol": "QQQ", "secType": "STK", "conId": 320227571,
         "qty": 200.0, "mark": 500.0, "marketValue": 100000.0, "avgCost": 500.0, "orderRef": ""},
        {"account": ACCOUNT, "symbol": "SPY   261028P00570000", "localSymbol": "SPY   261028P00570000",
         "secType": "OPT", "tradingClass": "SPY", "underlyingSymbol": "SPY", "conId": 9001,
         "qty": -2.0, "mark": 1.5, "marketValue": -300.0, "avgCost": 150.0, "orderRef": ""},
    ]


def test_sync_keeps_etf_0dte_out_of_both_books_even_against_sleeve_tags(tmp_path, monkeypatch):
    live = tmp_path / "live"
    write_forecast(live, "spy", "2026-10-27", {"SPY": -100})
    monkeypatch.setenv("ETF_0DTE_LIVE_DIR", str(live))
    monkeypatch.setattr("_system.trading.sleeves.etf_0dte_delivery.new_york_today", lambda: TODAY)
    cfg = load_config()
    cfg["ibkr"]["account_id"] = ACCOUNT
    store = SleeveStore(tmp_path / "store")
    # A Drew tag on every etf-0dte line, by conId and by ticker. None may win.
    for con_id, ticker, sec in ((756733, "SPY", "STK"), (320227571, "QQQ", "STK"), (9001, "SPY", "OPT")):
        store.save_sleeve_tag({"owner": "drew", "ticker": ticker, "con_id": con_id, "sec_type": sec})

    result = sync_holdings(store, cfg, positions=_rows(), ingest=False, write_dashboard=False)

    by_con = {row["conId"]: row["classification"] for row in store.positions()}
    assert by_con[756733]["bucket"] == "etf_0dte_delivery"                  # forecast -100, held -100
    assert by_con[320227571]["bucket"] == "etf_0dte_delivery_unattributed"  # QQQ: no forecast
    assert by_con[9001]["bucket"] == "etf_0dte"
    assert by_con[1]["bucket"] == "michael"
    assert {p["ticker"] for p in result["michael"]["positions"]} == {"CSU"}
    assert result["drew"]["positions"] == []
    excluded = result["michael"]["header"]["excluded"]
    assert excluded["etf_0dte"] == 1
    assert excluded["etf_0dte_delivery"] == 1
    assert excluded["etf_0dte_delivery_unattributed"] == 1
