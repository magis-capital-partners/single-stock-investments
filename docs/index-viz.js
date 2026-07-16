/**
 * Index Watch panel — confirmed + potential index membership changes + float impact.
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

  function primaryFloatImpact(entry) {
    return (entry && entry.float_impact && entry.float_impact.primary) || null;
  }

  function formatPctFloat(pct) {
    if (pct == null || Number.isNaN(Number(pct))) return '—';
    const n = Number(pct);
    const sign = n > 0 ? '+' : '';
    return `${sign}${n.toFixed(1)}%`;
  }

  function pctFloatTone(pct) {
    if (pct == null) return '';
    const n = Number(pct);
    if (n < -1) return 'color:var(--accent-red, #c44)';
    if (n > 1) return 'color:var(--accent-green, #2a7)';
    return '';
  }

  function pctFloatTooltip(fi) {
    if (!fi) return 'No float-impact estimate (missing float, ADV, or AUM)';
    const low = fi.pct_of_float_low;
    const base = fi.pct_of_float_base;
    const high = fi.pct_of_float_high;
    const adv = fi.pct_of_adv_days;
    const cliff = fi.hk_weight_cliff_ratio;
    const parts = [
      `low ${formatPctFloat(low)} / base ${formatPctFloat(base)} / high ${formatPctFloat(high)} of float`,
    ];
    if (adv != null) parts.push(`${Number(adv).toFixed(2)} days ADV`);
    if (cliff != null) parts.push(`HK cliff ${Number(cliff).toFixed(1)}x`);
    if (fi.aum_stale) parts.push('AUM registry stale');
    if (fi.float_flag === 'float_unknown') parts.push('float unknown — upper bound');
    return parts.join(' · ');
  }

  function renderPctFloatCell(fi) {
    const pct = fi && fi.pct_of_float_base;
    const tip = pctFloatTooltip(fi);
    const tone = pctFloatTone(pct);
    return `<td class="mono" style="${tone}" title="${esc(tip)}">${esc(formatPctFloat(pct))}</td>`;
  }

  function renderHoldingsCell(entry) {
    if (!entry) return '<span style="color:var(--text-muted)">—</span>';
    const status = entry.badge_status || 'n_a';
    const mem = (entry.current_memberships || []).slice(0, 2).join(', ');
    const fi = primaryFloatImpact(entry);
    const floatBit =
      fi && fi.pct_of_float_base != null ? ` · float ${formatPctFloat(fi.pct_of_float_base)}` : '';
    const title = mem
      ? `In: ${mem}${floatBit}`
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

  function findMatchingImpact(entry, indexId, action) {
    const events = (entry && entry.float_impact && entry.float_impact.events) || [];
    const match = events.find((ev) => ev.primary_index === indexId && ev.action === action);
    return match || primaryFloatImpact(entry);
  }

  function renderFlowBridge(fi, escapeHtml) {
    const e = escapeHtml || esc;
    if (!fi || !fi.legs || !fi.legs.length) {
      return '<p class="muted">No flow legs.</p>';
    }
    const body = fi.legs
      .map((lg) => {
        const flow = lg.flow_usd_base;
        const flowLabel =
          flow == null ? '—' : (flow >= 0 ? '+' : '') + '$' + (Math.abs(flow) / 1e6).toFixed(1) + 'M';
        const dir = lg.sign > 0 ? 'buy' : 'sell';
        return `<tr>
          <td>${e(lg.label || lg.index)}</td>
          <td class="mono">${e(dir)}</td>
          <td class="mono">${lg.weight_bps == null ? '—' : e(Number(lg.weight_bps).toFixed(2) + ' bps')}</td>
          <td class="mono">${e(flowLabel)}</td>
          <td class="muted">${e(lg.reason || '')}</td>
        </tr>`;
      })
      .join('');
    const cliff =
      fi.hk_weight_cliff_ratio != null
        ? `<p style="margin:8px 0 0"><span class="badge badge-warn" title="Horizon Kinetics weight cliff × AUM asymmetry">HK graduation penalty: ~${e(
            Number(fi.hk_weight_cliff_ratio).toFixed(1)
          )}× demand differential</span></p>`
        : '';
    const band = `low ${formatPctFloat(fi.pct_of_float_low)} · base ${formatPctFloat(
      fi.pct_of_float_base
    )} · high ${formatPctFloat(fi.pct_of_float_high)} of float`;
    const adv =
      fi.pct_of_adv_days != null ? ` · ${Number(fi.pct_of_adv_days).toFixed(2)} days ADV` : '';
    const aum = fi.aum_as_of
      ? ` · AUM as-of ${fi.aum_as_of}${fi.aum_stale ? ' (stale)' : ''}`
      : '';
    return `<details style="margin-top:4px">
      <summary style="cursor:pointer;font-size:12px">Flow bridge · ${e(band)}${e(adv)}${e(aum)}</summary>
      <table class="insights-table" style="margin-top:6px"><thead><tr>
        <th>Index</th><th>Dir</th><th>Weight</th><th>Base $</th><th>Reason</th>
      </tr></thead><tbody>${body}</tbody></table>
      ${cliff}
      <p class="muted" style="margin-top:6px;font-size:11px">Negative % float = net forced selling. Both sides of Russell 1000/2000 migrations are modeled (HK 2013). BMI (high) is scenario-only.</p>
    </details>`;
  }

  function renderConfirmedTable(byTicker, escapeHtml, linkHtml) {
    const e = escapeHtml || esc;
    const rows = [];
    Object.keys(byTicker || {})
      .sort()
      .forEach((t) => {
        const entry = byTicker[t];
        (entry.confirmed_events || []).forEach((ev) => {
          if (ev.confidence === 'provider_confirmed' || ev.quality_gated) {
            rows.push({
              ticker: t,
              fi: findMatchingImpact(entry, ev.index, ev.action),
              ...ev,
            });
          }
        });
      });
    rows.sort((a, b) => String(b.announced || '').localeCompare(String(a.announced || '')));
    if (!rows.length) {
      return '<p class="muted">No confirmed index events yet. News headlines appear under News notes.</p>';
    }
    const body = rows
      .slice(0, 40)
      .map((r) => {
        const confLabel =
          r.confidence === 'provider_confirmed' ? 'provider_confirmed' : 'quality_gated';
        const src =
          r.source_url && linkHtml ? linkHtml(r.source_url, confLabel) : e(confLabel);
        const bridge =
          r.fi && r.fi.is_russell_breakpoint_migration
            ? renderFlowBridge(r.fi, e)
            : r.fi
              ? `<span class="muted" title="${esc(pctFloatTooltip(r.fi))}" style="font-size:11px">hover % for band</span>`
              : '';
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.index)}</td>
          <td>${e(r.action)}</td>
          ${renderPctFloatCell(r.fi)}
          <td class="mono">${e(r.announced || '—')}</td>
          <td class="mono">${e(r.effective || '—')}</td>
          <td>${src}${bridge}</td>
        </tr>`;
      })
      .join('');
    return `<h4 style="margin:12px 0 6px;font-size:13px">Confirmed (provider / quality-gated)</h4>
      <table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Action</th><th title="Base-case net forced flow as % of float (signed)">% float</th><th>Announced</th><th>Effective</th><th>Source</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderNewsNotesTable(byTicker, escapeHtml, linkHtml) {
    const e = escapeHtml || esc;
    const rows = [];
    Object.keys(byTicker || {})
      .sort()
      .forEach((t) => {
        const entry = byTicker[t];
        (entry.news_notes || []).forEach((ev) => {
          rows.push({
            ticker: t,
            fi: findMatchingImpact(entry, ev.index, ev.action),
            ...ev,
          });
        });
      });
    rows.sort((a, b) => String(b.announced || '').localeCompare(String(a.announced || '')));
    if (!rows.length) {
      return '<p class="muted">No news index notes.</p>';
    }
    const body = rows
      .slice(0, 40)
      .map((r) => {
        const label = r.style_subset ? 'style/subset' : 'news';
        const src =
          r.source_url && linkHtml ? linkHtml(r.source_url, label) : e(label);
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.index)}</td>
          <td>${e(r.action)}</td>
          ${renderPctFloatCell(r.fi)}
          <td class="mono">${e(r.announced || '—')}</td>
          <td class="mono">${e(r.effective || 'unknown')}</td>
          <td>${src}</td>
        </tr>`;
      })
      .join('');
    return `<h4 style="margin:16px 0 6px;font-size:13px">News notes (unconfirmed)</h4>
      <table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Action</th><th>% float</th><th>Announced</th><th>Effective</th><th>Source</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderFloatImpactsTable(summary, byTicker, escapeHtml) {
    const e = escapeHtml || esc;
    const rows = summary.top_float_impacts || [];
    if (!rows.length) {
      return '<p class="muted">No float-impact estimates yet (need float_pct, ADV, and AUM registry).</p>';
    }
    const stale = summary.aum_stale
      ? ` <span class="badge badge-warn">AUM stale (as-of ${e(summary.aum_as_of || '?')})</span>`
      : summary.aum_as_of
        ? ` <span class="muted">AUM as-of ${e(summary.aum_as_of)}</span>`
        : '';
    const body = rows
      .slice(0, 25)
      .map((r) => {
        const entry = byTicker[r.ticker] || {};
        const fi = primaryFloatImpact(entry) || r;
        const cliff =
          r.hk_weight_cliff_ratio != null
            ? `<span class="badge badge-warn" title="HK weight cliff">~${e(
                Number(r.hk_weight_cliff_ratio).toFixed(1)
              )}×</span>`
            : '—';
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.primary_index || '—')}</td>
          <td>${e(r.action || '—')}</td>
          ${renderPctFloatCell(fi)}
          <td class="mono">${r.pct_of_adv_days == null ? '—' : e(Number(r.pct_of_adv_days).toFixed(2))}</td>
          <td>${cliff}</td>
          <td>${e(r.confidence || '—')}</td>
          <td>${renderFlowBridge(fi, e)}</td>
        </tr>`;
      })
      .join('');
    return `<h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Float impact (forced flow)</h3>
      <p class="muted" style="margin-bottom:8px">Expected net index demand as % of company float. Negative = net forced selling. Both sides of Russell migrations modeled per Horizon Kinetics (2013).${stale}</p>
      <table class="insights-table"><thead><tr>
        <th>Ticker</th><th>Index</th><th>Action</th><th>% float</th><th>ADV days</th><th>HK cliff</th><th>Conf</th><th>Detail</th>
      </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderPotentialTable(byTicker, escapeHtml, filter) {
    const e = escapeHtml || esc;
    const dir = (filter && filter.direction) || 'all';
    const indexFilter = (filter && filter.index) || '';
    const showWeak = !!(filter && filter.showWeak);
    const maxDist = (filter && filter.maxDistanceAbs) != null ? Number(filter.maxDistanceAbs) : 15;
    const rows = [];
    const weakRows = [];
    Object.keys(byTicker || {}).forEach((t) => {
      const entry = byTicker[t];
      const fi = primaryFloatImpact(entry);
      (entry.scorecards || []).forEach((sc) => {
        if (sc.status !== 'inclusion_candidate' && sc.status !== 'deletion_risk') return;
        if (dir === 'inclusion' && sc.status !== 'inclusion_candidate') return;
        if (dir === 'exclusion' && sc.status !== 'deletion_risk') return;
        if (indexFilter && sc.index !== indexFilter) return;
        const dist = sc.distance_to_boundary_pct;
        const near = dist != null && Math.abs(Number(dist)) <= maxDist;
        const row = {
          ticker: t,
          company: entry.company,
          priority: (entry.impact_proxy || {}).priority_score || 0,
          shock: (entry.impact_proxy || {}).demand_shock_pct_of_adv,
          pctFloat: (entry.impact_proxy || {}).pct_of_float_base,
          fi,
          band: (entry.prediction || {}).inclusion_probability_band,
          next: (entry.prediction || {}).next_calendar_event,
          ...sc,
        };
        if (near || sc.status === 'deletion_risk') rows.push(row);
        else weakRows.push(row);
      });
    });
    rows.sort((a, b) => b.priority - a.priority);
    weakRows.sort((a, b) => b.priority - a.priority);
    const display = showWeak ? rows.concat(weakRows) : rows;
    if (!display.length) {
      return `<p class="muted">No near-boundary candidates (|distance| ≤ ${e(String(maxDist))}%).${
        weakRows.length ? ` ${weakRows.length} weak floor-pass hits hidden.` : ''
      }</p>`;
    }
    const body = display
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
          ${renderPctFloatCell(r.fi)}
          <td class="mono">${r.shock == null ? '—' : e(Number(r.shock).toFixed(1) + '% ADV')}</td>
          <td>${e(r.band || '—')}</td>
          <td>${e(nextLabel)}</td>
        </tr>`;
      })
      .join('');
    const weakNote = !showWeak && weakRows.length
      ? `<p class="muted" style="margin-top:6px">${weakRows.length} weak (far-from-boundary) hits hidden. Pass showWeak to expand.</p>`
      : '';
    return `<table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Status</th><th>Gate</th><th>Distance</th><th>Priority</th><th>% float</th><th>Shock</th><th>Prob</th><th>Next event</th>
    </tr></thead><tbody>${body}</tbody></table>${weakNote}`;
  }

  function renderIndexWatch(payload, options) {
    const escapeHtml = (options && options.escapeHtml) || esc;
    const linkHtml = options && options.linkHtml;
    const summary = (payload && payload.portfolio_summary) || {};
    const caption =
      (payload && payload.caption) ||
      'The average large-cap S&P 500 index effect has fallen to near zero since 2010; treat these as research triggers, weighted by demand-shock size, not mechanical trades. Migrations across the Russell 1000/2000 breakpoint are typically net-negative for the promoted stock (Horizon Kinetics 2013).';
    const byTicker = (payload && payload.by_ticker) || {};
    const calendar = (payload && payload.calendar) || [];
    const maxDist = summary.max_candidate_distance_pct != null ? summary.max_candidate_distance_pct : 15;

    const stats = [
      `Candidates: <strong>${(summary.inclusion_candidates || []).length}</strong>`,
      `Deletion risks: <strong>${(summary.deletion_risks || []).length}</strong>`,
      `Confirmed ≤30d: <strong>${(summary.confirmed_next_30d || []).length}</strong>`,
      `Provider events: <strong>${summary.provider_confirmed_events != null ? summary.provider_confirmed_events : (summary.quality_gated_events != null ? summary.quality_gated_events : '—')}</strong>`,
      `News notes: <strong>${summary.news_notes != null ? summary.news_notes : '—'}</strong>`,
      `Float impacts: <strong>${(summary.top_float_impacts || []).length}</strong>`,
    ].join(' · ');

    return `<div class="index-watch-panel">
      <p class="muted" style="margin-bottom:8px">${escapeHtml(caption)}</p>
      <p style="margin-bottom:8px">${stats}</p>
      <h3 style="margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Reconstitution calendar</h3>
      ${renderCalendarStrip(calendar, escapeHtml)}
      ${renderFloatImpactsTable(summary, byTicker, escapeHtml)}
      <h3 style="margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Index events</h3>
      <p class="muted" style="margin-bottom:6px">Confirmed = provider notices or quality-gated headlines with effective dates. News notes are unconfirmed (style-box moves included). % float = base-case net forced flow / company float (signed).</p>
      ${renderConfirmedTable(byTicker, escapeHtml, linkHtml)}
      ${renderNewsNotesTable(byTicker, escapeHtml, linkHtml)}
      <h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Potential (near-boundary)</h3>
      <p class="muted" style="margin-bottom:8px">Only |distance| ≤ ${escapeHtml(String(maxDist))}%. Min-mcap floor passes alone are not candidates.</p>
      ${renderPotentialTable(byTicker, escapeHtml, {
        ...(options && options.filter),
        maxDistanceAbs: maxDist,
        showWeak: !!(options && options.filter && options.filter.showWeak),
      })}
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
