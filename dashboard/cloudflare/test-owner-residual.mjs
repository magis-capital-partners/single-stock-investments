import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { loadPortfolio } from "../functions/_lib/portfolio.js";
import {
  classifyPolicyPosition,
  classifyPosition,
  drewSymbolsFromSleeveRows,
  lsUniverseSymbols,
  michaelResidualPositions,
  normSym,
} from "../functions/_lib/owner_residual.js";

const canonicalUniverse = fileURLToPath(new URL("../../_system/trading/sleeves/data/etf_ls_universe.json", import.meta.url));
const stagedUniverse = fileURLToPath(new URL("../data/etf_ls_universe.json", import.meta.url));

function position(overrides) {
  return {
    account_alias: "U805366",
    conid: 1,
    model_code: "",
    symbol: "CSU",
    local_symbol: "CSU",
    description: "Constellation Software",
    sec_type: "STK",
    currency: "USD",
    native_currency: "USD",
    base_currency: "USD",
    quantity_decimal: "12",
    market_value_decimal: "1200",
    market_value_base_decimal: "1200",
    ...overrides,
  };
}

test("the staged LS universe is the sleeve universe, not a second list", () => {
  const canonical = JSON.parse(readFileSync(canonicalUniverse, "utf8"));
  const staged = JSON.parse(readFileSync(stagedUniverse, "utf8"));
  assert.deepEqual(staged.symbols, canonical.symbols);
  assert.equal(lsUniverseSymbols().has("AAPL"), true);
  assert.equal(lsUniverseSymbols().has("NVDA"), true);
  assert.equal(lsUniverseSymbols().has("APLD"), true);
  assert.equal(lsUniverseSymbols().has("CSU"), false);
  assert.equal(lsUniverseSymbols().has("GTX"), false);
  assert.equal(normSym("BRK.B"), "BRK-B");
});

test("policy matches the owner-custody exclusions", () => {
  const ls = lsUniverseSymbols();
  const drew = new Set(["IBKR"]);
  const policy = (row) => classifyPolicyPosition(row, { lsSymbols: ls, drewSymbols: drew });

  assert.deepEqual(
    policy({ symbol: "CSU", local_symbol: "CSU", sec_type: "STK" }),
    { owner: "michael", strategy: "single_stock", reason: "michael_residual_book", bucket: null },
  );
  assert.equal(policy({ symbol: "AAPL", local_symbol: "AAPL", sec_type: "STK" }).owner, "unallocated");
  assert.equal(policy({ symbol: "AAPL", local_symbol: "AAPL", sec_type: "STK" }).strategy, "letf");
  // LS universe wins over a Drew tag on the same shares.
  assert.equal(
    classifyPolicyPosition(
      { symbol: "AAPL", local_symbol: "AAPL", sec_type: "STK" },
      { lsSymbols: new Set(["AAPL"]), drewSymbols: new Set(["AAPL"]) },
    ).owner,
    "unallocated",
  );

  const spx = policy({
    symbol: "SPX", local_symbol: "SPXW  260817P05000000", sec_type: "OPT", underlying: "SPX",
  });
  assert.equal(spx.strategy, "spx_0dte");
  assert.equal(spx.owner, "unallocated");

  // Flex stores the OCC string in symbol and does not store underlyingSymbol.
  const xsp = policy({ symbol: "XSP   270129P00540000", local_symbol: "XSP   270129P00540000", sec_type: "OPT" });
  assert.deepEqual(
    { owner: xsp.owner, strategy: xsp.strategy, bucket: xsp.bucket, reason: xsp.reason },
    { owner: "unallocated", strategy: "ls_algo", bucket: "index_put_hedge", reason: "index_put_hedge" },
  );
  const spxw = policy({ symbol: "SPXW  260817P05000000", local_symbol: "SPXW  260817P05000000", sec_type: "OPT" });
  assert.equal(spxw.strategy, "spx_0dte");
  // Flex often stores the OCC local symbol and no underlying. The root is
  // supplied as `underlying`, which is the field the existing rule reads.
  // Without that, "SPX   ..." is not the symbol SPX and would stay on Michael.
  const spxOcc = policy({ symbol: "SPX   260817P05000000", local_symbol: "SPX   260817P05000000", sec_type: "OPT" });
  assert.equal(spxOcc.strategy, "spx_0dte");

  const overlay = policy({ symbol: "APLD  261009C00038000", local_symbol: "APLD  261009C00038000", sec_type: "OPT" });
  assert.equal(overlay.owner, "drew");
  assert.equal(overlay.strategy, "letf_option_overlay");
  assert.equal(overlay.reason, "ls_algo_option_overlay");

  const shares = policy({ symbol: "APLD", local_symbol: "APLD", sec_type: "STK" });
  assert.equal(shares.strategy, "letf");

  assert.equal(policy({ symbol: "IBKR", local_symbol: "IBKR", sec_type: "STK" }).owner, "drew");
  assert.equal(policy({ symbol: "GTX", local_symbol: "GTX", sec_type: "STK" }).owner, "michael");
  assert.equal(policy({ symbol: "USD", local_symbol: "USD", sec_type: "CASH" }).reason, "michael_residual_book");

  // The allocation policy does not pass openDateTime, so an undated or dated
  // folded 3905.T stays Michael unless the ticker is in drew_symbols.
  const dated = policy({ symbol: "3905.T", local_symbol: "3905.T", sec_type: "STK", openDateTime: "20260913;211246" });
  assert.equal(dated.owner, "michael");
  const tagged = classifyPosition(
    { symbol: "3905.T", secType: "STK", openDateTime: "20260913;211246" },
    { etfLsSymbols: [], drewSymbols: [] },
  );
  assert.equal(tagged.bucket, "drew");
});

