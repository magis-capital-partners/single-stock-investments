// Feeds that stopped say so: a visible "STALE since <date>" badge.
//
// A producer that stops leaves a well-formed file behind, and a page that only
// prints the file's date reads the same the day it stopped as a month later.
// The Darwin tab (refresh disabled since 2026-08-23, data from 2026-08-19), the
// activist "Last scan" line (last scan 2026-08-26 on a daily scan) and the INV
// two-phase watch all did exactly that. These tests drive the real renderers:
// ActivistViz from its own file, and the Darwin / two-phase renderers lifted
// out of index.html's inline script, all on one fake clock.

import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { FakeClock, loadScripts } from "./spa-harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const INDEX = readFileSync(join(HERE, "..", "index.html"), "utf8").replace(/\r\n/g, "\n");
const NOW = Date.parse("2026-09-25T14:00:00Z");

/** A top-level `function name(...) {...}` from index.html's inline script. */
function extract(name) {
  // UPPER_CASE names are `const NAME = {...};` tables; everything else a function.
  const isConst = /^[A-Z0-9_]+$/.test(name);
  const start = INDEX.indexOf(isConst ? `\nconst ${name} = ` : `\nfunction ${name}(`);
  assert.ok(start >= 0, `index.html defines ${name}`);
  const close = isConst ? "\n};\n" : "\n}\n";
  const end = INDEX.indexOf(close, start);
  return INDEX.slice(start + 1, end + close.length - 1);
}

function indexFunctions(names, extraGlobals = {}) {
  const page = loadScripts(["ui-format.js"], { clock: new FakeClock(NOW) });
  const context = vm.createContext({
    window: page.window, document: page.document, Date: undefined, ...extraGlobals,
  });
  // Share the harness's clock-driven Date so "now" is the same everywhere.
  context.Date = vm.runInNewContext("Date");
  context.Date.now = () => NOW;
  vm.runInContext(names.map(extract).join("\n"), context);
  return context;
}

test("the helper is quiet inside the cadence and loud past it", () => {
  const page = loadScripts(["ui-format.js"], { clock: new FakeClock(NOW) });
  const format = page.window.DashboardFormat;
  assert.equal(format.staleBadge("2026-09-24T06:00:00Z", 48), "", "a day old on a daily feed is fine");
  assert.match(format.staleBadge("2026-08-19T13:32:10Z", 96), /STALE since 2026-08-19/);
  assert.match(format.staleBadge("2026-09-06", 240), /STALE since 2026-09-06/, "bare calendar dates are read too");
  assert.equal(format.staleBadge("", 48), "", "no stamp, no claim");
  assert.equal(format.staleBadge("not a date", 48), "");
  assert.deepEqual({ ...format.FEED_MAX_AGE_HOURS }, { darwin: 96, activist: 48, two_phase_watch: 240 });
});

test("activist: a daily scan last run a month ago is badged on the Last scan line", () => {
  const page = loadScripts(["ui-format.js", "activist-viz.js"], { clock: new FakeClock(NOW) });
  const state = { escapeHtml: (value) => String(value ?? ""), linkHtml: (url, label) => label, view: "active" };
  const stale = page.window.ActivistViz.renderActivistPanel({ summary: {}, feed: [], review_queue: [], last_scan: "2026-08-26T19:37:35Z" }, state);
  assert.match(stale, /Last scan: 2026-08-26T19:37:35Z <span class="badge badge-bad stale-badge"[^>]*>STALE since 2026-08-26<\/span>/);
  const fresh = page.window.ActivistViz.renderActivistPanel({ summary: {}, feed: [], review_queue: [], last_scan: "2026-09-25T06:12:00Z" }, state);
  assert.doesNotMatch(fresh, /STALE since/);
});

test("INV two-phase watch: a weekly watch three weeks old is badged in the section and the header chip", () => {
  const context = indexFunctions(["escapeHtml", "linkHtml", "feedStaleBadge", "twoPhaseRankBadge", "renderTwoPhaseWatch", "renderTwoPhaseHeaderChip"]);
  const inv = (asOf) => ({ ticker: "INV", two_phase_watch: { as_of: asOf, highest_open_rank: 4, hits: [], status: "no_material_hit", show_header_chip: true } });
  assert.match(context.renderTwoPhaseWatch(inv("2026-09-06")), /Two-phase cooling watch · 2026-09-06 <span[^>]*>STALE since 2026-09-06<\/span>/);
  assert.match(context.renderTwoPhaseHeaderChip(inv("2026-09-06")), /STALE since 2026-09-06/);
  assert.doesNotMatch(context.renderTwoPhaseWatch(inv("2026-09-20")), /STALE since/, "last Sunday's run is on time");
  assert.doesNotMatch(context.renderTwoPhaseHeaderChip(inv("2026-09-20")), /STALE since/);
});

test("Darwin: a paper book from before the refresh was disabled is badged in the subhead", () => {
  const content = { innerHTML: "", style: {} };
  const loading = { textContent: "", style: {} };
  const darwinViz = {
    destroyCharts() {}, mountCharts() {}, renderExplanation: () => "", renderPerfTable: () => "", renderChartsHtml: () => "",
  };
  const render = (generatedAt) => {
    const context = indexFunctions(["STANCE_BADGE", "DARWIN_METHOD_LABELS", "escapeHtml", "linkHtml", "feedStaleBadge", "fmtUsd", "renderDarwin"], {
      data: { darwin: { generated_at: generatedAt, tier: 1, phase: "paper", weights: [] } },
      activeDarwinAccount: "roth", activeView: "darwin", loadedShards: new Set(["file:darwin_bundle"]),
      DarwinViz: darwinViz, requestAnimationFrame: () => 0, applyDarwinView: () => {}, loadLazyFile: () => Promise.resolve(),
    });
    context.window.DarwinViz = darwinViz;
    context.document.getElementById = (id) => (id === "darwin-content" ? content : loading);
    context.renderDarwin();
    return content.innerHTML;
  };
  assert.match(render("2026-08-19T13:32:10Z"), /2026-08-19T13:32:10Z <span class="badge badge-bad stale-badge"[^>]*>STALE since 2026-08-19<\/span> · phase/);
  assert.doesNotMatch(render("2026-09-24T01:25:00Z"), /STALE since/, "last night's weekday refresh is on time");
});

test("index.html's inline scripts still compile", () => {
  const blocks = [...INDEX.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  assert.ok(blocks.length > 0);
  for (const block of blocks) new vm.Script(block);
});
