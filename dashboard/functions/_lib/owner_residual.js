/**
 * Michael's book when no allocation projection is published.
 *
 * This is the owner-custody rule in
 * `_system/trading/portfolio_hub/allocation_policy.py` and
 * `_system/trading/sleeves/classify_positions.py`: Michael is every broker
 * position except LS Algo, SPX 0DTE, and Drew. It is a read-model fallback
 * only. A published projection is never rewritten here.
 *
 * Flex stores an option's OCC local symbol in `symbol` and does not keep
 * `underlyingSymbol`. The classifier already reads `underlying`; for OPT/FOP
 * the OCC root is supplied as that field so the same overlay and index rules
 * fire.
 */
import universeFile from "../../data/etf_ls_universe.json" with { type: "json" };

const CASH_SEC_TYPES = new Set(["CASH", "BILL"]);
const CASH_SYMBOLS = new Set(["USD", "EUR", "GBP", "CAD", "JPY", "BIL", "SGOV", "SHV", "TBIL", "TFLO", "VMFXX"]);
const SPX_NAMES = new Set(["SPX", "SPXW"]);
const ETF_LS_REFS = ["ETF_LS", "B5P"];
const DREW_REF = "DREW_SLEEVE";
const DREW_LOTS_OPENED_ON_OR_AFTER = { "3905.T": "20260913" };
const MICHAEL_REF = "MICHAEL_SLEEVE";
const DREW_HOLDING_REASONS = new Set(["drew_new", "drew_sleeve_holding", "sleeve_tag"]);
const OCC_ROOT = /^([A-Z0-9.]{1,6})\s+\d{6}[CP]\d/;

export function normSym(symbol) {
  const raw = String(symbol || "").trim().toUpperCase();
  if (raw === "BRK.B" || raw === "BRK B") return "BRK-B";
  return raw.replace(/ /g, "-");
}

export function lsUniverseSymbols() {
  return new Set((universeFile.symbols || []).map(normSym).filter(Boolean));
}

function asSet(values) {
  return values instanceof Set ? values : new Set(values || []);
}

function occRoot(raw) {
  const match = String(raw || "").trim().toUpperCase().match(OCC_ROOT);
  return match ? match[1] : "";
}

function withOptionUnderlying(row) {
  const sec = String(row.sec_type || row.secType || "STK").trim().toUpperCase();
  const underlying = row.underlying || row.underlyingSymbol || row.underlying_symbol || "";
  if (underlying || (sec !== "OPT" && sec !== "FOP")) return row;
  const root = occRoot(row.local_symbol || row.localSymbol) || occRoot(row.symbol);
  return root ? { ...row, underlying: root } : row;
}

/**
 * Port of classify_position. blacklist_family stays empty on the policy path;
 * the argument is here so the branch order matches the Python function.
 */
export function classifyPosition(pos, {
  blacklistFamily = [],
  etfLsSymbols = [],
  drewSymbols = [],
} = {}) {
  const under = normSym(pos.underlyingSymbol || pos.underlying || "");
  const ticker = normSym(pos.symbol || pos.ticker || pos.localSymbol || "");
  const sec = String(pos.secType || pos.sec_type || "STK").trim().toUpperCase();
  const tclass = String(pos.tradingClass || pos.trading_class || "").trim().toUpperCase();
  const ref = String(pos.orderRef || pos.order_ref || "").trim().toUpperCase();
  const family = asSet([...blacklistFamily].map(normSym));
  const letf = asSet([...etfLsSymbols].map(normSym));
  const drew = asSet([...drewSymbols].map(normSym));
  const indexName = under || ticker || tclass;
  const option = sec === "OPT" || sec === "FOP";

  if (option) {
    const local = String(pos.localSymbol || pos.symbol || "").toUpperCase();
    if (indexName === "XSP" || local.startsWith("XSP")) {
      return { ticker: "XSP", bucket: "index_put_hedge", reason: "index_put_hedge", owner: null };
    }
    if (SPX_NAMES.has(indexName) || local.includes("SPXW")) {
      return { ticker: indexName || "SPX", bucket: "spx_0dte", reason: "spxw_option", owner: null };
    }
  }

  const strategyName = option ? (under || ticker) : ticker;
  if (option && (ETF_LS_REFS.some((tag) => ref.includes(tag)) || letf.has(strategyName))) {
    return { ticker: strategyName || ticker, bucket: "drew", reason: "ls_algo_option_overlay", owner: "drew" };
  }
  if (ETF_LS_REFS.some((tag) => ref.includes(tag))) {
    return { ticker: under || ticker, bucket: "etf_ls", reason: "order_ref", owner: null };
  }
  if (letf.has(strategyName)) {
    return { ticker: strategyName, bucket: "etf_ls", reason: "etf_ls_universe", owner: null };
  }

  const opened = String(pos.openDateTime || pos.open_date_time || "");
  const cutoff = DREW_LOTS_OPENED_ON_OR_AFTER[ticker];
  if (cutoff && !option && opened >= cutoff) {
    return { ticker, bucket: "drew", reason: "drew_new", owner: "drew" };
  }
  if (ref.includes(DREW_REF) || drew.has(ticker)) {
    return { ticker, bucket: "drew", reason: "drew_new", owner: "drew" };
  }
  if (family.has(ticker)) {
    return { ticker, bucket: "michael", reason: "blacklist_family", owner: "michael" };
  }
  if (option) {
    const name = under || ticker;
    if (family.has(name)) return { ticker: name, bucket: "michael", reason: "blacklist_family", owner: "michael" };
    if (ref.includes(MICHAEL_REF)) return { ticker: name || ticker, bucket: "michael", reason: "michael_new", owner: "michael" };
    if (name) return { ticker: name, bucket: "michael", reason: "residual", owner: "michael" };
    return { ticker, bucket: "ignored", reason: "option_not_stock", owner: null };
  }
  if (ref.includes(MICHAEL_REF)) return { ticker, bucket: "michael", reason: "michael_new", owner: "michael" };
  if (CASH_SEC_TYPES.has(sec) || CASH_SYMBOLS.has(ticker)) {
    return { ticker, bucket: "michael", reason: "cash", owner: "michael" };
  }
  if (!ticker) return { ticker: "", bucket: "ignored", reason: "missing_symbol", owner: null };
  return { ticker, bucket: "michael", reason: "residual", owner: "michael" };
}

