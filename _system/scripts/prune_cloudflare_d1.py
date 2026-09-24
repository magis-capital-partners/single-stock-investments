#!/usr/bin/env python3
"""Bound high-frequency dashboard history after D1 efficiency migrations.

The portfolio publisher archives every raw payload in R2, while D1 serves the
current dashboard and its daily NAV history.  Keeping every 30-second D1
snapshot duplicates the archive and can fill a free-tier database quickly.

Deploy applies pending migrations first (CREATE INDEX / DROP TABLE), then this
script. Retention without received_at / as_of indexes full-scans and can burn
the free-tier row-read quota before indexes ever land. Every delete is batched
so D1 does not have to rewrite a large table in one statement.

Nonce tables (portfolio / sleeve / market-risk) are pruned here only — ingest
handlers must not DELETE on the hot path.

Retention runs ONCE per UTC day. It used to run on every deploy (up to 20 a
day), which re-ran the portfolio ranking scans each time for a few dozen rows.
The date of the last completed pass lives in ops_state (``prune:last_date``,
migration 0019); a pass that fails or hits the daily quota does not record it,
so the next deploy retries. Every statement's rows_read / rows_written come
from D1's own result meta and are printed, with a machine-readable total on
the last line (``D1_METRICS {...}``) for the deploy summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


Execute = Callable[[str], int]

LAST_PRUNE_KEY = "prune:last_date"
QUOTA_EXIT_CODE = 75  # EX_TEMPFAIL: the daily free-tier quota, retried after 00:00 UTC
# The quota's own words, and nothing else. D1 reports EVERY query error as
# code 7500 ("no such table: ...: SQLITE_ERROR [code: 7500]"), so matching the
# code would turn a retention SQL bug into a daily "deferral" forever.
QUOTA_PATTERN = re.compile(r"exceeded D1's free tier daily row (read|write) limit", re.IGNORECASE)

PORTFOLIO_REFERENCES = (
    "portfolio_reconciliation_breaks",
    "portfolio_strategy_snapshots",
    "portfolio_allocation_projections",
    "portfolio_flex_sessions",
)

# These tables are useful as bounded history, not as an indefinite event log.
# Portfolio NAV is handled separately because it needs daily downsampling.
DEFAULT_TIME_POLICIES = (
    ("criticality_snapshots", "as_of", 14),
    ("flow_stress_snapshots", "as_of", 14),
    ("market_risk_component_snapshots", "as_of", 14),
    ("market_risk_ingest_runs", "received_at", 30),
    ("market_risk_ingest_nonces", "received_at", 2),
    ("portfolio_ingest_nonces", "received_at", 2),
    ("sleeve_ingest_nonces", "received_at", 2),
    # Resolved alerts only: open alerts have closed_at NULL, which never
    # compares below the cutoff. Seeks on idx_market_risk_alerts_open, which
    # leads with closed_at (0005).
    ("market_risk_alerts", "closed_at", 30),
    ("sleeve_classifier_audit", "as_of", 90),
    ("sleeve_marks", "as_of", 400),
    ("price_observations", "observed_on", 3650),
    ("ohlcv_observations", "observed_on", 3650),
    ("technical_snapshots", "as_of_date", 3650),
    ("capitulation_snapshots", "as_of_date", 3650),
    ("market_context_snapshots", "as_of_date", 3650),
    ("market_structure_snapshots", "as_of_date", 3650),
)

LATEST_REF_GUARDS = {
    "criticality_snapshots": """NOT EXISTS (
      SELECT 1 FROM market_risk_latest_refs latest
      WHERE latest.series='criticality'
        AND latest.scope=criticality_snapshots.scope
        AND latest.symbol=criticality_snapshots.symbol
        AND latest.qualifier=criticality_snapshots.horizon
        AND latest.as_of=criticality_snapshots.as_of
        AND latest.model_version=criticality_snapshots.model_version
    )""",
    "flow_stress_snapshots": """NOT EXISTS (
      SELECT 1 FROM market_risk_latest_refs latest
      WHERE latest.series='flow'
        AND latest.scope=flow_stress_snapshots.scope
        AND latest.symbol=flow_stress_snapshots.symbol
        AND latest.as_of=flow_stress_snapshots.as_of
        AND latest.model_version=flow_stress_snapshots.model_version
    )""",
    "market_risk_component_snapshots": """NOT EXISTS (
      SELECT 1 FROM market_risk_latest_refs latest
      WHERE latest.series='component'
        AND latest.scope=market_risk_component_snapshots.scope
        AND latest.symbol=market_risk_component_snapshots.symbol
        AND latest.qualifier=market_risk_component_snapshots.component
        AND latest.as_of=market_risk_component_snapshots.as_of
        AND latest.model_version=market_risk_component_snapshots.model_version
        AND latest.source=market_risk_component_snapshots.source
    )""",
}


def table_names(connection: sqlite3.Connection) -> set[str]:
    """Return SQLite table names; kept small so policy tests use real SQL."""
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _portfolio_candidates(batch_size: int) -> str:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    return f"""
WITH ibkr_ranked AS (
  SELECT source_run_id,
         ROW_NUMBER() OVER (
           PARTITION BY COALESCE(account_alias, ''), date(as_of)
           ORDER BY as_of DESC, received_at DESC, source_run_id DESC
         ) AS keep_rank
  FROM portfolio_source_runs
  WHERE source = 'ibkr' AND complete = 1 AND date(as_of) < date('now')
), other_ranked AS (
  SELECT source_run_id,
         ROW_NUMBER() OVER (
           PARTITION BY source, COALESCE(account_alias, '')
           ORDER BY as_of DESC, received_at DESC, source_run_id DESC
         ) AS keep_rank
  FROM portfolio_source_runs
  WHERE source NOT IN ('ibkr', 'ibkr_flex')
), candidates AS (
  SELECT source_run_id FROM ibkr_ranked WHERE keep_rank > 1
  UNION
  SELECT source_run_id FROM other_ranked WHERE keep_rank > 1
  UNION
  SELECT source_run_id FROM portfolio_source_runs
   WHERE complete = 0 AND received_at < datetime('now', '-1 day')
), batch AS (
  SELECT source_run_id FROM candidates LIMIT {int(batch_size)}
)
""".strip()


def prune_portfolio_history(
    execute: Execute,
    existing_tables: set[str],
    *,
    batch_size: int = 100,
    max_batches: int = 10_000,
) -> int:
    """Keep today's IBKR detail, one close per prior day, and latest producers."""
    if "portfolio_source_runs" not in existing_tables:
        return 0
    cte = _portfolio_candidates(batch_size)
    total = 0
    for _ in range(max_batches):
        # These foreign keys intentionally pre-date ON DELETE CASCADE. Remove
        # their rows before the source run; account/position/order rows cascade.
        for table in PORTFOLIO_REFERENCES:
            if table in existing_tables:
                execute(
                    f"{cte}\nDELETE FROM {table} "
                    "WHERE source_run_id IN (SELECT source_run_id FROM batch)"
                )
        changed = execute(
            f"{cte}\nDELETE FROM portfolio_source_runs "
            "WHERE source_run_id IN (SELECT source_run_id FROM batch)"
        )
        total += changed
        if changed == 0:
            return total
    raise RuntimeError("portfolio retention exceeded the safety batch limit")


