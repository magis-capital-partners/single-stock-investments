/* RSI-4: recovered facts, explicit estimates and a complete attrition audit. */
(function (global) {
  'use strict';
  const esc = v => String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const num = (v, d = 0) => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', {maximumFractionDigits: d});
  const pct = v => v == null ? '—' : `${num(v * 100, 2)}%`;
  const money = v => v == null ? '—' : `${v < 0 ? '−' : ''}$${num(Math.abs(v), 0)}`;
  const words = v => String(v ?? '').replaceAll('_', ' ');
  const scenarioLabel = r => r.scenario_id === 'borrow100' ? '2× borrowing · 100% fallback' : r.scenario_id === 'borrow300' ? '6× borrowing · 300% fallback' : r.label;
  const safeLink = value => { try { const u = new URL(value); return u.protocol === 'https:' ? esc(u.href) : '#'; } catch { return '#'; } };
  let data, state, selectedAudit, generation = 0;
  async function verified(spec, prefix) {
    if (!spec || !spec.url.startsWith(prefix) || !/^[a-zA-Z0-9_./]+$/.test(spec.url) || spec.url.includes('..') || !/^[a-f0-9]{64}$/.test(spec.sha256)) throw new Error('Invalid reference');
    const response = await fetch(`${spec.url}?v=${spec.sha256.slice(0, 12)}`);
    if (!response.ok) throw new Error('Unavailable');
    const bytes = await response.arrayBuffer();
    if (!global.crypto?.subtle) throw new Error('Verification unavailable');
    const actual = Array.from(new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
    if (actual !== spec.sha256) throw new Error('Version mismatch');
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  const current = () => data.cases.filter(r => r.policy_id === state.policy && r.variant === state.variant && r.window === state.window);
  function recoverySummary(doc) {
    const comparison = doc.baseline_comparison;
    if (!comparison) return '';
    const recent = comparison.entry_prices.recent, full = comparison.entry_prices.full, f = comparison.financials;
    return `<p><strong>Recovery against the original gaps:</strong> ${num(recent.recovered_entry_records)} of ${num(recent.original_missing_entry_records)} recent missing-entry records recovered (${num(recent.remaining_missing_entry_records)} remain); ${num(full.recovered_entry_records)} of ${num(full.original_missing_entry_records)} across the full history (${num(full.remaining_missing_entry_records)} remain). These are source records, not extra independent trades.</p><p>Of ${num(f.current_reported_scores)} reported scores, ${num(f.current_reported_assumed_identity)} rely on an assumed company-name identity link. The remaining raw-financial gaps include ${num(f.missing_issuer_identity)} events without an issuer identity and ${num(f.identified_issuer_raw_file_missing)} with an issuer but no raw file. The scenario results also change costs and conviction assumptions, so their P&amp;L difference from RSI-3 cannot be attributed to data recovery alone.</p>`;
  }
  function financialSources(packet) {
    const rows = [...(packet.financials?.evidence || []), ...(packet.stale_financial_model?.evidence || [])];
    if (!rows.length) return '';
    const cik = /^cik\/([0-9]+)$/.exec(packet.issuer || '')?.[1];
    return `<article class="sne-detail"><details><summary>Reported financial facts and filing dates</summary><p>Period end describes the financial observation. Filing date establishes when it became public; date-only filings wait until the following Eastern day.</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Financial fact</th><th scope="col">Financial period</th><th scope="col">Filed</th><th scope="col">Reported amount</th><th scope="col">Source</th></tr></thead><tbody>${rows.map(r => {
      const url = r.source_url || (cik && /^[0-9]{10}-[0-9]{2}-[0-9]{6}$/.test(r.accn || '') ? `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${r.accn.replaceAll('-', '')}/` : '');
      return `<tr><th scope="row">${esc(r.tag)}</th><td>${esc(r.start ? r.start+" → "+r.end : r.end)}</td><td>${esc(r.filed)}</td><td>${num(r.val, 0)} ${esc(r.unit)}</td><td>${url ? `<a href="${safeLink(url)}" target="_blank" rel="noopener">${esc(r.accn || 'Filing')}</a>` : 'Source accession unavailable'}</td></tr>`;
    }).join('')}</tbody></table></div></details></article>`;
  }
  function table() {
    return `<div class="rsp-scroll"><table class="insights-table"><caption>Each row starts with $50,000 · conditional historical simulation · $0 data purchases</caption><thead><tr><th scope="col">Assumptions</th><th scope="col">Trades / companies</th><th scope="col">With estimated scores</th><th scope="col">Net P&amp;L</th><th scope="col">Annual return</th><th scope="col">Drawdown</th><th scope="col">Calmar</th><th scope="col">After extra $1,000 loss</th><th scope="col">Audit</th></tr></thead><tbody>${current().map(r => `<tr><th scope="row">${esc(scenarioLabel(r))}</th><td>${num(r.trades)} / ${num(r.issuers)}</td><td>${num(r.estimated_rating_trades)}</td><td>${money(r.net_pnl)}</td><td>${pct(r.cagr)}</td><td>${pct(r.max_drawdown)}</td><td>${num(r.calmar, 3)}</td><td>${money(r.extra_2pct_loss_pnl)}</td><td><button class="sne-name" data-id="${esc(r.id)}" onclick="ShortsCoverageViz.inspect(this.dataset.id)">Explain</button>${!r.performance_valid ? `<small>${num(r.unresolved_admitted_names)} unresolved · ${num(r.margin_stress_breaches)} funding breaches</small>` : ''}</td></tr>`).join('')}</tbody></table></div><p class="sne-note">P&amp;L is suppressed when an admitted portfolio cannot be fully resolved or funded. Calmar is also unavailable with no trades or no drawdown. No missing exit is removed to improve performance. The extra $1,000 column is a separate hypothetical loss deduction, not an observed trade or a recalculated Calmar ratio.</p>`;
  }
  async function open(spec) {
    const mount = document.getElementById('sev-coverage-research');
    if (!mount) return;
    mount.innerHTML = '<p>Loading recovered data and assumption comparisons…</p>';
    try {
      const doc = await verified(spec, 'data/shorts_coverage_research.json');
      if (doc.schema_version !== 'shorts_coverage_research.v1' || doc.authority !== 'none' || doc.data_cost_usd !== 0 || doc.paid_requests !== 0 || doc.frozen_rsi3_unchanged !== true || doc.bindings.frozen_rsi3_summary_sha256 !== spec.base_summary_sha256) throw new Error('Invalid study');
      data = doc; state = {policy: 'p1', variant: 'fundamental', window: 'recent'};
      const c = doc.coverage;
      mount.innerHTML = `<details class="sne-method" open><summary>RSI-4 · expanded backtest and documented assumptions</summary><p><strong>Read this as a set of conditional scenarios.</strong> Recovered facts and estimated inputs are identified for every name. Broker approval and execution evidence remain separate requirements. The original RSI-3 results are retained above.</p><div class="sne-waterfall">${[['Candidate records', c.input_events], ['Unique prepared actions', c.prepared_events], ['Reported financial scores', c.reported_ratings], ['Estimated financial scores', c.estimated_ratings], ['Price symbols supplemented', c.supplemented_price_symbols], ['Actual locate approvals', c.approved_locates]].map(([k, v]) => `<span>${esc(k)}<b>${num(v)}</b></span>`).join('')}</div><p>${num(c.primary_clock_repairs)} primary filing-clock repairs · ${num(c.assumed_identity_events)} assumed company-name identity links · ${num(c.clock_proxy_events)} effective-date clock proxies (enabled only in their labeled scenario). Public borrow history covers ${num(c.public_borrow_symbols)} symbols and supplies ${num(c.announcement_borrow_proxies)} nearby announcement proxies; these remain indications. All ${num(c.framework_routes_per_packet)} framework routes have a recorded assessment for ${num(c.framework_packets)} names; ${num(c.complete_underwriting)} are claimed as completed underwriting.</p><div class="sne-controls"><label>Entry and exit rules<select onchange="ShortsCoverageViz.change('policy',this.value)">${doc.plan.policies.map((p, i) => `<option value="p${i}" ${i === 1 ? 'selected' : ''}>${p.entry === 'post_split_next_open' ? 'After split' : 'After announcement'} · ${p.sessions} sessions · ${p.bracket ? `${pct(p.profit_take)} target / ${pct(p.stop_loss)} stop` : 'time exit'}</option>`).join('')}</select></label><label>Filter<select onchange="ShortsCoverageViz.change('variant',this.value)"><option value="fundamental">Financial score ≥ 60</option><option value="net_edge">Score + positive conservative net edge</option></select></label><label>Period<select onchange="ShortsCoverageViz.change('window',this.value)"><option value="recent">October 2023–October 2026</option><option value="full">May 2018–October 2026</option></select></label></div><div id="scv-table">${table()}</div><div id="scv-audit" aria-live="polite"><p>Choose Explain to see every exclusion and the individual decisions.</p></div><div id="scv-name" aria-live="polite"></div><details><summary>Every modeling assumption, in plain language</summary>${doc.assumptions.map(a => `<p><strong>${esc(words(a.id))}.</strong> ${esc(a.rule)} ${esc(a.consequence)}</p>`).join('')}</details><details><summary>What remains unavailable</summary><ul>${doc.remaining.map(v => `<li>${esc(v)}</li>`).join('')}</ul><p>Strict evidence case: ${num(doc.strict_case.trades)} trades. ${esc(doc.strict_case.reason)}</p></details></details>`;
      const recovery = recoverySummary(doc);
      if (recovery) mount.innerHTML = mount.innerHTML.replace('<div class="sne-controls">', recovery+'<div class="sne-controls">');
    } catch { mount.innerHTML = '<p class="sne-empty">The expanded research could not be verified. Reload to retry.</p>'; }
  }
  function change(key, value) {
    state[key] = value; generation++; selectedAudit = null;
    document.getElementById('scv-table').innerHTML = table();
    document.getElementById('scv-audit').innerHTML = '<p>Choose Explain for a scenario.</p>';
    document.getElementById('scv-name').innerHTML = '';
  }
  async function inspect(id) {
    const row = current().find(r => r.id === id), mount = document.getElementById('scv-audit');
    if (!row || !mount) return;
    const request = ++generation;
    mount.innerHTML = '<p>Loading the complete decision record…</p>';
    document.getElementById('scv-name').innerHTML = '';
    try {
      const audit = await verified(data.audit_files[id], 'data/shorts_coverage_audits/');
      if (request !== generation) return;
      if (audit.id !== id || audit.schema_version !== 'shorts_coverage_audit.v1') throw new Error('Mismatched audit');
      selectedAudit = audit;
      const counts = Object.entries(row.skipped).sort((a, b) => b[1]-a[1]);
      mount.innerHTML = `<article class="sne-detail"><h4>${esc(scenarioLabel(row))} · where the names go</h4><p>${num(row.considered_events)} events reached this period’s decision loop. ${num(row.admitted_positions)} positions were admitted and ${num(row.trades)} were closed. Counts below identify the first failing rule for each event.</p><div class="sne-exclusions">${counts.map(([k, v]) => `<span>${esc(words(k))}<b>${num(v)}</b></span>`).join('')}</div><p>Borrow ${money(row.costs.borrow)} · slippage ${money(row.costs.slippage)} · commissions ${money(row.costs.commission)}. Borrow accrues over settlement calendar days; the simulated exit is never used to predict its own holding duration.</p><label>Find a ticker<input type="search" aria-label="Find a ticker in expanded backtest" oninput="ShortsCoverageViz.search(this.value)"></label><div id="scv-decisions">${decisions('')}</div></article>`;
    } catch { if (request === generation) mount.innerHTML = '<p>The decision record could not be verified.</p>'; }
  }
  function decisions(query) {
    const rows = selectedAudit.journal.filter(r => !query || r.ticker.toUpperCase().includes(query.toUpperCase()));
    return `<p>${num(rows.length)} matching decisions; showing the first 100. Search to find any name.</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Name / entry</th><th scope="col">Decision</th><th scope="col">Shares</th><th scope="col">Net edge</th><th scope="col">Conservative edge</th><th scope="col">Net skew</th><th scope="col">Expected billed days</th></tr></thead><tbody>${rows.slice(0, 100).map(r => `<tr><th scope="row"><button class="sne-name" data-key="${esc(r.key)}" onclick="ShortsCoverageViz.name(this.dataset.key)">${esc(r.ticker)}</button><small>${esc(r.date)}</small></th><td>${esc(words(r.reason))}</td><td>${num(r.shares)}</td><td>${pct(r.net_edge)}</td><td>${pct(r.net_lower_bound)}</td><td>${num(r.net_distribution?.skewness, 2)}</td><td>${num(r.expected_billed_days, 2)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function search(value) { if (selectedAudit) document.getElementById('scv-decisions').innerHTML = decisions(value); }
  async function name(key) {
    const spec = data.names.find(r => r.key === key), mount = document.getElementById('scv-name');
    if (!spec || !mount) return;
    const request = ++generation;
    mount.innerHTML = '<p>Loading dated facts and estimates…</p>';
    try {
      const p = await verified(spec, 'data/shorts_coverage_packets/');
      if (request !== generation) return;
      if (p.key !== key || p.completed_underwriting !== false || p.authority !== 'none') throw new Error('Invalid packet');
      const financing = p.financing;
      mount.innerHTML = `<article class="sne-detail"><h4>${esc(p.ticker)} · facts and estimates</h4><p>Information cutoff ${esc(p.known_at)} · financial period ${esc(p.financial_period || 'unavailable')}.</p><p>Reported financial score: ${num(p.reported_rating, 1)}. Modeled score: ${num(p.modeled_rating, 1)}. Provisional conviction for sizing: ${num(p.modeled_conviction, 1)} / 100. ${pct(p.financial_evidence_fraction)} of numerical mechanisms have observed signals.</p><p>Identity / clock assumptions: ${p.assumptions.length ? p.assumptions.map(v => esc(words(v))).join(' · ') : 'none added'}. Full underwriting remains incomplete.</p><details><summary>Estimated financial signals</summary><ul>${Object.entries(p.imputed_signals).map(([k, v]) => `<li>${esc(words(k))}: ${num(v.value * 100, 1)} / 100 · ${esc(words(v.basis))}${v.prior_other_issuers ? ` · ${num(v.prior_other_issuers)} earlier other issuers` : ''}.</li>`).join('')}</ul></details><p>A reverse split contributes <strong>0% economic dilution</strong>. Possible new financing is modeled separately. Historical cash runway: ${num(financing.historical_runway_months, 1)} months. The financing value change below includes cash proceeds and is not added again to expected short returns.</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Scenario probability</th><th scope="col">New shares / old shares</th><th scope="col">Issue discount</th><th scope="col">Per-share value effect</th></tr></thead><tbody>${financing.scenarios.map(s => `<tr><td>${pct(s.probability)}</td><td>${pct(s.issuance_fraction)}</td><td>${pct(s.discount)}</td><td>${pct(s.per_share_value_change)}</td></tr>`).join('')}</tbody></table></div><details open><summary>All 27 short framework routes</summary><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Framework</th><th scope="col">Assessment</th><th scope="col">Dated source passages</th></tr></thead><tbody>${p.frameworks.map(f => `<tr><th scope="row">${esc(words(f.framework))}</th><td>${esc(words(f.status))}</td><td>${num(f.citations.length)}</td></tr>`).join('')}</tbody></table></div></details></article>`;
      const plan = selectedAudit?.announcement_plans?.[key], forecast = selectedAudit?.forecasts?.[key];
      const actual = selectedAudit?.journal.find(r => r.key === key);
      const financials = p.financials || {};
      const stale = p.stale_financial_model || {};
      if (stale.age_days) mount.innerHTML += `<article class="sne-detail"><h4>Estimate from older company financials</h4><p>The last as-filed period is ${num(stale.age_days)} days old. Estimated cash after elapsed operating burn: ${num(stale.estimated_cash_after_elapsed_burn)} ${esc(stale.currency)}. This assumes no unreported financing and unchanged annual burn; it is not a reported cash balance.</p></article>`;
      mount.innerHTML += `<article class="sne-detail"><h4>Announcement plan versus entry decision</h4><p>Latest comparable exit: ${esc(forecast?.latest_training_exit || 'unavailable')}. Only earlier completed other issuers inform the forecast. ${num(forecast?.donors)} comparable issuers.</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Estimate</th><th scope="col">At announcement</th><th scope="col">At entry</th></tr></thead><tbody>${[['Decision', words(plan?.reason), words(actual?.reason)], ['Shares in entry units', num(plan?.shares), num(actual?.shares)], ['Net edge', pct(plan?.net_edge), pct(actual?.net_edge)], ['Conservative net edge', pct(plan?.net_lower_bound), pct(actual?.net_lower_bound)], ['Expected borrow', pct(plan?.expected_borrow), pct(actual?.expected_borrow)], ['Expected billed calendar days', num(plan?.expected_billed_days, 2), num(actual?.expected_billed_days, 2)]].map(([k, a, b]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</tbody></table></div><p>Announcement annual borrow input: ${pct(plan?.annual_borrow)} · ${esc(words(plan?.borrow_basis))}. Projected share factor: ${num(plan?.projected_share_factor, 5)}. An opening-price estimate is never described as an observed fill.</p><h4>Reported financial amounts</h4><p>Currency: ${esc(financials.currency || 'unknown')}. A missing amount remains unknown.</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Metric</th><th scope="col">Reported / trailing amount</th></tr></thead><tbody>${Object.entries({...financials.balances, ...financials.flows}).map(([k, v]) => `<tr><th scope="row">${esc(words(k))}</th><td>${num(v, 0)}</td></tr>`).join('')}</tbody></table></div><details><summary>Dated filing sources for the framework assessments</summary><ul>${p.frameworks.flatMap(f => f.citations.map(c => `<li>${esc(words(f.framework))} · ${esc(c.known_at)} · <a href="${safeLink(c.source_url)}" target="_blank" rel="noopener">${esc(c.locator)}</a></li>`)).join('')}</ul></details></article>`;
      mount.innerHTML += financialSources(p);
    } catch { if (request === generation) mount.innerHTML = '<p>The name’s evidence packet could not be verified.</p>'; }
  }
  global.ShortsCoverageViz = {open, change, inspect, search, name};
})(window);
