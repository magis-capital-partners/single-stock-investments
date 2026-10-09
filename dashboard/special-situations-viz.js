(function (global) {
  'use strict';

  const state = {
    lane: 'all',
    query: '',
    focus: '',
    openId: '',
    showDiscovery: false,
    showHistory: false,
    gatesOpen: false,
  };

  const esc = (value) => String(value == null ? '' : value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  function laneLabel(payload, id) {
    const lane = (payload.lanes || []).find((row) => row.id === id);
    return lane ? lane.label : String(id || '').replaceAll('_', ' ');
  }

  function matchesLane(row, lane) {
    if (!lane || lane === 'all') return true;
    return (row.lanes || [row.lane]).includes(lane);
  }

  function matchesQuery(row) {
    if (!state.query) return true;
    const hay = `${row.ticker} ${row.company} ${row.what} ${row.ends_label} ${row.lane}`.toLowerCase();
    return hay.includes(state.query.toLowerCase());
  }

  function selectRows(rows, lane) {
    return (rows || []).filter((row) => matchesLane(row, lane) && matchesQuery(row));
  }

  function evidenceCell(row) {
    if (!row.evidence_url) return esc(row.evidence_label || '—');
    return `<a href="${esc(row.evidence_url)}" target="_blank" rel="noopener">${esc(row.evidence_label || 'Source')}</a>`;
  }

  function rowHtml(row, payload) {
    const focus = state.focus && row.ticker === state.focus ? ' is-focus' : '';
    const open = state.openId === row.id;
    const lanes = (row.lanes || [row.lane]).map((id) => laneLabel(payload, id)).join(' · ');
    const detail = open ? `<tr class="situation-detail${focus}"><td colspan="6">
      <p>${esc(row.what)}</p>
      <p>${esc(row.company || '')}${row.headline_count > 1 ? ` · ${row.headline_count} headlines in the window` : ''}</p>
      <p><strong>Ends.</strong> ${esc(row.ends_label || 'Not stated')}</p>
      <p><strong>Next.</strong> ${esc(row.next || '')}</p>
      <p><strong>Annualized spread.</strong> ${row.annualized_spread == null ? 'Not stated. Shown only when a filing states it.' : esc(row.annualized_spread)}</p>
      <p><strong>Source.</strong> ${evidenceCell(row)} · ${esc(row.evidence_kind || '')}</p>
    </td></tr>` : '';
    return `<tr class="${focus.trim()}" data-situation-id="${esc(row.id)}">
      <td><button type="button" class="idea-open" data-situation-open="${esc(row.id)}">${esc(row.ticker || '—')}</button></td>
      <td>${esc(row.what)}</td>
      <td><span class="idea-type">${esc(lanes)}</span></td>
      <td>${esc(row.ends_label || '—')}</td>
      <td>${evidenceCell(row)}</td>
      <td>${esc(row.next || '')}</td>
    </tr>${detail}`;
  }

  function render(payload, options) {
    const opts = options || {};
    if (opts.lane) state.lane = opts.lane;
    if (Object.prototype.hasOwnProperty.call(opts, 'focus')) state.focus = opts.focus || '';
    if (opts.gatesOpen) state.gatesOpen = true;
    const doc = payload || {};
    const counts = (doc.counts && doc.counts.ranked) || {};
    const ranked = selectRows(doc.rows, state.lane);
    const discovery = selectRows(doc.discovery, state.lane);
    const history = selectRows(doc.history, state.lane);
    if (state.focus && !ranked.some((row) => row.ticker === state.focus) && discovery.some((row) => row.ticker === state.focus)) {
      state.showDiscovery = true;
    }
    const shownDiscovery = state.showDiscovery ? discovery : discovery.slice(0, 12);
    const chips = [{ id: 'all', label: 'All', count: (doc.rows || []).length }].concat(
      (doc.lanes || []).map((lane) => ({ id: lane.id, label: lane.label, count: counts[lane.id] || 0 })),
    );
    const gates = state.lane === 'warrants'
      ? `<details class="situation-gates" data-situation-gates ${state.gatesOpen ? 'open' : ''}><summary>Contract gates</summary><div data-situation-gates-host></div></details>`
      : '';
    const historyBlock = history.length
      ? `<p class="form-hint"><label><input type="checkbox" data-situation-history ${state.showHistory ? 'checked' : ''}/> Show ${history.length} ended contract${history.length === 1 ? '' : 's'}</label></p>${state.showHistory ? `<div class="ideas-table-wrap"><table class="ideas-table"><tbody>${history.map((row) => rowHtml(row, doc)).join('')}</tbody></table></div>` : ''}`
      : '';
    const discoveryBlock = discovery.length
      ? `<details class="situation-discovery" ${state.showDiscovery ? 'open' : ''}><summary>Unverified candidates · ${discovery.length}. Terms unknown. Not a position.</summary>
        <div class="ideas-table-wrap"><table class="ideas-table"><tbody>${shownDiscovery.map((row) => rowHtml(row, doc)).join('')}</tbody></table></div>
        ${discovery.length > 12 ? `<button type="button" class="filter-btn" data-situation-more>${state.showDiscovery ? 'Show fewer' : `Show all ${discovery.length}`}</button>` : ''}
      </details>`
      : '';
    return `<div class="ideas-shell">
      <header class="ideas-header"><div>
        <div class="warrant-kicker">Special situations</div>
        <h2>The situation ends.</h2>
        <p>${esc(doc.definition || '')}</p>
      </div><span class="ideas-asof">As of ${esc((doc.generated_at || '').slice(0, 10) || '—')}</span></header>
      <div class="screen-switcher" aria-label="Special situation lanes">${chips.map((chip) => `<button type="button" class="${state.lane === chip.id ? 'active' : ''}" data-situation-lane="${esc(chip.id)}">${esc(chip.label)} · ${chip.count}</button>`).join('')}</div>
      <div class="warrant-toolbar">
        <input class="search" data-situation-search aria-label="Search special situations" placeholder="Search ticker, company, or situation…" value="${esc(state.query)}">
      </div>
      <section class="ideas-surface"><div class="ideas-surface-head"><strong>${ranked.length} ranked</strong><span>Filing before headline · click a ticker for the clock and the next step</span></div>
        <div class="ideas-table-wrap"><table class="ideas-table"><thead><tr><th>Ticker</th><th>What</th><th>Lane</th><th>Ends</th><th>Evidence</th><th>Next</th></tr></thead><tbody>${ranked.length ? ranked.map((row) => rowHtml(row, doc)).join('') : '<tr><td colspan="6">Nothing ranked in this lane. Unverified candidates, when the screen has them, stay below.</td></tr>'}</tbody></table></div>
      </section>
      ${historyBlock}
      ${discoveryBlock}
      ${gates}
      ${doc.error ? `<p class="form-hint">${esc(doc.error)}</p>` : ''}
    </div>`;
  }

  function attach(container, payload, hooks) {
    const refresh = () => {
      if (hooks && hooks.onChange) hooks.onChange();
    };
    container.querySelectorAll('[data-situation-lane]').forEach((button) => {
      button.addEventListener('click', () => {
        state.lane = button.dataset.situationLane;
        state.openId = '';
        if (hooks && hooks.onLane) hooks.onLane(state.lane);
        else refresh();
      });
    });
    const search = container.querySelector('[data-situation-search]');
    search?.addEventListener('input', (event) => {
      state.query = event.target.value;
      refresh();
      requestAnimationFrame(() => container.querySelector('[data-situation-search]')?.focus());
    });
    container.querySelectorAll('[data-situation-open]').forEach((button) => {
      button.addEventListener('click', () => {
        state.openId = state.openId === button.dataset.situationOpen ? '' : button.dataset.situationOpen;
        refresh();
      });
    });
    container.querySelector('[data-situation-more]')?.addEventListener('click', () => {
      state.showDiscovery = !state.showDiscovery;
      refresh();
    });
    container.querySelector('[data-situation-history]')?.addEventListener('change', (event) => {
      state.showHistory = event.target.checked;
      refresh();
    });
    container.querySelector('[data-situation-gates]')?.addEventListener('toggle', (event) => {
      state.gatesOpen = event.target.open;
    });
    const focusRow = container.querySelector('tr.is-focus');
    if (focusRow) focusRow.scrollIntoView({ block: 'nearest' });
  }

  global.SpecialSituationsViz = { render, attach };
})(window);
