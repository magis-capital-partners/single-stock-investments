"""The dashboard D1 seed must fit the Workers Free quota (100k rows written/day).

Before 2026-09-24 every rebuild of core.json rewrote ~20.5k rows because the
rebuild time was part of every run, valuation-run and fact identity. These
tests pin the incremental contract: a rebuild that changes nothing D1 stores
writes nothing, a real change writes only the rows it changes, removed rows are
deleted by key through indexes, and no incremental statement scans a table.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "dashboard" / "cloudflare" / "migrations"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


exporter = load_module(
    "export_dashboard_d1_seed_budget", ROOT / "_system" / "scripts" / "export_dashboard_d1_seed.py"
)


def schema() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    for path in sorted(MIGRATIONS.glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def workbench(ticker: str, facts: list[tuple[str, float]], *, model_hash: str = "model-1") -> dict:
    lineage = [
        {"ref": f"{ticker}/10-K.pdf", "node_id": node, "source_id": f"{ticker}-src-{node}",
         "locator": "p.1", "as_of": "2026-06-30"}
        for node, _value in facts
    ]
    traces = [{"id": node, "value": value, "unit": "USD"} for node, value in facts]
    return {
        "as_of": "2026-09-20",
        "decision": {"status": "decision_grade", "model_hash": model_hash, "value_per_share": {"base": 10}},
        "method_fit": {"profile_id": "quality_reinvestment", "primary_methods": ["owner_earnings_reinvestment_dcf"]},
        "valuation": {
            "valuation": {"value_per_share": {"low": 8, "base": 10, "high": 12}},
            "calculation_proof_summary": {"aggregate_proof_hash": "proof-" + model_hash},
            "components": [{
                "component_id": "core_business",
                "label": "Core business",
                "category": "operating",
                "range_per_share": {"low": 8, "base": 10, "high": 12},
                "calculation_proof": {
                    "proof_hash": "component-proof",
                    "output_unit": "USD per share",
                    "traces": {"base": traces},
                    "source_lineage": lineage,
                },
            }],
        },
    }


def ticker_row(ticker: str, *, price: float = 50.0, last_research: str = "2026-09-20") -> dict:
    return {
        "ticker": ticker,
        "company": f"{ticker} Inc",
        "market": "US",
        "exchange": "NYSE",
        "last_research": last_research,
        "detail_shard": f"data/tickers/{ticker}.json",
        "classification": {"investment_sleeve": "Software", "stance": "watch",
                           "archetype": "compounder", "analysis_as_of": "2026-09-01"},
        "valuation_decision": {
            "status": "evidence_blocked",
            "provisional": True,
            "price_per_share": price,
            "value_per_share": {"low": 8, "base": 10, "high": 12},
            "open_gap_count": 1,
            "critical_gap_count": 1,
            "next_gap_id": "revenue_required",
            "dates": {"model_as_of": "2026-09-20", "price_as_of": "2026-09-23"},
        },
    }


class SeedFixture:
    """A throwaway repo root: core.json, ticker shards, an evidence queue."""

    def __init__(self, directory: Path):
        self.root = directory
        (directory / "dashboard" / "data" / "tickers").mkdir(parents=True)
        self.queue = directory / "evidence_recovery_queue.json"
        self.queue.write_text(json.dumps({"items": [{
            "ticker": "AAA",
            "task_packet": {"updated_at": "2026-09-20T00:00:00Z", "tasks": [
                {"id": "t1", "question": "Find audited revenue."},
                {"id": "t2", "question": "Find segment margin."},
            ]},
        }]}), encoding="utf-8")
        self.counter = 0

    def shard(self, ticker: str, body: dict) -> None:
        path = self.root / "dashboard" / "data" / "tickers" / f"{ticker}.json"
        path.write_text(json.dumps({"ticker": ticker, "valuation_workbench": body}), encoding="utf-8")

    def export(self, core: dict, connection: sqlite3.Connection | None = None, *, full: bool = False):
        self.counter += 1
        core_path = self.root / f"core_{self.counter}.json"
        seed_path = self.root / f"seed_{self.counter}.sql"
        core_path.write_text(json.dumps(core), encoding="utf-8")
        ops_state = None
        if connection is not None and not full:
            ops_state = dict(connection.execute("SELECT key, value FROM ops_state").fetchall())
        report = exporter.export(
            core_path, seed_path, self.queue, ops_state=ops_state, full=full,
            technical_summary={}, criticality_summary={}, root=self.root,
        )
        return report, seed_path.read_text(encoding="utf-8")


def apply(connection: sqlite3.Connection, seed: str) -> int:
    before = connection.total_changes
    connection.executescript(seed)
    return connection.total_changes - before


def statements(seed: str) -> list[str]:
    return [line for line in seed.split("\n") if line.strip() and not line.startswith("--")]


DATA_TABLES = (
    "securities", "valuation_current", "evidence_tasks", "source_documents",
    "valuation_runs", "valuation_components", "facts",
)


def snapshot(connection: sqlite3.Connection, tables) -> dict[str, list[tuple]]:
    return {
        table: sorted(connection.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
        for table in tables
    }


def delete_plan(connection: sqlite3.Connection, sql: str) -> str:
    """A DELETE's plan, including the child-key lookups its foreign keys run
    for every deleted row. (INSERT plans also list child-table scans, but
    SQLite runs those only while deferred violations are outstanding, so they
    are not reads; a DELETE's child lookups always run.)"""
    return " | ".join(row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + sql))


