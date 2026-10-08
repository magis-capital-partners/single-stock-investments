import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { evaluateOverlap, leverageOf } from "../functions/_lib/overlap_map.js";

const fixture = JSON.parse(readFileSync(
  new URL("../../_system/scripts/tests/fixtures/overlap_map_mini.json", import.meta.url),
  "utf8",
));

test("owned-book overlap matches the toy book and HubCo is the hub holder", () => {
  const panel = evaluateOverlap({
    names: fixture.names,
    scope: "owned",
    positions: fixture.positions,
    asOf: "2026-10-07",
    quarter: "2026Q2",
  });
  assert.equal(panel.stress.hub_holder.fund_id, "hubco");
  assert.ok(Math.abs(panel.stress.hub_holder.overlap_share - 0.8) < 1e-12);
  const other = panel.stress.random_holder;
  assert.ok(other);
  assert.notEqual(other.fund_id, "hubco");
  const shares = {
    hubco: 0.8,
    otherco: 0.5,
    levered: 0.5,
  };
  assert.ok(Math.abs(shares[panel.stress.hub_holder.fund_id] - panel.stress.hub_holder.overlap_share) < 1e-12);
});

test("EEE is a hub name and DDD is not, and the universe scope has no NAV stress", () => {
  const panel = evaluateOverlap({ names: fixture.names, scope: "universe" });
  const eee = panel.rows.find((row) => row.ticker === "EEE");
  const ddd = panel.rows.find((row) => row.ticker === "DDD");
  assert.equal(eee.hub_name, true);
  assert.ok(Math.abs(eee.top_share - 0.9) < 1e-12);
  assert.equal(ddd.hub_name, false);
  assert.equal(panel.stress, null);
  assert.ok(panel.rows.some((row) => row.ticker === "DDD"));
  assert.ok(panel.rows.some((row) => row.ticker === "EEE"));
});

test("only the leveraged ETF is above the threshold, and silence is not reported", () => {
  const panel = evaluateOverlap({ names: fixture.names, scope: "universe" });
  const aaa = panel.rows.find((row) => row.ticker === "AAA");
  assert.ok(aaa.leverage_above >= 1);
  for (const ticker of ["BBB", "CCC", "DDD", "EEE"]) {
    const row = panel.rows.find((item) => item.ticker === ticker);
    assert.equal(row.leverage_above, 0);
    assert.equal(row.leverage_text, "not reported");
  }
  const silent = leverageOf({ fund_id: "x" });
  assert.equal(silent.text, "not reported");
  assert.equal(silent.above, false);
  assert.equal(JSON.stringify(silent).includes("unlevered"), false);
});

test("HubCo and OtherCo overlap on the smaller shared holding", () => {
  const panel = evaluateOverlap({ names: fixture.names, scope: "universe" });
  const pair = panel.pairs.find((item) => {
    const ids = [item.left.fund_id, item.right.fund_id].sort().join("|");
    return ids === "hubco|otherco";
  });
  assert.ok(pair);
  assert.equal(pair.overlap_dollars, 100);
  assert.equal(pair.shared_names, 1);
});

test("the panel copy does not use sizing or valuation language", () => {
  const source = readFileSync(new URL("../overlap-viz.js", import.meta.url), "utf8");
  for (const phrase of ["target weight", "fair value", "buy", "sell", "IRR", "house", "default", "cascade probability", "stable", "unstable", "unlevered"]) {
    assert.equal(source.toLowerCase().includes(phrase.toLowerCase()), false, phrase);
  }
});
