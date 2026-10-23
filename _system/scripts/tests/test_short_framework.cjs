const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const E = require('../../../dashboard/short-framework-engine.js');
const { Store, validate, hash } = require('../short_framework/store.cjs');
const A = require('../short_framework/adapters.cjs');
const R = require('../short_framework/research.cjs');
const O = require('../short_framework/operations.cjs');
const C = require('../short_framework/context.cjs');
const NOW = '2026-10-22T13:30:00Z', BEFORE = '2026-10-22T13:29:45Z';
const SOURCE = { source_url: 'https://example.test/primary', source_sha256: 'a'.repeat(64), locator: 'section 1' };
function fixture() {
  const policy = E.policy();
  const snapshot = { as_of: NOW, observation_mode: 'prospective',
    event: { id: 'split/1/event', issuer_id: 'cik/1', instrument_id: 'instrument/1', ticker: 'TEST', family: 'split',
      known_at: '2026-10-20T20:00:00Z', verified: true, first_seen_at: '2026-10-20T20:01:00Z', effective_at: '2026-10-21T13:30:00Z',
      entry_at: NOW, entry_until: '2026-10-22T20:00:00Z', ...SOURCE },
    security: { issuer_id: 'cik/1', instrument_id: 'instrument/1', ticker: 'TEST', known_at: BEFORE,
      valid_from: '2026-01-01T00:00:00Z', identity_verified: true, units_verified: true, conid: 123, currency: 'USD' },
    fundamentals: { known_at: '2026-10-01T12:00:00Z', period_end: '2026-06-30', score: 70,
      numeric_signals: 4, as_filed: true, operating_company: true },
    market: { known_at: BEFORE, quote_at: BEFORE, bid: 10, ask: 10.01, nbbo_verified: true,
      adv_shares: 100000, adv_sessions: 20, adv_known_at: '2026-10-21T20:00:00Z', volume_verified: true,
      ssr: 'clear', ssr_known_at: BEFORE },
    borrow: { known_at: BEFORE, quoted_at: BEFORE, status: 'approval', broker: 'TEST_BROKER', reference: 'TEST_ONLY', shares: 1000, annual_rate: .05 },
    costs: { known_at: BEFORE, roundtrip_fraction: .001, locate_per_share: 0,
      calibration_verified: true, entry_observations: 10, cover_observations: 10 },
    thesis: { known_at: BEFORE, catalyst_at: '2026-10-23T15:00:00Z', target_price: 8,
      scenarios: { bear: 5, base: 8, bull: 15 }, claims_and_financing_reconciled: true,
      lenses: E.LENSES.map(lens_id => ({ lens_id, known_at: BEFORE, status: 'supported', ...SOURCE,
        mechanism: 'Test mechanism', contrary_evidence: 'Test contrary evidence', falsifier: 'Test falsifier' })) } };
  const account = { known_at: BEFORE, equity: 1000000, positions: [], reservations: [],
    other_stress_loss: 0, other_stressed_margin: 0, reconciled: true, basis: 'observed_account', source_reference: 'TEST_ONLY', account_reference: 'TEST_ACCOUNT' };
  return { snapshot, account, policy };
}
function temporary(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'short-framework-test-'));
  const store = new Store(path.join(dir, 'evidence.sqlite'));
  t.after(() => { store.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  return store;
}
function record(kind, fields = {}) { return { id: kind + '/test', kind, known_at: NOW, ...SOURCE, ...fields }; }
function fill(kind = 'entry_fill', fields = {}) {
  return record(kind, { at: NOW, observed: true, broker_reference: 'TEST_ONLY', instrument_id: 'instrument/1',
    issuer_id: 'cik/1', policy_sha256: 'b'.repeat(64), event_id: 'split/1/event', order_id: 'TEST_ORDER',
    shares: 10, price: 10, fees: 1, compliance_verified: true, ...fields });
}
test('browser and node produce identical immutable decisions', () => {
  const context = { globalThis: {} }; vm.createContext(context);
  vm.runInContext(fs.readFileSync('dashboard/short-framework-engine.js', 'utf8'), context);
  const input = fixture(), original = JSON.stringify(input);
  const browser = context.globalThis.ShortFrameworkEngine.evaluate(input.snapshot, input.account, input.policy);
  const node = E.evaluate(input.snapshot, input.account, input.policy);
  assert.equal(E.canonical(browser), E.canonical(node)); assert.equal(JSON.stringify(input), original);
  assert.equal(node.state, 'eligible'); assert.equal(node.sizing.shares, 100);
});
test('verified results reject indicative borrow and proxy market capacity', () => {
  const f = fixture(); f.snapshot.borrow.status = 'indication'; f.snapshot.market.volume_verified = false;
  const r = E.evaluate(f.snapshot, f.account, f.policy);
  assert.ok(r.blockers.includes('borrow')); assert.ok(r.blockers.includes('liquidity')); assert.equal(r.sizing.shares, 0);
});
test('future facts, stale quotes and future evidence cannot enter a decision', () => {
  const f = fixture(); f.snapshot.fundamentals.known_at = '2026-10-23T00:00:00Z'; f.snapshot.market.quote_at = '2026-10-22T13:00:00Z';
  const r = E.evaluate(f.snapshot, f.account, f.policy);
  assert.ok(r.blockers.includes('fundamentals')); assert.ok(r.blockers.includes('quote'));
  f.snapshot.fundamentals.future_return = -.9;
  assert.throws(() => E.evaluate(f.snapshot, f.account, f.policy), /Outcome field/);
});
test('nonfinite inputs are rejected before JSON serialization can erase them', () => {
  const f = fixture(); f.account.equity = Infinity;
  assert.throws(() => E.evaluate(f.snapshot, f.account, f.policy), /finite JSON/);
});
test('unknown SSR blocks, restricted SSR requires an above-bid passive limit', () => {
  const f = fixture(); f.snapshot.market.ssr = 'unknown';
  assert.ok(E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('ssr'));
  f.snapshot.market.ssr = 'restricted'; f.snapshot.market.ssr_execution = 'passive_above_nbb'; f.snapshot.market.short_limit = 10;
  assert.ok(E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('ssr'));
  f.snapshot.market.short_limit = 10.01;
  assert.ok(!E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('ssr'));
});
test('issuer overlap includes pending orders, and account-wide stress constrains size', () => {
  const f = fixture(); f.account.reservations = [{ issuer_id: 'cik/1', shares: 1, mark: 10 }];
  assert.ok(E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('issuer_overlap'));
  f.account.reservations = []; f.account.other_stressed_margin = 900000;
  assert.equal(E.evaluate(f.snapshot, f.account, f.policy).sizing.shares, 0);
});
test('missing financial count stays unknown in verified mode; old lower-bound contract is explicit', () => {
  const f = fixture(); f.snapshot.fundamentals.numeric_signals = null; f.snapshot.fundamentals.numeric_signals_lower_bound = 3;
  assert.ok(E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('fundamentals'));
  assert.ok(!E.evaluate(f.snapshot, f.account, E.policy({ evidence_mode: 'conditional' })).blockers.includes('fundamentals'));
});
test('fundamentals-only cannot use a universe selected from eventual splitters', () => {
  const f = fixture(); f.snapshot.event.family = 'fundamental';
  const p = E.policy({ variant: 'fundamentals_only', entry: 'observation' });
  assert.ok(E.evaluate(f.snapshot, f.account, p).blockers.includes('opportunity'));
  f.snapshot.event.independent_universe = true;
  assert.ok(!E.evaluate(f.snapshot, f.account, p).blockers.includes('opportunity'));
});
test('completed-split catalogue cannot select an announcement cohort', () => {
  const f = fixture(); f.snapshot.event.discovery_basis = 'completed_action_catalogue';
  f.snapshot.event.effective_at = '2026-10-23T13:30:00Z';
  assert.ok(E.evaluate(f.snapshot, f.account, E.policy({ entry: 'announcement' })).blockers.includes('entry_window'));
});
test('revenue warnings do not replace reconciled claims, six lenses and a falsifier', () => {
  const f = fixture(); delete f.snapshot.thesis.lenses[0].falsifier;
  assert.ok(E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('thesis'));
  f.snapshot.thesis.lenses[0].falsifier = 'Test'; f.snapshot.thesis.claims_and_financing_reconciled = false;
  assert.ok(E.evaluate(f.snapshot, f.account, f.policy).blockers.includes('thesis'));
});
test('short proceeds remain offset by liability; partial cover and loan persist', () => {
  let a = E.initialAccount(1000);
  a = E.reduce(a, fill()); assert.equal(E.accountMetrics(a, NOW).equity, 999);
  a = E.reduce(a, fill('cover_fill', { shares: 4, price: 8 }));
  assert.equal(a.positions['instrument/1'].shares, 6); assert.equal(a.positions['instrument/1'].loan_shares, 10);
  assert.equal(E.accountMetrics(a, NOW).loan_returns_pending, 1);
  assert.throws(() => E.reduce(a, record('loan_return', { at: NOW, instrument_id: 'instrument/1', shares: 5 })), /Unproven loan return/);
  a = E.reduce(a, record('loan_return', { at: NOW, instrument_id: 'instrument/1', shares: 4 }));
  assert.equal(a.positions['instrument/1'].loan_shares, 6);
});
test('corporate actions preserve liability and retain fractional obligations', () => {
  let a = E.reduce(E.initialAccount(1000), fill('entry_fill', { shares: 3 }));
  const before = E.accountMetrics(a, NOW);
  a = E.reduce(a, record('split', { at: NOW, instrument_id: 'instrument/1', new_per_old: 1 / 10 }));
  const after = E.accountMetrics(a, NOW);
  assert.equal(after.liability, before.liability); assert.equal(after.fractional_positions, 1);
  const exit = E.exitIntent(a.positions['instrument/1'], { as_of: NOW, recall: { known_at: NOW }, market: {} }, E.policy());
  assert.equal(exit.state, 'cover_blocked'); assert.equal(exit.shares, 0);
});
test('missing quote cannot invent a stop or recall fill', () => {
  const position = { shares: 10, loan_shares: 10, entry_price: 10, mark: 20, instrument_id: 'instrument/1' };
  const exit = E.exitIntent(position, { as_of: NOW, recall: { known_at: NOW }, market: {} }, E.policy({ stop_fraction: .2 }));
  assert.equal(exit.state, 'cover_blocked'); assert.deepEqual(exit.reasons, ['recall', 'stop']);
});
test('order uncertainty survives restart and cannot become a fresh order', () => {
  let a = E.initialAccount(1000);
  for (const [i, state] of ['requested', 'submitted', 'uncertain'].entries()) a = E.reduce(a, { id: String(i), kind: 'order', at: NOW, order_id: 'o1', state });
  assert.throws(() => E.reduce(a, { id: 'bad', kind: 'order', at: NOW, order_id: 'o1', state: 'submitted' }), /Illegal order transition/);
  a = E.reduce(a, { id: 'found', kind: 'order', at: NOW, order_id: 'o1', state: 'acknowledged' });
  assert.equal(a.orders.o1.state, 'acknowledged');
});
test('evidence batch import is atomic and conflicting IDs cannot replace history', t => {
  const s = temporary(t), first = fill();
  assert.equal(s.import([first], NOW).added, 1); assert.equal(s.import([first], NOW).added, 0);
  assert.throws(() => s.import([record('cashflow', { observed: true, broker_reference: 'T', at: NOW, amount: -1, category: 'borrow' }), { ...first, price: 11 }], NOW), /identity conflict/);
  assert.equal(s.records().length, 1);
  assert.throws(() => s.import([fill('cover_fill', { shares: 20 })], NOW), /Cover exceeds/);
  assert.equal(s.records().length, 1);
});
test('tampered evidence is detected before any projection or readiness result', t => {
  const s = temporary(t); s.import([fill()], NOW);
  s.db.prepare('UPDATE evidence SET payload=?').run(JSON.stringify({ ...fill(), shares: 900 }));
  assert.throws(() => s.records(), /chain mismatch/);
});
test('forward forecasts freeze before entry, retain abstentions and cannot be replaced', t => {
  const s = temporary(t), f = fixture();
  f.snapshot.event.entry_at = '2026-10-22T13:31:00Z'; f.snapshot.borrow.status = 'indication';
  const decision = s.decision(f, 'shadow', NOW), frozen = s.freeze(decision, f.snapshot.event.entry_at, NOW);
  assert.equal(frozen.status, 'abstain'); assert.equal(s.status().frozen_abstentions, 1);
  f.snapshot.borrow.status = 'approval'; f.snapshot.as_of = '2026-10-22T13:30:01Z';
  const replacement = s.decision(f, 'shadow', '2026-10-22T13:30:01Z');
  assert.throws(() => s.freeze(replacement, f.snapshot.event.entry_at, '2026-10-22T13:30:01Z'), /replace frozen/);
  assert.throws(() => s.decision(f, 'shadow', '2026-10-23T00:00:00Z'), /current actual observation/);
});
test('replay records cannot be relabeled as prospective forecasts', t => {
  const s = temporary(t), f = fixture(), decision = s.decision(f, 'replay', NOW);
  assert.throws(() => s.freeze(decision, '2026-10-23T13:30:00Z', NOW), /before future entry/);
});
test('calibration matches instrument and pre-arrival clock, preserving unmatched fills', () => {
  const q = record('market', { known_at: BEFORE, quote_at: BEFORE, instrument_id: 'instrument/2', bid: 9, ask: 11, nbbo_verified: true });
  const f = fill('entry_fill', { arrival_at: '2026-10-22T13:29:46Z' });
  assert.equal(O.calibration([q, f]).matched_fills, 0);
  q.instrument_id = 'instrument/1'; assert.equal(O.calibration([q, f]).matched_fills, 1);
  q.known_at = NOW; assert.equal(O.calibration([q, f]).matched_fills, 0);
});
test('same person cannot satisfy independent source review', t => {
  const s = temporary(t), base = record('review', { event_id: 'e1', reviewer: 'test-reviewer', outcome_blinded: true,
    review_role: 'primary', checks: { identity: 'pass', clock: 'pass', economic_state: 'pass', cash_and_shares: 'pass', saleability: 'pass' } });
  s.import([base, { ...base, id: 'second', review_role: 'second' }], NOW);
  assert.equal(s.status().source_reviews, 1); assert.equal(s.status().independently_reviewed_passes, 0);
});
test('full-account cash cannot be mislabeled as attributed strategy reconciliation', () => {
  const a = E.initialAccount(1000), result = O.reconcile(a, { source: 'ibkr_flex', complete: true, as_of: NOW, known_at: NOW,
    scope: 'account', cash: 1000, positions: [], other_stress_loss: 0, other_stressed_margin: 0 }, NOW);
  assert.equal(result.reconciled, false); assert.match(result.breaks.join(), /attributed/);
});
test('live handoff needs completed evidence review and separate human policy approval', t => {
  const store = temporary(t), f = fixture(), decision = store.decision(f, 'live_review', NOW);
  const draft = O.handoff(f, decision, NOW);
  assert.equal(draft.request.mode, 'dry_run'); assert.equal(draft.transmitted, false);
  assert.throws(() => O.handoff(f, decision, NOW, 'live'), /approval/);
  f.account.equity -= 1;
  assert.throws(() => O.handoff(f, decision, NOW), /frozen decision/);
});
test('security master rejects ambiguous overlapping instruments', () => {
  const rows = [1, 2].map(i => record('security', { instrument_id: 'i' + i, issuer_id: 'cik/1', ticker: 'TEST', valid_from: BEFORE }));
  assert.equal(A.resolveSecurity(rows, { issuer: 'cik/1', ticker: 'TEST' }, NOW), null);
});

test('event-specific financing and thesis evidence cannot leak between deals on one instrument', () => {
  const e = { id: 'deal/1', issuer_id: 'cik/1', instrument_id: 'instrument/1' };
  const other = record('terms', { event_id: 'deal/2', instrument_id: e.instrument_id });
  assert.equal(A.latest([other], 'terms', e, E.time(NOW)), undefined);
  const own = { ...other, id: 'own', event_id: e.id };
  assert.equal(A.latest([other, own], 'terms', e, E.time(NOW)).id, 'own');
});
test('research declares every setting before replay and retains unavailable baselines', () => {
  const p = R.protocol(); assert.equal(p.models.length, 180); assert.equal(new Set(p.models.map(m => m.id)).size, 180);
  assert.equal(p.models.filter(m => m.variant === 'fundamentals_only').length, 36);
});
test('naive timestamps, fabricated fills and incomplete financing terms are rejected', () => {
  assert.throws(() => E.time('2026-10-22T09:30:00'), /aware/);
  assert.throws(() => validate({ ...fill(), observed: false }, NOW), /observed broker evidence/);
  assert.throws(() => validate(record('terms', { shares_before: 100, saleable_shares: 10, net_proceeds: 10 }), NOW), /reconciliation/);
});
test('fractional liabilities close only with an observed broker settlement', () => {
  let a = E.reduce(E.initialAccount(1000), fill('entry_fill', { shares: 3 }));
  a = E.reduce(a, record('split', { at: NOW, instrument_id: 'instrument/1', new_per_old: .1 }));
  assert.throws(() => E.reduce(a, record('fractional_settlement', { at: NOW, instrument_id: 'instrument/1', shares: .3, amount: -30 })), /Verified fractional/);
  a = E.reduce(a, record('fractional_settlement', { at: NOW, instrument_id: 'instrument/1', shares: .3, amount: -30, settlement_verified: true }));
  assert.ok(a.positions['instrument/1'].shares < 1e-9); assert.ok(a.positions['instrument/1'].loan_shares < 1e-9);
  assert.equal(E.accountMetrics(a, NOW).open_positions, 0);
});

test('account used by the order path must match journal equity, positions and account-wide risk', () => {
  const f = fixture(), actual = E.initialAccount(f.account.equity);
  const broker = { source: 'ibkr_flex', scope: 'short_framework', complete: true, as_of: NOW, known_at: NOW,
    account_reference: f.account.account_reference, cash: actual.cash, positions: [], other_stress_loss: 0, other_stressed_margin: 0 };
  const projection = { account: actual, metrics: E.accountMetrics(actual, NOW) };
  assert.equal(C.assertAccount(f, projection, broker, [], NOW).reconciled, true);
  f.account.equity += 100;
  assert.throws(() => C.assertAccount(f, projection, broker, [], NOW), /private journal/);
  f.account.equity -= 100;
  assert.throws(() => C.assertAccount(f, projection, { ...broker, account_reference: 'other' }, [], NOW), /reconciliation required/);
  assert.throws(() => C.assertAccount(f, projection, broker, [{ order_id: 'new', instrument_id: 'i2', issuer_id: 'cik/2', action: 'SELL', shares: 10, mark: 10 }], NOW), /Pending orders changed/);
});

test('hub reservations retain uncertain orders and terminal fills until imported', t => {
  const { DatabaseSync } = require('node:sqlite');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'short-framework-hub-')), filename = path.join(dir, 'hub.sqlite');
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const db = new DatabaseSync(filename);
  db.exec(`CREATE TABLE order_intents(intent_uuid TEXT,strategy TEXT,mode TEXT,state TEXT,quantity_decimal TEXT,limit_price_decimal TEXT,action TEXT,account_alias TEXT);
    CREATE TABLE executions(intent_uuid TEXT,quantity_decimal TEXT);
    CREATE TABLE order_events(intent_uuid TEXT,event_type TEXT,payload_json TEXT,created_at TEXT);`);
  db.prepare('INSERT INTO order_intents VALUES(?,?,?,?,?,?,?,?)').run('o1', 'short_framework', 'paper', 'SubmitUncertain', '10', '10', 'SELL', 'TEST_ACCOUNT');
  db.prepare('INSERT INTO executions VALUES(?,?)').run('o1', '4');
  db.prepare('INSERT INTO order_events VALUES(?,?,?,?)').run('o1', 'intent_created', JSON.stringify({ framework_binding: 'SF1:' + 'a'.repeat(64) + ':' + 'b'.repeat(64) }), NOW);
  fs.mkdirSync(path.join(dir, 'handoffs'));
  fs.writeFileSync(path.join(dir, 'handoffs', 'b'.repeat(64) + '.json'), JSON.stringify({ envelope: fixture() }));
  assert.equal(C.hubReservations(filename, dir, [])[0].shares, 10);
  assert.equal(C.hubReservations(filename, dir, [{ kind: 'entry_fill', hub_intent_uuid: 'o1', shares: 4 }])[0].shares, 6);
  assert.deepEqual(C.hubReservations(filename, dir, [], 'o1'), []);
  db.exec("UPDATE order_intents SET state='Cancelled'");
  assert.equal(C.hubReservations(filename, dir, [])[0].shares, 4);
  assert.deepEqual(C.hubReservations(filename, dir, [{ kind: 'entry_fill', hub_intent_uuid: 'o1', shares: 4 }]), []);
  db.close();
});

