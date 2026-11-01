(function (root) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const money = value => Number.isFinite(value) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value) : 'Unavailable';
  const number = value => Number.isFinite(value) ? value.toLocaleString('en-US') : 'Unknown';
  async function digest(value) {
    if (!root.crypto?.subtle) throw new Error('A secure browser context is required to verify this file.');
    const bytes = typeof value === 'string' ? new TextEncoder().encode(value) : value;
    return Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256', bytes))).map(v => v.toString(16).padStart(2, '0')).join('');
  }
  function render() { return '<section class="sf" data-short-framework><p role="status">Loading shared-framework evidence.</p></section>'; }
  function summary(doc, state) {
    const selected = doc.models.filter(m => m.hold === state.hold && m.cost === state.cost && m.evidence_mode === state.evidence && m.ssr === state.ssr);
    const label = { split_only: 'Reverse splits', fundamentals_only: 'Fundamentals alone', combined: 'Splits + fundamentals', financing: 'Financing', deficiency: 'Listing deficiency' };
    const select = (key, title, values) => `<label>${title}<select data-sf-control="${key}">${values.map(([v, text]) => `<option value="${v}"${String(state[key]) === String(v) ? ' selected' : ''}>${text}</option>`).join('')}</select></label>`;
    return `<div class="sf-intro"><div><h3>One decision framework, from replay to review</h3><p>Compare each source of opportunity under the same account rules. Then track the evidence needed to use it.</p></div><span class="spp-status">${doc.evidence.ready_for_evidence_review ? 'Evidence review due' : 'Evidence incomplete'}</span></div>
      <p class="spp-note">Market history through <strong>${escape(doc.market_through || 'unavailable')}</strong>. Built ${escape(doc.built_at.slice(0, 10))}. ${number(doc.comparison_count)} of ${number(doc.declared_comparison_count)} declared comparisons available. ${state.evidence === 'conditional' ? 'These results assume borrowing and execution. They do not establish achievable trading profits.' : 'Verified mode requires dated security identity, NBBO, consolidated volume, approved borrow and calibrated costs. Missing evidence blocks entry.'}</p>
      <dl class="spp-stats sf-key-metrics">${[['Cached review packets', `${number(doc.source_review.cached_packets)} / ${number(doc.source_review.selected)}`], ['Completed primary reviews', number(doc.source_review.completed_primary_reviews)], ['Independent review passes', number(doc.source_review.independently_reviewed_passes)], ['Approved borrows', number(doc.evidence.borrow_approvals)], ['Observed entry / cover fills', `${number(doc.evidence.observed_entry_fills)} / ${number(doc.evidence.observed_cover_fills)}`], ['Frozen estimates / abstentions', `${number(doc.evidence.frozen_estimates)} / ${number(doc.evidence.frozen_abstentions)}`]].map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join('')}</dl>
      <div class="spp-controls">${select('evidence', 'Evidence', [['verified', 'Verified inputs'], ['conditional', 'Historical assumptions']])}${select('hold', 'Maximum hold', [[1, '1 session'], [5, '5 sessions'], [10, '10 sessions']])}${select('cost', 'Cost case', [['lower_cost', 'Lower cost'], ['base', 'Base'], ['stress', 'Stress']])}${select('ssr', 'Restricted short sales', [['skip', 'Skip baseline'], ['passive_sensitivity', 'Passive-fill sensitivity']])}</div>
      <div class="spp-scroll"><table><caption>Matched strategy comparison - $50,000 research account</caption><thead><tr><th>Opportunity</th><th>Entries / issuers</th><th>Marked net P&amp;L</th><th>Max drawdown</th><th>Peak marked margin</th><th>Unfinished</th></tr></thead><tbody>${selected.map(m => `<tr><th>${escape(label[m.variant] || m.variant)}${m.missing_reason ? `<small>${escape(m.missing_reason)}</small>` : ''}</th><td>${m.available ? `${number(m.entered)} / ${number(m.issuers)}` : 'Unavailable'}</td><td>${m.available ? money(m.net_pnl) : 'Unavailable'}</td><td>${m.available ? money(Math.abs(m.max_drawdown_dollars)) : 'Unavailable'}</td><td>${m.available ? money(m.peak_margin) : 'Unavailable'}</td><td>${m.available ? number(m.unresolved_positions + m.loan_returns_pending) : 'Unknown'}</td></tr>`).join('') || '<tr><td colspan="6">This comparison has not been built.</td></tr>'}</tbody></table></div>
      <p>All variants remain visible. A missing independent universe is shown as unavailable. Open shares, stale marks, fractional obligations and pending loan returns remain in accounting.</p>
      <details class="spp-details"><summary>Why trades were blocked</summary><div class="spp-scroll"><table><thead><tr><th>Opportunity</th><th>Blockers and exclusions</th></tr></thead><tbody>${selected.map(m => `<tr><th>${escape(label[m.variant])}</th><td class="sf-wrap">${escape(Object.entries(m.funnel).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${number(v)}`).join(' · ') || m.missing_reason || 'No observations')}</td></tr>`).join('')}</tbody></table></div></details>
      <h3>Evidence needed before a deployment review</h3><div class="sf-gates">${doc.evidence.gates.map(g => `<article><span class="sf-dot${g.pass ? ' sf-dot-pass' : ''}" aria-label="${g.pass ? 'Complete' : 'Pending'}"></span><div><strong>${escape(g.id.replaceAll('_', ' '))}</strong><small>${g.observed === null ? g.pass ? 'Satisfied' : 'Evidence required' : `${number(g.observed)}${g.required === null ? '' : ' / ' + number(g.required)}`}</small></div></article>`).join('')}</div><p>${escape(doc.evidence.review_note)} Live transmission also requires the existing hub preview, human approval and account controls.</p>
      <details class="spp-details"><summary>Protocol, coverage and all registered settings</summary><ul>${doc.limitations.map(t => `<li>${escape(t)}</li>`).join('')}</ul><p>Calendar: ${escape(doc.calendar_basis)}. Dataset: <code>${escape(doc.dataset_version)}</code>.</p><button type="button" data-sf-export>Download comparison results</button><pre>${escape(JSON.stringify(doc.protocol, null, 2))}</pre></details>`;
  }
  function workspace() {
    return `<section class="sf-workspace"><h3>Decision workspace</h3><p>Load a dated decision to inspect its gates, or a reviewed order handoff to request a preview. The file stays in this tab until you request an order preview.</p><label>Decision or reviewed order<input type="file" accept=".json,application/json" data-sf-file></label><div data-sf-decision aria-live="polite"></div><div data-sf-order-result aria-live="polite"></div></section>`;
  }
  async function inspect(value, now = new Date().toISOString()) {
    if (value.schema_version === 'short_framework_handoff.v1') {
      const request = value.request || {}, { rationale, framework_request_sha256, ...base } = request;
      if (await digest(root.ShortFrameworkEngine.canonical(base)) !== value.request_sha256
        || framework_request_sha256 !== value.request_sha256 || rationale !== `SF1:${value.decision_id}:${value.request_sha256}`) throw new Error('The reviewed order binding does not match its contents.');
      if (!value.expires_at || Date.parse(value.expires_at) <= Date.parse(now)) throw new Error('This reviewed order has expired. Refresh its evidence before requesting a preview.');
      return { kind: 'handoff', value };
    }
    const envelope = value.snapshot ? value : value.decision;
    if (!envelope?.snapshot || !envelope.account || !envelope.policy) throw new Error('This file needs a dated snapshot, account state and policy.');
    if (envelope.input_sha256 && await digest(root.ShortFrameworkEngine.canonical(envelope.snapshot)) !== envelope.input_sha256) throw new Error('Frozen decision input hash mismatch.');
    const result = root.ShortFrameworkEngine.evaluate(envelope.snapshot, envelope.account, envelope.policy);
    if (envelope.result && root.ShortFrameworkEngine.canonical(result) !== root.ShortFrameworkEngine.canonical(envelope.result)) throw new Error('The frozen result differs from this framework version.');
    return { kind: 'decision', result, ticker: envelope.snapshot.event.ticker };
  }
  function decisionView(loaded) {
    if (loaded.kind === 'handoff') {
      const r = loaded.value.request;
      return `<article class="spp-event"><h4>${escape(r.action)} ${escape(r.quantity)} ${escape(r.symbol)} at ${money(Number(r.limit_price))}</h4><p>Mode: ${escape(r.mode)}. Expires ${escape(loaded.value.expires_at)}. The hub will recheck this private decision before preview and submission.</p><button type="button" data-sf-preview>Request ${escape(r.mode)} order preview</button></article>`;
    }
    return `<article class="spp-event"><h4>${escape(loaded.ticker)} — ${escape(loaded.result.state)}</h4><p>Eligible size: ${number(loaded.result.sizing.shares)} shares. Expected total cost: ${loaded.result.sizing.total_cost_fraction === null ? 'Unknown' : (100 * loaded.result.sizing.total_cost_fraction).toFixed(2) + '%'}.</p><ul>${loaded.result.gates.map(g => `<li><strong>${g.pass ? 'Pass' : 'Blocked'}: ${escape(g.id.replaceAll('_', ' '))}</strong> — ${escape(g.detail)}</li>`).join('')}</ul></article>`;
  }
  async function attach(container) {
    const host = container.querySelector('[data-short-framework]');
    if (!host || host.dataset.mounted) return; host.dataset.mounted = 'true';
    try {
      const manifestResponse = await fetch('data/short_framework/manifest.json', { cache: 'no-store' });
      if (!manifestResponse.ok) throw new Error('The framework comparison snapshot is unavailable.');
      const manifest = await manifestResponse.json();
      const response = await fetch('data/short_framework/summary.json', { cache: 'no-store' });
      if (!response.ok) throw new Error('The framework comparison snapshot is unavailable.');
      const raw = await response.text();
      if (await digest(raw) !== manifest.summary_sha256) throw new Error('Framework files are from different builds. Reload to retry.');
      const doc = JSON.parse(raw);
      if (doc.schema_version !== 'short_framework.v1' || doc.dataset_version !== manifest.dataset_version) throw new Error('Unsupported framework dataset.');
      if (!host.isConnected) return;
      const state = { evidence: 'verified', hold: 1, cost: 'base', ssr: 'skip' }; let loaded = null;
      host.innerHTML = '<div data-sf-summary></div>' + workspace();
      const paint = () => { host.querySelector('[data-sf-summary]').innerHTML = summary(doc, state); }; paint();
      host.addEventListener('change', async event => {
        if (event.target.matches('[data-sf-control]')) {
          state[event.target.dataset.sfControl] = event.target.dataset.sfControl === 'hold' ? Number(event.target.value) : event.target.value;
          const key = event.target.dataset.sfControl; paint(); host.querySelector(`[data-sf-control="${key}"]`)?.focus();
        }
        if (event.target.matches('[data-sf-file]')) {
          const target = host.querySelector('[data-sf-decision]'); loaded = null;
          try { if (!event.target.files[0]) return; loaded = await inspect(JSON.parse(await event.target.files[0].text())); target.innerHTML = decisionView(loaded); }
          catch (error) { target.textContent = error.message; }
        }
      });
      host.addEventListener('click', async event => {
        if (event.target.closest('[data-sf-export]')) {
          const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' }));
          const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'short-framework-comparisons.json'; anchor.click(); URL.revokeObjectURL(url);
        }
        const button = event.target.closest('[data-sf-preview]');
        if (!button || loaded?.kind !== 'handoff') return;
        const target = host.querySelector('[data-sf-order-result]'); button.disabled = true;
        try {
          await inspect(loaded.value);
          const reply = await fetch('/api/v2/portfolio/order-intents', { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(loaded.value.request) });
          const body = await reply.json(); if (!reply.ok) throw new Error(body.error || 'Order preview request failed.');
          target.innerHTML = `<p>Request ${escape(body.request_id_created)} is ${escape(body.state)}. <a href="#/portfolio/all/orders">Open the order desk to review it.</a></p>`;
        } catch (error) { target.textContent = error.message; button.disabled = false; }
      });
    } catch (error) { if (host.isConnected) host.innerHTML = `<p role="alert">${escape(error.message)}</p>`; }
  }
  const api = { render, attach, summary, inspect, decisionView, escape, digest };
  root.ShortFrameworkViz = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window === 'undefined' ? globalThis : window);
