"""Export the local SQLite research database to the committed JSONL ledger.

Reads the database read-only. Writes ``events.jsonl``, ``announcements.jsonl``,
``finra_short_interest.jsonl``, ``book_runs.jsonl``,
``book_source_manifests.jsonl``, ``decisions.jsonl`` and ``ledger_manifest.json``
under the ledger directory. Tables that are reproducible from public sources or
too large for git (``prices_daily``, ``edgar_hits``, ``control_prices``,
``book_trades``, ``book_equity``, ``issuers``) are not exported; issuer names
travel denormalised on the event and announcement rows.

A file that would exceed ``MAX_FILE_BYTES`` is capped to rows dated within
``CAP_YEARS`` years and the cap is recorded in the manifest.

    python -m _system.scripts.reverse_splits.export_ledger [--db PATH] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from .config import load_config
from .ledger import (
    ANNOUNCEMENT_FIELDS,
    CAP_YEARS,
    EVENT_FIELDS,
    FINRA_FIELDS,
    MAX_FILE_BYTES,
    SCHEMA_VERSION,
    canonical,
    dumps_row,
    ledger_paths,
    parse_notes,
    sha256_file,
    utc_now,
    verify_decision_chain,
    write_json,
    write_jsonl,
)
from .utils import years_ago


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _event_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.*, i.name AS company
        FROM reverse_splits s LEFT JOIN issuers i ON i.cik = s.cik
        WHERE COALESCE(s.status, '') != 'announced_only'
        ORDER BY s.ex_date, s.ticker, s.split_from, s.split_to
        """
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        accession, form = parse_notes(item.get("notes"))
        item["accession"], item["form"] = accession, form
        out.append({k: item.get(k) for k in EVENT_FIELDS})
    return out


