// The book on the Flex EOD feed, end to end against real SQL.
//
// fixtures/flex_eod_account_snapshot.json is exactly what flex_ingest builds
// from a statement carrying an equity summary (test_flex_eod_nav.py compares
// the two), so this is the payload NY4 will POST once the Flex query states
// NAV. It is stored through the real ingest code beside the collector's
// 2026-08-25 run and a positions-only (complete=0) Flex run, and the real book
// query must then:
//
//   * select the Flex run -- the book stops being frozen at 2026-08-25;
//   * judge its age by the session calendar, not the collector's two hours:
//     fresh through the next session's close plus grace, weekend-aware;
//   * keep the live rule for a live-feed snapshot.

import assert from "node:assert/strict";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { loadPortfolio, snapshotFreshness, storeAccountSnapshot, validateAccountSnapshot } from "../functions/_lib/portfolio.js";
import { onRequestGet as performance } from "../functions/api/v2/portfolio/performance.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const GOLDEN = JSON.parse(readFileSync(join(HERE, "fixtures", "flex_eod_account_snapshot.json"), "utf8"));

function d1(database) {
  const make = (sql, binds = []) => {
    const values = () => binds.map((value) => (value === undefined ? null : typeof value === "boolean" ? Number(value) : value));
    const select = /^\s*(select|with)/i.test(sql);
    return {
      sql,
      bind: (...next) => make(sql, next),
      run: async () => ({ meta: { changes: Number(database.prepare(sql).run(...values()).changes || 0) } }),
      all: async () => ({ results: database.prepare(sql).all(...values()) }),
      first: async () => database.prepare(sql).get(...values()) ?? null,
      _batch: () => (select
        ? { results: database.prepare(sql).all(...values()) }
        : { results: [], meta: { changes: Number(database.prepare(sql).run(...values()).changes || 0) } }),
    };
  };
  return { prepare: (sql) => make(sql), batch: async (statements) => statements.map((statement) => statement._batch()) };
}

function freshEnv() {
  const database = new DatabaseSync(":memory:");
  const dir = join(HERE, "migrations");
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".sql")).sort()) {
    const sql = readFileSync(join(dir, file), "utf8").replace(/--[^\n]*/g, "");
    for (const statement of sql.split(";").map((part) => part.trim()).filter(Boolean)) {
      try { database.exec(statement); } catch (_) { /* unrelated legacy tables */ }
    }
  }
  const archived = [];
  return {
    database,
    env: {
      DB: d1(database), PRIVATE_ARTIFACTS: { put: async (key) => archived.push(key) },
      PORTFOLIO_AUTH_MODE: "development",
    },
  };
}

async function store(env, payload) {
  return storeAccountSnapshot(env, validateAccountSnapshot(payload), Buffer.from(JSON.stringify(payload)));
}

const collectorRun = () => ({
  schema_version: "account_snapshot.v1", source_run_id: "collector-2026-08-25", account_alias: "U805366",
  as_of: "2026-08-25T15:26:01Z", complete: true, base_currency: "USD", completeness: { account_summary: true },
  account_values: [{ tag: "NetLiquidation", value: "11870000", currency: "USD", source: "ibkr", as_of: "2026-08-25T15:26:01Z" }],
  positions: [],
});

// What NY4 has been posting every weekday since 2026-08-27: positions, no NAV.
const positionsOnlyFlexRun = () => ({
  ...GOLDEN, source_run_id: "flex-positions-only", complete: false, account_values: [],
  as_of: "2026-09-23T22:15:09Z",
  completeness: { ...GOLDEN.completeness, account_summary: false, session_date: "2026-09-23" },
});

const at = (iso) => ({ now: Date.parse(iso) });

test("a complete Flex EOD run replaces the frozen collector run in the book", async () => {
  const { env } = freshEnv();
  await store(env, collectorRun());
  await store(env, positionsOnlyFlexRun());

  const before = await loadPortfolio(env, "all", at("2026-09-24T12:00:00Z"));
  assert.equal(before.snapshot.source_run_id, "collector-2026-08-25", "today: frozen, complete=0 runs are never served");

  await store(env, GOLDEN);
  const book = await loadPortfolio(env, "all", at("2026-09-25T10:00:00Z"));
  assert.equal(book.status, "complete");
  assert.equal(book.snapshot.source_run_id, GOLDEN.source_run_id);
  assert.equal(book.snapshot.feed, "flex_eod");
  assert.equal(book.snapshot.session_date, "2026-09-24");
  assert.equal(book.snapshot.stale, false, "the morning after the close is not a stopped feed");
  const nav = book.account_values.find((row) => row.tag === "NetLiquidation");
  assert.equal(nav.value_decimal, "11867165.25");
  assert.equal(book.positions.length, GOLDEN.positions.length);
});

