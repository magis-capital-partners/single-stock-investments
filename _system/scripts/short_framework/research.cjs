'use strict';
const E = require('../../../dashboard/short-framework-engine.js');
const { hash } = require('./store.cjs');
const { nyClock, dateAfter, assemble } = require('./adapters.cjs');
const CASES = [
  { id: 'lower_cost', execution: .01, apr: .2, passive_capture: .75 },
  { id: 'base', execution: .0172, apr: .5, passive_capture: .5 },
  { id: 'stress', execution: .0344, apr: 1.5, passive_capture: .25 },
];
const VARIANTS = ['split_only', 'fundamentals_only', 'combined', 'financing', 'deficiency'];
function protocol() {
  const models = [];
  for (const variant of VARIANTS) for (const hold of [1, 5, 10]) for (const cost of CASES)
    for (const evidence of ['conditional', 'verified']) for (const ssr of ['skip', 'passive_sensitivity']) {
      models.push({ id: [variant, hold, cost.id, evidence, ssr].join('__'), variant, hold, cost: cost.id, evidence, ssr });
    }
  return { version: E.VERSION, models, maximum_horizon: 10, initial_equity: 50000,
    selection: 'Same account/capacity policy, last nine entry sessions excluded for every hold. No outcome-based recovery or admission.',
    calendar: 'Reuse frozen XNYS replay session dates; dataset-date fallback stays unverified.',
    costs: '1/1.72/3.44% roundtrip execution sensitivities; 20/50/150% APR; original profit_prices commission, allowance and dated SEC/TAF schedule, including modeled settlement charge dates. Locate, dividends and overhead require separate observed cash flows.',
    borrowing: 'Calendar ACT/360 rounded collateral from modeled settlement; one minimum billed day. Loan return requires modeled settlement or observed evidence.',
    ssr: 'Skip baseline and separately declared passive-above-bid capture sensitivity. Conditional capture is not queue evidence.',
    validation: 'Previously explored history is development. Chronological fresh-account diagnostics are not an untouched holdout. No designated sealed execution files are read.',
    independence: 'Fundamentals-only requires separately imported dated universe membership; never synthesize it from eventual splitters.',
    account: 'Partial covers, fractional shares, unresolved continuity and loan returns persist. Marks are not completed liquidation.',
    policy_note: 'New research comparisons relax the cost gate and thesis review explicitly; operational policy and original studies remain frozen.',
    production_authority: 'none' };
}
function accountInput(a, asOf) {
  const metrics = E.accountMetrics(a, asOf);
  return { known_at: asOf, equity: metrics.equity, positions: Object.values(a.positions), reservations: [],
    other_stress_loss: 0, other_stressed_margin: 0, reconciled: true,
    basis: 'simulated_ledger', source_reference: 'declared_hypothetical_portfolio' };
}
function run(events, prices, model, records = [], options = {}) {
  const cost = CASES.find(c => c.id === model.cost), nav = options.nav || 50000;
  const spec = E.policy({ id: model.id, variant: model.variant, hold_sessions: model.hold,
    entry: ['combined', 'split_only'].includes(model.variant) ? 'post_split' : 'observation',
    evidence_mode: model.evidence, account_basis: 'simulated', require_thesis: false, maximum_cost_fraction: 1, maximum_borrow_apr: 3,
    carry_days: Math.ceil(model.hold * 7 / 5) });
  const days = prices.days.filter(d => (!options.first || d >= options.first) && (!options.last || d <= options.last));
  const dayIndex = new Map(days.map((d, i) => [d, i])), byDay = new Map(), funnel = {}, cashflows = { borrow: 0, commissions: 0 };
  const count = key => { funnel[key] = (funnel[key] || 0) + 1; };
  const selected = e => model.variant === 'fundamentals_only' ? e.family === 'fundamental' && e.independent_universe === true
    : ['combined', 'split_only'].includes(model.variant) ? e.family === 'split' : e.family === model.variant;
  for (const e of events.filter(selected)) {
    count('discoveries');
    const day = prices.entryDay(e, spec.entry);
    if (!day || !dayIndex.has(day)) { count('missing_entry_history'); continue; }
    if (dayIndex.get(day) > days.length - 10) { count('common_maturity_exclusion'); continue; }
    const rows = byDay.get(day) || []; rows.push(e); byDay.set(day, rows);
  }
  let state = E.initialAccount(nav), eventCounter = 0, entered = 0, closed = 0, previousDay = null;
  let peakMargin = 0, peakCollateral = 0;
  const daily = [], returns = [], tradePnl = new Map(), metadata = new Map(), obligations = [];
  const apply = event => {
    // Retain the immutable modeled event log separately; compact the projection's dedup cache.
    state.processed = {};
    state = E.reduce(state, { id: model.id + '/' + (++eventCounter), ...event });
  };
  const settlement = (day, offset = 0) => {
    const i = prices.index.get(day), lag = day < '2024-05-28' ? 2 : 1;
    return prices.days[i + lag + offset] || dateAfter(day);
  };
  function loanDay(day) {
    const at = nyClock(day, '00:00:00');
    for (const pending of obligations.filter(x => !x.done && x.day <= day)) {
      const pos = state.positions[pending.instrument];
      if (pos) apply({ kind: 'loan_return', at, instrument_id: pending.instrument, shares: Math.min(pending.shares, pos.loan_shares - pos.shares) });
      pending.done = true;
    }
    for (const p of Object.values(state.positions)) {
      const meta = metadata.get(p.instrument_id);
      if (!meta || !(p.loan_shares > 0) || day < meta.settlement) continue;
      if (!meta.firstSettlementDayConsumed) { meta.firstSettlementDayConsumed = true; continue; }
      const charge = Math.round(E.collateral(p.loan_shares, p.mark) * meta.apr / 360 * 100) / 100;
      apply({ kind: 'cashflow', at, category: 'borrow', amount: -charge }); cashflows.borrow += charge;
      meta.pnl -= charge;
    }
  }
  function finishReturnedPositions() {
    for (const p of Object.values(state.positions)) if (p.shares <= 0 && p.loan_shares <= 0) {
      const meta = metadata.get(p.instrument_id);
      if (meta) { tradePnl.set(meta.issuer, (tradePnl.get(meta.issuer) || 0) + meta.pnl); returns.push(meta.pnl); }
      metadata.delete(p.instrument_id); delete state.positions[p.instrument_id];
    }
  }
  for (let di = 0; di < days.length; di++) {
    const day = days[di], openAt = nyClock(day), closeAt = nyClock(day, '16:00:00');
    let calendarDay = previousDay ? dateAfter(previousDay) : day;
    while (calendarDay <= day) { loanDay(calendarDay); calendarDay = dateAfter(calendarDay); }
    finishReturnedPositions();
    for (const p of Object.values(state.positions)) {
      const action = prices.actions.get(p.ticker)?.get(day);
      if (action === null) p.continuity_blocked = true;
      if (action && !p.continuity_blocked) {
        apply({ kind: 'split', at: openAt, instrument_id: p.instrument_id, new_per_old: action });
        for (const pending of obligations.filter(x => !x.done && x.instrument === p.instrument_id)) pending.shares *= action;
      }
      const current = state.positions[p.instrument_id];
      if ((E.time(openAt) - E.time(current.mark_at)) > 7 * E.DAY && current.shares > 0) current.continuity_blocked = true;
      const point = current.continuity_blocked ? null : prices.point(p.ticker, day);
      if (point && current.shares > 0) apply({ kind: 'mark', at: openAt, instrument_id: p.instrument_id, price: point.open });
    }
    const openingFunding = E.accountMetrics(state, openAt);
    peakMargin = Math.max(peakMargin, openingFunding.margin); peakCollateral = Math.max(peakCollateral, openingFunding.collateral);
    const candidates = (byDay.get(day) || []).map(e => ({ e, adv: prices.prior(e.ticker, day).adv }))
      .sort((a, b) => b.adv - a.adv || a.e.id.localeCompare(b.e.id));
    for (const { e } of candidates) {
      const snapshot = assemble(e, day, prices, spec, records, { executionFraction: cost.execution, borrowApr: cost.apr });
      if (model.ssr === 'passive_sensitivity' && snapshot.market.ssr === 'restricted') {
        snapshot.market.ssr_execution = 'passive_above_nbb';
        snapshot.market.short_limit = snapshot.market.bid + .01;
      }
      const input = accountInput(state, openAt), decision = E.evaluate(snapshot, input, spec);
      if (!decision.eligible) { decision.blockers.forEach(x => count('blocked_' + x)); continue; }
      const point = prices.point(e.ticker, day), capture = snapshot.market.ssr === 'restricted' ? cost.passive_capture : 1;
      if (snapshot.market.ssr === 'restricted' && (!Number.isFinite(point.high) || point.high < snapshot.market.short_limit)) {
        count('passive_limit_not_reached'); continue;
      }
      // Realized volume limits fills only; it never chooses a decision or its intended size.
      const qty = Math.floor(Math.min(decision.sizing.shares, Math.max(0, point.volume || 0) * .05 * capture));
      if (!qty) { count('no_conditional_fill'); continue; }
      const price = snapshot.market.short_limit || snapshot.market.bid, fee = E.stockFee(qty, price, day, true, spec, settlement(day));
      const instrument = snapshot.event.instrument_id;
      const exitDay = days[Math.min(di + spec.hold_sessions - 1, days.length - 1)];
      apply({ kind: 'entry_fill', at: openAt, instrument_id: instrument, issuer_id: snapshot.event.issuer_id,
        ticker: e.ticker, shares: qty, price, fees: fee, exit_at: nyClock(exitDay, '16:00:00'), policy_id: spec.id });
      const minimumCarry = Math.round(E.collateral(qty, price) * cost.apr / 360 * 100) / 100;
      apply({ kind: 'cashflow', at: openAt, category: 'borrow', amount: -minimumCarry });
      metadata.set(instrument, { apr: cost.apr, settlement: settlement(day), firstSettlementDayConsumed: false,
        pnl: qty * price - fee - minimumCarry, initial_qty: qty, issuer: snapshot.event.issuer_id, entry_day: day });
      entered++; cashflows.commissions += fee; cashflows.borrow += minimumCarry; count('entered');
      const funding = E.accountMetrics(state, openAt);
      peakMargin = Math.max(peakMargin, funding.margin); peakCollateral = Math.max(peakCollateral, funding.collateral);
    }
    for (const p of Object.values(state.positions)) {
      const point = p.continuity_blocked ? null : prices.point(p.ticker, day);
      if (point && p.shares > 0) apply({ kind: 'mark', at: closeAt, instrument_id: p.instrument_id, price: point.close });
      const current = state.positions[p.instrument_id], metrics = E.accountMetrics(state, closeAt);
      const exit = E.exitIntent(current, { as_of: closeAt, market: point ? { known_at: closeAt, quote_at: closeAt,
        ask: point.close * (1 + cost.execution / 2) } : {}, risk_breach: metrics.margin > metrics.equity * .8 || metrics.liability * 2 > nav * .02 }, spec);
      if (exit.reasons.length) current.exit_reason = exit.reasons[0];
      if (exit.state !== 'cover_required') continue;
      const qty = Math.min(exit.shares, Math.floor(Math.max(0, point.volume || 0) * .05));
      if (!qty) continue;
      const fee = E.stockFee(qty, exit.limit_price, day, false, spec);
      apply({ kind: 'cover_fill', at: closeAt, instrument_id: p.instrument_id, shares: qty, price: exit.limit_price, fees: fee });
      obligations.push({ instrument: p.instrument_id, shares: qty, day: settlement(day), done: false });
      metadata.get(p.instrument_id).pnl -= qty * exit.limit_price + fee; cashflows.commissions += fee;
      if (state.positions[p.instrument_id].shares <= 0) { closed++; count('closed'); }
    }
    const m = E.accountMetrics(state, closeAt);
    daily.push({ date: day, ...m });
    peakMargin = Math.max(peakMargin, m.margin); peakCollateral = Math.max(peakCollateral, m.collateral);
    finishReturnedPositions();
    previousDay = day;
  }
  const last = daily.at(-1) || E.accountMetrics(state, nyClock(options.last || '2026-10-12', '16:00:00'));
  let peak = nav, dd = 0, worstDay = 0, previous = nav;
  const changes = daily.map(d => { const delta = d.equity - previous; previous = d.equity; peak = Math.max(peak, d.equity);
    dd = Math.min(dd, d.equity - peak); worstDay = Math.min(worstDay, delta); return delta; });
  const sorted = changes.slice().sort((a, b) => a - b), tail = sorted.slice(0, Math.max(1, Math.ceil(sorted.length * .05)));
  const reliable = entered > 0 && last.open_positions === 0 && last.loan_returns_pending === 0 && last.stale_liability === 0;
  const years = daily.length / 252, cagr = reliable && last.equity > 0 && years > 0 ? (last.equity / nav) ** (1 / years) - 1 : null;
  return { id: model.id, variant: model.variant, hold: model.hold, cost: model.cost, evidence_mode: model.evidence,
    ssr: model.ssr, policy_sha256: hash(spec), entered, closed, issuers: new Set([...tradePnl.keys(), ...[...metadata.values()].map(x => x.issuer)]).size,
    available: model.variant !== 'fundamentals_only' || events.some(selected),
    missing_reason: model.variant === 'fundamentals_only' && !events.some(selected) ? 'Independent historical universe and dated fundamentals have not been imported' : null,
    net_pnl: last.net_pnl, annual_net_dollars: years ? last.net_pnl / years : null, max_drawdown_dollars: dd,
    cagr, calmar: cagr !== null && dd < 0 ? cagr / (-dd / nav) : null,
    worst_day: worstDay, expected_shortfall_95_dollars: tail.length ? tail.reduce((a, b) => a + b, 0) / tail.length : null,
    largest_closed_issuer_profit: Math.max(0, ...tradePnl.values()),
    net_excluding_largest_closed_issuer: last.net_pnl - Math.max(0, ...tradePnl.values()),
    open_liability: last.liability, unresolved_positions: last.open_positions, loan_returns_pending: last.loan_returns_pending,
    stale_liability: last.stale_liability, fractional_positions: last.fractional_positions,
    peak_margin: peakMargin, peak_collateral: peakCollateral,
    cashflows, funnel, return_statistics_available: reliable, observed_fills: 0,
    assumptions: model.evidence === 'conditional' ? 'Price/spread/borrow/flow assumptions; unverified identities and recorded partial-venue capacity' : 'Only admitted evidence-based decisions; absent approvals/quotes remain exclusions',
    ...(options.includeDaily ? { daily } : {}) };
}
module.exports = { CASES, VARIANTS, protocol, run, accountInput };
