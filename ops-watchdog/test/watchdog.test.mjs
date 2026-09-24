// node --test ops-watchdog/test/watchdog.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  chooseStore, kvStore, parseD1Usage, readHeadField, runChecks, slotStore,
} from "../src/checks.js";

const NOW = new Date("2026-09-24T20:41:00Z");

class FakeKV {
  constructor() { this.map = new Map(); this.writes = 0; }
  async get(key) { return this.map.has(key) ? this.map.get(key) : null; }
  async put(key, value) { this.writes += 1; this.map.set(key, value); }
  async delete(key) { this.map.delete(key); }
}

function response(status, body) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async text() { return typeof body === "string" ? body : JSON.stringify(body); },
    async json() { return typeof body === "string" ? JSON.parse(body) : body; },
  };
}

// A fake fetch for raw.githubusercontent.com, the GraphQL endpoint and Slack.
function world({ checkedAt = "2026-09-24T20:03:55Z", coreAt = "2026-09-24T19:30:05Z",
  d1 = { rowsRead: 1000, rowsWritten: 10 }, d1Status = 200, d1Errors = null,
  rawStatus = 206, slackStatus = 200 } = {}) {
  const calls = [];
  const slack = [];
  const fetch = async (url, init = {}) => {
    calls.push({ url, init });
    if (url.includes("repository_health_supervisor.json")) {
      return response(rawStatus, `{\n  "schema_version": "2.0",\n  "checked_at": "${checkedAt}",\n`);
    }
    if (url.includes("core.json")) {
      assert.match(init.headers.Range, /^bytes=0-\d+$/, "core.json must be range-read");
      return response(rawStatus, `{"generated_at":"${coreAt}","workspace":"/workspace","summary":{`);
    }
    if (url.includes("api.cloudflare.com")) {
      if (d1Errors) return response(200, { data: null, errors: d1Errors });
      return response(d1Status, { data: { viewer: { accounts: [
        { d1AnalyticsAdaptiveGroups: [{ sum: d1 }] }] } } });
    }
    if (url.startsWith("https://hooks.slack.com/")) {
      slack.push(JSON.parse(init.body).text);
      return response(slackStatus, "ok");
    }
    throw new Error(`unexpected fetch ${url}`);
  };
  return { fetch, calls, slack };
}

const ENV = {
  SLACK_WEBHOOK_URL: "https://hooks.slack.com/services/T/B/x",
  CF_API_TOKEN: "token", CF_ACCOUNT_ID: "account",
};

test("healthy: nothing is sent", async () => {
  const w = world();
  const report = await runChecks(ENV, NOW, { fetch: w.fetch, store: kvStore(new FakeKV()) });
  assert.deepEqual(report.alerts, []);
  assert.equal(w.slack.length, 0);
  assert.ok(!w.calls.some((c) => /d1|database/i.test(c.url) && !c.url.includes("graphql")),
    "the worker only reads D1 analytics, never a database");
});

test("a supervisor gap alerts once per tier, then says it recovered", async () => {
  const kv = new FakeKV();
  const stale = world({ checkedAt: "2026-09-24T11:00:00Z" });       // 9.7h
  await runChecks(ENV, NOW, { fetch: stale.fetch, store: kvStore(kv) });
  assert.equal(stale.slack.length, 1);
  assert.match(stale.slack[0], /\[GAP\] The repository-health supervisor has not run for 9\.7h/);
  await runChecks(ENV, new Date(NOW.getTime() + 30 * 60e3), { fetch: stale.fetch, store: kvStore(kv) });
  assert.equal(stale.slack.length, 1, "the same gap is not repeated every 30 minutes");
  await runChecks(ENV, new Date("2026-09-25T12:00:00Z"), { fetch: stale.fetch, store: kvStore(kv) });
  assert.equal(stale.slack.length, 2, "a gap past 3x the limit reminds once");
  const back = world({ checkedAt: "2026-09-25T12:41:00Z" });
  await runChecks(ENV, new Date("2026-09-25T13:00:00Z"), { fetch: back.fetch, store: kvStore(kv) });
  assert.match(back.slack[0], /\[RECOVERED\] The supervisor ran again/);
  await runChecks(ENV, new Date("2026-09-25T13:30:00Z"), { fetch: back.fetch, store: kvStore(kv) });
  assert.equal(back.slack.length, 1);
});

