"""Economic invariants and information cutoffs in the research upgrade."""
from datetime import date, timedelta
from types import SimpleNamespace
import json

import pytest

from reverse_splits.adjust import PriceFrame
from reverse_splits.analysis import cluster_interval
from reverse_splits.book import Candidate, Settings
from reverse_splits.config import load_config
from reverse_splits.fundamentals import FundamentalBridge
from reverse_splits.realism import Realism, _locate, maintenance, prepare, rounded_collateral, simulate_daily, verified_announcements


def candidate(ticker="TEST", entry="2024-01-05", exit="2024-01-08", px=10, close_px=9):
    path = {entry: {"open": px, "high": px, "low": px, "close": px, "volume": 100000, "factor": 1},
            exit: {"open": close_px, "high": close_px, "low": close_px, "close": close_px, "volume": 100000, "factor": 1}}
    return Candidate(1, ticker, ticker, "first", "listed", "announcement_evidence", "announce",
                     entry, exit, px, close_px, 100, 3, False, "none", 100000, 100000, 1,
                     {entry: px, exit: close_px}, extra={"entry_price": px, "exit_price": close_px, "path": path})


def frictionless(**kw):
    return Realism(commission_per_share=0, minimum_commission=0, extra_slippage_bps=0,
                   position_fraction=1, buffer_fraction=0, **kw)


def business_days(start: str, count: int) -> list[str]:
    out, day = [], date.fromisoformat(start)
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def scratch_config(tmp_path):
    cfg = load_config(ensure_dirs=False)
    cfg.root = tmp_path
    return cfg


def test_margin_is_equity_requirement_and_respects_low_price_floor():
    assert maintenance(100, 1) == 250
    assert maintenance(100, 3) == 300
    assert maintenance(100, 10, house=.5) == 500
    assert maintenance(100, 10) == 1000
    assert rounded_collateral(100, 1.01) == 200


def test_fee_uses_marked_rounded_collateral_and_calendar_weekend():
    c = candidate()
    taken, _, eq = simulate_daily([c], Settings(max_book=10000, target_notional=1000, fee_annual=1), frictionless())
    assert taken[0].fee_pnl == pytest.approx(100 * 11 * 3 / 360)
    assert taken[0].net_pnl == pytest.approx(100 - 100 * 11 * 3 / 360)
    assert eq[-1]["equity"] == pytest.approx(10000 + taken[0].net_pnl)


def test_close_today_does_not_fund_an_entry_at_todays_open():
    c = candidate()
    second = candidate("SECOND", entry="2024-01-08", exit="2024-01-09")
    taken, skipped, _ = simulate_daily([c, second], Settings(max_book=1000, target_notional=1000, fee_annual=0), frictionless())
    assert [t.ticker for t in taken] == ["TEST"]
    assert skipped["margin_or_minimum_size"] == 1


def test_margin_loss_is_covered_at_next_open_with_gap_not_at_trigger():
    c = candidate(entry="2024-01-05", exit="2024-01-09", px=100, close_px=100)
    c.shares = 10
    c.extra["path"]["2024-01-05"]["high"] = 200
    c.extra["path"]["2024-01-05"]["close"] = 200
    c.extra["path"]["2024-01-08"] = {"open": 250, "high": 250, "low": 250, "close": 250, "volume": 100000, "factor": 1}
    taken, _, eq = simulate_daily([c], Settings(max_book=1000, target_notional=1000, fee_annual=0, spread_floor=0, spread_range_fraction=0), frictionless())
    assert taken[0].exit_date == "2024-01-08"
    assert taken[0].exit_fill == 250
    assert taken[0].net_pnl == -1500
    assert taken[0].extra["exit_reason"] == "next_open_margin"
    assert eq[-1]["equity"] == -500  # no clipping away a short's loss


def test_split_shares_and_marks_change_only_on_action_day():
    c = candidate(px=2, close_px=18)
    c.extra["path"][c.exit_date]["factor"] = .1
    c.share_factor = .1
    taken, _, eq = simulate_daily([c], Settings(max_book=5000, target_notional=200, fee_annual=0), frictionless())
    assert taken[0].gross_pnl == pytest.approx(20)
    assert eq[0]["equity"] == 5000
    assert eq[-1]["equity"] == pytest.approx(5020)