test("drew symbols are sleeve stock holdings, and a shared name stays untagged", () => {
  const symbols = drewSymbolsFromSleeveRows([
    { owner: "drew", ticker: "IBKR", sec_type: "STK", classifier_reason: "drew_new" },
    { owner: "drew", ticker: "3905.T", sec_type: "STK", classifier_reason: "drew_new" },
    { owner: "michael", ticker: "3905.T", sec_type: "STK", classifier_reason: "residual" },
    { owner: "drew", ticker: "APLD", sec_type: "OPT", classifier_reason: "ls_algo_option_overlay" },
  ]);
  assert.deepEqual([...symbols], ["IBKR"]);
});

test("residual rows keep broker market value by allocating the full quantity", () => {
  const rows = michaelResidualPositions([
    position({ conid: 1, symbol: "CSU", local_symbol: "CSU", quantity_decimal: "12", market_value_base_decimal: "1200" }),
    position({ conid: 2, symbol: "AAPL", local_symbol: "AAPL", quantity_decimal: "4", market_value_base_decimal: "800" }),
    position({
      conid: 3, symbol: "SPXW  260817P05000000", local_symbol: "SPXW  260817P05000000",
      sec_type: "OPT", quantity_decimal: "-1", market_value_base_decimal: "-100",
    }),
  ], { drewSymbols: [] });
  assert.deepEqual(rows.map((row) => row.symbol), ["CSU"]);
  assert.equal(rows[0].allocations[0].owner, "michael");
  assert.equal(rows[0].allocations[0].quantity_decimal, "12");
  const brokerQty = Number(rows[0].quantity_decimal);
  const allocated = Number(rows[0].allocations[0].quantity_decimal);
  const base = Number(rows[0].market_value_base_decimal);
  assert.equal(base * allocated / brokerQty, 1200);
});

function portfolioDb({
  ownerJoinRows = [],
  brokerRows = [],
  sleeveRows = [],
  allocationCount = 0,
  sleeveThrows = false,
}) {
  const queries = [];
  const run = {
    source_run_id: "run-flex",
    account_alias: "U805366",
    as_of: "2026-10-07T22:15:14Z",
    completeness_json: JSON.stringify({ feed: "flex_eod", session_date: "2026-10-07" }),
  };
  const db = {
    prepare(sql) {
      queries.push(sql);
      return {
        bind() { return this; },
        async first() { return run; },
        async all() {
          if (sql.includes("sleeve_positions")) {
            if (sleeveThrows) throw new Error("no sleeve table");
            return { results: sleeveRows };
          }
          if (sql.startsWith("SELECT * FROM portfolio_positions")) return { results: brokerRows };
          throw new Error(`unexpected all(): ${sql}`);
        },
      };
    },
    async batch() {
      return [
        { results: [{ tag: "NetLiquidation", value_decimal: "12469181.49" }] },
        { results: ownerJoinRows },
        { results: [] },
        { results: [] },
        { results: [{ count: 0 }] },
        { results: [{ count: brokerRows.length }] },
        { results: allocationCount > 0 ? [{ allocation_count: allocationCount, projection_id: "p1", as_of: run.as_of }] : [] },
      ];
    },
  };
  return { env: { DB: db }, queries };
}

