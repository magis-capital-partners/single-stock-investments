"""Offline tests for N-PORT and EDINET stake normalization. No network."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import intl_holdings  # noqa: E402


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nport" / "mini.xml"


def test_nport_reads_period_isin_and_country():
    period, rows = intl_holdings.parse_nport_holdings(FIXTURE.read_bytes())
    assert period == "2026-06-30"
    assert rows[0]["isin"] == "JP3183200009"
    assert rows[0]["country"] == "JP"
    assert rows[0]["shares"] == 1000
    assert rows[0]["value_usd"] == 250000
    assert rows[1]["cusip"] == "478160104"
    assert rows[1]["isin"] == "US4781601046"


def test_a_japan_issuer_matches_one_portfolio_name():
    period, rows = intl_holdings.parse_nport_holdings(FIXTURE.read_bytes())
    portfolio = {"8697.T": "Japan Exchange Group", "JNJ": "Johnson & Johnson", "0388.HK": "Hong Kong Exchanges and Clearing"}
    assert intl_holdings.match_portfolio_ticker(rows[0], portfolio) == "8697.T"
    assert intl_holdings.match_portfolio_ticker(rows[1], portfolio) == "JNJ"
    assert intl_holdings.is_international(rows[0], "8697.T")
    assert not intl_holdings.is_international(rows[1], "JNJ")
    assert period


def test_two_similar_names_do_not_match():
    row = {"name": "Exchange Group", "isin": ""}
    portfolio = {"8697.T": "Japan Exchange Group", "0388.HK": "Hong Kong Exchanges and Clearing"}
    assert intl_holdings.match_portfolio_ticker(row, portfolio) is None


def test_the_daily_job_runs_the_international_scripts():
    text = Path(__file__).resolve().parents[3].joinpath(".github/workflows/data-pipeline.yml").read_text(encoding="utf-8")
    assert "python _system/scripts/ingest_nport_intl.py --tracked-only --limit 8" in text
    assert "python _system/scripts/ingest_edinet_stakes.py" in text


def test_edinet_without_a_key_is_an_empty_status():
    status = intl_holdings.edinet_status(False, detail="EDINET_API_KEY is not set")
    assert status["configured"] is False
    assert status["in_base_irr"] is False
    assert status["stakes"] == []
    assert status["source"] == "edinet"
    json.dumps(status)
