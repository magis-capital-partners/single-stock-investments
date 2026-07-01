/** Activist long/short feed panel for portfolio dashboard. */
(function (global) {
  function sideBadge(side) {
    if (side === 'long') return 'badge-ok';
    if (side === 'short') return 'badge-bad';
    return 'badge-us';
  }

  function renderSummary(summary) {
    const s = summary || {};
    return `
      <div class="darwin-grid">
        <div class="metric"><div class="k">Portfolio reports</div><div class="v mono">${s.portfolio_hits || 0}</div></div>
        <div class="metric"><div class="k">Long</div><div class="v mono">${s.long_count || 0}</div></div>
        <div class="metric"><div class="k">Short</div><div class="v mono">${s.short_count || 0}</div></div>
        <div class="metric"><div class="k">Tickers with hits</div><div class="v mono">${s.tickers_with_hits || 0}</div></div>
        <div class="metric"><div class="k">Unreconciled</div><div class="v mono">${s.unreconciled_count || 0}</div></div>
      </div>`;
  }

  function renderFilters(state) {
    return `
      <div class="toolbar" style="margin:12px 0">
        <input class="search" id="activist-search" placeholder="Filter ticker, firm, title…" value="${state.escapeHtml(state.search || '')}" />
        <button type="button" class="filter-btn${state.side === 'all' ? ' active' : ''}" data-activist-side="all">All</button>
        <button type="button" class="filter-btn${state.side === 'long' ? ' active' : ''}" data-activist-side="long">Long</button>
        <button type="button" class="filter-btn${state.side === 'short' ? ' active' : ''}" data-activist-side="short">Short</button>
      </div>`;
  }

  function renderFeed(feed, state) {
    const q = (state.search || '').trim().toLowerCase();
    let rows = Array.isArray(feed) ? feed.slice() : [];
    if (state.side && state.side !== 'all') {
      rows = rows.filter(r => r.side === state.side);
    }
    if (q) {
      rows = rows.filter(r =>
        [r.ticker, r.firm_name, r.firm_id, r.title, r.source].join(' ').toLowerCase().includes(q)
      );
    }
    if (!rows.length) {
      return '<div class="empty">No activist reports match your filters.</div>';
    }
    return `
      <table class="darwin-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Ticker</th>
            <th>Side</th>
            <th>Firm</th>
            <th>Title</th>
            <th>Source</th>
            <th>Links</th>
          </tr>
        </thead>
        <tbody>
          ${rows.slice(0, 300).map(r => `
            <tr class="clickable-row" data-select-ticker="${state.escapeHtml(r.ticker || '')}">
              <td class="mono">${state.escapeHtml(r.report_date || '—')}</td>
              <td class="mono">${state.escapeHtml(r.ticker || '—')}</td>
              <td><span class="badge ${sideBadge(r.side)}">${state.escapeHtml(r.side || '—')}</span></td>
              <td>${state.escapeHtml(r.firm_name || r.firm_id || '—')}</td>
              <td>${state.escapeHtml(r.title || '—')}</td>
              <td>${state.escapeHtml(r.source || '—')}${r.status === 'new' ? ' <span class="badge badge-warn">new</span>' : ''}</td>
              <td>
                ${r.github_url ? state.linkHtml(r.github_url, 'PDF', 'source-open-link') : ''}
                ${r.source_url ? state.linkHtml(r.source_url, 'Source', 'source-open-link') : ''}
              </td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  function renderTickerActivistSection(activist, helpers) {
    if (!activist || (!activist.long_count && !activist.short_count)) return '';
    const latest = activist.latest || {};
    return `
      <div class="detail-section">
        <h3>Activist reports</h3>
        <div class="metric-grid metric-grid-3">
          <div class="metric"><div class="k">Long</div><div class="v mono">${activist.long_count || 0}</div></div>
          <div class="metric"><div class="k">Short</div><div class="v mono">${activist.short_count || 0}</div></div>
          <div class="metric"><div class="k">Latest</div><div class="v">${helpers.escapeHtml(latest.firm_name || '—')} · ${helpers.escapeHtml(latest.date || '—')}</div></div>
        </div>
        ${activist.has_unreconciled ? '<div class="tier-sub"><span class="badge badge-warn">Unreconciled hits</span> — run Milly adversarial pass.</div>' : ''}
      </div>`;
  }

  function renderActivistBadge(activist) {
    if (!activist) return '<span class="tier-sub">—</span>';
    const longN = activist.long_count || 0;
    const shortN = activist.short_count || 0;
    if (!longN && !shortN) return '<span class="tier-sub">—</span>';
    const dot = activist.has_unreconciled ? ' <span class="badge badge-warn" title="Unreconciled">!</span>' : '';
    return `<span class="mono">L${longN}/S${shortN}</span>${dot}`;
  }

  function renderActivistPanel(feedDoc, state) {
    if (!feedDoc) {
      return '<div class="empty">Activist feed not built. Run: python _system/scripts/build_activist_feed.py</div>';
    }
    return `
      <h2 style="margin-bottom:8px">Activist reports</h2>
      <div class="subhead">Long activists (13D, proxy) and short forensic reports · context tier until human approval</div>
      ${renderSummary(feedDoc.summary)}
      ${renderFilters(state)}
      ${renderFeed(feedDoc.feed, state)}
      <div class="tier-sub" style="margin-top:12px">Last scan: ${state.escapeHtml(feedDoc.last_scan || feedDoc.generated_at || '—')}</div>`;
  }

  global.ActivistViz = {
    renderActivistPanel,
    renderTickerActivistSection,
    renderActivistBadge,
  };
})(window);
