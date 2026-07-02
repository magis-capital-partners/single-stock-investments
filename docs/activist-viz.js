/** Activist long/short feed panel for portfolio dashboard. */
(function (global) {
  function sideBadge(side) {
    if (side === 'long') return 'badge-ok';
    if (side === 'short') return 'badge-bad';
    return 'badge-us';
  }

  function formatReportDate(row) {
    const date = row?.report_date;
    if (!date) return '—';
    const precision = row?.date_precision || 'day';
    if (precision === 'month' && /^\d{4}-\d{2}$/.test(String(date).slice(0, 7))) {
      const [year, month] = String(date).slice(0, 7).split('-');
      const monthName = new Date(Number(year), Number(month) - 1, 1).toLocaleString(undefined, { month: 'short' });
      return `${monthName} ${year}`;
    }
    if (precision === 'year' && /^\d{4}/.test(String(date))) {
      return String(date).slice(0, 4);
    }
    return String(date).slice(0, 10);
  }

  function dateTitle(row) {
    const bits = [];
    if (row?.report_date) bits.push(`Date: ${row.report_date}`);
    if (row?.date_source) bits.push(`Source: ${row.date_source}`);
    if (row?.date_precision && row.date_precision !== 'day') bits.push(`Precision: ${row.date_precision}`);
    return bits.join(' · ');
  }

  function firmDisplay(row) {
    const name = row?.firm_name || row?.firm_id || '—';
    const persons = row?.reporting_persons || [];
    if (persons.length <= 1) return name;
    const extra = persons.length - 1;
    return `${name} <span class="tier-sub">(+${extra})</span>`;
  }

  function renderSummary(summary) {
    const s = summary || {};
    return `
      <div class="darwin-grid">
        <div class="metric"><div class="k">Portfolio reports</div><div class="v mono">${s.portfolio_hits || 0}</div></div>
        <div class="metric"><div class="k">Long</div><div class="v mono">${s.long_count || 0}</div></div>
        <div class="metric"><div class="k">Short</div><div class="v mono">${s.short_count || 0}</div></div>
        <div class="metric"><div class="k">Tickers with hits</div><div class="v mono">${s.tickers_with_hits || 0}</div></div>
        <div class="metric"><div class="k">Unresolved filers</div><div class="v mono">${s.unresolved_filer_count || 0}</div></div>
        <div class="metric"><div class="k">Missing dates</div><div class="v mono">${s.missing_date_count || 0}</div></div>
      </div>`;
  }

  function renderFilters(state) {
    const reviewActive = state.reviewFilter === 'needs_filer_review';
    return `
      <div class="toolbar" style="margin:12px 0">
        <input class="search" id="activist-search" placeholder="Filter ticker, firm, title…" value="${state.escapeHtml(state.search || '')}" />
        <button type="button" class="filter-btn${state.side === 'all' && !reviewActive ? ' active' : ''}" data-activist-side="all">All</button>
        <button type="button" class="filter-btn${state.side === 'long' ? ' active' : ''}" data-activist-side="long">Long</button>
        <button type="button" class="filter-btn${state.side === 'short' ? ' active' : ''}" data-activist-side="short">Short</button>
        <button type="button" class="filter-btn${reviewActive ? ' active' : ''}" data-activist-review="needs_filer_review">Needs filer review</button>
      </div>`;
  }

  function isPdfReport(row) {
    if (row?.local_is_pdf) return true;
    const path = row?.local_pdf || row?.github_url || '';
    return /\.pdf(\?|#|$)/i.test(String(path));
  }

  function renderReportLinks(row, linkHtml) {
    if (isPdfReport(row) && row.github_url) {
      return linkHtml(row.github_url, 'PDF', 'source-open-link');
    }
    if (row.source_url) {
      return linkHtml(row.source_url, 'Source', 'source-open-link');
    }
    if (row.github_url) {
      return linkHtml(row.github_url, 'Source', 'source-open-link');
    }
    return '—';
  }

  function sortFeedRows(rows) {
    return rows.slice().sort((a, b) => {
      const da = a.report_date || '';
      const db = b.report_date || '';
      if (da !== db) return db.localeCompare(da);
      const ta = (a.ticker || '').localeCompare(b.ticker || '');
      if (ta) return ta;
      const fa = (a.firm_name || a.firm_id || '').localeCompare(b.firm_name || b.firm_id || '');
      if (fa) return fa;
      return (a.title || '').localeCompare(b.title || '');
    });
  }

  function renderFeed(feed, state) {
    const q = (state.search || '').trim().toLowerCase();
    let rows = Array.isArray(feed) ? feed.slice() : [];
    if (state.reviewFilter === 'needs_filer_review') {
      rows = rows.filter(r => r.needs_filer_review);
    } else if (state.side && state.side !== 'all') {
      rows = rows.filter(r => r.side === state.side);
    }
    if (q) {
      rows = rows.filter(r =>
        [r.ticker, r.firm_name, r.firm_id, r.title, r.source, ...(r.reporting_persons || [])]
          .join(' ')
          .toLowerCase()
          .includes(q)
      );
    }
    rows = sortFeedRows(rows);
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
          ${rows.slice(0, 300).map(r => {
            const groupBadge = r.campaign_group_size > 1
              ? ` <span class="badge badge-purple" title="Latest in ${r.campaign_group_size}-filing campaign window">×${r.campaign_group_size}</span>`
              : '';
            const reviewBadge = r.needs_filer_review
              ? ' <span class="badge badge-warn" title="Filer unresolved or low confidence">review</span>'
              : '';
            return `
            <tr class="clickable-row" data-select-ticker="${state.escapeHtml(r.ticker || '')}">
              <td class="mono" title="${state.escapeHtml(dateTitle(r))}">${state.escapeHtml(formatReportDate(r))}${r.date_precision && r.date_precision !== 'day' ? ' <span class="tier-sub">~</span>' : ''}</td>
              <td class="mono">${state.escapeHtml(r.ticker || '—')}</td>
              <td><span class="badge ${sideBadge(r.side)}">${state.escapeHtml(r.side || '—')}</span></td>
              <td>${firmDisplay(r)}${reviewBadge}</td>
              <td>${state.escapeHtml(r.title || '—')}${groupBadge}</td>
              <td>${state.escapeHtml(r.source || '—')}${r.status === 'new' ? ' <span class="badge badge-warn">new</span>' : ''}</td>
              <td>${renderReportLinks(r, state.linkHtml)}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      ${rows.length > 300 ? `<p class="tier-sub">${rows.length - 300} more reports outside the current table window.</p>` : ''}`;
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
