/**
 * Peters time-average growth for one sleeve.
 *
 * Ole Peters, Optimal Leverage from Non-ergodicity, SFI 2009-02-004.
 * Equations 11, 13, 16, 17, and 19. No I/O. Not a valuation input.
 */

export const TRADING_DAYS = 252;
export const SCHEMA_FLAGS = {
  research_only: true,
  in_base_irr: false,
  authority: "none",
};

const STRUCTURAL = /\.(ESC|CVR|WTS|DB|CNT|MRG|PS\d*)$/i;

export function mean(values) {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function sampleStdev(values) {
  if (values.length < 2) return null;
  const center = mean(values);
  const square = values.reduce((sum, value) => sum + (value - center) ** 2, 0);
  return Math.sqrt(square / (values.length - 1));
}

export function dailyRiskless(continuous) {
  return Math.exp(continuous / TRADING_DAYS) - 1;
}

/** Equations 16, 17, 19, and 13 at full investment in the risky portfolio. */
export function leverageObjects({ muExcess, sigma, riskless }) {
  const variance = sigma * sigma;
  if (!(variance > 0) || !Number.isFinite(muExcess) || !Number.isFinite(riskless)) return null;
  const lOpt = muExcess / variance;
  const growthAtFull = riskless + muExcess - variance / 2;
  const tC = Math.abs(growthAtFull) < 1e-12 ? Infinity : variance / (growthAtFull ** 2);
  const inside = muExcess ** 2 + 2 * riskless * variance;
  const lC = inside < 0 ? null : (muExcess + Math.sqrt(inside)) / variance;
  return { lOpt, growthAtFull, tC, lC };
}

export function itoDrag(scale, sigma) {
  if (!Number.isFinite(scale) || !Number.isFinite(sigma)) return null;
  return (scale ** 2) * (sigma ** 2) / 2;
}

function finiteReturn(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > -0.999 ? number : null;
}

function structuralReason(ticker) {
  return STRUCTURAL.test(String(ticker || "")) ? "not_stock" : null;
}

function sessionsBetween(older, newer) {
  const left = Date.parse(`${older}T00:00:00Z`);
  const right = Date.parse(`${newer}T00:00:00Z`);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return null;
  return Math.round((right - left) / 86400000);
}

/**
 * Status of the scale annotation. The numbers themselves are computed either way.
 * `showScale` is true only for past_peak and room.
 */
export function annotationStatus({ lOptLow, lOptHigh, lNow, tC, n, hedged, lowCoverage }) {
  const reasons = [];
  if (hedged) reasons.push("hedged");
  if (lowCoverage) reasons.push("low_coverage");
  if (!(n >= TRADING_DAYS)) reasons.push("short_window");
  if (!Number.isFinite(tC)) reasons.push("zero_growth");
  else if (tC > 3) reasons.push("long_characteristic_time");
  if (!reasons.length) {
    if (lOptHigh < lNow) return { status: "past_peak", reasons: [], showScale: true };
    if (lOptLow > lNow) return { status: "room", reasons: [], showScale: true };
    reasons.push("straddles");
  }
  return { status: "unidentified", reasons, showScale: false };
}

function seriesMap(block) {
  const map = new Map();
  for (const row of block?.returns || []) {
    const value = finiteReturn(row.r);
    if (value == null || !row.date) continue;
    map.set(row.date, value);
  }
  return map;
}

function aligned(maps) {
  if (!maps.length) return [];
  const dates = [...maps[0].keys()].filter((date) => maps.every((map) => map.has(date))).sort();
  return dates;
}

function logGrowth(simple) {
  const logs = [];
  for (const value of simple) {
    if (value > -0.999) logs.push(Math.log1p(value));
  }
  if (logs.length < 2) return null;
  const sigma = sampleStdev(logs) * Math.sqrt(TRADING_DAYS);
  const growth = mean(logs) * TRADING_DAYS;
  return { sigma, growth, n: logs.length, ensemble: mean(simple) * TRADING_DAYS };
}

function nameRow(ticker, weight, returns, riskless) {
  const simple = returns.map((row) => {
    const asset = finiteReturn(row.r);
    if (asset == null) return null;
    return weight * asset + (1 - weight) * dailyRiskless(riskless);
  }).filter((value) => value != null);
  const assetOnly = returns.map((row) => finiteReturn(row.r)).filter((value) => value != null);
  const book = logGrowth(simple);
  const asset = logGrowth(assetOnly);
  if (!book || !asset) {
    return { ticker, weight, drag: null, growth: null, status: "unidentified", show_scale: false, reasons: ["short_window"] };
  }
  const objects = leverageObjects({
    muExcess: asset.growth + (asset.sigma ** 2) / 2 - riskless,
    sigma: asset.sigma,
    riskless,
  });
  const se = asset.sigma / Math.sqrt(asset.n);
  const variance = asset.sigma ** 2;
  const low = objects ? (objects.lOpt * variance - se) / variance : null;
  const high = objects ? (objects.lOpt * variance + se) / variance : null;
  const call = annotationStatus({
    lOptLow: low,
    lOptHigh: high,
    lNow: weight,
    tC: objects ? objects.tC : Infinity,
    n: asset.n,
    hedged: false,
    lowCoverage: false,
  });
  return {
    ticker,
    weight,
    drag: itoDrag(weight, asset.sigma),
    growth: book.growth,
    status: call.status,
    show_scale: call.showScale,
    reasons: call.reasons,
    l_opt: call.showScale ? objects.lOpt : null,
    upper_bound: call.showScale && objects.lOpt > 1,
  };
}

/**
 * Build the panel from a sleeve book and a parameter file.
 * Weights are signed market value over NAV. The fully invested mix is those
 * weights scaled to 1. Cash and omitted value earn the riskless rate in the
 * hypothetical only.
 */
export function evaluateSleeve({ nav, asOf = null, positions = [], params = {} }) {
  const riskless = Number(params.riskless?.continuous);
  const symbols = params.symbols || {};
  const wealth = Number(nav);
  const omitted = [];
  const included = [];
  const ends = Object.values(symbols).map((block) => block?.end).filter(Boolean).sort();
  const newest = ends.at(-1) || null;

  for (const position of positions) {
    const ticker = String(position.ticker || "").trim();
    if (!ticker) continue;
    const marketValue = Number(position.market_value);
    if (!Number.isFinite(marketValue) || !Number.isFinite(wealth) || wealth === 0) continue;
    const weight = marketValue / wealth;
    const sec = String(position.sec_type || "STK").toUpperCase();
    const reason = structuralReason(ticker);
    if (sec !== "STK" || position.classifier_reason === "cash" || reason) {
      omitted.push({ ticker, weight, reason: "not_stock" });
      continue;
    }
    const block = symbols[ticker];
    if (!block || block.ok === false) {
      omitted.push({ ticker, weight, reason: block?.reason || "short_history" });
      continue;
    }
    if (block.reason === "missing_fx") {
      omitted.push({ ticker, weight, reason: "missing_fx" });
      continue;
    }
    const age = newest && block.end ? sessionsBetween(block.end, newest) : 0;
    if (block.stale && age != null && age > 16) {
      omitted.push({ ticker, weight, reason: "stale_params" });
      continue;
    }
    const returns = Array.isArray(block.returns) ? block.returns : [];
    if (returns.length < TRADING_DAYS) {
      omitted.push({ ticker, weight, reason: "short_history" });
      continue;
    }
    included.push({ ticker, weight, marketValue, returns, map: seriesMap(block) });
  }

  const lNow = included.reduce((sum, row) => sum + row.weight, 0);
  const gross = included.reduce((sum, row) => sum + Math.abs(row.weight), 0);
  const coverage = included.reduce((sum, row) => sum + Math.abs(row.marketValue), 0) / (wealth || 1);
  const dates = aligned(included.map((row) => row.map));
  const rfDaily = Number.isFinite(riskless) ? dailyRiskless(riskless) : null;
  const names = included
    .map((row) => nameRow(row.ticker, row.weight, row.returns, riskless))
    .sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight));
  const empty = {
    ...SCHEMA_FLAGS,
    schema_version: 1,
    owner: "michael",
    as_of: asOf,
    nav: Number.isFinite(wealth) ? wealth : null,
    headline: null,
    annotation: { status: "unidentified", reasons: ["short_window"], show_scale: false, l_opt: null, l_c: null, t_c: null, upper_bound: false },
    names,
    omitted,
    lineage: lineage(params, dates[0] || null, dates.at(-1) || null, dates.length),
  };
  if (!included.length || rfDaily == null) return empty;

  const bookSimple = [];
  for (const date of dates) {
    let stock = 0;
    for (const row of included) stock += row.weight * row.map.get(date);
    const atScale = stock + (1 - lNow) * rfDaily;
    if (atScale > -0.999) bookSimple.push(atScale);
  }
  const book = logGrowth(bookSimple);
  if (Math.abs(lNow) < 1e-6) {
    if (!book) return empty;
    return {
      ...empty,
      headline: {
        ito_drag: (book.sigma ** 2) / 2,
        empirical_growth: book.growth,
        empirical_ensemble: book.ensemble,
        empirical_gap: book.ensemble - book.growth,
        l_now: lNow,
        gross,
        coverage,
        sessions: book.n,
        window_start: dates[0] || null,
        window_end: dates.at(-1) || null,
      },
      annotation: {
        status: "unidentified",
        reasons: gross > 0.3 ? ["hedged"] : ["short_window"],
        show_scale: false,
        l_opt: null,
        l_c: null,
        t_c: null,
        upper_bound: false,
      },
    };
  }
  const fullSimple = [];
  for (const date of dates) {
    let stock = 0;
    for (const row of included) stock += row.weight * row.map.get(date);
    const full = stock / lNow;
    if (full > -0.999) fullSimple.push(full);
  }
  const full = logGrowth(fullSimple);
  if (!book || !full) return empty;

  const mu = full.growth + (full.sigma ** 2) / 2;
  const muExcess = mu - riskless;
  const objects = leverageObjects({ muExcess, sigma: full.sigma, riskless });
  if (!objects) return empty;
  const se = full.sigma / Math.sqrt(full.n);
  const variance = full.sigma ** 2;
  const lOptLow = (muExcess - se) / variance;
  const lOptHigh = (muExcess + se) / variance;
  const hedged = Math.abs(lNow) < 0.05 && gross > 0.3;
  const lowCoverage = coverage < 0.5;
  const call = annotationStatus({
    lOptLow,
    lOptHigh,
    lNow,
    tC: objects.tC,
    n: full.n,
    hedged,
    lowCoverage,
  });
  return {
    ...SCHEMA_FLAGS,
    schema_version: 1,
    owner: "michael",
    as_of: asOf,
    nav: wealth,
    headline: {
      ito_drag: itoDrag(lNow, full.sigma),
      empirical_growth: book.growth,
      empirical_ensemble: book.ensemble,
      empirical_gap: book.ensemble - book.growth,
      l_now: lNow,
      gross,
      coverage,
      sessions: full.n,
      window_start: dates[0] || null,
      window_end: dates.at(-1) || null,
    },
    annotation: {
      status: call.status,
      reasons: call.reasons,
      show_scale: call.showScale,
      l_opt: call.showScale ? objects.lOpt : null,
      l_c: call.showScale ? objects.lC : null,
      t_c: call.showScale ? objects.tC : null,
      upper_bound: call.showScale && objects.lOpt > 1,
    },
    names,
    omitted: omitted.sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight)),
    lineage: lineage(params, dates[0], dates.at(-1), dates.length),
  };
}

function lineage(params, start, end, sessions) {
  return {
    paper: "Ole Peters, Optimal Leverage from Non-ergodicity, SFI working paper 2009-02-004",
    equations: ["11", "13", "16", "17", "19"],
    riskless_series: params.riskless?.series || "DGS3MO",
    riskless_as_of: params.riskless?.as_of || null,
    riskless_continuous: Number.isFinite(Number(params.riskless?.continuous)) ? Number(params.riskless.continuous) : null,
    window_start: start,
    window_end: end,
    sessions,
    cash_earns: "Cash and omitted market value earn the Treasury bill inside this hypothetical.",
  };
}