function outcomeFixture(store) {
  const envelope = fixture(); envelope.snapshot.event.entry_at = '2026-10-22T13:31:00Z';
  const decision = store.decision(envelope, 'shadow', NOW), forecast = store.freeze(decision, envelope.snapshot.event.entry_at, NOW);
  const policy_sha256 = decision.policy_sha256, after = '2026-10-22T14:02:00Z';
  const entry = fill('entry_fill', { at: '2026-10-22T13:31:00Z', known_at: '2026-10-22T13:31:00Z', arrival_at: '2026-10-22T13:30:59Z', policy_sha256 });
  const cover = fill('cover_fill', { at: '2026-10-22T14:00:00Z', known_at: '2026-10-22T14:00:00Z', arrival_at: '2026-10-22T13:59:59Z', price: 8, policy_sha256 });
  const loan = record('loan_return', { at: '2026-10-22T14:01:00Z', known_at: after, instrument_id: entry.instrument_id, shares: 10, observed: true, broker_reference: 'TEST_ONLY' });
  const cost = record('cashflow', { at: cover.at, known_at: after, category: 'borrow', amount: -2, event_id: entry.event_id, observed: true, broker_reference: 'TEST_ONLY' });
  const quotes = [entry, cover].map((r, i) => record('market', { id: 'quote/' + i, known_at: r.arrival_at, quote_at: r.arrival_at,
    instrument_id: r.instrument_id, bid: r.price - .01, ask: r.price + .01, nbbo_verified: true, ssr: 'clear' }));
  const outcome = record('outcome', { at: after, known_at: after, forecast_id: forecast.id, event_id: entry.event_id,
    issuer_id: entry.issuer_id, instrument_id: entry.instrument_id, policy_sha256, net_dollars: 16,
    execution_ids: [entry.id, cover.id], cashflow_ids: [cost.id], completed_cover: true, loan_return_verified: true });
  return { entry, cover, loan, cost, quotes, outcome, after };
}

