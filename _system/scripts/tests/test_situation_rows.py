"""Situation rows: schema, append-only versions, and the dashboard projection."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_situation_rows as checker  # noqa: E402
import situation_rows  # noqa: E402

LEDGER = ROOT / "_system" / "data" / "special_situations" / "situations.jsonl"


def test_committed_ledger_has_no_errors():
    rows = situation_rows.load_lines(LEDGER)
    assert len(rows) >= 7
    assert checker.check_rows(rows, root=ROOT) == []


def test_latest_version_wins_and_projects_open_rows_to_the_inbox():
    rows = situation_rows.load_lines(LEDGER)
    latest = situation_rows.latest_by_id(rows)
    ids = {row["situation_id"] for row in latest}
    assert "sit:skya-tender-2026" in ids
    assert "sit:mdt-mmed-2026" in ids
    book = situation_rows.attach_to_book({"rows": [], "discovery": [], "history": [], "counts": {}}, rows)
    projected = {row["situation_id"]: row for row in book["rows"] + book["history"]}
    assert projected["sit:skya-tender-2026"]["inbox"] is True
    assert projected["sit:skya-tender-2026"]["one_number"].startswith("$3.00")
    assert projected["sit:mdt-mmed-2026"]["book"] == "history"
    assert projected["sit:fdx-freight-2026"]["lane"] == "forced_sellers"
    assert book["situation_rows"]


def test_a_second_version_appends_and_a_gap_fails(tmp_path: Path):
    rows = situation_rows.load_lines(LEDGER)
    skya = next(row for row in rows if row["situation_id"] == "sit:skya-tender-2026")
    updated = copy.deepcopy({key: value for key, value in skya.items() if key != "_line"})
    updated["version"] = 2
    updated["recorded_at"] = "2026-11-05T15:00:00Z"
    updated["status"] = "passed"
    updated["drew_verdict"] = {"by": "drew", "at": "2026-11-05", "text": "Pass. Proration too tight."}
    ledger = tmp_path / "situations.jsonl"
    original = LEDGER.read_text(encoding="utf-8").splitlines()
    skya_line = next(line for line in original if "sit:skya-tender-2026" in line)
    ledger.write_text(skya_line + "\n" + json.dumps(updated) + "\n", encoding="utf-8")
    loaded = situation_rows.load_lines(ledger)
    assert checker.check_rows(loaded, root=ROOT) == []
    assert situation_rows.latest_by_id(loaded)[0]["status"] == "passed"

    updated["version"] = 4
    ledger.write_text(skya_line + "\n" + json.dumps(updated) + "\n", encoding="utf-8")
    errors = checker.check_rows(situation_rows.load_lines(ledger), root=ROOT)
    assert any("versions must be 1..N" in error for error in errors)


def test_a_fact_without_an_accession_fails(tmp_path: Path):
    rows = situation_rows.load_lines(LEDGER)
    skya = copy.deepcopy(next(row for row in rows if row["situation_id"] == "sit:skya-tender-2026"))
    skya.pop("_line", None)
    skya["statements"][0].pop("accession")
    ledger = tmp_path / "situations.jsonl"
    ledger.write_text(json.dumps(skya) + "\n", encoding="utf-8")
    errors = checker.check_rows(situation_rows.load_lines(ledger), root=ROOT)
    assert any("without an accession" in error for error in errors)


def test_missing_input_path_fails(tmp_path: Path):
    rows = situation_rows.load_lines(LEDGER)
    skya = copy.deepcopy(next(row for row in rows if row["situation_id"] == "sit:skya-tender-2026"))
    skya.pop("_line", None)
    skya["inputs_read"] = [
        {
            "feed": "portfolio_news",
            "path": "dashboard/data/does-not-exist.json",
            "generated_at": None,
            "envelope_generated_at": None,
            "health": None,
        }
    ]
    ledger = tmp_path / "situations.jsonl"
    ledger.write_text(json.dumps(skya) + "\n", encoding="utf-8")
    errors = checker.check_rows(situation_rows.load_lines(ledger), root=ROOT)
    assert any("does not exist" in error for error in errors)
