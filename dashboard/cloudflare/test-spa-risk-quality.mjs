// Component quality on the market-risk page: a lagging feed is late, not dead.
//
// The daily capitulation feed now reports quality_state "lagging" when its
// latest run is behind the session it should cover. qualityMeta had no entry
// for it, so it fell through to the red "unavailable" style reserved for
// sources with no data at all. It must read as its own amber state.

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { FakeClock, loadScripts } from "./spa-harness.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const NOW = Date.parse("2026-09-25T14:00:00Z");

const component = (overrides) => ({
  component: "capitulation_daily", scope: "market", symbol: "SPY", label: "Capitulation",
  as_of: "2026-09-25T00:00:00Z", value: 1, unit: "index_points", source: "capitulation_daily", ...overrides,
});

function renderComponents(components) {
  const page = loadScripts(["ui-format.js", "criticality-viz.js"], { clock: new FakeClock(NOW) });
  return page.window.CriticalityViz.renderRiskView({ components }, {}, {});
}

test("a lagging feed gets its own amber label, not the unavailable style", () => {
  const html = renderComponents([component({ quality_state: "lagging" }), component({ component: "vix_regime", symbol: "VIX", quality_state: "ready" })]);
  assert.match(html, /<b class="is-lagging">Lagging: behind the expected session<\/b>/);
  assert.doesNotMatch(html, /<b class="is-unavailable">lagging<\/b>/);
  assert.match(html, /1 lagging · /, "the coverage line counts it");
  const css = readFileSync(join(HERE, "..", "index.html"), "utf8");
  assert.match(css, /\.risk-component-head \.is-delayed, \.risk-component-head \.is-lagging \{ color: var\(--warning\); \}/, "amber, like delayed");
});

test("unknown states still fall through to the unavailable style", () => {
  const html = renderComponents([component({ quality_state: "mystery_state" })]);
  assert.match(html, /<b class="is-unavailable">mystery state<\/b>/);
  assert.doesNotMatch(html, / lagging · /);
});

function reconciliation(intraday, close) {
  return renderComponents([
    component({component:'letf_rebalance_intraday',quality_state:'ready',value:-100,cadence:'intraday',universe_hash:'fixture',...intraday}),
    component({component:'letf_rebalance_close',quality_state:'ready',value:100,cadence:'daily',universe_hash:'fixture',...close}),
  ]);
}

test('different trading dates never receive a disagreement verdict or a numeric gap', () => {
  const html=reconciliation({as_of:'2026-09-25T01:00:00Z'},{as_of:'2026-09-25T20:00:00Z'});
  assert.match(html,/Different trading dates/,'01:00 UTC still belongs to the prior New York date');
  assert.doesNotMatch(html,/Same-session estimates differ|<dt>Difference<\/dt>|At least one is wrong/);
});

test('matching dates compare modeled flows and disclose opposite directions', () => {
  const html=reconciliation({as_of:'2026-09-24T19:50:00Z'},{as_of:'2026-09-24T20:00:00Z'});
  assert.match(html,/Same-session estimates differ/);
  assert.match(html,/<dt>Difference<\/dt>/);
  assert.match(html,/Both are modeled flows, not observed orders/);
});

test('old or undated components cannot receive a positive agreement judgment', () => {
  const html=reconciliation({as_of:'2026-09-14T19:50:00Z'},{as_of:'2026-09-14T20:00:00Z'});
  assert.match(html,/Older estimates/);
  assert.doesNotMatch(html,/Same-session estimates are broadly aligned|<dt>Difference<\/dt>/);
  assert.doesNotMatch(reconciliation({as_of:null},{as_of:null}),/Same-session estimates/);
});

test('a daily Friday close does not become stale over the weekend', () => {
  const page=loadScripts(['ui-format.js','criticality-viz.js'],{clock:new FakeClock(Date.parse('2026-09-28T12:00:00Z'))});
  const html=page.window.CriticalityViz.renderRiskView({components:[component({as_of:'2026-09-25T20:00:00Z',cadence:'daily',quality_state:'ready'})]}, {}, {});
  assert.match(html,/<b class="is-ready">Current<\/b>/);
});
