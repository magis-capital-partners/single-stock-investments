// The portfolio page itself, run in a Node vm against scripted API answers.
//
// Two behaviours are pinned here because both cost something real when wrong:
//
//   * The Orders view's ticket poll. It was a bare 1 Hz setInterval with no
//     end: a ticket nothing would advance kept every open tab reading D1 once a
//     second forever, hidden or not. It must now run fast for a minute, slow
//     after, stop at a bound, pause while hidden and resume on focus.
//
//   * The cockpit on a Flex EOD snapshot. The statement states NAV; margin,
//     buying power and daily P&L exist only on the live account summary. Those
//     must read as absent and "not in Flex EOD" -- not "IBKR live" -- and a
//     fresh statement must read "EOD snapshot as of <date>", not "Broker feed
//     stopped".

import assert from "node:assert/strict";
import test from "node:test";

import { FakeClock, loadScripts, settle } from "./spa-harness.mjs";

const SCRIPTS = ["ui-format.js", "portfolio-viz.js"];

function book(snapshot, accountValues) {
  return {
    schema_version: "portfolio_read_model.v1", status: "complete", scope: "all",
    snapshot: { source_run_id: "run-1", account_alias: "U805366", base_currency: "USD", ...snapshot },
    account_values: accountValues, positions: [], cash_events: [], reconciliation_breaks: [],
    broker_position_count: 0, owner_position_count: 0, allocation_status: "not_applicable", broker_open_order_count: 0,
  };
}

const eodBook = (overrides = {}) => book(
  { as_of: "2026-09-24T22:15:14Z", feed: "flex_eod", session_date: "2026-09-24", age_seconds: 56_000, stale: false, ...overrides },
  [
    { tag: "NetLiquidation", value_decimal: "11867165.25", currency: "USD" },
    { tag: "TotalCashValue", value_decimal: "1150000.25", currency: "USD" },
  ],
);

const collectorBook = () => book(
  { as_of: "2026-08-25T15:26:01Z", feed: "live", age_seconds: 30 * 86_400, stale: true },
  [
    { tag: "NetLiquidation", value_decimal: "11870000", currency: "USD" },
    { tag: "MaintMarginReq", value_decimal: "2000000", currency: "USD" },
    { tag: "ExcessLiquidity", value_decimal: "9000000", currency: "USD" },
    { tag: "BuyingPower", value_decimal: "30000000", currency: "USD" },
  ],
);

function routesFor({ bookBody, tickets = () => [] }) {
  return (url) => {
    if (url.startsWith("/api/v2/portfolio/book")) return bookBody;
    if (url.startsWith("/api/v2/portfolio/performance")) return { nav_series: [], rolling: [] };
    if (url.startsWith("/api/v2/portfolio/orders")) return { events: [], broker_open_orders: [] };
    if (url.startsWith("/api/v2/portfolio/paper-orders")) return { orders: [], viewer: { order_owner: "drew", email: "drew@example.com" } };
    if (url.startsWith("/api/v2/portfolio/order-intents")) return { requests: tickets(), viewer: { order_owner: "drew" } };
    return {};
  };
}

async function openPortfolio(page, section = "positions", scope = "all") {
  page.window.PortfolioViz.setRoute(scope, section);
  page.window.PortfolioViz.openPortfolio(() => {});
  await settle();
  return page.element("portfolio-content").innerHTML;
}

// ------------------------------------------------------------ Flex EOD cockpit

test("a fresh EOD snapshot reads as an EOD statement, not a stopped feed", async () => {
  const page = loadScripts(SCRIPTS, { routes: routesFor({ bookBody: eodBook() }) });
  const html = await openPortfolio(page);
  assert.match(html, /EOD snapshot as of 2026-09-24/);
  assert.doesNotMatch(html, /Broker feed stopped/);
  assert.match(html, /as of 2026-09-24 · daily P&amp;L not in Flex EOD/, "the caption under NAV is the statement date");
});

test("fields Flex cannot state are absent and labelled, never 'IBKR live'", async () => {
  const page = loadScripts(SCRIPTS, { routes: routesFor({ bookBody: eodBook() }) });
  const html = await openPortfolio(page);
  assert.doesNotMatch(html, /IBKR live/, "nothing on an EOD statement is live");
  for (const label of ["Daily P&amp;L", "Buying power", "Initial margin", "Maintenance margin", "Excess liquidity"]) {
    const fact = html.split('class="ph-fact ph-lineage-target"').find((chunk) => chunk.includes(`<div class="ph-fact-label">${label}</div>`));
    assert.ok(fact, `${label} fact rendered`);
    assert.match(fact, /<div class="ph-fact-value">—<\/div>/, `${label} shows a dash`);
    assert.match(fact, /<div class="ph-fact-source">not in Flex EOD<\/div>/, `${label} says why`);
  }
  assert.match(html, /IBKR Flex EOD/, "NAV names its real source");
});

