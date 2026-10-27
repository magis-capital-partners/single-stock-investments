"""Verified historical filings must survive primary-checkpoint refreshes."""

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import investor_history as archive
import investor_history_checkpoint as checkpoint
import investor_universe as universe
import ownership_common as ownership
import stage_investor_history as staging
from holdings_asset_bundles import iter_packed_assets


def test_historical_supplement_survives_an_older_primary_pin_without_replacing_books(
    tmp_path, monkeypatch
):
    vault = tmp_path / "vault"
    parts = vault / "dashboard-private/investor-history"
    original = tmp_path / "earlier"
    db = archive.connect(original / "archive.sqlite")
    archive.store_filing(
        db,
        {
            "accession": "old",
            "manager_id": "former-name",
            "cik": "2",
            "period_end": "1999-12-31",
            "filed_at": "2000-02-01",
            "form": "13F-HR",
        },
        [{"cusip": "000000001", "value_usd": 20, "shares": 2}],
    )
    db.execute(
        "INSERT INTO raw_documents VALUES(?,?,?,?)",
        ("old", "original", "original-sha", b"source-bytes"),
    )
    db.commit()
    db.close()
    supplement = checkpoint.pack(original, parts)
    primary = tmp_path / "primary"
    db = archive.connect(primary / "archive.sqlite")
    manager = {"manager_id": "current", "display_name": "Example", "cik": "1"}
    archive.store_filing(
        db,
        {
            "accession": "new",
            "manager_id": "current",
            "cik": "1",
            "period_end": "2020-12-31",
            "filed_at": "2021-02-01",
            "form": "13F-HR",
        },
        [{"cusip": "000000002", "value_usd": 10, "shares": 1}],
    )
    db.close()
    archive.write_json(
        primary / "universe.json", {"managers": [manager], "source_ids": {}}
    )
    archive.write_json(primary / "disclosures.json", {"disclosures": [], "review": []})
    base = checkpoint.pack(primary, parts)
    records = [
        {
            "primary_cik": "1",
            "cik": "2",
            "sec_name": "Earlier Example",
            "first_quarter": "1999Q4",
            "last_quarter": "1999Q4",
            "checkpoint_identity": supplement["identity"],
        }
    ]
    reference = tmp_path / "histories.json"
    archive.write_json(reference, {"filers": records})
    monkeypatch.setattr(universe, "FILER_HISTORY", reference)
    monkeypatch.setattr(ownership, "load_cusip_map", dict)
    monkeypatch.setattr(ownership, "portfolio_universe", lambda: (set(), {}))
    receipt = tmp_path / "receipt.json"
    archive.write_json(receipt, {"identity": base["identity"]})
    target = tmp_path / "restored"
    result = staging.stage(
        tmp_path / "site", vault=vault, receipt=receipt, cache=target
    )
    assert result["historical_filings_added"] == 1
    index = json.loads(
        (tmp_path / "site/data/holdings/directory_index.json").read_text()
    )
    assert [r["quarter"] for r in index["managers"][0]["history"]] == [
        "1999Q4",
        "2020Q4",
    ]
    assert "former-name" not in "".join(
        body.decode() for _, body in iter_packed_assets(tmp_path / "site/data/holdings")
    )
    books = [
        json.loads(body).get("quarters", {})
        for relative, body in iter_packed_assets(tmp_path / "site/data/holdings")
        if relative.startswith("history/")
    ]
    earlier = next(quarters["1999Q4"] for quarters in books if "1999Q4" in quarters)
    assert earlier["filings"][0]["cik"] == "2"
    with closing(archive.connect(target / "archive.sqlite")) as db:
        assert (
            db.execute(
                "SELECT content_gzip FROM raw_documents WHERE accession='old'"
            ).fetchone()[0]
            == b"source-bytes"
        )
        archive.store_filing(
            db,
            {
                "accession": "old",
                "manager_id": "current",
                "cik": "2",
                "period_end": "1999-12-31",
                "filed_at": "2000-02-01",
                "form": "13F-HR",
            },
            [{"cusip": "000000001", "value_usd": 99, "shares": 2}],
        )
        db.commit()
    kwargs = dict(
        identity=supplement["identity"],
        manager_id="current",
        cik="2",
        first_quarter="1999Q4",
        last_quarter="1999Q4",
    )
    assert checkpoint.merge_historical(parts, target, **kwargs) == 0
    with closing(archive.connect(target / "archive.sqlite")) as db:
        assert archive.filing_rows(db, "old")[0]["value_usd"] == 99
    for invalid in (
        {"cik": "3"},
        {"first_quarter": "2000Q1", "last_quarter": "2000Q4"},
    ):
        with pytest.raises(ValueError, match="declared filer or dates"):
            checkpoint.merge_historical(parts, target, **{**kwargs, **invalid})
    with pytest.raises(RuntimeError, match="historical filings checkpoint is missing"):
        checkpoint.merge_historical(parts, target, **{**kwargs, "identity": "0" * 64})


def test_declared_historical_filer_does_not_mutate_inputs_or_take_another_owner():
    original = {
        "managers": [{"manager_id": "current", "display_name": "Example", "cik": "1"}]
    }
    records = [{"primary_cik": "1", "cik": "2", "sec_name": "Earlier Example"}]
    updated = universe.with_declared_filer_history(original, records)
    assert not original["managers"][0].get("cik_history")
    assert archive.cik_map(updated["managers"]) == {"1": "current", "2": "current"}
    assert universe.with_declared_filer_history(updated, records) == updated
    conflicting = {
        "managers": [*original["managers"], {"manager_id": "other", "cik": "2"}]
    }
    with pytest.raises(ValueError, match="another manager"):
        universe.with_declared_filer_history(conflicting, records)
