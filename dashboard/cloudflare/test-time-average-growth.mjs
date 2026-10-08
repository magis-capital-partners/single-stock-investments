import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import {
  annotationStatus,
  evaluateSleeve,
  itoDrag,
  leverageObjects,
} from "../functions/_lib/time_average_growth.js";

const figures = JSON.parse(readFileSync(
  new URL("../../_system/scripts/tests/fixtures/peters_2009_fig1.json", import.meta.url),
  "utf8",
));

test("figure 1 matches Peters: l_opt is excess over variance, and t_c is between 4 and 5 years", () => {
  const fig = figures.figure_1;
  const out = leverageObjects({ muExcess: fig.mu_excess, sigma: fig.sigma, riskless: fig.riskless });
  assert.ok(Math.abs(out.lOpt - fig.mu_excess / (fig.sigma ** 2)) < 1e-12);
  assert.ok(out.tC > fig.t_c_years_between[0] && out.tC < fig.t_c_years_between[1]);
});

test("figure 2 matches Peters: negative growth, l_opt near 0.247, l_c near 0.494", () => {
  const fig = figures.figure_2;
  const out = leverageObjects({ muExcess: fig.mu_excess, sigma: fig.sigma, riskless: fig.riskless });
  assert.ok(Math.abs(out.growthAtFull - fig.growth) < 1e-12);
  assert.ok(Math.abs(out.lOpt - fig.l_opt) < 1e-12);
  assert.ok(Math.abs(out.lC - fig.l_c) < 1e-12);
});

test("a drift band that straddles today's scale stays unidentified even though a point l_opt exists", () => {
  const call = annotationStatus({
    lOptLow: 0.4,
    lOptHigh: 1.4,
    lNow: 0.9,
    tC: 1.2,
    n: 252,
    hedged: false,
    lowCoverage: false,
  });
  assert.equal(call.status, "unidentified");
  assert.equal(call.showScale, false);
  assert.deepEqual(call.reasons, ["straddles"]);
});

test("Itô drag does not move when the drift input changes", () => {
  const sigma = 0.18;
  const drag = itoDrag(1.2, sigma);
  const cool = leverageObjects({ muExcess: 0.02, sigma, riskless: 0.04 });
  const warm = leverageObjects({ muExcess: 0.09, sigma, riskless: 0.04 });
  assert.notEqual(cool.lOpt, warm.lOpt);
  assert.equal(itoDrag(1.2, sigma), drag);
  assert.equal(drag, (1.2 ** 2) * (sigma ** 2) / 2);
});

test("a hedged book withholds the scale and still reports growth", () => {
  const returns = path(252, 0.0004, 0.01);
  const panel = evaluateSleeve({
    nav: 1000,
    positions: [
      { ticker: "LONG", market_value: 400, sec_type: "STK" },
      { ticker: "SHORT", market_value: -400, sec_type: "STK" },
    ],
    params: params({
      LONG: returns,
      SHORT: returns.map((row) => ({ date: row.date, r: -row.r })),
    }),
  });
  assert.equal(panel.annotation.show_scale, false);
  assert.ok(panel.annotation.reasons.includes("hedged"));
  assert.ok(panel.headline);
  assert.equal(panel.annotation.l_opt, null);
});

test("coverage under half of NAV withholds the scale", () => {
  const panel = book(path(252, 0.01, 0.005), 0.02, { marketValue: 100, nav: 1000 });
  assert.ok(panel.headline.coverage < 0.5);
  assert.equal(panel.annotation.show_scale, false);
  assert.ok(panel.annotation.reasons.includes("low_coverage"));
  assert.equal(panel.names.length, 1);
});

test("fewer than 252 shared sessions withholds the scale", () => {
  const left = [];
  const right = [];
  for (let index = 0; index < 252; index += 1) {
    const day = new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10);
    left.push({ date: day, r: 0.001 + 0.01 * Math.sin(index / 3) });
  }
  for (let index = 0; index < 252; index += 1) {
    const day = new Date(Date.UTC(2025, 0, 80 + index)).toISOString().slice(0, 10);
    right.push({ date: day, r: 0.001 + 0.01 * Math.sin(index / 5) });
  }
  const panel = evaluateSleeve({
    nav: 1000,
    positions: [
      { ticker: "AAA", market_value: 500, sec_type: "STK" },
      { ticker: "BBB", market_value: 500, sec_type: "STK" },
    ],
    params: params({ AAA: left, BBB: right }),
  });
  assert.ok(panel.headline.sessions < 252);
  assert.equal(panel.annotation.status, "unidentified");
  assert.equal(panel.annotation.show_scale, false);
  assert.ok(panel.annotation.reasons.includes("short_window"));
  assert.equal(panel.annotation.l_opt, null);
});

test("options stay out of the mix and are named as omitted", () => {
  const panel = evaluateSleeve({
    nav: 100,
    positions: [
      { ticker: "GTX", market_value: 80, sec_type: "STK" },
      { ticker: "GTX", market_value: 20, sec_type: "OPT" },
    ],
    params: params({ GTX: path(252, 0.0003, 0.01) }),
  });
  assert.equal(panel.names.length, 1);
  assert.equal(panel.omitted[0].reason, "not_stock");
  assert.ok(panel.headline.coverage < 1);
});

test("the panel copy does not use sizing or valuation language", () => {
  const source = readFileSync(new URL("../sleeve-viz.js", import.meta.url), "utf8");
  const start = source.indexOf("function renderTimeAverage");
  const end = source.indexOf("function pctPlain");
  const body = source.slice(start, end);
  for (const phrase of ["target weight", "fair value", "buy", "sell", "IRR", "house"]) {
    assert.equal(body.toLowerCase().includes(phrase.toLowerCase()), false, phrase);
  }
});
test("the sleeve endpoint refuses every owner except Michael", async () => {
  const { onRequestGet } = await import("../functions/api/v1/sleeves/time-average.js");
  const response = await onRequestGet({
    request: new Request("https://example.com/api/v1/sleeves/time-average?owner=drew"),
    env: {},
  });
  assert.equal(response.status, 400);
  const body = await response.json();
  assert.match(body.error, /Michael/);
});

function path(n, drift, noise) {
  const rows = [];
  for (let index = 0; index < n; index += 1) {
    const day = new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10);
    const wave = noise * Math.sin(index / 3);
    rows.push({ date: day, r: drift + wave });
  }
  return rows;
}

function params(symbols) {
  const packed = {};
  for (const [ticker, returns] of Object.entries(symbols)) {
    packed[ticker] = { ok: true, returns, end: returns.at(-1).date, stale: false };
  }
  return { riskless: { series: "DGS3MO", as_of: "2026-10-06", continuous: 0.04 }, symbols: packed };
}

function book(returns, riskless, shape = {}) {
  const marketValue = shape.marketValue ?? 500;
  const nav = shape.nav ?? 1000;
  return evaluateSleeve({
    nav,
    positions: [{ ticker: "AAA", market_value: marketValue, sec_type: "STK" }],
    params: {
      riskless: { series: "DGS3MO", as_of: "2026-10-06", continuous: riskless },
      symbols: { AAA: { ok: true, returns, end: returns.at(-1).date, stale: false } },
    },
  });
}
