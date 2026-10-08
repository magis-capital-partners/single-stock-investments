/**
 * Holder overlap for the research universe.
 * Caccioli, Shrestha, Moore, Farmer 2012-10-018 and Caccioli, Catanach, Farmer 2011-09-044.
 * No prices. No I/O. Not a valuation input.
 */

export const HUB_NAME_SHARE = 0.25;
export const LEVERAGE_MULTIPLE = 2;
export const BORROWINGS_RATIO = 0.1;
export const SCHEMA_FLAGS = {
  research_only: true,
  in_base_irr: false,
  authority: "none",
};

const CURATED = new Set(["specialist_13f", "tracked_13f", "large_13f", "etf"]);

export function leverageOf(holder) {
  const multiple = numberOrNull(holder?.stated_multiple);
  if (multiple != null) {
    return {
      text: `${multiple}×`,
      above: Math.abs(multiple) >= LEVERAGE_MULTIPLE,
      reported: true,
      multiple,
    };
  }
  const ratio = numberOrNull(holder?.borrowings_ratio);
  if (ratio != null) {
    return {
      text: `${(ratio * 100).toFixed(1)}% borrowings`,
      above: ratio >= BORROWINGS_RATIO,
      reported: true,
      multiple: null,
    };
  }
  return { text: "not reported", above: false, reported: false, multiple: null };
}

export function nameStats(holders) {
  const rows = (holders || []).filter((holder) => numberOrNull(holder.market_value) != null && holder.market_value > 0);
  const total = rows.reduce((sum, holder) => sum + holder.market_value, 0);
  if (!(total > 0)) {
    return {
      holder_count: (holders || []).length,
      top_share: null,
      top_holder: null,
      herfindahl: null,
      hub_name: false,
      leverage_above: 0,
      leverage_text: rows.length ? "not reported" : "no holder on file",
      max_multiple: null,
    };
  }
  const ranked = [...rows].sort(byValueThenCik);
  const top = ranked[0];
  const topShare = top.market_value / total;
  const herfindahl = rows.reduce((sum, holder) => sum + (holder.market_value / total) ** 2, 0);
  const flags = rows.map(leverageOf);
  const above = flags.filter((flag) => flag.above);
  const reported = flags.filter((flag) => flag.reported);
  const multiples = flags.map((flag) => flag.multiple).filter((value) => value != null);
  return {
    holder_count: rows.length,
    top_share: topShare,
    top_holder: top,
    herfindahl,
    hub_name: topShare >= HUB_NAME_SHARE,
    leverage_above: above.length,
    leverage_text: above.length
      ? `${above.length} above the threshold`
      : (reported[0]?.text || "not reported"),
    max_multiple: multiples.length ? multiples.sort((a, b) => Math.abs(b) - Math.abs(a))[0] : null,
  };
}

export function holderPairs(names, limit = 25) {
  const books = new Map();
  const keep = new Set();
  for (const name of names) {
    const holders = (name.holders || []).filter((holder) => numberOrNull(holder.market_value) > 0);
    const ranked = [...holders].sort(byValueThenCik);
    ranked.slice(0, 3).forEach((holder) => keep.add(holder.fund_id));
    holders.filter((holder) => CURATED.has(holder.kind)).forEach((holder) => keep.add(holder.fund_id));
  }
  for (const name of names) {
    for (const holder of name.holders || []) {
      if (!keep.has(holder.fund_id) || !(numberOrNull(holder.market_value) > 0)) continue;
      const book = books.get(holder.fund_id) || {
        fund_id: holder.fund_id,
        name: holder.name,
        kind: holder.kind,
        cik: holder.cik || "",
        by_ticker: new Map(),
      };
      book.by_ticker.set(name.ticker, holder.market_value);
      books.set(holder.fund_id, book);
    }
  }
  const list = [...books.values()];
  const pairs = [];
  for (let left = 0; left < list.length; left += 1) {
    for (let right = left + 1; right < list.length; right += 1) {
      const a = list[left];
      const b = list[right];
      let overlap = 0;
      let shared = 0;
      let aShared = 0;
      let bShared = 0;
      for (const [ticker, value] of a.by_ticker) {
        if (!b.by_ticker.has(ticker)) continue;
        shared += 1;
        const other = b.by_ticker.get(ticker);
        overlap += Math.min(value, other);
        aShared += value;
        bShared += other;
      }
      if (!shared) continue;
      const aTotal = [...a.by_ticker.values()].reduce((sum, value) => sum + value, 0);
      const bTotal = [...b.by_ticker.values()].reduce((sum, value) => sum + value, 0);
      pairs.push({
        left: { fund_id: a.fund_id, name: a.name, kind: a.kind },
        right: { fund_id: b.fund_id, name: b.name, kind: b.kind },
        shared_names: shared,
        overlap_dollars: overlap,
        left_share: aTotal > 0 ? aShared / aTotal : null,
        right_share: bTotal > 0 ? bShared / bTotal : null,
      });
    }
  }
  pairs.sort((a, b) => b.overlap_dollars - a.overlap_dollars || b.shared_names - a.shared_names);
  return pairs.slice(0, limit);
}