test("D1 thresholds alert once per day, highest threshold only", async () => {
  const kv = new FakeKV();
  const w60 = world({ d1: { rowsRead: 3_100_000, rowsWritten: 10 } });
  await runChecks(ENV, NOW, { fetch: w60.fetch, store: kvStore(kv) });
  assert.match(w60.slack[0], /\[D1 60%\] D1 rows read today: 3,100,000 of the free 5,000,000\/day/);
  await runChecks(ENV, NOW, { fetch: w60.fetch, store: kvStore(kv) });
  assert.equal(w60.slack.length, 1);
  const w85 = world({ d1: { rowsRead: 10, rowsWritten: 85_000 } });
  await runChecks(ENV, NOW, { fetch: w85.fetch, store: kvStore(kv) });
  assert.match(w85.slack[0], /\[D1 80%\] D1 rows written/);
  assert.doesNotMatch(w85.slack[0], /\[D1 60%\]/);
  const tomorrow = new Date("2026-09-25T09:00:00Z");
  await runChecks(ENV, tomorrow, { fetch: w60.fetch, store: kvStore(kv) });
  assert.equal(w60.slack.length, 2, "a new UTC day re-arms the thresholds");
});

test("an unauthorized analytics token degrades quietly", async () => {
  for (const w of [world({ d1Status: 403 }), world({ d1Errors: [{ message: "not authorized" }] })]) {
    const report = await runChecks(ENV, NOW, { fetch: w.fetch, store: kvStore(new FakeKV()) });
    assert.equal(report.d1.ok, false);
    assert.equal(w.slack.length, 0);
  }
});

test("a stale committed core.json alerts; the Access-protected site is never fetched", async () => {
  const w = world({ coreAt: "2026-09-23T02:00:00Z" });              // 42.7h
  await runChecks(ENV, NOW, { fetch: w.fetch, store: kvStore(new FakeKV()) });
  assert.match(w.slack[0], /\[STALE DASHBOARD\] dashboard\/data\/core\.json on main was generated 43h ago/);
  assert.ok(w.calls.every((c) => !c.url.includes("pages.dev")));
});

test("unreadable GitHub raw content alerts once a day, not every run", async () => {
  const kv = new FakeKV();
  const w = world({ rawStatus: 503 });
  await runChecks(ENV, NOW, { fetch: w.fetch, store: kvStore(kv) });
  await runChecks(ENV, new Date(NOW.getTime() + 30 * 60e3), { fetch: w.fetch, store: kvStore(kv) });
  assert.equal(w.slack.length, 1);
  assert.match(w.slack[0], /Cannot read the supervisor state/);
});

test("a failed Slack send leaves the condition to be sent next run", async () => {
  const kv = new FakeKV();
  const down = world({ checkedAt: "2026-09-24T11:00:00Z", slackStatus: 500 });
  await runChecks(ENV, NOW, { fetch: down.fetch, store: kvStore(kv) });
  assert.equal(kv.writes, 0);
  const up = world({ checkedAt: "2026-09-24T11:00:00Z" });
  await runChecks(ENV, NOW, { fetch: up.fetch, store: kvStore(kv) });
  assert.equal(up.slack.length, 1);
});

test("without KV or a working cache, fixed slots cap repeats at four a day", async () => {
  const noopCache = { async match() { return undefined; }, async put() {}, async delete() {} };
  const inSlot = new Date("2026-09-24T18:10:00Z");
  const offSlot = new Date("2026-09-24T19:10:00Z");
  assert.equal((await chooseStore({}, offSlot, noopCache)).kind, "slots");
  const w = world({ checkedAt: "2026-09-24T08:00:00Z" });
  await runChecks(ENV, offSlot, { fetch: w.fetch, store: slotStore(offSlot) });
  assert.equal(w.slack.length, 0);
  await runChecks(ENV, inSlot, { fetch: w.fetch, store: slotStore(inSlot) });
  assert.equal(w.slack.length, 1);
  assert.equal((await chooseStore({ DEDUPE: new FakeKV() }, NOW, noopCache)).kind, "kv");
});

test("parsers", async () => {
  assert.deepEqual(parseD1Usage({ data: { viewer: { accounts: [{ d1AnalyticsAdaptiveGroups: [
    { sum: { rowsRead: 5, rowsWritten: 1 } }, { sum: { rowsRead: 7, rowsWritten: 2 } }] }] } } }),
  { ok: true, rows_read: 12, rows_written: 3 });
  const field = await readHeadField(async () => response(206, '{"checked_at": "2026-09-24T20:41:00Z"'),
    "https://raw.githubusercontent.com/x", "checked_at");
  assert.equal(field.ok, true);
  assert.equal(field.value, "2026-09-24T20:41:00Z");
});
