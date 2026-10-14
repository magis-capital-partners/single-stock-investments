// The tail panel on Michael's sleeve: Hill exponent, Noah share, max-to-sum,
// and a seeded Monte Carlo whose drift is the bill, never last year's gain.

import assert from "node:assert/strict";
import test from "node:test";

import {
  blockBootstrapDraw,
  evaluateTailRisk,
  excessKurtosis,
  hillIndex,
  maxDrawdown,
  maxToSum,
  mulberry32,
  normal,
  seedFrom,
  simulate,
  studentT,
  tailReading,
} from "../functions/_lib/tail_risk.js";
import { evaluateSleeve, varianceShares } from "../functions/_lib/time_average_growth.js";

function params(symbols, riskless = 0.04) {
  const packed = {};
  for (const [ticker, returns] of Object.entries(symbols)) {
    packed[ticker] = { ok: true, returns, end: returns.at(-1).date, stale: false };
  }
  return { riskless: { series: "DGS3MO", as_of: "2026-10-06", continuous: riskless }, symbols: packed };
}

function dated(values) {
  return values.map((r, index) => ({ date: new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10), r }));
}

function gaussianPath(n, sigma, seed = 7) {
  const rng = mulberry32(seed);
  const out = [];
  for (let index = 0; index < n; index += 1) out.push(sigma * normal(rng));
  return out;
}

test("the Hill estimator recovers a Pareto exponent", () => {
  const rng = mulberry32(11);
  const alpha = 3;
  const sample = [];
  for (let index = 0; index < 20000; index += 1) sample.push(Math.pow(1 - rng(), -1 / alpha));
  const hill = hillIndex(sample);
  assert.ok(Math.abs(hill.alpha - alpha) < 0.2, `alpha ${hill.alpha}`);
  assert.equal(hill.k, 2000);
  assert.ok(hill.se < hill.alpha);
});

test("a short sample refuses to invent an exponent", () => {
  assert.equal(hillIndex([1, 2, 3, 4, 5]), null);
  assert.equal(hillIndex(new Array(10).fill(1)), null);
  assert.match(tailReading(null), /Too few/);
  assert.match(tailReading(1.8), /not finite/);
  assert.match(tailReading(2.5), /infinite kurtosis/);
});

test("Noah-style statistics read a dominated series as dominated", () => {
  const quiet = new Array(251).fill(0.001);
  const dominated = [...quiet, -0.3];
  assert.ok(maxToSum(dominated) > 0.9);
  assert.ok(maxToSum(quiet) < 0.01);
  assert.ok(excessKurtosis(dominated) > 100);
  assert.ok(Math.abs(maxDrawdown([0.1, -0.5, 0.2]) - 0.5) < 1e-12);
});

test("the Gaussian model lands on its own arithmetic", () => {
  // sigma 1% a day for 252 days with no drift: terminal log return has sd
  // about 0.159, so the 5th percentile sits near -23% and the median near -1%.
  const sigma = 0.01;
  const out = simulate((rng) => sigma * normal(rng), { rng: mulberry32(3), paths: 4000, horizon: 252 });
  assert.ok(out.terminal.p05 > -0.30 && out.terminal.p05 < -0.17, `p05 ${out.terminal.p05}`);
  assert.ok(Math.abs(out.terminal.p50 + 0.012) < 0.03, `p50 ${out.terminal.p50}`);
  assert.ok(out.drawdown_probability["0.2"] > out.drawdown_probability["0.3"]);
  assert.ok(out.loss_probability["0.5"] < 0.01);
});

test("a Student t with the same scale has a fatter tail than the Gaussian", () => {
  const nu = 2.5;
  const scale = 0.01 * Math.sqrt((nu - 2) / nu);
  const fat = simulate((rng) => scale * studentT(rng, nu), { rng: mulberry32(5), paths: 3000, horizon: 252 });
  const thin = simulate((rng) => 0.01 * normal(rng), { rng: mulberry32(5), paths: 3000, horizon: 252 });
  assert.ok(fat.drawdown_probability["0.5"] > thin.drawdown_probability["0.5"]);
  assert.ok(fat.terminal.expected_shortfall_05 < thin.terminal.expected_shortfall_05);
});