export function scopeStress({ positions, namesByTicker, asOf, quarter }) {
  const rows = (positions || [])
    .map((row) => ({ ticker: String(row.ticker || "").toUpperCase(), market_value: Number(row.market_value) }))
    .filter((row) => row.ticker && Number.isFinite(row.market_value) && row.market_value !== 0);
  const nav = rows.reduce((sum, row) => sum + Math.abs(row.market_value), 0);
  if (!(nav > 0)) {
    return { nav: 0, hub_holder: null, random_holder: null, difference: null, reason: "no dollars in this scope" };
  }
  const ours = new Map(rows.map((row) => [row.ticker, row.market_value]));
  const holders = new Map();
  for (const [ticker, marketValue] of ours) {
    const record = namesByTicker[ticker];
    for (const holder of record?.holders || []) {
      const current = holders.get(holder.fund_id) || {
        fund_id: holder.fund_id,
        name: holder.name,
        kind: holder.kind,
        cik: holder.cik || "",
        reported: 0,
        tickers: new Set(),
      };
      current.tickers.add(ticker);
      current.reported += numberOrNull(holder.market_value) || 0;
      holders.set(holder.fund_id, current);
    }
    void marketValue;
  }
  const ranked = [...holders.values()].map((holder) => {
    let overlap = 0;
    for (const ticker of holder.tickers) overlap += Math.abs(ours.get(ticker) || 0);
    return { ...holder, overlap, overlap_share: overlap / nav };
  }).sort((a, b) => b.overlap - a.overlap || b.reported - a.reported || String(a.cik).localeCompare(String(b.cik)));
  if (!ranked.length) {
    return {
      nav,
      hub_holder: null,
      random_holder: null,
      difference: null,
      our_concentration: Math.max(...rows.map((row) => Math.abs(row.market_value))) / nav,
      reason: "no holder on file for this book",
    };
  }
  const hub = ranked[0];
  const others = ranked.slice(1);
  const largest = Math.max(...rows.map((row) => Math.abs(row.market_value))) / nav;
  const base = {
    nav,
    our_concentration: largest,
    crowd_concentration: hub.overlap_share,
    sentence: `The largest position is ${pct(largest)} of this book. Names also reported by ${hub.name} are ${pct(hub.overlap_share)} of this book.`,
    disclaimer: "This is how much of this book sits in names that holder also reports. It is not a loss.",
    names_only_after_hub: namesLeftAlone(ours, namesByTicker, hub.fund_id),
  };
  if (!others.length) {
    return {
      ...base,
      hub_holder: publicHolder(hub),
      random_holder: null,
      difference: null,
      reason: "only one overlapping holder",
    };
  }
  const pick = others[hashSeed(`${asOf || ""}|${quarter || ""}`) % others.length];
  return {
    ...base,
    hub_holder: publicHolder(hub),
    random_holder: publicHolder(pick),
    difference: hub.overlap_share - pick.overlap_share,
    reason: null,
  };
}