test('forward outcomes reconcile every fill, cash cost and returned loan', t => {
  const s = temporary(t), f = outcomeFixture(s);
  assert.throws(() => s.import([f.entry, f.cover, f.cost, f.loan, { ...f.outcome, cashflow_ids: [], net_dollars: 18 }], f.after), /every observed/);
  assert.equal(s.status().observed_entry_fills, 0);
  s.import([f.entry, f.cover, f.cost, f.loan, f.outcome], f.after);
  assert.equal(s.status().evaluated_forecasts, 1);
});

test('positive doubled-cost stress cannot be asserted without matched execution evidence', t => {
  const s = temporary(t), f = outcomeFixture(s);
  const outcome = { ...f.outcome, stress_basis: 'double_observed_costs_v1', stressed_net_dollars: 12 };
  assert.throws(() => s.import([f.entry, f.cover, f.cost, f.loan, outcome], f.after), /matched arrival NBBO/);
  assert.throws(() => s.import([...f.quotes, f.entry, f.cover, f.cost, f.loan, { ...outcome, stressed_net_dollars: 20 }], f.after), /does not reconcile/);
  s.import([...f.quotes, f.entry, f.cover, f.cost, f.loan, outcome], f.after);
  assert.equal(s.status().evaluated_forecasts, 1);
});