def test_locate_excludes_future_same_day_stale_and_naive_timestamps():
    rows = {"TEST": [("2024-01-05T10:00:00-05:00", 100, .2), ("2024-01-03T08:00:00-05:00", 100, .2), ("2024-01-05", 100, .2)]}
    assert _locate(rows, "TEST", "2024-01-05", 24) is None
    rows["TEST"].append(("2024-01-05T08:00:00-05:00", 100, .2))
    assert _locate(rows, "TEST", "2024-01-05", 24)[2] == .2


def test_five_sessions_includes_entry_and_uses_twenty_prior_sessions():
    days = business_days("2024-01-01", 30)
    frame = PriceFrame(days, [10.0]*30, [10.1]*30, [9.9]*30, [10.0]*30, [100000]*30)
    event = {"id": 1, "ticker": "TEST", "outcome": "announcement_evidence", "exchange_class": "listed",
             "announce_date": days[19], "ex_date": "", "ratio": .1}
    pool, _ = prepare([event], {"TEST": frame}, Settings(horizon=5))
    assert len(pool) == 1
    assert pool[0].entry_date == days[20]
    assert pool[0].exit_date == days[24]


def test_verified_universe_does_not_require_later_completion():
    issuer = {"id": 1, "ticker": "TEST", "cik": "123", "outcome": "announced_only", "exchange_class": "listed"}
    hit = {"cik": "123", "accession": "1", "substantive": 1, "text_parsed": 1,
           "parsed_ratio": .1, "filed_at": "2024-01-05", "parsed_ex_date": None}
    pool, _ = verified_announcements([issuer], [hit])
    assert len(pool) == 1
    issuer["outcome"] = "effective"
    assert verified_announcements([issuer], [hit])[0] == pool
    hit["parsed_ex_date"] = "2023-01-01"
    assert not verified_announcements([issuer], [hit])[0]


def test_whole_issuer_interval_is_repeatable_and_keeps_repeated_names():
    rows = [{"ticker": str(i), "net_return": float(i-3)/10} for i in range(6)]
    rows += [{"ticker": "0", "net_return": -.5}]
    assert cluster_interval(rows) == cluster_interval(rows)
    assert cluster_interval(rows)["clusters"] == 6
    assert cluster_interval(rows)["low"] < cluster_interval(rows)["high"]


def test_raw_facts_filter_revisions_and_same_day_before_shared_extraction(tmp_path):
    cfg = scratch_config(tmp_path)
    cfg.raw["paths"]["raw_dir"] = "raw"
    bridge = FundamentalBridge(cfg)
    assert bridge.extractor is not None, "build_fundamental_series must import from _system/scripts"
    assert bridge.screen is not None, "build_short_quant_screen must import from _system/scripts"
    bridge.cache.mkdir(parents=True)
    facts = {"cik": 123, "facts": {"us-gaap": {"Assets": {"units": {"USD": [
        {"end": "2023-12-31", "val": 100, "filed": "2024-01-04", "form": "10-K", "accn": "old"},
        {"end": "2023-12-31", "val": 999, "filed": "2024-01-05", "form": "10-K/A", "accn": "later"}]}}}}}
    (bridge.cache / "CIK0000000123.json").write_text(json.dumps(facts))
    doc, source, evidence = bridge.series("TEST", "0000000123", "2024-01-05")
    assert source == "raw_companyfacts"
    assert doc["metrics"]["total_assets"][-1]["value"] == 100
    assert doc["metrics"]["total_assets"][-1]["accessions"] == ["old"]
    later, _, _ = bridge.series("TEST", "123", "2024-01-06")
    assert later["metrics"]["total_assets"][-1]["value"] == 999


def test_bridge_manifest_hashes_the_imported_ssi_modules(tmp_path):
    bridge = FundamentalBridge(scratch_config(tmp_path))
    manifest = bridge.manifest()
    assert manifest["available"] is True
    labels = {link["label"]: link for link in manifest["links"]}
    assert labels["build_fundamental_series.py"]["sha256"]
    assert labels["build_short_quant_screen.py"]["sha256"]
    assert labels["build_fundamental_series.py"]["url"].endswith("_system/scripts/build_fundamental_series.py")


