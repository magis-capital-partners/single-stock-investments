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
    const hay = `${row.ticker} ${row.company} ${row.what} ${row.ends_label} ${row.lane} ${row.terms_summary || ''}`.toLowerCase();
    return hay.includes(state.query.toLowerCase());
  }

  const CAPTION_LANES = new Set(['all', 'spinoffs', 'split_offs', 'forced_sellers']);

  function isNum(value) {
    return value != null && value !== '' && Number.isFinite(Number(value));
  }

  function pct(value, digits) {
    if (!isNum(value)) return '—';
    const n = Number(value);
    return `${n > 0 ? '+' : ''}${n.toFixed(digits == null ? 1 : digits)}%`;
  }

  /** A 0..1 factor as an unsigned percent: 0.25 -> "25%". */
  function factorPct(value) {
    return isNum(value) ? `${(Number(value) * 100).toFixed(0)}%` : '—';
  }

  function num(value, digits) {
    return isNum(value) ? Number(value).toFixed(digits == null ? 4 : digits) : '—';
  }

  function usd(value) {
    if (!isNum(value)) return '—';
    const n = Number(value);
    return `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
  }

  function metric(key, value, title) {
    return `<div class="situation-term"${title ? ` title="${esc(title)}"` : ''}><div class="k">${esc(key)}</div><div class="v">${value}</div></div>`;
  }

  /**
   * Exchange terms for a split-off row (`row.spread`, README "Dashboard
   * payload"). Only drawn when the builder produced a spread, which it does
   * only from a filed formula and quotes inside the 7-day staleness window.
   */
  function exchangeTermsHtml(spread) {
    if (!spread) return '';
    const s = spread;
    const odd = s.odd_lot_payoff_per_99 || {};
    const pro = s.proration || {};
    const hold = s.holder_expected_gain_pct || {};
    const basis = s.basis ? String(s.basis).replaceAll('_', ' ') : 'basis not stated';
    const asOf = s.as_of ? ` · quotes ${esc(s.as_of)}` : '';
    const prices = isNum(s.parent_price) || isNum(s.spinco_price)
      ? ` · parent ${esc(num(s.parent_price, 2))} / spinco ${esc(num(s.spinco_price, 2))}`
      : '';
    const prorationBasis = pro.basis ? ` (${String(pro.basis).replaceAll('_', ' ')})` : '';
    const holder = isNum(hold.base)
      ? metric('Holder gain (low / base / high)', `${esc(pct(hold.low))} / ${esc(pct(hold.base))} / ${esc(pct(hold.high))}`, 'Expected gain for a tendering holder after proration')
      : '';
    return `<div class="situation-terms-block">
      <div class="situation-terms-head"><strong>Exchange terms.</strong> <span>${esc(basis)}${asOf}${prices}</span></div>
      <div class="situation-terms">
        ${metric('Implied ratio', esc(num(s.implied_ratio, 4)), 'SpinCo shares per parent share at the formula and current quotes')}
        ${metric('Realized discount', esc(pct(s.realized_discount_pct, 2)), 'Discount the formula delivers at current quotes')}
        ${metric('Upper limit binding', s.upper_limit_binding == null ? '—' : (s.upper_limit_binding ? '<span class="badge badge-warn">yes</span>' : 'no'), 'When the limit binds, the discount is less than the filed percentage')}
        ${metric('Days to settlement', esc(isNum(s.days_to_settlement) ? String(Math.round(Number(s.days_to_settlement))) : '—'))}
        ${metric('Annualized spread', esc(pct(s.annualized_spread_pct, 1)), 'Realized discount annualized over days to settlement')}
        ${metric('Odd-lot payoff / 99 sh', `${esc(usd(odd.gain_usd))}${isNum(odd.gain_pct) ? ` <span class="muted">(${esc(pct(odd.gain_pct, 2))})</span>` : ''}`, 'Odd lots (99 shares or fewer) are accepted before proration')}
        ${metric('Proration (low / base / high)', `${esc(factorPct(pro.low))} / ${esc(factorPct(pro.base))} / ${esc(factorPct(pro.high))}${esc(prorationBasis)}`, 'Share of tendered parent shares accepted')}
        ${holder}
      </div>
    </div>`;
  }

  /** Compact "Who must sell" line for a desk row (`row.flow`). */
  function whoMustSellHtml(flow) {
    if (!flow) return '';
    const f = flow;
    const window = f.window_start && f.window_end
      ? `${f.window_start} → ${f.window_end}`
      : (f.window_end ? `through ${f.window_end}` : (f.window_start ? `from ${f.window_start}` : 'window not stated'));
    const conf = f.confidence ? String(f.confidence).replaceAll('_', ' ') : 'confidence not stated';
    const legs = global.SeparationsViz && Array.isArray(f.legs) && f.legs.length
      ? global.SeparationsViz.renderFlowLegs(f, { escapeHtml: esc })
      : '';
    return `<div class="situation-terms-block">
      <div class="situation-terms-head"><strong>Who must sell.</strong> <span class="muted">Negative % float = net forced selling. Research only.</span></div>
      <div class="situation-terms">
        ${metric('% of float (base)', esc(pct(f.pct_of_float_base, 1)))}
        ${metric('Days of ADV', esc(isNum(f.pct_of_adv_days) ? Number(f.pct_of_adv_days).toFixed(1) : '—'))}
        ${metric('Window', esc(window))}
        ${metric('Confidence', esc(conf))}
      </div>
      ${legs}
    </div>`;
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
      ${row.terms_summary ? `<p class="situation-terms-summary">${esc(row.terms_summary)}</p>` : ''}
      <p>${esc(row.company || '')}${row.headline_count > 1 ? ` · ${row.headline_count} headlines in the window` : ''}</p>
      ${row.one_number ? `<p><strong>The number.</strong> ${esc(row.one_number)}</p>` : ''}
      ${row.research_only ? '<p>Research only. Not a position.</p>' : ''}
      <p><strong>Ends.</strong> ${esc(row.ends_label || 'Not stated')}</p>
      <p><strong>Next.</strong> ${esc(row.next || '')}</p>
      <p><strong>Annualized spread.</strong> ${row.annualized_spread == null ? 'Not stated. Shown only when a filing states it.' : esc(row.annualized_spread)}</p>
      ${exchangeTermsHtml(row.spread)}
      ${row.buyback_event && global.BuybackViz ? global.BuybackViz.renderEventDetails(row.buyback_event) : ''}
      ${whoMustSellHtml(row.flow)}
      <p><strong>Source.</strong> ${evidenceCell(row)} · ${esc(row.evidence_kind || '')}</p>
    </td></tr>` : '';
    return `<tr class="${focus.trim()}" data-situation-id="${esc(row.id)}">
      <td><button type="button" class="idea-open" data-situation-open="${esc(row.id)}">${esc(row.ticker || '—')}</button></td>
      <td>${esc(row.what)}${row.one_number ? ` <span class="mono">${esc(row.one_number)}</span>` : ''}${row.research_only ? ' <span class="idea-type">Research only</span>' : ''}</td>
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
    const mentionRows = state.lane === 'buyback_events' ? (doc.buyback_mentions || []).filter(row => !state.query || `${row.ticker} ${row.line}`.toLowerCase().includes(state.query.toLowerCase())) : [];
    const mentionBlock = mentionRows.length
      ? `<section class="ideas-surface"><div class="ideas-surface-head"><strong>Ordinary programs</strong><span>One line each. Not a situation row.</span></div><ul>${mentionRows.map((row) => `<li>${esc(row.ticker || '—')} · ${esc(row.filed || '')} · ${esc(row.line || '')}${row.url ? ` · <a href="${esc(row.url)}" target="_blank" rel="noopener">filing</a>` : ''}</li>`).join('')}</ul></section>`
      : '';
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
        ${doc.caption && CAPTION_LANES.has(state.lane) ? `<p class="situation-caption" data-situation-caption>${esc(doc.caption)}</p>` : ''}
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
      ${state.lane === 'buyback_events' ? `<p class="bb-notice">${doc.buyback_error ? esc(doc.buyback_error) : `Buyback evidence snapshot ${esc(doc.buyback_snapshot?.as_of || 'unavailable')}. Review items have unresolved terms, status, or size.`}</p>` : ''}
      ${mentionBlock}
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
    global.BuybackViz?.attachScenarios(container);
    const focusRow = container.querySelector('tr.is-focus');
    if (focusRow) focusRow.scrollIntoView({ block: 'nearest' });
  }

  global.SpecialSituationsViz = { render, attach };
})(window);
