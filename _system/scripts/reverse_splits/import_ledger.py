"""Rebuild the local SQLite research database from the committed JSONL ledger.

Creates the schema when the database is absent and upserts every ledger row,
so a clean clone can run the weekly collectors against a populated universe.
Prices, EDGAR hits and control samples are not in the ledger; the collectors
refetch them (``prices``, ``seed``, ``controls``). The decision journal is
rebuilt in its own SQLite file with the original canonical payloads, so the
hash chain verifies byte for byte.

    python -m _system.scripts.reverse_splits.import_ledger [--ledger-dir DIR] [--db PATH] [--replace]
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .config import load_config
from .db import init_db
from .ledger import (
    ANNOUNCEMENT_DEFAULTS,
    EVENT_FIELDS,
    FINRA_FIELDS,
    canonical,
    ledger_paths,
    load_jsonl,
    make_notes,
    verify_decision_chain,
)

_EVENT_COLUMNS = [f for f in EVENT_FIELDS if f not in {"company", "accession", "form"}] + ["notes"]


def _upsert_issuers(conn: sqlite3.Connection, rows: list[dict]) -> int:
    n = 0
    for row in rows:
        cik, name = row.get("cik"), row.get("company")
        if not cik or not name:
            continue
        conn.execute(
            """
            INSERT INTO issuers (cik, name, primary_ticker, exchange_class)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cik) DO UPDATE SET
                name = COALESCE(excluded.name, issuers.name),
                primary_ticker = COALESCE(issuers.primary_ticker, excluded.primary_ticker),
                exchange_class = CASE
                    WHEN excluded.exchange_class != 'unknown' THEN excluded.exchange_class
                    ELSE issuers.exchange_class
                END,
                updated_at = datetime('now')
            """,
            (cik, name, row.get("ticker"), row.get("exchange_class") or "unknown"),
        )
        n += 1
    return n


def _upsert_split(conn: sqlite3.Connection, values: dict) -> None:
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in {"ticker", "ex_date", "split_from", "split_to"})
    conn.execute(
        f"INSERT INTO reverse_splits ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(ticker, ex_date, split_from, split_to) DO UPDATE SET {updates}",
        [values[c] for c in columns],
    )


def _event_values(row: dict) -> dict:
    values = {c: row.get(c) for c in _EVENT_COLUMNS if c != "notes"}
    values["notes"] = make_notes(row.get("status"), row.get("accession"), row.get("form"))
    values["exchange_class"] = values.get("exchange_class") or "unknown"
    values["status"] = values.get("status") or "seeded"
    values["outcome"] = values.get("outcome") or "effective"
    values["source"] = values.get("source") or "unknown"
    return values


def _announcement_values(row: dict) -> dict:
    announce = row.get("announce_date")
    values = {
        "ticker": row.get("ticker"),
        "cik": row.get("cik"),
        "exchange": row.get("exchange"),
        "exchange_class": row.get("exchange_class") or "unknown",
        "split_from": 1.0,
        "split_to": 1.0,
        "ratio": 1.0,
        "first_proxy_date": row.get("first_proxy_date"),
        "announce_date": announce,
        "vote_date": None,
        "ratio_set_date": None,
        "effective_date": row.get("ex_date") or announce,
        "ex_date": row.get("ex_date") or announce,
        "prior_rs_count": 0,
        "cohort": None,
        "status": "announced_only",
        "confidence": row.get("confidence") if row.get("confidence") is not None else ANNOUNCEMENT_DEFAULTS["confidence"],
        "needs_review": row.get("needs_review") if row.get("needs_review") is not None else ANNOUNCEMENT_DEFAULTS["needs_review"],
        "source": row.get("source") or ANNOUNCEMENT_DEFAULTS["source"],
        "outcome": row.get("outcome") or "announced_only",
        "vote_path": row.get("vote_path"),
        "accept_time": row.get("accept_time"),
        "announced_ex_date": row.get("announced_ex_date"),
        "announced_ratio": row.get("announced_ratio"),
        "jump_status": None,
        "jump_observed": None,
        "date_quality": row.get("date_quality"),
        "notes": make_notes("announced_only", row.get("accession"), row.get("form")),
    }
    # created_at / updated_at are not in the ledger for announcements; SQLite stamps them.
    return values


def _import_book_runs(conn: sqlite3.Connection, runs: list[dict], manifests: list[dict]) -> int:
    by_hash = {m.get("sha256"): m.get("manifest") for m in manifests}
    n = 0
    for run in runs:
        manifest = by_hash.get(run.get("source_manifest_sha256"))
        conn.execute(
            """
            INSERT INTO book_runs (id, created_at, label, config_json, analysis_json, source_manifest_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                created_at = excluded.created_at, label = excluded.label, config_json = excluded.config_json,
                analysis_json = excluded.analysis_json, source_manifest_json = excluded.source_manifest_json
            """,
            (
                int(run["id"]),
                run.get("created_at"),
                run.get("label"),
                canonical(run.get("config")) if run.get("config") is not None else None,
                canonical(run.get("analysis")) if run.get("analysis") is not None else None,
                canonical(manifest) if manifest is not None else None,
            ),
        )
        conn.execute("DELETE FROM book_funnel WHERE run_id=?", (int(run["id"]),))
        for stage in run.get("funnel") or []:
            conn.execute(
                "INSERT OR REPLACE INTO book_funnel (run_id, stage, n) VALUES (?, ?, ?)",
                (int(run["id"]), stage.get("stage"), stage.get("n")),
            )
        n += 1
    return n


def _import_decisions(path: Path, rows: list[dict]) -> int:
    errors = verify_decision_chain(rows)
    if errors:
        raise ValueError("decisions ledger failed verification: " + "; ".join(errors[:3]))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, ticker TEXT NOT NULL, "
            "payload TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)"
        )
        existing = {r[0] for r in conn.execute("SELECT id FROM decisions")}
        n = 0
        for row in rows:
            if row["id"] in existing:
                continue
            conn.execute(
                "INSERT INTO decisions VALUES (?,?,?,?,?,?)",
                (row["id"], row["recorded_at"], row["ticker"], canonical(row["record"]), row["previous_hash"], row["record_hash"]),
            )
            n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def import_ledger(ledger_dir: Path, db_path: Path, decisions_db: Path | None = None, *, replace: bool = False) -> dict:
    paths = ledger_paths(ledger_dir)
    events = load_jsonl(paths["events"])
    announcements = load_jsonl(paths["announcements"])
    finra = load_jsonl(paths["finra_short_interest"])
    runs = load_jsonl(paths["book_runs"])
    manifests = load_jsonl(paths["book_source_manifests"])
    decisions = load_jsonl(paths["decisions"])

    conn = init_db(Path(db_path))
    try:
        if replace:
            conn.execute("DELETE FROM reverse_splits")
            conn.execute("DELETE FROM finra_short_interest")
            conn.execute("DELETE FROM book_funnel")
            conn.execute("DELETE FROM book_runs")
        issuers = _upsert_issuers(conn, events + announcements)
        for row in events:
            _upsert_split(conn, _event_values(row))
        for row in announcements:
            _upsert_split(conn, _announcement_values(row))
        for row in finra:
            conn.execute(
                """
                INSERT INTO finra_short_interest (ticker, settlement_date, short_interest, avg_daily_volume, days_to_cover, source_file)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, settlement_date) DO UPDATE SET
                    short_interest=excluded.short_interest, avg_daily_volume=excluded.avg_daily_volume,
                    days_to_cover=excluded.days_to_cover, source_file=excluded.source_file
                """,
                [row.get(k) for k in FINRA_FIELDS],
            )
        book_runs = _import_book_runs(conn, runs, manifests)
        conn.commit()
    finally:
        conn.close()
    imported_decisions = _import_decisions(decisions_db, decisions) if decisions_db is not None and decisions else 0
    return {
        "events": len(events),
        "announcements": len(announcements),
        "finra_short_interest": len(finra),
        "book_runs": book_runs,
        "issuers": issuers,
        "decisions": imported_decisions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--ledger-dir", type=Path, default=None, help="ledger directory (default: config ledger_dir)")
    parser.add_argument("--db", type=Path, default=None, help="SQLite research database to write (default: config db_path)")
    parser.add_argument("--decisions-db", type=Path, default=None, help="decision journal SQLite to write (default: config)")
    parser.add_argument("--replace", action="store_true", help="clear the ledger-backed tables before importing")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    counts = import_ledger(
        args.ledger_dir or cfg.ledger_dir,
        args.db or cfg.db_path,
        args.decisions_db or cfg.decisions_db_path,
        replace=args.replace,
    )
    print(" ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