test("an EOD snapshot is fresh through the next session plus grace, weekend-aware", () => {
  const thursday = { as_of: "2026-09-24T22:15:14Z", completeness_json: JSON.stringify({ feed: "flex_eod", session_date: "2026-09-24" }) };
  assert.equal(snapshotFreshness(thursday, Date.parse("2026-09-25T20:00:00Z")).stale, false, "Friday, before Friday's statement");
  assert.equal(snapshotFreshness(thursday, Date.parse("2026-09-26T04:59:00Z")).stale, false, "~30.7h: still inside the grace");
  assert.equal(snapshotFreshness(thursday, Date.parse("2026-09-26T05:01:00Z")).stale, true, "Friday's statement never came");

  const friday = { as_of: "2026-09-25T22:15:14Z", completeness_json: JSON.stringify({ feed: "flex_eod", session_date: "2026-09-25" }) };
  assert.equal(snapshotFreshness(friday, Date.parse("2026-09-27T12:00:00Z")).stale, false, "Sunday: no session since Friday");
  assert.equal(snapshotFreshness(friday, Date.parse("2026-09-28T23:59:00Z")).stale, false, "Monday evening, statement due");
  assert.equal(snapshotFreshness(friday, Date.parse("2026-09-29T05:01:00Z")).stale, true, "~79h: Monday's statement is late");
  assert.equal(snapshotFreshness(friday, Date.parse("2026-09-29T05:01:00Z")).stale_after, "2026-09-29T05:00:00.000Z");
});

test("the live feed keeps its two-hour rule", async () => {
  const { env } = freshEnv();
  await store(env, collectorRun());
  const book = await loadPortfolio(env, "all", at("2026-08-25T16:00:00Z"));
  assert.equal(book.snapshot.feed, "live");
  assert.equal(book.snapshot.stale, false);
  const later = await loadPortfolio(env, "all", at("2026-09-24T12:00:00Z"));
  assert.equal(later.snapshot.stale, true);
  assert.ok(later.snapshot.age_seconds > 29 * 86_400, "~30 days: the banner says so");
});

test("an unparseable as_of is unknown, never assumed fresh", () => {
  const fresh = snapshotFreshness({ as_of: "", completeness_json: '{"feed":"flex_eod"}' }, Date.now());
  assert.equal(fresh.stale, null);
  assert.equal(fresh.age_seconds, null);
});

test("the NAV history gains the EOD observation", async () => {
  const { env } = freshEnv();
  await store(env, collectorRun());
  await store(env, positionsOnlyFlexRun());
  await store(env, GOLDEN);
  const response = await performance({ request: new Request("http://localhost/api/v2/portfolio/performance?owner=all"), env });
  const body = await response.json();
  assert.deepEqual(body.nav_series.map((row) => row.nav_decimal), ["11870000", "11867165.25"]);
});

test("an EOD statement with an unreadable session date says so instead of borrowing one", () => {
  // flex_ingest leaves session_date null (and warns) when the statement's date
  // cannot be read. The book still judges freshness -- by the ingest date --
  // but must not present that date as the session's.
  const unreadable = {
    as_of: "2026-09-24T22:15:14Z",
    completeness_json: JSON.stringify({ feed: "flex_eod", session_date: null, warnings: ["session date unreadable: 'sometime'"] }),
  };
  const fresh = snapshotFreshness(unreadable, Date.parse("2026-09-25T10:00:00Z"));
  assert.equal(fresh.feed, "flex_eod");
  assert.equal(fresh.session_date, null, "no date is invented");
  assert.equal(fresh.session_date_source, "ingest_time");
  assert.equal(fresh.stale, false);
  assert.equal(fresh.stale_after, "2026-09-26T05:00:00.000Z", "judged from the ingest date's calendar");

  const read = snapshotFreshness({ as_of: "2026-09-24T22:15:14Z", completeness_json: JSON.stringify({ feed: "flex_eod", session_date: "2026-09-24" }) }, Date.parse("2026-09-25T10:00:00Z"));
  assert.equal(read.session_date_source, "statement");
});