test('broker fractional settlement can complete an outcome without an invented cover fill', t => {
  const s = temporary(t), f = outcomeFixture(s), entry = { ...f.entry, shares: 3 };
  const split = record('split', { at: f.cover.at, known_at: f.after, instrument_id: entry.instrument_id, new_per_old: .1, observed: true, broker_reference: 'TEST_ONLY' });
  const settlement = record('fractional_settlement', { at: f.loan.at, known_at: f.after, instrument_id: entry.instrument_id,
    event_id: entry.event_id, shares: .3, amount: -15, settlement_verified: true, observed: true, broker_reference: 'TEST_ONLY' });
  const outcome = { ...f.outcome, execution_ids: [entry.id], cashflow_ids: [], net_dollars: 14 };
  s.import([entry, split, settlement, outcome], f.after);
  assert.equal(s.status().evaluated_forecasts, 1); assert.equal(s.project(1000, f.after).metrics.open_positions, 0);
});

test('dated fee schedule preserves frozen commission cap and SEC/TAF transitions', () => {
  assert.equal(E.stockFee(100, 10, '2026-09-30', true), 1.05);
  assert.equal(E.stockFee(100, 10, '2026-10-01', true), 1.03);
  assert.equal(E.stockFee(100, 10, '2026-10-01', false), 1.01);
  assert.equal(E.stockFee(1, .5, '2026-10-01', false), .01);
  assert.throws(() => E.policy({ fee_schedule: 'unversioned' }), /Unknown policy/);
});

