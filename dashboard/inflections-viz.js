(function (global) {
  'use strict';
  const KEY = 'ssi_inflections_v1';
  const DEFAULT = Object.freeze({ view: 'companies', scope: 'holdings', query: '', direction: 'all', persistence: 'all', kind: 'all', source: 'all', includeQuiet: false, includeSuppressed: false, includeSteady: false, page: 0, more: false });
  const DIRECTIONS = { improving: 'Improving', weakening: 'Weakening', mixed: 'Mixed', no_shift: 'No clear shift', insufficient: 'Insufficient data' };
  const KINDS = { business: 'Reported business changes', history: 'Company history', operating: 'Operating observations', peers: 'Peer comparisons', expectations: 'Earnings vs consensus', context: 'Demand and news context', balance_sheet: 'Balance sheet' };
  const SOURCES = { sec_fundamentals: 'SEC filings', equity_model: 'Equity model', issuer_operating: 'Issuer operating report', peer_relative: 'Sleeve-peer comparison', earnings_revision: 'Reported earnings vs consensus', respiratory_panel: 'Respiratory demand panel', news_flow: 'News flow' };
  const REASONS = { source_stale: 'Source marked outdated', volatile_base: 'Volatile or sign-changing base', duplicate_component: 'Included in a composite', not_selected: 'Outside the curated selection', period_unavailable: 'Reporting period unavailable', revenue_proxy: 'Operating-income substitute for revenue', aged: 'Reporting period is outdated', future: 'Reporting period is in the future' };
  const PAGE_SIZE = 25;
  const cache = new Map();
  let remembered = null;
  const rememberedOpen = new Set();
  let returnToExplorer = null;
  let returnScroll = null;
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const canonical = value => String(value || '').trim().toUpperCase();
  const numeric = value => value !== null && value !== '' && Number.isFinite(Number(value));

  function periodTime(value) {
    const text = String(value || '');
    let match = /^(\d{4})-Q([1-4])$/.exec(text);
    if (match) return Date.UTC(Number(match[1]), Number(match[2]) * 3, 0);
    match = /^(\d{4})-(\d{2})$/.exec(text);
    if (match && Number(match[2]) >= 1 && Number(match[2]) <= 12) return Date.UTC(Number(match[1]), Number(match[2]), 0);
    match = /^(\d{4})-(\d{2})-(\d{2})(?:T.*)?$/.exec(text);
    if (!match) return null;
    const time = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    const date = new Date(time);
    return date.getUTCFullYear() === Number(match[1]) && date.getUTCMonth() === Number(match[2]) - 1 && date.getUTCDate() === Number(match[3]) ? time : null;
  }

  function dateLabel(value) {
    if (/^\d{4}-Q[1-4]$/.test(String(value))) return value + ' (calendar quarter)';
    if (/^\d{4}-\d{2}$/.test(String(value))) return new Date(periodTime(value)).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
    const time = periodTime(value);
    return time === null ? 'Period unavailable' : new Date(time).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  }

  function signalReasons(signal, now = Date.now()) {
    const reasons = [...(signal.reasons || [])];
    const time = periodTime(signal.period);
    if (time === null && !reasons.includes('period_unavailable')) reasons.push('period_unavailable');
    if (time !== null) {
      const today = Math.floor(now / 86400000) * 86400000;
      if (time > today) reasons.push('future');
      else if ((today - time) / 86400000 > (signal.max_age_days || 200)) reasons.push('aged');
    }
    return [...new Set(reasons)];
  }

  function eligible(signal, now = Date.now()) {
    return Boolean(signal.candidate && signalReasons(signal, now).length === 0);
  }

  function deriveCompany(company, now = Date.now()) {
    let signals = (company.signals || []).filter(signal => eligible(signal, now));
    const composites = signals.filter(signal => (signal.members || []).length);
    signals = signals.filter(signal => !composites.some(parent => parent.members.includes(signal.metric) && parent.effect === signal.effect));
    const effects = new Set(signals.map(s => s.effect).filter(value => ['improving', 'weakening'].includes(value)));
    const latest = periodTime(company.data_period === undefined ? company.latest_period : company.data_period);
    const today = Math.floor(now / 86400000) * 86400000;
    const fresh = latest !== null && latest <= today && today - latest <= (company.max_age_days || 200) * 86400000;
    const direction = effects.size > 1 ? 'mixed' : effects.size === 1 ? [...effects][0] : fresh ? 'no_shift' : 'insufficient';
    signals.sort((a, b) => Number(b.primary) - Number(a.primary) || Number(b.support === 'confirmed') - Number(a.support === 'confirmed') || (periodTime(b.period) || 0) - (periodTime(a.period) || 0) || String(a.metric).localeCompare(String(b.metric)));
    const uniqueDomains = new Set(signals.map(s => s.domain));
    const persistent = signals.filter(s => s.support === 'confirmed').length;
    let headline;
    if (direction === 'mixed') {
      const up = signals.find(s => s.effect === 'improving');
      const down = signals.find(s => s.effect === 'weakening');
      headline = `${up.label} is improving; ${down.label.toLowerCase()} is weakening.`;
      if (up.metric === down.metric) headline = `${up.label}: the growth trend and comparison with company history disagree.`;
    } else if (signals.length) headline = signals[0].summary;
    else headline = direction === 'no_shift' ? 'No qualifying business change in the available reported data.' : 'The available business data is missing, outdated, or cannot support an assessment.';
    return { ...company, signals, direction, headline, persistent, domains: uniqueDomains.size, lead: signals[0] || null };
  }

  function cleanState(input) {
    const result = { ...DEFAULT, ...(input || {}) };
    if (!['companies', 'signals'].includes(result.view)) result.view = DEFAULT.view;
    if (!['holdings', 'tracked'].includes(result.scope)) result.scope = DEFAULT.scope;
    if (!['all', ...Object.keys(DIRECTIONS)].includes(result.direction)) result.direction = 'all';
    if (!['all', 'confirmed', 'two_quarters', 'emerging'].includes(result.persistence)) result.persistence = 'all';
    if (!['all', ...Object.keys(KINDS)].includes(result.kind)) result.kind = 'all';
    result.query = String(result.query || '').slice(0, 200);
    result.page = Math.max(0, Math.floor(Number(result.page) || 0));
    for (const key of ['includeQuiet', 'includeSuppressed', 'includeSteady', 'more']) result[key] = result[key] === true;
    return result;
  }

  function matchesEvidence(signal, state) {
    return (state.persistence === 'all' || signal.support === state.persistence || (state.persistence === 'two_quarters' && signal.support === 'confirmed' && signal.support_basis === 'two_quarters'))
      && (state.kind === 'all' || signal.kind === state.kind)
      && (state.source === 'all' || signal.source === state.source);
  }

  function select(overview, input, tickers = [], signalIndex = null, now = Date.now()) {
    const state = cleanState(input);
    const identities = new Map();
    for (const row of tickers) for (const key of [row.ticker, row.display_ticker, row.quote_ticker]) if (key) identities.set(canonical(key), row);
    const seen = new Set();
    const query = state.query.trim().toLowerCase();
    let companies = (overview?.companies || []).map(company => {
      const identity = [company.ticker, ...(company.aliases || [])].map(canonical).map(key => identities.get(key)).find(Boolean);
      const id = canonical(identity?.ticker || company.ticker);
      if (seen.has(id) || (tickers.length && !identity)) return null;
      seen.add(id);
      return deriveCompany({ ...company, company: identity?.company || company.company, in_holdings: identity?.in_holdings === true }, now);
    }).filter(Boolean).filter(company => (state.scope !== 'holdings' || company.in_holdings)
      && (!query || [company.ticker, company.company, ...(company.aliases || [])].join(' ').toLowerCase().includes(query))
      && (state.direction === 'all' || company.direction === state.direction));
    const byTicker = new Map(companies.map(company => [company.ticker, company]));
    let signals = (signalIndex?.signals || []).filter(signal => {
      if (!byTicker.has(signal.ticker) || !matchesEvidence(signal, state)) return false;
      if (!state.includeSteady && signal.effect === 'steady') return false;
      const reasons = signalReasons(signal, now);
      // A persistence filter means current, eligible business evidence. Context
      // never borrows a two-quarter badge, even in the suppressed-data view.
      if (state.persistence !== 'all' && !eligible(signal, now)) return false;
      const blocking = reasons.filter(reason => !(reason === 'period_unavailable' && !signal.candidate));
      return state.includeSuppressed || blocking.length === 0;
    });
    if (state.view === 'companies' && (state.persistence !== 'all' || state.kind !== 'all' || state.source !== 'all')) {
      companies = companies.filter(company => company.signals.some(signal => matchesEvidence(signal, state)));
    } else if (state.view === 'signals' && signalIndex) {
      const withSignals = new Set(signals.map(signal => signal.ticker));
      companies = companies.filter(company => withSignals.has(company.ticker));
    }
    const coverage = { total: companies.length, improving: 0, weakening: 0, mixed: 0, no_shift: 0, insufficient: 0 };
    companies.forEach(company => { coverage[company.direction] += 1; });
    const sorted = list => list.sort((a, b) => Number(b.in_holdings) - Number(a.in_holdings) || Number(Boolean(b.lead?.primary)) - Number(Boolean(a.lead?.primary)) || Number(Boolean(b.persistent)) - Number(Boolean(a.persistent)) || (periodTime(b.lead?.period || b.latest_period) || 0) - (periodTime(a.lead?.period || a.latest_period) || 0) || a.ticker.localeCompare(b.ticker));
    sorted(companies);
    if (state.view === 'companies' && !state.includeQuiet && state.direction === 'all') companies = companies.filter(company => ['improving', 'weakening', 'mixed'].includes(company.direction) || company.change?.kind === 'resolved');
    const order = new Map(companies.map((company, index) => [company.ticker, index]));
    signals = signals.filter(signal => order.has(signal.ticker)).sort((a, b) => order.get(a.ticker) - order.get(b.ticker) || (periodTime(b.period) || 0) - (periodTime(a.period) || 0) || String(a.metric).localeCompare(String(b.metric)));
    const rows = state.view === 'signals' ? signals : companies;
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    const page = Math.min(state.page, pages - 1);
    return { state: { ...state, page }, companies, signals, byTicker, coverage, total: rows.length, page, pages, rows: rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), holdingsAvailable: tickers.length > 0 };
  }

  function option(value, label, selected) {
    return `<option value="${esc(value)}"${value === selected ? ' selected' : ''}>${esc(label)}</option>`;
  }
  function selector(name, label, values, value) {
    return `<label class="inf-field"><span>${esc(label)}</span><select data-inf-field="${esc(name)}">${values.map(([key, text]) => option(key, text, value)).join('')}</select></label>`;
  }
  function support(signal) {
    if (!signal) return 'No qualifying signal';
    if (signal.support === 'confirmed') {
      if (signal.support_basis === 'two_quarters') return 'Two-quarter support';
      if (signal.support_basis === 'trailing_year') return 'Trailing-year support';
      if (signal.support_basis === 'two_periods') return 'Two-period support';
      if (signal.support_basis === 'components') return 'Supported · inspect components';
      return 'Supported · method not supplied';
    }
    if (signal.support === 'emerging') return 'Early · one quarter';
    return 'Observation';
  }
  function status(direction) {
    const symbol = { improving: '↑', weakening: '↓', mixed: '↔', no_shift: '—', insufficient: '?' }[direction];
    return `<span class="inf-direction inf-${esc(direction)}"><span aria-hidden="true">${symbol}</span> ${esc(DIRECTIONS[direction])}</span>`;
  }
  function changeBadge(company, now) {
    const change = company.change;
    if (!change || !['new', 'changed', 'resolved'].includes(change.kind)) return '';
    const time = periodTime(change.observed_at);
    if (time === null || now < time || now - time > 7 * 86400000) return '';
    return `<span class="inf-change">${esc(change.kind[0].toUpperCase() + change.kind.slice(1))} · observed ${esc(dateLabel(change.observed_at))}</span>`;
  }

  function companyRow(company, opened, now) {
    const signal = company.lead;
    return `<details class="inf-company" data-inf-company="${esc(company.ticker)}"${opened.has(company.ticker) ? ' open' : ''}>
      <summary class="inf-company-summary">
        <span class="inf-identity"><strong>${esc(company.ticker)}</strong><span class="inf-company-name">${esc(company.company)}</span>${company.in_holdings ? '<span class="inf-held">Holding</span>' : ''}</span>
        <span class="inf-status-cell">${status(company.direction)}</span>
        <span class="inf-headline"><span>${esc(company.headline)}</span>${changeBadge(company, now)}<span class="inf-sub">${company.domains ? `${company.domains} business ${company.domains === 1 ? 'area' : 'areas'} · ` : ''}${company.signal_count} changed observations available</span></span>
        <span class="inf-support">${esc(support(signal))}${company.direction === 'mixed' ? '<span class="inf-sub">Evidence disagrees</span>' : company.signals.length > 1 ? '<span class="inf-sub">Applies to lead signal</span>' : ''}</span>
        <span class="inf-period">${esc(dateLabel(signal?.period || company.latest_period))}<span class="inf-sub">Period end</span><span class="inf-expand" aria-hidden="true">+</span></span>
      </summary>
      <div class="inf-company-body" data-inf-evidence><p class="inf-secondary">Open evidence to load the reported observations.</p></div>
    </details>`;
  }

  function pagination(selection) {
    if (selection.pages === 1) return '';
    return `<nav class="inf-pagination" aria-label="Inflections result pages"><button type="button" data-inf-page="${selection.page - 1}"${selection.page === 0 ? ' disabled' : ''}>Previous</button><span>Page ${selection.page + 1} of ${selection.pages}</span><button type="button" data-inf-page="${selection.page + 1}"${selection.page + 1 === selection.pages ? ' disabled' : ''}>Next</button></nav>`;
  }

  function signalRows(selection, now) {
    return `<div class="inf-table-wrap"><table class="inf-signal-table"><caption class="sr-only">Matching observations with their comparison basis, period and data quality</caption><thead><tr><th scope="col">Company / evidence</th><th scope="col">Observation and comparison</th><th scope="col">Support / data quality</th><th scope="col">Period end</th><th scope="col">Source</th></tr></thead><tbody>${selection.rows.map(signal => {
      const reasons = signalReasons(signal, now);
      return `<tr><td><button type="button" class="inf-text-button" data-inf-open="${esc(signal.ticker)}">${esc(signal.ticker)}</button><span class="inf-sub">${esc(KINDS[signal.kind] || signal.kind)}</span></td><td>${esc(signal.summary)}<span class="inf-sub">${esc(signal.comparison)}</span></td><td>${esc(support(signal))}${reasons.length ? `<span class="inf-quality">${reasons.map(reason => esc(REASONS[reason] || reason)).join(' · ')}</span>` : ''}</td><td>${esc(dateLabel(signal.period))}</td><td>${esc(SOURCES[signal.source] || signal.source)}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }

  function render(overview, input = {}, options = {}) {
    if (!overview || overview.schema_version !== 'inflections.v1' || !Array.isArray(overview.companies)) return '<section class="inf-workbench"><h2>Inflections</h2><p class="inf-empty">Company observations are unavailable. Try loading this section again.</p><button type="button" data-inf-retry>Retry</button></section>';
    const now = options.now == null ? Date.now() : options.now;
    const selection = select(overview, input, options.tickers || [], options.signalIndex, now);
    const state = selection.state;
    const sources = [...new Set((overview.companies || []).flatMap(company => (company.signals || []).map(signal => signal.source)).concat((state.view === 'signals' ? options.signalIndex?.signals || [] : []).map(signal => signal.source)))].sort();
    const active = Object.entries({ Scope: state.scope === 'holdings' ? 'Holdings' : 'All tracked', Direction: state.direction === 'all' ? null : DIRECTIONS[state.direction], Persistence: state.persistence === 'all' ? null : state.persistence === 'confirmed' ? 'Supported signals' : state.persistence === 'two_quarters' ? 'Two-quarter support' : 'Early signal', Evidence: state.kind === 'all' ? null : KINDS[state.kind], Source: state.source === 'all' ? null : SOURCES[state.source] || state.source }).filter(([, value]) => value);
    const start = selection.total ? selection.page * PAGE_SIZE + 1 : 0;
    const end = Math.min((selection.page + 1) * PAGE_SIZE, selection.total);
    const filtersNarrowEvidence = state.kind !== 'all' || state.source !== 'all' || state.persistence !== 'all';
    const snapshotAge = periodTime(overview.source_generated_at);
    return `<section class="inf-workbench" aria-label="Inflections workbench">
      <header class="inf-header"><div><h2>Inflections</h2><p>Meaningful changes in the businesses you follow.</p></div><div class="inf-clock">Source snapshot ${esc(dateLabel(overview.source_generated_at))}${snapshotAge !== null && now - snapshotAge > 7 * 86400000 ? '<span class="inf-quality">Snapshot is more than a week old</span>' : ''}<span class="inf-sub">Reporting periods are shown on each observation</span></div></header>
      <nav class="inf-views" aria-label="Inflections views"><button type="button" data-inf-view="companies" aria-pressed="${state.view === 'companies'}">Company overview</button><button type="button" data-inf-view="signals" aria-pressed="${state.view === 'signals'}">Signal explorer</button></nav>
      ${options.explorerReturn ? '<p class="inf-secondary"><button type="button" data-inf-back-explorer>Back to filtered observations</button></p>' : ''}
      <div class="inf-toolbar"><label class="inf-field inf-search"><span>Company</span><input type="search" data-inf-field="query" value="${esc(state.query)}" placeholder="Search ticker or company" autocomplete="off"></label>${selector('scope', 'Scope', [['holdings', 'Holdings'], ['tracked', 'All tracked companies']], state.scope)}${selector('direction', 'Business direction', [['all', 'All directions'], ['improving', 'Improving'], ['weakening', 'Weakening'], ['mixed', 'Mixed'], ['no_shift', 'No clear shift'], ['insufficient', 'Insufficient data']], state.direction)}<button type="button" data-inf-more aria-expanded="${state.more}">More filters</button></div>
      <div class="inf-more"${state.more ? '' : ' hidden'}>${selector('persistence', 'Persistence', [['all', 'All support levels'], ['confirmed', 'Supported signals'], ['two_quarters', 'Two-quarter support'], ['emerging', 'Early signal']], state.persistence)}${selector('kind', 'Evidence category', [['all', 'All categories'], ...Object.entries(KINDS).filter(([key]) => state.view === 'signals' || ['business', 'history'].includes(key))], state.kind)}${selector('source', 'Source', [['all', 'All sources'], ...sources.map(source => [source, SOURCES[source] || source])], state.source)}<label class="inf-check"><input type="checkbox" data-inf-field="includeQuiet"${state.includeQuiet ? ' checked' : ''}> Include companies without a clear signal</label>${state.view === 'signals' ? `<label class="inf-check"><input type="checkbox" data-inf-field="includeSuppressed"${state.includeSuppressed ? ' checked' : ''}> Include suppressed and outdated observations</label><label class="inf-check"><input type="checkbox" data-inf-field="includeSteady"${state.includeSteady ? ' checked' : ''}> Include steady observations</label>` : ''}</div>
      <div class="inf-active"><span>${active.map(([key, value]) => `${esc(key)}: ${esc(value)}`).join(' · ')}${state.query ? ` · Search: ${esc(state.query)}` : ''}${state.includeQuiet ? ' · Includes quiet companies' : ''}${state.includeSuppressed && state.view === 'signals' ? ' · Includes suppressed data' : ''}${state.includeSteady && state.view === 'signals' ? ' · Includes steady observations' : ''}</span><button type="button" class="inf-text-button" data-inf-clear>Clear filters</button></div>
      ${filtersNarrowEvidence ? `<p class="inf-secondary">${state.view === 'companies' ? 'Filters find companies with matching business evidence. Each summary still includes all eligible business evidence, including disagreements. Peer, operating, and context observations are searchable in Signal explorer.' : 'Business direction refers to the company assessment. The rows below retain each observation’s own comparison basis.'}</p>` : ''}
      ${state.scope === 'holdings' && !selection.holdingsAvailable ? '<p class="inf-quality">Holdings membership is unavailable. Choose All tracked companies to inspect the research universe.</p>' : ''}
      <div class="inf-results" aria-live="polite"><span>Showing ${start}–${end} of ${selection.total} matching ${state.view === 'companies' ? 'companies' : 'observations'}</span>${state.view === 'companies' ? '<span>Order: holdings · material core changes · persistence · reporting date</span>' : ''}</div>
      ${state.view === 'signals' && options.signalLoading ? '<p class="inf-empty" role="status">Loading the observation index…</p>' : state.view === 'signals' && options.signalError ? '<p class="inf-empty">The observation index could not be loaded.</p><button type="button" data-inf-retry-signals>Retry observations</button>' : selection.total ? state.view === 'companies' ? `<div class="inf-column-heads" aria-hidden="true"><span>Company</span><span>Business direction</span><span>What changed</span><span>Evidence</span><span>Latest period</span></div>${selection.rows.map(company => companyRow(company, options.opened || new Set(), now)).join('')}` : signalRows(selection, now) : `<div class="inf-empty"><p>${selection.coverage.total && state.view === 'companies' ? 'No qualifying business changes in this selection. Coverage below shows companies with no clear shift or insufficient data.' : 'No results match these filters.'}</p><button type="button" data-inf-clear>Clear filters</button></div>`}
      ${pagination(selection)}
      <details class="inf-coverage"><summary>Coverage and definitions · ${selection.coverage.total} matching companies</summary><div class="inf-coverage-counts">${Object.entries(DIRECTIONS).map(([key, label]) => `<button type="button" data-inf-direction="${key}">${esc(label)} <strong>${selection.coverage[key]}</strong></button>`).join('')}</div><p>Coverage uses the same selected scope, company search, direction and evidence filters. In the overview, quiet companies are counted here even when their rows are hidden.</p><p>Business direction combines eligible reported business signals. Related metrics and composite components do not earn extra votes. Opposing evidence remains Mixed.</p><p>Support belongs to a specific business signal. Two-quarter and trailing-year checks are labeled separately; legacy confirmation without a recorded method is disclosed. Early means one quarter. Operating observations, earnings surprises, peer comparisons and external context have separate meanings.</p><p>Financial series older than ${overview.max_age_days || 200} days, unknown periods, volatile bases and suppressed duplicates cannot support a headline. The source snapshot date is different from the reporting period and any forecast period.</p><p>Change labels compare successful snapshots, are baselined on first publication, and expire after seven days. Rebuilding the same observations does not create new changes.</p></details>
    </section>`;
  }

  function safeSource(signal) {
    const raw = signal.raw || {};
    const url = String(raw.source_url || '');
    if (/^https?:\/\//i.test(url)) return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open source report</a>`;
    const ref = String(raw.evidence_ref || '');
    if (!ref || ref.includes('..') || ref.includes(':')) return '';
    return `<a href="https://github.com/magis-capital-partners/single-stock-investments/blob/main/${ref.split('/').map(encodeURIComponent).join('/')}" target="_blank" rel="noopener noreferrer">Open source evidence</a>`;
  }

  function valueLabel(value, raw) {
    if (!numeric(value)) return 'Unavailable';
    const n = Number(value);
    if (['op_margin', 'cfo_margin'].includes(String(raw.metric || '').replace('growth_regime.', ''))) return (n * 100).toFixed(1) + '%';
    if (raw.unit === 'share_pct') return n.toFixed(2) + '%';
    if (raw.unit === 'usd_per_contract') return '$' + n.toFixed(3);
    return n.toLocaleString('en-US', { maximumFractionDigits: 3 });
  }

  function observation(signal, now) {
    const reasons = signalReasons(signal, now);
    const raw = signal.raw || {};
    const points = (raw.points || []).filter(point => point && numeric(point.value)).slice(-8);
    const source = safeSource(signal);
    return `<article class="inf-observation"><div class="inf-observation-heading"><h4>${esc(signal.label)}</h4><span>${esc(support(signal))}</span></div><p>${esc(signal.summary)}</p><p class="inf-comparison">${esc(signal.comparison)}</p><p class="inf-provenance">${esc(SOURCES[signal.source] || signal.source)} · ${esc(dateLabel(signal.period))}${source ? ` · ${source}` : ''}</p>${reasons.length ? `<p class="inf-quality">${reasons.map(reason => esc(REASONS[reason] || reason)).join(' · ')}. Excluded from the company headline.</p>` : ''}${raw.revenue_proxy ? '<p class="inf-quality">Revenue proxy: this series uses an operating-income substitute. Inspect the source before treating it as revenue.</p>' : ''}${signal.ttm_agrees === true ? '<p class="inf-secondary">Trailing-year trend supports this signal.</p>' : signal.ttm_agrees === false ? '<p class="inf-secondary">Trailing-year trend does not yet support this signal.</p>' : signal.candidate ? '<p class="inf-secondary">A supporting trailing-year check is not established for this observation.</p>' : ''}<details class="inf-method"><summary>Reported history and calculation detail</summary>${points.length ? `<div class="inf-table-wrap"><table><caption>Reported levels · ${esc(raw.unit || 'filing units; not growth rates')}</caption><thead><tr><th scope="col">Period end</th><th scope="col">Value</th></tr></thead><tbody>${points.map(point => `<tr><td>${esc(dateLabel(point.period))}</td><td class="inf-number">${esc(valueLabel(point.value, raw))}</td></tr>`).join('')}</tbody></table></div>` : '<p>Underlying reported levels are not available in this series.</p>'}<dl class="inf-diagnostics"><div><dt>Comparison basis</dt><dd>${esc(raw.basis || 'Not supplied')}</dd></div><div><dt>Smoothed change</dt><dd>${esc(numeric(raw.accel) ? Number(raw.accel).toPrecision(4) : 'Not supplied')}</dd></div><div><dt>Raw change</dt><dd>${esc(numeric(raw.accel_raw) ? Number(raw.accel_raw).toPrecision(4) : 'Not supplied')}</dd></div><div><dt>Change / noise threshold</dt><dd>${esc(numeric(raw.strength) ? Number(raw.strength).toFixed(2) + '×' : 'Not supplied')}</dd></div><div><dt>Materiality threshold</dt><dd>${esc(numeric(raw.threshold) ? Number(raw.threshold).toPrecision(4) : 'Not supplied')}</dd></div></dl></details></article>`;
  }

  function renderEvidence(company, observations, now = Date.now()) {
    const parts = [];
    const clean = observations.filter(signal => !signalReasons(signal, now).some(reason => ['duplicate_component', 'not_selected', 'source_stale', 'aged', 'volatile_base', 'future'].includes(reason)));
    for (const kind of ['business', 'history', 'operating', 'peers', 'expectations', 'context']) {
      const group = clean.filter(signal => signal.kind === kind);
      if (!group.length) continue;
      if (['business', 'history'].includes(kind)) parts.push(`<section class="inf-evidence-section"><h3>${esc(KINDS[kind])}</h3>${group.map(signal => observation(signal, now)).join('')}</section>`);
      else parts.push(`<details class="inf-evidence-section inf-secondary-evidence"><summary>${esc(KINDS[kind])} (${group.length})<span class="inf-sub">${esc(group[0].summary)}${group.length > 1 ? ` · ${group.length - 1} more` : ''}</span></summary>${group.map(signal => observation(signal, now)).join('')}</details>`);
    }
    const suppressed = observations.filter(signal => !clean.includes(signal) || signal.kind === 'balance_sheet');
    if (suppressed.length) parts.push(`<details class="inf-suppressed"><summary>Other metrics and suppressed observations (${suppressed.length})</summary>${suppressed.map(signal => observation(signal, now)).join('')}</details>`);
    if (!observations.length) parts.push('<p>No metric series is available for this company.</p>');
    if (company.ticker === 'QDEL') parts.push('<details class="inf-model" data-inf-model><summary>Respiratory demand research and forecasts</summary><div data-inf-model-body><p>Open to load the separate revenue model.</p></div></details>');
    return `<div class="inf-evidence-top"><p>Reported periods and comparison types are kept separate below.</p><button type="button" data-inf-research="${esc(company.ticker)}">Open company research</button></div>${parts.join('')}`;
  }

  function initialState() {
    if (remembered) return cleanState(remembered);
    try { return cleanState(JSON.parse(global.localStorage?.getItem(KEY) || 'null')); } catch (_) { return cleanState(); }
  }

  function mount(root, options = {}) {
    const lifecycle = new AbortController();
    let disposed = false;
    let state = initialState();
    let overview = options.overview;
    let signalIndex = null, signalLoading = false, signalError = false;
    const opened = rememberedOpen;
    const request = options.fetchJson || (async url => {
      const response = await global.fetch(url, { cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) throw new Error('Observation request failed');
      return response.json();
    });
    let debounce;
    const now = () => options.now == null ? Date.now() : options.now;
    const persist = () => {
      remembered = { ...state };
      try { global.localStorage?.setItem(KEY, JSON.stringify(remembered)); } catch (_) { /* unavailable storage */ }
    };
    function draw(focusQuery = false) {
      if (disposed) return;
      // A lazy index has no rows until it arrives. Do not clamp a remembered
      // explorer page against that temporary empty collection.
      if (state.view !== 'signals' || signalIndex) state = select(overview, state, options.tickers || [], signalIndex, now()).state;
      const oldInput = root.querySelector('[data-inf-field="query"]');
      const position = oldInput?.selectionStart;
      const focused = root.ownerDocument?.activeElement;
      const focusedField = root.contains(focused) ? focused?.dataset.infField : null;
      const focusedView = root.contains(focused) ? focused?.dataset.infView : null;
      const focusedMore = root.contains(focused) && focused?.hasAttribute('data-inf-more');
      root.innerHTML = render(overview, state, { ...options, signalIndex, signalLoading, signalError, opened, explorerReturn: Boolean(returnToExplorer), now: now() });
      if (focusQuery) {
        const input = root.querySelector('[data-inf-field="query"]');
        input?.focus();
        try { input?.setSelectionRange(position ?? input.value.length, position ?? input.value.length); } catch (_) { /* search input implementations differ */ }
      } else if (focusedField) Array.from(root.querySelectorAll('[data-inf-field]')).find(element => element.dataset.infField === focusedField)?.focus();
      else if (focusedView) Array.from(root.querySelectorAll('[data-inf-view]')).find(element => element.dataset.infView === focusedView)?.focus();
      else if (focusedMore) root.querySelector('[data-inf-more]')?.focus();
      for (const details of root.querySelectorAll('[data-inf-company][open]')) loadEvidence(details);
    }
    async function loadIndex() {
      if (signalIndex || signalLoading || !overview) return;
      signalLoading = true; signalError = false; draw();
      try {
        const key = `${overview.snapshot_id}|${overview.signals_ref}`;
        if (!cache.has(key)) cache.set(key, request(overview.signals_ref).then(doc => {
          if (doc.schema_version !== 'inflections.v1' || doc.snapshot_id !== overview.snapshot_id || !Array.isArray(doc.signals)) throw new Error('Snapshot mismatch');
          return doc;
        }).catch(error => { cache.delete(key); throw error; }));
        signalIndex = await cache.get(key);
      } catch (_) { signalError = true; }
      signalLoading = false;
      if (state.view === 'signals') draw();
    }
    async function loadEvidence(details) {
      const ticker = details.dataset.infCompany;
      const company = overview?.companies.find(row => row.ticker === ticker);
      const body = details.querySelector('[data-inf-evidence]');
      if (!company || !body || body.dataset.loaded === overview.snapshot_id || body.dataset.loading === 'true') return;
      body.dataset.loading = 'true';
      body.innerHTML = '<p class="inf-secondary" role="status">Loading the reported evidence…</p>';
      const key = `${overview.snapshot_id}|${company.evidence_ref}`;
      try {
        if (!cache.has(key)) cache.set(key, request(company.evidence_ref).then(doc => {
          if (doc.schema_version !== 'inflections.v1' || doc.snapshot_id !== overview.snapshot_id || !doc.by_ticker) throw new Error('Snapshot mismatch');
          return doc;
        }).catch(error => { cache.delete(key); throw error; }));
        const doc = await cache.get(key);
        if (!Array.isArray(doc.by_ticker[ticker])) throw new Error('Company evidence missing');
        body.innerHTML = renderEvidence(company, doc.by_ticker[ticker], now());
        body.dataset.loaded = overview.snapshot_id;
      } catch (_) {
        body.innerHTML = '<p class="inf-quality">The evidence could not be loaded or belongs to a different snapshot. Reload the source snapshot, or try the evidence again.</p><button type="button" data-inf-retry-evidence>Retry evidence</button><button type="button" data-inf-retry>Reload snapshot</button>';
      } finally { delete body.dataset.loading; }
    }
    async function loadModel(details) {
      const body = details.querySelector('[data-inf-model-body]');
      if (!body || body.dataset.loaded) return;
      body.innerHTML = '<p role="status">Loading respiratory demand research…</p>';
      try {
        const doc = await request('data/respiratory_model.json');
        if (!doc.baseline || !options.renderModel) throw new Error('Model unavailable');
        body.innerHTML = `<p class="inf-secondary">Model snapshot: ${esc(dateLabel(doc.generated_at || doc.as_of))}. Forward periods are forecasts; historical observations are reported data.</p>` + options.renderModel(doc);
        body.dataset.loaded = 'true';
      } catch (_) { body.innerHTML = '<p class="inf-quality">The separate respiratory model is unavailable.</p><button type="button" data-inf-retry-model>Retry model</button>'; }
    }
    root.addEventListener('toggle', event => {
      const details = event.target;
      if (details.matches('[data-inf-company]')) {
        if (details.open) { opened.add(details.dataset.infCompany); loadEvidence(details); }
        else opened.delete(details.dataset.infCompany);
      } else if (details.matches('[data-inf-model]') && details.open) loadModel(details);
    }, { capture: true, signal: lifecycle.signal });
    function updateField(target, focusQuery = false) {
      const key = target.dataset.infField;
      if (!(key in DEFAULT)) return;
      state = cleanState({ ...state, [key]: target.type === 'checkbox' ? target.checked : target.value, page: 0 });
      persist(); draw(focusQuery);
    }
    root.addEventListener('input', event => {
      if (event.target.dataset.infField !== 'query') return;
      clearTimeout(debounce);
      const value = event.target.value;
      state = cleanState({ ...state, query: value, page: 0 });
      debounce = setTimeout(() => { state = cleanState({ ...state, query: value, page: 0 }); persist(); draw(true); }, 150);
    }, { signal: lifecycle.signal });
    root.addEventListener('change', event => { if (event.target.dataset.infField && event.target.dataset.infField !== 'query') updateField(event.target); }, { signal: lifecycle.signal });
    root.addEventListener('click', async event => {
      const button = event.target.closest('button');
      if (!button || !root.contains(button)) return;
      if (button.hasAttribute('data-inf-research')) { returnScroll = global.scrollY || 0; options.onResearch?.(button.dataset.infResearch); return; }
      if (button.hasAttribute('data-inf-retry-evidence')) { loadEvidence(button.closest('[data-inf-company]')); return; }
      if (button.hasAttribute('data-inf-retry-model')) { loadModel(button.closest('[data-inf-model]')); return; }
      if (button.hasAttribute('data-inf-retry-signals')) { loadIndex(); return; }
      if (button.hasAttribute('data-inf-retry')) {
        try {
          const next = await request('data/inflection_overview.json');
          if (next.schema_version !== 'inflections.v1' || !Array.isArray(next.companies)) throw new Error('Invalid snapshot');
          overview = next;
          options.onOverviewReload?.(overview);
          signalIndex = null; signalError = false; opened.clear(); draw();
          if (state.view === 'signals') loadIndex();
        } catch (_) { button.textContent = 'Snapshot unavailable · retry'; }
        return;
      }
      if (button.hasAttribute('data-inf-open')) {
        const ticker = button.dataset.infOpen;
        returnToExplorer = { ...state };
        state = cleanState({ ...DEFAULT, scope: 'tracked', query: ticker, includeQuiet: true });
        opened.add(ticker);
      } else if (button.hasAttribute('data-inf-back-explorer')) {
        state = returnToExplorer || { ...DEFAULT, view: 'signals' };
        returnToExplorer = null;
      } else if (button.hasAttribute('data-inf-view')) {
        if (button.dataset.infView === 'signals' && returnToExplorer) { state = returnToExplorer; returnToExplorer = null; }
        else {
          const view = button.dataset.infView;
          const sources = new Set((overview?.companies || []).flatMap(company => (company.signals || []).map(signal => signal.source)));
          state = { ...state, view, page: 0,
            kind: view === 'companies' && !['all', 'business', 'history'].includes(state.kind) ? 'all' : state.kind,
            source: view === 'companies' && !sources.has(state.source) ? 'all' : state.source };
        }
      }
      else if (button.hasAttribute('data-inf-more')) state = { ...state, more: !state.more };
      else if (button.hasAttribute('data-inf-clear')) state = { ...DEFAULT, view: state.view, scope: state.scope };
      else if (button.hasAttribute('data-inf-page')) state = { ...state, page: Number(button.dataset.infPage) };
      else if (button.hasAttribute('data-inf-direction')) state = { ...state, direction: button.dataset.infDirection, includeQuiet: true, page: 0 };
      else return;
      clearTimeout(debounce); persist(); draw();
      if (state.view === 'signals') loadIndex();
    }, { signal: lifecycle.signal });
    draw();
    if (returnScroll !== null && global.requestAnimationFrame) {
      const position = returnScroll;
      returnScroll = null;
      global.requestAnimationFrame(() => global.scrollTo?.(0, position));
    }
    if (state.view === 'signals') loadIndex();
    return { getState: () => ({ ...state }), dispose: () => { disposed = true; clearTimeout(debounce); lifecycle.abort(); } };
  }

  global.InflectionsViz = { DEFAULT, PAGE_SIZE, periodTime, dateLabel, signalReasons, eligible, deriveCompany, cleanState, select, render, renderEvidence, mount };
})(window);