/** Port of classify_policy_position. */
export function classifyPolicyPosition(row, { lsSymbols = [], drewSymbols = [] } = {}) {
  const prepared = withOptionUnderlying(row);
  const symbol = normSym(prepared.symbol || prepared.local_symbol || prepared.localSymbol || "");
  if (!symbol) {
    return { owner: "unallocated", strategy: "other", reason: "missing_symbol_quarantine", bucket: null };
  }
  const classification = classifyPosition({
    symbol,
    localSymbol: prepared.local_symbol || prepared.localSymbol,
    secType: prepared.sec_type || prepared.secType,
    underlying: prepared.underlying,
    tradingClass: prepared.trading_class || prepared.tradingClass,
    orderRef: prepared.order_ref || prepared.orderRef,
  }, { etfLsSymbols: lsSymbols, drewSymbols, blacklistFamily: [] });

  if (classification.bucket === "index_put_hedge") {
    return { owner: "unallocated", strategy: "ls_algo", reason: "index_put_hedge", bucket: "index_put_hedge" };
  }
  if (classification.bucket === "spx_0dte") {
    return { owner: "unallocated", strategy: "spx_0dte", reason: "spx_option_strategy_exclusion", bucket: null };
  }
  if (classification.bucket === "etf_ls") {
    return { owner: "unallocated", strategy: "letf", reason: "ls_algo_universe_exclusion", bucket: null };
  }
  if (classification.bucket === "drew") {
    if (classification.reason === "ls_algo_option_overlay") {
      return { owner: "drew", strategy: "letf_option_overlay", reason: classification.reason, bucket: null };
    }
    return { owner: "drew", strategy: "single_stock", reason: "drew_sleeve_holding", bucket: null };
  }
  if (classification.bucket === "ignored") {
    return { owner: "unallocated", strategy: "other", reason: classification.reason, bucket: null };
  }
  return { owner: "michael", strategy: "single_stock", reason: "michael_residual_book", bucket: null };
}

/**
 * Drew tickers for the policy's drew_symbols argument.
 *
 * Sleeve rows are the desk record the dashboard already has (order refs are
 * not on Flex positions). Option overlays are not added: the policy routes
 * those by the LS-universe option rule, and their ticker is the underlying.
 * A symbol that Michael's sleeve also holds is left out. The broker row is
 * one folded contract, and an undated 3905.T stays Michael in classify_position
 * because the September lot split is not on this row.
 */
export function drewSymbolsFromSleeveRows(rows) {
  const michael = new Set();
  for (const row of rows || []) {
    if (String(row.owner || "").toLowerCase() !== "michael") continue;
    const ticker = normSym(row.ticker || "");
    if (ticker) michael.add(ticker);
  }
  const drew = new Set();
  for (const row of rows || []) {
    if (String(row.owner || "").toLowerCase() !== "drew") continue;
    const reason = String(row.classifier_reason || "");
    const sec = String(row.sec_type || row.secType || "STK").trim().toUpperCase();
    if (reason === "ls_algo_option_overlay" || sec === "OPT" || sec === "FOP") continue;
    if (reason && !DREW_HOLDING_REASONS.has(reason)) continue;
    const ticker = normSym(row.ticker || "");
    if (!ticker || michael.has(ticker)) continue;
    drew.add(ticker);
  }
  return drew;
}

/**
 * Broker rows whose policy owner is Michael, each carrying one allocation for
 * the full broker quantity so the positions table can scale market value.
 */
export function michaelResidualPositions(rows, { lsSymbols = lsUniverseSymbols(), drewSymbols = [] } = {}) {
  const positions = [];
  for (const row of rows || []) {
    const policy = classifyPolicyPosition(row, { lsSymbols, drewSymbols });
    if (policy.owner !== "michael") continue;
    positions.push({
      ...row,
      allocations: [{
        allocation_id: `residual:${row.account_alias || ""}:${row.conid}:${row.model_code || ""}`,
        owner: "michael",
        strategy: policy.strategy,
        bucket: policy.bucket,
        quantity_decimal: row.quantity_decimal,
        confidence: "michael_residual_fallback",
      }],
    });
  }
  return positions;
}
