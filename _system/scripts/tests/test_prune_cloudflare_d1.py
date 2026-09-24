import importlib.util
import io
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "dashboard/cloudflare/migrations"

# Verbatim wrangler --json stderr from deploy run 36046368603 (2026-09-24),
# when the free-tier write quota was spent.
WRANGLER_QUOTA_ERROR = """{
  "error": {
    "text": "A request to the Cloudflare API (/accounts/***/d1/database/e8982743-9502-47f2-981b-9a4975c36a7e/query) failed.",
    "notes": [
      {
        "text": "Your account has exceeded D1's free tier daily row write limit. Upgrade to a paid plan or wait until tomorrow (midnight UTC) to continue. See https://developers.cloudflare.com/d1/platform/limits/ for more details. [code: 7500]"
      }
    ],
    "kind": "error",
    "name": "APIError",
    "code": 7500,
    "accountTag": "***"
  }
}"""

# The same envelope for an ordinary SQL error. D1 labels those code 7500 too,
# which is why "code": 7500 alone must never read as the quota.
WRANGLER_SQL_ERROR = """{
  "error": {
    "text": "A request to the Cloudflare API (/accounts/***/d1/database/e8982743-9502-47f2-981b-9a4975c36a7e/query) failed.",
    "notes": [
      {
        "text": "no such table: portfolio_strategy_snapshots: SQLITE_ERROR [code: 7500]"
      }
    ],
    "kind": "error",
    "name": "APIError",
    "code": 7500,
    "accountTag": "***"
  }
}"""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pruner = load_module(
    "prune_cloudflare_d1",
    ROOT / "_system" / "scripts" / "prune_cloudflare_d1.py",
)


def execute_on(connection: sqlite3.Connection):
    def execute(sql: str) -> int:
        connection.execute(sql)
        return connection.execute("SELECT changes()").fetchone()[0]

    return execute


def test_portfolio_prune_keeps_latest_daily_and_current_intraday_snapshots():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (ROOT / "dashboard/cloudflare/migrations/0008_portfolio_hub.sql").read_text(
            encoding="utf-8"
        )
    )
    connection.execute("PRAGMA foreign_keys = ON")
    rows = [
        ("old-1", "ibkr", "acct", "2020-01-02T10:00:00Z", 1),
        ("old-2", "ibkr", "acct", "2020-01-02T16:00:00Z", 1),
        ("today-1", "ibkr", "acct", "2999-01-02T10:00:00Z", 1),
        ("today-2", "ibkr", "acct", "2999-01-02T16:00:00Z", 1),
        ("strategy-1", "risk-engine", None, "2020-01-02T10:00:00Z", 1),
        ("strategy-2", "risk-engine", None, "2020-01-02T11:00:00Z", 1),
        ("flex-1", "ibkr_flex", "acct", "2020-01-02T23:59:00Z", 1),
        ("flex-2", "ibkr_flex", "acct", "2020-01-03T23:59:00Z", 1),
    ]
    connection.executemany(
        """INSERT INTO portfolio_source_runs
        (source_run_id,schema_version,source,account_alias,as_of,complete,
         completeness_json,content_sha256,object_key,received_at)
        VALUES (?, 'test.v1', ?, ?, ?, ?, '{}', 'sha', 'r2/key', ?)""",
        [(*row, row[3]) for row in rows],
    )
    connection.executemany(
        """INSERT INTO portfolio_account_values
        (source_run_id,tag,currency,segment,model_code,value_decimal,source,as_of)
        VALUES (?, 'NetLiquidation', 'USD', '', '', '100', 'ibkr', ?)""",
        [(row[0], row[3]) for row in rows if row[1] == "ibkr"],
    )
    connection.execute(
        """INSERT INTO portfolio_reconciliation_breaks
        (break_id,source_run_id,account_alias,break_type,severity,status,details_json,created_at)
        VALUES ('break-old','old-1','acct','test','low','open','{}','2020-01-02')"""
    )

    deleted = pruner.prune_portfolio_history(
        execute_on(connection), pruner.table_names(connection), batch_size=1
    )

    remaining = {
        row[0]
        for row in connection.execute(
            "SELECT source_run_id FROM portfolio_source_runs"
        ).fetchall()
    }
    assert deleted == 2
    assert remaining == {
        "old-2",
        "today-1",
        "today-2",
        "strategy-2",
        "flex-1",
        "flex-2",
    }
    assert connection.execute(
        "SELECT COUNT(*) FROM portfolio_reconciliation_breaks"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM portfolio_account_values"
    ).fetchone()[0] == 3


