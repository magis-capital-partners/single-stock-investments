/* RSI-3.0: frozen theses, prior-only distributions and size-dependent carry. */
(function (global) {
  'use strict';
  const esc = v => String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const num = (v, d = 0) => v == null || !Number.isFinite(v) ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: d});
  const pct = v => v == null ? '—' : `${num(v * 100, 2)}%`;
  const money = v => v == null ? '—' : `${v < 0 ? '−' : ''}$${num(Math.abs(v))}`;
  const label = v => String(v ?? '').replaceAll('_', ' ');
  const variants = {baseline: 'Common forecastable cohort', fundamental: 'Fundamental floor', net_edge: 'Fundamentals + net edge', strict: 'Complete evidence + approved borrow'};
  let data, audit, state, freeData, selectedKey, revision = 0;
  const freeNames = new Map();
  const freeBorrowNames = new Map();
  const cache = new Map();
  const group = () => `${state.entry}_${state.hold}_${state.exit}`;
  const safeUrl = v => { try { const u = new URL(v); return u.protocol === 'https:' ? esc(u.href) : '#'; } catch { return '#'; } };
  function render(doc) {
    if (doc?.schema_version !== 'shorts_net_edge.v3') return '';
    if (!doc.cases) {
      setTimeout(() => loadSummary(doc), 0);
      return '<div id="sev-root" aria-live="polite"><p>Loading RSI-3.0 edge research…</p></div>';
    }
    data = doc; audit = null; freeData = null; selectedKey = null; freeNames.clear(); freeBorrowNames.clear(); cache.clear(); revision++;
    state = {entry: doc.policy.entry, hold: String(doc.policy.sessions), exit: doc.policy.bracket ? 'bracket' : 'time', account: doc.cases.find(r => r.id === doc.primary_case)?.account_id || doc.accounts[0].id, query: '', show: 'all', page: 0};
    setTimeout(loadAudit, 0);
    if (doc.free_evidence_ref) setTimeout(() => loadFreeSummary(doc.free_evidence_ref), 0);
    const c = doc.coverage;
    return `<section class="sne sev3" aria-labelledby="sev-title">
      <div class="sne-heading"><div><span class="sne-eyebrow">RSI-3.0 · fundamentals and net-edge research</span><h2 id="sev-title">Size the edge that survives.</h2><p>Freeze the thesis at announcement. Estimate a distribution of exits and borrowing days. Recheck costs and capacity at entry, then size the short.</p></div><span class="sne-status">Conditional research</span></div>
      <div class="sne-equation"><span>Fundamentals + financing<small>Prior completed issuers; no additive dilution bonus</small></span><b>→</b><span>Gross payoff distribution</span><b>−</b><span>Slippage + fees + carry<small>Evaluated at each proposed position size</small></span><b>=</b><strong>Net edge</strong></div>
      <div class="sne-coverage"><span><b>${num(c.rescored_original_691)} / 691</b>original sample with dated ratings · previously ${num(c.prior_numeric_ratings_691)}</span><span><b>${num(c.numeric_ratings)} / ${num(c.dated_primary_snapshots)}</b>ratings across dated primary records</span><span><b>${num(c.complete_framework_reviews)}</b>complete framework reviews</span><span><b>${num(c.approved_entry_locates)}</b>imported approved entry locates</span></div>
      <p class="sne-evidence">${num(c.catalogue_events)} catalogue records and ${num(c.discovery_accessions)} discovery accessions remain distinct. The catalogue is incomplete. ${num(c.reconciled_financing)} financing packages are reconciled; ${num(c.announcement_borrow_indications)} snapshots have a dated announcement-time borrow indication. Missing evidence excludes names from the complete-evidence case.</p>
      <div id="sev-free-summary" aria-live="polite">${doc.free_evidence_ref ? '<p>Loading free public evidence…</p>' : ''}</div>
      <div class="sne-controls"><label>Entry<select onchange="ShortsEdgeV3Viz.change('entry',this.value)"><option value="announcement_next_open" ${state.entry === 'announcement_next_open' ? 'selected' : ''}>Next session after announcement</option><option value="post_split_next_open" ${state.entry === 'post_split_next_open' ? 'selected' : ''}>Next session after split</option></select></label><label>Maximum hold<select onchange="ShortsEdgeV3Viz.change('hold',this.value)">${[1, 5, 10, 20].map(n => `<option value="${n}" ${String(n) === state.hold ? 'selected' : ''}>${n} session${n > 1 ? 's' : ''}</option>`).join('')}</select></label><label>Exit<select onchange="ShortsEdgeV3Viz.change('exit',this.value)"><option value="bracket" ${state.exit === 'bracket' ? 'selected' : ''}>${pct(doc.policy.profit_take)} profit / ${pct(doc.policy.stop_loss)} stop / time limit</option><option value="time" ${state.exit === 'time' ? 'selected' : ''}>Time limit only</option></select></label><label>Account scenario<select onchange="ShortsEdgeV3Viz.change('account',this.value)">${doc.accounts.map(a => `<option value="${esc(a.id)}" ${a.id === state.account ? 'selected' : ''}>${esc(a.label)}</option>`).join('')}</select></label></div>
      <div id="sev-results">${results()}</div>
      <section class="sne-audit" aria-labelledby="sev-audit-title"><h3 id="sev-audit-title">Decision audit for the selected policy</h3><p class="sne-note">The numerical rating measures deterioration. Full conviction also needs the dated framework, valuation, catalyst and financing review. Rejected sizes show the best evaluated trial; they are not positions.</p><div class="sne-controls"><label>Find a name<input type="search" placeholder="Ticker" aria-label="Find a ticker in RSI-3.0" oninput="ShortsEdgeV3Viz.change('query',this.value)"></label><label>Show<select onchange="ShortsEdgeV3Viz.change('show',this.value)"><option value="all">All dated records</option><option value="forecast">Forecast available</option><option value="included">Included positions</option><option value="excluded">Excluded positions</option>${doc.free_evidence_ref ? '<option value="free">Original 691 · free evidence</option><option value="free_borrow">Prior-day borrow proxy</option>' : ''}</select></label></div><div id="sev-names" aria-live="polite"><p>Loading selected decision audit…</p></div><div id="sev-detail" aria-live="polite"></div></section>
      <details class="sne-method"><summary>Execution evidence, SSR and the prospective test</summary><p>${num(doc.ssr.counts.ssr_requires_limit)} sampled entries were SSR-restricted; ${num(doc.ssr.counts.halt || 0)} were halted. SSR requires a separate limit-order replay. ${esc(doc.ssr.rule)}</p><p>${Object.entries(doc.ssr.limit_replay).map(([k, v]) => `${num(v)} ${esc(label(k))}`).join(' · ')}</p><p>Historical calibration is diagnostic. The prospective policy starts ${esc(doc.policy.prospective_start)}. Forecasts and abstentions are archived before their scheduled entry; later outcomes are separate. Previously explored history is never relabelled an untouched test.</p><p>${num(doc.prospective?.estimates || 0)} archived prospective estimates · ${num(doc.prospective?.abstentions || 0)} explicit abstentions · ${num(doc.prospective?.evaluated_estimates || 0)} evaluated estimates.</p><div id="sev-calibration">${calibration()}</div></details>
      <details class="sne-method"><summary>Method, account assumptions and remaining data work</summary><dl>${Object.entries(doc.definitions).map(([k, v]) => `<dt>${esc(label(k))}</dt><dd>${esc(v)}</dd>`).join('')}</dl><ul>${doc.limits.map(s => `<li>${esc(s)}</li>`).join('')}</ul><p>Required inputs: cited as-filed financial overrides; blinded reviews of all 27 framework routes; dated capitalization scenarios; historical borrow indications and inventory; fresh entry approvals; daily loan charges and recalls; policy-bound execution reports or verified NBBO and eligible trade prints; dividends and fractional split settlements.</p><p>${doc.sources.map(s => `<a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(' · ')}</p></details>
    </section>`;
  }
  async function loadSummary(reference) {
    const mount = document.getElementById('sev-root');
    if (!mount) return;
    try {
      if (reference.summary_url !== 'data/shorts_net_edge_v3.json') throw new Error('Unknown summary');
      const response = await fetch(`${reference.summary_url}?v=${reference.summary_sha256.slice(0, 12)}`);
      if (!response.ok) throw new Error('Summary unavailable');
      const bytes = await response.arrayBuffer();
      if (global.crypto?.subtle) {
        const hash = Array.from(new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
        if (hash !== reference.summary_sha256) throw new Error('Summary version mismatch');
      }
      const summary = JSON.parse(new TextDecoder().decode(bytes));
      if (summary.schema_version !== 'shorts_net_edge.v3' || !summary.cases) throw new Error('Invalid summary');
      mount.innerHTML = render({...summary, prospective: reference.prospective || summary.prospective, free_evidence_ref: reference.free_evidence_ref});
    } catch { mount.innerHTML = '<p class="sne-empty">RSI-3.0 could not be loaded. Reload to retry; no stale model results are shown.</p>'; }
  }
  function results() {
    const rows = data.cases.filter(r => r.group === group() && r.account_id === state.account);
    const a = data.accounts.find(r => r.id === state.account).account;
    const primary = rows.find(r => r.variant === 'net_edge');
    return `<p class="sne-note">${money(a.equity)} starting capital · ${money(a.commission_minimum)} minimum / side, $${num(a.commission_per_share, 3)} / share, ${pct(a.commission_max_fraction)} maximum · ${pct(data.policy.assumed_annual_borrow)} annual borrow sensitivity when historical rates are absent · ${pct(a.name_stress_budget ?? .005)} name / ${pct(a.sleeve_stress_budget ?? .02)} sleeve loss budgets under a +${pct(a.squeeze_increase ?? 2)} squeeze.</p>
      <div class="rsp-scroll"><table class="insights-table sne-compare"><caption>2018-05-01 → 2026-10-13 · conditional daily-bar benchmarks; costs and concurrent positions included</caption><thead><tr><th scope="col">Filter</th><th scope="col">Closed trades</th><th scope="col">Conditional net P&amp;L</th><th scope="col">Drawdown</th><th scope="col">Borrow</th><th scope="col">Data / funding status</th></tr></thead><tbody>${rows.map(r => `<tr class="${r.variant === 'net_edge' ? 'sne-primary' : ''}"><th scope="row">${esc(variants[r.variant])}</th><td>${num(r.trades)}</td><td>${r.trades ? money(r.net_pnl) : '—'}</td><td>${r.trades ? pct(r.max_drawdown) : '—'}</td><td>${money(r.costs.borrow)}</td><td>${!r.funding_valid ? 'Margin stress breach' : r.unresolved_admitted_names ? `${num(r.unresolved_admitted_names)} unresolved admitted names` : r.trades ? 'Conditional scenario' : 'No positions admitted'}</td></tr>`).join('')}</tbody></table></div>
      <p class="sne-note">Missing future paths retain their admitted liabilities and invalidate performance. A funding breach also suppresses P&amp;L. Daily bars do not establish execution, dividend charges or fractional entitlements.</p>
      ${primary?.open_positions ? '<p class="sne-empty"><strong>Admitted positions remain unresolved.</strong> Their liabilities are retained; performance is unavailable.</p>' : primary?.trades ? '' : '<p class="sne-empty"><strong>No positions admitted by this net-edge case.</strong> Idle capital is a filter outcome; it does not establish a profitable strategy.</p>'}
      <details class="sne-method"><summary>Why names were excluded</summary><div class="sne-exclusions">${Object.entries(primary?.skipped || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span>${esc(label(k))}<b>${num(v)}</b></span>`).join('')}</div></details>`;
  }
  function calibration() {
    const c = data.validation[group()];
    return `<p class="sne-note">${num(c.observations)} historical matched forecasts · mean absolute gross-return error ${pct(c.mean_absolute_error)} · ${num(c.prospective_observations)} future-period historical records (not proof of a frozen prospective forecast).</p>`;
  }
  async function loadAudit() {
    const key = group(), request = ++revision;
    audit = null;
    const mount = document.getElementById('sev-names');
    if (!mount) return;
    mount.innerHTML = '<p>Loading selected decision audit…</p>';
    try {
      if (!cache.has(key)) {
        const spec = data.audit_files[key];
        if (!spec || !/^data\/net_edge_audits_v3\/[a-z0-9_]+\.json$/.test(spec.url)) throw new Error('Missing audit');
        const response = await fetch(`${spec.url}?v=${spec.sha256.slice(0, 12)}`);
        if (!response.ok) throw new Error('Audit unavailable');
        const bytes = await response.arrayBuffer();
        if (global.crypto?.subtle) {
          const hash = Array.from(new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
          if (hash !== spec.sha256) throw new Error('Audit version mismatch');
        }
        cache.set(key, JSON.parse(new TextDecoder().decode(bytes)));
      }
      if (request !== revision) return;
      audit = cache.get(key); mount.innerHTML = names();
    } catch { if (request === revision) mount.innerHTML = '<p class="sne-empty">This policyâ€™s audit could not be loaded. Reload to retry; no other policyâ€™s decisions are shown.</p>'; }
  }
  function decision(r) {
    const status = audit.outcomes[r.key];
    return audit.accounts[state.account]?.[r.key] || {shares: 0, reason: ['entry_price_unavailable', 'no_future_entry_in_sample'].includes(status) ? status : r.rating == null ? 'fundamentals_unavailable' : 'insufficient_prior_issuers'};
  }
  async function verifiedJSON(url, hash) {
    if (!/^[a-f0-9]{64}$/.test(hash || '')) throw new Error('Missing evidence hash');
    const response = await fetch(`${url}?v=${hash.slice(0, 12)}`);
    if (!response.ok) throw new Error('Evidence unavailable');
    const bytes = await response.arrayBuffer();
    if (global.crypto?.subtle) {
      const actual = Array.from(new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
      if (actual !== hash) throw new Error('Evidence version mismatch');
    }
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  async function loadFreeSummary(spec) {
    const mount = document.getElementById('sev-free-summary');
    try {
      if (spec.url !== 'data/shorts_free_evidence.json') throw new Error('Unknown evidence source');
      const doc = await verifiedJSON(spec.url, spec.sha256);
      if (doc.schema_version !== 'shorts_free_evidence.v1' || doc.data_cost_usd !== 0 || doc.paid_requests !== 0) throw new Error('Invalid free evidence');
      freeData = doc; doc.names.forEach(r => freeNames.set(r.event_id, r));
      if (state.show === 'free') {
        const list = document.getElementById('sev-names');
        if (list) list.innerHTML = names();
      }
      if (spec.borrow_ref) {
        try {
          if (spec.borrow_ref.url !== 'data/shorts_free_borrow.json') throw new Error('Unknown borrow source');
          const borrow = await verifiedJSON(spec.borrow_ref.url, spec.borrow_ref.sha256);
          if (borrow.schema_version !== 'shorts_free_borrow.v1' || borrow.data_cost_usd !== 0 || borrow.paid_requests !== 0) throw new Error('Invalid borrow evidence');
          borrow.names.forEach(r => freeBorrowNames.set(r.event_id, r));
          doc.borrow_proxy_events = borrow.coverage.collected_prior_day_proxy || 0;
          if (state.show === 'free_borrow') {
            const list = document.getElementById('sev-names');
            if (list) list.innerHTML = names();
          }
        } catch { doc.borrow_proxy_events = null; }
      }
      if (mount) mount.innerHTML = `<details class="sne-method"><summary>Free public evidence · ${num(doc.packets)} event packets · $0 in data charges</summary><p>${num(doc.events_with_documents)} events have retrieved filing text available by announcement. ${num(doc.events_with_financing_passages)} have financing passages to reconcile. ${num(doc.borrow_proxy_events)} have a prior-day public borrow-rate proxy within the free one-year window. Each packet addresses all ${num(doc.framework_routes)} framework routes; unsupported conclusions remain unresolved. This backfill adds evidence without changing frozen strategy returns.</p><p>${num(doc.complete_framework_reviews)} complete underwriting reviews · ${num(doc.reconciled_financing)} reconciled financing packages · ${num(doc.approved_locates)} historical account approvals. Public observations cannot establish past account approval.</p><p>Open a name in the original 691-event cohort to inspect its financial facts, framework routes, financing passages and citations. A 30-event pilot was selected by event identity with outcomes hidden.</p></details>`;
    } catch { if (mount) mount.innerHTML = '<p class="sne-empty">Free evidence could not be verified. Reload to retry.</p>'; }
  }
  function carryHeadroom(plan) {
    const rate = data.policy.assumed_annual_borrow;
    if (!plan || !Number.isFinite(plan.expected_borrow) || !Number.isFinite(plan.net_edge) || !(rate > 0) || data.policy.preborrow_fee_per_share > 0) return '';
    const before = plan.net_edge + plan.expected_borrow;
    if (plan.expected_borrow === 0) return `<p>Borrow headroom: ${before > 0 ? 'no modeled time carry for this frozen plan' : 'no positive edge before borrow'}. Availability and other charges still require evidence.</p>`;
    const unit = plan.expected_borrow / rate;
    const ceiling = Math.max(0, before / unit), lower = Number.isFinite(plan.net_lower_bound) ? Math.max(0, (plan.net_lower_bound + plan.expected_borrow) / unit) : null;
    return `<details class="sne-method"><summary>Borrow cost headroom · ${pct(ceiling)} annual fee ceiling</summary><p>At the frozen announcement ${num(plan.shares || plan.trial_shares)}-share proposal, expected net edge reaches zero at ${pct(ceiling)} annual borrow; the model's lower-bound cost ceiling is ${pct(lower)}. This is a cost threshold, before availability, margin and thesis gates. It is not a historical quote or approval.</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Assumed annual borrow</th><th scope="col">Expected net edge</th></tr></thead><tbody>${[0, .25, .5, 1, 3, 10].map(apr => `<tr><th scope="row">${pct(apr)}</th><td>${pct(before - unit * apr)}</td></tr>`).join('')}</tbody></table></div><p>${num(plan.expected_billed_days, 2)} expected billed calendar days, using the selected exit rule and settlement convention. This sensitivity holds the proposed size fixed.</p></details>`;
  }
  function packetHTML(packet) {
    const financial = packet.financials, currency = esc(financial.currency || 'currency unavailable');
    const routes = packet.frameworks.map(row => `<tr><th scope="row">${esc(label(row.framework))}</th><td>${esc(label(row.status))}</td><td>${esc(row.mechanism)} ${row.evidence.slice(0, 2).map(e => `<a href="${safeUrl(e.source_url)}" target="_blank" rel="noopener">${esc(e.accession)}</a>`).join(' ')}<small>${esc(row.contrary_evidence)} Falsifier: ${esc(row.falsifier)}</small></td></tr>`).join('');
    const passages = packet.financing_terms.slice(0, 16).map(e => `<blockquote>${esc(e.excerpt)}<p><a href="${safeUrl(e.source_url)}" target="_blank" rel="noopener">${esc(e.accession)}</a> · available ${esc(e.known_at)} · ${esc(e.locator)}</p></blockquote>`).join('');
    const citations = packet.documents.map(e => `<p><a href="${safeUrl(e.source_url)}" target="_blank" rel="noopener">${esc(e.form)} · ${esc(e.accessionNumber)}</a> · available ${esc(e.known_at)}</p>`).join('');
    const factRows = (financial.evidence || []).map(f => {
      const cik = /^cik\/(\d+)$/.exec(packet.issuer || '')?.[1];
      const source = f.source_url || (cik && f.accn ? `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${String(f.accn).replaceAll('-', '')}/` : '');
      const metric = String(f.tag || '').split(':').pop().replace(/([a-z])([A-Z])/g, '$1 $2');
      return `<tr><th scope="row">${esc(metric)}</th><td>${num(f.val, 2)} ${esc(f.unit)}</td><td>${esc(f.start || '')} → ${esc(f.end)}</td><td><a href="${safeUrl(source)}" target="_blank" rel="noopener">${esc(f.filed)}</a></td></tr>`;
    }).join('');
    return `<details class="sne-method" open><summary>Public evidence available by this announcement</summary><p>${num(packet.documents.length)} retrieved filings · financial period ${esc(financial.period || 'unavailable')} · numerical screen ${num(packet.screen_rating, 1)} / 100 · historical cash runway ${num(packet.historical_cash_runway_months, 1)} months if reported burn persists. Framework judgments remain incomplete; full conviction is unavailable.</p><p>Reported cash ${num(financial.balances?.cash)} ${currency}; trailing operating cash flow ${num(financial.flows?.cfo)} ${currency}. Claims, proceeds and the share basis still require reconciliation.</p><details><summary>Financial facts and filing dates</summary><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Reported metric</th><th scope="col">Value</th><th scope="col">Period</th><th scope="col">Filing published</th></tr></thead><tbody>${factRows}</tbody></table></div></details><details><summary>All 27 framework routes</summary><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Framework</th><th scope="col">Assessment</th><th scope="col">Evidence and unresolved questions</th></tr></thead><tbody>${routes}</tbody></table></div></details><details><summary>Financing passages (${num(packet.financing_terms.length)})</summary>${passages || '<p>No verified passages retrieved. This does not establish an absence of financing.</p>'}</details><details><summary>Filing citations</summary>${citations || '<p>Filing text is unavailable for this cutoff.</p>'}</details><p class="sne-note">Reconstructed ${esc(packet.reconstructed_at)} from information available by ${esc(packet.announcement_at)}. Later outcomes were excluded from this packet.</p></details>`;
  }
  function borrowProxyHTML(key) {
    const row = freeBorrowNames.get(key), proxy = row?.proxy;
    if (!proxy) return '<p class="sne-note">No eligible free historical borrow proxy for this announcement. Missing data is not a zero borrowing fee.</p>';
    const plan = audit.forecasts[key]?.announcement_plans?.[state.account], rate = data.policy.assumed_annual_borrow;
    const net = plan && Number.isFinite(plan.expected_borrow) && rate > 0 && !(data.policy.preborrow_fee_per_share > 0) ? plan.net_edge + plan.expected_borrow - plan.expected_borrow / rate * proxy.annual_rate : null;
    return `<details class="sne-method" open><summary>Free historical borrow-rate sensitivity</summary><p>${pct(proxy.annual_rate)} annual fee at the ${esc(proxy.date)} daily close · ${num(proxy.available_shares)} publicly indicated shares. Used no earlier than ${esc(proxy.known_at)}.</p><p>${pct(net)} expected net edge at the frozen announcement size if that rate stayed constant over the modeled holding period. This sensitivity does not resize the position or rewrite portfolio returns.</p><p>Historical identifiers remain unverified; the provider's current CUSIP cannot establish past security identity. This is a symbol-linked public proxy, with no account approval. <a href="${safeUrl(proxy.source_url)}" target="_blank" rel="noopener">Public source</a></p></details>`;
  }
  async function loadFreePacket(key) {
    const mount = document.getElementById('sev-free-detail');
    if (!mount) return;
    if (!freeData && data.free_evidence_ref) {
      await loadFreeSummary(data.free_evidence_ref);
      if (selectedKey !== key) return;
    }
    const spec = freeNames.get(key);
    if (!spec) { mount.innerHTML = '<p class="sne-note">This record is outside the original 691-event free backfill, or its packet is unavailable.</p>'; return; }
    try {
      if (!/^data\/free_short_packets\/[a-f0-9]{24}\.json$/.test(spec.path)) throw new Error('Invalid packet path');
      const packet = await verifiedJSON(spec.path, spec.sha256);
      if (selectedKey !== key) return;
      if (packet.schema_version !== 'shorts_free_packet.v1' || packet.event_id !== key || !packet.outcome_blinded) throw new Error('Invalid evidence packet');
      mount.innerHTML = packetHTML(packet) + borrowProxyHTML(key);
    } catch { if (selectedKey === key) mount.innerHTML = '<p class="sne-empty">This evidence packet could not be verified. Reload to retry.</p>'; }
  }
  function names() {
    if (!audit) return '<p>Loading selected decision audit…</p>';
    const rows = data.names.filter(r => r.ticker.toLowerCase().includes(state.query.toLowerCase()) && (state.show === 'all' || state.show === 'forecast' && audit.forecasts[r.key] || state.show === 'included' && decision(r).shares > 0 || state.show === 'excluded' && !decision(r).shares || state.show === 'free' && freeNames.has(r.key) || state.show === 'free_borrow' && freeBorrowNames.get(r.key)?.proxy));
    const pages = Math.max(1, Math.ceil(rows.length / 75)); state.page = Math.min(state.page, pages - 1);
    const start = state.page * 75;
    return `<p class="sne-note">${num(rows.length)} matching records · page ${state.page + 1} / ${pages} · selected net-edge sizing case</p><div class="sev-pages"><button onclick="ShortsEdgeV3Viz.page(-1)" ${state.page === 0 ? 'disabled' : ''}>Previous</button><button onclick="ShortsEdgeV3Viz.page(1)" ${state.page + 1 >= pages ? 'disabled' : ''}>Next</button></div><div class="rsp-scroll sne-name-scroll"><table class="insights-table"><thead><tr><th scope="col">Name / announcement</th><th scope="col">Rating</th><th scope="col">Gross edge</th><th scope="col">Net edge</th><th scope="col">90% lower bound</th><th scope="col">Net skew</th><th scope="col">Expected billed days</th><th scope="col">Shares / reason</th></tr></thead><tbody>${rows.slice(start, start + 75).map(r => { const f = audit.forecasts[r.key], d = decision(r); return `<tr><th scope="row"><button class="sne-name" data-index="${data.names.indexOf(r)}" onclick="ShortsEdgeV3Viz.inspect(Number(this.dataset.index))">${esc(r.ticker)}</button><small>${esc(r.announcement.slice(0, 10))}</small></th><td>${num(r.rating, 1)}</td><td>${pct(f?.gross_edge)}</td><td class="sne-edge">${pct(d.net_edge)}</td><td>${pct(d.net_lower_bound)}</td><td>${num(d.net_distribution?.skewness, 2)}</td><td>${num(d.expected_billed_days, 2)}</td><td>${d.shares ? num(d.shares) : esc(label(d.reason))}</td></tr>`; }).join('')}</tbody></table></div>`;
  }
  function inspect(index) {
    const r = data.names[index], mount = document.getElementById('sev-detail');
    if (!r || !audit || !mount) return;
    selectedKey = r.key;
    const f = audit.forecasts[r.key], d = decision(r), plan = f?.announcement_plans?.[state.account];
    mount.innerHTML = `<article class="sne-detail"><h4>${esc(r.ticker)} · ${esc(r.announcement.slice(0, 10))}</h4><p>${esc(label(d.reason))} · ${num(d.shares)} shares admitted${d.trial_shares ? ` · best rejected trial: ${num(d.trial_shares)} shares / ${money(d.trial_notional)}` : ''}</p><div class="sne-waterfall">${[['Gross edge', f?.gross_edge], ['Slippage', d.expected_slippage], ['Commissions', d.expected_commission], ['Expected borrow', d.expected_borrow], ['Net edge', d.net_edge], ['90% lower bound', d.net_lower_bound]].map(([k, v]) => `<span>${k}<b>${pct(v)}</b></span>`).join('')}</div><p>${num(f?.donors)} prior other issuers · ${num(f?.expected_hold_sessions, 2)} expected overnight session intervals · ${num(d.expected_billed_days, 2)} expected billed calendar days · ${num(d.net_distribution?.gain_loss_ratio, 2)} net expected gain / loss ratio. Financing and framework evidence affect matching only when present; they are never added to historical price returns.</p><p>Frozen announcement plan: ${pct(plan?.net_edge)} net edge, ${pct(plan?.net_lower_bound)} lower bound; ${esc(label(f?.announcement_borrow_basis || "unavailable"))}. Entry costs above are evaluated with the selected account and current capacity. Full reviewed conviction: ${num(r.conviction_rating, 1)} / 100.</p><p>Financials: ${esc(label(r.fundamental_status))}. Frameworks: ${num(r.framework_reviewed)} / 27 reviewed. Financing: ${esc(label(r.financing_status))}. Announcement borrow: ${r.borrow_indication ? 'dated indication' : 'missing'}. Price path: ${esc(label(audit.outcomes[r.key]))}.</p><p>Thesis cutoff ${esc(r.announcement)}; latest training exit ${esc(f?.latest_training_exit || 'unavailable')}. <a href="${safeUrl(r.source_url)}" target="_blank" rel="noopener">Announcement source</a></p></article>`;
    mount.innerHTML += carryHeadroom(plan) + '<div id="sev-free-detail" aria-live="polite"></div>';
    if (data.free_evidence_ref) loadFreePacket(r.key);
  }
  function change(key, value) {
    state[key] = value; state.page = 0;
    if (['query', 'show'].includes(key)) { document.getElementById('sev-names').innerHTML = names(); return; }
    document.getElementById('sev-results').innerHTML = results();
    selectedKey = null;
    document.getElementById('sev-calibration').innerHTML = calibration();
    document.getElementById('sev-detail').innerHTML = '';
    loadAudit();
  }
  function page(delta) { state.page = Math.max(0, state.page + delta); document.getElementById('sev-names').innerHTML = names(); }
  global.ShortsEdgeV3Viz = {render, change, inspect, page};
})(window);