test("a late EOD statement says it is late, with its date", async () => {
  const page = loadScripts(SCRIPTS, { routes: routesFor({ bookBody: eodBook({ stale: true, age_seconds: 4 * 86_400 }) }) });
  const html = await openPortfolio(page);
  assert.match(html, /EOD feed stale · last snapshot 2026-09-24 \(4 days ago\)/);
});

test("the live-feed wording is unchanged for the collector's snapshot", async () => {
  const page = loadScripts(SCRIPTS, { routes: routesFor({ bookBody: collectorBook() }) });
  const html = await openPortfolio(page);
  assert.match(html, /Broker feed stopped · last snapshot 30 days ago/);
  assert.match(html, /IBKR live/);
  assert.doesNotMatch(html, /not in Flex EOD/);
});

test("the margin tab on an EOD snapshot explains that margin is not in the statement", async () => {
  const page = loadScripts(SCRIPTS, { routes: routesFor({ bookBody: eodBook() }) });
  const html = await openPortfolio(page, "margin");
  assert.match(html, /Margin is not in Flex EOD\./);
  assert.doesNotMatch(html, /needs another observation/);
});

// ------------------------------------------------------------- ticket polling

const stuckTicket = () => [{
  request_id: "r1", owner: "drew", symbol: "MSFT", sec_type: "STK", action: "BUY", quantity_decimal: "1",
  limit_price_decimal: "400", mode: "paper", state: "requested", created_at: "2026-09-25T13:59:00Z",
}];

const intentPolls = (page) => page.fetches.filter((url) => url.startsWith("/api/v2/portfolio/order-intents")).length;

test("a stuck ticket is polled fast for a minute, slowly after, then not at all", async () => {
  const clock = new FakeClock();
  const page = loadScripts(SCRIPTS, { clock, routes: routesFor({ bookBody: collectorBook(), tickets: stuckTicket }) });
  await openPortfolio(page, "orders");
  const opened = intentPolls(page);

  await clock.advance(60_000);
  const firstMinute = intentPolls(page) - opened;
  assert.ok(firstMinute >= 55 && firstMinute <= 61, `~1 Hz for the first minute, got ${firstMinute}`);

  await clock.advance(240_000);
  const slow = intentPolls(page) - opened - firstMinute;
  assert.ok(slow >= 44 && slow <= 49, `~every 5s for the next four minutes, got ${slow}`);

  const atBound = intentPolls(page);
  await clock.advance(600_000);
  assert.equal(intentPolls(page), atBound, "no polling once the bound is spent");
  assert.match(page.element("portfolio-content").innerHTML, /data-ph-poll-paused/, "and the ticket says so");
});

test("a hidden tab does not poll, and showing it again resumes", async () => {
  const clock = new FakeClock();
  const page = loadScripts(SCRIPTS, { clock, routes: routesFor({ bookBody: collectorBook(), tickets: stuckTicket }) });
  await openPortfolio(page, "orders");
  await clock.advance(10_000);

  page.setHidden(true);
  const hiddenAt = intentPolls(page);
  await clock.advance(120_000);
  assert.equal(intentPolls(page), hiddenAt, "a background tab reads nothing");

  page.setHidden(false);
  await clock.advance(3_000);
  assert.ok(intentPolls(page) >= hiddenAt + 2, "visible again: back to the fast cadence");
});

test("focus after the bound starts a fresh fast minute", async () => {
  const clock = new FakeClock();
  const page = loadScripts(SCRIPTS, { clock, routes: routesFor({ bookBody: collectorBook(), tickets: stuckTicket }) });
  await openPortfolio(page, "orders");
  await clock.advance(400_000);
  const paused = intentPolls(page);
  page.focus();
  await clock.advance(5_000);
  assert.ok(intentPolls(page) >= paused + 4, "a returning human gets 1 Hz again");
});

test("a ticket that finishes stops the poll for good", async () => {
  const clock = new FakeClock();
  let calls = 0;
  const tickets = () => {
    calls += 1;
    return [{ ...stuckTicket()[0], state: calls > 3 ? "filled" : "requested" }];
  };
  const page = loadScripts(SCRIPTS, { clock, routes: routesFor({ bookBody: collectorBook(), tickets }) });
  await openPortfolio(page, "orders");
  await clock.advance(10_000);
  const done = intentPolls(page);
  await clock.advance(120_000);
  page.focus();
  await clock.advance(10_000);
  assert.equal(intentPolls(page), done, "a filled ticket is never polled again, focus or not");
});
