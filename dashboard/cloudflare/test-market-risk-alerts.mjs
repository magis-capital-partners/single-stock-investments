// /api/v1/market-risk/alerts and /health read alerts through an index.
//
// Both run on every page load. The alerts route used to order by a CASE over
// severity that no index could supply, behind a parameterised OR the planner
// could not see through, so each call read and sorted the whole (never pruned)
// table to return 100 rows; /health then counted the same table again. These
// tests pin the order the page relies on, that each statement walks an index
// and stops at LIMIT, and that the route's expression matches the migration's.

import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { onRequestGet as alerts } from "../functions/api/v1/market-risk/alerts.js";
import { onRequestGet as health } from "../functions/api/v1/market-risk/health.js";
import { ALERT_SEVERITY_RANK_SQL, ALL_ALERTS_SQL, OPEN_ALERTS_SQL, OPEN_ALERT_COUNT_SQL } from "../functions/_lib/market-risk.js";

const HERE = dirname(fileURLToPath(import.meta.url));

function d1(database, log = []) {
  const make = (sql, binds = []) => ({
    sql,
    bind: (...next) => make(sql, next),
    all: async () => { log.push(sql); return { results: database.prepare(sql).all(...binds) }; },
    first: async () => { log.push(sql); return database.prepare(sql).get(...binds) ?? null; },
    run: async () => { log.push(sql); return { meta: { changes: Number(database.prepare(sql).run(...binds).changes || 0) } }; },
    _batch() { log.push(sql); return { results: database.prepare(sql).all(...binds) }; },
  });
  return { prepare: (sql) => make(sql), batch: async (statements) => statements.map((statement) => statement._batch()) };
}

function freshDatabase() {
  const database = new DatabaseSync(":memory:");
  const dir = join(HERE, "migrations");
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".sql")).sort()) {
    const sql = readFileSync(join(dir, file), "utf8").replace(/--[^\n]*/g, "");
    for (const statement of sql.split(";").map((part) => part.trim()).filter(Boolean)) {
      try { database.exec(statement); }
      catch (error) {
        if (file.startsWith("0020")) throw new Error(`0020 failed: ${error.message}`);
      }
    }
  }
  return database;
}

function seedAlerts(database, rows) {
  const insert = database.prepare(`INSERT INTO market_risk_alerts
    (alert_id, scope, symbol, opened_at, updated_at, closed_at, state, severity, model_version, reason_codes_json, payload_json)
    VALUES (?, 'market', ?, ?, ?, ?, 'stress', ?, 'm1', '[]', '{}')`);
  for (const row of rows) insert.run(randomUUID(), row.symbol, row.updated_at, row.updated_at, row.closed_at ?? null, row.severity);
}

const plan = (database, sql, binds) => database.prepare(`EXPLAIN QUERY PLAN ${sql}`).all(...binds).map((row) => row.detail).join(" | ");

test("migration 0020 applies and indexes the route's exact rank expression", () => {
  const database = freshDatabase();
  const names = new Set(database.prepare("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='market_risk_alerts'").all().map((row) => row.name));
  assert.ok(names.has("idx_market_risk_alerts_rank"));
  assert.ok(names.has("idx_market_risk_alerts_open_rank"));
  const squash = (text) => text.replace(/\s+/g, " ").trim();
  const migration = squash(readFileSync(join(HERE, "migrations", "0020_market_risk_alert_rank_index.sql"), "utf8").replace(/--[^\n]*/g, ""));
  assert.ok(migration.includes(`(${squash(ALERT_SEVERITY_RANK_SQL)})`), "route and migration must spell the rank identically");
});

test("both alert views walk an index in order and stop at LIMIT", () => {
  const database = freshDatabase();
  for (const [sql, index] of [[OPEN_ALERTS_SQL, "idx_market_risk_alerts_open_rank"], [ALL_ALERTS_SQL, "idx_market_risk_alerts_rank"]]) {
    const detail = plan(database, sql, [100]);
    assert.match(detail, new RegExp(`USING INDEX ${index}`), detail);
    assert.doesNotMatch(detail, /TEMP B-TREE/, `no sort pass: ${detail}`);
  }
  const count = plan(database, OPEN_ALERT_COUNT_SQL, []);
  assert.match(count, /SEARCH market_risk_alerts USING COVERING INDEX idx_market_risk_alerts_open\w* \(closed_at=\?\)/, count);
});

test("the route returns the same order the page always got", async () => {
  const database = freshDatabase();
  seedAlerts(database, [
    { symbol: "LOW-NEW", severity: "low", updated_at: "2026-09-24T10:00:00Z" },
    { symbol: "HIGH-OLD", severity: "high", updated_at: "2026-09-20T10:00:00Z" },
    { symbol: "CRIT", severity: "critical", updated_at: "2026-09-19T10:00:00Z" },
    { symbol: "HIGH-NEW", severity: "high", updated_at: "2026-09-23T10:00:00Z" },
    { symbol: "ODD", severity: "unknown", updated_at: "2026-09-24T11:00:00Z" },
    { symbol: "CLOSED-CRIT", severity: "critical", updated_at: "2026-09-24T12:00:00Z", closed_at: "2026-09-24T12:00:00Z" },
    { symbol: "MED", severity: "medium", updated_at: "2026-09-21T10:00:00Z" },
  ]);
  const call = async (query) => (await (await alerts({ request: new Request(`https://dash.example/api/v1/market-risk/alerts${query}`), env: { DB: d1(database) } })).json()).items.map((row) => row.symbol);

  assert.deepEqual(await call(""), ["CRIT", "HIGH-NEW", "HIGH-OLD", "MED", "ODD", "LOW-NEW"]);
  assert.deepEqual(await call("?open=false&limit=3"), ["CLOSED-CRIT", "CRIT", "HIGH-NEW"]);
});

test("health counts open alerts without reading closed ones", async () => {
  const database = freshDatabase();
  seedAlerts(database, [
    { symbol: "A", severity: "high", updated_at: "2026-09-20T10:00:00Z" },
    { symbol: "B", severity: "low", updated_at: "2026-09-20T10:00:00Z", closed_at: "2026-09-21T10:00:00Z" },
  ]);
  const log = [];
  const response = await health({ request: new Request("https://dash.example/api/v1/market-risk/health"), env: { DB: d1(database, log) } });
  const body = await response.json();
  assert.equal(body.alerts.open_count, 1);
  const alertSql = log.find((sql) => /market_risk_alerts/.test(sql));
  assert.match(alertSql, /WHERE closed_at IS NULL/);
  assert.doesNotMatch(alertSql, /COUNT\(\*\) AS total_count/, "the unbounded total is gone");
});
