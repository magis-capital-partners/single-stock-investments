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
  // The reporting quarter and the printed letter date are separate facts; a missing date is never inferred.
  const dateText = item => (item.letter_date ? `Letter dated ${item.letter_date}` : 'Letter date unavailable');
  const period = letter => `${letter.reporting_period || 'Period unavailable'} · ${dateText(letter)}`;

  // Shared workspace state. Every view reads the same object, and it round-trips through the query string
  // (or session storage when embedded in the dashboard), so a view is linkable and back/forward restores it.
  const VIEWS = ['funds', 'ideas', 'ticker'];
  const CHIPS = [
    { id: 'new', label: 'New position', group: 'activity' },
    { id: 'add', label: 'Added', group: 'activity' },
    { id: 'trim', label: 'Reduced', group: 'activity' },
    { id: 'exit', label: 'Exited', group: 'activity' },
    { id: 'short', label: 'Short', group: 'activity' },
    { id: 'first', label: 'First mentioned this quarter', group: 'history' },
    { id: 'quality', label: 'Quality compounders', group: 'theme' },
    { id: 'ma', label: 'M&A compounders', group: 'theme' },
    { id: 'book', label: 'Our book', group: 'book' },
  ];
  const THEME_LABELS = { quality: 'Quality compounder', ma: 'M&A compounder' };
  const CHIP_IDS = CHIPS.map(chip => chip.id);
  const STATE_KEYS = ['view', 'period', 'q', 'f', 'fund', 'letter', 'idea', 'ticker', 'type', 'focus', 'stack', 'mode', 'review_q'];
  const TICKER = /^[A-Z0-9._-]{1,16}$/;

  function readState(search) {
    const params = new URLSearchParams(search || '');
    const chips = new Set(String(params.get('f') || '').split(',').map(s => s.trim().toLowerCase()));
    // Links written before the workspace used activity=, scope=book and tickers=.
    for (const activity of String(params.get('activity') || '').split(',')) chips.add(activity.trim().toLowerCase() === 'cover' ? 'exit' : activity.trim().toLowerCase());
    if (params.get('scope') === 'book') chips.add('book');
    const ticker = String(params.get('ticker') || String(params.get('tickers') || '').split(',')[0] || '').trim().toUpperCase();
    const periodValue = String(params.get('period') || '').trim().toUpperCase();
    return {
      view: VIEWS.includes(params.get('view')) ? params.get('view') : 'funds',
      period: periodValue === 'ALL' ? 'all' : /^\d{4}Q[1-4]$/.test(periodValue) ? periodValue : '',
      q: String(params.get('q') || ''),
      chips: CHIP_IDS.filter(id => chips.has(id)),
      fund: String(params.get('fund') || ''),
      letter: String(params.get('letter') || ''),
      idea: String(params.get('idea') || ''),
      ticker: TICKER.test(ticker) ? ticker : '',
      type: String(params.get('type') || ''),
      focus: ['micro', 'macro', 'mixed'].includes(params.get('focus')) ? params.get('focus') : '',
      stack: params.get('stack') === '1' ? '1' : '',
      mode: params.get('mode') === 'review' ? 'review' : '',
      review_q: String(params.get('review_q') || ''),
    };
  }

  function writeState(state) {
    const params = new URLSearchParams();
    for (const key of STATE_KEYS) {
      const value = key === 'f' ? (state.chips || []).join(',') : state[key];
      if (!value || (key === 'view' && value === 'funds')) continue;
      params.set(key, value);
    }
    return params.toString();
  }

  // A summary's statements: one per line in newer summaries, otherwise its sentences.
  function statements(summary) {
    const text = String(summary || '').trim();
    const lines = text.split('\n').map(line => line.trim()).filter(Boolean);
    if (lines.length > 1) return lines;
    return text.split(/(?<=[.!?])\s+(?=[A-Z0-9"“(])/).map(s => s.trim()).filter(Boolean);
  }

  // Which group emptied a view: the first step of the server's filter-by-filter counts that reached zero.
  function emptiedReason(steps) {
    const list = Array.isArray(steps) ? steps : [];
    const index = list.findIndex(step => !step.count);
    if (index < 0) return null;
    return { key: list[index].key, label: list[index].label, before: index ? list[index - 1].count : null };
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

  const ACTIVITY_LABELS = { new: 'New position', add: 'Added', trim: 'Reduced', exit: 'Exited', short: 'Short', cover: 'Covered', watch: 'Watching' };
  function direction(item) {
    const activity = String(item.activity || '').toLowerCase();
    if (item.idea_type === 'short' || activity === 'short' || activity === 'cover') return ['Short', 'short'];
    if (item.idea_type === 'long') return ['Long', 'long'];
    return [label(item.idea_type), typeTone(item.idea_type)];
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
  const STORE = 'fl-reader-state';

  async function mount(root, options = {}) {
    states.get(root)?.dispose();
    const embedded = Boolean(options.embedded);
    let state = readState(embedded ? sessionStorage.getItem(STORE) || '' : location.search);
    let role = 'reader', workspace = null, workspaceKey = null, next = null, loading = false, sequence = 0, workspaceSequence = 0;
    let disposed = false, observer, pages = 0, restoring = false, fundSort = 'alpha', overlapOpen = false, searchTimer = null;
    const bookSet = new Set((options.bookTickers || []).map(t => String(t || '').trim().toUpperCase()).filter(Boolean));
    const watchlistSet = new Set((options.watchlistTickers || []).map(t => String(t || '').trim().toUpperCase()).filter(Boolean));
    const overlapMap = new Map();

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
      <a class="fl-skip" href="#fl-reading">Skip to research</a>
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
        <button type="button" class="fl-drawer-toggle fl-btn-sm" aria-controls="fl-fund-list" aria-expanded="false">Funds</button>
        <label class="fl-compact-field fl-quarter-field">
          <span class="fl-quarter-label">Quarter</span>
          <select name="period" aria-label="Reporting quarter"><option value="">Latest quarter</option></select>
        </label>
        <form class="fl-filters" role="search">
          <div class="fl-search-field">
            <label class="fl-sr-only" for="fl-search-input">Fund, company, ticker or argument</label>
            <input id="fl-search-input" name="q" type="search" placeholder="Search fund, company, ticker or argument…" autocomplete="off">
            <div class="fl-search-suggest" hidden role="listbox" aria-label="Search suggestions"></div>
          </div>
          <button type="submit" class="fl-sr-only">Search</button>
        </form>
        <div class="fl-view-tabs" role="group" aria-label="View">
          <button type="button" class="fl-view-tab" data-view-mode="funds" aria-pressed="true">By fund</button>
          <button type="button" class="fl-view-tab" data-view-mode="ideas" aria-pressed="false">Ideas</button>
          <button type="button" class="fl-view-tab" data-view-mode="ticker" aria-pressed="false">By ticker</button>
        </div>
        ${embedded ? '<div class="fl-owner-tools"></div>' : ''}
      </div>
      <div class="fl-chipbar" role="group" aria-label="Filters">
        <div class="fl-chip-group" role="group" aria-label="Position activity">
          <span class="fl-chip-label" aria-hidden="true">Position</span>
          ${CHIPS.filter(chip => chip.group === 'activity').map(chip => `<button type="button" class="fl-chip" data-chip="${chip.id}" aria-pressed="false">${escape(chip.label)}</button>`).join('')}
        </div>
        <div class="fl-chip-group" role="group" aria-label="Letter history">
          <button type="button" class="fl-chip" data-chip="first" aria-pressed="false" title="No earlier letter from this fund in the archive names the company">First mentioned this quarter</button>
        </div>
        <div class="fl-chip-group" role="group" aria-label="Theme">
          <span class="fl-chip-label" aria-hidden="true">Theme</span>
          <button type="button" class="fl-chip" data-chip="quality" aria-pressed="false" title="Companies on our compounder lists, or that the letter itself calls a compounder or a high-quality business">Quality compounders</button>
          <button type="button" class="fl-chip" data-chip="ma" aria-pressed="false" title="Serial acquirers on our lists, or companies the letter describes as compounding through acquisitions">M&amp;A compounders</button>
        </div>
        <div class="fl-chip-group" role="group" aria-label="Our holdings" data-owner-only hidden>
          <button type="button" class="fl-chip fl-chip--book" data-chip="book" aria-pressed="false" title="Companies we currently hold. Names only.">Our book</button>
        </div>
        <label class="fl-compact-field fl-type-field">
          <span class="fl-sr-only">Category</span>
          <select name="type" aria-label="Category">
            <option value="">All categories</option>
            <optgroup label="Groups">
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
        <button type="button" data-reset class="fl-reset" hidden>Clear filters</button>
      </div>
      <div class="fl-active-filters" hidden aria-label="Active filters"></div>
      <section class="fl-overlap" aria-label="Companies discussed by more than one fund" hidden></section>
      <div class="fl-grid">
        <aside class="fl-directory" id="fl-fund-list" aria-label="Funds">
          <div class="fl-directory-head">
            <h2>Funds <span class="fl-directory-count"></span></h2>
            <div class="fl-dir-sort" role="group" aria-label="Sort funds">
              <button type="button" class="fl-dir-sort-btn is-active" data-dir-sort="alpha" aria-pressed="true">A–Z</button>
              <button type="button" class="fl-dir-sort-btn" data-dir-sort="count" aria-pressed="false">Most discussed</button>
            </div>
            <button type="button" class="fl-drawer-close fl-btn-ghost" aria-label="Close fund list">Close</button>
          </div>
          <input type="search" aria-label="Find a fund in this list" placeholder="Find a fund…">
          <ul></ul>
        </aside>
        <div class="fl-drawer-scrim" hidden></div>
        <div id="fl-reading" class="fl-reading" tabindex="-1" aria-live="polite">
          <p role="status" class="fl-status">Loading the archive…</p>
        </div>
      </div>
      <dialog aria-labelledby="fl-review-title"></dialog>`;

    const reading = root.querySelector('.fl-reading');
    const form = root.querySelector('form.fl-filters');
    const searchInput = form.elements.q;
    const periodSelect = root.querySelector('select[name="period"]');
    const typeSelect = root.querySelector('select[name="type"]');
    const suggestBox = root.querySelector('.fl-search-suggest');
    const activeFiltersBar = root.querySelector('.fl-active-filters');
    const overlapBar = root.querySelector('.fl-overlap');
    const directory = root.querySelector('.fl-directory');
    const fundList = directory.querySelector('ul');
    const fundFilter = directory.querySelector('input');
    const drawerToggle = root.querySelector('.fl-drawer-toggle');
    const scrim = root.querySelector('.fl-drawer-scrim');
    const dialog = root.querySelector('dialog');
    const resetBtn = root.querySelector('[data-reset]');
    const on = (el, event, fn) => el && el.addEventListener(event, fn, { signal: abort.signal });
    const link = extra => '/fund-letters/?' + writeState({ ...state, ...extra });
    const showError = error => {
      if (!disposed) {
        reading.innerHTML = `<div class="fl-error" role="alert">${escape(error.message)}</div><button type="button" data-retry>Try again</button>`;
      }
    };
    const reviewing = () => state.mode === 'review' && role === 'owner';
    const activeChips = () => state.chips.filter(chip => chip !== 'book' || role === 'owner');
    const currentPeriod = () => state.period || workspace?.period || '';
    const periodName = () => (String(currentPeriod()).toUpperCase() === 'ALL' ? 'all quarters' : currentPeriod() || 'the latest quarter');
    const narrowed = () => Boolean(state.q || activeChips().length || state.ticker || state.type || state.focus);

    // The query every view sends: quarter, search and filters. The book list goes to the API only, never into links.
    function scopeArgs() {
      const args = {};
      const quarter = currentPeriod();
      if (quarter) args.period = String(quarter).toUpperCase() === 'ALL' ? 'all' : quarter;
      if (state.q) args.q = state.q;
      const chips = activeChips();
      if (chips.length) args.f = chips.join(',');
      if (chips.includes('book')) args.book = [...bookSet].join(',');
      if (state.ticker) args.ticker = state.ticker;
      if (state.type) args.type = state.type;
      if (state.focus) args.focus = state.focus;
      return args;
    }
    const scopeKey = () => JSON.stringify({ ...scopeArgs(), period: state.period, book: undefined });

    // The securities an idea was matched to. Mentions that matched none are shown muted and never counted.
    const tickersOf = item => (Array.isArray(item?.tickers) ? item.tickers : []);
    const tickerButton = sym => `<button type="button" class="fl-ticker" data-pick-ticker="${escape(sym)}" title="Every fund's view of ${escape(sym)}">${escape(sym)}</button>`;
    function unresolvedHtml(item) {
      const mentions = Array.isArray(item?.unresolved) ? item.unresolved : [];
      return mentions.length ? `<span class="fl-unresolved" title="Not matched to a security, so not counted in overlap, company or book filters">${escape(mentions.join(', '))}</span>` : '';
    }
    const themeBadges = item => (Array.isArray(item?.themes) ? item.themes : []).filter(theme => THEME_LABELS[theme]).map(theme => badgeHtml(THEME_LABELS[theme], 'neutral')).join('');

    function ideaMetaBadges(item) {
      const out = [];
      const [directionText, directionTone] = direction(item);
      if (directionText) out.push(badgeHtml(directionText, directionTone));
      for (const sym of tickersOf(item)) {
        out.push(tickerButton(sym));
        const overlap = overlapMap.get(sym);
        if (overlap) out.push(badgeHtml(`${overlap.funds} funds`, 'special'));
      }
      out.push(unresolvedHtml(item));
      const activity = String(item.activity || '').toLowerCase();
      if (ACTIVITY_LABELS[activity] && !(activity === 'short' && directionText === 'Short')) out.push(badgeHtml(ACTIVITY_LABELS[activity], activityTone(activity)));
      if (item.first_mentioned) out.push(badgeHtml('First mention', 'macro'));
      out.push(themeBadges(item));
      out.push(bookBadge(tickersOf(item)));
      return out.join('');
    }

    // A fund's several letters count once, and funds publishing a near-identical argument count as one manager.
    const managersText = n => `${n} independent ${Number(n) === 1 ? 'manager' : 'managers'}`;
    const managersBadge = item => (Number(item?.managers) > 1
      ? `<span class="fl-badge fl-badge--special" title="Independent managers discussing this company in the current view">${escape(managersText(item.managers))}</span>`
      : '');

    function bookBadge(tickers) {
      if (role !== 'owner' || !tickers.length) return '';
      if (tickers.some(sym => bookSet.has(sym))) return badgeHtml('Our book', 'add', 'fl-badge--book');
      if (tickers.some(sym => watchlistSet.has(sym))) return badgeHtml('Watchlist', 'macro');
      return '';
    }

    function syncControls() {
      root.querySelectorAll('[data-view-mode]').forEach(btn => {
        const current = btn.dataset.viewMode === state.view && !reviewing();
        btn.classList.toggle('is-active', current);
        btn.setAttribute('aria-pressed', String(current));
      });
      root.querySelectorAll('[data-chip]').forEach(btn => {
        const pressed = state.chips.includes(btn.dataset.chip);
        btn.classList.toggle('is-active', pressed);
        btn.setAttribute('aria-pressed', String(pressed));
      });
      root.querySelector('[data-owner-only]').hidden = role !== 'owner';
      if (document.activeElement !== searchInput) searchInput.value = reviewing() ? state.review_q : state.q;
      searchInput.placeholder = reviewing() ? 'Find a fund or review issue…' : 'Search fund, company, ticker or argument…';
      periodSelect.value = state.period;
      typeSelect.value = state.type;
      for (const el of [periodSelect.closest('label'), root.querySelector('.fl-chipbar'), root.querySelector('.fl-view-tabs')]) el.hidden = reviewing();
      resetBtn.hidden = !narrowed();
      renderActiveFilterPills();
    }

    function renderActiveFilterPills() {
      const pills = [];
      if (state.q && !reviewing()) pills.push({ key: 'q', label: `Search: “${state.q}”` });
      if (state.ticker) pills.push({ key: 'ticker', label: `Company: ${state.ticker}` });
      if (state.view === 'ideas' && state.fund) pills.push({ key: 'fund', label: `Fund: ${workspace?.funds.find(f => f.id === state.fund)?.name || state.fund}` });
      if (state.focus) pills.push({ key: 'focus', label: `Letter focus: ${state.focus}` });
      if (!pills.length || reviewing()) {
        activeFiltersBar.hidden = true;
        activeFiltersBar.innerHTML = '';
        return;
      }
      activeFiltersBar.hidden = false;
      activeFiltersBar.innerHTML = `<span class="fl-active-label">Showing</span>`
        + pills.map(p => `<button type="button" class="fl-filter-pill" data-clear-key="${escape(p.key)}" aria-label="Remove ${escape(p.label)}">${escape(p.label)} <span aria-hidden="true">×</span></button>`).join('')
        + `<button type="button" class="fl-filter-clear-all" data-reset-all>Clear all</button>`;
    }

    function populatePeriodSelect() {
      const quarters = workspace?.periods || [];
      const latest = quarters[0]?.period;
      periodSelect.innerHTML = `<option value="">${latest ? `Latest (${escape(latest)})` : 'Latest quarter'}</option>`
        + quarters.map(p => `<option value="${escape(p.period)}">${escape(p.period)} · ${p.count} ${p.count === 1 ? 'letter' : 'letters'}</option>`).join('')
        + '<option value="all">All quarters</option>';
      periodSelect.value = state.period;
    }

    function buildSearchSuggestions(rawInput) {
      const text = String(rawInput || '');
      const parts = text.split(/\s+/);
      const lastToken = parts[parts.length - 1] || '';
      const prefixText = parts.slice(0, -1).join(' ');
      const withPrefix = token => (prefixText ? `${prefixText} ${token} ` : `${token} `);
      const funds = workspace?.funds || [];
      const overlap = workspace?.overlap || [];
      const items = [];
      if (!lastToken.includes(':')) {
        const q = lastToken.toLowerCase();
        if (!q) return [];
        for (const t of overlap.filter(x => x.ticker.toLowerCase().startsWith(q)).slice(0, 4)) {
          items.push({ value: withPrefix(`ticker:${t.ticker}`), label: `ticker:${t.ticker}`, hint: `${t.funds} funds in ${periodName()}` });
        }
        for (const f of funds.filter(x => x.name.toLowerCase().includes(q) || x.id.includes(q)).slice(0, 4)) {
          items.push({ value: withPrefix(`fund:${f.id}`), label: `fund:${f.id}`, hint: `${f.name} · ${f.discussions} discussions` });
        }
        return items;
      }
      const [rawKey, rawVal = ''] = lastToken.split(':', 2);
      const key = rawKey.toLowerCase();
      const val = rawVal.toLowerCase();
      if (key === 'ticker' || key === 'sym') {
        for (const t of overlap.filter(x => !val || x.ticker.toLowerCase().startsWith(val)).slice(0, 8)) {
          items.push({ value: withPrefix(`ticker:${t.ticker}`), label: `ticker:${t.ticker}`, hint: `${t.funds} funds · ${t.long} long · ${t.short} short` });
        }
      } else if (key === 'type') {
        for (const t of types.filter(x => !val || x.includes(val))) items.push({ value: withPrefix(`type:${t}`), label: `type:${t}`, hint: label(t) });
      } else if (key === 'action' || key === 'activity') {
        for (const a of ['new', 'add', 'trim', 'exit', 'hold', 'short', 'cover'].filter(x => !val || x.startsWith(val))) items.push({ value: withPrefix(`action:${a}`), label: `action:${a}`, hint: ACTIVITY_LABELS[a] || 'Held' });
      } else if (key === 'focus') {
        for (const f of ['micro', 'macro', 'mixed'].filter(x => !val || x.startsWith(val))) items.push({ value: withPrefix(`focus:${f}`), label: `focus:${f}`, hint: `${label(f)} letter focus` });
      } else if (key === 'fund') {
        for (const f of funds.filter(x => !val || x.id.includes(val) || x.name.toLowerCase().includes(val)).slice(0, 8)) items.push({ value: withPrefix(`fund:${f.id}`), label: `fund:${f.id}`, hint: f.name });
      }
      return items.slice(0, 8);
    }

    function renderSuggestions() {
      if (!suggestBox || document.activeElement !== searchInput || reviewing()) {
        if (suggestBox) suggestBox.hidden = true;
        return;
      }
      const list = buildSearchSuggestions(searchInput.value);
      if (!list.length) {
        suggestBox.hidden = true;
        return;
      }
      suggestBox.hidden = false;
      suggestBox.innerHTML = `<div class="fl-suggest-head">Suggestions <span>also try type:short or action:new</span></div>`
        + list.map(item => `
          <button type="button" class="fl-suggest-item" role="option" data-suggest-val="${escape(item.value)}">
            <code class="fl-suggest-code">${escape(item.label)}</code>
            <span class="fl-suggest-hint">${escape(item.hint)}</span>
          </button>`).join('');
    }

    function remember() {
      if (embedded) sessionStorage.setItem(STORE, writeState(state));
      else history.replaceState({ ...history.state, flScroll: global.scrollY, flPages: pages, flListScroll: directory.scrollTop }, '', location.href);
    }

    // Changing the quarter, search or filters reloads the fund list; choosing a fund, letter or view only swaps the pane.
    function navigate(change, push = true) {
      remember();
      state = { ...state, ...change };
      if (embedded) sessionStorage.setItem(STORE, writeState(state));
      else history[push ? 'pushState' : 'replaceState']({ flScroll: 0, flListScroll: directory.scrollTop }, '', '?' + writeState(state));
      refresh();
    }

    async function refresh(restoreScroll = null) {
      syncControls();
      if (!reviewing() && scopeKey() !== workspaceKey) await loadWorkspace();
      else drawFundList();
      await load(false, restoreScroll);
    }

    async function loadWorkspace() {
      const ticket = ++workspaceSequence;
      const key = scopeKey();
      const { period: _period, ...rest } = scopeArgs();
      try {
        const data = await api({ action: 'workspace', ...rest, ...(state.period ? { period: state.period } : {}) });
        if (ticket !== workspaceSequence || disposed) return;
        workspace = data;
        workspaceKey = key;
        overlapMap.clear();
        for (const row of data.overlap || []) overlapMap.set(row.ticker, row);
        populatePeriodSelect();
        const scroll = directory.scrollTop;
        drawFundList();
        directory.scrollTop = scroll;
        drawOverlap();
        syncControls();
      } catch (error) {
        if (ticket === workspaceSequence) fundList.innerHTML = `<li class="fl-dir-empty" role="alert">${escape(error.message)}</li>`;
      }
    }

    function emptyMessage(steps, noun) {
      const reason = emptiedReason(steps);
      if (!reason) return `<p>No ${noun} match this view.</p>`;
      if (reason.key === 'period') return `<p>No published letters in ${escape(periodName())} yet.</p><button type="button" class="fl-btn-sm" data-clear-group="period">Show all quarters</button>`;
      const before = reason.before === null ? '' : ` It removed the last ${reason.before.toLocaleString('en-US')} ${reason.before === 1 ? 'discussion' : 'discussions'}.`;
      return `<p><strong>${escape(reason.label)}</strong> left nothing to show.${escape(before)}</p>`
        + `<button type="button" class="fl-btn-sm" data-clear-group="${escape(reason.key)}">Remove this filter</button>`;
    }

    function drawFundList() {
      const funds = workspace?.funds || [];
      const query = fundFilter.value.toLowerCase().trim();
      const rows = funds.filter(f => !query || f.name.toLowerCase().includes(query) || f.id.includes(query));
      rows.sort((a, b) => (fundSort === 'count' ? b.discussions - a.discussions : 0) || a.name.localeCompare(b.name));
      directory.querySelectorAll('[data-dir-sort]').forEach(btn => {
        btn.classList.toggle('is-active', btn.dataset.dirSort === fundSort);
        btn.setAttribute('aria-pressed', String(btn.dataset.dirSort === fundSort));
      });
      directory.querySelector('.fl-directory-count').textContent = workspace ? `(${funds.length})` : '';
      drawerToggle.textContent = workspace ? `Funds (${funds.length})` : 'Funds';
      if (!workspace) return;
      if (!funds.length) {
        fundList.innerHTML = `<li class="fl-dir-empty">${emptyMessage(workspace.emptied_by, 'funds')}</li>`;
        return;
      }
      const all = workspace.totals || {};
      const allPeriod = String(workspace.period).toUpperCase() === 'ALL';
      fundList.innerHTML = `
        <li>
          <a href="${escape(link({ fund: '', letter: '', idea: '', mode: '', stack: '' }))}" data-fund=""${!state.fund ? ' aria-current="true"' : ''}>
            <span class="fl-dir-row-top"><strong>All funds</strong><span class="fl-dir-pill" title="Discussions">${Number(all.discussions || 0).toLocaleString('en-US')}</span></span>
            <small>${all.letters || 0} ${all.letters === 1 ? 'letter' : 'letters'} · ${escape(periodName())}</small>
          </a>
        </li>` + rows.map(f => `
        <li>
          <a href="${escape(link({ fund: f.id, letter: '', idea: '', mode: '', stack: '' }))}" data-fund="${escape(f.id)}"${state.fund === f.id ? ' aria-current="true"' : ''}>
            <span class="fl-dir-row-top"><strong>${escape(f.name)}</strong><span class="fl-dir-pill" title="${f.discussions} ${f.discussions === 1 ? 'discussion' : 'discussions'}">${f.discussions}</span></span>
            <small>${allPeriod || f.letters > 1
              ? `${f.letters} ${f.letters === 1 ? 'letter' : 'letters'}${allPeriod ? ` · latest ${escape(f.reporting_period || 'undated')}` : ` · ${escape(f.reporting_period || '')}`}`
              : `${escape(f.reporting_period || 'Period unavailable')} · ${f.letter_date ? escape(f.letter_date) : 'date unavailable'}`}</small>
          </a>
        </li>`).join('') + (rows.length ? '' : '<li class="fl-dir-empty"><p>No fund in this list matches that name.</p></li>');
    }

    function markCurrentFund() {
      fundList.querySelectorAll('a[data-fund]').forEach(a => {
        if (a.dataset.fund === state.fund) a.setAttribute('aria-current', 'true');
        else a.removeAttribute('aria-current');
      });
    }

    function drawOverlap() {
      const rows = workspace?.overlap || [];
      if (!rows.length || reviewing()) {
        overlapBar.hidden = true;
        overlapBar.innerHTML = '';
        return;
      }
      const shown = overlapOpen ? rows : rows.slice(0, 8);
      overlapBar.hidden = false;
      const unresolved = workspace?.totals?.unresolved || 0;
      overlapBar.innerHTML = `
        <span class="fl-meta">Discussed by 2+ independent managers · ${escape(periodName())}${unresolved ? ` · <span title="Ticker text in these letters that matched no security, such as an acronym or a symbol another company uses today">${unresolved} unmatched ${unresolved === 1 ? 'mention' : 'mentions'} not counted</span>` : ''}</span>
        <ul class="fl-overlap-list">
          ${shown.map(row => {
            const contested = row.long > 0 && row.short > 0;
            const inBook = role === 'owner' && bookSet.has(row.ticker);
            return `<li><button type="button" class="fl-overlap-item${contested ? ' is-contested' : ''}${inBook ? ' is-book' : ''}${state.ticker === row.ticker ? ' is-active' : ''}"
              data-pick-ticker="${escape(row.ticker)}" aria-pressed="${state.ticker === row.ticker}"
              title="${row.name ? `${escape(row.name)} · ` : ''}${managersText(row.managers)} · ${row.long} long · ${row.short} short or selling${inBook ? ' · in our book' : ''}">
              <strong>${escape(row.ticker)}</strong> <span>${row.managers}</span></button></li>`;
          }).join('<li aria-hidden="true" class="fl-overlap-dot">·</li>')}
        </ul>
        ${rows.length > 8 ? `<button type="button" class="fl-overlap-more" data-overlap-toggle aria-expanded="${overlapOpen}">${overlapOpen ? 'Show fewer' : `Show all ${rows.length}`}</button>` : ''}`;
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

    // A small number after a statement names the passage of the original letter it rests on.
    // Owners can open that passage; everyone else sees where in the letter it comes from.
    function citeHtml(letter, passage, target) {
      if (!passage) return '';
      const total = letter.coverage?.sections;
      const where = `passage ${passage}${total ? ` of ${total}` : ''} of the original letter`;
      if (role !== 'owner') return `<span class="fl-cite" title="From ${escape(where)}" aria-label="From ${escape(where)}">${passage}</span>`;
      const data = Object.entries(target).map(([key, value]) => ` data-cite-${key}="${escape(value)}"`).join('');
      return `<button type="button" class="fl-cite" data-cite="${escape(letter.id)}" data-cite-passage="${passage}"${data} title="Open ${escape(where)}" aria-label="Open ${escape(where)}">${passage}</button>`;
    }

    // Newer summaries keep one statement per line with a passage number for each.
    // Statements that rest on the same passage share one marker.
    function citedProse(letter, idea) {
      const cites = Array.isArray(idea.cites) ? idea.cites : null;
      if (!cites) return paragraphs(idea.summary);
      let line = 0;
      return String(idea.summary || '').split(/\n\s*\n/).filter(block => block.trim()).map(block => {
        const lines = block.split('\n').filter(text => text.trim());
        let run = [];
        const parts = lines.map((text, index) => {
          const passage = cites[line];
          run.push(line);
          line += 1;
          const closes = index === lines.length - 1 || cites[line] !== passage;
          const marker = closes ? citeHtml(letter, passage, { idea: idea.id, lines: run.join(',') }) : '';
          if (closes) run = [];
          return `${escape(text.trim())}${marker}`;
        });
        return `<p>${parts.join(' ')}</p>`;
      }).join('');
    }

    // In newer summaries the overview is made of statements from the ideas below, so each one
    // carries the passage marker it has there. Any other text is shown as it is.
    function citedOverview(letter) {
      const known = [];
      for (const idea of Array.isArray(letter.ideas) ? letter.ideas : []) {
        if (!Array.isArray(idea.cites)) continue;
        String(idea.summary || '').split('\n').map(text => text.trim()).filter(Boolean).forEach((text, line) => {
          if (idea.cites[line]) known.push({ text, passage: idea.cites[line], idea: idea.id, line });
        });
      }
      if (!known.length) return paragraphs(letter.overview);
      known.sort((a, b) => b.text.length - a.text.length);
      return String(letter.overview || '').split(/\n\s*\n/).filter(block => block.trim()).map(block => {
        const pieces = [];
        let rest = block.trim();
        while (rest) {
          const hit = known.find(item => rest.startsWith(item.text));
          if (hit) {
            pieces.push({ text: hit.text, hit });
            rest = rest.slice(hit.text.length).trimStart();
            continue;
          }
          const next = known.map(item => rest.indexOf(item.text)).filter(at => at > 0).sort((a, b) => a - b)[0];
          pieces.push({ text: rest.slice(0, next || rest.length).trim() });
          rest = next ? rest.slice(next) : '';
        }
        let run = [];
        return `<p>${pieces.map((piece, index) => {
          if (!piece.hit) return escape(piece.text);
          const following = pieces[index + 1]?.hit;
          run.push(piece.hit.line);
          const closes = !following || following.passage !== piece.hit.passage || following.idea !== piece.hit.idea;
          const marker = closes ? citeHtml(letter, piece.hit.passage, { idea: piece.hit.idea, lines: run.join(',') }) : '';
          if (closes) run = [];
          return `${escape(piece.text)}${marker}`;
        }).join(' ')}</p>`;
      }).join('');
    }

    // Tables the summarizer transcribed from the letter, under the letter's own column headings.
    // `ideaId` picks the tables that belong to one idea; null picks the ones about the fund itself.
    function tablesHtml(letter, ideaId) {
      const tables = (Array.isArray(letter.tables) ? letter.tables : []).filter(table => (table.idea_id || null) === ideaId);
      return tables.map(table => `
        <figure class="fl-table">
          <figcaption>${escape(table.title || 'From a table in the letter')}${citeHtml(letter, table.passage, { table: table.index })}</figcaption>
          <div class="fl-table-scroll" tabindex="0" role="group" aria-label="${escape(table.title || 'Table from the letter')}">
            <table>
              <thead><tr><td></td>${table.columns.map(column => `<th scope="col">${escape(column)}</th>`).join('')}</tr></thead>
              <tbody>
                ${table.rows.map(row => `<tr><th scope="row">${escape(row.label)}</th>${row.values.map(value => `<td${/^[-(]/.test(value) ? ' class="fl-neg"' : ''}>${escape(value)}</td>`).join('')}</tr>`).join('')}
              </tbody>
            </table>
          </div>
        </figure>`).join('');
    }

    function fundTablesHtml(letter) {
      const html = tablesHtml(letter, null);
      if (!html) return '';
      return `
        <section class="fl-tables" aria-label="Figures from the letter's tables">
          <h4 class="fl-meta">Figures from the letter's tables</h4>
          ${html}
        </section>`;
    }

    function coverageHtml(letter) {
      const c = letter.coverage;
      if (!c || !c.sections) return '';
      const count = (n, one, many) => `${Number(n).toLocaleString('en-US')} ${n === 1 ? one : many}`;
      const parts = [];
      if (c.statements) parts.push(`${count(c.statements, 'statement', 'statements')}${c.topics ? ` on ${count(c.topics, 'topic', 'topics')}` : ''}`);
      if (c.tables) parts.push(`${count(c.tables, 'table', 'tables')} transcribed${c.figures ? ` (${count(c.figures, 'figure', 'figures')})` : ''}`);
      if (c.sections_cited) parts.push(`drawn from ${c.sections_cited} of ${count(c.sections, 'passage', 'passages')} of the original`);
      if (c.summary_words && c.source_words) parts.push(`${Number(c.summary_words).toLocaleString('en-US')} words on a ${Number(c.source_words).toLocaleString('en-US')}-word letter`);
      if (!parts.length) return '';
      const omitted = c.tables_omitted ? ` ${count(c.tables_omitted, 'other table or chart', 'other tables or charts')} could not be transcribed with certainty and ${c.tables_omitted === 1 ? 'is' : 'are'} in the original only.` : '';
      return `<p class="fl-coverage"><strong>Coverage.</strong> ${escape(parts.join(' · '))}. The small numbers mark the passage each statement comes from${role === 'owner' ? '; select one to read it in the original' : ''}.${escape(omitted)}</p>`;
    }

    function whatChangedHtml(item, fundId) {
      const prior = item.prior;
      if (!prior && !item.evolution) return '';
      const then = prior ? statements(prior.summary).slice(0, 3) : [];
      const priorActivity = prior && ACTIVITY_LABELS[String(prior.activity || '').toLowerCase()];
      const nowActivity = ACTIVITY_LABELS[String(item.activity || '').toLowerCase()];
      return `
        <details class="fl-expander fl-what-changed">
          <summary>What changed${prior ? ` since ${escape(prior.reporting_period || 'the earlier letter')}` : ''}</summary>
          <div class="fl-expander-body">
            ${item.evolution ? paragraphs(item.evolution) : ''}
            ${prior ? `
            <p class="fl-change-row">
              <span class="fl-meta">Then</span> ${escape(prior.reporting_period || 'Earlier')} · ${escape(dateText(prior))}${priorActivity ? ` · ${badgeHtml(priorActivity, activityTone(prior.activity))}` : ''}
              <span class="fl-meta">Now</span> ${escape(item.reporting_period || '')}${nowActivity ? ` · ${badgeHtml(nowActivity, activityTone(item.activity))}` : ''}
            </p>
            <blockquote class="fl-prior">${then.map(text => `<p>${escape(text)}</p>`).join('')}</blockquote>
            <a href="${escape(link({ view: 'funds', fund: fundId, letter: prior.letter_id, idea: '' }))}" data-open-fund="${escape(fundId)}" data-open-letter="${escape(prior.letter_id)}">Read the ${escape(prior.reporting_period || 'earlier')} letter →</a>` : ''}
          </div>
        </details>`;
    }

    // An idea as a card: company, direction, activity and book badges, a one-line headline and a short
    // argument from the summary, with the full argument and the change since the fund's last discussion on demand.
    function ideaCardHtml(item) {
      const parts = statements(item.summary);
      const [headline, ...rest] = parts;
      const argument = rest.slice(0, 3);
      const longer = rest.length > 3;
      const tickers = tickersOf(item);
      return `
        <article class="fl-idea-card" id="fl-card-${escape(item.letter_id)}-${escape(item.id)}">
          <header class="fl-idea-card-head">
            <div class="fl-idea-card-id">
              ${tickers.map(tickerButton).join('')}
              <h3><a href="${escape(link({ view: 'funds', fund: item.fund_id, letter: item.letter_id, idea: item.id }))}"
                data-open-letter="${escape(item.letter_id)}" data-open-fund="${escape(item.fund_id)}" data-open-idea="${escape(item.id)}">${escape(item.title)}</a></h3>
            </div>
            <div class="fl-idea-card-badges">${(() => {
              const [directionText, directionTone] = direction(item);
              const activity = String(item.activity || '').toLowerCase();
              return [
                badgeHtml(directionText, directionTone),
                ACTIVITY_LABELS[activity] && !(activity === 'short' && directionText === 'Short') ? badgeHtml(ACTIVITY_LABELS[activity], activityTone(activity)) : '',
                item.first_mentioned ? badgeHtml('First mention', 'macro') : '',
                managersBadge(item),
                themeBadges(item),
                bookBadge(tickers),
                unresolvedHtml(item),
              ].join('');
            })()}</div>
          </header>
          ${headline ? `<p class="fl-idea-headline">${escape(headline)}</p>` : ''}
          ${argument.length ? `<div class="fl-idea-argument">${argument.map(text => `<p>${escape(text)}</p>`).join('')}</div>` : ''}
          ${longer ? `
          <details class="fl-expander">
            <summary>Read full argument</summary>
            <div class="fl-expander-body fl-idea-prose">${paragraphs(item.summary)}</div>
          </details>` : ''}
          ${whatChangedHtml(item, item.fund_id)}
          <footer class="fl-idea-card-foot">
            <button type="button" class="fl-fund-tag" data-fund="${escape(item.fund_id)}">${escape(item.fund)}</button>
            <span class="fl-period-tag">${escape(item.reporting_period || 'Period unavailable')}</span>
            <span class="fl-date-inline">${escape(dateText(item))}</span>
            <span class="fl-source-type">Fund letter</span>
          </footer>
        </article>`;
    }

    const STANCE_SECTIONS = [['long', 'Long'], ['opposing', 'Short or selling'], ['other', 'Other discussions']];
    const entriesOf = quarter => STANCE_SECTIONS.flatMap(([key]) => quarter[key] || []);

    function companyAlsoHtml(entry) {
      if (!entry.also?.length) return '';
      return `<p class="fl-company-also">Same argument also published by ${entry.also.map(other =>
        `<button type="button" class="fl-fund-tag" data-fund="${escape(other.fund_id)}">${escape(other.fund)}</button>`).join(', ')}, so counted as one manager.</p>`;
    }

    // A fund's argument this quarter in full, with its other discussions of the company on demand.
    function companyEntryHtml(entry, period) {
      return `
        <div class="fl-company-entry">
          ${ideaCardHtml(entry.idea)}
          ${companyAlsoHtml(entry)}
          ${entry.more?.length ? `
          <details class="fl-expander fl-company-more">
            <summary>${entry.more.length} more ${entry.more.length === 1 ? 'discussion' : 'discussions'} from ${escape(entry.idea.fund)} in ${escape(period || 'this quarter')}</summary>
            <div class="fl-expander-body fl-idea-card-list">${entry.more.map(ideaCardHtml).join('')}</div>
          </details>` : ''}
        </div>`;
    }

    // An earlier quarter's entry on one line: fund, stance and the argument's first statement.
    function companyBriefHtml(entry) {
      const item = entry.idea;
      const [directionText, directionTone] = direction(item);
      const activity = String(item.activity || '').toLowerCase();
      const headline = statements(item.summary)[0] || item.title;
      return `
        <li class="fl-company-brief">
          <button type="button" class="fl-fund-tag" data-fund="${escape(item.fund_id)}">${escape(item.fund)}</button>
          ${badgeHtml(directionText, directionTone)}
          ${ACTIVITY_LABELS[activity] && !(activity === 'short' && directionText === 'Short') ? badgeHtml(ACTIVITY_LABELS[activity], activityTone(activity)) : ''}
          <a href="${escape(link({ view: 'funds', fund: item.fund_id, letter: item.letter_id, idea: item.id }))}"
            data-open-letter="${escape(item.letter_id)}" data-open-fund="${escape(item.fund_id)}" data-open-idea="${escape(item.id)}">${escape(headline)}</a>
          ${entry.also?.length ? `<span class="fl-company-brief-also">Also published by ${escape(entry.also.map(other => other.fund).join(', '))}</span>` : ''}
        </li>`;
    }

    function companyOverviewHtml(data) {
      const rows = data.companies || [];
      const shared = rows.filter(row => row.managers > 1).length;
      if (!rows.length) return `<div class="fl-empty"><h2>No companies match</h2>${emptyMessage(data.emptied_by, 'discussions')}</div>`;
      return `
        <header class="fl-section-head">
          <div>
            <div class="fl-meta">By ticker · ${escape(periodName())}</div>
            <h2>${narrowed() ? 'Companies matching your filters' : 'Companies discussed'}</h2>
          </div>
          <span class="fl-date">${count(rows.length, 'company', 'companies')}${shared ? ` · ${shared} with 2+ managers` : ''}</span>
        </header>
        <section aria-label="Companies">
        <p class="fl-notice">Ranked by independent managers. A fund's several letters count once, and funds publishing a near-identical argument count as one manager.</p>
        <ol class="fl-company-list">
          ${rows.map(row => `
          <li><button type="button" class="fl-company-row${role === 'owner' && bookSet.has(row.ticker) ? ' is-book' : ''}" data-pick-ticker="${escape(row.ticker)}">
            <strong class="fl-company-ticker">${escape(row.ticker)}</strong>
            <span class="fl-company-name">${escape(row.name || '')}</span>
            <span class="fl-company-counts">
              <span>${escape(managersText(row.managers))}</span>
              <span class="is-long">${row.long ? `${row.long} long` : ''}</span>
              <span class="is-opposing">${row.short ? `${row.short} short or selling` : ''}</span>
            </span>
          </button></li>`).join('')}
        </ol>
        </section>`;
    }

    // Every manager's argument on one company: the chosen quarter split into longs, shorts or sellers and
    // other mentions, then the company's earlier quarters for context.
    function companyHtml(data) {
      const quarters = data.quarters || [];
      const current = data.current ? quarters[0] : null;
      const earlier = current ? quarters.slice(1) : quarters;
      const allQuarters = String(data.period).toUpperCase() === 'ALL';
      const where = allQuarters ? 'across all quarters' : `in ${data.period}`;
      const sideHtml = (key, title) => {
        const entries = current?.[key] || [];
        if (!entries.length) return key === 'other' ? '' : `<section class="fl-company-side is-${key}"><h4>${title}</h4><p class="fl-company-none">No fund ${key === 'long' ? 'argued the long case' : 'was short or selling'} ${escape(allQuarters ? `in ${current.period}` : where)}.</p></section>`;
        return `<section class="fl-company-side is-${key}"><h4>${title} <span>(${entries.length})</span></h4>${entries.map(entry => companyEntryHtml(entry, current.period)).join('')}</section>`;
      };
      return `
        <header class="fl-section-head fl-company-head">
          <div>
            <button type="button" class="fl-back-btn" data-ticker-overview>← All companies</button>
            <div class="fl-meta">By ticker · ${escape(periodName())}</div>
            <h2>${escape(data.ticker)}${data.name ? ` <span class="fl-company-title-name">${escape(data.name)}</span>` : ''}</h2>
          </div>
          <p class="fl-company-headline"><strong>${Number(data.managers || 0)}</strong> ${Number(data.managers) === 1 ? 'independent manager' : 'independent managers'} ${escape(where)}${state.q || activeChips().length || state.type || state.focus ? ' matching the filters' : ''}</p>
        </header>
        ${current ? `
        <section class="fl-company-quarter" aria-label="${escape(current.period || 'Undated')}">
          ${allQuarters ? `<h3 class="fl-group-heading">Latest: ${escape(current.period || 'Undated')} <span>(${escape(managersText(current.managers))})</span></h3>` : ''}
          <div class="fl-company-columns">
            ${sideHtml('long', 'Long')}
            ${sideHtml('opposing', 'Short or selling')}
          </div>
          ${sideHtml('other', 'Other discussions')}
        </section>` : `<div class="fl-empty"><h2>No fund discussed ${escape(data.ticker)} ${escape(where)}</h2>${emptyMessage(data.emptied_by, 'discussions')}</div>`}
        ${earlier.length ? `
        <section class="fl-company-earlier" aria-label="Earlier quarters">
          <h3 class="fl-group-heading">${current ? 'Earlier quarters' : 'Other quarters'}</h3>
          ${earlier.map(quarter => `
          <div class="fl-company-earlier-quarter">
            <h4>${escape(quarter.period || 'Undated')} <span>${escape(managersText(quarter.managers))}</span></h4>
            <ul>${entriesOf(quarter).map(companyBriefHtml).join('')}</ul>
          </div>`).join('')}
        </section>` : ''}`;
    }

    function letterCardHtml(letter) {
      const ideas = Array.isArray(letter.ideas) ? letter.ideas : [];
      const matched = ideas.filter(i => i.matches);
      const primaryIdeas = ideas.filter(i => i.idea_type !== 'factual_note');
      const chipIdeas = (matched.length ? matched : primaryIdeas.length ? primaryIdeas : ideas).slice(0, 5);
      const previewParagraph = String(letter.overview || '').split(/\n\s*\n/).filter(Boolean)[0] || '';
      const hasBookOverlap = role === 'owner' && ideas.some(i => tickersOf(i).some(sym => bookSet.has(sym)));
      return `
        <article class="fl-letter-card" id="fl-card-${escape(letter.id)}">
          <header class="fl-letter-card-head">
            <div class="fl-letter-card-meta">
              <button type="button" class="fl-fund-tag" data-fund="${escape(letter.fund_id)}">${escape(letter.fund)}</button>
              <span class="fl-period-tag">${escape(letter.reporting_period || 'Period unavailable')}</span>
              <span class="fl-date-inline">${escape(dateText(letter))}</span>
              ${letter.focus ? badgeHtml(label(letter.focus), letter.focus === 'macro' ? 'macro' : letter.focus === 'mixed' ? 'special' : 'neutral') : ''}
              ${hasBookOverlap ? badgeHtml('Our book', 'add', 'fl-badge--book') : ''}
            </div>
            <div class="fl-letter-card-actions">
              ${role === 'owner' ? `<button type="button" class="fl-btn-ghost" data-original="${escape(letter.id)}">Original</button>
              <button type="button" class="fl-btn-ghost" data-source="${escape(letter.id)}">Edit</button>` : ''}
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
          <div class="fl-card-ideas" aria-label="${matched.length ? 'Matching discussions' : 'Discussed in this letter'}">
            ${chipIdeas.map(i => {
              const sym = tickersOf(i).join(', ');
              const inBook = role === 'owner' && tickersOf(i).some(t => bookSet.has(t));
              return `
              <a class="fl-idea-chip${inBook ? ' is-book' : ''}"
                 href="${escape(link({ fund: letter.fund_id, letter: letter.id, idea: i.id }))}"
                 data-open-letter="${escape(letter.id)}"
                 data-open-fund="${escape(letter.fund_id)}"
                 data-open-idea="${escape(i.id)}">
                ${sym ? `<strong class="fl-chip-ticker">${escape(sym)}</strong>` : ''}
                <span>${escape(i.title)}</span>
                ${ACTIVITY_LABELS[i.activity] ? `<em class="fl-chip-act">${escape(ACTIVITY_LABELS[i.activity])}</em>` : ''}
              </a>`;
            }).join('')}
            ${(matched.length || ideas.length) > chipIdeas.length ? `<span class="fl-more-ideas">+${(matched.length || ideas.length) - chipIdeas.length} more</span>` : ''}
          </div>` : ''}
        </article>`;
    }


    function ideaSectionHtml(letter, i) {
      return `
        <section class="fl-idea${i.matches ? ' is-match' : ''}" id="fl-idea-${escape(letter.id)}-${escape(i.id)}">
          <div class="fl-idea-badges">${ideaMetaBadges(i)}</div>
          <h4>${escape(i.title)}</h4>
          <div class="fl-idea-prose">${citedProse(letter, i)}</div>
          ${tablesHtml(letter, i.id)}
          ${whatChangedHtml({ ...i, reporting_period: letter.reporting_period }, letter.fund_id)}
        </section>`;
    }

    function ideaGroupsHtml(letter, ideas) {
      const companyIdeas = ideas.filter(i => !MACRO_TYPES.has(i.idea_type) && i.idea_type !== 'factual_note');
      const macroIdeas = ideas.filter(i => MACRO_TYPES.has(i.idea_type));
      const factualIdeas = ideas.filter(i => i.idea_type === 'factual_note');
      const hasMultipleGroups = [companyIdeas.length > 0, macroIdeas.length > 0, factualIdeas.length > 0].filter(Boolean).length > 1;
      return `
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
          </div>`) : ''}`;
    }

    // With filters active, the discussions that match lead and the rest of the letter stays one click away.
    function letterHtml(letter) {
      const ideas = Array.isArray(letter.ideas) ? letter.ideas : [];
      const filtered = ideas.some(i => i.matches !== undefined);
      const matching = filtered ? ideas.filter(i => i.matches) : ideas;
      const others = filtered ? ideas.filter(i => !i.matches) : [];
      const focusLabel = letter.focus || letter.stance?.focus || '';

      return `
        <article class="fl-letter" id="fl-letter-${escape(letter.id)}">
          <header class="fl-letter-head">
            <div>
              <div class="fl-letter-eyebrow">
                <span class="fl-period-tag">${escape(letter.reporting_period || 'Period unavailable')}</span>
                <span class="fl-date">${escape(dateText(letter))}</span>
                ${focusLabel ? badgeHtml(`${label(focusLabel)} focus`, focusLabel === 'macro' ? 'macro' : focusLabel === 'mixed' ? 'special' : 'neutral') : ''}
              </div>
              <h3>${escape(letter.headline || `${letter.fund} · ${letter.reporting_period || 'Letter'}`)}</h3>
            </div>
            ${role === 'owner' ? `<div class="fl-letter-owner-actions">
              <button type="button" class="fl-btn-sm" data-original="${escape(letter.id)}">Read original</button>
              <button type="button" class="fl-btn-sm" data-source="${escape(letter.id)}">Source &amp; revisions</button>
            </div>` : ''}
          </header>

          <div class="fl-overview">${citedOverview(letter)}</div>

          ${fundTablesHtml(letter)}

          ${stanceHtml(letter)}

          ${ideas.length ? `
          <nav class="fl-contents" aria-label="Ideas in this letter">
            <h4>In this letter (${ideas.length})${filtered ? ` · ${matching.length} matching` : ''}</h4>
            <ul class="fl-contents-chips">
              ${ideas.map(i => `
                <li>
                  <a class="fl-idea-chip${i.matches ? ' is-match' : ''}"
                     href="${escape(link({ fund: letter.fund_id, letter: letter.id, idea: i.id }))}"
                     data-jump="fl-idea-${escape(letter.id)}-${escape(i.id)}">
                    ${i.ticker ? `<strong class="fl-chip-ticker">${escape(i.ticker)}</strong>` : ''}
                    <span>${escape(i.title)}</span>
                    ${ACTIVITY_LABELS[i.activity] ? `<em class="fl-chip-act">${escape(ACTIVITY_LABELS[i.activity])}</em>` : ''}
                  </a>
                </li>`).join('')}
            </ul>
          </nav>` : ''}

          ${filtered && matching.length ? `<h4 class="fl-group-heading fl-match-heading">Matching your filters <span>(${matching.length})</span></h4>` : ''}
          ${ideaGroupsHtml(letter, matching)}

          ${others.length ? `
          <details class="fl-other-ideas">
            <summary>${others.length} other ${others.length === 1 ? 'discussion' : 'discussions'} in this letter</summary>
            ${ideaGroupsHtml(letter, others)}
          </details>` : ''}

          ${coverageHtml(letter)}

          <footer class="fl-revision">
            Attributed to ${escape(letter.fund)} · ${escape(letter.reporting_period || 'Period unavailable')} · ${escape(dateText(letter))}${letter.summary_published_at ? ` · Summary published ${escape(letter.summary_published_at.slice(0, 10))}` : ''}${letter.summary_revised_at ? ` · Revision ${escape(letter.summary_revised_at.slice(0, 10))}` : ''}
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
      button.textContent = state.view === 'funds' && state.fund ? 'Load older letters' : 'Load more';
      reading.append(button);
      if ('IntersectionObserver' in global && !restoring) {
        observer = new IntersectionObserver(entries => {
          if (entries.some(e => e.isIntersecting) && !loading) load(true);
        }, { rootMargin: '200px' });
        observer.observe(button);
      }
    }

    const fundName = id => workspace?.funds.find(f => f.id === id)?.name || '';
    const count = (n, one, many) => `${Number(n || 0).toLocaleString('en-US')} ${Number(n) === 1 ? one : many}`;

    async function load(append = false, restoreScroll = null) {
      if (loading && append) return;
      const ticket = ++sequence;
      loading = true;
      observer?.disconnect();
      if (!append) {
        next = null;
        pages = 0;
        reading.innerHTML = '<p class="fl-status" role="status">Loading…</p>';
      } else {
        const btn = reading.querySelector('[data-more]');
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Loading…';
        }
      }
      markCurrentFund();
      const offset = append ? String(next) : '0';

      try {
        if (reviewing()) {
          const data = await api({ action: 'review', review_q: state.review_q, letter: state.letter, offset });
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
        } else if (state.view === 'ticker') {
          const data = await api({ action: 'ticker', ...scopeArgs() });
          if (ticket !== sequence || disposed) return;
          reading.innerHTML = data.ticker ? companyHtml(data) : companyOverviewHtml(data);
          next = null;
        } else if (state.view === 'ideas') {
          const data = await api({ action: 'ideas', ...scopeArgs(), ...(state.fund ? { fund: state.fund } : {}), offset });
          if (ticket !== sequence || disposed) return;
          if (!append) {
            const fund = state.fund && workspace?.funds.find(f => f.id === state.fund);
            const total = fund ? fund.discussions : workspace?.totals?.discussions;
            reading.innerHTML = `
              <header class="fl-section-head">
                <div>
                  <div class="fl-meta">Ideas · ${escape(periodName())}</div>
                  <h2>${state.fund ? `Ideas from ${escape(fundName(state.fund) || 'this fund')}` : state.ticker ? `Every fund on ${escape(state.ticker)}` : narrowed() ? 'Matching ideas' : 'Ideas across funds'}</h2>
                </div>
                ${total !== undefined ? `<span class="fl-date">${count(total, 'discussion', 'discussions')}${fund ? '' : ` from ${count(workspace?.totals?.funds, 'fund', 'funds')}`}</span>` : ''}
              </header>
              <section data-items class="fl-idea-card-list"></section>`;
          }
          reading.querySelector('[data-items]').insertAdjacentHTML('beforeend', data.results.map(ideaCardHtml).join('')
            || (append ? '' : `<div class="fl-empty"><h2>No ideas match</h2>${emptyMessage(data.emptied_by, 'ideas')}</div>`));
          next = data.next_offset;
        } else if (state.fund) {
          const explicit = Boolean(state.letter);
          const allQuarters = String(currentPeriod()).toUpperCase() === 'ALL';
          const data = await api(explicit
            ? { action: 'letters', fund: state.fund, letter: state.letter }
            : { action: 'letters', ...scopeArgs(), fund: state.fund, offset, limit: '5' });
          if (ticket !== sequence || disposed) return;
          const fund = workspace?.funds.find(f => f.id === state.fund);
          const name = fund?.name || data.letters[0]?.fund || 'Fund';
          if (!append) {
            reading.innerHTML = `
              <header class="fl-fund-bar">
                <div class="fl-fund-bar-left">
                  <button type="button" class="fl-back-btn" data-all-funds>← All funds</button>
                  <div class="fl-fund-identity">
                    <h2>${escape(name)}</h2>
                    <span>${fund ? `${count(fund.discussions, 'discussion', 'discussions')} in ${escape(periodName())}${narrowed() ? ' matching the filters' : ''}` : explicit ? 'Letter outside the current list' : ''}</span>
                  </div>
                </div>
                <div class="fl-fund-bar-right">
                  ${explicit ? '<button type="button" class="fl-back-btn" data-archive>Back to the quarter</button>' : ''}
                  <div class="fl-quarter-pills" role="navigation" aria-label="This fund's letters by quarter"></div>
                  <select class="fl-letter-select" aria-label="Choose a letter" hidden>
                    <option value="">Choose a letter</option>
                  </select>
                </div>
              </header>
              <section data-items></section>`;
          }
          const items = reading.querySelector('[data-items]');
          if (!data.letters.length && !append) {
            items.innerHTML = `<div class="fl-empty"><h2>No letter from ${escape(name)} matches</h2><p>Nothing from this fund in ${escape(periodName())} matches the current search and filters. Its other letters are listed above.</p>
              ${allQuarters ? '' : '<button type="button" class="fl-btn-sm" data-clear-group="period">Search all quarters</button>'}</div>`;
          } else if (!append && !explicit && allQuarters && !narrowed() && state.stack !== '1' && data.letters.length > 1) {
            const [featured, ...older] = data.letters;
            items.innerHTML = letterHtml(featured)
              + `<section class="fl-older-section">
                  <div class="fl-older-head">
                    <h3>Earlier letters from ${escape(name)}</h3>
                    <button type="button" class="fl-btn-sm" data-stack-all>Expand all full letters</button>
                  </div>
                  <div class="fl-letter-card-list">${older.map(letterCardHtml).join('')}</div>
                </section>`;
          } else {
            const cards = append && allQuarters && !narrowed() && state.stack !== '1' && reading.querySelector('.fl-letter-card-list');
            (cards || items).insertAdjacentHTML('beforeend', data.letters.map(cards ? letterCardHtml : letterHtml).join(''));
          }
          next = explicit ? null : data.next_offset;

          if (!append) {
            const activeLetterId = state.letter || data.letters[0]?.id || '';
            api({ action: 'archive', fund: state.fund }).then(archive => {
              if (ticket !== sequence || disposed) return;
              const list = archive.letters || [];
              if (!fund && !data.letters.length && archive.fund_name) {
                reading.querySelector('.fl-fund-identity h2').textContent = archive.fund_name;
                reading.querySelector('.fl-empty h2').textContent = `No letter from ${archive.fund_name} matches`;
              }
              const select = reading.querySelector('.fl-letter-select');
              if (select) {
                select.hidden = list.length <= 1;
                select.innerHTML = '<option value="">All letters (' + list.length + ')</option>'
                  + list.map(l => `<option value="${escape(l.id)}"${l.id === activeLetterId ? ' selected' : ''}>${escape(period(l))}</option>`).join('');
              }
              const pillBox = reading.querySelector('.fl-quarter-pills');
              if (pillBox && list.length > 1) {
                const perQuarter = new Map();
                for (const l of list) perQuarter.set(l.reporting_period, (perQuarter.get(l.reporting_period) || 0) + 1);
                pillBox.innerHTML = list.slice(0, 8).map(l => `
                  <button type="button"
                          class="fl-quarter-pill${l.id === activeLetterId ? ' is-active' : ''}"
                          data-pick-letter="${escape(l.id)}" title="${escape(period(l))}">
                    ${escape(l.reporting_period || l.letter_date || 'Letter')}${perQuarter.get(l.reporting_period) > 1 && l.letter_date ? ` · ${escape(l.letter_date.slice(5))}` : ''}
                  </button>`).join('');
              }
            }).catch(() => {});
          }
        } else {
          const data = await api({ action: 'letters', ...scopeArgs(), offset, limit: '12' });
          if (ticket !== sequence || disposed) return;
          if (!append) {
            const totals = workspace?.totals;
            reading.innerHTML = `
              <header class="fl-section-head">
                <div>
                  <div class="fl-meta">By fund · ${escape(periodName())}</div>
                  <h2>${narrowed() ? 'Letters with matching discussions' : `Letters from ${escape(periodName())}`}</h2>
                </div>
                ${totals ? `<span class="fl-date">${count(totals.letters, 'letter', 'letters')} from ${count(totals.funds, 'fund', 'funds')} · choose a fund to read it beside this list</span>` : ''}
              </header>
              <section data-items class="fl-letter-card-list"></section>`;
          }
          reading.querySelector('[data-items]').insertAdjacentHTML('beforeend', data.letters.map(letterCardHtml).join('')
            || (append ? '' : `<div class="fl-empty"><h2>${workspace?.periods?.length ? 'No matching letters' : 'The archive is being prepared'}</h2>${workspace?.periods?.length ? emptyMessage(workspace?.emptied_by, 'letters') : '<p>Letters will appear here after their summaries have completed verification.</p>'}</div>`));
          next = data.next_offset;
        }
        pages++;
        moreButton();
        if (!append && state.idea) scrollToIdea(state.letter, state.idea);
        if (restoreScroll !== null) global.scrollTo(0, restoreScroll);
      } catch (error) {
        if (ticket === sequence) showError(error);
      } finally {
        if (ticket === sequence) loading = false;
      }
    }


    // Evidence quotes are stored with single spaces; the original keeps its line breaks.
    function markQuotes(container, text, quotes) {
      const spans = [];
      for (const quote of quotes) {
        const words = String(quote || '').trim().split(/\s+/).filter(Boolean);
        if (!words.length) continue;
        const match = new RegExp(words.map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+')).exec(text);
        if (match) spans.push([match.index, match.index + match[0].length]);
      }
      spans.sort((a, b) => a[0] - b[0]);
      container.textContent = '';
      let at = 0, first = null;
      for (const [start, end] of spans) {
        if (start < at) continue;
        const mark = document.createElement('mark');
        mark.textContent = text.slice(start, end);
        container.append(text.slice(at, start), mark);
        first = first || mark;
        at = end;
      }
      container.append(text.slice(at));
      return first;
    }

    // The private quotes behind one citation marker. Owner only; the API refuses everyone else.
    const sourceCache = new Map();
    async function citedQuotes(target) {
      const letterId = target.dataset.cite;
      if (!sourceCache.has(letterId)) sourceCache.set(letterId, api({ action: 'source', letter: letterId }).catch(error => { sourceCache.delete(letterId); throw error; }));
      const source = await sourceCache.get(letterId);
      if (target.dataset.citeTable !== undefined) {
        return [source.tables?.[Number(target.dataset.citeTable)]?.quote].filter(Boolean);
      }
      const lines = new Set(String(target.dataset.citeLines || '').split(',').filter(Boolean).map(Number));
      const row = (source.evidence || []).find(item => item.idea_id === target.dataset.citeIdea);
      let claims = [];
      try { claims = JSON.parse(row?.claims_json || '[]'); } catch { claims = []; }
      return claims.filter(claim => lines.has(claim?.line)).map(claim => claim.quote);
    }

    async function openCitation(target) {
      let quotes = [];
      try { quotes = await citedQuotes(target); } catch { quotes = []; }
      await readOriginal(target.dataset.cite, { quotes, passage: target.dataset.citePassage });
    }

    async function readOriginal(letterId, focus = null) {
      dialog.classList.add('fl-original-dialog');
      dialog.innerHTML = '<p role="status">Loading the original letter…</p>';
      if (!dialog.open) dialog.showModal();
      try {
        const data = await api({ action: 'original', letter: letterId });
        const meta = data.letter || {};
        const views = [data.text && ['text', 'Text'], data.preview_url && ['pdf', 'PDF']].filter(Boolean);
        dialog.innerHTML = `
          <header>
            <div>
              <div class="fl-meta">Original letter · ${escape(meta.reporting_period || 'Undated')}${meta.letter_date ? ` · dated ${escape(meta.letter_date)}` : ''}</div>
              <h2 id="fl-review-title">${escape(meta.fund || 'Original letter')}</h2>
            </div>
            <div class="fl-dialog-actions">
              ${views.length > 1 ? `<div class="fl-original-views" role="tablist">${views.map(([key, name], index) => `<button type="button" role="tab" class="fl-btn-sm" data-original-view="${key}" aria-selected="${index === 0}">${name}</button>`).join('')}</div>` : ''}
              ${data.original_url ? `<a class="fl-btn-sm" href="${escape(data.original_url)}" target="_blank" rel="noopener noreferrer">${data.in_drive ? 'Open in Google Drive' : 'Open original'} ↗</a>` : ''}
              <button type="button" class="fl-btn-sm" data-close>Close</button>
            </div>
          </header>
          ${data.text ? `<div class="fl-original-pane" data-pane="text">
            <p class="fl-notice">Full text extracted from the original letter. Tables and charts read best in the PDF.</p>
            <div class="fl-original-text" tabindex="0"></div>
          </div>` : ''}
          ${data.preview_url ? `<div class="fl-original-pane" data-pane="pdf"${data.text ? ' hidden' : ''}>
            <p class="fl-notice">Shown through Google Drive, so you need to be signed in to a Google account with access. If it does not load, use Open in Google Drive.</p>
            <iframe class="fl-original-pdf" title="Original letter PDF" data-src="${escape(data.preview_url)}" referrerpolicy="no-referrer" allow="fullscreen"></iframe>
          </div>` : ''}
          ${!views.length ? `<p class="fl-notice">${data.original_url ? 'The extracted text is not available for this letter. Open the original instead.' : 'This letter is not linked to an original yet; it remains in the private research vault.'}</p>` : ''}`;
        const text = dialog.querySelector('.fl-original-text');
        const body = String(data.text || '').replace(/\f/g, '\n\n');
        const cited = text && focus?.quotes?.length ? markQuotes(text, body, focus.quotes) : null;
        if (text && !cited) text.textContent = body;
        if (text && focus) {
          const notice = dialog.querySelector('.fl-original-pane[data-pane="text"] .fl-notice');
          if (notice) notice.textContent = cited
            ? `Highlighted: the sentences in passage ${focus.passage} that the statement rests on.`
            : `The cited sentences in passage ${focus.passage} could not be located in this copy of the text.`;
        }
        const show = key => {
          dialog.querySelectorAll('[data-pane]').forEach(pane => { pane.hidden = pane.dataset.pane !== key; });
          dialog.querySelectorAll('[data-original-view]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.originalView === key)));
          const frame = key === 'pdf' && dialog.querySelector('.fl-original-pdf');
          if (frame && !frame.src) frame.src = frame.dataset.src;
        };
        dialog.querySelectorAll('[data-original-view]').forEach(tab => { tab.onclick = () => show(tab.dataset.originalView); });
        if (views.length) show(views[0][0]);
        dialog.querySelector('[data-close]').onclick = () => dialog.close();
        if (cited) cited.scrollIntoView({ block: 'center' });
      } catch (error) {
        dialog.innerHTML = `<h2 id="fl-review-title">Original unavailable</h2><p>${escape(error.message)}</p><button data-close type="button">Close</button>`;
        dialog.querySelector('button').onclick = () => dialog.close();
      }
    }

    async function review(letterId, revisionId = '') {
      dialog.classList.remove('fl-original-dialog');
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
          <p class="fl-dialog-actions">
            <button type="button" class="fl-btn-sm" data-original="${escape(letterId)}">Read original here</button>
            ${validUrl ? `<a class="fl-btn-sm" href="${escape(sourceUrl)}" target="_blank" rel="noopener noreferrer">${/^https:\/\/drive\.google\.com\//.test(sourceUrl) ? 'Open in Google Drive' : 'Open original letter'} ↗</a>` : ''}
            <a class="fl-btn-sm" href="/api/fund-letters?action=document&amp;letter=${encodeURIComponent(letterId)}" target="_blank" rel="noopener noreferrer">Plain text file ↗</a>
          </p>
          ${validUrl ? '' : '<p>The original PDF is not linked yet; it remains in the private research vault.</p>'}
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
              // Citations are kept line by line, so a hand-edited summary no longer carries them.
              if (key === 'summary' && idea.cites && el.value !== draft.ideas[Number(group.dataset.idea)].summary) delete idea.cites;
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
            sourceCache.delete(letterId);
            load();
          });
        }
      } catch (error) {
        dialog.innerHTML = `<h2 id="fl-review-title">Review unavailable</h2><p>${escape(error.message)}</p><button data-close type="button">Close</button>`;
        dialog.querySelector('button').onclick = () => dialog.close();
      }
    }

    function setDrawer(open) {
      root.classList.toggle('is-drawer-open', open);
      drawerToggle.setAttribute('aria-expanded', String(open));
      scrim.hidden = !open;
      if (open) (fundList.querySelector('a[aria-current]') || fundFilter).focus();
    }
    const drawerOpen = () => root.classList.contains('is-drawer-open');

    const clearGroup = {
      period: () => ({ period: 'all' }),
      search: () => ({ q: '' }),
      q: () => ({ q: '' }),
      fund: () => ({ fund: '' }),
      ticker: () => ({ ticker: '' }),
      activity: () => ({ chips: state.chips.filter(chip => CHIPS.find(c => c.id === chip)?.group !== 'activity') }),
      first: () => ({ chips: state.chips.filter(chip => chip !== 'first') }),
      theme: () => ({ chips: state.chips.filter(chip => CHIPS.find(c => c.id === chip)?.group !== 'theme') }),
      book: () => ({ chips: state.chips.filter(chip => chip !== 'book') }),
      type: () => ({ type: '' }),
      focus: () => ({ focus: '' }),
    };
    const resetAllFilters = () => navigate({ q: '', chips: [], ticker: '', type: '', focus: '', letter: '', idea: '', stack: '' });

    on(form, 'submit', e => {
      e.preventDefault();
      if (searchTimer) global.clearTimeout(searchTimer);
      if (suggestBox) suggestBox.hidden = true;
      if (reviewing()) navigate({ review_q: searchInput.value, letter: '', idea: '' });
      else navigate({ q: searchInput.value.trim(), letter: '', idea: '' });
    });

    on(searchInput, 'focus', () => renderSuggestions());
    on(searchInput, 'blur', () => {
      global.setTimeout(() => {
        if (suggestBox) suggestBox.hidden = true;
      }, 160);
    });
    on(searchInput, 'keydown', e => {
      if (e.key === 'Escape' && suggestBox && !suggestBox.hidden) suggestBox.hidden = true;
    });
    on(searchInput, 'input', () => {
      renderSuggestions();
      if (searchTimer) global.clearTimeout(searchTimer);
      searchTimer = global.setTimeout(() => {
        if (reviewing()) navigate({ review_q: searchInput.value, letter: '', idea: '' }, false);
        else navigate({ q: searchInput.value.trim(), letter: '', idea: '' }, false);
      }, 300);
    });

    on(resetBtn, 'click', resetAllFilters);
    on(periodSelect, 'change', () => navigate({ period: periodSelect.value, letter: '', idea: '', stack: '' }));
    on(typeSelect, 'change', () => navigate({ type: typeSelect.value, letter: '', idea: '' }));
    on(fundFilter, 'input', () => drawFundList());
    on(drawerToggle, 'click', () => setDrawer(!drawerOpen()));
    on(scrim, 'click', () => setDrawer(false));
    on(directory.querySelector('.fl-drawer-close'), 'click', () => { setDrawer(false); drawerToggle.focus(); });
    on(root, 'keydown', e => {
      if (e.key === 'Escape' && drawerOpen()) {
        setDrawer(false);
        drawerToggle.focus();
      }
    });
    // Arrow keys move through the fund list; Enter opens the focused fund.
    on(fundList, 'keydown', e => {
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
      const links = [...fundList.querySelectorAll('a[data-fund]')];
      const at = links.indexOf(document.activeElement);
      if (!links.length) return;
      e.preventDefault();
      const target = e.key === 'Home' ? 0 : e.key === 'End' ? links.length - 1 : Math.min(links.length - 1, Math.max(0, at + (e.key === 'ArrowDown' ? 1 : -1)));
      links[target].focus();
    });

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
      if (target.dataset.clearKey || target.dataset.clearGroup) {
        e.preventDefault();
        const clear = clearGroup[target.dataset.clearKey || target.dataset.clearGroup];
        if (clear) navigate({ ...clear(), letter: '', idea: '' });
        return;
      }
      if (target.hasAttribute('data-reset-all')) {
        e.preventDefault();
        resetAllFilters();
        return;
      }
      if (target.dataset.chip) {
        e.preventDefault();
        const chips = new Set(state.chips);
        if (chips.has(target.dataset.chip)) chips.delete(target.dataset.chip);
        else chips.add(target.dataset.chip);
        navigate({ chips: CHIP_IDS.filter(id => chips.has(id)), letter: '', idea: '' });
        return;
      }
      if (target.dataset.pickTicker !== undefined) {
        e.preventDefault();
        const ticker = target.dataset.pickTicker;
        if (!ticker || (ticker === state.ticker && state.view === 'ticker')) navigate({ ticker: '', letter: '', idea: '' });
        else navigate({ ticker, view: 'ticker', fund: '', letter: '', idea: '', mode: '', stack: '' });
        return;
      }
      if (target.dataset.dirSort) {
        e.preventDefault();
        fundSort = target.dataset.dirSort;
        drawFundList();
        return;
      }
      if (target.hasAttribute('data-overlap-toggle')) {
        e.preventDefault();
        overlapOpen = !overlapOpen;
        drawOverlap();
        overlapBar.querySelector('[data-overlap-toggle]')?.focus();
        return;
      }
      if (target.dataset.viewMode) {
        e.preventDefault();
        navigate({ view: target.dataset.viewMode, letter: '', idea: '', mode: '', stack: '' });
        return;
      }
      if (target.hasAttribute('data-ticker-overview')) {
        e.preventDefault();
        navigate({ ticker: '', letter: '', idea: '' });
        return;
      }
      if (target.hasAttribute('data-fund')) {
        e.preventDefault();
        const fromDrawer = drawerOpen();
        navigate({ fund: target.dataset.fund, letter: '', idea: '', mode: '', stack: '', ...(state.view === 'ticker' ? { view: 'funds' } : {}) });
        if (fromDrawer) {
          setDrawer(false);
          reading.focus({ preventScroll: true });
        }
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
        navigate({ view: 'funds', fund: target.dataset.openFund, letter: target.dataset.openLetter, idea: target.dataset.openIdea || '', stack: '', mode: '' });
        return;
      }
      if (target.dataset.jump) {
        e.preventDefault();
        const destination = new URL(target.href, location.origin).searchParams;
        const el = root.querySelector(`#${CSS.escape(target.dataset.jump)}`);
        if (el) {
          const details = el.closest('details');
          if (details) details.open = true;
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          state.idea = destination.get('idea') || '';
          remember();
          return;
        }
        navigate({ fund: destination.get('fund'), letter: destination.get('letter'), idea: destination.get('idea') });
        return;
      }
      if (target.hasAttribute('data-more')) load(true);
      if (target.hasAttribute('data-retry')) refresh();
      if (target.hasAttribute('data-archive')) navigate({ letter: '', idea: '', stack: '' });
      if (target.dataset.cite) openCitation(target);
      if (target.dataset.original) readOriginal(target.dataset.original);
      if (target.dataset.source) review(target.dataset.source);
      if (target.hasAttribute('data-review-queue')) navigate({ mode: state.mode === 'review' ? '' : 'review', letter: '', idea: '' });
    });

    on(root, 'change', e => {
      if (e.target.matches('.fl-letter-select') && e.target.value) navigate({ letter: e.target.value, idea: '', stack: '' });
    });

    if (!embedded) {
      on(global, 'popstate', async e => {
        state = readState(location.search);
        restoring = true;
        await refresh();
        for (let n = 1; n < (e.state?.flPages || 1) && next !== null; n++) await load(true);
        restoring = false;
        moreButton();
        global.scrollTo(0, e.state?.flScroll || 0);
        if (Number.isFinite(e.state?.flListScroll)) directory.scrollTop = e.state.flListScroll;
      });
    }

    try {
      const session = await api({ action: 'session' });
      if (disposed) return;
      role = session.role;
      if (role === 'owner' && Array.isArray(session.book_tickers)) {
        session.book_tickers.forEach(t => bookSet.add(String(t || '').trim().toUpperCase()));
      }
      const tools = root.querySelector('.fl-owner-tools');
      if (tools) {
        if (role === 'owner') {
          tools.innerHTML = `${embedded ? '' : '<a href="/" class="fl-btn-sm">Dashboard</a>'}<button type="button" class="fl-btn-sm" data-review-queue>Review queue</button>`;
        } else if (session.email && !embedded) {
          tools.innerHTML = `<span class="fl-user-chip">Signed in as ${escape(session.email)}</span>`;
        }
      }
      await refresh();
      const reviewLetter = embedded ? '' : new URLSearchParams(location.search).get('review');
      if (role === 'owner' && reviewLetter) await review(reviewLetter);
    } catch (error) {
      showError(error);
    }
    return controller;
  }

  global.FundLettersReader = { mount, unmount: root => states.get(root)?.dispose(), state: { readState, writeState, statements, emptiedReason } };
  if (document.getElementById('fund-letters-app')) mount(document.getElementById('fund-letters-app'));
})(window);