def test_missing_and_mismatched_fundamentals_are_unscored(tmp_path):
    bridge = FundamentalBridge(scratch_config(tmp_path))
    result = bridge.score("NOT_A_REAL_ISSUER", "999", "2024-01-05")
    assert result["score"] is None
    assert not result["historical_eligible"]
    assert result["fraud_bad_actors"] == "unscored"


def test_financial_issuers_cannot_get_an_operating_company_composite(tmp_path):
    bridge = FundamentalBridge(scratch_config(tmp_path))
    bridge.cache.mkdir(parents=True)
    (bridge.cache / "CIK0000000123.issuer.json").write_text(json.dumps({"cik": 123, "sic": 6020}))
    bridge.series = lambda *args: ({"metrics": {}}, "raw_companyfacts", [])
    bridge.screen = SimpleNamespace(
        fundamental_signals=lambda *args: ({k: {"value": 1, "score": 1} for k in ("a", "b", "c")}, {}),
        FUNDAMENTAL_SIGNALS={k: ("accounting", 1) for k in ("a", "b", "c")},
        profile_for=lambda sic: "financial" if sic == 6020 else "operating")
    result = bridge.score("BANK", "123", "2024-01-05")
    assert result["evidence_count"] == 3
    assert result["profile"] == "financial"
    assert result["score"] is None
    assert not result["historical_eligible"]


def test_borrow_csv_retains_source_time_and_low_percentage_fees(tmp_path):
    from reverse_splits.borrow import import_ibkr_slb_csv
    from reverse_splits.db import init_db
    cfg = scratch_config(tmp_path)
    cfg.raw["paths"]["db_path"] = "test.db"
    path = tmp_path / "borrow.csv"
    path.write_text("Symbol,Available,Fee Rate,asof_ts\nTEST,100,1.2%,2024-01-05T08:00:00-05:00\n")
    assert import_ibkr_slb_csv(path, cfg) == 1
    conn = init_db(cfg.db_path)
    row = conn.execute("SELECT * FROM borrow_snapshots").fetchone()
    assert row["asof_ts"] == "2024-01-05T08:00:00-05:00"
    assert row["fee_rate"] == pytest.approx(.012)
    assert row["source"] == "ibkr_csv"
    conn.close()


def test_new_scenario_and_evidence_persist_for_reproduction(tmp_path):
    from reverse_splits.db import init_db
    from reverse_splits.run_book import persist_snapshot
    cfg = scratch_config(tmp_path)
    cfg.raw["paths"]["db_path"] = "test.db"
    trade = {"event_id": -1, "ticker": "TEST", "name": "TEST", "cohort": "first",
             "outcome": "announcement_evidence", "signal": "announce", "entry_date": "2024-01-05",
             "exit_date": "2024-01-08", "entry_fill": 10, "exit_fill": 9, "shares": 100,
             "notional": 1000, "gross_pnl": 100, "fee_pnl": 9, "net_pnl": 91, "net_return": .091,
             "forced_cover": False, "jump_status": "none", "hold_days": 3, "exit_breach": False,
             "peer_ticker": None, "peer_return": None, "control_ticker": None, "control_return": None,
             "date_quality": "filing_text", "adv_shares": 10000, "audit_flags": ["review"]}
    book = {"id": "verified", "assumptions": {"borrow_policy": "assumed_fee", "fee_annual": 1},
            "funnel": [{"stage": "taken", "n": 1}], "trades": [trade], "analysis": {"test": 1},
            "equity": [{"date": "2024-01-08", "equity": 50091, "cash": 50091, "open_names": 0,
                        "margin_required": 0, "gross_exposure": 0, "margin_breach": False}]}
    persist_snapshot(cfg, {"books": [], "realism": {"books": [book]}, "provenance": {"test": "hash"}})
    conn = init_db(cfg.db_path)
    row = conn.execute("SELECT gross_pnl,fee_pnl,evidence_json FROM book_trades").fetchone()
    assert row["gross_pnl"] == 100
    assert row["fee_pnl"] == 9
    assert json.loads(row["evidence_json"])["audit_flags"] == ["review"]
    assert conn.execute("SELECT label FROM book_runs").fetchone()[0] == "verified"
    conn.close()
