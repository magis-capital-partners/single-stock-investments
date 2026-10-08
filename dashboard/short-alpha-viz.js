(function (global) {
  'use strict';

  const CUSTOM_KEY = 'ssi_short_alpha_custom_v2';
  const CHECKINS_KEY = 'ssi_short_alpha_checkins_v2';
  const FILTER_KEY = 'ssi_short_alpha_filter_v2';
  const REMOVED_KEY = 'ssi_short_alpha_removed_v2';
  const SELECTED_KEY = 'ssi_short_alpha_selected_v2';
  const REPO_BASE = 'https://github.com/magis-capital-partners/single-stock-investments/blob/main/';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; } catch (_) { return fallback; }
  }
  function write(key, value) { localStorage.setItem(key, JSON.stringify(value)); }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function price(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('en-US', { minimumFractionDigits: n < 2 ? 3 : 2, maximumFractionDigits: 4 }) : '—';
  }
  function frameworkMap(payload) { return Object.fromEntries((payload.frameworks || []).map(row => [row.id, row])); }
  function sourceTypeMap(payload) { return Object.fromEntries((payload.source_types || []).map(row => [row.id, row])); }
  function removedSet() { return new Set(read(REMOVED_KEY, [])); }
  function applyCheckins(row) {
    const overlays = read(CHECKINS_KEY, {});
    const all = [...(row.check_ins || []), ...(overlays[row.ticker] || [])]
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    if (!all.length) return row;
    const latest = all[all.length - 1];
    row.check_ins = all;
    row.outcome = {
      latest_date: latest.date,
      latest_price: Number(latest.price),
      hypothesis_state: latest.hypothesis_state || 'open',
      check_in_count: all.length,
    };
    return row;
  }
  function getCandidates(payload) {
    const removed = removedSet();
    return [...(payload.candidates || []), ...read(CUSTOM_KEY, [])]
      .filter(row => row && row.ticker && !removed.has(row.ticker))
      .map(row => clone(row));
  }
  function getPositions(payload) {
    const removed = removedSet();
    const drafts = read(CUSTOM_KEY, []).filter(row => row && row.position);
    return [...(payload.positions || payload.ideas || []), ...drafts]
      .filter(row => row && row.ticker && !removed.has(row.ticker) && row.position)
      .map(row => applyCheckins(clone(row)));
  }
  function linkFor(source) {
    if (!source) return '';
    if (source.url) {
      try {
        const parsed = new URL(source.url);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
      } catch (_) { return ''; }
    }
    if (!source.ref) return '';
    return REPO_BASE + String(source.ref).split('/').map(encodeURIComponent).join('/');
  }
  function matchesFramework(candidate, frameworkId, frameworks) {
    if (!frameworkId || frameworkId === 'all') return true;
    const ids = new Set([...(candidate.effective_frameworks || candidate.frameworks || []), ...(candidate.gate_hits || [])]);
    if (ids.has(frameworkId)) return true;
    return (frameworks || []).some(row => row.parent === frameworkId && ids.has(row.id));
  }
  function sourceLabel(candidate, sourceTypes) {
    const first = (candidate.sources || [])[0];
    if (!first) return candidate.origin || '—';
    const kind = sourceTypes[first.type]?.label || first.type || 'Source';
    return `${kind}: ${first.label || candidate.origin || '—'}`;
  }
  function frameworkOptions(payload, selected) {
    const groups = payload.groups || [];
    const byGroup = new Map(groups.map(group => [group.id, []]));
    const loose = [];
    for (const row of payload.frameworks || []) {
      if (byGroup.has(row.group)) byGroup.get(row.group).push(row);
      else loose.push(row);
    }
    const html = groups.map(group => {
      const rows = byGroup.get(group.id) || [];
      if (!rows.length) return '';
      const options = rows.map(row => `<option value="${esc(row.id)}" ${row.id === selected ? 'selected' : ''}>${esc(row.label)}</option>`).join('');
      return `<optgroup label="${esc(group.label)}">${options}</optgroup>`;
    }).join('');
    return html + loose.map(row => `<option value="${esc(row.id)}" ${row.id === selected ? 'selected' : ''}>${esc(row.label)}</option>`).join('');
  }
  function renderFrameworkBoard(payload, active) {
    const groups = payload.groups || [];
    const coverage = payload.summary?.framework_coverage || {};
    const cards = (rows) => rows.map(row => {
      const stat = coverage[row.id] || { names: 0, positions: 0, status: row.empty_label || 'Unscored' };
      const empty = stat.names === 0;
      return `<button type="button" class="short-framework-card${active === row.id ? ' active' : ''}${empty ? ' is-unscored' : ''}" data-short-framework-card="${esc(row.id)}" title="${esc(row.question)}">
        <strong>${esc(row.label)}</strong>
        <small>${esc(row.question)}</small>
        <em>${empty ? esc(stat.status) : `${stat.names} names · ${stat.positions} live`}</em>
      </button>`;
    }).join('');
    return groups.map(group => {
      const rows = (payload.frameworks || []).filter(row => row.group === group.id);
      if (!rows.length) return '';
      return `<section class="short-framework-group"><h3>${esc(group.label)}</h3><p>${esc(group.reading || '')}</p><div class="short-framework-cards">${cards(rows)}</div></section>`;
    }).join('');
  }
  function renderNames(candidates, payload, selected) {
    const sourceTypes = sourceTypeMap(payload);
    const maps = frameworkMap(payload);
    if (!candidates.length) return '<div class="short-alpha-empty">No names match this partition.</div>';
    const body = candidates.map(row => {
      const tags = (row.effective_frameworks || row.frameworks || []).map(id => esc(maps[id]?.label || id)).join(', ') || 'Unscored';
      const borrow = row.borrow?.rate_pct == null ? (row.has_position ? 'Pending' : '—') : `${Number(row.borrow.rate_pct).toFixed(1)}%`;
      const dtc = row.crowding?.days_to_cover == null ? '—' : `${Number(row.crowding.days_to_cover).toFixed(1)}d`;
      const dtcTitle = row.crowding?.settlement_ymd ? `FINRA ${row.crowding.settlement_ymd}, context tier` : 'No days-to-cover observation';
      return `<tr class="${selected === row.ticker ? 'is-selected' : ''}" data-short-select="${esc(row.ticker)}" tabindex="0">
        <td class="short-symbol">${esc(row.ticker)}</td>
        <td>${esc(row.security_name || '')}</td>
        <td><span class="short-stage" data-stage="${esc(row.stage || '')}">${esc(row.stage || '—')}</span></td>
        <td>${tags}</td>
        <td>${esc(sourceLabel(row, sourceTypes))}</td>
        <td>${esc(row.research?.next_step || '—')}</td>
        <td class="num">${esc(borrow)}</td>
        <td class="num" title="${esc(dtcTitle)}">${esc(dtc)}</td>
      </tr>`;
    }).join('');
    return `<div class="short-names-wrap"><table class="short-names">
      <thead><tr><th>Ticker</th><th>Name</th><th>Stage</th><th>Frameworks</th><th>Source</th><th>Next gate</th><th>Borrow</th><th>Days to cover</th></tr></thead>
      <tbody>${body}</tbody>
    </table></div>`;
  }
  function renderDetail(candidate, payload) {
    if (!candidate) return '';
    const sourceTypes = sourceTypeMap(payload);
    const maps = frameworkMap(payload);
    const list = rows => (rows || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>Not recorded yet.</li>';
    const sources = (candidate.sources || []).map(source => {
      const href = linkFor(source);
      const label = `${sourceTypes[source.type]?.label || source.type}: ${source.label || 'Source'}`;
      return href ? `<a class="short-source" href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>` : `<span class="short-source">${esc(label)}</span>`;
    }).join('');
    const lenses = (candidate.effective_frameworks || []).map(id => {
      const row = maps[id];
      return `<li><strong>${esc(row?.label || id)}</strong> ${esc(row?.question || '')}</li>`;
    }).join('') || '<li>Unscored. No lens has been written for this name.</li>';
    const furnace = (candidate.furnace_hits || []).map(hit => `<li>${esc(hit.short_impact || 'event')} · ${esc(hit.tag)} · ${esc(hit.claim || 'Filing event')}</li>`).join('');
    const hypothesis = String(candidate.hypothesis || '').trim();
    return `<section class="short-name-detail">
      <h3>${esc(candidate.ticker)} · ${esc(candidate.security_name || '')}</h3>
      <p>${hypothesis ? esc(hypothesis) : 'Lead only. A publisher hit or filing event is not a thesis. Write the market belief, the variant view, one catalyst, and one falsifier before promoting it.'}</p>
      ${candidate.research?.review_note ? `<p class="form-hint">${esc(candidate.research.review_note)}</p>` : ''}
      <div class="short-detail-grid">
        <div class="short-detail-card"><h4>Lenses</h4><ul>${lenses}</ul></div>
        <div class="short-detail-card"><h4>What should break</h4><ul>${list(candidate.catalysts)}</ul></div>
        <div class="short-detail-card"><h4>What proves us wrong</h4><ul>${list(candidate.falsifiers)}</ul></div>
      </div>
      <div class="short-sources">${sources || '<span class="form-hint">No sources linked.</span>'}</div>
      ${furnace ? `<div class="short-detail-card"><h4>Filing events</h4><ul>${furnace}</ul></div>` : ''}
    </section>`;
  }
  function renderAddForm(payload) {
    return `<details class="short-alpha-add">
      <summary>+ Track a name</summary>
      <form class="short-alpha-add-form" data-short-add-form>
        <label>Ticker<input name="ticker" required maxlength="14" placeholder="XYZ"></label>
        <label>Security name<input name="security_name" required placeholder="Company or instrument"></label>
        <label>Shares short <span class="form-hint">optional</span><input name="shares" type="number" min="1" step="any" placeholder="Leave blank to track a lead"></label>
        <label>Opened price<input name="opened_price" type="number" min="0.0001" step="any" placeholder="Required only with shares"></label>
        <label>Primary framework<select name="framework">${frameworkOptions(payload)}</select></label>
        <label>Instrument<select name="instrument_type"><option value="operating_company">Operating company</option><option value="holding_company">Holding company</option><option value="leveraged_etf">Leveraged ETF</option><option value="etf">ETF</option><option value="other">Other</option></select></label>
        <label>Source type<select name="source_type">${(payload.source_types || []).map(row => `<option value="${esc(row.id)}">${esc(row.label)}</option>`).join('')}</select></label>
        <label>Source URL<input name="source_url" type="url" placeholder="https://…"></label>
        <label class="full">Hypothesis<textarea name="hypothesis" required rows="2" placeholder="What does the market believe, why is it wrong, and what changes the price?"></textarea></label>
        <div class="full"><button type="submit">Save browser draft</button> <span class="form-hint" data-short-add-status>Saved in this browser until exported into candidates.json. Shares are optional. A name without shares stays off the open book.</span></div>
      </form>
    </details>`;
  }
  function renderPosition(idea, maps) {
    const outcome = idea.outcome || {};
    const completion = Number(idea.artifact_status?.completion_pct || 0);
    const sourceTypes = sourceTypeMap(maps.payload);
    const tags = (idea.effective_frameworks || idea.frameworks || []).map(id => `<span class="short-tag" title="${esc(maps.frameworks[id]?.question || '')}">${esc(maps.frameworks[id]?.label || id)}</span>`).join('');
    const list = rows => (rows || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>Not recorded yet.</li>';
    const sources = (idea.sources || []).map(source => {
      const href = linkFor(source);
      const label = `${sourceTypes[source.type]?.label || source.type}: ${source.label}`;
      return href ? `<a class="short-source" href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>` : `<span class="short-source">${esc(label)}</span>`;
    }).join('');
    const latest = (idea.check_ins || [])[idea.check_ins.length - 1] || {};
    const opened = idea.position?.opened_date || idea.position?.baseline_date || '—';
    const borrow = idea.borrow?.rate_pct == null ? '—' : `${Number(idea.borrow.rate_pct).toFixed(1)}%`;
    const dtc = idea.crowding?.days_to_cover == null ? '—' : `${Number(idea.crowding.days_to_cover).toFixed(1)}d`;
    return `<details class="short-alpha-row" data-short-ticker="${esc(idea.ticker)}">
      <summary>
        <div class="short-name"><span class="short-symbol">${esc(idea.ticker)}</span><span class="short-security"><strong>${esc(idea.security_name)}</strong><small>${esc(String(idea.instrument_type || '').replace(/_/g, ' '))}${idea.underlying ? ` · underlying ${esc(idea.underlying)}` : ''}</small></span></div>
        <div class="short-frameworks">${tags}</div>
        <div class="short-metric">$${price(idea.position?.split_adjusted_open_price || idea.position?.opened_price)}<small>split-adjusted entry</small></div>
        <div class="short-metric">${borrow}<small>borrow · ${esc(idea.borrow?.status || 'pending')}</small></div>
        <div class="short-metric">${dtc}<small>${completion}% research</small></div>
      </summary>
      <div class="short-alpha-detail">
        <div class="short-hypothesis-flow">
          <div class="short-flow-block"><h4>Hypothesis · ${esc(opened)}</h4><p>${esc(idea.hypothesis || 'No hypothesis recorded.')}</p></div>
          <div class="short-flow-arrow" aria-hidden="true">→</div>
          <div class="short-flow-block"><h4>Observed · ${esc(outcome.latest_date || '—')}</h4><p><strong>${esc(outcome.hypothesis_state || 'open')}</strong> at $${price(outcome.latest_price)}. ${esc(latest.note || 'Add a check-in to compare evidence with the original claim.')}</p></div>
        </div>
        <div class="short-detail-grid">
          <div class="short-detail-card"><h4>What should break</h4><ul>${list(idea.catalysts)}</ul></div>
          <div class="short-detail-card"><h4>What proves us wrong</h4><ul>${list(idea.falsifiers)}</ul></div>
          <div class="short-detail-card"><h4>Evidence and next gate</h4><div class="short-sources">${sources || '<span class="form-hint">No sources linked.</span>'}</div><p class="form-hint" style="margin-top:8px">${esc(idea.research?.next_step || 'Define the next research gate.')}</p></div>
        </div>
        <details class="short-checkin"><summary>+ Record actual outcome</summary>
          <form class="short-checkin-form" data-short-checkin-form data-ticker="${esc(idea.ticker)}">
            <label>Date<input name="date" required type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
            <label>Price<input name="price" required type="number" min="0.0001" step="any" value="${esc(outcome.latest_price || idea.position?.opened_price || '')}"></label>
            <label>Hypothesis state<select name="state"><option value="open">Open</option><option value="strengthened">Strengthened</option><option value="weakened">Weakened</option><option value="falsified">Falsified</option><option value="realized">Realized</option><option value="closed_risk">Closed for risk</option></select></label>
            <label>What actually happened<textarea name="note" required rows="1" placeholder="Evidence, borrow, catalyst, or falsifier"></textarea></label>
            <button type="submit">Save check-in</button>
          </form>
        </details>
        <button type="button" class="short-remove" data-short-remove="${esc(idea.ticker)}">Hide in this browser</button>
      </div>
    </details>`;
  }
  function render(payload) {
    const maps = { frameworks: frameworkMap(payload), payload };
    const saved = read(FILTER_KEY, { query: '', framework: 'all', stage: 'all' });
    const selected = read(SELECTED_KEY, '');
    const candidates = getCandidates(payload).filter(row => {
      const hay = `${row.ticker} ${row.security_name} ${row.hypothesis} ${row.origin || ''}`.toLowerCase();
      const stageOk = saved.stage === 'all' || row.stage === saved.stage;
      return (!saved.query || hay.includes(saved.query.toLowerCase()))
        && stageOk
        && matchesFramework(row, saved.framework, payload.frameworks);
    });
    const positions = getPositions(payload).filter(row => {
      const hay = `${row.ticker} ${row.security_name} ${row.hypothesis}`.toLowerCase();
      const stageOk = saved.stage === 'all' || row.stage === saved.stage;
      return (!saved.query || hay.includes(saved.query.toLowerCase()))
        && stageOk
        && matchesFramework(row, saved.framework, payload.frameworks);
    });
    const selectedRow = getCandidates(payload).find(row => row.ticker === selected) || null;
    const summary = payload.summary || {};
    const stages = ['all', 'lead', 'researching', 'ic', 'live', 'closed', 'rejected'];
    return `<div class="short-alpha-header">
      <div><div class="short-alpha-kicker">Short Alpha</div><h2>Frameworks, names that fit, and the open book</h2><p>Every lens from the short library, every name that fits one, and the positions we have actually borrowed. A publisher hit is a lead. It is not a thesis.</p></div>
      <div class="short-alpha-rail"><span>Framework</span><i></i><span>Name</span><i></i><span>Position</span></div>
    </div>
    <div class="short-alpha-summary">
      <div class="short-alpha-stat"><span>Names</span><strong>${summary.candidate_count ?? candidates.length}</strong><small>${summary.lead_count ?? 0} leads</small></div>
      <div class="short-alpha-stat"><span>Open book</span><strong>${summary.position_count ?? positions.length}</strong><small>borrowed shorts</small></div>
      <div class="short-alpha-stat"><span>Research complete</span><strong>${summary.research_complete_count ?? 0}/${summary.position_count ?? positions.length}</strong><small>artifact gate, not an IC decision</small></div>
      <div class="short-alpha-stat"><span>Unscored lenses</span><strong>${(summary.unscored_frameworks || []).length}</strong><small>no name has been tagged</small></div>
    </div>
    <section class="short-section"><h3 class="short-section-title">Frameworks</h3>${renderFrameworkBoard(payload, saved.framework)}</section>
    <div class="short-alpha-toolbar">
      <input class="search" data-short-search placeholder="Search ticker, name, or thesis…" value="${esc(saved.query)}" aria-label="Search short names">
      <select class="short-alpha-filter" data-short-framework aria-label="Filter by short framework"><option value="all">All frameworks</option>${frameworkOptions(payload, saved.framework)}</select>
      <select class="short-alpha-filter" data-short-stage aria-label="Filter by stage">${stages.map(stage => `<option value="${stage}" ${saved.stage === stage ? 'selected' : ''}>${stage === 'all' ? 'All stages' : stage}</option>`).join('')}</select>
      <div class="short-alpha-actions"><button type="button" data-short-export>Export ledger</button><button type="button" data-short-reset title="Remove browser-only drafts and check-ins">Reset browser drafts</button></div>
    </div>
    ${renderAddForm(payload)}
    <section class="short-section"><h3 class="short-section-title">Names that fit <span>${candidates.length}</span></h3>
      <p class="short-alpha-note">Days to cover is FINRA context when the biotech file has the symbol. It is not a reason to short. Borrow stays pending until an IBKR export arrives. Missing is never zero.</p>
      ${renderNames(candidates, payload, selected)}
      ${renderDetail(selectedRow && candidates.some(row => row.ticker === selectedRow.ticker) ? selectedRow : null, payload)}
    </section>
    <section class="short-section"><h3 class="short-section-title">Open book <span>${positions.length}</span></h3>
      <div class="short-alpha-book">${positions.length ? positions.map(row => renderPosition(row, maps)).join('') : '<div class="short-alpha-empty">No borrowed shorts in this partition.</div>'}</div>
    </section>
    <p class="short-alpha-note">${esc(payload.methodology?.excluded || '')} ${esc(payload.methodology?.leads || '')}</p>`;
  }
  function mergedExport(payload) {
    const out = clone(payload);
    out.candidates = getCandidates(payload);
    out.positions = getPositions(payload);
    out.ideas = out.positions;
    out.exported_at = new Date().toISOString();
    return out;
  }
  function attach(container, payload, rerender) {
    const search = container.querySelector('[data-short-search]');
    const framework = container.querySelector('[data-short-framework]');
    const stage = container.querySelector('[data-short-stage]');
    const updateFilter = restoreFocus => {
      write(FILTER_KEY, {
        query: search.value.trim(),
        framework: framework.value,
        stage: stage.value,
      });
      rerender();
      if (restoreFocus) {
        const nextSearch = container.querySelector('[data-short-search]');
        if (nextSearch) { nextSearch.focus(); nextSearch.setSelectionRange(nextSearch.value.length, nextSearch.value.length); }
      }
    };
    search?.addEventListener('input', () => updateFilter(true));
    framework?.addEventListener('change', () => updateFilter(false));
    stage?.addEventListener('change', () => updateFilter(false));
    container.querySelectorAll('[data-short-framework-card]').forEach(button => button.addEventListener('click', () => {
      const id = button.dataset.shortFrameworkCard;
      const current = read(FILTER_KEY, { query: search.value.trim(), framework: 'all', stage: stage.value });
      current.framework = current.framework === id ? 'all' : id;
      current.query = search.value.trim();
      current.stage = stage.value;
      write(FILTER_KEY, current);
      rerender();
    }));
    const selectTicker = ticker => {
      write(SELECTED_KEY, ticker);
      rerender();
    };
    container.querySelectorAll('[data-short-select]').forEach(row => {
      row.addEventListener('click', () => selectTicker(row.dataset.shortSelect));
      row.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectTicker(row.dataset.shortSelect);
        }
      });
    });
    container.querySelector('[data-short-add-form]')?.addEventListener('submit', event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const ticker = String(form.get('ticker') || '').trim().toUpperCase();
      const sharesRaw = String(form.get('shares') || '').trim();
      const shares = sharesRaw ? Number(sharesRaw) : 0;
      const openedRaw = String(form.get('opened_price') || '').trim();
      const openedPrice = openedRaw ? Number(openedRaw) : 0;
      const status = event.currentTarget.querySelector('[data-short-add-status]');
      if (!ticker) return;
      if ((payload.candidates || []).some(row => row.ticker === ticker) || (payload.positions || []).some(row => row.ticker === ticker)) {
        if (status) status.textContent = `${ticker} is already in the repository ledger.`;
        return;
      }
      if (sharesRaw && !(shares > 0 && openedPrice > 0)) {
        if (status) status.textContent = 'A borrowed short needs a share count and an opened price.';
        return;
      }
      const frameworkId = String(form.get('framework'));
      const sourceUrl = String(form.get('source_url') || '').trim();
      const today = new Date().toISOString().slice(0, 10);
      const draft = {
        ticker,
        security_name: String(form.get('security_name') || ticker),
        instrument_type: String(form.get('instrument_type') || 'operating_company'),
        stage: shares > 0 ? 'researching' : 'lead',
        origin: 'browser_draft',
        frameworks: [frameworkId],
        primary_framework: frameworkId,
        effective_frameworks: [frameworkId],
        hypothesis: String(form.get('hypothesis') || ''),
        catalysts: [],
        falsifiers: [],
        research: { status: 'browser_draft', ic: 'not_ready', next_step: 'Promote the exported draft into candidates.json.' },
        sources: sourceUrl ? [{ type: String(form.get('source_type') || 'internal_analysis'), label: 'Initial source', url: sourceUrl }] : [],
        gates: { path_and_timing: 'unscored', issuer_retaliation: 'unscored' },
        gate_hits: [],
        furnace_hits: [],
        borrow: { status: 'pending', source: 'IBKR borrow feed', message: 'Awaiting the next IBKR borrow refresh.' },
        crowding: null,
        artifact_status: { completion_pct: 0 },
        has_position: shares > 0,
      };
      if (shares > 0) {
        draft.position = { shares: -Math.abs(shares), opened_price: openedPrice, opened_date: today, split_adjustment_factor: 1, split_adjusted_open_price: openedPrice };
        draft.check_ins = [{ date: today, price: openedPrice, hypothesis_state: 'open', note: 'Browser draft baseline.' }];
        draft.outcome = { latest_date: today, latest_price: openedPrice, hypothesis_state: 'open', check_in_count: 1 };
      }
      const custom = read(CUSTOM_KEY, []).filter(row => row.ticker !== ticker);
      custom.push(draft);
      write(CUSTOM_KEY, custom);
      rerender();
    });
    container.querySelectorAll('[data-short-checkin-form]').forEach(node => node.addEventListener('submit', event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const ticker = event.currentTarget.dataset.ticker;
      const overlays = read(CHECKINS_KEY, {});
      overlays[ticker] = overlays[ticker] || [];
      overlays[ticker].push({ date: String(form.get('date')), price: Number(form.get('price')), hypothesis_state: String(form.get('state')), note: String(form.get('note')) });
      write(CHECKINS_KEY, overlays);
      rerender();
    }));
    container.querySelector('[data-short-export]')?.addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(mergedExport(payload), null, 2) + '\n'], { type: 'application/json' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `short-alpha-ledger-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    });
    container.querySelector('[data-short-reset]')?.addEventListener('click', () => {
      if (!window.confirm('Remove all browser-only Short Alpha drafts and check-ins? The repository ledger is unchanged.')) return;
      localStorage.removeItem(CUSTOM_KEY);
      localStorage.removeItem(CHECKINS_KEY);
      localStorage.removeItem(REMOVED_KEY);
      localStorage.removeItem(SELECTED_KEY);
      rerender();
    });
    container.querySelectorAll('[data-short-remove]').forEach(button => button.addEventListener('click', () => {
      const ticker = button.dataset.shortRemove;
      if (!window.confirm(`Hide ${ticker} in this browser? The repository ledger is unchanged. Reset browser drafts restores it.`)) return;
      write(REMOVED_KEY, [...new Set([...read(REMOVED_KEY, []), ticker])]);
      rerender();
    }));
  }
  global.ShortAlphaViz = { render, attach, getCandidates, getPositions };
})(window);
