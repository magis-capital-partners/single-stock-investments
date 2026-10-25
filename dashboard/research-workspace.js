/* Stock research workspace. Presentation only: published economics and authority stay upstream. */
(function (global) {
  'use strict';
  const tabs = [['overview', 'Overview'], ['valuation', 'Valuation'], ['business', 'Business & KPIs'], ['evidence', 'Evidence']];
  const states = new Map();
  let current = null;
  const number = value => value == null || value === '' || typeof value === 'boolean' || typeof value === 'object' ? null : Number.isFinite(Number(value)) ? Number(value) : null;
  const text = value => String(value ?? '').replace(/_/g, ' ');
  const validTab = value => tabs.some(([key]) => key === value) ? value : value === 'buyback' ? 'business' : 'overview';
  const pct = value => number(value) == null ? 'Unavailable' : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(value))}%`;
  const date = value => value ? String(value).slice(0, 10) : 'date missing';
  function decision(t) { return global.ValuationViz?.decisionOf(t) || t.valuation_decision || {}; }
  function metrics(t, limit = Infinity) {
    const rows = (t.kpi_trends?.metrics || []).filter(m => m.display === true && !m.artifact && !m.stale && !m.composite && m.tier !== 'excluded' && (m.points || []).filter(p => number(p.value) != null).length >= 2);
    const rank = m => (/revenue|fcf|operating_income|volume|contracts|subscription|organic/.test(m.metric || '') ? 0 : 1);
    return rows.slice().sort((a, b) => rank(a) - rank(b)).slice(0, limit);
  }
  function metricValue(m, value) {
    if (number(value) == null) return 'Unavailable';
    if (m.unit === '%' || /margin|yield|roe|roic|ratio/.test(m.metric || '')) return pct(Number(value) * (m.unit === '%' ? 1 : 100));
    return new Intl.NumberFormat(undefined, { notation: Math.abs(value) >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 2 }).format(value) + (m.unit ? ` ${m.unit}` : '');
  }
  function sparkline(m, h) {
    const points = (m.points || []).filter(p => number(p.value) != null);
    if (points.length < 2) return '';
    const dates = points.map(p => Date.parse(p.period));
    const dated = dates.every(Number.isFinite) && Math.max(...dates) > Math.min(...dates);
    const lo = Math.min(...points.map(p => Number(p.value))), hi = Math.max(...points.map(p => Number(p.value)));
    const coords = points.map((p, i) => `${8 + (dated ? (dates[i] - Math.min(...dates)) / (Math.max(...dates) - Math.min(...dates)) : i / (points.length - 1)) * 204},${50 - (hi === lo ? 0.5 : (Number(p.value) - lo) / (hi - lo)) * 40}`).join(' ');
    const desc = points.map(p => `${p.period}: ${metricValue(m, p.value)}`).join('; ');
    return `<svg class="rw-spark" viewBox="0 0 220 60" role="img" aria-label="${h.escapeHtml(`${m.label || m.metric}: ${desc}`)}"><title>${h.escapeHtml(desc)}</title><polyline points="${coords}" /></svg>`;
  }
  function sourceLink(ref, h) {
    if (!ref) return '';
    const url = /^https?:\/\//i.test(ref) ? ref : `https://github.com/${h.ghRepo || 'magis-capital-partners/single-stock-investments'}/blob/main/${String(ref).split('/').map(encodeURIComponent).join('/')}`;
    return h.linkHtml(url, 'Source');
  }
  function kpis(t, h, limit = Infinity, historical = false) {
    const cleared = new Set(metrics(t));
    const rows = historical ? (t.kpi_trends?.metrics || []).filter(m => !cleared.has(m) && !m.composite && !m.artifact && (m.points || []).filter(p => number(p.value) != null).length >= 2).slice(0,limit) : [...cleared].slice(0,limit);
    if (!rows.length) {
      if (historical) return '<p class="rw-empty">No additional historical KPI series. Cleared series are shown above.</p>';
      const observations = (t.compounder_monitor?.kpi_coverage || []).filter(m => m.status === 'current' && number(m.value) != null).slice(0,limit);
      if (observations.length) return `<div class="rw-kpis">${observations.map(m => `<article class="rw-kpi"><h4>${h.escapeHtml(text(m.kpi_id))}</h4><div class="rw-kpi-number">${new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:2}).format(Number(m.value))}</div><p>${h.escapeHtml(text(m.unit || 'unit unspecified'))}</p><p class="rw-meta">${h.escapeHtml(date(m.period))} · ${sourceLink(m.source?.ref,h)}</p><p class="rw-meta">Latest observation · trend unavailable</p></article>`).join('')}</div>`;
      return '<p class="rw-empty">No current, comparable KPI series is cleared for display. Operating-driver observations and gaps are retained in Business &amp; KPIs.</p>';
    }
    return `<div class="rw-kpis">${rows.map(m => `<article class="rw-kpi"><h4>${h.escapeHtml(m.label || m.metric)}</h4><div class="rw-kpi-number">${h.escapeHtml(metricValue(m, m.level_latest))}</div>${sparkline(m, h)}<p>${historical ? 'Historical series · not a current signal' : h.escapeHtml(text(m.direction || 'trend unavailable'))}${historical || number(m.growth_latest) == null ? '' : ` · ${pct(Number(m.growth_latest) * 100)} ${h.escapeHtml(m.basis || 'change')}`}</p><p class="rw-meta">${h.escapeHtml(date(m.latest_period))} · ${sourceLink(m.evidence_ref, h)}</p><p class="rw-meta">${h.escapeHtml(m.unit || 'Units not published; see source')}${historical ? (m.stale ? ' · stale' : ' · signal not cleared') : ''}</p><p class="rw-meta">${h.escapeHtml(m.human_summary || '')}</p></article>`).join('')}</div>`;
  }
  function range(t, h) {
    const d = decision(t), values = d.present_value_today_per_share || d.value_per_share || {};
    const price = number(d.price_per_share), low = number(values.low), base = number(values.base), high = number(values.high);
    const quote = v => h.fmtQuote(v, h.quoteUnitsOf(t));
    const zones = t.pricing_analysis?.buy_zones;
    const entries = zones?.status === 'available' ? (zones.zones || []).filter(z => number(z.price) != null) : [];
    let graphic = '<p class="rw-empty">Value range unavailable. Complete the ownership map and dated economics before using entry thresholds.</p>';
    if (low != null && base != null && high != null && low <= base && base <= high) {
      const nums = [low, base, high, price, ...entries.map(z => Number(z.price))].filter(v => v != null);
      const min = Math.min(...nums), max = Math.max(...nums), span = max - min || Math.abs(max) * .1 || 1;
      const pos = v => min === max ? 50 : 5 + 90 * (v - min) / span;
      graphic = `<div class="rw-ruler" role="img" aria-label="${h.escapeHtml(`Value low ${quote(low)}, base ${quote(base)}, high ${quote(high)}. Price ${quote(price)}.`)}"><div class="rw-ruler-line" style="left:${pos(low)}%;width:${pos(high) - pos(low)}%"></div>${[['low', low], ['base', base], ['high', high]].map(([label, value]) => `<span class="rw-ruler-dot ${label}" style="left:${pos(value)}%"></span>`).join('')}${price == null ? '' : `<span class="rw-ruler-price" style="left:${pos(price)}%" aria-hidden="true"></span>`}${entries.map(z => `<span class="rw-ruler-entry" style="left:${pos(Number(z.price))}%" aria-hidden="true"></span>`).join('')}</div><dl class="rw-range-labels">${[['Low', low], ['Base', base], ['High', high]].map(([label, value]) => `<div><dt>${label}</dt><dd>${quote(value)}</dd></div>`).join('')}</dl>`;
    }
    const ret = global.ValuationViz?.displayReturn(t) || { pct: null, label: 'Forward return', sub: d.forward_return_reason || 'Dated cash flows required' };
    return `<section class="rw-value"><div class="rw-value-heading"><h3>Price versus value</h3><span class="rw-meta">${h.escapeHtml(text(d.output_basis || 'basis unavailable'))}${d.provisional ? ' · provisional' : ''}</span></div><div class="rw-price"><span>Price <strong>${quote(price)}</strong></span><span class="rw-meta">${h.escapeHtml(date(d.dates?.price_as_of))} · listing currency</span></div>${graphic}<div class="rw-return"><span>Margin of safety <strong>${pct(d.margin_of_safety_pct?.base)}</strong></span><span>${h.escapeHtml(ret.label || 'Forward return')} <strong>${ret.pct == null ? 'Unavailable' : pct(ret.pct)}</strong>${ret.pct == null ? '' : ` · ${h.escapeHtml(String(d.horizon_years || 'unspecified'))}-year horizon`}</span></div><p class="rw-meta">${h.escapeHtml((ret.sub || '').includes('present_value_today') ? 'A present value is not a dated future cash flow; forward return is unavailable.' : ret.sub || '')}</p><p class="rw-meta">Model ${h.escapeHtml(date(d.dates?.model_as_of))} · Facts ${h.escapeHtml(date(d.dates?.latest_fact_as_of))} · Price ${h.escapeHtml(date(d.dates?.price_as_of))}</p>${entries.length ? `<p class="rw-meta">Research entry thresholds · owner review required: ${entries.map(z => `${h.escapeHtml(z.label)} ≤ ${quote(z.price)}`).join(' · ')}</p>` : ''}</section>`;
  }
  function scenarios(t, h) {
    const d = decision(t), bridge = t.compounder_monitor?.tci_return_bridge;
    const published = d.return_publishable ? d.forward_return_at_price_pct : null;
    const rows = [['Bear', 'low', 'bear'], ['Base', 'base', 'base'], ['Bull', 'high', 'bull']].map(([label, key, research]) => ({label, value: number(published?.[key] ?? (!published ? bridge?.scenarios?.[research]?.exact_irr_pct : null))}));
    if (!rows.some(r => r.value != null)) return '<p class="rw-empty">Scenario returns are unavailable until dated forward economics are supplied.</p>';
    const research = !published, horizon = research ? bridge.horizon_years : d.horizon_years;
    const min = Math.min(0, ...rows.filter(r => r.value != null).map(r => r.value)), max = Math.max(0, ...rows.filter(r => r.value != null).map(r => r.value));
    const span = max - min || 1, zero = 100 * (0 - min) / span;
    return `<section class="rw-scenarios"><h3>${research ? 'Research scenario diagnostic' : 'Forward-return scenarios'}</h3><p class="rw-meta">${h.escapeHtml(String(horizon || 'Unspecified'))}-year horizon · percent per year${research ? ' · research only; capital action blocked' : ''} · ${h.escapeHtml(date(research ? bridge.model_as_of : d.dates?.model_as_of))}</p>${rows.map(r => `<div class="rw-scenario"><span>${r.label}</span><div class="rw-scenario-track">${r.value == null ? '' : `<span style="left:${Math.min(zero, 100 * (r.value - min) / span)}%;width:${100 * Math.abs(r.value) / span}%"></span>`}</div><strong>${pct(r.value)}</strong></div>`).join('')}</section>`;
  }
  function status(t,h) {
    const d = decision(t), committee = t.valuation_workbench?.committee || {}, e = h.escapeHtml;
    const meta = global.ValuationViz?.modelLevelMeta(d.model_level,d.status) || {label:text(d.model_level || d.status || 'unmodeled'),cls:'badge-warn'};
    const owner = committee.owner_status || 'pending';
    return `<div class="rw-status"><span>Stance <strong>${e(t.classification?.stance || 'unassigned')}</strong></span>${t.human_review?.approved_stance ? `<span>Owner stance <strong>${e(t.human_review.approved_stance)}</strong></span>` : ''}<span>Readiness <strong class="badge ${meta.cls}">${e(meta.label)}</strong></span><span>Owner <strong>${e(text(owner))}</strong></span></div>`;
  }
  function friendlyAction(value) {
    const raw = String(value || 'Review primary evidence and establish a dated valuation.');
    if (/Replace stale or unbound|Refresh.*isolated/i.test(raw)) return 'Update the independent review with the latest evidence.';
    if (/Complete.*hash-bound|isolated outputs/i.test(raw)) return 'Complete the independent review documents.';
    if (/Freeze the evidence packet/i.test(raw)) return 'Prepare the evidence and assign independent reviewers.';
    if (/Gather.*primary evidence|proof-complete component/i.test(raw)) return 'Collect the primary sources and complete the valuation model.';
    return raw;
  }
  function overview(t, h) {
    const d = decision(t), committee = t.valuation_workbench?.committee || {}, e = h.escapeHtml;
    const meta = global.ValuationViz?.modelLevelMeta(d.model_level, d.status) || {label: text(d.model_level || d.status || 'unmodeled'), cls:'badge-warn'};
    const owner = committee.owner_status || 'pending';
    const falsifiers = t.valuation_workbench?.valuation?.monitoring?.falsifiers || [];
    const risk = falsifiers[0];
    const riskText = typeof risk === 'string' ? risk : risk?.falsifier || risk?.metric || t.investment_committee?.strongest_dissent || 'No falsifier recorded. Review the thesis and evidence gaps.';
    const changes = (h.developments || []).slice(0, 3);
    const blockers = [...new Set([d.decision_eligibility?.reason || d.model_level_reason, ...(t.pricing_analysis?.buy_zones?.blockers || []).slice(0,1)].filter(Boolean))];
    return `<section class="rw-next"><div><h3>Next action</h3><p>${e(friendlyAction(d.next_action || d.next_gap_question))}</p>${blockers.length ? `<p class="rw-meta">${e(blockers.join(' '))}</p>` : ''}</div><button type="button" data-rw-go="evidence">Review evidence${Number(d.critical_gap_count) > 0 ? ` · ${Number(d.critical_gap_count)} critical` : ''}</button></section>${t.human_review?.override_reason ? `<p class="rw-review"><strong>Owner review:</strong> ${e(t.human_review.override_reason)}</p>` : ''}${range(t,h)}<div class="rw-overview-bottom"><section><div class="rw-value-heading"><h3>Operating pulse</h3><button type="button" class="rw-text-button" data-rw-go="business">All KPIs</button></div>${kpis(t,h,3)}</section><section class="rw-brief"><h3>What breaks the case</h3><p>${e(riskText)}</p><h3>Recent changes</h3>${changes.length ? `<ol class="rw-timeline">${changes.map(row => `<li><time>${e(row.date || 'Undated')}</time><span>${row.url ? h.linkHtml(row.url,row.label) : e(row.label || '')}</span></li>`).join('')}</ol>` : '<p class="rw-empty">No dated developments recorded.</p>'}</section></div>`;
  }
  function section(label, html, open = false) { return html ? `<details class="rw-section"${open ? ' open' : ''}><summary>${label}</summary><div class="rw-section-body">${html}</div></details>` : ''; }
  function normalize(panel) {
    panel.querySelectorAll('details[data-buyback-detail]').forEach(el => { if (!el.dataset.rwInitialized) { el.open = false; el.dataset.rwInitialized = 'true'; } });
    // Workbench's nested tab system becomes a single, fully retained audit document.
    panel.querySelectorAll('.workbench-tabs').forEach(el => el.remove());
    panel.querySelectorAll('[data-workbench-page]').forEach(el => {
      el.classList.remove('workbench-page'); el.classList.add('rw-audit-page');
      el.removeAttribute('role'); el.removeAttribute('aria-labelledby');
      const title = document.createElement('h4'); title.textContent = text(el.dataset.workbenchPage); el.removeAttribute('data-workbench-page'); el.prepend(title);
    });
    // Only the tab's section disclosures remain collapsible; evidence inside is readable in one layer.
    [...panel.querySelectorAll('details')].reverse().forEach(el => {
      if (!el.parentElement.closest('details')) return;
      const replacement = document.createElement('section');
      [...el.attributes].forEach(a => { if (a.name !== 'open') replacement.setAttribute(a.name,a.value); });
      const summary = el.querySelector(':scope > summary');
      if (summary) { const heading = document.createElement('h4'); heading.textContent = summary.textContent; summary.replaceWith(heading); }
      replacement.append(...el.childNodes); el.replaceWith(replacement);
    });
    panel.querySelectorAll('img').forEach(img => { img.loading = 'lazy'; });
  }
  function scrollToTarget(root, target) {
    if (matchMedia('(max-width:720px)').matches) { target.scrollIntoView({block:'start'}); return; }
    const header = root.querySelector('.rw-header');
    root.scrollTo({top:Math.max(0,target.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - (header?.offsetHeight || 0)),behavior:'instant'});
  }
  function mount(root, t, h, renderers, options = {}) {
    root._rwObserver?.disconnect();
    const previous = current?.ticker === t.ticker ? current : null;
    const saved = states.get(t.ticker) || {tab:'overview', scroll:{}};
    const requested = options.tab || previous?.tab || saved.tab;
    const initial = validTab(requested);
    current = {ticker:t.ticker, tab:initial, root, activate:null};
    root.classList.add('research-workspace');
    root.innerHTML = `<header class="rw-header"><div class="rw-header-top"><div><h2>${h.escapeHtml(t.display_ticker || t.ticker)} <span>${h.escapeHtml(t.company || '')}</span></h2><p class="rw-meta">${h.escapeHtml(t.exchange || t.market || '')} · ${h.escapeHtml(t.quote_ticker || t.ticker)}${t.valuation_tier?.label ? ` · ${h.escapeHtml(t.valuation_tier.label)}` : ''}</p></div><button type="button" data-detail-close>Back to coverage</button></div><p class="rw-thesis">${h.escapeHtml(t.one_line_thesis || 'Investment thesis not yet recorded.')}</p>${status(t,h)}${h.watch ? `<p class="rw-watch"><strong>${h.escapeHtml(h.watch.title)}</strong> <button type="button" class="rw-text-button" data-rw-go="business">Watch details</button></p>` : ''}${h.headerExtras || ''}<nav class="rw-tabs" role="tablist" aria-label="Stock research">${tabs.map(([id,label]) => `<button type="button" id="rw-tab-${id}" role="tab" data-rw-tab="${id}" aria-controls="rw-panel-${id}" aria-selected="false" tabindex="-1">${label}</button>`).join('')}</nav></header>${tabs.map(([id]) => `<section class="rw-panel" id="rw-panel-${id}" role="tabpanel" aria-labelledby="rw-tab-${id}" hidden></section>`).join('')}<p class="rw-sr" aria-live="polite" data-rw-announcement></p>`;
    const rendered = new Set();
    const activate = (value, focus = false, route = true) => {
      const id = validTab(value), state = states.get(t.ticker) || saved;
      if (current.tab && rendered.has(current.tab)) state.scroll[current.tab] = root.scrollTop;
      current.tab = id; state.tab = id; states.set(t.ticker,state);
      root.querySelectorAll('[data-rw-tab]').forEach(btn => { const selected = btn.dataset.rwTab === id; btn.setAttribute('aria-selected',String(selected)); btn.tabIndex = selected ? 0 : -1; if (selected && focus) btn.focus(); });
      root.querySelectorAll('.rw-panel').forEach(panel => { panel.hidden = panel.id !== `rw-panel-${id}`; });
      const panel = root.querySelector(`#rw-panel-${id}`);
      if (!rendered.has(id)) {
        panel.innerHTML = id === 'overview' ? overview(t,h) : renderers[id]?.() || '<p class="rw-empty">No research recorded in this view.</p>';
        normalize(panel);
        if (state.open?.[id]) panel.querySelectorAll(':scope > details').forEach(el => { el.open = state.open[id].includes(el.querySelector(':scope > summary')?.textContent); });
        rendered.add(id); options.afterRender?.(id,panel);
      }
      root.scrollTop = state.scroll[id] || 0;
      root.querySelector('[data-rw-announcement]').textContent = `${t.display_ticker || t.ticker}: ${tabs.find(([key]) => key === id)[1]}`;
      if (route) options.onTab?.(id);
    };
    current.activate = activate;
    root.addEventListener('click', handleClick);
    root.addEventListener('keydown', handleKeys);
    function handleClick(event) {
      const control = event.target.closest('[data-rw-tab], [data-rw-go], [data-open-two-phase]');
      if (control && root.contains(control)) {
        activate(control.hasAttribute('data-open-two-phase') ? 'business' : control.dataset.rwTab || control.dataset.rwGo, false);
        if (control.hasAttribute('data-open-two-phase')) { const target = root.querySelector('#two-phase-watch'); if (target) { target.open = true; scrollToTarget(root,target); } }
      }
    }
    function handleKeys(event) {
      const tab = event.target.closest('[data-rw-tab]'); if (!tab) return;
      const index = tabs.findIndex(([id]) => id === tab.dataset.rwTab);
      const next = event.key === 'ArrowRight' ? (index+1)%tabs.length : event.key === 'ArrowLeft' ? (index+tabs.length-1)%tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : null;
      if (next != null) { event.preventDefault(); activate(tabs[next][0],true); }
    }
    // Root is reused across selections; remove old delegated listeners before attaching a new mount.
    if (root._rwCleanup) root._rwCleanup();
    root._rwCleanup = () => { root.removeEventListener('click',handleClick); root.removeEventListener('keydown',handleKeys); };
    activate(initial,false,false);
    let pending = false;
    root._rwObserver = new MutationObserver(() => {
      if (pending) return;
      pending = true;
      queueMicrotask(() => { root.querySelectorAll('.rw-panel').forEach(normalize); pending = false; });
    });
    root._rwObserver.observe(root, { childList: true, subtree: true });
    return current;
  }
  global.ResearchWorkspace = {number, metrics, metricValue, friendlyAction, scrollToTarget, range, scenarios, kpis, section, overview, normalize, mount, validTab, activeTab:()=>current?.tab || 'overview', activate:(tab)=>current?.activate(tab), rememberScroll:()=>{ if(current?.root.querySelector('.rw-panel:not([hidden])')){ const state=states.get(current.ticker); if(state) { state.scroll[current.tab]=current.root.scrollTop; state.open ||= {}; state.open[current.tab]=[...current.root.querySelectorAll('.rw-panel:not([hidden]) > details[open] > summary')].map(el=>el.textContent); } } }};
  if (typeof module !== 'undefined') module.exports = global.ResearchWorkspace;
})(typeof window !== 'undefined' ? window : globalThis);
