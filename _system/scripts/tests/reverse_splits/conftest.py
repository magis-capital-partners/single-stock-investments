"""Shared setup for the reverse-split suites: ``_system/scripts`` on the path and a fixture ledger."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from reverse_splits.ledger import (  # noqa: E402
    SCHEMA_VERSION as LEDGER_SCHEMA,
    canonical,
    ledger_paths,
    record_hash,
    write_json,
    write_jsonl,
)

AS_OF = "2026-10-11"


def decision_rows(tickers=("DFLI", "NXGL")) -> list[dict]:
    """A valid two-link decision chain shaped like strategy.record_decision output."""
    rows, previous = [], ""
    for index, ticker in enumerate(tickers, 1):
        record = {
            "id": f"00000000-0000-0000-0000-00000000000{index}",
            "recorded_at": f"2026-10-0{index}T15:00:00+00:00",
            "ticker": ticker,
            "decision": "review" if index % 2 else "pass",
            "reason": "fixture",
            "supersedes": None,
            "prospective": True,
            "policy": {"version": "RSI-1.0"},
            "inputs": {"as_of": AS_OF},
            "evaluation": {"status": "review_required"},
            "source_system": "reverse_split_research",
            "previous_hash": previous,
        }
        record["record_hash"] = record_hash(record)
        rows.append(
            {
                "id": record["id"],
                "recorded_at": record["recorded_at"],
                "ticker": ticker,
                "previous_hash": previous,
                "record_hash": record["record_hash"],
                "record": record,
            }
        )
        previous = record["record_hash"]
    return rows


def fixture_events() -> list[dict]:
    base = {
        "exchange": "Nasdaq", "exchange_class": "listed", "split_to": 1.0, "status": "seeded", "confidence": 0.5,
        "needs_review": 0, "source": "yfinance", "outcome": "effective", "vote_path": None, "accept_time": None,
        "announced_ex_date": None, "announced_ratio": None, "jump_status": None, "jump_observed": None,
        "date_quality": "filing_text", "accession": None, "form": None, "vote_date": None, "ratio_set_date": None,
        "created_at": "2026-10-09 03:14:38", "updated_at": "2026-10-09 04:04:43",
    }
    return [
        {**base, "ticker": "AAA", "cik": "0000000001", "company": "Alpha Corp", "split_from": 10.0, "ratio": 0.1,
         "first_proxy_date": "2024-01-02", "announce_date": "2024-02-01", "effective_date": "2024-03-01", "ex_date": "2024-03-01",
         "prior_rs_count": 0, "cohort": "first"},
        {**base, "ticker": "AAA", "cik": "0000000001", "company": "Alpha Corp", "split_from": 20.0, "ratio": 0.05,
         "first_proxy_date": None, "announce_date": "2026-09-20", "effective_date": "2026-10-20", "ex_date": "2026-10-20",
         "prior_rs_count": 1, "cohort": "second", "status": "edgar_candidate", "source": "edgar_search",
         "accession": "000100000026000001", "form": "8-K", "confidence": 0.3, "needs_review": 1},
        {**base, "ticker": "BBB", "cik": "0000000002", "company": "Beta Inc", "exchange_class": "otc", "exchange": "OTC",
         "split_from": 50.0, "ratio": 0.02, "first_proxy_date": None, "announce_date": "2025-05-01",
         "effective_date": "2025-06-01", "ex_date": "2025-06-01", "prior_rs_count": 0, "cohort": "first"},
    ]


def fixture_announcements() -> list[dict]:
    return [
        {"ticker": "CCC", "cik": "0000000003", "company": "Gamma Ltd", "exchange": "NYSE", "exchange_class": "listed",
         "announce_date": "2026-10-01", "announced_ex_date": "2026-10-15", "announced_ratio": 0.1, "outcome": "announced_only",
         "date_quality": "filing_text", "accept_time": "2026-10-01T20:30:00.000Z", "accession": "000100000026000003", "form": "8-K"},
        {"ticker": "DDD", "cik": "0000000004", "company": None, "exchange": None, "exchange_class": "unknown",
         "announce_date": "2026-09-28", "announced_ex_date": "2026-11-01", "outcome": "cancelled",
         "date_quality": "filing_text", "accept_time": "2026-09-28T12:00:00.000Z", "accession": "000100000026000004", "form": "6-K"},
        {"ticker": "EEE", "cik": "0000000005", "company": "Epsilon Co", "exchange": "Nasdaq", "exchange_class": "listed",
         "announce_date": "2026-06-01", "outcome": "announced_only", "date_quality": "acceptance_time",
         "accept_time": "2026-06-01T12:00:00.000Z", "accession": "000100000026000005", "form": "8-K"},
        {"ticker": "FFF", "cik": "0000000006", "company": "Zeta plc", "exchange": "Nasdaq", "exchange_class": "listed",
         "announce_date": "2026-10-09", "outcome": "mention", "date_quality": "filing_text",
         "accept_time": "2026-10-09T12:00:00.000Z", "accession": "000100000026000006", "form": "8-K"},
    ]


def fixture_book_runs() -> tuple[list[dict], list[dict]]:
    manifest = {"python": "3.12", "source_files": [{"path": "x.py", "sha256": "0" * 64}]}
    import hashlib

    digest = hashlib.sha256(canonical(manifest).encode()).hexdigest()
    runs = [
        {"id": 1, "created_at": "2026-10-11 23:18:48", "label": "assumed_100_h5_effective",
         "config": {"signal": "announce", "horizon_days": 5, "fee_annual": 1.0, "borrow_policy": "assumed_fee"},
         "analysis": {"waterfall": {"raw_price_pnl": -10000.0, "gross_after_fills": -12000.0, "borrow": 2000.0, "commission": 286.0, "net": -14286.0},
                      "profit_factor": 0.6, "losses_over_50pct": 7, "margin_breach_days": 0, "max_margin_required": 1000.0},
         "funnel": [{"stage": "events", "n": 632}, {"stage": "taken", "n": 124}], "source_manifest_sha256": digest},
        {"id": 2, "created_at": "2026-10-11 23:18:48", "label": "fundamental_60",
         "config": {"signal": "announce", "horizon_days": 5, "fee_annual": 1.0, "borrow_policy": "assumed_fee"},
         "analysis": {"waterfall": {"net": 140.72}, "profit_factor": 1.34, "losses_over_50pct": 0, "margin_breach_days": 0},
         "funnel": [{"stage": "evidence_pool", "n": 48}, {"stage": "taken", "n": 4}], "source_manifest_sha256": digest},
    ]
    return runs, [{"sha256": digest, "manifest": manifest}]


def write_fixture_ledger(directory: Path, *, exported_at: str | None = None) -> dict[str, Path]:
    paths = ledger_paths(directory)
    runs, manifests = fixture_book_runs()
    write_jsonl(paths["events"], fixture_events())
    write_jsonl(paths["announcements"], fixture_announcements(), sparse=True)
    write_jsonl(paths["finra_short_interest"], [
        {"ticker": "AAA", "settlement_date": "2024-02-29", "avg_daily_volume": 123456.0, "source_file": "synthetic_adv_only"},
        {"ticker": "BBB", "settlement_date": "2025-05-30", "short_interest": 1000.0, "avg_daily_volume": 500.0, "days_to_cover": 2.0, "source_file": "finra.csv"},
    ], sparse=True)
    write_jsonl(paths["book_runs"], runs)
    write_jsonl(paths["book_source_manifests"], manifests)
    write_jsonl(paths["decisions"], decision_rows())
    stamp = exported_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(paths["manifest"], {"schema_version": LEDGER_SCHEMA, "exported_at": stamp,
                                   "files": {"events": {"rows": 3}, "announcements": {"rows": 4}},
                                   "caps": {"announcements_since": None, "finra_since": None},
                                   "decisions_chain_valid": True, "decisions_chain_errors": []})
    return paths


@pytest.fixture
def fixture_ledger(tmp_path):
    directory = tmp_path / "ledger"
    directory.mkdir()
    write_fixture_ledger(directory)
    return directory


@pytest.fixture
def stale_fixture_ledger(tmp_path):
    directory = tmp_path / "stale_ledger"
    directory.mkdir()
    old = (datetime.now(timezone.utc) - timedelta(days=11)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_fixture_ledger(directory, exported_at=old)
    return directory