test('published comparisons are complete and identical to the research artifact', () => {
  const { fileHash } = require('../short_framework/store.cjs');
  const root = path.resolve(__dirname, '../../..'), publicDir = path.join(root, 'dashboard/data/short_framework');
  const doc = JSON.parse(fs.readFileSync(path.join(publicDir, 'summary.json'), 'utf8'));
  const manifest = JSON.parse(fs.readFileSync(path.join(publicDir, 'manifest.json'), 'utf8'));
  assert.equal(doc.models.length, 180); assert.equal(doc.comparisons_complete, true);
  assert.equal(new Set(doc.models.map(m => m.id)).size, 180);
  assert.equal(fileHash(path.join(publicDir, 'summary.json')), manifest.summary_sha256);
  assert.equal(fileHash(path.join(root, '_system/data/reverse_splits/framework/summary.json')), manifest.summary_sha256);
  const sources = ['dashboard/short-framework-engine.js', '_system/scripts/short_framework.cjs',
    ...['store', 'adapters', 'research', 'operations', 'discovery', 'context'].map(n => '_system/scripts/short_framework/' + n + '.cjs')];
  assert.equal(doc.implementation_sha256, hash(Object.fromEntries(sources.map(f => [f, fileHash(path.join(root, f))]))));
  assert.equal(doc.inputs_sha256, hash(doc.input_hashes));
  assert.equal(doc.research_only, true); assert.equal(doc.production_authority, 'none');
  assert.equal(doc.models.filter(m => m.variant === 'fundamentals_only').every(m => !m.available), true);
  assert.equal(doc.models.filter(m => m.evidence_mode === 'verified').every(m => m.entered === 0), true);
  assert.doesNotMatch(JSON.stringify(doc), /account_reference|broker_reference|receipt_path|handoffs[\\/]/);
});