export function evaluateOverlap({ names, scope = "universe", positions = null, asOf = null, quarter = null, coverage = null }) {
  const entries = Object.entries(names || {}).map(([ticker, record]) => ({
    ticker,
    ...record,
    holders: record.holders || [],
  }));
  const priced = new Set((positions || []).map((row) => String(row.ticker || "").toUpperCase()));
  const visible = scope === "universe"
    ? entries
    : entries.filter((entry) => priced.has(entry.ticker) || (positions || []).some((row) => String(row.ticker || "").toUpperCase() === entry.ticker));
  const rows = visible.map((entry) => {
    const computed = nameStats(entry.holders);
    const stored = entry.full_stats || null;
    const stats = stored
      ? {
        ...computed,
        holder_count: stored.holder_count,
        top_share: stored.top_share,
        herfindahl: stored.herfindahl,
        hub_name: stored.hub_name,
        leverage_above: stored.leverage_above,
        leverage_text: stored.leverage_text,
        top_holder: {
          ...(computed.top_holder || {}),
          name: stored.top_holder || computed.top_holder?.name || null,
          shares: stored.top_shares ?? computed.top_holder?.shares ?? null,
        },
      }
      : computed;
    const topShares = numberOrNull(stats.top_holder?.shares);
    const floatShares = numberOrNull(entry.float_shares);
    let floatNote = null;
    let topFloat = null;
    if (topShares != null && floatShares) {
      topFloat = topShares / floatShares;
    } else if (stats.top_holder && topShares == null) {
      floatNote = "shares not on the filing";
    } else if (stats.top_holder && !floatShares) {
      floatNote = "float not on file";
    }
    return {
      ticker: entry.ticker,
      tier: entry.tier ?? null,
      company: entry.company || entry.ticker,
      omitted: entry.omitted || null,
      index_tags: entry.index_tags || [],
      short_percent_float: numberOrNull(entry.short_percent_float),
      float_as_of: entry.float_as_of || null,
      holder_count: stats.holder_count,
      top_holder: stats.top_holder ? stats.top_holder.name : null,
      top_share: stats.top_share,
      hub_name: stats.hub_name,
      herfindahl: stats.herfindahl,
      leverage_text: stats.leverage_text,
      leverage_above: stats.leverage_above,
      max_multiple: stats.max_multiple,
      top_float_share: topFloat,
      float_note: floatNote,
      holders: entry.holders.map((holder) => ({
        ...holder,
        leverage: leverageOf(holder).text,
        above_threshold: leverageOf(holder).above,
      })),
    };
  }).sort((a, b) => (b.top_share || -1) - (a.top_share || -1) || a.ticker.localeCompare(b.ticker));
  const stress = scope === "universe"
    ? null
    : scopeStress({ positions, namesByTicker: names || {}, asOf, quarter });
  const rankedHolders = rankHolders(entries);
  return {
    ...SCHEMA_FLAGS,
    schema_version: 1,
    scope,
    as_of: asOf,
    quarter,
    coverage,
    rows,
    pairs: holderPairs(entries),
    holder_rank: scope === "universe" ? rankedHolders : [],
    stress,
    cutoffs: { hub_name_share: HUB_NAME_SHARE, leverage_multiple: LEVERAGE_MULTIPLE, borrowings_ratio: BORROWINGS_RATIO },
  };
}

function rankHolders(entries) {
  const totals = new Map();
  for (const entry of entries) {
    for (const holder of entry.holders || []) {
      const current = totals.get(holder.fund_id) || {
        fund_id: holder.fund_id, name: holder.name, kind: holder.kind, names: 0, reported: 0,
      };
      current.names += 1;
      current.reported += numberOrNull(holder.market_value) || 0;
      totals.set(holder.fund_id, current);
    }
  }
  return [...totals.values()].sort((a, b) => b.reported - a.reported || b.names - a.names).slice(0, 25);
}

function namesLeftAlone(ours, namesByTicker, removedId) {
  const left = [];
  for (const ticker of ours.keys()) {
    const holders = (namesByTicker[ticker]?.holders || []).filter((holder) => holder.fund_id !== removedId);
    if (!holders.length && (namesByTicker[ticker]?.holders || []).some((holder) => holder.fund_id === removedId)) {
      left.push(ticker);
    }
  }
  return left.sort();
}

function publicHolder(holder) {
  return {
    fund_id: holder.fund_id,
    name: holder.name,
    kind: holder.kind,
    overlap_share: holder.overlap_share,
    overlap_dollars: holder.overlap,
  };
}

function byValueThenCik(a, b) {
  return (b.market_value || 0) - (a.market_value || 0) || String(a.cik || "").localeCompare(String(b.cik || ""));
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function hashSeed(text) {
  let hash = 2166136261;
  for (const char of String(text)) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return hash >>> 0;
}

function pct(value) {
  return `${(value * 100).toFixed(1)}%`;
}
