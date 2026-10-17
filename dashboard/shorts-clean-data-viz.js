/* Fixed original rules, measured data repairs and cited remaining work. */
(function (global) {
  'use strict';
  const esc = v => String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const num = v => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', {maximumFractionDigits: 1});
  const words = v => String(v ?? '').replaceAll('_', ' ');
  const safe = v => { try { const u = new URL(v); return u.protocol === 'https:' ? esc(u.href) : '#'; } catch { return '#'; } };
  const labels = {original: 'Original frozen data', scope_and_duplicates: 'Scope checks and duplicate removal', validated_prices: 'Add validated price observations', reported_financials: 'Add reported financial facts', verified_actions_and_identities: 'Add verified actions and historical identities', volume_proxy_sensitivity: 'Public-volume proxy · separate sensitivity'};
  let data, period = 'recent', parts = new Map(), records = [], page = 0, term = '', generation = 0;
  async function verified(spec, prefix) {
    if (!spec || !spec.url.startsWith(prefix) || !/^[A-Za-z0-9_./-]+$/.test(spec.url) || spec.url.includes('..') || !/^[a-f0-9]{64}$/.test(spec.sha256)) throw new Error('Invalid source');
    const response = await fetch(`${spec.url}?v=${spec.sha256.slice(0, 12)}`);
    if (!response.ok) throw new Error('Unavailable');
    const bytes = await response.arrayBuffer();
    const hash = Array.from(new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
    if (hash !== spec.sha256) throw new Error('Changed source');
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  function table() {
    let previous = null;
    return `<div class="rsp-scroll"><table class="insights-table"><caption>Same financial filter, sizing, costs and exits for every row</caption><thead><tr><th scope="col">Data used</th><th scope="col">Scored records at entry</th><th scope="col">Closed / admitted trades</th><th scope="col">Companies</th><th scope="col">Change in closed trades</th></tr></thead><tbody>${data.stages.map(stage => {
      const r = stage.windows.find(x => x.period === period), delta = previous == null ? null : r.closed_trades - previous;
      previous = r.closed_trades;
      return `<tr><th scope="row">${esc(labels[stage.id] || words(stage.id))}${!stage.clean_data ? '<small>Historical volume units remain an assumption</small>' : ''}</th><td>${num(r.scored_records)}</td><td>${num(r.closed_trades)} / ${num(r.admitted_trades)}${r.unresolved ? `<small>${num(r.unresolved)} unresolved</small>` : ''}</td><td>${num(r.issuers)}</td><td>${delta == null ? 'Baseline' : `${delta > 0 ? '+' : ''}${num(delta)}`}</td></tr>`;
    }).join('')}</tbody></table></div><p>Closed trades can differ from admitted positions when an exit remains unresolved. New data can also remove trades. Changes in which positions overlap or qualify as historical comparables are included in each replay.</p>`;
  }
  async function loadPart(i) {
    if (!parts.has(i)) parts.set(i, verified(data.queue.parts[i], 'data/shorts_clean_data_queue/'));
    return parts.get(i);
  }
  function queueTable() {
    const filtered = records.filter(r => `${r.ticker} ${r.company || ''} ${r.cik || ''} ${r.first_exclusion} ${r.blockers.join(' ')}`.toLowerCase().includes(term.toLowerCase()));
    const shown = filtered.slice(page * 20, page * 20 + 20);
    return `<div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Company / event</th><th scope="col">Reported score</th><th scope="col">Identity evidence</th><th scope="col">First exclusion</th><th scope="col">Details</th></tr></thead><tbody>${shown.map(r => `<tr><th scope="row">${esc(r.ticker)}<small>${esc(r.company || '')} · ${esc(r.ex_date)}</small></th><td>${num(r.reported_score)}</td><td>${esc(words(r.identity_status))}</td><td>${esc(words(r.first_exclusion))}</td><td><button class="sne-name" data-key="${esc(r.key)}" onclick="ShortsCleanDataViz.inspect(this.dataset.key)">Sources and remaining work</button></td></tr>`).join('')}</tbody></table></div><p>${num(filtered.length)} matching records loaded · ${num(data.queue.records)} in the complete queue. Acquisition priority uses data gaps, recent events and repeated issuers; it never uses the later return.</p><button class="rsp-action" onclick="ShortsCleanDataViz.move(-1)" ${page === 0 ? 'disabled' : ''}>Previous</button> <button class="rsp-action" onclick="ShortsCleanDataViz.move(1)" ${shown.length < 20 && parts.size >= data.queue.parts.length ? 'disabled' : ''}>Next</button>`;
  }
  async function open(spec) {
    const mount = document.getElementById('sev-clean-data-research');
    if (!mount) return;
    mount.innerHTML = '<p>Loading the original-policy data comparison…</p>';
    try {
      const doc = await verified(spec, 'data/shorts_clean_data_research.json');
      if (doc.schema_version !== 'shorts_clean_data_research.v1' || doc.source_collection_complete !== true || doc.authority !== 'none' || doc.data_cost_usd !== 0 || doc.production_policy_changed !== false || doc.bindings.research_summary_sha256 !== spec.base_summary_sha256 || doc.stages.some(s => s.policy_sha256 !== doc.policy_sha256)) throw new Error('Invalid replay');
      if (doc.stages[0].windows.find(r => r.period === 'recent')?.closed_trades !== 46 || doc.stages[0].windows.find(r => r.period === 'full')?.closed_trades !== 83) throw new Error('Baseline changed');
      data = doc; parts = new Map(); records = []; page = 0; term = ''; period = 'recent';
      const c = doc.coverage;
      const pending = num(doc.acquisition?.uncached_sources_pending);
      mount.innerHTML = `<details class="sne-method" open><summary>Clean-data recovery · original rules</summary><p>Reproduces the original 46 recent trades and 83 full-history trades before changing inputs. The rules stay fixed: next session after the split, at most 10 sessions, 20% target / 20% stop, reported financial score ≥60, $100 minimum and 0.1% of prior share volume. Missing financial signals are never filled with estimates in this comparison.</p><div class="sne-waterfall">${[['Confirmed dated identity records', c.confirmed_identity_records], ['Primary scheduled-action records', c.primary_action_records], ['Reported XBRL facts extracted', c.reported_facts], ['Reported financial scores', c.reported_scores], ['Actual locate approvals', c.actual_locate_approvals], ['Strict recent trades', c.strict_recent_trades]].map(([k, v]) => `<span>${esc(k)}<b>${num(v)}</b></span>`).join('')}</div><label>Comparison period<select onchange="ShortsCleanDataViz.change(this.value)"><option value="recent">October 2023–October 2026</option><option value="full">May 2018–October 2026</option></select></label><div id="scd-stages">${table()}</div><button class="rsp-action" onclick="ShortsCleanDataViz.changes()">Show trades added and removed</button><div id="scd-changes" aria-live="polite"></div><details><summary>Remaining data work, in acquisition order</summary><label>Find a ticker, company, CIK or gap<input type="search" aria-label="Search clean data work queue" oninput="ShortsCleanDataViz.search(this.value)"></label><div id="scd-queue" aria-live="polite"><p>Loading the highest-priority records…</p></div><div id="scd-record" aria-live="polite"></div></details><details><summary>Evidence still required for the strict case</summary><p>${num(c.full_underwriting)} completed full-framework reviews · ${num(c.reconciled_financing)} reconciled financing assessments · ${num(c.actual_locate_approvals)} actual approvals · ${num(c.observed_fills)} observed fills. Filing passages remain research leads until their claims and calculations are reconciled. Historical broker exports can be imported through the existing evidence interface; public rate indications cannot become approvals.</p><ul>${doc.limits.map(v => `<li>${esc(v)}</li>`).join('')}</ul></details><p>Data purchases: $0. Source requests are public SEC GETs and cached public charts.</p></details>`;
      mount.innerHTML += `<p>${pending} source requests remain uncached after this bounded collection pass. Counts above describe the evidence accepted so far.</p>`;
      const first = await loadPart(0); records = first.records;
      document.getElementById('scd-queue').innerHTML = queueTable();
    } catch { mount.innerHTML = '<p>The clean-data comparison could not be verified. Reload to retry.</p>'; }
  }
  function change(value) { period = value; document.getElementById('scd-stages').innerHTML = table(); document.getElementById('scd-changes').innerHTML = ''; }
  async function changes() {
    const mount = document.getElementById('scd-changes'); mount.innerHTML = '<p>Loading trade changes…</p>';
    try {
      const doc = await verified(data.changes, 'data/shorts_clean_data_changes.json');
      mount.innerHTML = `<div class="rsp-scroll"><table class="insights-table"><thead><tr><th>Data step</th><th>Ticker / entry</th><th>Change</th><th>Previous exclusion</th><th>Current result</th></tr></thead><tbody>${doc.records.filter(r => r.period === period).map(r => `<tr><td>${esc(labels[r.to_stage])}</td><td>${esc(r.ticker)} · ${esc(r.entry_day)}</td><td>${esc(r.change)}</td><td>${esc(words(r.before_reason))}</td><td>${esc(words(r.after_reason))}</td></tr>`).join('')}</tbody></table></div>`;
    } catch { mount.innerHTML = '<p>The trade-change record could not be verified.</p>'; }
  }
  async function search(value) {
    term = value; page = 0; const request = ++generation;
    const mount = document.getElementById('scd-queue'); mount.innerHTML = '<p>Searching all event records…</p>';
    try {
      const all = [];
      for (let i = 0; i < data.queue.parts.length; i += 3) all.push(...await Promise.all(data.queue.parts.slice(i, i + 3).map((_, j) => loadPart(i + j))));
      if (request !== generation) return;
      records = all.flatMap(p => p.records); mount.innerHTML = queueTable();
    } catch { if (request === generation) mount.innerHTML = '<p>The complete work queue could not be verified.</p>'; }
  }
  async function move(delta) {
    const next = Math.max(0, page + delta);
    if (!term && next * 20 >= records.length && parts.size < data.queue.parts.length) {
      try { const part = await loadPart(parts.size); records.push(...part.records); } catch { return; }
    }
    page = next; document.getElementById('scd-queue').innerHTML = queueTable();
  }
  function inspect(key) {
    const r = records.find(x => x.key === key); if (!r) return;
    const mount = document.getElementById('scd-record');
    mount.innerHTML = `<article class="sne-detail"><h4>${esc(r.ticker)} · ${esc(r.ex_date)}</h4><p>${esc(r.company)}. ${esc(words(r.identity_status))}. Reported financial score: ${num(r.reported_score)}.</p><p>Remaining gates: ${r.blockers.length ? r.blockers.map(x => esc(words(x))).join(' · ') : 'Passed the financial simulation entry gates'}. Volume-capacity estimate: $${num(r.volume_capacity_usd)} versus $${num(r.minimum_order_usd)} minimum.</p>${r.identity_source ? `<p>Historical identity: <a href="${safe(r.identity_source.source_url)}" target="_blank" rel="noopener">${esc(r.identity_source.locator)}</a> · ${esc(r.identity_source.known_at)}</p>` : ''}<h4>Dated filing sources</h4><ul>${r.filing_sources.map(s => `<li><a href="${safe(s.source_url)}" target="_blank" rel="noopener">${esc(s.accessionNumber)}</a> · ${esc(s.known_at)}</li>`).join('')}</ul><h4>Reported financial evidence used</h4><div class="rsp-scroll"><table class="insights-table"><thead><tr><th>Fact</th><th>Period</th><th>Amount</th><th>Public date / source</th></tr></thead><tbody>${(r.financial_evidence || []).map(f => `<tr><td>${esc(f.tag)}</td><td>${esc(f.start ? f.start+' → '+f.end : f.end)}</td><td>${num(f.val)} ${esc(f.unit)}</td><td><a href="${safe(f.source_url)}" target="_blank" rel="noopener">${esc(f.known_at || f.filed)}</a></td></tr>`).join('')}</tbody></table></div><h4>Financing passages to reconcile</h4>${r.financing_leads.length ? r.financing_leads.map(l => `<p>${esc(l.excerpt)} <a href="${safe(l.source_url)}" target="_blank" rel="noopener">${esc(l.locator)}</a></p>`).join('') : '<p>No dated passage has been extracted for this record. Absence of a passage does not establish absence of a financing claim.</p>'}<p>Full underwriting and financing reconciliation remain ${esc(r.full_underwriting)} and ${esc(r.financing_reconciliation)}.</p></article>`;
  }
  global.ShortsCleanDataViz = {open, change, changes, search, move, inspect};
})(window);