def prune_time_series(
    execute: Execute,
    existing_tables: set[str],
    *,
    batch_size: int = 1_000,
    max_batches: int = 10_000,
    policies: Iterable[tuple[str, str, int]] = DEFAULT_TIME_POLICIES,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for table, column, days in policies:
        if table not in existing_tables:
            continue
        guard = ""
        if "market_risk_latest_refs" in existing_tables and table in LATEST_REF_GUARDS:
            guard = f" AND {LATEST_REF_GUARDS[table]}"
        total = 0
        for _ in range(max_batches):
            changed = execute(
                f"DELETE FROM {table} WHERE rowid IN ("
                f"SELECT rowid FROM {table} "
                f"WHERE {column} < datetime('now', '-{int(days)} days'){guard} "
                f"LIMIT {int(batch_size)})"
            )
            total += changed
            if changed == 0:
                break
        else:
            raise RuntimeError(f"{table} retention exceeded the safety batch limit")
        totals[table] = total
    return totals


def _decode_json(output: str) -> Any:
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError("Wrangler did not return JSON")


def _statements(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
        return [payload]
    return []


def _statement_label(sql: str) -> str:
    match = re.search(r"\b(DELETE FROM|INSERT INTO|UPDATE|FROM)\s+(\w+)", sql)
    return match.group(2) if match else "query"


class StatementMetrics:
    """rows_read / rows_written per statement, as D1 reports them."""

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout
        self.statements = 0
        self.rows_read = 0
        self.rows_written = 0
        self.changes = 0

    def record(self, sql: str, results: list[dict[str, Any]]) -> None:
        for statement in results:
            meta = statement.get("meta") or {}
            rows_read = int(meta.get("rows_read") or 0)
            rows_written = int(meta.get("rows_written") or 0)
            changes = int(meta.get("changes") or 0)
            self.statements += 1
            self.rows_read += rows_read
            self.rows_written += rows_written
            self.changes += changes
            print(
                f"D1 statement {self.statements}: {_statement_label(sql)} "
                f"rows_read={rows_read} rows_written={rows_written} changes={changes}",
                file=self.stream,
            )

    def as_dict(self) -> dict[str, int]:
        return {
            "statements": self.statements,
            "rows_read": self.rows_read,
            "rows_written": self.rows_written,
            "changes": self.changes,
        }


class WranglerD1:
    def __init__(self, wrangler: Path, database: str, config: Path, metrics: StatementMetrics | None = None):
        self.wrangler = str(wrangler)
        self.database = database
        self.config = str(config)
        self.metrics = metrics if metrics is not None else StatementMetrics()

    def query(self, sql: str) -> list[dict[str, Any]]:
        command = [
            self.wrangler,
            "d1",
            "execute",
            self.database,
            "--remote",
            "--yes",
            "--command",
            sql,
            "--config",
            self.config,
            "--json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[-2_000:]
            raise RuntimeError(f"Wrangler D1 command failed: {detail}")
        statements = _statements(_decode_json(result.stdout))
        self.metrics.record(sql, statements)
        return statements

    def execute(self, sql: str) -> int:
        return sum(int(row.get("meta", {}).get("changes", 0)) for row in self.query(sql))

    def rows(self, sql: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for statement in self.query(sql):
            result = statement.get("results", [])
            if isinstance(result, list):
                out.extend(row for row in result if isinstance(row, dict))
        return out

    def tables(self) -> set[str]:
        return {
            str(row["name"])
            for row in self.rows("SELECT name FROM sqlite_master WHERE type='table'")
            if row.get("name")
        }


def last_prune_date(rows: Callable[[str], list[dict[str, Any]]]) -> str | None:
    """The UTC date of the last completed pass, or None (no row / no table)."""
    try:
        found = rows(f"SELECT value FROM ops_state WHERE key = '{LAST_PRUNE_KEY}'")
    except RuntimeError as error:
        if "no such table" in str(error).lower():
            return None
        raise
    return str(found[0].get("value")) if found else None


def record_prune_date(execute: Execute, today: str, now: str) -> None:
    execute(
        "INSERT INTO ops_state (key, value, updated_at) "
        f"VALUES ('{LAST_PRUNE_KEY}', '{today}', '{now}') "
        "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at"
    )


def run_retention(
    client: Any,
    *,
    today: str,
    now: str,
    force: bool = False,
    batch_size: int = 1_000,
) -> dict[str, Any]:
    """One daily pass. Returns what it did; raises on a D1 failure."""
    if not force and last_prune_date(client.rows) == today:
        return {"status": "skipped", "reason": f"already ran on {today} (UTC)", "deleted": 0}
    tables = client.tables()
    if not tables:
        return {"status": "skipped", "reason": "new database; nothing to prune", "deleted": 0}
    portfolio_deleted = prune_portfolio_history(
        client.execute,
        tables,
        batch_size=max(1, min(batch_size, 250)),
    )
    time_deleted = prune_time_series(client.execute, tables, batch_size=max(1, batch_size))
    if "ops_state" in tables:
        record_prune_date(client.execute, today, now)
    return {
        "status": "ran",
        "deleted": portfolio_deleted + sum(time_deleted.values()),
        "portfolio_source_runs": portfolio_deleted,
        "tables": {table: count for table, count in time_deleted.items() if count},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wrangler",
        type=Path,
        default=Path("dashboard/cloudflare/node_modules/.bin/wrangler"),
    )
    parser.add_argument("--database", default="DB")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument(
        "--force",
        action="store_true",
        help="run even when today's pass is already recorded in ops_state",
    )
    args = parser.parse_args(argv)

    moment = datetime.now(timezone.utc)
    client = WranglerD1(args.wrangler, args.database, args.config)
    outcome: dict[str, Any] = {"status": "failed"}
    code = 0
    try:
        outcome = run_retention(
            client,
            today=moment.strftime("%Y-%m-%d"),
            now=moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            force=args.force,
            batch_size=args.batch_size,
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        quota = bool(QUOTA_PATTERN.search(str(error)))
        outcome = {"status": "quota" if quota else "failed", "error": str(error)[-300:]}
        code = QUOTA_EXIT_CODE if quota else 1
    if outcome.get("status") == "ran":
        details = ", ".join(f"{table}={count}" for table, count in outcome["tables"].items())
        suffix = f" ({details})" if details else ""
        print(
            f"D1 retention removed {outcome['deleted']} rows; "
            f"portfolio_source_runs={outcome['portfolio_source_runs']}{suffix}."
        )
    elif outcome.get("status") == "skipped":
        print(f"D1 retention skipped: {outcome['reason']}.")
    metrics = {"stage": "retention", **outcome, **client.metrics.as_dict()}
    metrics.pop("error", None)
    print("D1_METRICS " + json.dumps(metrics, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
