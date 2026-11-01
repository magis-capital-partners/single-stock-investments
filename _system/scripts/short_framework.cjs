#!/usr/bin/env node
'use strict';
// Offline first. This command never opens a Gateway session or submits an order.
const fs = require('node:fs');
const path = require('node:path');
const E = require('../../dashboard/short-framework-engine.js');
const { Store, hash, fileHash, write } = require('./short_framework/store.cjs');
const A = require('./short_framework/adapters.cjs');
const R = require('./short_framework/research.cjs');
const O = require('./short_framework/operations.cjs');
const C = require('./short_framework/context.cjs');
const ROOT = path.resolve(__dirname, '../..');
function args(argv) {
  const result = { command: argv[0] || 'help' };
  for (let i = 1; i < argv.length; i++) {
    if (!argv[i].startsWith('--') || !argv[i + 1] || argv[i + 1].startsWith('--')) throw new TypeError('Options require --name value');
    const key = argv[i].slice(2); if (Object.hasOwn(result, key)) throw new TypeError('Duplicate option: ' + key);
    result[key] = argv[++i];
  }
  return result;
}
function jsonInput(filename) {
  if (!filename) throw new TypeError('--input is required');
  const raw = fs.readFileSync(filename, 'utf8').trim();
  return raw.startsWith('[') || raw.startsWith('{') && !raw.includes('\n{') ? JSON.parse(raw) : raw.split(/\r?\n/).filter(Boolean).map(JSON.parse);
}
function independentEvents(records) {
  return records.filter(r => r.kind === 'event').filter(r => r.family !== 'fundamental' || records.some(u =>
    u.kind === 'universe' && u.independent_universe === true && u.instrument_id === r.instrument_id
    && E.time(u.known_at) <= E.time(r.known_at) && (!u.valid_until || E.time(u.valid_until) > E.time(r.known_at))));
}
async function build(root, work, store, options) {
  const loaded = A.loadEvents(root), records = store.records(), extra = independentEvents(records);
  const events = loaded.events.concat(extra.filter(e => !loaded.events.some(x => x.id === e.id)));
  const builtAt = new Date().toISOString(), asOf = options['as-of'] || builtAt;
  E.time(asOf);
  const priceFile = options.prices || path.join(root, '_system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z/prices.sqlite');
  const prices = new A.Prices(root, events, { calendar: options.calendar, filename: priceFile });
  const optionalHash = filename => fs.existsSync(filename) ? fileHash(filename) : null;
  const inputs = {
    events_sha256: loaded.source_sha256, evidence_sha256: hash(records),
    prices_sha256: optionalHash(priceFile), prices_wal_sha256: optionalHash(priceFile + '-wal'),
    calendar_sha256: hash({ sessions: prices.days, basis: prices.calendar_basis, verified: prices.calendar_verified }),
    calendar_source_sha256: options.calendar ? fileHash(options.calendar) : null,
    action_repairs_sha256: optionalHash(path.join(A.cached(root), 'corporate_action_repairs.json')),
    review_packets_sha256: optionalHash(path.join(A.cached(root), 'review_packets.local.json')),
    broker_sha256: options.broker ? fileHash(options.broker) : null,
  };
  const codeFiles = ['dashboard/short-framework-engine.js', '_system/scripts/short_framework.cjs',
    ...['store', 'adapters', 'research', 'operations', 'discovery', 'context'].map(n => '_system/scripts/short_framework/' + n + '.cjs')];
  const implementation = Object.fromEntries(codeFiles.map(f => [f, fileHash(path.join(ROOT, f))]));
  const declaration = { protocol: R.protocol(), implementation_sha256: hash(implementation),
    inputs_sha256: hash(inputs), cutoff: asOf, ledger_initial_equity: Number(options.equity || 50000) };
  const runDir = path.join(work, 'runs', builtAt.replace(/[-:.]/g, '') + '_' + hash(declaration).slice(0, 16));
  fs.mkdirSync(runDir, { recursive: true });
  const protocolFile = path.join(runDir, 'protocol.json');
  if (fs.existsSync(protocolFile) && hash(A.read(protocolFile).declaration) !== hash(declaration)) throw new TypeError('Frozen protocol changed');
  if (!fs.existsSync(protocolFile)) write(protocolFile, { declaration, declared_at: new Date().toISOString() });
  const counts = {}, coverage = {}, models = [], diagnostics = [];
  for (const e of events) {
    counts[e.family] = (counts[e.family] || 0) + 1;
    const f = e.financials || {}, key = Number.isFinite(f.score) ? 'scored' : 'missing_or_unscored';
    coverage[key] = (coverage[key] || 0) + 1;
  }
  if (prices.available) {
    try {
      for (const model of declaration.protocol.models) {
        models.push(R.run(events, prices, model, records));
        if (models.length % 30 === 0) process.stderr.write('Compared ' + models.length + '/' + declaration.protocol.models.length + ' frozen settings\n');
      }
      for (const variant of R.VARIANTS) for (const [first, last] of [['2021-01-01', '2022-12-31'], ['2023-01-01', '2024-12-31'], ['2025-01-01', prices.last]]) {
        const model = declaration.protocol.models.find(m => m.variant === variant && m.hold === 1 && m.cost === 'base' && m.evidence === 'conditional' && m.ssr === 'skip');
        diagnostics.push({ first, last, ...R.run(events, prices, model, records, { first, last }) });
      }
    } finally { prices.close(); }
  }
  if (optionalHash(priceFile) !== inputs.prices_sha256 || optionalHash(priceFile + '-wal') !== inputs.prices_wal_sha256
    || (options.calendar ? fileHash(options.calendar) : null) !== inputs.calendar_source_sha256
    || A.loadEvents(root).source_sha256 !== inputs.events_sha256 || hash(store.records()) !== inputs.evidence_sha256
    || optionalHash(path.join(A.cached(root), 'corporate_action_repairs.json')) !== inputs.action_repairs_sha256
    || optionalHash(path.join(A.cached(root), 'review_packets.local.json')) !== inputs.review_packets_sha256
    || (options.broker ? fileHash(options.broker) : null) !== inputs.broker_sha256
    || hash(Object.fromEntries(codeFiles.map(f => [f, fileHash(path.join(ROOT, f))]))) !== declaration.implementation_sha256)
    throw new TypeError('Replay inputs or implementation changed during the run; publication refused');
  const panel = A.reviewPanel(root, events), projection = store.project(Number(options.equity || 50000), asOf);
  const broker = options.broker ? jsonInput(options.broker) : {};
  const reconciliation = O.reconcile(projection.account, broker, asOf);
  const ready = O.readiness(store, projection, reconciliation, records);
  const summary = { schema_version: E.VERSION, built_at: builtAt, research_only: true, production_authority: 'none',
    dataset_version: hash({ source: loaded.source_sha256, declaration, ready, counts, asOf }).slice(0, 24),
    market_through: prices.last, financial_source: loaded.basis, source_sha256: loaded.source_sha256,
    counts, financial_coverage: coverage, comparison_count: models.length,
    declared_comparison_count: declaration.protocol.models.length, comparisons_complete: models.length === declaration.protocol.models.length,
    protocol: declaration.protocol, implementation_sha256: declaration.implementation_sha256,
    inputs_sha256: declaration.inputs_sha256, input_hashes: inputs,
    calendar_basis: prices.calendar_basis, calendar_verified: prices.calendar_verified,
    models, chronological_diagnostics: diagnostics,
    source_review: { selected: panel.source_packets, cached_packets: panel.source_packets,
      automated_checks_passed: panel.checks_passed || 0, completed_primary_reviews: ready.source_reviews,
      independently_reviewed_passes: ready.independently_reviewed_passes,
      note: 'Cached source packets and automated checks do not complete underwriting or independent review.' },
    evidence: ready, reconciliation: { reconciled: reconciliation.reconciled, breaks: reconciliation.breaks.length },
    limitations: [
      'Old studies remain unchanged. All new historical comparisons are exploratory development.',
      'Completed-action catalogue supports post-split comparisons only; it cannot establish an unbiased announcement cohort.',
      'Recorded volume covers partial venues and is not verified consolidated capacity. Price proxies are not NBBO or fills.',
      'The independent fundamentals-only universe is unavailable until separately sourced membership and financial records are imported.',
      'Fundamental signal counts in old exports are lower bounds under the original scoring contract; exact counts and company profile require new evidence.',
      'Unresolved positions, stale marks, fractional obligations and pending loan returns remain liabilities. Funded return ratios are suppressed when incomplete.',
      'Real broker evidence and forward outcomes cannot be generated by a historical replay. Readiness counts never grant production authority.',
    ] };
  write(path.join(runDir, 'summary.json'), summary);
  write(path.join(work, 'review-panel.local.json'), panel);
  write(path.join(work, 'reconciliation.local.json'), reconciliation);
  const dest = options.out ? path.resolve(options.out) : path.join(root, '_system/data/reverse_splits/framework');
  const dashboard = path.join(root, 'dashboard/data/short_framework');
  // Only explicit aggregate fields are published; no account, receipt paths, fills or ticket contents.
  for (const dir of [dest, dashboard]) {
    write(path.join(dir, 'summary.json'), summary);
    write(path.join(dir, 'manifest.json'), { schema_version: 'short_framework_manifest.v1',
      dataset_version: summary.dataset_version, summary_sha256: fileHash(path.join(dir, 'summary.json')) });
  }
  return { comparisons: models.length, verified_entries: models.filter(m => m.evidence_mode === 'verified').reduce((s, m) => s + m.entered, 0),
    cached_review_packets: panel.source_packets, completed_reviews: ready.source_reviews, market_through: prices.last,
    production_authority: 'none' };
}
async function main(argv = process.argv.slice(2)) {
  const options = args(argv), root = path.resolve(options['source-root'] || ROOT);
  const work = path.resolve(options.work || path.join(root, '_system/data/reverse_splits/local/short_framework/v1'));
  if (options.command === 'help') {
    process.stdout.write('Commands: build, import, evaluate, shadow, status, reconcile, handoff, cover, verify-handoff, review-export, discover\n'
      + 'Common options: --source-root PATH --work PATH --input FILE --as-of ISO --equity USD\n'
      + 'Imports and decisions remain private. build publishes aggregate comparisons and evidence gaps.\n'); return;
  }
  const store = new Store(path.join(work, 'evidence.sqlite'));
  try {
    const now = new Date().toISOString(); let result;
    if (options.command === 'build') result = await build(root, work, store, options);
    else if (options.command === 'import') { const incoming = jsonInput(options.input); result = store.import(Array.isArray(incoming) ? incoming : [incoming], now); }
    else if (['evaluate', 'shadow'].includes(options.command)) {
      const envelope = jsonInput(options.input), mode = options.command === 'shadow' ? 'shadow' : 'replay';
      result = store.decision(envelope, mode, now);
      if (mode === 'shadow') result = { decision: result, forecast: store.freeze(result, envelope.snapshot.event.entry_at, now) };
      write(path.join(work, 'last-decision.local.json'), result);
    } else if (options.command === 'status') {
      const projection = store.project(Number(options.equity || 50000), options['as-of'] || now);
      result = O.readiness(store, projection, null);
    } else if (options.command === 'reconcile') {
      const at = options['as-of'] || now, projection = store.project(Number(options.equity || 50000), at);
      result = O.reconcile(projection.account, jsonInput(options.input), at);
      write(path.join(work, 'reconciliation.local.json'), result);
    } else if (['handoff', 'cover'].includes(options.command)) {
      const envelope = jsonInput(options.input), record = options.command === 'cover' ? store.coverDecision(envelope, now) : store.decision(envelope, 'live_review', now);
      const projection = store.project(Number(options.equity || 50000), now);
      const broker = options.broker ? jsonInput(options.broker) : {};
      const reservations = C.hubReservations(options['hub-ledger'], work, store.records());
      const reconciliation = C.assertAccount(envelope, projection, broker, reservations, now);
      const ready = O.readiness(store, projection, reconciliation, store.records(), record.policy_sha256);
      const approvalFile = path.join(root, '_system/reviews/approved/short_framework_v1.json');
      const approval = fs.existsSync(approvalFile) ? A.read(approvalFile) : null;
      result = options.command === 'cover' ? O.coverHandoff(envelope, record, now, options.mode || 'dry_run')
        : O.handoff(envelope, record, now, options.mode || 'dry_run', approval, ready);
      write(path.join(work, 'handoff.local.json'), result);
      write(path.join(work, 'handoffs', result.request_sha256 + '.json'), { handoff: result, envelope, record_id: record.id,
        initial_equity: Number(options.equity || 50000), broker });
    } else if (options.command === 'verify-handoff') {
      if (!/^[a-f0-9]{64}$/.test(options['request-hash'] || '')) throw new TypeError('Invalid private handoff reference');
      const saved = A.read(path.join(work, 'handoffs', options['request-hash'] + '.json'));
      const row = store.db.prepare('SELECT payload FROM decisions WHERE id=?').get(saved.record_id);
      if (!row) throw new TypeError('Private decision missing');
      const record = JSON.parse(row.payload), projection = store.project(saved.initial_equity || 50000, now);
      if (record.engine_sha256 !== fileHash(path.join(ROOT, 'dashboard/short-framework-engine.js'))) throw new TypeError('Decision engine changed; a new reviewed policy/decision is required');
      const reservations = C.hubReservations(options['hub-ledger'], work, store.records(), options['exclude-intent']);
      const reconciliation = C.assertAccount(saved.envelope, projection, saved.broker, reservations, now);
      const ready = O.readiness(store, projection, reconciliation, store.records(), record.policy_sha256);
      const approvalFile = path.join(root, '_system/reviews/approved/short_framework_v1.json');
      const approved = fs.existsSync(approvalFile) ? A.read(approvalFile) : null;
      const verified = record.type === 'cover' ? O.coverHandoff(saved.envelope, record, now, saved.handoff.request.mode)
        : O.handoff(saved.envelope, record, now, saved.handoff.request.mode, approved, ready);
      if (verified.request_sha256 !== options['request-hash']) throw new TypeError('Private handoff changed or size is no longer available');
      result = { valid: true, request: verified.request, request_sha256: verified.request_sha256,
        account_reference: saved.envelope.account.account_reference || null };
    } else if (options.command === 'review-export') {
      const panel = A.reviewPanel(root, A.loadEvents(root).events);
      const destination = options.out ? path.resolve(options.out) : path.join(work, 'review-panel.local.json');
      write(destination, panel); result = { selected: panel.source_packets, automated_checks_passed: panel.checks_passed, completed_reviews: store.status().source_reviews };
    } else if (options.command === 'discover') {
      const { discover } = require('./short_framework/discovery.cjs');
      result = await discover({ root, work, store, maximum: Number(options.maximum || 20), since: options.since || now.slice(0, 10) });
    } else throw new TypeError('Unknown command: ' + options.command);
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } finally { store.close(); }
}
if (require.main === module) main().catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; });
module.exports = { main, args, build, independentEvents };
