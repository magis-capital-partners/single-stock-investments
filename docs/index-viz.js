/**
 * Index Watch panel — confirmed + potential index membership changes.
 * Loaded by dashboard/index.html; used from InsightsViz Index Watch section.
 */
(function (global) {
  'use strict';

  const BADGE_CLASS = {
    member: 'badge-us',
    inclusion_candidate: 'badge-warn',
    deletion_risk: 'badge-bad',
    ineligible: 'badge-purple',
    n_a: 'badge-warn',
  };

  const STATUS_LABEL = {
    member: 'Member',
    inclusion_candidate: 'Candidate',
    deletion_risk: 'Deletion risk',
    ineligible: 'Ineligible',
    n_a: 'n/a',
  };

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderBadge(status, opts) {
    const st = status || 'n_a';
    const cls = BADGE_CLASS[st] || 'badge-warn';
    const label = STATUS_LABEL[st] || st;
    const dist = opts && opts.distance != null ? ` ${Number(opts.distance).toFixed(0)}%` : '';
    const dot =
      opts && opts.confirmedSoon
        ? ' <span title="Confirmed event within 30 days" style="color:var(--accent-blue)">●</span>'
        : '';
    const title = opts && opts.title ? ` title="${esc(opts.title)}"` : '';
    return `<span class="badge ${cls}"${title}>${esc(label)}${esc(dist)}${dot}</span>`;
  }

  function confirmedSoon(entry) {
    const events = (entry && entry.confirmed_events) || [];
    const now = Date.now();
    return events.some((ev) => {
      if (!ev.effective) return false;
      const t = Date.parse(ev.effective);
      if (Number.isNaN(t)) return false;
      const days = (t - now) / 86400000;
      return days >= 0 && days <= 30;
    });
  }

  function bestDistance(entry) {
    const cards = (entry && entry.scorecards) || [];
    let best = null;
    for (const sc of cards) {
      if (sc.status !== 'inclusion_candidate' && sc.status !== 'deletion_risk') continue;
      if (sc.distance_to_boundary_pct == null) continue;
      const a = Math.abs(sc.distance_to_boundary_pct);
      if (best == null || a < Math.abs(best)) best = sc.distance_to_boundary_pct;
    }
    return best;
  }

  function renderHoldingsCell(entry) {
    if (!entry) return '<span style="color:var(--text-muted)">—</span>';
    const status = entry.badge_status || 'n_a';
    const mem = (entry.current_memberships || []).slice(0, 2).join(', ');
    const title = mem
      ? `In: ${mem}`
      : (entry.scorecards || [])
          .filter((s) => s.status === 'inclusion_candidate' || s.status === 'deletion_risk')
          .map((s) => `${s.index}: ${s.status}`)
          .slice(0, 3)
          .join('; ') || status;
    return renderBadge(status, {
      distance: status === 'inclusion_candidate' ? bestDistance(entry) : null,
      confirmedSoon: confirmedSoon(entry),
      title,
    });
  }

  function renderCalendarStrip(calendar, escapeHtml) {
    const e = escapeHtml || esc;
    const rows = (calendar || []).filter((c) => c.days_out != null).slice(0, 8);
    if (!rows.length) return '<p class="muted">No reconstitution dates configured.</p>';
    return `<div class="index-cal-strip" style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px">
      ${rows
        .map((c) => {
          const d = c.days_out;
          const tone = d < 0 ? 'badge-purple' : d <= 30 ? 'badge-warn' : 'badge-us';
          const when = d < 0 ? `${Math.abs(d)}d ago` : `in ${d}d`;
          return `<span class="badge ${tone}" title="${e(c.kind || '')}">${e(c.label || c.id)} · ${e(when)}</span>`;
        })
        .join('')}
    </div>`;
  }

  function renderConfirmedTable(byTicker, escapeHtml, linkHtml) {
    const e = escapeHtml || esc;
    const rows = [];
    Object.keys(byTicker || {})
      .sort()
      .forEach((t) => {
        (byTicker[t].confirmed_events || []).forEach((ev) => {
          rows.push({ ticker: t, ...ev });
        });
      });
    rows.sort((a, b) => String(b.announced || '').localeCompare(String(a.announced || '')));
    if (!rows.length) {
      return '<p class="muted">No confirmed or news-sourced index events yet.</p>';
    }
    const body = rows
      .slice(0, 40)
      .map((r) => {
        const src =
          r.source_url && linkHtml
            ? linkHtml(r.source_url, r.confidence || 'source')
            : e(r.confidence || '—');
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.index)}</td>
          <td>${e(r.action)}</td>
          <td class="mono">${e(r.announced || '—')}</td>
          <td class="mono">${e(r.effective || 'TBD')}</td>
          <td>${src}</td>
        </tr>`;
      })
      .join('');
    return `<table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Action</th><th>Announced</th><th>Effective</th><th>Source</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderPotentialTable(byTicker, escapeHtml, filter) {
    const e = escapeHtml || esc;
    const dir = (filter && filter.direction) || 'all';
    const indexFilter = (filter && filter.index) || '';
    const rows = [];
    Object.keys(byTicker || {}).forEach((t) => {
      const entry = byTicker[t];
      (entry.scorecards || []).forEach((sc) => {
        if (sc.status !== 'inclusion_candidate' && sc.status !== 'deletion_risk') return;
        if (dir === 'inclusion' && sc.status !== 'inclusion_candidate') return;
        if (dir === 'exclusion' && sc.status !== 'deletion_risk') return;
        if (indexFilter && sc.index !== indexFilter) return;
        rows.push({
          ticker: t,
          company: entry.company,
          priority: (entry.impact_proxy || {}).priority_score || 0,
          shock: (entry.impact_proxy || {}).demand_shock_pct_of_adv,
          band: (entry.prediction || {}).inclusion_probability_band,
          next: (entry.prediction || {}).next_calendar_event,
          ...sc,
        });
      });
    });
    rows.sort((a, b) => b.priority - a.priority);
    if (!rows.length) {
      return '<p class="muted">No inclusion candidates or deletion risks at current thresholds.</p>';
    }
    const body = rows
      .slice(0, 60)
      .map((r) => {
        const nextLabel = r.next
          ? `${r.next.label || r.next.id} (${r.next.days_out != null ? r.next.days_out + 'd' : '—'})`
          : '—';
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.index)}</td>
          <td>${renderBadge(r.status, { distance: r.distance_to_boundary_pct })}</td>
          <td>${e(r.gating_check || '—')}</td>
          <td class="mono">${r.distance_to_boundary_pct == null ? '—' : e(Number(r.distance_to_boundary_pct).toFixed(1) + '%')}</td>
          <td class="mono">${e(Number(r.priority).toFixed(2))}</td>
          <td class="mono">${r.shock == null ? '—' : e(Number(r.shock).toFixed(1) + '% ADV')}</td>
          <td>${e(r.band || '—')}</td>
          <td>${e(nextLabel)}</td>
        </tr>`;
      })
      .join('');
    return `<table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Status</th><th>Gate</th><th>Distance</th><th>Priority</th><th>Shock</th><th>Prob</th><th>Next event</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderIndexWatch(payload, options) {
    const escapeHtml = (options && options.escapeHtml) || esc;
    const linkHtml = options && options.linkHtml;
    const summary = (payload && payload.portfolio_summary) || {};
    const caption =
      (payload && payload.caption) ||
      'The average large-cap S&P 500 index effect has fallen to near zero since 2010; treat these as research triggers, weighted by demand-shock size, not mechanical trades.';
    const byTicker = (payload && payload.by_ticker) || {};
    const calendar = (payload && payload.calendar) || [];

    const stats = [
      `Candidates: <strong>${(summary.inclusion_candidates || []).length}</strong>`,
      `Deletion risks: <strong>${(summary.deletion_risks || []).length}</strong>`,
      `Confirmed ≤30d: <strong>${(summary.confirmed_next_30d || []).length}</strong>`,
      `High priority: <strong>${(summary.high_priority_watch || []).length}</strong>`,
    ].join(' · ');

    return `<div class="index-watch-panel">
      <p class="muted" style="margin-bottom:8px">${escapeHtml(caption)}</p>
      <p style="margin-bottom:8px">${stats}</p>
      <h3 style="margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Reconstitution calendar</h3>
      ${renderCalendarStrip(calendar, escapeHtml)}
      <h3 style="margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Confirmed / news events</h3>
      ${renderConfirmedTable(byTicker, escapeHtml, linkHtml)}
      <h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Potential (proximity scorecards)</h3>
      <p class="muted" style="margin-bottom:8px">Sorted by demand-shock priority. Missing float/ADV/earnings show as n/a — never invented.</p>
      ${renderPotentialTable(byTicker, escapeHtml, options && options.filter)}
    </div>`;
  }

  global.IndexViz = {
    renderBadge,
    renderHoldingsCell,
    renderIndexWatch,
    renderCalendarStrip,
    BADGE_CLASS,
    STATUS_LABEL,
  };
})(window);
