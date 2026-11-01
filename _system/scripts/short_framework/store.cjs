'use strict';
// Private append-only evidence and decisions. SQLite transactions prevent lost imports.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const E = require('../../../dashboard/short-framework-engine.js');
const hash = value => crypto.createHash('sha256').update(E.canonical(value)).digest('hex');
const fileHash = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const KINDS = new Set(['security', 'event', 'fundamentals', 'market', 'borrow', 'terms', 'thesis', 'costs',
  'portfolio', 'review', 'entry_fill', 'cover_fill', 'loan_return', 'split', 'mark', 'recall',
  'cashflow', 'external_flow', 'order', 'outcome', 'universe', 'fractional_settlement']);
const LEDGER_KINDS = new Set(['entry_fill', 'cover_fill', 'loan_return', 'split', 'mark', 'recall', 'cashflow', 'external_flow', 'order', 'fractional_settlement']);
function write(filename, value) {
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  const temporary = filename + '.' + crypto.randomUUID() + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
  fs.renameSync(temporary, filename);
}
function validate(r, now = new Date().toISOString()) {
  E.canonical(r);
  if (!r || !KINDS.has(r.kind) || typeof r.id !== 'string' || !r.id.trim()) throw new TypeError('Unknown evidence kind or missing record identity');
  const known = E.time(r.known_at);
  if (known > E.time(now)) throw new TypeError('Evidence is not yet known');
  if (!/^https:\/\//.test(r.source_url || '') || !r.locator || !/^[a-f0-9]{64}$/.test(r.source_sha256 || '')) throw new TypeError('Source URL, locator and SHA-256 required');
  if (r.at && E.time(r.at) > known) throw new TypeError('Evidence predates its occurrence');
  const number = (key, zero = false) => {
    if (typeof r[key] !== 'number' || !Number.isFinite(r[key]) || (zero ? r[key] < 0 : r[key] <= 0)) throw new TypeError('Invalid ' + key);
  };
  if (r.receipt_path && fileHash(r.receipt_path) !== r.source_sha256) throw new TypeError('Receipt hash mismatch');
  if (LEDGER_KINDS.has(r.kind) && (!r.at || r.observed !== true || !r.broker_reference)) throw new TypeError('Ledger imports require observed broker evidence');
  if (['entry_fill', 'cover_fill'].includes(r.kind)) {
    number('shares'); number('price'); number('fees', true);
    if (!r.instrument_id || !r.policy_sha256 || !r.order_id || !r.event_id || r.compliance_verified !== true) throw new TypeError('Fill lacks instrument, event, policy, order or compliance evidence');
    if (r.kind === 'entry_fill' && !r.issuer_id) throw new TypeError('Fill issuer missing');
    if (r.arrival_at && E.time(r.arrival_at) > E.time(r.at)) throw new TypeError('Fill precedes order arrival');
  }
  if (r.kind === 'borrow') {
    number('annual_rate', true); number('shares', true);
    if (!['indication', 'approval', 'accrual', 'rejection'].includes(r.status)) throw new TypeError('Unknown borrow status');
    E.time(r.quoted_at);
    if (E.time(r.quoted_at) > known) throw new TypeError('Future borrow quote');
    if (r.status === 'approval' && (!r.broker || !r.reference || r.shares <= 0)) throw new TypeError('Borrow approval needs broker reference and size');
  }
  if (r.kind === 'security') {
    E.time(r.valid_from);
    if (!r.instrument_id || !r.issuer_id || !r.ticker || !r.reviewer) throw new TypeError('Security identity incomplete');
    if (r.valid_until && E.time(r.valid_until) <= E.time(r.valid_from)) throw new TypeError('Invalid security interval');
  }
  if (r.kind === 'market') {
    number('bid'); number('ask');
    if (r.ask < r.bid || E.time(r.quote_at) > known) throw new TypeError('Invalid quote or clock');
    if (!r.instrument_id || !['clear', 'restricted', 'unknown'].includes(r.ssr)) throw new TypeError('Quote instrument/SSR missing');
  }
  if (r.kind === 'fundamentals') {
    E.noFutureLabels(r);
    if (!r.issuer_id || !r.period_end || !Array.isArray(r.facts) || r.as_filed !== true) throw new TypeError('As-filed fact provenance required');
    for (const fact of r.facts) if (!fact.accession || !fact.tag || E.time(fact.known_at) > known) throw new TypeError('Fact unavailable at snapshot clock');
  }
  if (r.kind === 'terms') {
    number('shares_before'); number('saleable_shares', true); number('net_proceeds', true);
    if (!r.reviewer || r.reconciled !== true || !r.deal_id || !['priced', 'closed', 'exercisable', 'terminated'].includes(r.economic_state)
      || ['cash_reconciled', 'claims_reconciled', 'split_basis_reconciled', 'saleability_reconciled'].some(k => r[k] !== true)) throw new TypeError('Financing reconciliation incomplete');
  }
  if (r.kind === 'review') {
    if (!r.event_id || !r.reviewer || r.outcome_blinded !== true || !['primary', 'second'].includes(r.review_role)) throw new TypeError('Review identity, role and outcome blinding required');
    for (const key of ['identity', 'clock', 'economic_state', 'cash_and_shares', 'saleability']) {
      if (!['pass', 'fail', 'unresolved'].includes(r.checks?.[key])) throw new TypeError('Incomplete review checks');
    }
  }
  if (r.kind === 'universe' && (r.independent_universe !== true || !r.instrument_id || !r.issuer_id || r.selection_basis === 'eventual_split')) throw new TypeError('Independent dated universe membership required');
  if (r.kind === 'outcome' && (!r.forecast_id || !r.event_id || !r.issuer_id || !r.instrument_id || !r.policy_sha256
    || !Number.isFinite(r.net_dollars) || !r.at || r.completed_cover !== true || r.loan_return_verified !== true
    || !Array.isArray(r.execution_ids) || !r.execution_ids.length || !Array.isArray(r.cashflow_ids))) throw new TypeError('Outcome requires frozen forecast and complete execution/cost/loan evidence');
  if (['event', 'thesis', 'costs', 'portfolio', 'universe'].includes(r.kind)) E.noFutureLabels(r);
  return r;
}
class Store {
  constructor(filename) {
    fs.mkdirSync(path.dirname(filename), { recursive: true });
    this.db = new DatabaseSync(filename);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS evidence(seq INTEGER PRIMARY KEY,id TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,
        known_at TEXT NOT NULL,payload TEXT NOT NULL,recorded_at TEXT NOT NULL,previous_hash TEXT,hash TEXT NOT NULL UNIQUE);
      CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,event_id TEXT NOT NULL,policy_hash TEXT NOT NULL,
        input_hash TEXT NOT NULL,account_hash TEXT NOT NULL,cutoff TEXT NOT NULL,mode TEXT NOT NULL,payload TEXT NOT NULL,
        UNIQUE(event_id,policy_hash,cutoff,mode));
      CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY,event_id TEXT NOT NULL,policy_hash TEXT NOT NULL,
        decision_id TEXT NOT NULL,frozen_at TEXT NOT NULL,entry_at TEXT NOT NULL,status TEXT NOT NULL,
        UNIQUE(event_id,policy_hash,entry_at));`);
  }
  close() { this.db.close(); }
  records() {
    let previous = null;
    return this.db.prepare('SELECT * FROM evidence ORDER BY seq').all().map(row => {
      const record = JSON.parse(row.payload);
      if (row.previous_hash !== previous || hash({ record, recorded_at: row.recorded_at, previous_hash: previous }) !== row.hash) throw new TypeError('Evidence chain mismatch');
      previous = row.hash;
      return record;
    });
  }
  import(records, now = new Date().toISOString()) {
    if (!Array.isArray(records)) throw new TypeError('Import must be an array');
    records.forEach(r => validate(r, now));
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const existing = this.records(), seen = new Map(existing.map(r => [r.id, E.canonical(r)]));
      let previous = this.db.prepare('SELECT hash FROM evidence ORDER BY seq DESC LIMIT 1').get()?.hash || null, added = 0;
      for (const record of records) {
        const content = E.canonical(record), duplicate = seen.get(record.id);
        if (duplicate) { if (content !== duplicate) throw new TypeError('Immutable evidence identity conflict'); continue; }
        if (record.kind === 'outcome') {
          const forecast = this.db.prepare('SELECT * FROM forecasts WHERE id=?').get(record.forecast_id);
          if (!forecast || forecast.event_id !== record.event_id || forecast.status !== 'estimate' || E.time(record.at) < E.time(forecast.entry_at)) throw new TypeError('Outcome/forecast identity or clock mismatch');
          const frozen = JSON.parse(this.db.prepare('SELECT payload FROM decisions WHERE id=?').get(forecast.decision_id).payload);
          if (record.issuer_id !== frozen.snapshot.event.issuer_id || record.instrument_id !== frozen.snapshot.event.instrument_id
            || record.policy_sha256 !== forecast.policy_hash) throw new TypeError('Outcome is not bound to the frozen issuer, instrument and policy');
          const references = new Map(existing.concat(records).map(r => [r.id, r]));
          const executions = record.execution_ids.map(id => references.get(id));
          const settlements = [...references.values()].filter(r => r.kind === 'fractional_settlement' && r.event_id === record.event_id
            && r.instrument_id === record.instrument_id && E.time(r.known_at) <= E.time(record.known_at));
          if (!executions.some(r => r?.kind === 'entry_fill') || !executions.some(r => r?.kind === 'cover_fill') && !settlements.length
            || executions.some(r => !r || !['entry_fill', 'cover_fill'].includes(r.kind) || r.event_id !== record.event_id
              || r.instrument_id !== record.instrument_id || r.policy_sha256 !== record.policy_sha256
              || E.time(r.at) < E.time(forecast.entry_at) || E.time(r.known_at) > E.time(record.known_at))) throw new TypeError('Outcome execution references are incomplete or mismatched');
          const flows = record.cashflow_ids.map(id => references.get(id));
          if (flows.some(r => !r || r.kind !== 'cashflow' || r.event_id !== record.event_id || E.time(r.known_at) > E.time(record.known_at))) throw new TypeError('Outcome cost references are incomplete or mismatched');
          const complete = (kinds, supplied) => {
            const expected = [...references.values()].filter(r => kinds.includes(r.kind) && r.event_id === record.event_id
              && E.time(r.known_at) <= E.time(record.known_at)).map(r => r.id).sort();
            if (new Set(supplied).size !== supplied.length || E.canonical(expected) !== E.canonical([...supplied].sort())) throw new TypeError('Outcome must include every observed event execution and cost');
          };
          complete(['entry_fill', 'cover_fill'], record.execution_ids);
          complete(['cashflow'], record.cashflow_ids);
          const net = executions.reduce((s, r) => s + (r.kind === 'entry_fill' ? 1 : -1) * r.shares * r.price - r.fees, 0)
            + flows.reduce((s, r) => s + r.amount, 0) + settlements.reduce((s, r) => s + r.amount, 0);
          if (Math.abs(net - record.net_dollars) > .02) throw new TypeError('Outcome dollars do not reconcile to observed executions and costs');
          if (record.stressed_net_dollars !== undefined) {
            let adverse = 0;
            for (const fill of executions) {
              const quote = [...references.values()].filter(q => q.kind === 'market' && q.nbbo_verified === true
                && q.instrument_id === fill.instrument_id && (!q.account_reference || q.account_reference === fill.account_reference)
                && fill.arrival_at && E.time(q.known_at) <= E.time(fill.arrival_at) && E.time(q.quote_at) <= E.time(fill.arrival_at)
                && E.time(fill.arrival_at) - E.time(q.quote_at) <= 5000).sort((a, b) => E.time(b.quote_at) - E.time(a.quote_at))[0];
              if (!quote) throw new TypeError('Observed cost stress requires matched arrival NBBO for every execution');
              const mid = (quote.bid + quote.ask) / 2;
              adverse += Math.max(0, (fill.kind === 'entry_fill' ? mid - fill.price : fill.price - mid) * fill.shares);
            }
            const extra = adverse + executions.reduce((s, r) => s + r.fees, 0) + flows.reduce((s, r) => s + Math.max(0, -r.amount), 0);
            if (record.stress_basis !== 'double_observed_costs_v1' || !Number.isFinite(record.stressed_net_dollars)
              || Math.abs(record.stressed_net_dollars - (net - extra)) > .02) throw new TypeError('Observed doubled-cost stress does not reconcile');
          }
          let closed = E.initialAccount(1);
          for (const row of [...references.values()].filter(r => LEDGER_KINDS.has(r.kind) && r.instrument_id === record.instrument_id
            && E.time(r.known_at) <= E.time(record.known_at)).sort((a, b) => E.time(a.at) - E.time(b.at))) closed = E.reduce(closed, row);
          const position = closed.positions[record.instrument_id];
          if (!position || position.shares > 1e-9 || position.loan_shares > 1e-9) throw new TypeError('Outcome still has open shares or an unreturned loan');
          const prior = existing.concat(records.slice(0, records.indexOf(record))).find(r => r.kind === 'outcome' && r.forecast_id === record.forecast_id);
          if (prior) throw new TypeError('A frozen forecast already has an outcome');
        }
        const digest = hash({ record, recorded_at: now, previous_hash: previous });
        this.db.prepare('INSERT INTO evidence(id,kind,known_at,payload,recorded_at,previous_hash,hash) VALUES(?,?,?,?,?,?,?)')
          .run(record.id, record.kind, record.known_at, content, now, previous, digest);
        previous = digest; seen.set(record.id, content); added++;
      }
      // Validate all observed cash/position changes before committing any batch.
      const ledger = existing.concat(records.filter(r => !existing.some(x => x.id === r.id))).filter(r => LEDGER_KINDS.has(r.kind));
      let state = E.initialAccount(1); // Position validity does not depend on initial capital.
      for (const record of ledger.sort((x, y) => E.time(x.at) - E.time(y.at))) state = E.reduce(state, record);
      this.db.exec('COMMIT'); return { added, total: seen.size, chain_sha256: previous };
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  decision(envelope, mode = 'replay', now = new Date().toISOString()) {
    if (!['replay', 'shadow', 'live_review'].includes(mode)) throw new TypeError('Unknown decision mode');
    const { snapshot, account } = envelope, spec = E.policy(envelope.policy);
    if (mode !== 'replay' && (Math.abs(E.time(now) - E.time(snapshot.as_of)) > 5000 || snapshot.observation_mode !== 'prospective')) throw new TypeError('Forward decisions require current actual observation clocks');
    const result = E.evaluate(snapshot, account, spec);
    const record = { schema_version: E.VERSION, policy: spec, snapshot, account, result,
      engine_sha256: fileHash(path.resolve(__dirname, '../../../dashboard/short-framework-engine.js')),
      policy_sha256: hash(spec), input_sha256: hash(snapshot), account_sha256: hash(account), mode };
    record.id = hash(record);
    const old = this.db.prepare('SELECT id FROM decisions WHERE event_id=? AND policy_hash=? AND cutoff=? AND mode=?')
      .get(snapshot.event.id, record.policy_sha256, snapshot.as_of, mode);
    if (old && old.id !== record.id) throw new TypeError('Cannot replace a frozen decision');
    this.db.prepare('INSERT OR IGNORE INTO decisions VALUES(?,?,?,?,?,?,?,?)').run(record.id,
      snapshot.event.id, record.policy_sha256, record.input_sha256, record.account_sha256, snapshot.as_of, mode, E.canonical(record));
    return record;
  }
  freeze(record, entryAt, now = new Date().toISOString()) {
    const persisted = this.db.prepare('SELECT payload FROM decisions WHERE id=?').get(record.id);
    if (!persisted || persisted.payload !== E.canonical(record)) throw new TypeError('Unknown or changed frozen decision');
    if (record.mode === 'replay' || E.time(entryAt) <= E.time(now) || Math.abs(E.time(record.snapshot.as_of) - E.time(now)) > 5000) throw new TypeError('Forecast must be frozen before future entry from a current decision');
    if (entryAt !== record.snapshot.event.entry_at) throw new TypeError('Forecast entry differs from frozen schedule');
    const status = record.result.eligible ? 'estimate' : 'abstain';
    const id = hash({ decision_id: record.id, entry_at: entryAt });
    const prior = this.db.prepare('SELECT id FROM forecasts WHERE event_id=? AND policy_hash=? AND entry_at=?')
      .get(record.result.event_id, record.policy_sha256, entryAt);
    if (prior && prior.id !== id) throw new TypeError('Cannot replace frozen event/policy forecast');
    this.db.prepare('INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,?,?)').run(id, record.result.event_id,
      record.policy_sha256, record.id, now, entryAt, status);
    return { id, status, entry_at: entryAt, decision_id: record.id };
  }
  coverDecision(envelope, now = new Date().toISOString()) {
    const { snapshot, account } = envelope, spec = E.policy(envelope.policy);
    E.noFutureLabels(snapshot); E.noFutureLabels(account);
    if (snapshot.observation_mode !== 'prospective' || Math.abs(E.time(snapshot.as_of) - E.time(now)) > 5000) throw new TypeError('Cover review requires current observation clocks');
    const positions = (account.positions || []).filter(p => p.instrument_id === snapshot.security?.instrument_id);
    if (positions.length !== 1) throw new TypeError('Exactly one attributed short position required');
    const result = E.exitIntent(positions[0], snapshot, spec);
    const record = { schema_version: E.VERSION, type: 'cover', policy: spec, snapshot, account, result,
      engine_sha256: fileHash(path.resolve(__dirname, '../../../dashboard/short-framework-engine.js')),
      policy_sha256: hash(spec), input_sha256: hash(snapshot), account_sha256: hash(account), mode: 'live_review' };
    record.id = hash(record);
    const key = snapshot.event.id + '/cover/' + record.account_sha256;
    const old = this.db.prepare('SELECT id FROM decisions WHERE event_id=? AND policy_hash=? AND cutoff=? AND mode=?')
      .get(key, record.policy_sha256, snapshot.as_of, record.mode);
    if (old && old.id !== record.id) throw new TypeError('Cannot replace a frozen cover decision');
    this.db.prepare('INSERT OR IGNORE INTO decisions VALUES(?,?,?,?,?,?,?,?)').run(record.id, key,
      record.policy_sha256, record.input_sha256, record.account_sha256, snapshot.as_of, record.mode, E.canonical(record));
    return record;
  }
  project(initialEquity, asOf) {
    let a = E.initialAccount(initialEquity);
    const rows = this.records().filter(r => LEDGER_KINDS.has(r.kind) && E.time(r.known_at) <= E.time(asOf));
    for (const r of rows.sort((x, y) => E.time(x.at) - E.time(y.at))) a = E.reduce(a, r);
    return { account: a, metrics: E.accountMetrics(a, asOf) };
  }
  status() {
    const records = this.records(), counts = {}, byEvent = new Map();
    for (const r of records) {
      counts[r.kind] = (counts[r.kind] || 0) + 1;
      if (r.kind === 'review') { const rows = byEvent.get(r.event_id) || []; rows.push(r); byEvent.set(r.event_id, rows); }
    }
    const reviews = [...byEvent.values()];
    const pass = r => Object.values(r.checks).every(v => v === 'pass');
    const reviewed = reviews.filter(rows => rows.some(r => r.review_role === 'primary'));
    const doubleReviewed = reviews.filter(rows => rows.some(a => a.review_role === 'primary' && pass(a)
      && rows.some(b => b.review_role === 'second' && b.reviewer !== a.reviewer && pass(b))));
    const forecasts = this.db.prepare('SELECT status,count(*) AS n FROM forecasts GROUP BY status').all();
    return { counts, source_reviews: reviewed.length, independently_reviewed_passes: doubleReviewed.length,
      borrow_approvals: records.filter(r => r.kind === 'borrow' && r.status === 'approval').length,
      observed_entry_fills: counts.entry_fill || 0, observed_cover_fills: counts.cover_fill || 0,
      frozen_estimates: forecasts.find(r => r.status === 'estimate')?.n || 0,
      frozen_abstentions: forecasts.find(r => r.status === 'abstain')?.n || 0,
      evaluated_forecasts: counts.outcome || 0, independent_universe_records: counts.universe || 0,
      production_authority: 'none' };
  }
}
module.exports = { Store, validate, hash, fileHash, write, LEDGER_KINDS };