def base_core(generated_at: str = "2026-09-24T09:00:00Z") -> dict:
    return {
        "generated_at": generated_at,
        "summary": {"holdings": 2},
        "valuation_queue": {"items": []},
        "tickers": [ticker_row("AAA"), ticker_row("BBB")],
    }


class IncrementalSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = SeedFixture(Path(self._tmp.name))
        self.fx.shard("AAA", workbench("AAA", [("revenue", 100.0), ("margin", 0.25)]))
        self.fx.shard("BBB", workbench("BBB", [("revenue", 7.0)]))
        self.db = schema()
        report, seed = self.fx.export(base_core(), self.db)
        self.assertEqual(report["mode"], "full")
        apply(self.db, seed)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def count(self, table: str, where: str = "1=1") -> int:
        return self.db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]

    def test_timestamp_only_rebuild_writes_no_data_rows_even_without_state(self):
        # A FULL export of identical content with a new rebuild time: the old
        # exporter re-keyed facts and valuation runs by generated_at and
        # restamped latest_run_id everywhere, so this re-wrote every row.
        # Now the only writes are the import's own bookkeeping: its
        # pipeline_runs row and the state row that names it.
        before = snapshot(self.db, DATA_TABLES)
        _report, seed = self.fx.export(base_core("2026-09-24T17:45:00Z"), full=True)
        self.assertEqual(apply(self.db, seed), 2)
        self.assertEqual(snapshot(self.db, DATA_TABLES), before)

    def test_timestamp_only_rebuild_skips_the_seed(self):
        report, seed = self.fx.export(base_core("2026-09-24T17:45:00Z"), self.db)
        self.assertTrue(report["skip"])
        self.assertEqual(report["statement_count"], 0)
        self.assertEqual(statements(seed), [])

    def test_data_identities_carry_no_timestamp(self):
        for table, column in (("facts", "fact_id"), ("valuation_runs", "valuation_run_id")):
            before = {row[0] for row in self.db.execute(f"SELECT {column} FROM {table}")}
            _report, seed = self.fx.export(base_core("2031-01-01T00:00:00Z"), full=True)
            fresh = schema()
            apply(fresh, seed)
            after = {row[0] for row in fresh.execute(f"SELECT {column} FROM {table}")}
            self.assertEqual(before, after, table)

    def test_a_revert_records_a_new_latest_pipeline_run(self):
        # /api/v1/summary shows the newest pipeline_runs row by generated_at.
        # With a content-only run id, reverting to earlier content hit
        # ON CONFLICT DO NOTHING and "latest" kept naming the reverted-from run.
        changed = base_core("2026-09-24T12:00:00Z")
        changed["tickers"][1]["valuation_decision"]["price_per_share"] = 51.5
        _report, seed = self.fx.export(changed, self.db)
        apply(self.db, seed)
        _report, seed = self.fx.export(base_core("2026-09-24T18:00:00Z"), self.db)  # the revert
        apply(self.db, seed)
        latest_run, latest_at = self.db.execute(
            "SELECT run_id, generated_at FROM pipeline_runs ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(latest_at, "2026-09-24T18:00:00Z")
        self.assertEqual(
            self.db.execute("SELECT latest_run_id FROM valuation_current WHERE ticker='BBB'").fetchone()[0],
            latest_run,
        )
        self.assertEqual(self.count("pipeline_runs"), 3)

    def test_ops_state_is_written_last(self):
        # The seed state vouches for everything before it in the import. Written
        # any earlier, a partial import could record hashes for rows it never
        # wrote, and the next export would skip them for good.
        changed = base_core("2026-09-24T12:00:00Z")
        changed["tickers"][0]["valuation_decision"]["price_per_share"] = 44.0
        cases = [self.fx.export(changed, self.db)[1], self.fx.export(changed, full=True)[1]]
        for seed in cases:
            sql = statements(seed)
            touches_state = ["ops_state" in line for line in sql]
            self.assertIn(True, touches_state)
            first = touches_state.index(True)
            self.assertGreater(first, 1)
            self.assertTrue(all(touches_state[first:]), "a statement after the state writes")
            self.assertFalse(any(touches_state[:first]))

    def test_real_change_writes_only_the_changed_rows(self):
        core = base_core("2026-09-24T18:00:00Z")
        core["tickers"][1]["valuation_decision"]["price_per_share"] = 51.5
        report, seed = self.fx.export(core, self.db)
        self.assertEqual(report["mode"], "incremental")
        self.assertEqual(report["changed_ticker_count"], 1)
        self.assertNotIn("'AAA'", seed)
        # valuation_current for BBB, one new pipeline_runs row, the state row.
        self.assertEqual(apply(self.db, seed), 3)
        self.assertEqual(
            self.db.execute("SELECT price_per_share FROM valuation_current WHERE ticker='BBB'").fetchone()[0],
            51.5,
        )
        # latest_run_id moves only where content moved.
        runs = dict(self.db.execute("SELECT ticker, latest_run_id FROM valuation_current").fetchall())
        self.assertNotEqual(runs["AAA"], runs["BBB"])

    def test_removed_rows_are_deleted_by_key_set(self):
        self.fx.shard("AAA", workbench("AAA", [("revenue", 100.0)]))  # margin fact gone
        queue = json.loads(self.fx.queue.read_text(encoding="utf-8"))
        queue["items"][0]["task_packet"]["tasks"] = queue["items"][0]["task_packet"]["tasks"][:1]
        self.fx.queue.write_text(json.dumps(queue), encoding="utf-8")
        core = base_core("2026-09-24T18:00:00Z")
        core["tickers"] = core["tickers"][:1]  # BBB leaves the universe
        report, seed = self.fx.export(core, self.db)
        self.assertEqual(report["removed_ticker_count"], 1)
        apply(self.db, seed)
        self.assertEqual(self.count("facts", "ticker='AAA'"), 1)
        self.assertEqual(self.count("source_documents", "ticker='AAA'"), 1)
        self.assertEqual(self.count("evidence_tasks", "ticker='AAA'"), 1)
        for table in ("securities", "valuation_current", "evidence_tasks", "facts",
                      "source_documents", "valuation_runs"):
            self.assertEqual(self.count(table, "ticker='BBB'"), 0, table)
        self.assertEqual(self.count("valuation_components"), 1)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_new_model_replaces_the_run_and_its_components(self):
        self.fx.shard("AAA", workbench("AAA", [("revenue", 100.0), ("margin", 0.25)], model_hash="model-2"))
        _report, seed = self.fx.export(base_core("2026-09-24T18:00:00Z"), self.db)
        apply(self.db, seed)
        self.assertEqual(self.count("valuation_runs", "ticker='AAA'"), 1)
        self.assertEqual(
            self.db.execute("SELECT input_hash FROM valuation_runs WHERE ticker='AAA'").fetchone()[0],
            "model-2",
        )
        self.assertEqual(self.count("valuation_components"), 2)  # one per ticker's run

    def test_incremental_statements_never_scan_a_table(self):
        core = base_core("2026-09-24T18:00:00Z")
        core["tickers"][0]["valuation_decision"]["price_per_share"] = 49.0
        core["tickers"] = core["tickers"][:1]
        self.fx.shard("AAA", workbench("AAA", [("revenue", 101.0)], model_hash="model-3"))
        _report, seed = self.fx.export(core, self.db)
        deletes = [sql for sql in statements(seed) if sql.startswith("DELETE")]
        for sql in deletes:
            plan = delete_plan(self.db, sql)
            self.assertNotIn("SCAN ", plan, f"{plan}\n{sql[:160]}")
        self.assertGreaterEqual(len(deletes), 5)

    def test_full_export_scans_only_the_securities_sweep(self):
        _report, seed = self.fx.export(base_core("2026-09-24T18:00:00Z"), full=True)
        scanning = [
            sql for sql in statements(seed)
            if sql.startswith("DELETE") and "SCAN " in delete_plan(self.db, sql)
        ]
        self.assertEqual(len(scanning), 1)
        self.assertTrue(scanning[0].startswith("DELETE FROM securities WHERE ticker NOT IN"))

    def test_first_seed_rekeys_rows_left_by_the_old_exporter(self):
        # Rows keyed the old way (rebuild time inside the id) must be replaced
        # once, while unchanged securities are not rewritten.
        old_run = "dashboard:2026-09-23T21:50:55Z:08a77108"
        self.db.execute(
            "INSERT INTO pipeline_runs (run_id, generated_at, source_sha256, status, ticker_count, summary_json) "
            "VALUES (?, '2026-09-23T21:50:55Z', 'x', 'complete', 2, '{}')", (old_run,))
        self.db.execute(
            "INSERT INTO facts (fact_id, ticker, field_id, confidence, locked, run_id, method_version, derivation_json) "
            "VALUES ('old-fact', 'AAA', 'revenue', 'source_locked', 1, ?, '1.0', '{}')", (old_run,))
        self.db.execute(
            "INSERT INTO valuation_runs (valuation_run_id, ticker, method_id, method_version, status, "
            "input_hash, payload_json, run_id) VALUES ('old-run', 'AAA', 'm', '1.0', 's', 'h', '{}', ?)", (old_run,))
        self.db.execute(
            "INSERT INTO valuation_components (valuation_run_id, component_id, label, treatment, payload_json) "
            "VALUES ('old-run', 'core_business', 'x', 'additive', '{}')")
        self.db.execute("DELETE FROM ops_state")
        self.db.commit()
        report, seed = self.fx.export(base_core("2026-09-24T18:00:00Z"), self.db)
        self.assertEqual(report["mode"], "full")
        apply(self.db, seed)
        self.assertEqual(self.count("facts", "fact_id='old-fact'"), 0)
        self.assertEqual(self.count("valuation_runs", "valuation_run_id='old-run'"), 0)
        self.assertEqual(self.count("valuation_components", "valuation_run_id='old-run'"), 0)
        self.assertEqual(self.count("facts"), 3)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_state_survives_chunking_and_stale_chunks_are_removed(self):
        original = exporter.STATE_CHUNK_CHARS
        try:
            exporter.STATE_CHUNK_CHARS = 64
            core = base_core("2026-09-24T18:00:00Z")
            core["tickers"][0]["valuation_decision"]["price_per_share"] = 60.0
            _report, seed = self.fx.export(core, self.db)
            apply(self.db, seed)
            keys = [k for (k,) in self.db.execute("SELECT key FROM ops_state ORDER BY key")]
            self.assertGreater(len(keys), 3)
            state = exporter.load_previous_state(dict(self.db.execute("SELECT key, value FROM ops_state")))
            self.assertEqual(sorted(state["tickers"]), ["AAA", "BBB"])
            exporter.STATE_CHUNK_CHARS = original
            core["tickers"][0]["valuation_decision"]["price_per_share"] = 61.0
            _report, seed = self.fx.export(core, self.db)
            apply(self.db, seed)
            self.assertEqual(
                [k for (k,) in self.db.execute("SELECT key FROM ops_state ORDER BY key")],
                ["seed:state:000"],
            )
        finally:
            exporter.STATE_CHUNK_CHARS = original

    def test_unreadable_or_foreign_state_falls_back_to_full(self):
        self.assertIsNone(exporter.load_previous_state({"seed:state:000": "{not json"}))
        stale = json.dumps({"format": exporter.SEED_FORMAT - 1, "content_sha256": "x", "tickers": {}})
        self.assertIsNone(exporter.load_previous_state({"seed:state:000": stale}))
        report, _seed = self.fx.export(base_core(), None)
        self.assertEqual(report["mode"], "full")


class SeedWiringTests(unittest.TestCase):
    def test_migration_indexes_the_child_keys_the_seed_deletes_through(self):
        connection = schema()

        def indexed(table: str, columns: list[str]) -> bool:
            for _seq, name, *_rest in connection.execute(f"PRAGMA index_list('{table}')"):
                cols = [row[2] for row in connection.execute(f"PRAGMA index_info('{name}')")]
                if cols[: len(columns)] == columns:
                    return True
            return False

        self.assertTrue(indexed("facts", ["source_document_id"]))
        self.assertTrue(indexed("task_attempts", ["ticker", "task_id"]))
        self.assertEqual(
            [row[1] for row in connection.execute("PRAGMA table_info('ops_state')")],
            ["key", "value", "updated_at"],
        )


if __name__ == "__main__":
    unittest.main()