test("the block bootstrap only ever replays observed days", () => {
  const sample = [-0.05, 0.01, 0.02, -0.01];
  const draw = blockBootstrapDraw(sample);
  const rng = mulberry32(9);
  const seen = new Set();
  for (let index = 0; index < 500; index += 1) seen.add(draw(rng));
  assert.deepEqual([...seen].sort(), sample.slice().sort());
});

test("the same book on the same date simulates the same numbers", () => {
  const AAA = dated(gaussianPath(260, 0.02, 1));
  const BBB = dated(gaussianPath(260, 0.015, 2));
  const build = () => evaluateTailRisk({
    nav: 1000,
    asOf: "2026-10-07",
    positions: [{ ticker: "AAA", market_value: 600, sec_type: "STK" }, { ticker: "BBB", market_value: 300, sec_type: "STK" }],
    params: params({ AAA, BBB }),
    paths: 300,
  });
  const first = build();
  const second = build();
  assert.deepEqual(first.simulation.models.bootstrap, second.simulation.models.bootstrap);
  assert.equal(first.simulation.drift, "riskless");
  assert.equal(first.window.sessions, 260);
  assert.ok(first.book.hill_left && first.book.hill_left.k >= 10);
  assert.equal(first.concentration.ticker, "AAA");
  assert.ok(Math.abs(first.concentration.book_hit_if_halved + 0.3) < 1e-12);
  assert.notEqual(seedFrom("a"), seedFrom("b"));
});

test("a book with no eligible names reports why instead of a simulation", () => {
  const panel = evaluateTailRisk({
    nav: 100,
    positions: [{ ticker: "GTX", market_value: 100, sec_type: "OPT" }],
    params: params({ GTX: dated(gaussianPath(252, 0.01)) }),
  });
  assert.equal(panel.simulation, null);
  assert.equal(panel.reason, "no_eligible_names");
  assert.equal(panel.omitted[0].reason, "not_stock");
});

test("the past year's gain is not projected: a strong year still simulates at the bill", () => {
  const strong = dated(gaussianPath(252, 0.01, 4).map((value) => value + 0.004));
  const panel = evaluateTailRisk({
    nav: 100,
    asOf: "2026-10-07",
    positions: [{ ticker: "AAA", market_value: 100, sec_type: "STK" }],
    params: params({ AAA: strong }, 0.04),
    paths: 1500,
  });
  const median = panel.simulation.models.bootstrap.terminal.p50;
  assert.ok(median < 0.15, `median ${median} should sit near the bill, not near the sample's +170%`);
});

test("variance shares sum to one and the dominant name takes most of the drag", () => {
  const big = dated(gaussianPath(252, 0.03, 21));
  const small = dated(gaussianPath(252, 0.01, 22));
  const panel = evaluateSleeve({
    nav: 1000,
    positions: [{ ticker: "GTX", market_value: 400, sec_type: "STK" }, { ticker: "JPM", market_value: 200, sec_type: "STK" }],
    params: params({ GTX: big, JPM: small }),
  });
  const total = panel.names.reduce((sum, row) => sum + row.drag_share, 0);
  assert.ok(Math.abs(total - 1) < 1e-9);
  assert.equal(panel.names[0].ticker, "GTX");
  assert.ok(panel.names[0].drag_share > 0.8);
  const points = panel.names.reduce((sum, row) => sum + row.drag_points, 0);
  assert.ok(Math.abs(points - panel.headline.ito_drag) < 1e-9);
  const empty = varianceShares([], []);
  assert.equal(empty.size, 0);
});

test("the tail endpoint refuses every owner except Michael", async () => {
  const { onRequestGet } = await import("../functions/api/v1/sleeves/tail-risk.js");
  const response = await onRequestGet({
    request: new Request("https://example.com/api/v1/sleeves/tail-risk?owner=drew"),
    env: {},
  });
  assert.equal(response.status, 400);
  const body = await response.json();
  assert.match(body.error, /Michael/);
});