test('bounded SEC discovery preserves first-seen clocks and does not promote phrase leads', async t => {
  const s = temporary(t), dir = fs.mkdtempSync(path.join(os.tmpdir(), 'short-framework-sec-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const config = path.join(dir, '_system/data/reverse_splits'); fs.mkdirSync(config, { recursive: true });
  fs.writeFileSync(path.join(config, 'config.toml'), 'user_agent = "FrameworkTest test@example.test"');
  s.import([record('universe', { issuer_id: 'cik/1', instrument_id: 'instrument/1', independent_universe: true, selection_basis: 'all_listed_operating_companies' })]);
  const submission = { cik: 1, tickers: ['TEST'], filings: { recent: { accessionNumber: ['0000000001-26-000001'], form: ['8-K'],
    filingDate: ['2026-10-22'], primaryDocument: ['test.htm'], acceptanceDateTime: ['2026-10-22T20:00:00Z'] } } };
  const urls = [], fetcher = async url => { urls.push(url); return new Response(url.includes('/submissions/') ? JSON.stringify(submission) : '<html>Reverse stock split approved.</html>'); };
  const { discover } = require('../short_framework/discovery.cjs');
  const options = { root: dir, work: dir, store: s, maximum: 2, since: '2026-10-01', fetcher, delay: 0 };
  const first = await discover(options), lead = s.records().find(r => r.kind === 'event');
  assert.equal(first.requests, 2); assert.equal(first.new_leads, 1); assert.equal(first.coverage_complete, false);
  assert.equal(lead.event_status, 'phrase_lead_requires_source_review'); assert.equal(lead.identity_verified, false);
  assert.ok(E.time(lead.first_seen_at) >= E.time(lead.known_at));
  assert.equal((await discover(options)).new_leads, 0);
  assert.equal(s.records().filter(r => r.kind === 'event').length, 1);
  assert.ok(urls.every(url => /^https:\/\/(www|data)\.sec\.gov\//.test(url)));
  const denied = await discover({ ...options, fetcher: async () => new Response('', { status: 403 }) });
  assert.equal(denied.requests, 1); assert.equal(denied.blocked, true);
});

test('private CLI handoff verifies locally and rejects a later journal/account change', t => {
  const { spawnSync } = require('node:child_process'), { DatabaseSync } = require('node:sqlite');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'short-framework-cli-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const hub = path.join(dir, 'hub.sqlite'), db = new DatabaseSync(hub);
  db.exec('CREATE TABLE order_intents(strategy TEXT)'); db.close();
  const f = fixture(), at = Date.now(), iso = d => new Date(d).toISOString();
  f.snapshot.as_of = iso(at); f.snapshot.event.entry_at = iso(at - 1000); f.snapshot.event.entry_until = iso(at + 300000);
  f.snapshot.market.known_at = f.snapshot.market.quote_at = iso(at - 1000);
  f.snapshot.borrow.known_at = f.snapshot.borrow.quoted_at = iso(at - 1000);
  f.snapshot.thesis.catalyst_at = iso(at + E.DAY);
  const broker = { source: 'ibkr_flex', scope: 'short_framework', complete: true, as_of: iso(at), known_at: iso(at),
    account_reference: f.account.account_reference, cash: f.account.equity, positions: [], other_stress_loss: 0, other_stressed_margin: 0 };
  fs.writeFileSync(path.join(dir, 'decision.json'), JSON.stringify(f)); fs.writeFileSync(path.join(dir, 'broker.json'), JSON.stringify(broker));
  const cli = path.resolve(__dirname, '../short_framework.cjs');
  const run = args => spawnSync(process.execPath, [cli, ...args, '--work', dir], { encoding: 'utf8', timeout: 10000, windowsHide: true });
  const made = run(['handoff', '--input', path.join(dir, 'decision.json'), '--broker', path.join(dir, 'broker.json'), '--hub-ledger', hub, '--equity', String(f.account.equity)]);
  assert.equal(made.status, 0, made.stderr); const handoff = JSON.parse(made.stdout);
  const args = ['verify-handoff', '--request-hash', handoff.request_sha256, '--hub-ledger', hub];
  const checked = run(args); assert.equal(checked.status, 0, checked.stderr); assert.equal(JSON.parse(checked.stdout).valid, true);
  const store = new Store(path.join(dir, 'evidence.sqlite'));
  store.import([fill('entry_fill', { at: iso(at), known_at: iso(at), hub_intent_uuid: 'late-fill' })]); store.close();
  const changed = run(args); assert.equal(changed.status, 1); assert.match(changed.stderr, /reconciliation required/);
});
test('a mutated replay decision cannot become a shadow forecast', t => {
  const s = temporary(t), f = fixture(); f.snapshot.event.entry_at = '2026-10-22T13:31:00Z';
  const d = s.decision(f, 'replay', NOW);
  assert.throws(() => s.freeze({ ...d, mode: 'shadow' }, f.snapshot.event.entry_at, NOW), /changed frozen/);
});
test('an authorized reduce-only cover is available while new-entry approval is absent', t => {
  const s = temporary(t), f = fixture(); f.snapshot.operator_cover = true;
  f.account.positions = [{ instrument_id: 'instrument/1', issuer_id: 'cik/1', shares: 10, loan_shares: 10, mark: 10, entry_price: 10 }];
  const d = s.coverDecision(f, NOW), ticket = O.coverHandoff(f, d, NOW, 'live');
  assert.equal(ticket.request.action, 'BUY'); assert.equal(ticket.request.quantity, '10'); assert.equal(ticket.transmitted, false);
  f.account.reservations = [{ instrument_id: 'instrument/1', action: 'BUY', shares: 10 }];
  const reserved = s.coverDecision(f, NOW);
  assert.throws(() => O.coverHandoff(f, reserved, NOW, 'live'), /unreserved/);
});
test('reviewed handoff can be inspected in the browser with its content binding', async t => {
  const s = temporary(t), f = fixture(), d = s.decision(f, 'live_review', NOW);
  const V = require('../../../dashboard/short-framework-viz.js');
  const ticket = O.handoff(f, d, NOW);
  assert.equal((await V.inspect(ticket, NOW)).kind, 'handoff');
  ticket.request.quantity = '1000';
  await assert.rejects(V.inspect(ticket, NOW), /binding/);
});
test('browser refuses expired handoffs and escapes decision text', async t => {
  const s = temporary(t), f = fixture(), d = s.decision(f, 'live_review', NOW);
  const V = require('../../../dashboard/short-framework-viz.js');
  await assert.rejects(V.inspect(O.handoff(f, d, NOW), '2026-10-22T13:32:00Z'), /expired/);
  const html = V.decisionView({ kind: 'decision', ticker: '<script>bad()</script>', result: d.result });
  assert.ok(!html.includes('<script>')); assert.match(html, /&lt;script&gt;/);
});
test('operational policy cannot acquire authority through an imported flag', () => {
  assert.throws(() => E.policy({ production_authority: 'live' }), /cannot grant/);
});
test('outcome-only declarations cannot pass the evidence importer', () => {
  assert.throws(() => validate(record('outcome', { forecast_id: 'f', event_id: 'e', at: NOW, net_dollars: 100 }), NOW), /complete execution/);
});
function priceFixture(t) {
  const { DatabaseSync } = require('node:sqlite');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'short-framework-prices-')), filename = path.join(dir, 'prices.sqlite');
  const db = new DatabaseSync(filename), days = [];
  db.exec(`CREATE TABLE prices_daily(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL);
    CREATE TABLE price_provenance(ticker TEXT,date TEXT,nominal INTEGER,source TEXT,volume_basis TEXT);
    CREATE TABLE reverse_splits(ticker TEXT,ex_date TEXT,split_from REAL,split_to REAL);
    CREATE TABLE ssr_states(ticker TEXT,date TEXT,restricted INTEGER,source TEXT);`);
  for (let d = new Date('2026-08-03T12:00:00Z'); days.length < 40; d = new Date(d.valueOf() + E.DAY)) {
    if ([0, 6].includes(d.getUTCDay())) continue;
    const day = d.toISOString().slice(0, 10); days.push(day);
    db.prepare('INSERT INTO prices_daily VALUES(?,?,?,?,?,?,?)').run('TEST', day, 10, 11, 9, 10, 100000);
    db.prepare('INSERT INTO price_provenance VALUES(?,?,?,?,?)').run('TEST', day, 1, 'test_fixture', 'partial_venue');
    db.prepare('INSERT INTO ssr_states VALUES(?,?,?,?)').run('TEST', day, 0, 'test_fixture_at_open');
  }
  db.close();
  const prices = new A.Prices(dir, [], { filename });
  t.after(() => { prices.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  return { prices, days, dir, filename };
}

test('replay archives pin inputs and refuse publication when a source changes during replay', async t => {
  const f = priceFixture(t), store = temporary(t), { build } = require('../short_framework.cjs');
  const cache = A.cached(f.dir); fs.mkdirSync(cache, { recursive: true });
  const eventFile = path.join(cache, 'effective_events.local.json'); fs.writeFileSync(eventFile, '[]');
  const work = path.join(f.dir, 'work'), options = { prices: f.filename };
  const first = await build(f.dir, work, store, options);
  assert.equal(first.comparisons, 180);
  const publicFile = path.join(f.dir, 'dashboard/data/short_framework/summary.json'), previous = fs.readFileSync(publicFile, 'utf8');
  const runs = path.join(work, 'runs'), initial = fs.readdirSync(runs);
  assert.equal(initial.length, 1);
  const declaration = JSON.parse(fs.readFileSync(path.join(runs, initial[0], 'protocol.json'), 'utf8')).declaration;
  assert.equal(declaration.inputs_sha256, JSON.parse(previous).inputs_sha256);
  const original = R.run; let changed = false;
  R.run = (...args) => { if (!changed) { fs.writeFileSync(eventFile, '[ ]'); changed = true; } return original(...args); };
  try { await assert.rejects(build(f.dir, work, store, options), /inputs or implementation changed/); }
  finally { R.run = original; }
  assert.equal(fs.readFileSync(publicFile, 'utf8'), previous);
  assert.equal(fs.readdirSync(runs).length, 2);
});
test('prior volume is converted to current share units across reverse splits', t => {
  const { prices, days } = priceFixture(t);
  prices.setAction('TEST', days[20], .1);
  assert.equal(prices.prior('TEST', days[20]).adv, 10000);
  prices.setAction('TEST', days[20], .2); // Conflicting actions invalidate capacity.
  assert.equal(prices.prior('TEST', days[20]).adv, 0);
});
test('future close and realized volume cannot affect a pre-entry decision snapshot', t => {
  const { prices, days } = priceFixture(t);
  const event = { id: 'e', issuer: 'cik/1', ticker: 'TEST', family: 'deficiency', event_date: days[19],
    known_at: A.nyClock(days[19], '16:00:00'), source_url: SOURCE.source_url, source_locator: 'test' };
  const spec = E.policy({ variant: 'deficiency', entry: 'observation', evidence_mode: 'conditional', require_thesis: false });
  const before = A.assemble(event, days[20], prices, spec);
  const point = prices.point('TEST', days[20]); point.close = 1000; point.high = 2000; point.volume = 1;
  assert.deepEqual(A.assemble(event, days[20], prices, spec), before);
});

test('reviewed events can qualify their original catalogue identity after the review clock', t => {
  const { prices, days } = priceFixture(t), at = A.nyClock(days[20]);
  const event = { id: 'e', issuer: 'cik/1', ticker: 'TEST', family: 'deficiency', event_date: days[19],
    known_at: A.nyClock(days[19], '16:00:00'), source_url: SOURCE.source_url, source_locator: 'test' };
  const security = record('security', { issuer_id: 'cik/1', ticker: 'TEST', instrument_id: 'instrument/1', known_at: event.known_at,
    valid_from: event.known_at, identity_verified: true, units_verified: true });
  const review = record('event', { event_id: 'e', issuer_id: 'cik/1', instrument_id: 'instrument/1', known_at: at, verified: true });
  const spec = E.policy({ variant: 'deficiency', entry: 'observation' });
  assert.equal(A.assemble(event, days[20], prices, spec, [security, review]).event.verified, true);
  review.known_at = A.nyClock(days[21]);
  assert.equal(A.assemble(event, days[20], prices, spec, [security, review]).event.verified, false);
});

test('missing prior-session bars cannot claim twenty complete liquidity observations', t => {
  const { prices, days } = priceFixture(t);
  prices.history('TEST').delete(days[0]);
  const event = { id: 'e', issuer: 'cik/1', ticker: 'TEST', family: 'deficiency', event_date: days[19],
    known_at: A.nyClock(days[19], '16:00:00'), source_url: SOURCE.source_url, source_locator: 'test' };
  const snapshot = A.assemble(event, days[20], prices, E.policy({ variant: 'deficiency', entry: 'observation' }));
  assert.equal(snapshot.market.adv_sessions, 0);
});
test('portfolio replay retains unsupported covers and suppresses funded ratios', t => {
  const { prices, days } = priceFixture(t);
  const event = { id: 'e', issuer: 'cik/1', ticker: 'TEST', family: 'deficiency', event_date: days[19],
    known_at: A.nyClock(days[19], '16:00:00'), source_url: SOURCE.source_url, source_locator: 'test' };
  for (const day of days.slice(24)) prices.point('TEST', day).volume = 0;
  const model = R.protocol().models.find(m => m.variant === 'deficiency' && m.hold === 5 && m.cost === 'base' && m.evidence === 'conditional' && m.ssr === 'skip');
  const result = R.run([event], prices, model);
  assert.equal(result.entered, 1); assert.equal(result.unresolved_positions, 1);
  assert.ok(result.open_liability > 0); assert.ok(result.peak_margin > 0); assert.equal(result.cagr, null);
});
test('entry and cover order requests require exact framework references at the edge', async () => {
  const { validateOrderRequest } = await import('../../../dashboard/functions/_lib/order-requests.js');
  const req = { conid: 123, symbol: 'TEST', sec_type: 'STK', action: 'SELL', quantity: '10', limit_price: '10', strategy: 'short_framework' };
  assert.throws(() => validateOrderRequest(req, 'michael'), /reviewed short-framework/);
  const valid = { ...req, framework_decision_id: 'a'.repeat(64), framework_request_sha256: 'b'.repeat(64), rationale: 'SF1:' + 'a'.repeat(64) + ':' + 'b'.repeat(64) };
  assert.equal(validateOrderRequest(valid, 'michael').framework_request_sha256, 'b'.repeat(64));
  assert.throws(() => validateOrderRequest({ ...valid, rationale: 'changed' }, 'michael'), /exact request binding/);
});
