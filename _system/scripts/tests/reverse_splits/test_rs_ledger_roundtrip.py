"""SQLite <-> JSONL round trip: every exported table comes back identical, caps are recorded, chains verify."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from conftest import decision_rows
from reverse_splits.db import init_db
from reverse_splits.export_ledger import export_ledger
from reverse_splits.import_ledger import import_ledger
from reverse_splits.ledger import (
    ANNOUNCEMENT_DEFAULTS,
    canonical,
    ledger_paths,
    load_jsonl,
    make_notes,
    parse_notes,
    record_hash,
    verify_decision_chain,
)

SPLIT_COLUMNS = (
    "cik", "ticker", "exchange", "exchange_class", "split_from", "split_to", "ratio", "first_proxy_date",
    "announce_date", "vote_date", "ratio_set_date", "effective_date", "ex_date", "prior_rs_count", "cohort",
    "status", "confidence", "needs_review", "source", "notes", "outcome", "vote_path", "accept_time",
    "announced_ex_date", "announced_ratio", "jump_status", "jump_observed", "date_quality", "created_at", "updated_at",
)


def seed_source(db: Path, decisions_db: Path) -> None:
    conn = init_db(db)
    conn.executemany(
        "INSERT INTO issuers (cik, name, primary_ticker, exchange_class) VALUES (?, ?, ?, ?)",
        [("0000000001", "Alpha Corp", "AAA", "listed"), ("0000000003", "Gamma Ltd", "CCC", "listed"), ("0000000004", "Delta (no name)", "DDD", "unknown")],
    )
    conn.execute(
        """INSERT INTO reverse_splits (cik, ticker, exchange, exchange_class, split_from, split_to, ratio, first_proxy_date, announce_date,
           effective_date, ex_date, prior_rs_count, cohort, status, confidence, needs_review, source, notes, outcome, vote_path, accept_time,
           announced_ratio, date_quality, created_at, updated_at)
           VALUES ('0000000001','AAA','Nasdaq','listed',10,1,0.1,'2024-01-02','2024-02-01','2024-03-01','2024-03-01',0,'first','seeded',0.5,0,'yfinance',NULL,
                   'effective','board','2024-02-01T21:00:00.000Z',0.1,'filing_text','2026-10-09 03:14:38','2026-10-09 04:04:43')"""
    )
    conn.execute(
        """INSERT INTO reverse_splits (cik, ticker, exchange_class, split_from, split_to, ratio, announce_date, effective_date, ex_date,
           prior_rs_count, cohort, status, confidence, needs_review, source, notes, outcome, date_quality, created_at, updated_at)
           VALUES ('0000000001','AAA','listed',20,1,0.05,'2026-09-20','2026-10-20','2026-10-20',1,'second','edgar_candidate',0.3,1,'edgar_search',
                   'form=8-K accession=000100000026000001','effective','filing_text','2026-10-09 03:13:15','2026-10-09 04:04:43')"""
    )
    conn.executemany(
        """INSERT INTO reverse_splits (cik, ticker, exchange, exchange_class, split_from, split_to, ratio, announce_date, ex_date, effective_date,
           outcome, status, confidence, needs_review, source, date_quality, notes, accept_time, announced_ex_date, announced_ratio, vote_path,
           created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, 1, 1, ?, ?, ?, ?, 'announced_only', 0.4, 1, 'edgar_search', ?, ?, ?, ?, ?, ?, '2026-10-09 03:18:45', '2026-10-09 04:04:43')""",
        [
            ("0000000003", "CCC", "NYSE", "listed", "2026-10-01", "2026-10-01", "2026-10-01", "announced_only", "filing_text",
             "accession=000100000026000003 form=8-K", "2026-10-01T20:30:00.000Z", "2026-10-15", 0.1, None),
            ("0000000004", "DDD", None, "unknown", "2026-09-28", "2026-09-28", "2026-09-28", "cancelled", "filing_text",
             "accession=000100000026000004 form=6-K", "2026-09-28T12:00:00.000Z", None, None, "board"),
            ("0000000005", "EEE", None, "unknown", "2023-01-10", "2023-01-10", "2023-01-10", "announced_only", "acceptance_time",
             "accession=000100000023000005 form=8-K", "2023-01-10T12:00:00.000Z", None, None, None),
        ],
    )
    conn.executemany(
        "INSERT INTO finra_short_interest (ticker, settlement_date, short_interest, avg_daily_volume, days_to_cover, source_file) VALUES (?, ?, ?, ?, ?, ?)",
        [("AAA", "2024-02-29", None, 123456.5, None, "synthetic_adv_only"), ("CCC", "2026-09-30", 1000.0, 500.0, 2.0, "finra.csv"),
         ("EEE", "2023-01-15", None, 42.0, None, "synthetic_adv_only")],
    )
    manifest = json.dumps({"python": "3.12", "ssi_sources": [{"label": "x", "sha256": "0" * 64}]})
    conn.execute("INSERT INTO book_runs (id, created_at, label, config_json, analysis_json, source_manifest_json) VALUES (1, '2026-10-11 23:18:48', 'strict', ?, ?, ?)",
                 (json.dumps({"signal": "announce", "borrow_policy": "strict"}), json.dumps({"waterfall": {"net": 0.0}}), manifest))
    conn.execute("INSERT INTO book_runs (id, created_at, label, config_json, analysis_json, source_manifest_json) VALUES (2, '2026-10-11 23:18:48', 'fundamental_60', ?, ?, ?)",
                 (json.dumps({"signal": "announce", "horizon_days": 5}), json.dumps({"waterfall": {"net": 140.72}, "profit_factor": 1.34}), manifest))
    conn.execute("INSERT INTO book_runs (id, created_at, label, config_json, analysis_json, source_manifest_json) VALUES (3, '2026-10-09 15:26:12', 'legacy', ?, NULL, NULL)",
                 (json.dumps({"signal": "announce"}),))
    conn.executemany("INSERT INTO book_funnel (run_id, stage, n) VALUES (?, ?, ?)",
                     [(1, "events", 5), (1, "taken", 0), (2, "evidence_pool", 2), (2, "taken", 1), (3, "taken", 4)])
    conn.commit()
    conn.close()
    dec = sqlite3.connect(str(decisions_db))
    dec.execute("CREATE TABLE decisions (id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, ticker TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)")
    for row in decision_rows():
        dec.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?)", (row["id"], row["recorded_at"], row["ticker"], canonical(row["record"]), row["previous_hash"], row["record_hash"]))
    dec.commit()
    dec.close()


def split_rows(db: Path, where: str, skip: tuple[str, ...] = ()) -> dict:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = {}
    for r in conn.execute(f"SELECT * FROM reverse_splits WHERE {where}"):
        rows[(r["ticker"], r["ex_date"], r["split_from"], r["split_to"])] = {c: r[c] for c in SPLIT_COLUMNS if c not in skip}
    conn.close()
    return rows


@pytest.fixture
def exported(tmp_path):
    src, dec, out = tmp_path / "src.db", tmp_path / "dec.sqlite", tmp_path / "ledger"
    seed_source(src, dec)
    manifest = export_ledger(src, out, dec, today=date(2026, 10, 11))
    return src, dec, out, manifest


def test_export_writes_every_file_and_a_truthful_manifest(exported):
    _, _, out, manifest = exported
    paths = ledger_paths(out)
    assert manifest["files"]["events"]["rows"] == 2
    assert manifest["files"]["announcements"]["rows"] == 3
    assert manifest["files"]["finra_short_interest"]["rows"] == 3
    assert manifest["files"]["book_runs"]["rows"] == 3
    assert manifest["files"]["book_source_manifests"]["rows"] == 1  # two runs share one manifest, one has none
    assert manifest["files"]["decisions"]["rows"] == 2
    assert manifest["decisions_chain_valid"] is True
    assert manifest["caps"]["announcements_since"] is None
    for name in ("events", "announcements", "finra_short_interest", "book_runs", "book_source_manifests", "decisions"):
        assert paths[name].exists()
        assert manifest["files"][name]["bytes"] == paths[name].stat().st_size
    assert "prices_daily" in manifest["not_exported"] and "edgar_hits" in manifest["not_exported"]
    manifest_doc = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest_doc["exported_at"].endswith("Z")


def test_announcements_are_sparse_and_carry_parsed_filing_ids(exported):
    _, _, out, _ = exported
    rows = load_jsonl(ledger_paths(out)["announcements"])
    assert [r["ticker"] for r in rows] == ["EEE", "DDD", "CCC"]  # sorted by announce_date
    ccc = rows[-1]
    assert ccc["accession"] == "000100000026000003" and ccc["form"] == "8-K"
    assert ccc["company"] == "Gamma Ltd" and ccc["announced_ex_date"] == "2026-10-15"
    for constant in ("source", "confidence", "needs_review", "ex_date", "created_at", "updated_at", "notes"):
        assert constant not in ccc
    ddd = rows[1]
    assert ddd["outcome"] == "cancelled" and "announced_ratio" not in ddd and "exchange" not in ddd
    events = load_jsonl(ledger_paths(out)["events"])
    assert events[0]["accession"] is None and events[0]["source"] == "yfinance"
    assert events[1]["accession"] == "000100000026000001" and events[1]["form"] == "8-K" and events[1]["company"] == "Alpha Corp"
    assert "notes" not in events[1]


def test_import_rebuilds_sqlite_identically(exported, tmp_path):
    src, dec, out, _ = exported
    dst, dst_dec = tmp_path / "dst.db", tmp_path / "dst_dec.sqlite"
    counts = import_ledger(out, dst, dst_dec)
    assert counts == {"events": 2, "announcements": 3, "finra_short_interest": 3, "book_runs": 3, "issuers": 4, "decisions": 2}
    assert split_rows(src, "status != 'announced_only'") == split_rows(dst, "status != 'announced_only'")
    skip = ("created_at", "updated_at")
    assert split_rows(src, "status = 'announced_only'", skip) == split_rows(dst, "status = 'announced_only'", skip)
    conn = sqlite3.connect(str(dst))
    assert conn.execute("SELECT COUNT(*) FROM reverse_splits WHERE status='announced_only' AND created_at IS NULL").fetchone()[0] == 0
    assert conn.execute("SELECT source, confidence, needs_review FROM reverse_splits WHERE ticker='CCC'").fetchone() == (
        ANNOUNCEMENT_DEFAULTS["source"], ANNOUNCEMENT_DEFAULTS["confidence"], ANNOUNCEMENT_DEFAULTS["needs_review"])
    assert conn.execute("SELECT notes FROM reverse_splits WHERE ticker='DDD'").fetchone()[0] == "accession=000100000026000004 form=6-K"
    assert conn.execute("SELECT name FROM issuers WHERE cik='0000000003'").fetchone()[0] == "Gamma Ltd"
    finra_src = sqlite3.connect(str(src)).execute("SELECT * FROM finra_short_interest ORDER BY ticker").fetchall()
    assert conn.execute("SELECT * FROM finra_short_interest ORDER BY ticker").fetchall() == finra_src
    runs_src = {r[0]: (r[1], r[2], json.loads(r[3]), json.loads(r[4]) if r[4] else None, json.loads(r[5]) if r[5] else None)
                for r in sqlite3.connect(str(src)).execute("SELECT id, created_at, label, config_json, analysis_json, source_manifest_json FROM book_runs")}
    runs_dst = {r[0]: (r[1], r[2], json.loads(r[3]), json.loads(r[4]) if r[4] else None, json.loads(r[5]) if r[5] else None)
                for r in conn.execute("SELECT id, created_at, label, config_json, analysis_json, source_manifest_json FROM book_runs")}
    assert runs_src == runs_dst
    assert set(conn.execute("SELECT run_id, stage, n FROM book_funnel")) == {(1, "events", 5), (1, "taken", 0), (2, "evidence_pool", 2), (2, "taken", 1), (3, "taken", 4)}
    conn.close()
    original = sqlite3.connect(str(dec)).execute("SELECT id, recorded_at, ticker, payload, previous_hash, record_hash FROM decisions ORDER BY rowid").fetchall()
    rebuilt = sqlite3.connect(str(dst_dec)).execute("SELECT id, recorded_at, ticker, payload, previous_hash, record_hash FROM decisions ORDER BY rowid").fetchall()
    assert original == rebuilt


def test_import_is_idempotent_and_re_export_is_byte_stable(exported, tmp_path):
    _, _, out, _ = exported
    dst, dst_dec = tmp_path / "dst.db", tmp_path / "dst_dec.sqlite"
    import_ledger(out, dst, dst_dec)
    second = import_ledger(out, dst, dst_dec)
    assert second["decisions"] == 0  # already present
    conn = sqlite3.connect(str(dst))
    assert conn.execute("SELECT COUNT(*) FROM reverse_splits").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM book_funnel").fetchone()[0] == 5
    conn.close()
    again = tmp_path / "ledger2"
    export_ledger(dst, again, dst_dec, today=date(2026, 10, 11))
    for name in ("events", "announcements", "finra_short_interest", "book_runs", "book_source_manifests", "decisions"):
        assert ledger_paths(again)[name].read_bytes() == ledger_paths(out)[name].read_bytes(), name


def test_oversized_files_retain_older_history_in_shards(tmp_path):
    src, dec = tmp_path / "src.db", tmp_path / "dec.sqlite"
    seed_source(src, dec)
    manifest = export_ledger(src, tmp_path / "ledger", dec, cap_bytes=1024, today=date(2026, 10, 11))
    assert manifest["caps"]["announcements_since"] is None
    assert manifest["caps"]["finra_since"] is None
    assert manifest["caps"]["history_truncated"] is False
    rows = load_jsonl(ledger_paths(tmp_path / "ledger")["announcements"])
    assert sorted(r["ticker"] for r in rows) == ["CCC", "DDD", "EEE"]
    assert manifest["files"]["announcements"]["rows"] == 3
    assert manifest["files"]["finra_short_interest"]["rows"] == 3
    assert all(p["bytes"] <= 1024 for f in manifest["files"].values() for p in f.get("parts", []))


def test_notes_round_trip_in_the_collectors_field_order():
    assert parse_notes("accession=000121390022062538 form=8-K") == ("000121390022062538", "8-K")
    assert parse_notes("form=6-K accession=000121390026069474") == ("000121390026069474", "6-K")
    assert parse_notes(None) == (None, None)
    assert make_notes("announced_only", "A", "8-K") == "accession=A form=8-K"
    assert make_notes("edgar_candidate", "A", "8-K") == "form=8-K accession=A"
    assert make_notes("seeded", None, None) is None


def test_decision_chain_verification_catches_tampering_and_reordering():
    rows = decision_rows()
    assert verify_decision_chain(rows) == []
    tampered = json.loads(json.dumps(rows))
    tampered[0]["record"]["reason"] = "edited after the fact"
    errors = verify_decision_chain(tampered)
    assert any("record_hash does not match" in e for e in errors)
    # The next row links to the STORED hash, so a content-only edit is caught by the
    # content check alone; rewriting the stored hash to match the edit breaks the link.
    consistent = json.loads(json.dumps(tampered))
    consistent[0]["record"]["record_hash"] = record_hash(consistent[0]["record"])
    consistent[0]["record_hash"] = consistent[0]["record"]["record_hash"]
    assert any("previous_hash does not link" in e for e in verify_decision_chain(consistent))
    reordered = [rows[1], rows[0]]
    assert any("previous_hash does not link" in e for e in verify_decision_chain(reordered))
    bad_state = json.loads(json.dumps(rows))
    bad_state[1]["record"]["decision"] = "executed"
    bad_state[1]["record"]["record_hash"] = record_hash(bad_state[1]["record"])
    bad_state[1]["record_hash"] = bad_state[1]["record"]["record_hash"]
    assert any("decision must be one of" in e for e in verify_decision_chain(bad_state))
    broken_import = json.loads(json.dumps(rows))
    broken_import[0]["ticker"] = "OTHER"
    assert any("ticker differs" in e for e in verify_decision_chain(broken_import))


def test_import_refuses_a_broken_decision_chain(tmp_path):
    rows = decision_rows()
    rows[1]["record"]["reason"] = "tampered"
    from reverse_splits.ledger import write_jsonl

    out = tmp_path / "ledger"
    write_jsonl(ledger_paths(out)["decisions"], rows)
    with pytest.raises(ValueError, match="failed verification"):
        import_ledger(out, tmp_path / "dst.db", tmp_path / "dst_dec.sqlite")