function brokerBook() {
  return [
    position({ conid: 1, symbol: "CSU", local_symbol: "CSU", quantity_decimal: "300", market_value_base_decimal: "665000" }),
    position({ conid: 2, symbol: "AAPL", local_symbol: "AAPL", quantity_decimal: "4", market_value_base_decimal: "800" }),
    position({
      conid: 3, symbol: "SPXW  260817P05000000", local_symbol: "SPXW  260817P05000000",
      sec_type: "OPT", quantity_decimal: "-8", market_value_base_decimal: "-2400",
    }),
    position({
      conid: 4, symbol: "XSP   270129P00540000", local_symbol: "XSP   270129P00540000",
      sec_type: "OPT", quantity_decimal: "12", market_value_base_decimal: "3090",
    }),
    position({
      conid: 5, symbol: "APLD  261009C00038000", local_symbol: "APLD  261009C00038000",
      sec_type: "OPT", quantity_decimal: "-21", market_value_base_decimal: "-1500",
    }),
    position({ conid: 6, symbol: "IBKR", local_symbol: "IBKR", quantity_decimal: "9", market_value_base_decimal: "900" }),
    position({ conid: 7, symbol: "GTX", local_symbol: "GTX", quantity_decimal: "164492", market_value_base_decimal: "4826195.28" }),
    position({ conid: 8, symbol: "3905.T", local_symbol: "3905.T", quantity_decimal: "13200", market_value_base_decimal: "129000" }),
  ];
}

test("a missing projection fills Michael from the broker residual", async () => {
  const brokerRows = brokerBook();
  const { env, queries } = portfolioDb({
    brokerRows,
    sleeveRows: [
      { owner: "drew", ticker: "IBKR", sec_type: "STK", classifier_reason: "drew_new" },
      { owner: "drew", ticker: "3905.T", sec_type: "STK", classifier_reason: "drew_new" },
      { owner: "michael", ticker: "3905.T", sec_type: "STK", classifier_reason: "residual" },
      { owner: "drew", ticker: "APLD", sec_type: "OPT", classifier_reason: "ls_algo_option_overlay" },
    ],
  });
  const book = await loadPortfolio(env, "michael");
  assert.equal(book.allocation_status, "residual_fallback");
  assert.equal(book.broker_position_count, brokerRows.length);
  assert.deepEqual(book.positions.map((row) => row.symbol), ["CSU", "GTX", "3905.T"]);
  const gtx = book.positions.find((row) => row.symbol === "GTX");
  assert.equal(gtx.market_value_base_decimal, "4826195.28");
  assert.equal(gtx.allocations[0].quantity_decimal, "164492");
  assert.equal(gtx.allocations[0].confidence, "michael_residual_fallback");
  assert.equal(book.account_values[0].value_decimal, "12469181.49");
  assert.equal(queries.some((sql) => sql.startsWith("SELECT * FROM portfolio_positions")), true);
});

test("a published projection is not replaced by the residual", async () => {
  const joined = [{
    ...position({ conid: 1, symbol: "CSU", quantity_decimal: "300", market_value_base_decimal: "665000" }),
    allocation_id: "alloc-csu",
    owner: "michael",
    strategy: "single_stock",
    bucket: null,
    allocated_quantity_decimal: "300",
    confidence: "authoritative",
  }];
  const { env, queries } = portfolioDb({
    ownerJoinRows: joined,
    brokerRows: brokerBook(),
    allocationCount: 1,
  });
  const book = await loadPortfolio(env, "michael");
  assert.equal(book.allocation_status, "complete");
  assert.deepEqual(book.positions.map((row) => row.symbol), ["CSU"]);
  assert.equal(book.positions[0].allocations[0].confidence, "authoritative");
  assert.equal(book.positions[0].allocations[0].quantity_decimal, "300");
  assert.equal(queries.some((sql) => sql.startsWith("SELECT * FROM portfolio_positions")), false);
});

test("the whole-account scope stays the full broker book when the projection is absent", async () => {
  const brokerRows = brokerBook();
  const { env } = portfolioDb({ ownerJoinRows: brokerRows, brokerRows });
  const book = await loadPortfolio(env, "all");
  assert.equal(book.allocation_status, "upstream_absent");
  assert.equal(book.positions.length, brokerRows.length);
  assert.ok(book.positions.some((row) => row.symbol === "AAPL"));
});

test("drew stays empty when the projection is absent", async () => {
  const { env, queries } = portfolioDb({ brokerRows: brokerBook() });
  const book = await loadPortfolio(env, "drew");
  assert.equal(book.allocation_status, "upstream_absent");
  assert.equal(book.positions.length, 0);
  assert.equal(queries.some((sql) => sql.startsWith("SELECT * FROM portfolio_positions")), false);
});

test("a missing sleeve table still drops LS Algo and SPX 0DTE", async () => {
  const { env } = portfolioDb({ brokerRows: brokerBook(), sleeveThrows: true });
  const book = await loadPortfolio(env, "michael");
  assert.equal(book.allocation_status, "residual_fallback");
  const symbols = book.positions.map((row) => row.symbol);
  assert.ok(symbols.includes("CSU"));
  assert.ok(symbols.includes("GTX"));
  assert.ok(symbols.includes("IBKR"));
  assert.equal(symbols.includes("AAPL"), false);
  assert.equal(symbols.some((symbol) => symbol.startsWith("SPXW")), false);
  assert.equal(symbols.some((symbol) => symbol.startsWith("XSP")), false);
  assert.equal(symbols.some((symbol) => symbol.startsWith("APLD")), false);
});
