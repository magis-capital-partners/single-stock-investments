from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "build_short_alpha_dashboard.py"
SPEC = importlib.util.spec_from_file_location("build_short_alpha_dashboard", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

import short_scan_batch  # noqa: E402


REQUIRED_FRAMEWORKS = {
    "secular_obsolescence",
    "fad_single_product",
    "revenue_recognition",
    "earnings_vs_cash",
    "working_capital",
    "capitalization_reserves",
    "acquisition_nongaap_kpi",
    "reporting_integrity",
    "off_balance_sheet",
    "promotion_insider_selling",
    "borrow_and_carry",
    "crowding_squeeze",
    "path_and_timing",
    "issuer_retaliation",
}


def _bundle():
    positions = json.loads(MODULE.POSITIONS.read_text(encoding="utf-8"))["ideas"]
    candidates = json.loads(MODULE.CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    catalog = json.loads(MODULE.CATALOG.read_text(encoding="utf-8"))
    return positions, candidates, catalog


def test_initial_short_alpha_book_compiles() -> None:
    payload = MODULE.build()
    assert payload["summary"]["position_count"] == 7
    assert {row["ticker"] for row in payload["positions"]} == {
        "ASPN", "WEST", "EQPT", "FLUX", "XTIA", "EFOR", "LBRDK"
    }
    assert "ECHX" not in {row["ticker"] for row in payload["candidates"]}
    assert payload["summary"]["candidate_count"] > 7
    assert payload["summary"]["lead_count"] >= 1
    assert "gross_short_exposure_usd" not in payload["summary"]
    assert payload["positions"][0]["position"]["split_adjusted_open_price"] > 0
    assert payload["positions"][0]["borrow"]["status"] == "pending"
    assert REQUIRED_FRAMEWORKS <= {row["id"] for row in payload["frameworks"]}
    assert payload["summary"]["framework_coverage"]["secular_obsolescence"]["status"] == "Unscored"
    assert payload["summary"]["framework_coverage"]["borrow_and_carry"]["status"] == "Pending"


def test_activist_leads_do_not_clobber_the_open_book() -> None:
    payload = MODULE.build()
    by_ticker = {row["ticker"]: row for row in payload["candidates"]}
    feeds = short_scan_batch.collect_feed_shorts()
    for ticker, row in by_ticker.items():
        if row["origin"] == "position":
            assert row["stage"] == "live"
            assert row["hypothesis"]
    for ticker in feeds:
        assert ticker in by_ticker
        if by_ticker[ticker]["origin"] == "activist_index":
            assert by_ticker[ticker]["stage"] == "lead"
            assert by_ticker[ticker]["hypothesis"] == ""


def test_primary_framework_must_be_assigned() -> None:
    positions, candidates, catalog = _bundle()
    broken = copy.deepcopy(candidates)
    broken[0]["primary_framework"] = "regulatory"
    with pytest.raises(MODULE.LedgerError, match="primary framework"):
        MODULE._validate_bundle(positions, broken, catalog)


def test_position_must_be_short() -> None:
    positions, candidates, catalog = _bundle()
    broken = copy.deepcopy(positions)
    for row in broken:
        if row["ticker"] not in MODULE.EXCLUDED_TICKERS:
            row["position"]["shares"] = 100
            break
    with pytest.raises(MODULE.LedgerError, match="shares must be negative"):
        MODULE._validate_bundle(broken, candidates, catalog)


def test_position_requires_a_candidate() -> None:
    _positions, _candidates, catalog = _bundle()
    orphan = {
        "ticker": "ZZZZ",
        "position": {
            "shares": -1,
            "opened_price": 1,
            "opened_date": "2026-01-01",
            "split_adjustment_factor": 1,
        },
        "check_ins": [{"date": "2026-01-01", "price": 1, "hypothesis_state": "open", "note": "x"}],
    }
    with pytest.raises(MODULE.LedgerError, match="candidate"):
        MODULE._validate_bundle([orphan], [], catalog)


def test_upsert_does_not_overwrite_rejected_or_live_rows() -> None:
    existing = [
        {"ticker": "AAA", "stage": "rejected", "hypothesis": "no"},
        {"ticker": "LIVE", "stage": "live", "hypothesis": "yes"},
    ]
    incoming = [
        {"ticker": "AAA", "stage": "lead", "hypothesis": ""},
        {"ticker": "live", "stage": "lead", "hypothesis": ""},
        {"ticker": "bbb", "stage": "lead", "hypothesis": ""},
        {"ticker": "ECHX", "stage": "lead", "hypothesis": ""},
    ]
    merged, added = MODULE.upsert_leads(existing, incoming)
    assert added == ["BBB"]
    assert merged[0]["stage"] == "rejected"
    assert merged[0]["hypothesis"] == "no"
    assert merged[1]["stage"] == "live"


def test_furnace_events_map_onto_frameworks_and_keep_weakeners() -> None:
    hits = MODULE.furnace_hits([
        {"tags": ["going_concern"], "short_impact": "strengthens", "claim": "Runway fell."},
        {"tags": ["restatement"], "short_impact": "weakens", "claim": "Restatement was withdrawn."},
        {"tags": ["not_a_real_tag"], "short_impact": "strengthens", "claim": "Ignore."},
    ])
    assert hits[0]["framework_id"] == "cash_burn"
    assert hits[1]["framework_id"] == "reporting_integrity"
    assert hits[1]["short_impact"] == "weakens"
    assert hits[2]["framework_id"] is None
    effective = MODULE._effective_frameworks({"frameworks": ["accounting"]}, hits)
    assert effective == ["accounting", "cash_burn"]


def test_accounting_children_name_their_parent() -> None:
    catalog = json.loads(MODULE.CATALOG.read_text(encoding="utf-8"))
    children = [row for row in catalog["frameworks"] if row.get("parent") == "accounting"]
    assert {row["id"] for row in children} >= {
        "revenue_recognition",
        "earnings_vs_cash",
        "working_capital",
        "capitalization_reserves",
        "acquisition_nongaap_kpi",
        "reporting_integrity",
    }


def test_fugazi_rows_collapse_to_one_lead_per_ticker() -> None:
    leads = MODULE.leads_from_fugazi_rows([
        {"target": "Sidus Space", "ticker": "SIDU", "quote_symbol": "SIDU", "report_date": "2026-01-26", "report_url": "https://example.test/a"},
        {"target": "Sidus Space", "ticker": "sidu", "quote_symbol": "SIDU", "report_date": "2026-04-06", "report_url": "https://example.test/b"},
        {"target": "Advent Technologies", "ticker": "ADN", "quote_symbol": "ADNH", "report_date": "2025-08-18", "report_url": "https://example.test/c"},
    ])
    assert [row["ticker"] for row in leads] == ["ADN", "SIDU"]
    assert leads[0]["stage"] == "lead"
    assert leads[0]["hypothesis"] == ""
    assert "ADNH" in leads[0]["sources"][0]["label"]
    assert len(leads[1]["sources"]) == 2
    assert leads[1]["sources"][0]["label"].startswith("Fugazi Research")


def test_dashboard_wires_short_alpha_lazy_view() -> None:
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="short-alpha"' in html
    assert 'id="short-alpha-panel"' in html
    assert "short-alpha-viz.js" in html
    assert "fetch('data/short_alpha.json?'" in html
    assert "view === 'short-alpha'" in html
    assert "Short leads" in html
