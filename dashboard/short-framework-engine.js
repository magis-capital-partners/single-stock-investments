/* Shared deterministic short decisions and accounting. No I/O or broker access. */
(function (root) {
  'use strict';
  const VERSION = 'short_framework.v1', DAY = 86400000;
  const LENSES = ['earnings_quality', 'cash_and_financing', 'operating_impairment',
    'disclosures_and_control', 'valuation_and_payoff', 'catalyst_and_path'];
  const FORBIDDEN = new Set(['out180', 'out360', 'financing_60d_after', 'next_reverse_split_2y',
    'stopped_trading', 'regain_date', 'delist_date', 'realized_return', 'future_return', 'outcomes']);
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const clone = x => JSON.parse(JSON.stringify(x));
  const money = x => Math.round((x + Number.EPSILON) * 100) / 100;
  function time(value) {
    if (typeof value !== 'string' || !/(Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) throw new TypeError('An aware ISO timestamp is required');
    return Date.parse(value);
  }
  function canonical(value) {
    if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
    if (finite(value)) return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
    throw new TypeError('Only finite JSON values are allowed');
  }
  function noFutureLabels(value) {
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (FORBIDDEN.has(key)) throw new TypeError('Outcome field in decision inputs: ' + key);
      noFutureLabels(child);
    }
  }
  function known(row, at) { try { return !!row && time(row.known_at) <= at; } catch (_) { return false; } }
  function fresh(value, at, seconds) {
    try { const age = at - time(value); return age >= 0 && age <= seconds * 1000; } catch (_) { return false; }
  }
  function policy(overrides = {}) {
    const p = {
      version: VERSION, id: 'combined_post_split_v1', variant: 'combined', entry: 'post_split',
      evidence_mode: 'verified', account_basis: 'observed', score_floor: 60, minimum_signals: 3, maximum_fact_age_days: 200,
      minimum_price: 1, maximum_quote_age_seconds: 60, maximum_borrow_age_seconds: 14400,
      maximum_borrow_apr: .5, maximum_cost_fraction: .01, maximum_names: 3,
      notional_fraction: .025, participation: .001, name_loss_fraction: .005,
      sleeve_loss_fraction: .02, squeeze_increase: 2, carry_stress_multiple: 3,
      margin_buffer: .2, house_margin_fraction: 1, minimum_notional: 100,
      hold_sessions: 1, carry_days: 7, stop_fraction: null, target_fraction: null,
      commission_per_share: .005, minimum_commission: 1, require_thesis: true,
      fee_schedule: 'profit_prices_20261022',
      minimum_gross_downside: 0, minimum_net_downside: 0, announcement_age_days: 7,
      preflight_seconds: 3600, production_authority: 'none', ...clone(overrides),
    };
    if (p.version !== VERSION || !p.id || !['split_only', 'fundamentals_only', 'combined', 'financing', 'deficiency'].includes(p.variant)
      || !['post_split', 'announcement', 'observation'].includes(p.entry)
      || !['verified', 'conditional'].includes(p.evidence_mode)
      || !['observed', 'simulated'].includes(p.account_basis)
      || p.fee_schedule !== 'profit_prices_20261022') throw new TypeError('Unknown policy route');
    for (const k of ['maximum_quote_age_seconds', 'maximum_borrow_age_seconds', 'maximum_fact_age_days',
      'minimum_signals', 'maximum_names', 'hold_sessions', 'carry_days']) {
      if (!Number.isInteger(p[k]) || p[k] < 1) throw new TypeError('Invalid policy integer: ' + k);
    }
    for (const k of ['score_floor', 'minimum_price', 'maximum_borrow_apr', 'maximum_cost_fraction',
      'notional_fraction', 'participation', 'name_loss_fraction', 'sleeve_loss_fraction', 'squeeze_increase',
      'carry_stress_multiple', 'margin_buffer', 'minimum_notional', 'commission_per_share',
      'minimum_commission', 'house_margin_fraction', 'minimum_gross_downside', 'minimum_net_downside',
      'announcement_age_days', 'preflight_seconds']) {
      if (!finite(p[k]) || p[k] < 0) throw new TypeError('Invalid policy amount: ' + k);
    }
    for (const k of ['notional_fraction', 'participation', 'name_loss_fraction', 'sleeve_loss_fraction', 'margin_buffer']) {
      if (p[k] >= 1) throw new TypeError('Policy fraction must be below one: ' + k);
    }
    for (const k of ['stop_fraction', 'target_fraction']) if (p[k] !== null && (!finite(p[k]) || p[k] <= 0)) throw new TypeError('Invalid bracket');
    if (p.production_authority !== 'none') throw new TypeError('A research policy cannot grant production authority');
    return Object.freeze(p);
  }
  function maintenance(qty, price, house = 1) {
    return Math.abs(qty) * Math.max(house * price, price < 5 ? Math.max(2.5, price) : Math.max(5, .3 * price));
  }
  const collateral = (qty, price) => Math.abs(qty) * Math.ceil(1.02 * price);
  // Frozen, unchanged schedule from reverse_splits/profit_prices.py. Live
  // broker charge records remain authoritative; later schedules need a version.
  function stockFee(qty, price, day, sell, spec = policy(), chargeDay = day) {
    if (!(qty > 0)) return 0;
    const notional = qty * price, commission = Math.min(Math.max(spec.commission_per_share * qty, spec.minimum_commission), .01 * notional);
    const allowance = qty * .000003;
    if (!sell) return Math.ceil((commission + allowance) * 100 - 1e-10) / 100;
    const rates = [['2020-02-18', 22.1], ['2021-02-25', 5.1], ['2022-05-14', 22.9],
      ['2023-02-27', 8], ['2024-05-22', 27.8], ['2025-05-14', 0], ['2026-04-04', 20.6]];
    const sec = rates.slice().reverse().find(([date]) => date <= chargeDay)?.[1] ?? 22.1;
    let taf, cap;
    if (day >= '2026-10-01' && day <= '2026-12-31') { taf = 0; cap = 0; }
    else if (day >= '2026-01-01') { taf = .000195; cap = 9.79; }
    else if (day >= '2024-01-01') { taf = .000166; cap = 8.30; }
    else if (day >= '2023-01-01') { taf = .000145; cap = 7.27; }
    else if (day >= '2022-01-01') { taf = .000130; cap = 6.49; }
    else { taf = .000119; cap = 5.95; }
    return Math.ceil((commission + allowance + notional * sec / 1e6 + Math.min(qty * taf, cap)) * 100 - 1e-10) / 100;
  }
  function reviewThesis(thesis, at, price, p) {
    if (!known(thesis, at)) return { pass: false, reason: 'Dated thesis missing' };
    const reviews = thesis.lenses || [], supported = new Set();
    const complete = LENSES.every(id => {
      const rows = reviews.filter(r => r.lens_id === id);
      if (rows.length !== 1) return false;
      const r = rows[0];
      const valid = known(r, at) && ['supported', 'unresolved'].includes(r.status)
        && /^https:\/\//.test(r.source_url || '')
        && ['locator', 'mechanism', 'contrary_evidence', 'falsifier'].every(k => typeof r[k] === 'string' && r[k].trim());
      if (valid && r.status === 'supported') supported.add(id);
      return valid;
    });
    const mechanisms = ['earnings_quality', 'cash_and_financing', 'operating_impairment', 'disclosures_and_control'].filter(k => supported.has(k));
    let catalyst = false;
    try { catalyst = time(thesis.catalyst_at) >= at && time(thesis.catalyst_at) - at <= p.carry_days * DAY; } catch (_) { /* unknown */ }
    const values = thesis.scenarios || {};
    const valuation = ['bear', 'base', 'bull'].every(k => finite(values[k]) && values[k] >= 0)
      && values.bear <= values.base && values.base <= values.bull && thesis.claims_and_financing_reconciled === true;
    return { pass: complete && mechanisms.length >= 2
      && mechanisms.some(k => ['cash_and_financing', 'operating_impairment'].includes(k))
      && supported.has('valuation_and_payoff') && supported.has('catalyst_and_path') && catalyst && valuation
      && finite(thesis.target_price) && thesis.target_price > 0 && thesis.target_price < price,
    reason: 'Six dated lenses, reconciled bear/base/bull equity values, catalyst and falsifier',
    mechanisms, documentation_coverage: Math.min(1, reviews.length / 6) };
  }
  function evaluate(snapshot, account, spec = policy()) {
    canonical(snapshot); canonical(account); noFutureLabels(snapshot); noFutureLabels(account);
    const p = policy(spec), s = clone(snapshot), a = clone(account);
    const at = time(s.as_of), e = s.event || {}, security = s.security || {}, f = s.fundamentals || {};
    const m = s.market || {}, b = s.borrow || {}, costs = s.costs || {};
    const strict = p.evidence_mode === 'verified', gates = [];
    const gate = (id, pass, detail) => gates.push({ id, pass: !!pass, detail });
    gate('event_clock', known(e, at) && !!e.id && !!e.issuer_id && /^https:\/\//.test(e.source_url || '') && !!e.locator,
      'Source event must be public by the decision cutoff');
    gate('event_verification', !strict || e.verified === true, 'Source-reconciled event required for verified results');
    gate('observation_clock', s.observation_mode !== 'prospective' || known({ known_at: e.first_seen_at }, at),
      'Prospective inputs need the actual first-observed timestamp');
    const route = p.variant === 'fundamentals_only' ? e.family === 'fundamental' && e.independent_universe === true
      : ['split_only', 'combined'].includes(p.variant) ? e.family === 'split' : e.family === p.variant;
    gate('opportunity', route, 'Declared event family and independent-universe contract');
    let schedule = false;
    try {
      const entry = time(e.entry_at), end = time(e.entry_until);
      schedule = entry < end && at >= entry - p.preflight_seconds * 1000 && at < end;
      if (p.entry === 'post_split') schedule = schedule && time(e.effective_at) < entry && time(e.effective_at) <= at;
      if (p.entry === 'announcement') schedule = schedule && at - time(e.known_at) <= p.announcement_age_days * DAY
        && (!e.effective_at || at < time(e.effective_at)) && e.discovery_basis !== 'completed_action_catalogue';
    } catch (_) { /* no actionable schedule */ }
    gate('entry_window', schedule, 'Declared entry window; announcement cohorts cannot select eventual completions');
    let identity = known(security, at) && security.instrument_id === e.instrument_id && security.issuer_id === e.issuer_id;
    try { identity = identity && time(security.valid_from) <= at && (!security.valid_until || at < time(security.valid_until)); } catch (_) { identity = false; }
    gate('identity', identity && (!strict || security.identity_verified === true && security.units_verified === true), 'Dated instrument, issuer and nominal share units');
    const factAge = typeof f.period_end === 'string' ? (at - Date.parse(f.period_end + 'T00:00:00Z')) / DAY : Infinity;
    const needFundamental = ['combined', 'fundamentals_only'].includes(p.variant);
    gate('fundamentals', !needFundamental || known(f, at) && finite(f.score) && f.score >= p.score_floor
      && (f.numeric_signals >= p.minimum_signals || !strict && f.numeric_signals_lower_bound >= p.minimum_signals)
      && factAge >= 0 && factAge <= p.maximum_fact_age_days
      && f.as_filed === true && (!strict || f.operating_company === true),
    'As-filed score, coverage count, applicable profile and fresh period');
    gate('terms', p.variant !== 'financing' || known(s.terms, at) && s.terms.reconciled === true
      && ['priced', 'closed', 'exercisable'].includes(s.terms.economic_state)
      && finite(s.terms.shares_before) && s.terms.shares_before > 0 && finite(s.terms.saleable_shares),
    'Registration capacity cannot establish issued or saleable supply');
    const quote = known(m, at) && fresh(m.quote_at, at, p.maximum_quote_age_seconds)
      && finite(m.bid) && finite(m.ask) && m.bid >= p.minimum_price && m.ask >= m.bid;
    gate('quote', quote && (!strict || m.nbbo_verified === true), 'Fresh nominal quote; verified NBBO for evidence-based results');
    gate('liquidity', finite(m.adv_shares) && m.adv_shares > 0 && m.adv_sessions === 20
      && known({ known_at: m.adv_known_at }, at) && time(m.adv_known_at) < at && (!strict || m.volume_verified === true),
    'Prior twenty exchange sessions; verified consolidated volume for evidence-based capacity');
    const ssr = known({ known_at: m.ssr_known_at }, at) && (m.ssr === 'clear'
      || m.ssr === 'restricted' && m.ssr_execution === 'passive_above_nbb' && finite(m.short_limit) && m.short_limit > m.bid);
    gate('ssr', ssr, 'Unknown status blocks entry; restricted entries need an above-bid passive limit');
    const borrow = known(b, at) && fresh(b.quoted_at, at, p.maximum_borrow_age_seconds)
      && finite(b.annual_rate) && b.annual_rate >= 0 && b.annual_rate <= p.maximum_borrow_apr
      && finite(b.shares) && b.shares > 0 && (!b.expires_at || time(b.expires_at) > at);
    gate('borrow', borrow && (strict ? b.status === 'approval' && !!b.reference && !!b.broker : ['approval', 'assumption'].includes(b.status)),
      'Approved broker quantity/rate/reference; assumptions are conditional research only');
    const positions = (a.positions || []).filter(x => x.shares > 0 || x.loan_shares > 0);
    const pending = (a.reservations || []).filter(x => x.shares > 0), named = [...positions, ...pending];
    gate('portfolio', known(a, at) && finite(a.equity) && a.equity > 0
      && finite(a.other_stress_loss) && a.other_stress_loss >= 0 && finite(a.other_stressed_margin) && a.other_stressed_margin >= 0
      && named.every(x => !!x.issuer_id && finite(x.shares) && x.shares >= 0 && finite(x.mark) && x.mark > 0)
      && (!strict || a.reconciled === true && !!a.source_reference
        && a.basis === (p.account_basis === 'simulated' ? 'simulated_ledger' : 'observed_account')),
      'Reconciled account and other strategies\' stress/margin; hypothetical portfolios remain explicitly simulated');
    gate('issuer_overlap', !named.some(x => x.issuer_id === e.issuer_id)
      && new Set(named.map(x => x.issuer_id)).size < p.maximum_names, 'One position per issuer; pending orders reserve capacity');
    const px = quote ? (m.short_limit || m.bid) : 0, equity = finite(a.equity) ? a.equity : 0;
    const execution = finite(costs.roundtrip_fraction) && costs.roundtrip_fraction >= 0 ? costs.roundtrip_fraction : null;
    const apr = finite(b.annual_rate) ? b.annual_rate : 0;
    const existingLoss = named.reduce((sum, x) => sum + (finite(x.stress_loss) ? x.stress_loss : (x.shares || 0) * (x.mark || 0) * p.squeeze_increase), 0);
    const existingMargin = named.reduce((sum, x) => sum + maintenance(x.shares || 0, (x.mark || 0) * (1 + p.squeeze_increase), p.house_margin_fraction), 0);
    const stressCarry = px ? collateral(1, px * (1 + p.squeeze_increase)) * apr * p.carry_stress_multiple * p.carry_days / 360 : 0;
    const unitLoss = px * p.squeeze_increase + stressCarry + (execution || 0) * px + 2 * p.commission_per_share;
    const riskAvailable = Math.max(0, Math.min(equity * p.name_loss_fraction, equity * p.sleeve_loss_fraction - existingLoss));
    const marginAvailable = Math.max(0, equity * (1 - p.margin_buffer) - existingMargin - (a.other_stressed_margin || 0) - existingLoss - (a.other_stress_loss || 0));
    const limits = { notional: px ? equity * p.notional_fraction / px : 0,
      liquidity: finite(m.adv_shares) ? m.adv_shares * p.participation : 0, borrow: finite(b.shares) ? b.shares : 0,
      squeeze: unitLoss ? Math.max(0, riskAvailable - 2 * p.minimum_commission) / unitLoss : 0,
      margin: px ? Math.max(0, marginAvailable - 2 * p.minimum_commission) / (unitLoss + maintenance(1, px * (1 + p.squeeze_increase), p.house_margin_fraction)) : 0 };
    const quantity = Math.max(0, Math.floor(Math.min(...Object.values(limits)))), notional = quantity * px;
    const feeDay = s.as_of.slice(0, 10);
    const commissions = quantity ? stockFee(quantity, px, feeDay, true, p, costs.charge_day || feeDay) + stockFee(quantity, px, feeDay, false, p) : 0;
    const carry = quantity ? collateral(quantity, px) * apr * p.carry_days / 360 : 0;
    const locate = finite(costs.locate_per_share) && costs.locate_per_share >= 0 ? costs.locate_per_share * quantity : 0;
    const totalCost = notional && execution !== null ? execution + (commissions + carry + locate) / notional : null;
    gate('cost', known(costs, at) && totalCost !== null && totalCost <= p.maximum_cost_fraction
      && (!strict || costs.calibration_verified === true && costs.entry_observations > 0 && costs.cover_observations > 0),
    'Entry/cover costs, commissions, locate and carry; both sides need calibration');
    const thesis = reviewThesis(s.thesis, at, px, p);
    gate('thesis', !p.require_thesis || thesis.pass, thesis.reason);
    const gross = px && finite(s.thesis?.target_price) ? 1 - s.thesis.target_price / px : null;
    const net = gross !== null && totalCost !== null ? gross - totalCost : null;
    gate('payoff', !p.require_thesis || gross !== null && gross >= p.minimum_gross_downside && net !== null && net >= p.minimum_net_downside, 'Catalyst-reachable downside after costs');
    gate('size', quantity > 0 && notional >= p.minimum_notional, 'Whole shares within name, sleeve, borrow, volume and margin limits');
    const eligible = gates.every(g => g.pass);
    return { schema_version: VERSION, policy_id: p.id, event_id: e.id || null, as_of: s.as_of,
      state: eligible ? 'eligible' : 'blocked', eligible, evidence_mode: p.evidence_mode,
      actionable_at: e.entry_at || null, expires_at: e.entry_until || null, gates,
      blockers: gates.filter(g => !g.pass).map(g => g.id),
      sizing: { shares: eligible ? quantity : 0, proposed_shares: quantity, price: px, notional: money(notional),
        limits, limiting_constraint: Object.keys(limits).sort((x, y) => limits[x] - limits[y])[0],
        total_cost_fraction: totalCost, gross_downside: gross, net_downside: net,
        expected_net_dollars: net === null ? null : money(notional * net), stress_loss: money(quantity * unitLoss + commissions) },
      thesis, production_authority: 'none' };
  }
  function exitIntent(position, snapshot, spec) {
    const p = policy(spec), at = time(snapshot.as_of), m = snapshot.market || {}, reasons = [];
    if (!(position.shares > 0)) return { state: position.loan_shares > 0 ? 'loan_return_pending' : 'closed', shares: 0, reasons };
    if (known(snapshot.recall, at)) reasons.push('recall');
    if (known(snapshot.falsifier, at) && snapshot.falsifier.triggered === true) reasons.push('falsifier');
    if (known(snapshot.catalyst, at) && snapshot.catalyst.resolved === true) reasons.push('catalyst_resolved');
    if (position.exit_at && at >= time(position.exit_at)) reasons.push('time');
    if (p.entry === 'announcement' && position.effective_at && at >= time(position.effective_at) - 60000) reasons.push('before_split');
    const price = finite(m.ask) ? m.ask : position.mark;
    if (p.stop_fraction !== null && price >= position.entry_price * (1 + p.stop_fraction)) reasons.push('stop');
    if (p.target_fraction !== null && price <= position.entry_price * (1 - p.target_fraction)) reasons.push('target');
    if (snapshot.risk_breach === true) reasons.push('shared_risk');
    if (snapshot.operator_cover === true) reasons.push('operator_cover');
    if (!reasons.length && !position.exit_reason) return { state: 'open', shares: 0, reasons };
    if (position.exit_reason) reasons.push(position.exit_reason);
    const usable = known(m, at) && fresh(m.quote_at, at, p.maximum_quote_age_seconds)
      && finite(m.ask) && m.ask > 0 && (!snapshot.security || snapshot.security.instrument_id === position.instrument_id);
    return { state: usable && position.shares >= 1 ? 'cover_required' : 'cover_blocked',
      shares: usable ? Math.floor(position.shares) : 0, fractional_obligation: position.shares % 1,
      limit_price: usable ? m.ask : null, reasons: [...new Set(reasons)] };
  }
  function initialAccount(equity) {
    if (!finite(equity) || equity <= 0) throw new TypeError('Positive initial equity required');
    return { schema_version: VERSION, initial_equity: equity, cash: equity, external_flows: 0,
      positions: {}, orders: {}, processed: {}, fees: 0, last_at: null };
  }
  function reduce(account, event) {
    const a = clone(account); canonical(event);
    if (!event.id) throw new TypeError('Ledger event needs immutable identity');
    const content = canonical(event);
    if (a.processed[event.id]) {
      if (a.processed[event.id] !== content) throw new TypeError('Conflicting duplicate ledger event');
      return a;
    }
    const at = time(event.at);
    if (a.last_at && at < time(a.last_at)) throw new TypeError('Ledger projection must be chronological');
    const p = event.instrument_id ? a.positions[event.instrument_id] : null;
    const amount = x => { if (!finite(x) || x < 0) throw new TypeError('Invalid ledger amount'); return x; };
    if (event.kind === 'entry_fill') {
      const qty = amount(event.shares), price = amount(event.price), fees = amount(event.fees || 0);
      if (!qty || !price || !event.issuer_id || !event.instrument_id) throw new TypeError('Incomplete entry fill');
      const pos = p || { instrument_id: event.instrument_id, issuer_id: event.issuer_id, ticker: event.ticker || '',
        shares: 0, loan_shares: 0, entry_price: 0, mark: price, mark_at: event.at,
        entry_at: event.at, exit_at: event.exit_at || null, policy_id: event.policy_id || null };
      if (pos.issuer_id !== event.issuer_id) throw new TypeError('Instrument issuer changed without continuity evidence');
      pos.entry_price = (pos.entry_price * pos.shares + qty * price) / (pos.shares + qty);
      pos.shares += qty; pos.loan_shares += qty; pos.mark = price; pos.mark_at = event.at;
      a.positions[event.instrument_id] = pos; a.cash = money(a.cash + qty * price - fees); a.fees = money(a.fees + fees);
    } else if (event.kind === 'cover_fill') {
      const qty = amount(event.shares), price = amount(event.price), fees = amount(event.fees || 0);
      if (!p || qty <= 0 || price <= 0 || qty > p.shares + 1e-9) throw new TypeError('Cover exceeds open short');
      p.shares = Math.max(0, p.shares - qty); p.mark = price; p.mark_at = event.at;
      a.cash = money(a.cash - qty * price - fees); a.fees = money(a.fees + fees);
    } else if (event.kind === 'fractional_settlement') {
      const qty = amount(event.shares);
      if (!p || qty <= 0 || qty >= 1 || qty > p.shares + 1e-9 || !finite(event.amount)
        || event.settlement_verified !== true) throw new TypeError('Verified fractional settlement required');
      p.shares = Math.max(0, p.shares - qty); p.loan_shares = Math.max(0, p.loan_shares - qty);
      // An explicit settlement may differ from binary share arithmetic by dust.
      if (p.shares < 1e-9) p.shares = 0;
      if (p.loan_shares < 1e-9) p.loan_shares = 0;
      a.cash = money(a.cash + event.amount);
    } else if (event.kind === 'loan_return') {
      if (!p || amount(event.shares) > p.loan_shares - p.shares + 1e-9) throw new TypeError('Unproven loan return');
      p.loan_shares = Math.max(0, p.loan_shares - event.shares);
    } else if (event.kind === 'split') {
      if (!p || !finite(event.new_per_old) || event.new_per_old <= 0) throw new TypeError('Verified action ratio required');
      p.shares *= event.new_per_old; p.loan_shares *= event.new_per_old;
      p.mark /= event.new_per_old; p.entry_price /= event.new_per_old;
    } else if (event.kind === 'mark') {
      if (!p || !amount(event.price)) throw new TypeError('No position or positive mark');
      p.mark = event.price; p.mark_at = event.at;
    } else if (event.kind === 'recall') {
      if (!p) throw new TypeError('Recall for unknown position'); p.exit_reason = 'recall';
    } else if (event.kind === 'cashflow') {
      if (!finite(event.amount) || !['borrow', 'locate', 'dividend', 'cash_in_lieu', 'credit', 'overhead', 'other'].includes(event.category)) throw new TypeError('Invalid sourced cash flow');
      a.cash = money(a.cash + event.amount);
    } else if (event.kind === 'external_flow') {
      if (!finite(event.amount)) throw new TypeError('Invalid external flow');
      a.cash = money(a.cash + event.amount); a.external_flows = money(a.external_flows + event.amount);
    } else if (event.kind === 'order') {
      const prior = a.orders[event.order_id];
      const transitions = { requested: ['submitted', 'rejected', 'cancelled'], submitted: ['acknowledged', 'uncertain', 'rejected'],
        uncertain: ['acknowledged', 'rejected', 'cancelled'], acknowledged: ['partial', 'filled', 'cancelled', 'rejected'], partial: ['partial', 'filled', 'cancelled'] };
      if (!event.order_id || (!prior && event.state !== 'requested') || prior && !(transitions[prior.state] || []).includes(event.state)) throw new TypeError('Illegal order transition');
      a.orders[event.order_id] = { ...prior, ...event };
    } else throw new TypeError('Unsupported ledger event');
    a.processed[event.id] = content; a.last_at = event.at; return a;
  }
  function accountMetrics(account, asOf) {
    const at = time(asOf), positions = Object.values(account.positions), open = positions.filter(p => p.shares > 0);
    const liability = open.reduce((sum, p) => sum + p.shares * p.mark, 0), equity = account.cash - liability;
    return { as_of: asOf, equity: money(equity), net_pnl: money(equity - account.initial_equity - account.external_flows),
      liability: money(liability), open_positions: open.length,
      loan_returns_pending: positions.filter(p => p.loan_shares > p.shares + 1e-9).length,
      stale_liability: money(open.filter(p => at - time(p.mark_at) > DAY).reduce((sum, p) => sum + p.shares * p.mark, 0)),
      fractional_positions: open.filter(p => Math.abs(p.shares - Math.round(p.shares)) > 1e-9).length,
      margin: money(open.reduce((sum, p) => sum + maintenance(p.shares, p.mark), 0)),
      collateral: money(open.reduce((sum, p) => sum + collateral(p.shares, p.mark), 0)), fees: account.fees };
  }
  const api = { VERSION, DAY, LENSES, canonical, time, policy, evaluate, exitIntent, initialAccount, reduce,
    accountMetrics, maintenance, collateral, stockFee, reviewThesis, noFutureLabels };
  root.ShortFrameworkEngine = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window === 'undefined' ? globalThis : window);
