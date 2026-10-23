'use strict';
// Read the existing research caches. Provider mappings never become verified identities.
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const E = require('../../../dashboard/short-framework-engine.js');
const { hash, fileHash } = require('./store.cjs');
const read = filename => JSON.parse(fs.readFileSync(filename, 'utf8'));
const clocks = new Map();
function nyClock(day, clock = '09:30:00') {
  const key = day + '/' + clock;
  if (clocks.has(key)) return clocks.get(key);
  const noon = new Date(day + 'T12:00:00Z');
  const zone = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', timeZoneName: 'shortOffset' })
    .formatToParts(noon).find(x => x.type === 'timeZoneName').value;
  const offset = Number(zone.replace('GMT', ''));
  const result = day + 'T' + clock + (offset < 0 ? '-' : '+') + String(Math.abs(offset)).padStart(2, '0') + ':00';
  clocks.set(key, result); return result;
}
function dateAfter(day) { return new Date(Date.parse(day + 'T12:00:00Z') + E.DAY).toISOString().slice(0, 10); }
function cached(root) { return path.join(root, '_system/data/reverse_splits/local/profit_program/20261022_v1'); }
function loadEvents(root) {
  const dir = cached(root), primary = path.join(dir, 'effective_events.local.json');
  if (fs.existsSync(primary)) return { events: read(primary), source_sha256: fileHash(primary), basis: 'existing_as_filed_research_cache' };
  const published = path.join(root, '_system/data/reverse_splits/profit_program'), manifest = read(path.join(published, 'manifest.json'));
  const events = [];
  for (const part of manifest.parts) {
    if (!/^events-[a-z]+-\d{4}-\d{3}\.json$/.test(part.file)) throw new TypeError('Invalid source shard');
    const filename = path.join(published, part.file);
    if (fileHash(filename) !== part.sha256) throw new TypeError('Source shard hash mismatch');
    const doc = read(filename);
    if (doc.dataset_version !== manifest.dataset_version) throw new TypeError('Mixed source dataset');
    events.push(...doc.events);
  }
  return { events, source_sha256: fileHash(path.join(published, 'manifest.json')), basis: 'published_metadata_financial_clocks_incomplete' };
}
function latest(records, kind, event, cutoff) {
  return records.filter(r => r.kind === kind && E.time(r.known_at) <= cutoff
    && (r.event_id ? r.event_id === event.id : r.instrument_id ? r.instrument_id === event.instrument_id
      : r.issuer_id && r.issuer_id === event.issuer_id))
    .sort((a, b) => E.time(b.known_at) - E.time(a.known_at) || a.id.localeCompare(b.id))[0];
}
function resolveSecurity(records, row, asOf) {
  const cutoff = E.time(asOf), issuer = row.issuer_id || row.issuer;
  const candidates = records.filter(r => r.kind === 'security' && r.issuer_id === issuer && r.ticker === row.ticker
    && E.time(r.known_at) <= cutoff && E.time(r.valid_from) <= cutoff && (!r.valid_until || E.time(r.valid_until) > cutoff));
  if (new Set(candidates.map(r => r.instrument_id)).size > 1) return null;
  return candidates.sort((a, b) => E.time(b.known_at) - E.time(a.known_at))[0] || null;
}
class Prices {
  constructor(root, events, options = {}) {
    const filename = options.filename || path.join(root, '_system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z/prices.sqlite');
    this.available = fs.existsSync(filename); this.series = new Map(); this.actions = new Map(); this.priorCache = new Map();
    this.calendar_verified = false; this.calendar_basis = 'observed_dataset_dates';
    if (!this.available) { this.days = []; this.first = null; this.last = null; return; }
    this.db = new DatabaseSync(filename, { readOnly: true });
    const replay = path.join(cached(root), 'replays/deficiency_all__h10__25000__base__fixed__time.local.json');
    if (options.calendar) {
      const cal = read(options.calendar);
      if (!Array.isArray(cal.sessions) || !cal.source_url?.startsWith('https://') || !cal.source_sha256) throw new TypeError('Sourced session calendar required');
      this.days = cal.sessions; this.calendar_verified = cal.verified === true; this.calendar_basis = 'imported_exchange_sessions';
    } else if (fs.existsSync(replay)) {
      // Only session dates are consumed; no trade outcomes or performance select data.
      this.days = read(replay).daily.map(r => r.date);
      this.calendar_basis = 'existing_XNYS_exchange_calendars_replay_dates';
    } else this.days = this.db.prepare('SELECT DISTINCT date FROM prices_daily ORDER BY date').all().map(r => r.date);
    if (this.days.some((d, i) => !/^\d{4}-\d{2}-\d{2}$/.test(d) || i && d <= this.days[i - 1])) throw new TypeError('Invalid session calendar');
    const bounds = this.db.prepare('SELECT min(date) AS first,max(date) AS last FROM prices_daily').get();
    this.first = bounds.first; this.last = bounds.last; this.days = this.days.filter(d => d <= this.last);
    this.index = new Map(this.days.map((d, i) => [d, i]));
    this.openTimes = this.days.map(d => E.time(nyClock(d)));
    this.pointQuery = this.db.prepare(`SELECT p.*,v.nominal,v.source,v.volume_basis FROM prices_daily p
      LEFT JOIN price_provenance v ON v.ticker=p.ticker AND v.date=p.date WHERE p.ticker=? ORDER BY p.date`);
    this.ssrQuery = this.db.prepare('SELECT restricted FROM ssr_states WHERE ticker=? AND date=?');
    for (const action of this.db.prepare('SELECT ticker,ex_date,split_from,split_to FROM reverse_splits').all()) {
      if (action.split_from > 0 && action.split_to > 0) this.setAction(action.ticker, action.ex_date, action.split_to / action.split_from);
    }
    for (const e of events) if (e.family === 'split' && e.features?.ratio > 0) this.setAction(e.ticker, e.event_date, 1 / e.features.ratio);
    const repairs = path.join(cached(root), 'corporate_action_repairs.json');
    if (fs.existsSync(repairs)) for (const r of read(repairs)) if (r.price_factor > 0) this.setAction(r.ticker, r.ex_date, 1 / r.price_factor);
  }
  setAction(ticker, day, ratio) {
    this.priorCache.clear();
    const list = this.actions.get(ticker) || new Map();
    if (list.has(day) && Math.abs(list.get(day) / ratio - 1) > .001) list.set(day, null);
    else if (!list.has(day)) list.set(day, ratio);
    this.actions.set(ticker, list);
  }
  close() { this.db?.close(); }
  history(ticker) {
    if (!this.series.has(ticker)) {
      const points = new Map();
      for (const r of this.pointQuery.all(ticker)) {
        if (!r.nominal || ![r.open, r.high, r.low, r.close].every(x => Number.isFinite(x) && x > 0)
          || r.low > Math.min(r.open, r.close) || r.high < Math.max(r.open, r.close)) continue;
        points.set(r.date, r);
      }
      this.series.set(ticker, points);
    }
    return this.series.get(ticker);
  }
  point(ticker, day) { return this.available ? this.history(ticker).get(day) : null; }
  entryDay(row, entry = 'post_split') {
    if (!row.known_at) return null;
    const earliest = Math.max(E.time(row.known_at) + 300000, entry === 'post_split' ? E.time(nyClock(row.event_date, '16:00:00')) : 0);
    let lo = 0, hi = this.openTimes.length;
    while (lo < hi) { const mid = (lo + hi) >>> 1; if (this.openTimes[mid] <= earliest) lo = mid + 1; else hi = mid; }
    return this.days[lo] || null;
  }
  prior(ticker, day) {
    const key = ticker + '/' + day;
    if (this.priorCache.has(key)) return this.priorCache.get(key);
    const i = this.index.get(day), days = this.days.slice(Math.max(0, i - 20), i);
    let volume = 0, complete = days.length === 20, consolidated = complete;
    for (const d of days) {
      const r = this.point(ticker, d);
      if (!r || !Number.isFinite(r.volume) || r.volume < 0) { complete = false; consolidated = false; continue; }
      let units = 1;
      for (const [effective, ratio] of this.actions.get(ticker) || []) if (d < effective && effective <= day) {
        if (ratio === null) { units = 0; complete = false; consolidated = false; break; }
        units *= ratio;
      }
      // Historical share volume must be expressed in the entry day's share units.
      volume += r.volume * units;
      consolidated &&= r.volume_basis === 'US_consolidated';
    }
    const result = { adv: volume / 20, sessions: days.length, complete, verified: consolidated && this.calendar_verified,
      known_at: days.length ? nyClock(days.at(-1), '16:00:00') : null };
    this.priorCache.set(key, result); return result;
  }
}
function assemble(row, day, prices, spec, records = [], options = {}) {
  const asOf = options.asOf || nyClock(day), cutoff = E.time(asOf), issuer = row.issuer_id || row.issuer;
  const resolved = resolveSecurity(records, row, asOf), instrument = resolved?.instrument_id || 'unverified/' + issuer + '/' + row.ticker;
  const e = { id: row.id, issuer_id: issuer, instrument_id: instrument, ticker: row.ticker, family: row.family,
    known_at: row.known_at, source_url: row.source_url || '', locator: row.source_locator || row.locator || '',
    entry_at: options.entryAt || nyClock(day), entry_until: options.entryUntil || nyClock(day, '16:00:00'),
    discovery_basis: row.family === 'split' ? 'completed_action_catalogue' : 'source_disclosure',
    effective_at: row.family === 'split' ? nyClock(row.event_date) : null,
    first_seen_at: row.first_seen_at || row.captured_at || null, independent_universe: row.independent_universe === true,
    verified: row.verified === true };
  const reviewed = records.filter(r => r.kind === 'event' && (r.event_id || r.id) === row.id
    && r.issuer_id === issuer && r.instrument_id === instrument && E.time(r.known_at) <= cutoff)
    .sort((a, b) => E.time(b.known_at) - E.time(a.known_at))[0];
  if (reviewed) {
    e.verified = reviewed.verified === true;
    e.source_url = reviewed.source_url; e.locator = reviewed.locator;
    e.first_seen_at = reviewed.first_seen_at || e.first_seen_at;
  }
  const f = row.financials || {}, facts = f.evidence || [], filingDates = facts.map(r => r.filed).filter(Boolean).sort();
  const financial = { known_at: filingDates.length ? nyClock(dateAfter(filingDates.at(-1)), '00:00:00') : null,
    period_end: f.period || null, score: f.score ?? null, numeric_signals: null,
    numeric_signals_lower_bound: f.status === 'scored' && Number.isFinite(f.score) ? 3 : 0,
    signal_count_basis: 'Existing filing_rating guarantees at least three independent signals for scored results; exact count was not exported',
    as_filed: facts.length > 0 && facts.every(r => r.filed && E.time(nyClock(dateAfter(r.filed), '00:00:00')) <= cutoff),
    operating_company: null, cash: f.cash ?? null, cash_runway_years: f.runway_years ?? null,
    source_sha256: f.source_sha256 || null };
  const point = prices.point(row.ticker, day), prior = prices.prior(row.ticker, day);
  const half = (options.executionFraction ?? .0172) / 2;
  const ssr = prices.available ? prices.ssrQuery.get(row.ticker, day) : null;
  const snapshot = { as_of: asOf, observation_mode: options.observationMode || 'reconstruction', event: e,
    security: resolved || { instrument_id: instrument, issuer_id: issuer, ticker: row.ticker,
      known_at: row.known_at, valid_from: row.known_at, identity_verified: false, units_verified: false },
    fundamentals: latest(records, 'fundamentals', e, cutoff) || financial,
    market: latest(records, 'market', e, cutoff) || { known_at: asOf, quote_at: asOf,
      bid: point ? point.open * (1 - half) : null, ask: point ? point.open * (1 + half) : null,
      nbbo_verified: false, quote_basis: 'conditional_open_price_and_frozen_spread',
      adv_shares: prior.adv, adv_sessions: prior.complete ? prior.sessions : 0, adv_known_at: prior.known_at,
      volume_verified: prior.verified, ssr: ssr ? ssr.restricted ? 'restricted' : 'clear' : 'unknown',
      ssr_known_at: asOf },
    borrow: latest(records, 'borrow', e, cutoff) || { known_at: asOf, quoted_at: asOf, status: 'assumption',
      annual_rate: options.borrowApr ?? .5, shares: 1e12, reference: null, broker: null },
    costs: latest(records, 'costs', e, cutoff) || { known_at: asOf, roundtrip_fraction: options.executionFraction ?? .0172,
      locate_per_share: 0, calibration_verified: false, entry_observations: 0, cover_observations: 0 },
    thesis: latest(records, 'thesis', e, cutoff) || null, terms: latest(records, 'terms', e, cutoff) || null };
  return snapshot;
}
function reviewPanel(root, events) {
  const filename = path.join(cached(root), 'review_packets.local.json');
  if (!fs.existsSync(filename)) return { rows: [], source_packets: 0, manual_reviews_completed: 0 };
  const packets = read(filename), ids = new Set(events.map(e => e.id));
  const rows = packets.records.map(r => {
    const checks = { event_in_catalogue: ids.has(r.id), cached_source_present: r.source_available === true,
      source_hash_present: /^[a-f0-9]{64}$/.test(r.source_sha256 || ''),
      public_clock_after_header: !!r.header?.known_at && E.time(r.header.known_at) <= E.time(r.known_at),
      has_cited_clauses: (r.clauses || []).some(c => c.locator && c.excerpt) };
    return { event_id: r.id, ticker: r.ticker, family: r.family, source_url: r.source_url,
      source_sha256: r.source_sha256 || null, automated_checks: checks,
      status: 'requires_primary_and_independent_review', claims_and_financing_reconciled: false };
  });
  return { rows, source_packets: rows.length, source_packet_sha256: fileHash(filename),
    checks_passed: rows.filter(r => Object.values(r.automated_checks).every(Boolean)).length, manual_reviews_completed: 0 };
}
module.exports = { nyClock, dateAfter, cached, loadEvents, latest, resolveSecurity, Prices, assemble, reviewPanel, read };