def test_time_retention_prunes_only_rows_older_than_policy():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE criticality_snapshots (as_of TEXT NOT NULL, payload_json TEXT)"
    )
    connection.executemany(
        "INSERT INTO criticality_snapshots VALUES (?, '{}')",
        [("2020-01-01T00:00:00Z",), ("2999-01-01T00:00:00Z",)],
    )

    changes = pruner.prune_time_series(
        execute_on(connection),
        {"criticality_snapshots"},
        batch_size=1,
        policies=(("criticality_snapshots", "as_of", 14),),
    )

    assert changes == {"criticality_snapshots": 1}
    assert connection.execute(
        "SELECT as_of FROM criticality_snapshots"
    ).fetchall() == [("2999-01-01T00:00:00Z",)]


def test_time_retention_preserves_stale_current_risk_snapshot():
    connection = sqlite3.connect(":memory:")
    migrations = ROOT / "dashboard/cloudflare/migrations"
    for name in (
        "0005_criticality_monitor.sql",
        "0006_market_risk_components.sql",
        "0008_portfolio_hub.sql",
        "0014_d1_read_efficiency.sql",
    ):
        connection.executescript((migrations / name).read_text(encoding="utf-8"))
    values = (
        "market", "SPY", "multi", "model", "none", 10, 0, 0, 0,
        0, 0, "source", "eod", "ready", "{}",
    )
    for date in ("2020-01-01", "2020-01-02"):
        connection.execute(
            """INSERT INTO criticality_snapshots
            (scope,symbol,as_of,horizon,model_version,direction,criticality_score,
             positive_confidence,negative_confidence,qualified_confidence,
             fit_count,qualified_count,source,entitlement_mode,quality_state,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values[:2] + (date,) + values[2:],
        )

    changes = pruner.prune_time_series(
        execute_on(connection),
        pruner.table_names(connection),
        policies=(("criticality_snapshots", "as_of", 14),),
    )

    assert changes == {"criticality_snapshots": 1}
    assert connection.execute(
        "SELECT as_of FROM criticality_snapshots"
    ).fetchall() == [("2020-01-02",)]


class SqliteD1:
    """The WranglerD1 surface run_retention uses, backed by local SQLite.
    Errors surface as RuntimeError, the way a failed wrangler call does."""

    def __init__(self, connection: sqlite3.Connection, fail_on: str | None = None):
        self.connection = connection
        self.fail_on = fail_on
        self.executed: list[str] = []
        self.metrics = pruner.StatementMetrics(stream=io.StringIO())

    def rows(self, sql: str):
        try:
            cursor = self.connection.execute(sql)
        except sqlite3.Error as error:
            raise RuntimeError(f"Wrangler D1 command failed: {error}") from error
        columns = [column[0] for column in cursor.description or []]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql: str) -> int:
        self.executed.append(sql)
        if self.fail_on and self.fail_on in sql:
            # What WranglerD1.query raises for the recorded quota response.
            raise RuntimeError(f"Wrangler D1 command failed: {WRANGLER_QUOTA_ERROR}")
        self.connection.execute(sql)
        return self.connection.execute("SELECT changes()").fetchone()[0]

    def tables(self) -> set[str]:
        return pruner.table_names(self.connection)


def _database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    for name in (
        "0005_criticality_monitor.sql",
        "0006_market_risk_components.sql",
        "0007_sleeves.sql",
        "0008_portfolio_hub.sql",
        "0014_d1_read_efficiency.sql",
        "0016_bound_remaining_row_scans.sql",
    ):
        connection.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
    # 0019 also indexes seed tables absent here; retention only needs ops_state.
    ops_state = (MIGRATIONS / "0019_seed_state_and_gc_indexes.sql").read_text(encoding="utf-8")
    connection.executescript(ops_state.split("CREATE INDEX", 1)[0])
    connection.execute(
        "INSERT INTO portfolio_ingest_nonces (nonce, received_at) VALUES ('old', '2020-01-01T00:00:00Z')"
    )
    return connection


def _deletes(client: SqliteD1) -> int:
    return sum("DELETE FROM" in sql for sql in client.executed)


def test_retention_runs_once_per_utc_day():
    connection = _database()
    client = SqliteD1(connection)

    first = pruner.run_retention(client, today="2026-09-25", now="2026-09-25T04:00:00Z")
    assert first["status"] == "ran"
    assert first["tables"] == {"portfolio_ingest_nonces": 1}
    assert connection.execute(
        "SELECT value FROM ops_state WHERE key = 'prune:last_date'"
    ).fetchone() == ("2026-09-25",)

    deletes = _deletes(client)
    again = pruner.run_retention(client, today="2026-09-25", now="2026-09-25T18:00:00Z")
    assert again["status"] == "skipped"
    assert _deletes(client) == deletes  # the second deploy of the day deletes nothing

    assert pruner.run_retention(client, today="2026-09-26", now="2026-09-26T00:20:00Z")["status"] == "ran"
    forced = pruner.run_retention(client, today="2026-09-26", now="2026-09-26T01:00:00Z", force=True)
    assert forced["status"] == "ran"


def test_a_pass_stopped_by_the_quota_is_retried_by_the_next_deploy():
    connection = _database()
    client = SqliteD1(connection, fail_on="DELETE FROM portfolio_ingest_nonces")
    with pytest.raises(RuntimeError, match="free tier daily row write limit"):
        pruner.run_retention(client, today="2026-09-25", now="2026-09-25T04:00:00Z")
    assert connection.execute(
        "SELECT COUNT(*) FROM ops_state WHERE key = 'prune:last_date'"
    ).fetchone() == (0,)
    client.fail_on = None
    assert pruner.run_retention(client, today="2026-09-25", now="2026-09-25T05:00:00Z")["status"] == "ran"


def test_retention_without_ops_state_still_prunes():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE criticality_snapshots (as_of TEXT NOT NULL)")
    connection.execute("INSERT INTO criticality_snapshots VALUES ('2020-01-01')")
    outcome = pruner.run_retention(SqliteD1(connection), today="2026-09-25", now="2026-09-25T04:00:00Z")
    assert outcome["status"] == "ran"
    assert connection.execute("SELECT COUNT(*) FROM criticality_snapshots").fetchone() == (0,)


def test_resolved_market_risk_alerts_age_out_after_30_days():
    connection = sqlite3.connect(":memory:")
    connection.executescript((MIGRATIONS / "0005_criticality_monitor.sql").read_text(encoding="utf-8"))
    rows = [
        ("open-old", "2020-01-01T00:00:00Z", None),
        ("resolved-old", "2020-01-01T00:00:00Z", "2020-01-05T00:00:00Z"),
        ("resolved-recent", "2020-01-01T00:00:00Z", "2999-01-05T00:00:00Z"),
    ]
    connection.executemany(
        """INSERT INTO market_risk_alerts
        (alert_id, scope, symbol, opened_at, updated_at, closed_at, state, severity,
         model_version, reason_codes_json, payload_json)
        VALUES (?, 'market', 'SPY', ?, ?, ?, 'resolved', 'watch', 'm', '[]', '{}')""",
        [(alert, opened, opened, closed) for alert, opened, closed in rows],
    )
    changes = pruner.prune_time_series(execute_on(connection), pruner.table_names(connection))
    assert changes["market_risk_alerts"] == 1
    assert {row[0] for row in connection.execute("SELECT alert_id FROM market_risk_alerts")} == {
        "open-old",
        "resolved-recent",
    }
    plan = " ".join(
        row[3]
        for row in connection.execute(
            "EXPLAIN QUERY PLAN SELECT rowid FROM market_risk_alerts "
            "WHERE closed_at < datetime('now', '-30 days') LIMIT 1000"
        )
    )
    assert "SCAN market_risk_alerts" not in plan, plan


def _completed(stdout: str = "", stderr: str = "", code: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


def test_statement_metrics_come_from_d1_meta(monkeypatch, capsys):
    payload = [{"results": [], "success": True,
                "meta": {"changes": 3, "rows_read": 41, "rows_written": 9}}]
    monkeypatch.setattr(pruner.subprocess, "run", lambda *a, **k: _completed(json.dumps(payload)))
    client = pruner.WranglerD1(Path("wrangler"), "DB", Path("cfg.jsonc"))
    assert client.execute("DELETE FROM sleeve_marks WHERE rowid IN (SELECT 1)") == 3
    assert client.execute("DELETE FROM sleeve_marks WHERE rowid IN (SELECT 2)") == 3
    assert client.metrics.as_dict() == {
        "statements": 2, "rows_read": 82, "rows_written": 18, "changes": 6,
    }
    out = capsys.readouterr().out
    assert "D1 statement 1: sleeve_marks rows_read=41 rows_written=9 changes=3" in out


def test_quota_exhaustion_exits_75_with_metrics(monkeypatch, capsys):
    monkeypatch.setattr(
        pruner.subprocess, "run", lambda *a, **k: _completed(stderr=WRANGLER_QUOTA_ERROR, code=1)
    )
    assert pruner.main(["--config", "cfg.jsonc"]) == pruner.QUOTA_EXIT_CODE
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("D1_METRICS ")
    assert json.loads(last.split(" ", 1)[1])["status"] == "quota"


def test_quota_json_on_stdout_defers_despite_a_stderr_notice(monkeypatch, capsys):
    # wrangler --json prints its error on STDOUT; an update notice on stderr
    # used to be the only text classified, so the quota read as a failure.
    notice = (
        "[WARNING] The version of Wrangler you are using is now out-of-date.\n"
        "Please update to the latest version to prevent critical errors.\n"
    )
    monkeypatch.setattr(
        pruner.subprocess, "run",
        lambda *a, **k: _completed(stdout=WRANGLER_QUOTA_ERROR, stderr=notice, code=1),
    )
    assert pruner.main(["--config", "cfg.jsonc"]) == pruner.QUOTA_EXIT_CODE
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(last.split(" ", 1)[1])["status"] == "quota"


def test_a_sql_error_labelled_7500_fails_instead_of_deferring(monkeypatch, capsys):
    # D1 reports every SQL error as code 7500. Read as "quota", a retention
    # bug would exit 75, defer the seed, and repeat every day unnoticed.
    monkeypatch.setattr(
        pruner.subprocess, "run", lambda *a, **k: _completed(stderr=WRANGLER_SQL_ERROR, code=1)
    )
    assert pruner.main(["--config", "cfg.jsonc"]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(last.split(" ", 1)[1])["status"] == "failed"
    assert not pruner.QUOTA_PATTERN.search(WRANGLER_SQL_ERROR)
    assert pruner.QUOTA_PATTERN.search(WRANGLER_QUOTA_ERROR)


def test_other_failures_exit_1(monkeypatch, capsys):
    monkeypatch.setattr(
        pruner.subprocess, "run",
        lambda *a, **k: _completed(stderr="Authentication error [code: 10000]", code=1),
    )
    assert pruner.main(["--config", "cfg.jsonc"]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(last.split(" ", 1)[1])["status"] == "failed"
