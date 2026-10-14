/**
 * Tail risk of one sleeve: fat tails, the power-law exponent, and a seeded
 * Monte Carlo of the current mix.
 *
 * Mandelbrot and Hudson, The (Mis)behavior of Markets (2004): the Noah effect,
 * a few days holding most of the variance, and scaling that the Gaussian
 * cannot carry. Taleb, Statistical Consequences of Fat Tails (2020): the Hill
 * estimator for the tail exponent, the max-to-sum ratio, and the gap between
 * what the Gaussian says and what the sample did.
 *
 * Same book selection as the time-average panel, so both describe one mix.
 * Drift inside the simulation is the Treasury bill: the past year's gain is
 * never projected forward. No I/O. Research only. Not a valuation input.
 */

import {
  SCHEMA_FLAGS,
  TRADING_DAYS,
  NOAH_DAYS,
  mean,
  noahShare,
  sampleStdev,
  selectBook,
} from "./time_average_growth.js";

export const PATHS = 2000;
export const HORIZON = TRADING_DAYS;
export const MEAN_BLOCK = 10;
export const MIN_TAIL = 10;
export const MIN_SESSIONS = 60;
const LOSS_LEVELS = [0.2, 0.3, 0.5];

/* ---------- deterministic randomness ---------- */

export function seedFrom(text) {
  let hash = 0x811c9dc5;
  for (const char of String(text || "")) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

export function mulberry32(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function normal(rng) {
  let u = 0;
  while (u === 0) u = rng();
  const v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** Marsaglia and Tsang (2000), gamma with the given shape and unit scale. */
export function gamma(rng, shape) {
  if (shape < 1) return gamma(rng, shape + 1) * Math.pow(rng() || 1e-12, 1 / shape);
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x;
    let v;
    do {
      x = normal(rng);
      v = 1 + c * x;
    } while (v <= 0);
    v = v * v * v;
    const u = rng();
    if (u < 1 - 0.0331 * x ** 4) return d * v;
    if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}

export function studentT(rng, nu) {
  const z = normal(rng);
  const chi = 2 * gamma(rng, nu / 2);
  return z / Math.sqrt(chi / nu);
}

/* ---------- sample statistics ---------- */

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function excessKurtosis(values) {
  if (values.length < 4) return null;
  const center = mean(values);
  let m2 = 0;
  let m4 = 0;
  for (const value of values) {
    const d = value - center;
    m2 += d * d;
    m4 += d ** 4;
  }
  m2 /= values.length;
  m4 /= values.length;
  if (!(m2 > 0)) return null;
  return m4 / (m2 * m2) - 3;
}

/** Largest squared move over the sum of squared moves. */
export function maxToSum(values) {
  let total = 0;
  let top = 0;
  for (const value of values) {
    const square = value * value;
    total += square;
    if (square > top) top = square;
  }
  return total > 0 ? top / total : null;
}

export function maxDrawdown(simpleReturns) {
  let wealth = 1;
  let peak = 1;
  let worst = 0;
  for (const value of simpleReturns) {
    wealth *= 1 + value;
    if (wealth > peak) peak = wealth;
    const dd = 1 - wealth / peak;
    if (dd > worst) worst = dd;
  }
  return worst;
}

/**
 * Hill (1975) tail exponent on positive magnitudes. k is the tail count:
 * one tenth of the sample, never fewer than MIN_TAIL. Needs k + 1 points.
 * Standard error is alpha over the square root of k, so a short window
 * gives a rough number, and the output says how rough.
 */
export function hillIndex(magnitudes, tail = null) {
  const sorted = magnitudes.filter((value) => value > 0).sort((left, right) => right - left);
  const k = tail ?? Math.max(MIN_TAIL, Math.round(sorted.length / 10));
  if (sorted.length < k + 1) return null;
  const threshold = sorted[k];
  let sum = 0;
  for (let index = 0; index < k; index += 1) sum += Math.log(sorted[index] / threshold);
  if (!(sum > 0)) return null;
  const alpha = k / sum;
  return { alpha, k, se: alpha / Math.sqrt(k), threshold, n: sorted.length };
}

export function tailReading(alpha) {
  if (alpha == null) return "Too few tail points to estimate an exponent.";
  if (alpha < 2) return "Below 2: the variance of this tail is not finite. Standard deviation is not a measure of its risk.";
  if (alpha < 3) return "Between 2 and 3: finite variance, infinite kurtosis. A Gaussian fitted to this sample understates every tail.";
  if (alpha < 4) return "Between 3 and 4: the usual equity range. Fat, and the Gaussian still understates the far tail.";
  return "Above 4: this sample's tail is close to thin. One more year can change that.";
}

function quantile(sorted, p) {
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * p;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  if (low === high) return sorted[low];
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}

/* ---------- simulation ---------- */

/**
 * Run `paths` paths of `horizon` days, one daily simple return per call of
 * `draw(rng)`. Returns the terminal-return and max-drawdown distributions.
 */
export function simulate(draw, { rng, paths = PATHS, horizon = HORIZON } = {}) {
  const terminal = [];
  const drawdown = [];
  for (let path = 0; path < paths; path += 1) {
    let wealth = 1;
    let peak = 1;
    let worst = 0;
    for (let day = 0; day < horizon; day += 1) {
      const value = draw(rng);
      wealth *= Math.max(1 + value, 0);
      if (wealth > peak) peak = wealth;
      const dd = 1 - wealth / peak;
      if (dd > worst) worst = dd;
      if (wealth <= 0) break;
    }
    terminal.push(wealth - 1);
    drawdown.push(worst);
  }
  terminal.sort((left, right) => left - right);
  const tailCount = Math.max(1, Math.round(terminal.length * 0.05));
  const shortfall = mean(terminal.slice(0, tailCount));
  const share = (values, test) => values.filter(test).length / values.length;
  return {
    paths,
    horizon,
    terminal: {
      p05: quantile(terminal, 0.05),
      p25: quantile(terminal, 0.25),
      p50: quantile(terminal, 0.5),
      p75: quantile(terminal, 0.75),
      p95: quantile(terminal, 0.95),
      expected_shortfall_05: shortfall,
    },
    loss_probability: Object.fromEntries(LOSS_LEVELS.map((level) => [String(level), share(terminal, (value) => value <= -level)])),
    drawdown_probability: Object.fromEntries(LOSS_LEVELS.map((level) => [String(level), share(drawdown, (value) => value >= level)])),
  };
}

/**
 * Stationary block bootstrap (Politis and Romano 1994) over the sample,
 * mean block length MEAN_BLOCK, so volatility clustering survives resampling.
 */
export function blockBootstrapDraw(sample) {
  const n = sample.length;
  let cursor = -1;
  return (rng) => {
    if (cursor < 0 || rng() < 1 / MEAN_BLOCK) cursor = Math.floor(rng() * n);
    else cursor = (cursor + 1) % n;
    return sample[cursor];
  };
}

/* ---------- per-name and book ---------- */

function describeSeries(simple, dates = null) {
  const logs = simple.map((value) => Math.log1p(value));
  const sigma = sampleStdev(logs);
  let worstIndex = 0;
  let bestIndex = 0;
  simple.forEach((value, index) => {
    if (value < simple[worstIndex]) worstIndex = index;
    if (value > simple[bestIndex]) bestIndex = index;
  });
  const losses = simple.filter((value) => value < 0).map((value) => -Math.log1p(value));
  const gains = simple.filter((value) => value > 0).map((value) => Math.log1p(value));
  return {
    sessions: simple.length,
    worst_day: { r: simple[worstIndex], date: dates ? dates[worstIndex] : null },
    best_day: { r: simple[bestIndex], date: dates ? dates[bestIndex] : null },
    max_drawdown: maxDrawdown(simple),
    daily_sigma: sigma,
    annual_sigma: sigma == null ? null : sigma * Math.sqrt(TRADING_DAYS),
    excess_kurtosis: excessKurtosis(logs),
    noah_share: noahShare(simple),
    noah_days: NOAH_DAYS,
    max_to_sum: maxToSum(logs),
    hill_left: hillIndex(losses),
    hill_right: hillIndex(gains),
  };
}

function nameTail(row) {
  const simple = row.returns.map((entry) => finite(entry.r)).filter((value) => value != null && value > -0.999);
  const dates = row.returns.filter((entry) => finite(entry.r) != null && finite(entry.r) > -0.999).map((entry) => entry.date);
  const stats = describeSeries(simple, dates);
  return {
    ticker: row.ticker,
    weight: row.weight,
    sessions: stats.sessions,
    worst_day: stats.worst_day,
    book_hit_worst_day: row.weight * stats.worst_day.r,
    annual_sigma: stats.annual_sigma,
    excess_kurtosis: stats.excess_kurtosis,
    noah_share: stats.noah_share,
    hill_left: stats.hill_left ? { alpha: stats.hill_left.alpha, k: stats.hill_left.k, se: stats.hill_left.se } : null,
  };
}

function lineage(params, window) {
  return {
    sources: [
      "Benoit Mandelbrot and Richard Hudson, The (Mis)behavior of Markets, 2004: Noah effect and scaling.",
      "Nassim Taleb, Statistical Consequences of Fat Tails, 2020: Hill estimator, max-to-sum, Gaussian understatement.",
      "Bruce Hill, A Simple General Approach to Inference About the Tail of a Distribution, Annals of Statistics 1975.",
      "Dimitris Politis and Joseph Romano, The Stationary Bootstrap, JASA 1994.",
    ],
    riskless_series: params.riskless?.series || "DGS3MO",
    riskless_as_of: params.riskless?.as_of || null,
    window_start: window.start,
    window_end: window.end,
    sessions: window.sessions,
    drift: "Every simulated path drifts at the Treasury bill. The sample mean is removed before resampling.",
    hedged_note: "Weights are today's signed market value over NAV, rebalanced daily inside the hypothetical. Cash and omitted value earn the bill.",
  };
}

/**
 * Build the tail panel from a sleeve book and the same parameter file the
 * time-average panel reads.
 */
export function evaluateTailRisk({ nav, asOf = null, positions = [], params = {}, paths = PATHS, horizon = HORIZON }) {
  const { wealth, omitted, included, lNow, gross, coverage, dates, rfDaily } = selectBook({ nav, positions, params });
  const names = included.map(nameTail).sort((left, right) => left.book_hit_worst_day - right.book_hit_worst_day);
  const base = {
    ...SCHEMA_FLAGS,
    schema_version: 1,
    owner: "michael",
    as_of: asOf,
    nav: Number.isFinite(wealth) ? wealth : null,
    window: { sessions: dates.length, start: dates[0] || null, end: dates.at(-1) || null, coverage, l_now: lNow, gross },
    book: null,
    simulation: null,
    concentration: null,
    names,
    omitted: omitted.sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight)),
    lineage: lineage(params, { start: dates[0] || null, end: dates.at(-1) || null, sessions: dates.length }),
  };
  if (!included.length || rfDaily == null) return { ...base, reason: "no_eligible_names" };
  if (dates.length < MIN_SESSIONS) return { ...base, reason: "short_window" };

  const bookSimple = [];
  const bookDates = [];
  for (const date of dates) {
    let stock = 0;
    for (const row of included) stock += row.weight * row.map.get(date);
    const atScale = stock + (1 - lNow) * rfDaily;
    if (atScale > -0.999) {
      bookSimple.push(atScale);
      bookDates.push(date);
    }
  }
  const book = describeSeries(bookSimple, bookDates);
  const sigmaSimple = sampleStdev(bookSimple);
  const centered = bookSimple.map((value) => value - mean(bookSimple) + rfDaily);
  const seed = seedFrom(`${asOf || ""}|${dates.at(-1) || ""}|${included.map((row) => `${row.ticker}:${row.weight.toFixed(4)}`).join(",")}`);

  const alphaLeft = book.hill_left ? book.hill_left.alpha : null;
  const nu = alphaLeft == null ? 3 : Math.min(30, Math.max(2.05, alphaLeft));
  const scale = sigmaSimple * Math.sqrt((nu - 2) / nu);

  const run = (draw, salt) => simulate(draw, { rng: mulberry32(seed ^ salt), paths, horizon });
  const bootstrap = run(blockBootstrapDraw(centered), 0x1);
  const student = run((rng) => rfDaily + scale * studentT(rng, nu), 0x2);
  const gaussian = run((rng) => rfDaily + sigmaSimple * normal(rng), 0x3);

  const largest = included.slice().sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight))[0];
  const largestTail = names.find((row) => row.ticker === largest.ticker) || null;

  return {
    ...base,
    book: {
      ...book,
      hill_left: book.hill_left ? { ...book.hill_left, reading: tailReading(book.hill_left.alpha) } : null,
      hill_right: book.hill_right ? { alpha: book.hill_right.alpha, k: book.hill_right.k, se: book.hill_right.se } : null,
    },
    simulation: {
      paths,
      horizon,
      seed,
      drift: "riskless",
      block_mean_length: MEAN_BLOCK,
      student_nu: nu,
      student_nu_source: alphaLeft == null ? "default_3" : "hill_left",
      models: { bootstrap, student, gaussian },
    },
    concentration: {
      ticker: largest.ticker,
      weight: largest.weight,
      book_hit_if_halved: -largest.weight / 2,
      book_hit_worst_day: largestTail ? largestTail.book_hit_worst_day : null,
      worst_day: largestTail ? largestTail.worst_day : null,
    },
  };
}
