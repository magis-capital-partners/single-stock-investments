(function(global) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const types = ['long','short','update','postmortem','special_situation','credit','private','unnamed','sector','macro','portfolio','factual_note'];
  const checks = {
    complete_document: 'Read the complete letter, including tables and footnotes',
    idea_coverage: 'Every substantive idea is accounted for',
    claim_accuracy: 'Arguments and attribution reconcile to evidence',
    numerical_accuracy: 'Figures, currencies, units and periods are accurate',
    original_writing: 'Writing is original and source overlap has been reviewed',
    historical_dates: 'Dates and historical context are supported',
  };
  const MACRO_TYPES = new Set(['macro', 'sector', 'portfolio']);
  const paragraphs = text => String(text || '').split(/\n\s*\n/).filter(Boolean).map(p => `<p>${escape(p)}</p>`).join('');
  const label = value => String(value || '').replace(/_/g, ' ');
  const period = letter => `${letter.reporting_period || 'Period unavailable'} · ${letter.letter_date ? `Letter dated ${letter.letter_date}` : 'Exact letter date unavailable'}`;

  function periodSortKey(val) {
    const s = String(val || '').trim();
    const m = s.match(/^(\d{4})Q([1-4])$/i);
    if (m) {
      const ends = { '1': '03-31', '2': '06-30', '3': '09-30', '4': '12-31' };
      return `${m[1]}-${ends[m[2]]}`;
    }
    return s;
  }

  function typeTone(ideaType) {
    const t = String(ideaType || '').toLowerCase();
    if (t === 'long') return 'long';
    if (t === 'short') return 'short';
    if (t === 'special_situation' || t === 'credit' || t === 'private') return 'special';
    if (t === 'postmortem') return 'warn';
    if (t === 'macro' || t === 'sector' || t === 'portfolio') return 'macro';
    return 'neutral';
  }

  function activityTone(activity) {
    const a = String(activity || '').toLowerCase();
    if (a === 'new' || a === 'add') return 'add';
    if (a === 'trim' || a === 'exit' || a === 'cover') return 'trim';
    if (a === 'short') return 'short';
    return 'neutral';
  }

  function badgeHtml(text, tone = 'neutral', extraClass = '') {
    if (!text) return '';
    return `<span class="fl-badge fl-badge--${escape(tone)}${extraClass ? ' ' + extraClass : ''}">${escape(text)}</span>`;
  }

  async function api(args, payload) {
    const response = await fetch('/api/fund-letters?' + new URLSearchParams(args), {
      cache: 'no-store',
      credentials: 'same-origin',
      ...(payload ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) } : {}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error([result.error, ...(result.errors || [])].filter(Boolean).join(' '));
    return result;
  }

  const states = new WeakMap();

  async function mount(root, options = {}) {
    states.get(root)?.dispose();
    const embedded = Boolean(options.embedded);
    let params = new URLSearchParams(embedded ? sessionStorage.getItem('fl-reader-state') || '' : location.search);
    let funds = [], periods = [], tickerSignals = [], role = 'reader', next = null, loading = false, sequence = 0, disposed = false, observer, pages = 0, restoring = false;
    let dirSort = 'recent';
    let searchTimer = null;
    const bookSet = new Set((options.bookTickers || []).map(t => String(t || '').trim().toUpperCase()).filter(Boolean));
    const watchlistSet = new Set((options.watchlistTickers || []).map(t => String(t || '').trim().toUpperCase()).filter(Boolean));
    const tickerStatsMap = new Map();

    const abort = new AbortController();
    const controller = {
      dispose() {
        disposed = true;
        sequence++;
        if (searchTimer) global.clearTimeout(searchTimer);
        observer?.disconnect();
        abort.abort();
      },
    };
    states.set(root, controller);
    root.classList.add('fl-reader');
    if (embedded) root.classList.add('is-embedded');
    else root.classList.remove('is-embedded');

    root.innerHTML = `
      <a class="fl-skip" href="#fl-reading">Skip to letters</a>
      ${embedded ? '' : `
      <header class="fl-masthead">
        <div>
          <div class="fl-wordmark">MAGIS / RESEARCH LIBRARY</div>
          <h1>Fund Letters</h1>
          <p>Investment arguments, in the manager’s own historical context.</p>
        </div>
        <div class="fl-owner-tools"></div>
      </header>`}
      <div class="fl-toolbar">
        <div class="fl-view-tabs" role="tablist" aria-label="Reading mode">
          <button type="button" class="fl-view-tab" data-view-mode="letters">Letters</button>
          <button type="button" class="fl-view-tab" data-view-mode="ideas">Ideas &amp; Theses</button>
        </div>
        <form class="fl-filters" role="search">
          <div class="fl-search-field">
            <label class="fl-sr-only" for="fl-search-input">Company, ticker, fund or investment argument</label>
            <input id="fl-search-input" name="q" type="search" placeholder="Search company, ticker, or try ticker:TK type:short action:new focus:macro…" autocomplete="off">
            <div class="fl-search-suggest" hidden role="listbox" aria-label="Search suggestions"></div>
          </div>
          <label class="fl-compact-field">
            <span class="fl-sr-only">Signal or overlap</span>
            <select name="signal" aria-label="Signal or overlap">
              <option value="">All signals</option>
              <optgroup label="Cross-fund signals">
                <option value="multi">2+ funds discussing</option>
                <option value="battleground">Long vs. Short battleground</option>
                <option value="evolution">Updated vs. prior letter</option>
              </optgroup>
              <optgroup label="Letter focus">
                <option value="focus:micro">Micro / stock-picking focus</option>
                <option value="focus:macro">Macro / regime focus</option>
                <option value="focus:mixed">Mixed focus</option>
              </optgroup>
            </select>
          </label>
          <label class="fl-compact-field">
            <span class="fl-sr-only">Period</span>
            <select name="period" aria-label="Period">
              <option value="">All periods</option>
            </select>
          </label>
          <label class="fl-compact-field">
            <span class="fl-sr-only">Idea type</span>
            <select name="type" aria-label="Idea type">
              <option value="">All categories</option>
              <optgroup label="Quick groups">
                <option value="long">Longs</option>
                <option value="short">Shorts</option>
                <option value="special_situation,credit,private,unnamed">Special situations &amp; credit</option>
                <option value="update,postmortem">Updates &amp; postmortems</option>
                <option value="macro,sector,portfolio">Macro &amp; sector</option>
              </optgroup>
              <optgroup label="Specific types">
                ${types.map(t => `<option value="${t}">${escape(label(t))}</option>`).join('')}
              </optgroup>
            </select>
          </label>
          <label class="fl-compact-field">
            <span class="fl-sr-only">Position action</span>
            <select name="activity" aria-label="Position action">
              <option value="">Any action</option>
              <option value="new,add">New / Add</option>
              <option value="trim,exit">Trim / Exit</option>
              <option value="hold">Hold</option>
            </select>
          </label>
          <label class="fl-mobile-select fl-compact-field">
            <span class="fl-sr-only">Fund</span>
            <select name="fund" aria-label="Fund">
              <option value="">All funds</option>
            </select>
          </label>
          <details class="fl-date-range">
            <summary>Dates</summary>
            <div class="fl-date-range-pop">
              <label>From<input name="from" type="date"></label>
              <label>To<input name="to" type="date"></label>
            </div>
          </details>
          <button type="submit" class="fl-sr-only">Search</button>
          <button type="button" data-reset class="fl-reset" hidden>Clear</button>
        </form>
        ${embedded ? '<div class="fl-owner-tools"></div>' : ''}
      </div>
      <div class="fl-active-filters" hidden aria-label="Active filters"></div>
      <div class="fl-grid">
        <aside class="fl-directory" aria-label="Fund directory">
          <div class="fl-directory-head">
            <h2>Funds <span class="fl-directory-count"></span></h2>
            <div class="fl-dir-sort" role="group" aria-label="Sort funds">
              <button type="button" class="fl-dir-sort-btn is-active" data-dir-sort="recent">Recent</button>
              <button type="button" class="fl-dir-sort-btn" data-dir-sort="alpha">A–Z</button>
              <button type="button" class="fl-dir-sort-btn" data-dir-sort="count">Count</button>
            </div>
          </div>
          <input type="search" aria-label="Find a fund" placeholder="Filter funds…">
          <ul></ul>
        </aside>
        <div id="fl-reading" class="fl-reading" tabindex="-1" aria-live="polite">
          <p role="status" class="fl-status">Loading the archive…</p>
        </div>
      </div>
      <dialog aria-labelledby="fl-review-title"></dialog>`;

    const reading = root.querySelector('.fl-reading');
    const form = root.querySelector('form.fl-filters');
    const searchInput = form.elements.q;
    const suggestBox = root.querySelector('.fl-search-suggest');
    const activeFiltersBar = root.querySelector('.fl-active-filters');
    const directory = root.querySelector('.fl-directory');
    const dialog = root.querySelector('dialog');
    const resetBtn = form.querySelector('[data-reset]');
    const on = (el, event, fn) => el && el.addEventListener(event, fn, { signal: abort.signal });
    const link = extra => '/fund-letters/?' + new URLSearchParams({ ...Object.fromEntries(params), ...extra });
    const showError = error => {
      if (!disposed) {
        reading.innerHTML = `<div class="fl-error" role="alert">${escape(error.message)}</div><button type="button" data-retry>Try again</button>`;
      }
    };

    function ideaMetaBadges(item) {
      const out = [];
      if (item.idea_type) out.push(badgeHtml(label(item.idea_type), typeTone(item.idea_type)));
      if (item.ticker) {
        const sym = String(item.ticker).trim().toUpperCase();
        out.push(`<button type="button" class="fl-ticker" data-pick-ticker="${escape(sym)}" title="Filter by ${escape(sym)}">${escape(sym)}</button>`);
        if (role === 'owner' && bookSet.has(sym)) {
          out.push(badgeHtml('In book', 'add'));
        } else if (role === 'owner' && watchlistSet.has(sym)) {
          out.push(badgeHtml('Watchlist', 'macro'));
        }
        const sig = tickerStatsMap.get(sym);
        if (sig?.battleground) {
          out.push(badgeHtml(`Battleground (${sig.bull_count}▲ ${sig.bear_count}▼)`, 'warn'));
        } else if (sig?.multi_fund) {
          out.push(badgeHtml(`${sig.fund_count} funds`, 'special'));
        }
      }
      if (item.activity && item.activity !== 'hold') out.push(badgeHtml(label(item.activity), activityTone(item.activity)));
      return out.join('');
    }

    function activeViewMode() {
      if (params.get('mode') === 'review' && role === 'owner') return 'review';
      if (params.get('view') === 'ideas') return 'ideas';
      return 'letters';
    }

    function hasFilters() {
      return ['q', 'type', 'activity', 'period', 'from', 'to', 'signal', 'focus', 'tickers'].some(k => params.get(k));
    }

    function populateSignalSelect() {
      const select = form.elements.signal;
      if (!select) return;
      const multiCount = tickerSignals.filter(t => t.multi_fund).length;
      const battleCount = tickerSignals.filter(t => t.battleground).length;
      const ownerOptgroup = role === 'owner' && (bookSet.size || watchlistSet.size)
        ? `<optgroup label="Portfolio &amp; Watchlist">
            ${bookSet.size ? `<option value="scope:book">In our book (${bookSet.size} tickers)</option>` : ''}
            ${watchlistSet.size ? `<option value="scope:watchlist">On watchlist (${watchlistSet.size} tickers)</option>` : ''}
            ${(bookSet.size && watchlistSet.size) ? `<option value="scope:universe">Full research universe</option>` : ''}
          </optgroup>`
        : '';
      select.innerHTML = `<option value="">All signals</option>
        ${ownerOptgroup}
        <optgroup label="Cross-fund signals">
          <option value="multi">2+ funds discussing${multiCount ? ` (${multiCount} tickers)` : ''}</option>
          <option value="battleground">Long vs. Short battleground${battleCount ? ` (${battleCount} tickers)` : ''}</option>
          <option value="evolution">Updated vs. prior letter</option>
        </optgroup>
        <optgroup label="Letter focus">
          <option value="focus:micro">Micro / stock-picking focus</option>
          <option value="focus:macro">Macro / regime focus</option>
          <option value="focus:mixed">Mixed focus</option>
        </optgroup>`;
      const currentSignal = params.get('signal') || (params.get('focus') ? `focus:${params.get('focus')}` : '') || (params.get('scope') ? `scope:${params.get('scope')}` : '');
      select.value = currentSignal;
    }

    function renderActiveFilterPills() {
      if (!activeFiltersBar) return;
      const pills = [];
      if (params.get('fund')) {
        const fn = funds.find(f => f.id === params.get('fund'))?.name || params.get('fund');
        pills.push({ key: 'fund', label: `Fund: ${fn}` });
      }
      if (params.get('scope')) {
        const scopeNames = { book: 'In our book', watchlist: 'On watchlist', universe: 'Research universe' };
        pills.push({ key: 'scope', label: `Portfolio: ${scopeNames[params.get('scope')] || params.get('scope')}` });
      }
      if (params.get('signal')) {
        const sigNames = { multi: '2+ funds discussing', battleground: 'Long vs. Short battleground', evolution: 'Updated vs. prior letter' };
        pills.push({ key: 'signal', label: `Signal: ${sigNames[params.get('signal')] || params.get('signal')}` });
      }
      if (params.get('focus')) {
        pills.push({ key: 'focus', label: `Focus: ${params.get('focus')}` });
      }
      if (params.get('tickers')) {
        pills.push({ key: 'tickers', label: `Ticker: ${params.get('tickers')}` });
      }
      if (params.get('period')) {
        pills.push({ key: 'period', label: `Period: ${params.get('period')}` });
      }
      if (params.get('type')) {
        pills.push({ key: 'type', label: `Type: ${label(params.get('type'))}` });
      }
      if (params.get('activity')) {
        pills.push({ key: 'activity', label: `Action: ${label(params.get('activity'))}` });
      }
      if (params.get('q')) {
        pills.push({ key: 'q', label: `Query: “${params.get('q')}”` });
      }
      if (!pills.length) {
        activeFiltersBar.hidden = true;
        activeFiltersBar.innerHTML = '';
        return;
      }
      activeFiltersBar.hidden = false;
      activeFiltersBar.innerHTML = `<span class="fl-active-label">Active filters:</span>`
        + pills.map(p => `<button type="button" class="fl-filter-pill" data-clear-key="${escape(p.key)}">${escape(p.label)} <span aria-hidden="true">×</span></button>`).join('')
        + `<button type="button" class="fl-filter-clear-all" data-reset-all>Reset all</button>`;
    }

    function syncControlStates() {
      const mode = activeViewMode();
      root.querySelectorAll('[data-view-mode]').forEach(btn => {
        const isCurrent = btn.dataset.viewMode === mode;
        btn.classList.toggle('is-active', isCurrent);
        btn.setAttribute('aria-selected', String(isCurrent));
      });
      const anyActive = hasFilters() || Boolean(params.get('fund')) || Boolean(params.get('letter')) || Boolean(params.get('scope'));
      if (resetBtn) resetBtn.hidden = !anyActive;
      renderActiveFilterPills();
    }

    function populatePeriodSelect() {
      const select = form.elements.period;
      if (!select) return;
      const years = new Map();
      for (const p of periods) {
        const m = String(p.period || '').match(/^(\d{4})/);
        if (m) years.set(m[1], (years.get(m[1]) || 0) + Number(p.count || 0));
      }
      const yearOpts = [...years.entries()]
        .sort((a, b) => b[0].localeCompare(a[0]))
        .map(([y, count]) => `<option value="${escape(y)}">${escape(y)} (${count})</option>`)
        .join('');
      const quarterOpts = periods
        .map(p => `<option value="${escape(p.period)}">${escape(p.period)} (${p.count})</option>`)
        .join('');
      select.innerHTML = '<option value="">All periods</option>'
        + (yearOpts ? `<optgroup label="By year">${yearOpts}</optgroup>` : '')
        + (quarterOpts ? `<optgroup label="By quarter">${quarterOpts}</optgroup>` : '');
      select.value = params.get('period') || '';
    }

    function buildSearchSuggestions(rawInput) {
      const text = String(rawInput || '');
      const parts = text.split(/\s+/);
      const lastToken = parts[parts.length - 1] || '';
      const prefixText = parts.slice(0, -1).join(' ');
      const withPrefix = token => (prefixText ? `${prefixText} ${token} ` : `${token} `);
      const items = [];

      if (!lastToken || !lastToken.includes(':')) {
        const q = lastToken.toLowerCase();
        const operators = [
          { token: 'is:multi', label: 'is:multi', hint: 'Tickers discussed by 2+ funds' },
          { token: 'is:battleground', label: 'is:battleground', hint: 'Long vs. Short disagreement across funds' },
          ...(role === 'owner' && bookSet.size ? [{ token: 'is:book', label: 'is:book', hint: `Overlaps our portfolio (${bookSet.size} tickers)` }] : []),
          { token: 'type:long', label: 'type:long', hint: 'Long equity theses' },
          { token: 'type:short', label: 'type:short', hint: 'Short equity theses' },
          { token: 'action:new', label: 'action:new', hint: 'New position initiations' },
          { token: 'action:exit', label: 'action:exit', hint: 'Closed / exited positions' },
          { token: 'focus:macro', label: 'focus:macro', hint: 'Macro & regime letters' },
          { token: 'focus:micro', label: 'focus:micro', hint: 'Stock-picking letters' },
        ];
        for (const op of operators) {
          if (!q || op.token.includes(q) || op.hint.toLowerCase().includes(q)) {
            items.push({ value: withPrefix(op.token), label: op.label, hint: op.hint });
          }
        }
        if (q.length >= 1) {
          for (const t of tickerSignals.filter(x => x.ticker.toLowerCase().startsWith(q)).slice(0, 4)) {
            items.push({
              value: withPrefix(`ticker:${t.ticker}`),
              label: `ticker:${t.ticker}`,
              hint: `${t.fund_count} ${t.fund_count === 1 ? 'fund' : 'funds'}${t.battleground ? ' · Battleground' : ''}`,
            });
          }
          for (const f of funds.filter(x => x.name.toLowerCase().includes(q) || x.id.includes(q)).slice(0, 3)) {
            items.push({
              value: withPrefix(`fund:${f.id}`),
              label: `fund:${f.id}`,
              hint: `${f.name} (${f.letter_count})`,
            });
          }
        } else {
          for (const t of tickerSignals.slice(0, 4)) {
            items.push({
              value: withPrefix(`ticker:${t.ticker}`),
              label: `ticker:${t.ticker}`,
              hint: `${t.fund_count} ${t.fund_count === 1 ? 'fund' : 'funds'}${t.battleground ? ' · Battleground' : ''}`,
            });
          }
        }
        return items.slice(0, 8);
      }

      const [rawKey, rawVal = ''] = lastToken.split(':', 2);
      const key = rawKey.toLowerCase();
      const val = rawVal.toLowerCase();
      if (key === 'ticker' || key === 'sym') {
        for (const t of tickerSignals.filter(x => !val || x.ticker.toLowerCase().startsWith(val)).slice(0, 8)) {
          items.push({
            value: withPrefix(`ticker:${t.ticker}`),
            label: `ticker:${t.ticker}`,
            hint: `${t.fund_count} ${t.fund_count === 1 ? 'fund' : 'funds'} · ${t.bull_count}▲ ${t.bear_count}▼`,
          });
        }
      } else if (key === 'type') {
        for (const t of types.filter(x => !val || x.includes(val))) {
          items.push({ value: withPrefix(`type:${t}`), label: `type:${t}`, hint: label(t) });
        }
      } else if (key === 'action' || key === 'activity') {
        for (const a of ['new', 'add', 'trim', 'exit', 'hold', 'short', 'cover'].filter(x => !val || x.startsWith(val))) {
          items.push({ value: withPrefix(`action:${a}`), label: `action:${a}`, hint: `Position action: ${a}` });
        }
      } else if (key === 'focus') {
        for (const f of ['micro', 'macro', 'mixed'].filter(x => !val || x.startsWith(val))) {
          items.push({ value: withPrefix(`focus:${f}`), label: `focus:${f}`, hint: `${label(f)} letter focus` });
        }
      } else if (key === 'period' || key === 'quarter' || key === 'year') {
        for (const p of periods.filter(x => !val || x.period.toLowerCase().startsWith(val)).slice(0, 8)) {
          items.push({ value: withPrefix(`period:${p.period}`), label: `period:${p.period}`, hint: `${p.count} letters` });
        }
      } else if (key === 'fund') {
        for (const f of funds.filter(x => !val || x.id.includes(val) || x.name.toLowerCase().includes(val)).slice(0, 8)) {
          items.push({ value: withPrefix(`fund:${f.id}`), label: `fund:${f.id}`, hint: `${f.name} (${f.letter_count})` });
        }
      } else if (key === 'is' || key === 'signal') {
        const sigs = [
          { id: 'multi', hint: 'Tickers discussed by 2+ funds' },
          { id: 'battleground', hint: 'Long vs. Short disagreement' },
          { id: 'evolution', hint: 'Updated thesis vs. prior letter' },
          ...(role === 'owner' && bookSet.size ? [{ id: 'book', hint: 'Overlaps our portfolio' }] : []),
        ];
        for (const s of sigs.filter(x => !val || x.id.startsWith(val))) {
          items.push({ value: withPrefix(`is:${s.id}`), label: `is:${s.id}`, hint: s.hint });
        }
      }
      return items.slice(0, 8);
    }

    function renderSuggestions() {
      if (!suggestBox || document.activeElement !== searchInput) {
        if (suggestBox) suggestBox.hidden = true;
        return;
      }
      const list = buildSearchSuggestions(searchInput.value);
      if (!list.length) {
        suggestBox.hidden = true;
        return;
      }
      suggestBox.hidden = false;
      suggestBox.innerHTML = `<div class="fl-suggest-head">Smart search tokens <span>click to apply</span></div>`
        + list.map(item => `
          <button type="button" class="fl-suggest-item" role="option" data-suggest-val="${escape(item.value)}">
            <code class="fl-suggest-code">${escape(item.label)}</code>
            <span class="fl-suggest-hint">${escape(item.hint)}</span>
          </button>`).join('');
    }

    function remember() {
      if (embedded) sessionStorage.setItem('fl-reader-state', params.toString());
      else history.replaceState({ ...history.state, flScroll: global.scrollY, flPages: pages }, '', location.href);
    }

    function navigate(change, push = true) {
      remember();
      for (const [key, value] of Object.entries(change)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      if (embedded) sessionStorage.setItem('fl-reader-state', params.toString());
      else if (push) history.pushState({ flScroll: 0 }, '', '?' + params.toString());
      load();
    }

    function drawDirectory(filter = '') {
      const query = filter.toLowerCase().trim();
      const rows = funds.filter(f => `${f.name} ${f.manager} ${f.strategy}`.toLowerCase().includes(query));
      rows.sort((a, b) => {
        if (dirSort === 'count') {
          return (Number(b.letter_count || 0) - Number(a.letter_count || 0)) || String(a.name).localeCompare(String(b.name));
        }
        if (dirSort === 'recent') {
          const cmp = periodSortKey(b.latest).localeCompare(periodSortKey(a.latest));
          if (cmp !== 0) return cmp;
        }
        return String(a.name).localeCompare(String(b.name));
      });
      const totalLetters = funds.reduce((acc, f) => acc + Number(f.letter_count || 0), 0);
      directory.querySelectorAll('[data-dir-sort]').forEach(btn => {
        btn.classList.toggle('is-active', btn.dataset.dirSort === dirSort);
      });
      const currentFund = params.get('fund') || '';
      directory.querySelector('ul').innerHTML = `
        <li>
          <a href="${escape(link({ fund: '', letter: '', idea: '', mode: '' }))}" data-fund=""${!currentFund ? ' aria-current="true"' : ''}>
            <div class="fl-dir-row-top"><strong>All funds</strong><span class="fl-dir-pill">${totalLetters}</span></div>
            <small>${funds.length} published funds</small>
          </a>
        </li>` + rows.map(f => `
        <li>
          <a href="${escape(link({ fund: f.id, letter: '', idea: '', mode: '' }))}" data-fund="${escape(f.id)}"${currentFund === f.id ? ' aria-current="true"' : ''}>
            <div class="fl-dir-row-top"><strong>${escape(f.name)}</strong><span class="fl-dir-pill">${f.letter_count}</span></div>
            <small>${f.manager ? `${escape(f.manager)} · ` : ''}${escape(f.latest || 'undated')}</small>
          </a>
        </li>`).join('');
      directory.querySelector('.fl-directory-count').textContent = `(${funds.length})`;
      const alphaFunds = funds.slice().sort((a, b) => String(a.name).localeCompare(String(b.name)));
      form.elements.fund.innerHTML = '<option value="">All funds</option>' + alphaFunds.map(f => `<option value="${escape(f.id)}">${escape(f.name)} (${f.letter_count})</option>`).join('');
      form.elements.fund.value = currentFund;
    }

    function renderSignalStrip() {
      const activeSignal = params.get('signal') || '';
      const activeScope = params.get('scope') || '';
      const activeTicker = (params.get('tickers') || '').toUpperCase();
      let relevant = [];
      let title = '';
      if (activeSignal === 'battleground') {
        relevant = tickerSignals.filter(t => t.battleground);
        title = 'Battleground tickers (Long vs. Short disagreement across archive)';
      } else if (activeSignal === 'multi') {
        relevant = tickerSignals.filter(t => t.multi_fund);
        title = 'Multi-fund overlap (2+ funds discussing)';
      } else if (activeScope === 'book' && role === 'owner') {
        relevant = tickerSignals.filter(t => bookSet.has(t.ticker));
        title = 'Portfolio holdings discussed in published letters';
      } else if (activeScope === 'watchlist' && role === 'owner') {
        relevant = tickerSignals.filter(t => watchlistSet.has(t.ticker));
        title = 'Watchlist securities discussed in published letters';
      } else if (!hasFilters() && !params.get('fund')) {
        relevant = tickerSignals.filter(t => t.multi_fund || t.battleground || (role === 'owner' && bookSet.has(t.ticker))).slice(0, 10);
        if (relevant.length) title = 'Cross-fund signals & overlap';
      }
      if (!relevant.length) return '';
      return `
        <section class="fl-signal-strip" aria-label="${escape(title)}">
          <div class="fl-signal-strip-head">
            <span class="fl-meta">${escape(title)}</span>
            ${activeTicker ? `<button type="button" class="fl-btn-ghost" data-pick-ticker="">Show all tickers</button>` : ''}
          </div>
          <div class="fl-signal-pills">
            ${relevant.slice(0, 14).map(t => {
              const isSelected = activeTicker === t.ticker;
              const isBook = role === 'owner' && bookSet.has(t.ticker);
              return `
                <button type="button"
                        class="fl-signal-pill${isSelected ? ' is-active' : ''}${t.battleground ? ' is-battleground' : ''}"
                        data-pick-ticker="${escape(isSelected ? '' : t.ticker)}">
                  <strong>${escape(t.ticker)}</strong>
                  <span>${t.fund_count} ${t.fund_count === 1 ? 'fund' : 'funds'}</span>
                  <small>${t.bull_count}▲ ${t.bear_count}▼</small>
                  ${isBook ? '<em class="fl-in-book-dot" title="In our book">Book</em>' : ''}
                </button>`;
            }).join('')}
          </div>
        </section>`;
    }

    function resultHtml(item) {
      return `
        <article class="fl-result">
          <div class="fl-result-top">
            <button type="button" class="fl-fund-tag" data-fund="${escape(item.fund_id)}">${escape(item.fund)}</button>
            <span class="fl-period-tag">${escape(item.reporting_period || 'Undated')}</span>
            ${ideaMetaBadges(item)}
          </div>
          <h3>
            <a href="${escape(link({ fund: item.fund_id, letter: item.letter_id, idea: item.id, view: 'letters' }))}"
               data-open-letter="${escape(item.letter_id)}"
               data-open-fund="${escape(item.fund_id)}"
               data-open-idea="${escape(item.id)}">${escape(item.title)}</a>
          </h3>
          <div class="fl-result-body">${paragraphs(item.summary.split(/\n\s*\n/)[0])}</div>
        </article>`;
    }

    function letterCardHtml(letter) {
      const ideas = Array.isArray(letter.ideas) ? letter.ideas : [];
      const primaryIdeas = ideas.filter(i => i.idea_type !== 'factual_note');
      const chipIdeas = (primaryIdeas.length ? primaryIdeas : ideas).slice(0, 5);
      const previewParagraph = String(letter.overview || '').split(/\n\s*\n/).filter(Boolean)[0] || '';
      const hasBookOverlap = role === 'owner' && ideas.some(i => i.ticker && bookSet.has(String(i.ticker).toUpperCase()));
      return `
        <article class="fl-letter-card" id="fl-card-${escape(letter.id)}">
          <header class="fl-letter-card-head">
            <div class="fl-letter-card-meta">
              <button type="button" class="fl-fund-tag" data-fund="${escape(letter.fund_id)}">${escape(letter.fund)}</button>
              <span class="fl-period-tag">${escape(letter.reporting_period || 'Undated')}</span>
              ${letter.letter_date ? `<span class="fl-date-inline">${escape(letter.letter_date)}</span>` : ''}
              ${letter.focus ? badgeHtml(label(letter.focus), letter.focus === 'macro' ? 'macro' : letter.focus === 'mixed' ? 'special' : 'neutral') : ''}
              ${hasBookOverlap ? badgeHtml('In our book', 'add') : ''}
            </div>
            <div class="fl-letter-card-actions">
              ${role === 'owner' ? `<button type="button" class="fl-btn-ghost" data-source="${escape(letter.id)}">Edit</button>` : ''}
              <a class="fl-open-link"
                 href="${escape(link({ fund: letter.fund_id, letter: letter.id, idea: '' }))}"
                 data-open-letter="${escape(letter.id)}"
                 data-open-fund="${escape(letter.fund_id)}">Read letter →</a>
            </div>
          </header>
          <h3 class="fl-letter-card-title">
            <a href="${escape(link({ fund: letter.fund_id, letter: letter.id, idea: '' }))}"
               data-open-letter="${escape(letter.id)}"
               data-open-fund="${escape(letter.fund_id)}">${escape(letter.headline || `${letter.fund} · ${letter.reporting_period || 'Letter'}`)}</a>
          </h3>
          ${previewParagraph ? `<p class="fl-letter-card-preview">${escape(previewParagraph)}</p>` : ''}
          ${chipIdeas.length ? `
          <div class="fl-card-ideas" aria-label="Discussed in this letter">
            ${chipIdeas.map(i => {
              const sym = i.ticker ? String(i.ticker).toUpperCase() : '';
              const inBook = role === 'owner' && sym && bookSet.has(sym);
              return `
              <a class="fl-idea-chip${inBook ? ' is-book' : ''}"
                 href="${escape(link({ fund: letter.fund_id, letter: letter.id, idea: i.id }))}"
                 data-open-letter="${escape(letter.id)}"
                 data-open-fund="${escape(letter.fund_id)}"
                 data-open-idea="${escape(i.id)}">
                ${sym ? `<strong class="fl-chip-ticker">${escape(sym)}</strong>` : ''}
                <span>${escape(i.title)}</span>
              </a>`;
            }).join('')}
            ${ideas.length > chipIdeas.length ? `<span class="fl-more-ideas">+${ideas.length - chipIdeas.length} more</span>` : ''}
          </div>` : ''}
        </article>`;
    }

    function stanceHtml(letter) {
      const stance = letter.stance;
      if (!stance || (!stance.leaning_in?.length && !stance.leaning_out?.length)) return '';
      const column = (title, items, cls) => items?.length
        ? `<div class="fl-stance-col ${cls}"><h4>${title}</h4><ul>${items.map(item => `<li><strong>${escape(item.subject)}</strong>${paragraphs(item.why)}</li>`).join('')}</ul></div>`
        : '';
      return `
        <section class="fl-stance" aria-label="What the fund is leaning into and out of">
          <div class="fl-stance-head">
            <span class="fl-meta">Portfolio stance${stance.focus ? ` · ${escape(label(stance.focus))} letter` : ''}</span>
          </div>
          <div class="fl-stance-grid">
            ${column('Leaning in', stance.leaning_in, 'is-in')}
            ${column('Leaning out', stance.leaning_out, 'is-out')}
          </div>
        </section>`;
    }

    function ideaSectionHtml(letter, i) {
      return `
        <section class="fl-idea" id="fl-idea-${escape(letter.id)}-${escape(i.id)}">
          <div class="fl-idea-badges">${ideaMetaBadges(i)}</div>
          <h4>${escape(i.title)}</h4>
          <div class="fl-idea-prose">${paragraphs(i.summary)}</div>
          ${i.evolution ? `
          <div class="fl-evolution">
            <h4>What changed</h4>
            ${paragraphs(i.evolution)}
            <a href="${escape(link({ fund: letter.fund_id, letter: i.compared_letter_id, idea: '' }))}"
               data-open-fund="${escape(letter.fund_id)}"
               data-open-letter="${escape(i.compared_letter_id)}">Earlier discussion →</a>
          </div>` : ''}
        </section>`;
    }

    function letterHtml(letter) {
      const ideas = Array.isArray(letter.ideas) ? letter.ideas : [];
      const companyIdeas = ideas.filter(i => !MACRO_TYPES.has(i.idea_type) && i.idea_type !== 'factual_note');
      const macroIdeas = ideas.filter(i => MACRO_TYPES.has(i.idea_type));
      const factualIdeas = ideas.filter(i => i.idea_type === 'factual_note');
      const hasMultipleGroups = [companyIdeas.length > 0, macroIdeas.length > 0, factualIdeas.length > 0].filter(Boolean).length > 1;
      const focusLabel = letter.focus || letter.stance?.focus || '';

      return `
        <article class="fl-letter" id="fl-letter-${escape(letter.id)}">
          <header class="fl-letter-head">
            <div>
              <div class="fl-letter-eyebrow">
                <span class="fl-period-tag">${escape(letter.reporting_period || 'Period unavailable')}</span>
                <span class="fl-date">${escape(letter.letter_date ? `Letter dated ${letter.letter_date}` : 'Exact letter date unavailable')}</span>
                ${focusLabel ? badgeHtml(`${label(focusLabel)} focus`, focusLabel === 'macro' ? 'macro' : focusLabel === 'mixed' ? 'special' : 'neutral') : ''}
              </div>
              <h3>${escape(letter.headline || `${letter.fund} · ${letter.reporting_period || 'Letter'}`)}</h3>
            </div>
            ${role === 'owner' ? `<button type="button" class="fl-btn-sm" data-source="${escape(letter.id)}">Source &amp; revisions</button>` : ''}
          </header>

          <div class="fl-overview">${paragraphs(letter.overview)}</div>

          ${stanceHtml(letter)}

          ${ideas.length ? `
          <nav class="fl-contents" aria-label="Ideas in this letter">
            <h4>In this letter (${ideas.length})</h4>
            <ul class="fl-contents-chips">
              ${ideas.map(i => `
                <li>
                  <a class="fl-idea-chip"
                     href="${escape(link({ fund: letter.fund_id, letter: letter.id, idea: i.id }))}"
                     data-jump="fl-idea-${escape(letter.id)}-${escape(i.id)}">
                    ${i.ticker ? `<strong class="fl-chip-ticker">${escape(i.ticker)}</strong>` : ''}
                    <span>${escape(i.title)}</span>
                    ${i.activity && i.activity !== 'hold' ? `<em class="fl-chip-act">${escape(label(i.activity))}</em>` : ''}
                  </a>
                </li>`).join('')}
            </ul>
          </nav>` : ''}

          ${companyIdeas.length ? `
          <div class="fl-idea-group">
            ${hasMultipleGroups ? `<h4 class="fl-group-heading">Company &amp; position theses <span>(${companyIdeas.length})</span></h4>` : ''}
            ${companyIdeas.map(i => ideaSectionHtml(letter, i)).join('')}
          </div>` : ''}

          ${macroIdeas.length ? `
          <div class="fl-idea-group">
            ${hasMultipleGroups ? `<h4 class="fl-group-heading">Macro, sector &amp; portfolio views <span>(${macroIdeas.length})</span></h4>` : ''}
            ${macroIdeas.map(i => ideaSectionHtml(letter, i)).join('')}
          </div>` : ''}

          ${factualIdeas.length ? (companyIdeas.length || macroIdeas.length ? `
          <details class="fl-factual-notes">
            <summary>Factual &amp; holdings-table mentions (${factualIdeas.length})</summary>
            <div class="fl-idea-group">
              ${factualIdeas.map(i => ideaSectionHtml(letter, i)).join('')}
            </div>
          </details>` : `
          <div class="fl-idea-group">
            ${factualIdeas.map(i => ideaSectionHtml(letter, i)).join('')}
          </div>`) : ''}

          <footer class="fl-revision">
            Attributed to ${escape(letter.fund)} · ${escape(letter.reporting_period || 'Period unavailable')}${letter.summary_published_at ? ` · Summary published ${escape(letter.summary_published_at.slice(0, 10))}` : ''}${letter.summary_revised_at ? ` · Revision ${escape(letter.summary_revised_at.slice(0, 10))}` : ''}
          </footer>
        </article>`;
    }

    function scrollToIdea(letterId, ideaId) {
      if (!letterId || !ideaId) return;
      const target = root.querySelector(`#fl-idea-${CSS.escape(letterId)}-${CSS.escape(ideaId)}`);
      if (!target) return;
      const details = target.closest('details');
      if (details) details.open = true;
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function moreButton() {
      reading.querySelector('[data-more]')?.remove();
      observer?.disconnect();
      if (next === null) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'fl-more';
      button.dataset.more = '';
      button.textContent = params.get('fund') && !hasFilters() ? 'Load older letters' : 'Load more results';
      reading.append(button);
      if ('IntersectionObserver' in global && !restoring) {
        observer = new IntersectionObserver(entries => {
          if (entries.some(e => e.isIntersecting) && !loading) load(true);
        }, { rootMargin: '200px' });
        observer.observe(button);
      }
    }

    function resolveEffectiveQueryArgs() {
      const args = { ...Object.fromEntries(params) };
      let qText = String(args.q || '');
      if (/\bis:book\b/i.test(qText)) {
        qText = qText.replace(/\bis:book\b/gi, '').trim();
        args.q = qText;
        args.scope = 'book';
      }
      if (/\bis:watchlist\b/i.test(qText)) {
        qText = qText.replace(/\bis:watchlist\b/gi, '').trim();
        args.q = qText;
        args.scope = 'watchlist';
      }
      if (args.scope && role === 'owner') {
        const targetSet = args.scope === 'book'
          ? bookSet
          : args.scope === 'watchlist'
            ? watchlistSet
            : new Set([...bookSet, ...watchlistSet]);
        const scopeList = [...targetSet];
        if (scopeList.length) {
          args.tickers = args.tickers ? `${args.tickers},${scopeList.join(',')}` : scopeList.join(',');
        } else {
          args.tickers = '__NONE__';
        }
      }
      delete args.scope;
      return args;
    }

    async function load(append = false, restoreScroll = null) {
      if (loading && append) return;
      const ticket = ++sequence;
      loading = true;
      observer?.disconnect();
      if (!append) {
        next = null;
        pages = 0;
        reading.innerHTML = '<p class="fl-status" role="status">Loading letters…</p>';
      } else {
        const btn = reading.querySelector('[data-more]');
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Loading…';
        }
      }
      for (const key of ['q', 'type', 'activity', 'period', 'from', 'to', 'fund']) {
        if (form.elements[key]) form.elements[key].value = params.get(key) || '';
      }
      if (form.elements.signal) {
        form.elements.signal.value = params.get('signal')
          || (params.get('focus') ? `focus:${params.get('focus')}` : '')
          || (params.get('scope') ? `scope:${params.get('scope')}` : '');
      }
      const reviewing = params.get('mode') === 'review' && role === 'owner';
      for (const key of ['signal', 'type', 'activity', 'period', 'from', 'to', 'fund']) {
        const wrapper = form.elements[key]?.closest('label, details');
        if (wrapper) wrapper.hidden = reviewing;
      }
      form.elements.q.placeholder = reviewing
        ? 'Find a fund or review issue…'
        : 'Search company, ticker, or try ticker:TK type:short action:new focus:macro…';
      if (reviewing) form.elements.q.value = params.get('review_q') || '';
      syncControlStates();
      drawDirectory(directory.querySelector('input').value);

      try {
        const args = { ...resolveEffectiveQueryArgs(), offset: append ? String(next) : '0' };
        const mode = activeViewMode();

        if (mode === 'review') {
          const data = await api({ ...args, action: 'review' });
          if (ticket !== sequence || disposed) return;
          if (!append) {
            reading.innerHTML = `
              <header class="fl-section-head">
                <div>
                  <div class="fl-meta">Editorial workflow</div>
                  <h2>Review queue</h2>
                </div>
                <p class="fl-notice">${data.coverage?.published || 0} of ${data.coverage?.letters || 0} letters published. Readers see published summaries only.</p>
              </header>
              <section data-items></section>`;
          }
          reading.querySelector('[data-items]').insertAdjacentHTML(
            'beforeend',
            data.reviews.map(r => `
              <article class="fl-review-item">
                <div class="fl-meta">${escape(label(r.kind))}</div>
                <strong>${escape(r.fund)} · ${escape(r.reporting_period || 'Undated')}</strong>
                <p>${escape(r.detail)}</p>
                <button type="button" data-source="${escape(r.letter_id)}">Review letter</button>
              </article>`).join('') || '<p>No unresolved reviews.</p>',
          );
          next = data.next_offset;
        } else if (params.get('fund') && (mode === 'letters' || params.get('letter'))) {
          const data = await api({ ...args, action: 'letters' });
          if (ticket !== sequence || disposed) return;
          const fund = funds.find(f => f.id === params.get('fund'));
          const showAllStacked = params.get('stack') === '1';
          if (!append) {
            reading.innerHTML = `
              <header class="fl-fund-bar">
                <div class="fl-fund-bar-left">
                  <button type="button" class="fl-back-btn" data-all-funds>← All funds</button>
                  <div class="fl-fund-identity">
                    <h2>${escape(fund?.name || data.letters[0]?.fund || 'Fund')}</h2>
                    <span>${fund?.manager ? `${escape(fund.manager)} · ` : ''}${fund?.letter_count || data.letters.length || 0} published ${(fund?.letter_count || data.letters.length) === 1 ? 'letter' : 'letters'}</span>
                  </div>
                </div>
                <div class="fl-fund-bar-right">
                  ${hasFilters() ? '<button type="button" class="fl-back-btn" data-results>Filtered results</button>' : ''}
                  ${params.get('letter') ? '<button type="button" class="fl-back-btn" data-archive>Fund overview</button>' : ''}
                  <div class="fl-quarter-pills" role="navigation" aria-label="Letters by quarter"></div>
                  <select class="fl-letter-select" aria-label="Choose a letter" hidden>
                    <option value="">Choose a letter</option>
                  </select>
                </div>
              </header>
              <section data-items></section>`;
          }
          const items = reading.querySelector('[data-items]');
          if (!data.letters.length && !append) {
            items.innerHTML = '<div class="fl-empty"><h2>No published letters match this view</h2><p>Choose another quarter, clear active filters, or return to all funds.</p></div>';
          } else if (!append && !params.get('letter') && !showAllStacked && data.letters.length > 1) {
            const [featured, ...older] = data.letters;
            items.innerHTML = letterHtml(featured)
              + `<section class="fl-older-section">
                  <div class="fl-older-head">
                    <h3>Earlier letters from ${escape(fund?.name || featured.fund)}</h3>
                    <button type="button" class="fl-btn-sm" data-stack-all>Expand all full letters</button>
                  </div>
                  <div class="fl-letter-card-list">${older.map(letterCardHtml).join('')}</div>
                </section>`;
          } else {
            const container = (!append || showAllStacked || params.get('letter'))
              ? items
              : (reading.querySelector('.fl-letter-card-list') || items);
            const renderer = (!append || showAllStacked || params.get('letter')) ? letterHtml : letterCardHtml;
            container.insertAdjacentHTML('beforeend', data.letters.map(renderer).join(''));
          }
          next = data.next_offset;

          if (!append) {
            const activeLetterId = params.get('letter') || data.letters[0]?.id || '';
            api({ action: 'archive', fund: params.get('fund') }).then(archive => {
              if (ticket !== sequence || disposed) return;
              const list = archive.letters || [];
              const select = reading.querySelector('.fl-letter-select');
              if (select) {
                select.hidden = list.length <= 1;
                select.innerHTML = '<option value="">Archive (' + list.length + ')</option>'
                  + list.map(l => `<option value="${escape(l.id)}"${l.id === activeLetterId ? ' selected' : ''}>${escape(period(l))}</option>`).join('');
              }
              const pillBox = reading.querySelector('.fl-quarter-pills');
              if (pillBox && list.length > 1) {
                pillBox.innerHTML = list.slice(0, 8).map(l => `
                  <button type="button"
                          class="fl-quarter-pill${l.id === activeLetterId ? ' is-active' : ''}"
                          data-pick-letter="${escape(l.id)}">
                    ${escape(l.reporting_period || l.letter_date || 'Letter')}
                  </button>`).join('');
              }
            }).catch(() => {});
          }
        } else if (mode === 'letters') {
          const data = await api({ ...args, action: 'letters' });
          if (ticket !== sequence || disposed) return;
          if (!append) {
            const activePeriod = params.get('period') || 'All periods';
            const activeFund = params.get('fund') ? (funds.find(f => f.id === params.get('fund'))?.name || '') : 'All funds';
            reading.innerHTML = `
              ${renderSignalStrip()}
              <header class="fl-section-head">
                <div>
                  <h2>${hasFilters() || params.get('scope') ? 'Matching fund letters' : 'Recent fund letters'}</h2>
                </div>
                <span class="fl-date">${escape(activeFund)} · ${escape(activePeriod)}${params.get('type') ? ' · ' + escape(label(params.get('type'))) : ''}${params.get('activity') ? ' · ' + escape(label(params.get('activity'))) : ''}</span>
              </header>
              <section data-items class="fl-letter-card-list"></section>`;
          }
          reading.querySelector('[data-items]').insertAdjacentHTML(
            'beforeend',
            data.letters.map(letterCardHtml).join('')
              || `<div class="fl-empty"><h2>${funds.length ? 'No matching letters' : 'The archive is being prepared'}</h2><p>${funds.length ? 'Try a different search term, signal filter, or period.' : 'Letters will appear here after their summaries have completed verification.'}</p></div>`,
          );
          next = data.next_offset;
        } else {
          const data = await api({ ...args, action: 'search' });
          if (ticket !== sequence || disposed) return;
          if (!append) {
            reading.innerHTML = `
              ${renderSignalStrip()}
              <header class="fl-section-head">
                <div>
                  <h2>${hasFilters() || params.get('scope') ? 'Matching investment ideas' : 'Recent investment arguments'}</h2>
                </div>
                <span class="fl-date">${params.get('fund') ? escape(funds.find(f => f.id === params.get('fund'))?.name || '') : 'All funds'} · ${params.get('type') ? escape(label(params.get('type'))) : 'All categories'}${params.get('period') ? ' · ' + escape(params.get('period')) : ''}</span>
              </header>
              <section data-items class="fl-idea-result-list"></section>`;
          }
          reading.querySelector('[data-items]').insertAdjacentHTML(
            'beforeend',
            data.results.map(resultHtml).join('')
              || `<div class="fl-empty"><h2>${funds.length ? 'No matching ideas' : 'The archive is being prepared'}</h2><p>${funds.length ? 'Try a different company, signal filter, or idea type. Clear filters to explore every published idea.' : 'Letters will appear here after their summaries have completed review.'}</p></div>`,
          );
          next = data.next_offset;
        }
        pages++;
        moreButton();
        if (!append && params.get('idea')) {
          scrollToIdea(params.get('letter'), params.get('idea'));
        }
        if (restoreScroll !== null) global.scrollTo(0, restoreScroll);
      } catch (error) {
        if (ticket === sequence) showError(error);
      } finally {
        if (ticket === sequence) loading = false;
      }
    }

    async function review(letterId, revisionId = '') {
      dialog.innerHTML = '<p role="status">Loading private review…</p>';
      if (!dialog.open) dialog.showModal();
      try {
        const [source, versions, draftResult] = await Promise.all([
          api({ action: 'source', letter: letterId, revision: revisionId }),
          api({ action: 'revisions', letter: letterId }),
          api({ action: 'draft', letter: letterId, revision: revisionId }),
        ]);
        let revision = draftResult.draft, draft = revision?.content;
        const validationErrors = revision ? (JSON.parse(revision.checks_json || '{}').errors || []) : [];
        const sourceUrl = source.source.source_url;
        const validUrl = sourceUrl && /^https:\/\//.test(sourceUrl);
        dialog.innerHTML = `
          <header>
            <div><div class="fl-meta">Owner review</div><h2 id="fl-review-title">Letter sources &amp; revisions</h2></div>
            <button type="button" data-close aria-label="Close review">Close</button>
          </header>
          ${validUrl ? `<p><a href="${escape(sourceUrl)}" target="_blank" rel="noopener noreferrer">Open original letter</a></p>` : '<p>The original is available through the private research vault.</p>'}
          <p><a href="/api/fund-letters?action=document&amp;letter=${encodeURIComponent(letterId)}" target="_blank" rel="noopener noreferrer">Read full source text</a></p>
          <details><summary>Private references &amp; evidence</summary><pre>${escape(JSON.stringify(source, null, 2))}</pre></details>
          <label>Revision
            <select data-revision>
              <option value="">Choose a revision</option>
              ${versions.revisions.map(v => `<option value="${escape(v.id)}"${v.id === revision?.id ? ' selected' : ''}>${escape(v.created_at)} · ${escape(v.status)} · ${escape(v.author)}</option>`).join('')}
            </select>
          </label>
          ${validationErrors.length ? `<div class="fl-error">${validationErrors.map(escape).join('<br>')}</div>` : ''}
          ${draft ? `
            <label>Overview<textarea data-overview>${escape(draft.overview)}</textarea></label>
            ${draft.ideas.map((i, n) => `
              <fieldset data-idea="${n}">
                <legend>${escape(i.title)}</legend>
                <label>Idea title<input data-idea-field="title" value="${escape(i.title)}"></label>
                <label>Company or ticker<input data-idea-field="ticker" value="${escape(i.ticker)}"></label>
                <label>Idea type<select data-idea-field="idea_type">${types.map(t => `<option value="${t}"${i.idea_type === t ? ' selected' : ''}>${escape(label(t))}</option>`).join('')}</select></label>
                <label>Position activity<input data-idea-field="activity" value="${escape(i.activity)}"></label>
                <label>Summary<textarea data-idea-field="summary">${escape(i.summary)}</textarea></label>
                <details>
                  <summary>Update a comparison with an earlier letter</summary>
                  <label>What changed<textarea data-idea-field="evolution">${escape(i.evolution)}</textarea></label>
                  <label>Earlier published letter ID<input data-idea-field="compared_letter_id" value="${escape(i.compared_letter_id)}"></label>
                </details>
              </fieldset>`).join('')}
            <details><summary>Completeness checklist &amp; draft evidence</summary><pre>${escape(JSON.stringify({ checklist: draft.checklist, ideas: draft.ideas.map(i => ({ title: i.title, evidence: i.evidence })) }, null, 2))}</pre></details>
            <fieldset class="fl-checks"><legend>Editorial review</legend>${Object.entries(checks).map(([key, text]) => `<label><input type="checkbox" name="${key}">${escape(text)}</label>`).join('')}</fieldset>
            <div class="fl-dialog-actions">
              <button type="button" data-save>Save new revision</button>
              <button type="button" data-publish class="fl-primary">Publish selected revision</button>
            </div>` : '<p class="fl-notice">No summary draft yet. This letter is queued for full document synthesis.</p>'}
          <details>
            <summary>Resolve an archive issue</summary>
            <label>Issue<select data-kind>${['identity', 'extraction', 'duplicate_sources', 'date'].map(k => `<option value="${k}">${escape(label(k))}</option>`).join('')}</select></label>
            <label>Decision and supporting evidence<textarea data-reason></textarea></label>
            <label>Verified letter date (leave blank if unavailable)<input type="date" data-date></label>
            <button type="button" data-resolve>Record review decision</button>
          </details>
          <p class="fl-dialog-status" role="status"></p>`;
        dialog.querySelector('[data-close]').onclick = () => dialog.close();
        const status = dialog.querySelector('.fl-dialog-status');
        const busy = async fn => {
          try {
            status.textContent = 'Saving…';
            await fn();
          } catch (error) {
            status.textContent = error.message;
          }
        };
        dialog.querySelector('[data-resolve]').onclick = () => busy(async () => {
          const kind = dialog.querySelector('[data-kind]').value;
          await api({}, {
            action: kind === 'date' ? 'date' : 'resolve',
            letter_id: letterId,
            kind,
            reason: dialog.querySelector('[data-reason]').value,
            letter_date: dialog.querySelector('[data-date]').value || null,
          });
          status.textContent = 'Review decision recorded.';
        });
        const select = dialog.querySelector('[data-revision]');
        select.onchange = () => { if (select.value) review(letterId, select.value); };
        if (draft) {
          const readEdits = () => {
            const edited = structuredClone(draft);
            edited.overview = dialog.querySelector('[data-overview]').value;
            dialog.querySelectorAll('[data-idea]').forEach(group => group.querySelectorAll('[data-idea-field]').forEach(el => {
              const idea = edited.ideas[Number(group.dataset.idea)], key = el.dataset.ideaField;
              if (el.value || Object.hasOwn(idea, key)) idea[key] = el.value || (key === 'summary' || key === 'title' ? '' : null);
            }));
            return edited;
          };
          dialog.querySelector('[data-save]').onclick = () => busy(async () => {
            const result = await api({}, { action: 'draft', letter_id: letterId, draft: readEdits() });
            await review(letterId, result.revision_id);
          });
          dialog.querySelector('[data-publish]').onclick = () => busy(async () => {
            if (JSON.stringify(readEdits()) !== JSON.stringify(draft)) throw new Error('Save your changes as a new revision before publishing.');
            const attestations = Object.fromEntries(Object.keys(checks).map(k => [k, dialog.querySelector(`[name="${k}"]`).checked]));
            await api({}, { action: 'publish', letter_id: letterId, revision_id: revision.id, expected_revision: source.source.published_revision, attestations });
            status.textContent = 'Published. The previous revision remains available.';
            source.source.published_revision = revision.id;
            load();
          });
        }
      } catch (error) {
        dialog.innerHTML = `<h2 id="fl-review-title">Review unavailable</h2><p>${escape(error.message)}</p><button data-close type="button">Close</button>`;
        dialog.querySelector('button').onclick = () => dialog.close();
      }
    }

    on(form, 'submit', e => {
      e.preventDefault();
      if (searchTimer) global.clearTimeout(searchTimer);
      if (suggestBox) suggestBox.hidden = true;
      if (params.get('mode') === 'review' && role === 'owner') {
        navigate({ review_q: form.elements.q.value, letter: '', idea: '' });
        return;
      }
      navigate(Object.fromEntries(
        ['q', 'type', 'activity', 'period', 'from', 'to', 'fund']
          .map(k => [k, form.elements[k]?.value || ''])
          .concat([['letter', ''], ['idea', ''], ['mode', '']]),
      ));
    });

    on(searchInput, 'focus', () => {
      renderSuggestions();
    });

    on(searchInput, 'blur', () => {
      global.setTimeout(() => {
        if (suggestBox) suggestBox.hidden = true;
      }, 160);
    });

    on(searchInput, 'keydown', e => {
      if (e.key === 'Escape' && suggestBox && !suggestBox.hidden) {
        suggestBox.hidden = true;
      }
    });

    on(searchInput, 'input', () => {
      renderSuggestions();
      if (searchTimer) global.clearTimeout(searchTimer);
      searchTimer = global.setTimeout(() => {
        if (params.get('mode') === 'review' && role === 'owner') {
          navigate({ review_q: form.elements.q.value, letter: '', idea: '' });
          return;
        }
        navigate({ q: form.elements.q.value, letter: '', idea: '' });
      }, 240);
    });

    const resetAllFilters = () => navigate({
      q: '', type: '', activity: '', period: '', from: '', to: '', fund: '', letter: '', idea: '', mode: '', stack: '', signal: '', focus: '', scope: '', tickers: '',
    });

    on(resetBtn, 'click', resetAllFilters);

    on(form.elements.fund, 'change', () => navigate({ fund: form.elements.fund.value, letter: '', idea: '', mode: '', stack: '' }));
    on(form.elements.period, 'change', () => navigate({ period: form.elements.period.value, letter: '', idea: '', mode: '' }));
    on(form.elements.type, 'change', () => navigate({ type: form.elements.type.value, letter: '', idea: '', mode: '' }));
    on(form.elements.activity, 'change', () => navigate({ activity: form.elements.activity.value, letter: '', idea: '', mode: '' }));
    on(form.elements.signal, 'change', () => {
      const val = form.elements.signal.value || '';
      if (val.startsWith('focus:')) {
        navigate({ focus: val.slice(6), signal: '', scope: '', letter: '', idea: '', mode: '' });
      } else if (val.startsWith('scope:')) {
        navigate({ scope: val.slice(6), signal: '', focus: '', letter: '', idea: '', mode: '' });
      } else {
        navigate({ signal: val, focus: '', scope: '', letter: '', idea: '', mode: '' });
      }
    });
    on(form.elements.from, 'change', () => navigate({ from: form.elements.from.value, letter: '', idea: '', mode: '' }));
    on(form.elements.to, 'change', () => navigate({ to: form.elements.to.value, letter: '', idea: '', mode: '' }));

    on(directory.querySelector('input'), 'input', e => drawDirectory(e.target.value));

    on(root, 'click', e => {
      const target = e.target.closest('a,button');
      if (!target || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (target.dataset.suggestVal !== undefined) {
        e.preventDefault();
        searchInput.value = target.dataset.suggestVal;
        if (suggestBox) suggestBox.hidden = true;
        navigate({ q: searchInput.value.trim(), letter: '', idea: '' });
        return;
      }
      if (target.dataset.clearKey) {
        e.preventDefault();
        navigate({ [target.dataset.clearKey]: '', letter: '', idea: '' });
        return;
      }
      if (target.hasAttribute('data-reset-all')) {
        e.preventDefault();
        resetAllFilters();
        return;
      }
      if (target.dataset.pickTicker !== undefined) {
        e.preventDefault();
        navigate({ tickers: target.dataset.pickTicker, letter: '', idea: '', mode: '' });
        return;
      }
      if (target.dataset.dirSort) {
        e.preventDefault();
        dirSort = target.dataset.dirSort;
        drawDirectory(directory.querySelector('input').value);
        return;
      }
      if (target.dataset.viewMode) {
        e.preventDefault();
        navigate({ view: target.dataset.viewMode, letter: '', idea: '', mode: '' });
        return;
      }
      if (target.hasAttribute('data-fund')) {
        e.preventDefault();
        navigate({ fund: target.dataset.fund, letter: '', idea: '', mode: '', stack: '' });
        return;
      }
      if (target.hasAttribute('data-all-funds')) {
        e.preventDefault();
        navigate({ fund: '', letter: '', idea: '', stack: '' });
        return;
      }
      if (target.dataset.pickLetter) {
        e.preventDefault();
        navigate({ letter: target.dataset.pickLetter, idea: '', stack: '' });
        return;
      }
      if (target.hasAttribute('data-stack-all')) {
        e.preventDefault();
        navigate({ stack: '1', letter: '', idea: '' });
        return;
      }
      if (target.dataset.openLetter) {
        e.preventDefault();
        navigate({
          fund: target.dataset.openFund,
          letter: target.dataset.openLetter,
          idea: target.dataset.openIdea || '',
          view: 'letters',
          stack: '',
        });
        return;
      }
      if (target.dataset.jump) {
        e.preventDefault();
        const destination = new URL(target.href, location.origin).searchParams;
        const targetId = target.dataset.jump;
        const el = root.querySelector(`#${CSS.escape(targetId)}`);
        if (el) {
          const details = el.closest('details');
          if (details) details.open = true;
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          params.set('idea', destination.get('idea') || '');
          remember();
          return;
        }
        navigate({ fund: destination.get('fund'), letter: destination.get('letter'), idea: destination.get('idea') });
        return;
      }
      if (target.hasAttribute('data-more')) load(true);
      if (target.hasAttribute('data-retry')) load();
      if (target.hasAttribute('data-archive')) navigate({ letter: '', idea: '', stack: '' });
      if (target.hasAttribute('data-results')) navigate({ fund: '', letter: '', idea: '', stack: '' });
      if (target.dataset.source) review(target.dataset.source);
      if (target.hasAttribute('data-review-queue')) navigate({ mode: params.get('mode') === 'review' ? '' : 'review', letter: '', idea: '' });
    });

    on(root, 'change', e => {
      if (e.target.matches('.fl-letter-select') && e.target.value) {
        navigate({ letter: e.target.value, idea: '', stack: '' });
      }
    });

    if (!embedded) {
      on(global, 'popstate', async e => {
        params = new URLSearchParams(location.search);
        restoring = true;
        await load();
        for (let n = 1; n < (e.state?.flPages || 1) && next !== null; n++) await load(true);
        restoring = false;
        moreButton();
        global.scrollTo(0, e.state?.flScroll || 0);
      });
    }

    try {
      const [session, catalog] = await Promise.all([api({ action: 'session' }), api({ action: 'funds' })]);
      if (disposed) return;
      role = session.role;
      if (role === 'owner' && Array.isArray(session.book_tickers)) {
        session.book_tickers.forEach(t => bookSet.add(String(t || '').trim().toUpperCase()));
      }
      funds = catalog.funds || [];
      periods = catalog.periods || [];
      tickerSignals = catalog.tickers || [];
      tickerStatsMap.clear();
      tickerSignals.forEach(t => tickerStatsMap.set(t.ticker, t));
      populatePeriodSelect();
      populateSignalSelect();
      const tools = root.querySelector('.fl-owner-tools');
      if (tools) {
        if (role === 'owner') {
          tools.innerHTML = `${embedded ? '' : '<a href="/" class="fl-btn-sm">Dashboard</a>'}<button type="button" class="fl-btn-sm" data-review-queue>Review queue</button>`;
        } else if (session.email && !embedded) {
          tools.innerHTML = `<span class="fl-user-chip">Signed in as ${escape(session.email)}</span>`;
        }
      }
      await load();
      if (role === 'owner' && params.get('review')) await review(params.get('review'));
    } catch (error) {
      showError(error);
    }
    return controller;
  }

  global.FundLettersReader = { mount, unmount: root => states.get(root)?.dispose() };
  if (document.getElementById('fund-letters-app')) mount(document.getElementById('fund-letters-app'));
})(window);