def _announcement_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.*, i.name AS company
        FROM reverse_splits s LEFT JOIN issuers i ON i.cik = s.cik
        WHERE s.status = 'announced_only'
        ORDER BY s.announce_date, s.ticker, s.notes
        """
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        accession, form = parse_notes(item.get("notes"))
        item["accession"], item["form"] = accession, form
        out.append({k: item.get(k) for k in ANNOUNCEMENT_FIELDS})
    return out


def _finra_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM finra_short_interest ORDER BY settlement_date, ticker"
    ).fetchall()
    return [{k: dict(row).get(k) for k in FINRA_FIELDS} for row in rows]


def _loads(text):
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _book_rows(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    import hashlib

    columns = {row[1] for row in conn.execute("PRAGMA table_info(book_runs)")}
    runs = conn.execute("SELECT * FROM book_runs ORDER BY id").fetchall()
    funnel: dict[int, list[dict]] = {}
    for row in conn.execute("SELECT run_id, stage, n FROM book_funnel ORDER BY run_id, rowid"):
        funnel.setdefault(int(row["run_id"]), []).append({"stage": row["stage"], "n": row["n"]})
    manifests: dict[str, dict] = {}
    out = []
    for row in runs:
        item = dict(row)
        manifest = _loads(item.get("source_manifest_json")) if "source_manifest_json" in columns else None
        digest = None
        if manifest is not None:
            digest = hashlib.sha256(canonical(manifest).encode()).hexdigest()
            manifests.setdefault(digest, {"sha256": digest, "manifest": manifest})
        out.append(
            {
                "id": int(item["id"]),
                "created_at": item.get("created_at"),
                "label": item.get("label"),
                "config": _loads(item.get("config_json")),
                "analysis": _loads(item.get("analysis_json")) if "analysis_json" in columns else None,
                "funnel": funnel.get(int(item["id"]), []),
                "source_manifest_sha256": digest,
            }
        )
    return out, [manifests[k] for k in sorted(manifests)]


def _decision_rows(path: Path | None) -> list[dict]:
    if path is None or not Path(path).exists():
        return []
    conn = _connect_ro(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "decisions" not in tables:
            return []
        rows = conn.execute(
            "SELECT id, recorded_at, ticker, payload, previous_hash, record_hash FROM decisions ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        record = json.loads(row["payload"])
        out.append(
            {
                "id": row["id"],
                "recorded_at": row["recorded_at"],
                "ticker": row["ticker"],
                "previous_hash": row["previous_hash"],
                "record_hash": row["record_hash"],
                "record": record,
            }
        )
    return out


def _cap(rows: list[dict], field: str, *, cap_bytes: int, cap_years: int, today: date | None = None, sparse: bool = False) -> tuple[list[dict], str | None]:
    """Keep rows dated within ``cap_years`` when the serialised file exceeds ``cap_bytes``."""
    size = sum(len(dumps_row(r, sparse=sparse).encode("utf-8")) + 1 for r in rows)
    if size <= cap_bytes:
        return rows, None
    since = years_ago(cap_years, today).isoformat()
    kept = [r for r in rows if str(r.get(field) or "") >= since]
    return kept, since


def export_ledger(
    db_path: Path,
    ledger_dir: Path,
    decisions_db: Path | None = None,
    *,
    cap_bytes: int = MAX_FILE_BYTES,
    cap_years: int = CAP_YEARS,
    today: date | None = None,
) -> dict:
    paths = ledger_paths(ledger_dir)
    conn = _connect_ro(db_path)
    try:
        events = _event_rows(conn)
        announcements = _announcement_rows(conn)
        finra = _finra_rows(conn)
        book_runs, manifests = _book_rows(conn)
    finally:
        conn.close()
    decisions = _decision_rows(decisions_db)
    chain_errors = verify_decision_chain(decisions)

    announcements, ann_since = _cap(announcements, "announce_date", cap_bytes=cap_bytes, cap_years=cap_years, today=today, sparse=True)
    finra, finra_since = _cap(finra, "settlement_date", cap_bytes=cap_bytes, cap_years=cap_years, today=today, sparse=True)

    written = {
        "events": write_jsonl(paths["events"], events),
        "announcements": write_jsonl(paths["announcements"], announcements, sparse=True),
        "finra_short_interest": write_jsonl(paths["finra_short_interest"], finra, sparse=True),
        "book_runs": write_jsonl(paths["book_runs"], book_runs),
        "book_source_manifests": write_jsonl(paths["book_source_manifests"], manifests),
        "decisions": write_jsonl(paths["decisions"], decisions),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": utc_now(),
        "source_db": Path(db_path).name,
        "files": {
            name: {"rows": rows, "bytes": size, "sha256": sha256_file(paths[name])}
            for name, (rows, size) in written.items()
        },
        "caps": {
            "max_file_bytes": cap_bytes,
            "cap_years": cap_years,
            "announcements_since": ann_since,
            "finra_since": finra_since,
        },
        "decisions_chain_valid": not chain_errors,
        "decisions_chain_errors": chain_errors,
        "not_exported": ["prices_daily", "edgar_hits", "control_prices", "book_trades", "book_equity", "issuers", "filings", "borrow_snapshots", "backtest_runs", "backtest_trades"],
    }
    write_json(paths["manifest"], manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None, help="SQLite research database (default: config db_path)")
    parser.add_argument("--decisions-db", type=Path, default=None, help="decision journal SQLite (default: config)")
    parser.add_argument("--out", type=Path, default=None, help="ledger directory (default: config ledger_dir)")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    db = args.db or cfg.db_path
    if not Path(db).exists():
        print(f"no database at {db}; nothing exported")
        return 1
    manifest = export_ledger(db, args.out or cfg.ledger_dir, args.decisions_db or cfg.decisions_db_path)
    for name, info in manifest["files"].items():
        print(f"{name:24s} rows={info['rows']:>6} bytes={info['bytes']:>10,}")
    caps = manifest["caps"]
    if caps["announcements_since"] or caps["finra_since"]:
        print(f"caps applied: announcements_since={caps['announcements_since']} finra_since={caps['finra_since']}")
    if not manifest["decisions_chain_valid"]:
        for err in manifest["decisions_chain_errors"]:
            print(f"ERROR {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
