'use strict';
const E = require('../../../dashboard/short-framework-engine.js');
const { hash } = require('./store.cjs');
const mean = rows => rows.length ? rows.reduce((a, b) => a + b, 0) / rows.length : null;
function calibration(records) {
  const fills = records.filter(r => ['entry_fill', 'cover_fill'].includes(r.kind));
  const quotes = records.filter(r => r.kind === 'market' && r.nbbo_verified === true), matched = [];
  for (const fill of fills) {
    if (!fill.arrival_at) continue;
    const arrival = E.time(fill.arrival_at);
    const quote = quotes.filter(q => q.instrument_id === fill.instrument_id
      && (!q.account_reference || q.account_reference === fill.account_reference)
      && E.time(q.known_at) <= arrival && E.time(q.quote_at) <= arrival && arrival - E.time(q.quote_at) <= 5000)
      .sort((a, b) => E.time(b.quote_at) - E.time(a.quote_at))[0];
    if (!quote) continue;
    const mid = (quote.bid + quote.ask) / 2, entry = fill.kind === 'entry_fill';
    matched.push({ phase: entry ? 'entry' : 'cover', instrument_id: fill.instrument_id,
      order_id: fill.order_id, shares: fill.shares, notional: fill.shares * fill.price,
      shortfall: entry ? (mid - fill.price) / mid : (fill.price - mid) / mid,
      commission_fraction: fill.fees / (fill.shares * fill.price) });
  }
  const summary = rows => ({ n: rows.length, shares: rows.reduce((s, r) => s + r.shares, 0),
    mean_shortfall: mean(rows.map(r => r.shortfall)), mean_commission_fraction: mean(rows.map(r => r.commission_fraction)),
    weighted_shortfall: rows.length ? rows.reduce((s, r) => s + r.shortfall * r.notional, 0) / rows.reduce((s, r) => s + r.notional, 0) : null });
  return { observed_fills: fills.length, matched_fills: matched.length, unmatched_fills: fills.length - matched.length,
    entry: summary(matched.filter(r => r.phase === 'entry')), cover: summary(matched.filter(r => r.phase === 'cover')),
    size_buckets: [[0, 1000], [1000, 10000], [10000, 25000], [25000, Infinity]].map(([lo, hi]) => ({
      minimum_dollars: lo, maximum_dollars: Number.isFinite(hi) ? hi : null,
      entry: summary(matched.filter(r => r.phase === 'entry' && r.notional >= lo && r.notional < hi)),
      cover: summary(matched.filter(r => r.phase === 'cover' && r.notional >= lo && r.notional < hi)),
    })), status: matched.length ? 'observed_sample_requires_selection_and_size_review' : 'awaiting_observed_entry_and_cover_evidence' };
}
function reconcile(account, broker, asOf) {
  const breaks = [], at = E.time(asOf);
  let clock = false;
  try { clock = E.time(broker.known_at) <= at && E.time(broker.as_of) <= at && at - E.time(broker.as_of) <= 36 * 3600000; } catch (_) { /* absent */ }
  if (broker.source !== 'ibkr_flex' || broker.complete !== true || !clock) breaks.push('Missing complete, dated Flex reconciliation snapshot');
  if (broker.scope !== 'short_framework') breaks.push('An attributed short-framework cash/position export is required');
  const local = Object.values(account.positions).filter(p => p.shares > 0), rows = broker.positions || [];
  const ids = new Set([...local.map(p => p.instrument_id), ...rows.map(p => p.instrument_id)]);
  for (const id of ids) {
    const expected = -local.filter(p => p.instrument_id === id).reduce((s, p) => s + p.shares, 0);
    const observed = rows.filter(p => p.instrument_id === id).reduce((s, p) => s + Number(p.quantity), 0);
    if (!id || !Number.isFinite(observed) || Math.abs(expected - observed) > 1e-8) breaks.push('Position quantity mismatch: ' + (id || 'unmapped contract'));
  }
  if (!Number.isFinite(broker.cash) || Math.abs(broker.cash - account.cash) > .01) breaks.push('Cash mismatch or missing attributed cash');
  if (Object.values(account.positions).some(p => p.loan_shares > p.shares + 1e-8)) breaks.push('Broker loan return evidence pending');
  if (!Number.isFinite(broker.other_stress_loss) || !Number.isFinite(broker.other_stressed_margin)) breaks.push('Other account stress/margin exposure missing');
  return { as_of: asOf, reconciled: breaks.length === 0, breaks, matched_instruments: ids.size,
    source_reference: broker.source_sha256 || null, production_authority: 'none' };
}
function readiness(store, projection, reconciliation, records = store.records(), cohortPolicyHash = hash(E.policy())) {
  const status = store.status(), costs = calibration(records);
  const outcomes = records.filter(r => r.kind === 'outcome' && r.policy_sha256 === cohortPolicyHash), issuers = new Set(outcomes.map(r => r.issuer_id).filter(Boolean));
  const completedEvents = new Set(outcomes.map(r => r.event_id));
  const gates = [
    ['source_reviews', status.source_reviews >= 100, status.source_reviews, 100],
    ['independent_reviews', status.independently_reviewed_passes >= 100, status.independently_reviewed_passes, 100],
    ['borrow_evidence', status.borrow_approvals > 0, status.borrow_approvals, 1],
    ['entry_calibration', costs.entry.n > 0, costs.entry.n, 1],
    ['cover_calibration', costs.cover.n > 0, costs.cover.n, 1],
    ['forward_completed_events', completedEvents.size >= 100, completedEvents.size, 100],
    ['forward_independent_issuers', issuers.size >= 60, issuers.size, 60],
    ['observed_cost_stress', outcomes.length > 0 && outcomes.every(r => Number.isFinite(r.stressed_net_dollars))
      && outcomes.reduce((s, r) => s + (r.stressed_net_dollars || 0), 0) > 0, null, null],
    ['reconciliation', reconciliation?.reconciled === true, null, null],
    ['completed_covers_and_loans', projection.metrics.open_positions === 0 && projection.metrics.loan_returns_pending === 0
      && projection.metrics.fractional_positions === 0, projection.metrics.open_positions + projection.metrics.loan_returns_pending, 0],
  ].map(([id, pass, observed, required]) => ({ id, pass, observed, required }));
  return { ...status, cohort_policy_sha256: cohortPolicyHash, calibration: costs, gates, ready_for_evidence_review: gates.every(g => g.pass),
    review_note: '100 events/60 issuers is the existing intraday review milestone, not statistical proof or production approval.',
    production_authority: 'none' };
}
function handoff(envelope, record, now, mode = 'dry_run', approval = null, ready = null) {
  if (!['dry_run', 'paper', 'live'].includes(mode)) throw new TypeError('Unknown order mode');
  const p = E.policy(envelope.policy), s = envelope.snapshot, a = envelope.account;
  if (hash(s) !== record.input_sha256 || hash(a) !== record.account_sha256 || hash(p) !== record.policy_sha256) throw new TypeError('Handoff differs from frozen decision');
  if (Math.abs(E.time(now) - E.time(s.as_of)) > p.maximum_quote_age_seconds * 1000
    || E.time(now) < E.time(s.event.entry_at) || E.time(now) >= E.time(s.event.entry_until)) throw new TypeError('Decision expired or outside entry window');
  const current = E.evaluate({ ...s, as_of: now }, a, p);
  if (!current.eligible || p.evidence_mode !== 'verified' || p.account_basis !== 'observed' || !p.require_thesis) throw new TypeError('Verified underwriting, borrow and observed account inputs required');
  if (!a.account_reference) throw new TypeError('Private account reference required for handoff');
  if (!Number.isInteger(s.security.conid) || s.security.conid <= 0 || s.security.currency !== 'USD') throw new TypeError('Qualified USD stock contract required');
  if (mode === 'live' && (!ready?.ready_for_evidence_review || approval?.live_enabled !== true
    || approval.policy_sha256 !== record.policy_sha256 || !approval.approved_by || !approval.approved_at
    || E.time(approval.approved_at) > E.time(now))) throw new TypeError('Live policy approval and completed evidence review required');
  const base = { conid: s.security.conid, symbol: s.event.ticker, sec_type: 'STK', action: 'SELL',
    quantity: String(Math.min(record.result.sizing.shares, current.sizing.shares)), limit_price: String(current.sizing.price),
    currency: 'USD', tif: 'DAY', outside_rth: false, mode, strategy: 'short_framework',
    framework_decision_id: record.id };
  const digest = hash(base);
  const request = { ...base, framework_request_sha256: digest, rationale: 'SF1:' + record.id + ':' + digest };
  return { schema_version: 'short_framework_handoff.v1', decision_id: record.id, request,
    request_sha256: digest, expires_at: new Date(Math.min(E.time(s.event.entry_until), E.time(s.as_of) + p.maximum_quote_age_seconds * 1000)).toISOString(),
    next: 'Existing authenticated order-intent API, hub preview, exact human approval and broker interlocks',
    transmitted: false };
}
function coverHandoff(envelope, record, now, mode = 'dry_run') {
  const { snapshot: s, account: a } = envelope, p = E.policy(envelope.policy);
  if (!['dry_run', 'paper', 'live'].includes(mode) || record.type !== 'cover'
    || hash(s) !== record.input_sha256 || hash(a) !== record.account_sha256 || hash(p) !== record.policy_sha256) throw new TypeError('Cover handoff differs from reviewed decision');
  const positions = (a.positions || []).filter(x => x.instrument_id === s.security?.instrument_id);
  if (positions.length !== 1 || a.reconciled !== true || !a.account_reference || E.time(a.known_at) > E.time(now)) throw new TypeError('Attributed, reconciled short and account reference required');
  if (!Number.isInteger(s.security.conid) || s.security.conid <= 0 || s.security.currency !== 'USD'
    || s.market.nbbo_verified !== true || Math.abs(E.time(now) - E.time(s.as_of)) > p.maximum_quote_age_seconds * 1000) throw new TypeError('Fresh verified cover quote and qualified USD contract required');
  const current = E.exitIntent(positions[0], { ...s, as_of: now }, p);
  const reserved = (a.reservations || []).filter(r => r.instrument_id === s.security.instrument_id && r.action === 'BUY').reduce((sum, r) => sum + r.shares, 0);
  const qty = Math.floor(Math.max(0, Math.min(current.shares, record.result.shares) - reserved));
  if (current.state !== 'cover_required' || qty <= 0) throw new TypeError('No unreserved executable cover quantity');
  const base = { conid: s.security.conid, symbol: s.event.ticker, sec_type: 'STK', action: 'BUY',
    quantity: String(qty), limit_price: String(current.limit_price), currency: 'USD', tif: 'DAY', outside_rth: false,
    mode, strategy: 'short_framework', framework_decision_id: record.id };
  const digest = hash(base);
  return { schema_version: 'short_framework_handoff.v1', decision_id: record.id,
    request: { ...base, framework_request_sha256: digest, rationale: 'SF1:' + record.id + ':' + digest },
    request_sha256: digest, expires_at: new Date(E.time(s.as_of) + p.maximum_quote_age_seconds * 1000).toISOString(),
    next: 'Human-approved reduce-only cover through the existing hub', transmitted: false };
}
module.exports = { calibration, reconcile, readiness, handoff, coverHandoff };
