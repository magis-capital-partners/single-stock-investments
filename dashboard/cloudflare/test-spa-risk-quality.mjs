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
  assert.match(css, /\.risk-component-head \.is-delayed, \.risk-component-head \.is-lagging \{ color: #f5b942; \}/, "amber, like delayed");
});

test("unknown states still fall through to the unavailable style", () => {
  const html = renderComponents([component({ quality_state: "mystery_state" })]);
  assert.match(html, /<b class="is-unavailable">mystery state<\/b>/);
  assert.doesNotMatch(html, / lagging · /);
});
