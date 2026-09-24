"""Flex EOD statements that carry NAV become complete snapshots -- at the right date.

The Flex positions query is gaining an equity-summary section. From then on each
nightly statement states NetLiquidation, so flex_ingest marks the snapshot
complete and the book stops serving the collector's 2026-08-25 run. These tests
drive the fixture statements through the real parser and the real hub ledger:

  * an equity summary is one row per report date, and a multi-day period lists
    several -- the NAV is the latest date's, wherever that row sits in the file;
  * several ChangeInNAV rows resolve the same way, by toDate;
  * when both sections are present the equity summary wins, in either order;
  * the snapshot declares itself a Flex EOD feed with its session date;
  * the hub ledger then serves this run as the latest complete snapshot.

The JS half (dashboard/cloudflare/test-flex-eod-book.mjs) stores the golden
payload below in D1 and checks the edge's book query selects it. The golden is
compared here against what build_account_snapshot actually produces, so the two
halves cannot drift apart silently.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from _system.trading.portfolio_hub.flex_ingest import _report_date_key, build_account_snapshot
from _system.trading.portfolio_hub.ledger import PortfolioLedger

FIXTURES = Path(__file__).with_name("fixtures")
GOLDEN = Path(__file__).resolve().parents[4] / "dashboard" / "cloudflare" / "fixtures" / "flex_eod_account_snapshot.json"
FIXED_AS_OF = "2026-09-24T22:15:14Z"

LATEST_NAV = Decimal("11867165.25")  # the 20260924 row in every NAV-bearing fixture


def _snapshot(name: str) -> dict:
    return build_account_snapshot(FIXTURES / name, account_alias="U805366")


def _nav(payload: dict) -> Decimal:
    return Decimal(next(row["value"] for row in payload["account_values"] if row["tag"] == "NetLiquidation"))


@pytest.mark.parametrize("name", [
    "flex_eod_equity_summary_multi_date.xml",
    "flex_eod_change_in_nav_multi_row.xml",
    "flex_eod_summary_then_nav.xml",
    "flex_eod_nav_then_summary.xml",
])
def test_a_nav_bearing_statement_is_complete_at_its_latest_date(name):
    payload = _snapshot(name)
    assert payload["complete"] is True
    assert _nav(payload) == LATEST_NAV
    assert payload["completeness"]["account_summary"] is True
    assert payload["completeness"]["feed"] == "flex_eod"
    assert payload["completeness"]["session_date"] == "2026-09-24"


def test_the_equity_summary_is_read_at_its_latest_report_date_not_its_first_row():
    """summaries[0] is the oldest row when IBKR lists dates ascending."""
    payload = _snapshot("flex_eod_equity_summary_multi_date.xml")
    tags = {row["tag"]: Decimal(row["value"]) for row in payload["account_values"]}
    assert tags["NetLiquidation"] == LATEST_NAV, "not 11600000.00 (the first row, 2026-09-22)"
    assert tags["TotalCashValue"] == Decimal("1150000.25")
    assert tags["GrossPositionValue"] == Decimal("10722835")


def test_the_equity_summary_wins_over_change_in_nav_in_either_order():
    for name in ("flex_eod_summary_then_nav.xml", "flex_eod_nav_then_summary.xml"):
        assert _nav(_snapshot(name)) == LATEST_NAV, f"{name}: the disagreeing ChangeInNAV (999.00) won"


def test_a_positions_only_statement_stays_incomplete():
    payload = _snapshot("flex_eod_positions_only.xml")
    assert payload["complete"] is False
    assert payload["account_values"] == []
    assert payload["completeness"]["feed"] == "flex_eod"


@pytest.mark.parametrize("raw,expected", [
    ("20260924", "20260924"),
    ("2026-09-24", "20260924"),
    ("2026-09-24T18:10:02", "20260924"),
    ("20260924;181002", "20260924"),
    ("09/24/2026", "20260924"),
    ("", ""),
    ("not a date", ""),
])
def test_report_dates_sort_in_every_format_a_query_can_emit(raw, expected):
    assert _report_date_key(raw) == expected


def test_a_us_formatted_multi_date_summary_still_picks_the_latest(tmp_path):
    xml = (FIXTURES / "flex_eod_equity_summary_multi_date.xml").read_text(encoding="utf-8")
    for iso, us in (("20260922", "09/22/2026"), ("20260923", "09/23/2026"), ("20260924", "09/24/2026")):
        xml = xml.replace(f'reportDate="{iso}"', f'reportDate="{us}"')
    path = tmp_path / "us.xml"
    path.write_text(xml, encoding="utf-8")
    assert _nav(build_account_snapshot(path, account_alias="U805366")) == LATEST_NAV


def _collector_snapshot() -> dict:
    """A stand-in for the 2026-08-25 collector run the book has been stuck on."""
    return {
        "schema_version": "account_snapshot.v1", "source_run_id": "collector-2026-08-25",
        "account_alias": "U805366", "gateway_session_id": "gw-1", "as_of": "2026-08-25T15:26:01Z",
        "complete": True, "base_currency": "USD", "completeness": {"account_summary": True},
        "account_values": [{"tag": "NetLiquidation", "value": "11870000", "currency": "USD",
                            "source": "ibkr", "as_of": "2026-08-25T15:26:01Z"}],
        "positions": [],
    }


def test_the_hub_ledger_serves_the_complete_flex_run_as_the_latest_snapshot(tmp_path):
    ledger = PortfolioLedger(tmp_path / "portfolio.db")
    ledger.migrate()
    try:
        ledger.ingest_account_snapshot(_collector_snapshot())
        flex = _snapshot("flex_eod_equity_summary_multi_date.xml")
        ledger.ingest_account_snapshot(flex)

        latest = ledger.latest_account_snapshot_payload("U805366")
        assert latest["source_run_id"] == flex["source_run_id"], "the hourly publisher must move to the Flex run"
        assert latest["complete"] is True
        assert {row["tag"]: Decimal(row["value"]) for row in latest["account_values"]}["NetLiquidation"] == LATEST_NAV

        projection = ledger.allocation_projection("U805366")
        assert projection["source_run_id"] == flex["source_run_id"]
        assert projection["allocations"], "a complete Flex run gets policy allocations like the collector's did"
    finally:
        ledger.close()


def test_a_positions_only_flex_run_never_displaces_the_last_complete_snapshot(tmp_path):
    """Today's behaviour, kept: complete=0 runs are stored but never served."""
    ledger = PortfolioLedger(tmp_path / "portfolio.db")
    ledger.migrate()
    try:
        ledger.ingest_account_snapshot(_collector_snapshot())
        ledger.ingest_account_snapshot(_snapshot("flex_eod_positions_only.xml"))
        assert ledger.latest_account_snapshot_payload("U805366")["source_run_id"] == "collector-2026-08-25"
    finally:
        ledger.close()


def _normalized(payload: dict) -> dict:
    """Pin the fields that vary run to run: parse time, and the file-bytes hash
    in source_run_id (CRLF on a Windows checkout changes it)."""
    payload = json.loads(json.dumps(payload))
    payload["source_run_id"] = "flex-eod-golden"
    payload["as_of"] = FIXED_AS_OF
    for row in payload["positions"]:
        row["as_of"] = FIXED_AS_OF
        if row.get("fx_as_of"):
            row["fx_as_of"] = FIXED_AS_OF
    for row in payload["account_values"]:
        row["as_of"] = FIXED_AS_OF
    return payload


def test_the_edge_golden_is_exactly_what_flex_ingest_produces():
    produced = _normalized(_snapshot("flex_eod_equity_summary_multi_date.xml"))
    if os.environ.get("REGENERATE_FLEX_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(produced, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert produced == golden, "regenerate with REGENERATE_FLEX_GOLDEN=1 and review the diff"
