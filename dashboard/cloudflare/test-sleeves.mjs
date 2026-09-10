import assert from "node:assert/strict";
import test from "node:test";

import { contractLabel, formatExpiry, positionKey } from "../functions/_lib/sleeves.js";

test("an option keys on its contract, not on the name it is written against", () => {
  // classify_positions returns the UNDERLYING for an option, so both of these
  // arrive as ticker "APLD". Keyed by ticker they are one row and the second
  // INSERT fails the primary key, taking the whole ingest POST down.
  const call = { ticker: "APLD", local_symbol: "APLD  261009C00038000", sec_type: "OPT" };
  const put = { ticker: "APLD", local_symbol: "APLD  261017P00030000", sec_type: "OPT" };
  assert.notEqual(positionKey(call), positionKey(put));
  assert.equal(positionKey(call), "APLD  261009C00038000");
});

test("a share position still keys on its ticker", () => {
  assert.equal(positionKey({ ticker: "MSFT", sec_type: "STK" }), "MSFT");
  assert.equal(positionKey({ ticker: "MSFT", local_symbol: "", sec_type: "STK" }), "MSFT");
});

test("expiry is written the way IBKR writes it", () => {
  assert.equal(formatExpiry("20261009"), "09OCT26");
  assert.equal(formatExpiry("20270129"), "29JAN27");
  // Not a date we recognise: pass it through rather than inventing one.
  assert.equal(formatExpiry("2026-10-09"), "2026-10-09");
  assert.equal(formatExpiry(""), "");
  assert.equal(formatExpiry("20261309"), "20261309");
});

test("the row prints the contract, because a bare underlying does not say what was sold", () => {
  assert.equal(
    contractLabel({ ticker: "APLD", sec_type: "OPT", expiry: "20261009", strike: 38, right_code: "C" }),
    "APLD 09OCT26 38 C",
  );
  assert.equal(
    contractLabel({ ticker: "APLZ", sec_type: "OPT", expiry: "20261016", strike: 11, right_code: "P" }),
    "APLZ 16OCT26 11 P",
  );
});

test("a share position is labelled by ticker alone", () => {
  assert.equal(contractLabel({ ticker: "MSFT", sec_type: "STK" }), "MSFT");
});

test("an option missing a coordinate falls back to the OCC symbol, never a bare underlying", () => {
  // Ambiguity here is what puts a thesis against the wrong contract.
  const partial = { ticker: "APLD", sec_type: "OPT", expiry: "", strike: 38, right_code: "C", local_symbol: "APLD  261009C00038000" };
  assert.equal(contractLabel(partial), "APLD  261009C00038000");
});

test("a fractional strike is not rounded away", () => {
  assert.equal(
    contractLabel({ ticker: "SPY", sec_type: "OPT", expiry: "20261016", strike: 612.5, right_code: "P" }),
    "SPY 16OCT26 612.5 P",
  );
});

test("lots fold into one contract instead of overwriting each other", async () => {
  // Flex reports open lots. This XSP strike really does arrive as 68 + 12 in the
  // 2026-09-09 statement. Keyed by contract, the last lot would win and the page
  // would show 12 where 80 are held; two rows would fail the primary key.
  const { foldPositions } = await import("../functions/_lib/sleeves.js");
  const lot = (qty, mv) => ({
    ticker: "XSP", local_symbol: "XSP   270129P00540000", sec_type: "OPT",
    expiry: "20270129", strike: 540, right_code: "P", qty, mark: 2.0381, market_value: mv,
  });
  const folded = foldPositions([lot(68, 13858), lot(12, 2446)]);

  assert.equal(folded.size, 1);
  const row = folded.get("XSP   270129P00540000");
  assert.equal(row.qty, 80);
  assert.equal(row.market_value, 16304);
  assert.equal(row.mark, 2.0381, "mark is per-contract, not summed");
});

test("different contracts on one underlying stay separate rows", async () => {
  const { foldPositions } = await import("../functions/_lib/sleeves.js");
  const folded = foldPositions([
    { ticker: "APLD", local_symbol: "APLD  261009C00038000", sec_type: "OPT", qty: -21 },
    { ticker: "APLD", local_symbol: "APLD  261017P00030000", sec_type: "OPT", qty: -5 },
  ]);
  assert.equal(folded.size, 2);
});
