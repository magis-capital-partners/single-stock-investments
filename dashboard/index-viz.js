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
    banding_hold: 'badge-purple',
    committee_watch: 'badge-purple',
    ineligible: 'badge-purple',
    n_a: 'badge-warn',
  };

  const STATUS_LABEL = {
    member: 'Member',
    inclusion_candidate: 'Likely add',
    deletion_risk: 'Deletion risk',
    banding_hold: 'Banding hold',
    committee_watch: 'Committee watch',
    ineligible: 'Ineligible',
    n_a: 'n/a',
  };

  const RECON_LABEL = {
    likely_add: 'likely add',
    banding_hold: 'banding hold',
    likely_delete: 'likely delete',
    committee_watch: 'committee watch',
    size_band_watch: 'size band',
    announced: 'report: announced',
    provisional: 'report: provisional',
    rumor: 'report: rumor',
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
    const watch = new Set([
      'inclusion_candidate',
      'deletion_risk',
      'banding_hold',
      'committee_watch',
    ]);
    let best = null;
    for (const sc of cards) {
      if (!watch.has(sc.status)) continue;
      if (sc.distance_to_boundary_pct == null) continue;
      const a = Math.abs(sc.distance_to_boundary_pct);
      if (best == null || a < Math.abs(best)) best = sc.distance_to_boundary_pct;
    }
    return best;
  }

  function primaryFloatImpact(entry) {
    return (entry && entry.float_impact && entry.float_impact.primary) || null;
  }

  function formatPctFloat(pct, floatFlag) {
    if (pct == null || Number.isNaN(Number(pct))) return '—';
    const n = Number(pct);
    const sign = n > 0 ? '+' : '';
    const core = `${sign}${n.toFixed(1)}%`;
    // Cap-weighted constant when float unknown — asterisk + muted
    if (floatFlag === 'float_unknown') return `~${core}*`;
    return core;
  }

  function pctFloatTone(pct, floatFlag) {
    if (pct == null) return '';
    if (floatFlag === 'float_unknown') return 'color:var(--text-muted, #888)';
    const n = Number(pct);
    if (n < -1) return 'color:var(--accent-red, #c44)';
    if (n > 1) return 'color:var(--accent-green, #2a7)';
    return '';
  }

  function pctFloatTooltip(fi) {
    if (!fi) return 'No float-impact estimate (missing float, ADV, or AUM)';
    if (fi.status === 'n_a') {
      return `n/a: ${fi.reason || 'no size-migration flow'}`;
    }
    const low = fi.pct_of_float_low;
    const base = fi.pct_of_float_base;
    const high = fi.pct_of_float_high;
    const adv = fi.pct_of_adv_days;
    const cliff = fi.hk_weight_cliff_ratio;
    const parts = [
      `low ${formatPctFloat(low, fi.float_flag)} / base ${formatPctFloat(base, fi.float_flag)} / high ${formatPctFloat(high, fi.float_flag)} of float`,
    ];
    if (adv != null) parts.push(`${Number(adv).toFixed(2)} days ADV`);
    if (
      cliff != null &&
      fi.is_russell_breakpoint_migration &&
      fi.float_flag === 'float_adj'
    ) {
      parts.push(`HK cliff ${Number(cliff).toFixed(1)}x`);
    }
    if (fi.aum_stale) parts.push('AUM registry stale');
    if (fi.float_flag === 'float_unknown') {
      parts.push('Cap-weighted constant (AUM ÷ index mcap); not stock-specific — float/ADV missing');
    }
    if (fi.assumed_graduation) parts.push('pair inferred (assumed graduation)');
    if (fi.reason) parts.push(fi.reason);
    return parts.join(' · ');
  }

  function renderPctFloatCell(fi) {
    if (fi && fi.status === 'n_a') {
      const tip = pctFloatTooltip(fi);
      return `<td class="mono muted" title="${esc(tip)}">—</td>`;
    }
    const pct = fi && fi.pct_of_float_base;
    const tip = pctFloatTooltip(fi);
    const tone = pctFloatTone(pct, fi && fi.float_flag);
    return `<td class="mono" style="${tone}" title="${esc(tip)}">${esc(
      formatPctFloat(pct, fi && fi.float_flag)
    )}</td>`;
  }

  function renderHoldingsCell(entry) {
    if (!entry) return '<span style="color:var(--text-muted)">—</span>';
    const status = entry.badge_status || 'n_a';
    const mem = (entry.current_memberships || []).slice(0, 2).join(', ');
    const fi = primaryFloatImpact(entry);
    const floatBit =
      fi && fi.pct_of_float_base != null && fi.status !== 'n_a'
        ? ` · float ${formatPctFloat(fi.pct_of_float_base, fi.float_flag)}`
        : '';
    const watchStatuses = new Set([
      'inclusion_candidate',
      'deletion_risk',
      'banding_hold',
      'committee_watch',
    ]);
    const title = mem
      ? `In: ${mem}${floatBit}`
      : (entry.scorecards || [])
          .filter((s) => watchStatuses.has(s.status))
          .map((s) => `${s.index}: ${s.status}`)
          .slice(0, 3)
          .join('; ') || status;
    const showDist = watchStatuses.has(status);
    return renderBadge(status, {
      distance: showDist ? bestDistance(entry) : null,
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
    if (!fi || fi.status === 'n_a') {
      const why = fi && fi.reason ? fi.reason : 'no size-migration flow';
      return `<p class="muted" title="${e(why)}">— (${e(why)})</p>`;
    }
    if (!fi.legs || !fi.legs.length) {
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
      fi.is_russell_breakpoint_migration &&
      fi.float_flag === 'float_adj' &&
      fi.hk_weight_cliff_ratio != null
        ? `<p style="margin:8px 0 0"><span class="badge badge-warn" title="Horizon Kinetics weight cliff × AUM asymmetry">HK graduation penalty: ~${e(
            Number(fi.hk_weight_cliff_ratio).toFixed(1)
          )}× demand differential</span></p>`
        : '';
    const band = `low ${formatPctFloat(fi.pct_of_float_low, fi.float_flag)} · base ${formatPctFloat(
      fi.pct_of_float_base,
      fi.float_flag
    )} · high ${formatPctFloat(fi.pct_of_float_high, fi.float_flag)} of float`;
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
      return '<p class="muted">No size-membership events yet. Style/subset headlines stay under News notes.</p>';
    }
    const body = rows
      .slice(0, 40)
      .map((r) => {
        const confLabel =
          r.confidence === 'provider_confirmed' ? 'provider' : 'news (size cue)';
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
          <td class="mono">${e(r.effective || 'unknown')}</td>
          <td>${src}${bridge}</td>
        </tr>`;
      })
      .join('');
    return `<h4 style="margin:12px 0 6px;font-size:13px">Size membership events (provider or clear size cue)</h4>
      <table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Action</th><th title="Base-case net forced flow as % of float (signed)">% float</th><th>Announced</th><th>Effective</th><th>Source</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderNewsNotesTable(byTicker, escapeHtml, linkHtml, options) {
    const e = escapeHtml || esc;
    const showStyle = !!(options && options.showStyleSubset);
    const sizeRows = [];
    const styleRows = [];
    Object.keys(byTicker || {})
      .sort()
      .forEach((t) => {
        const entry = byTicker[t];
        (entry.news_notes || []).forEach((ev) => {
          const row = {
            ticker: t,
            fi: findMatchingImpact(entry, ev.index, ev.action),
            ...ev,
          };
          if (ev.style_subset) styleRows.push(row);
          else sizeRows.push(row);
        });
      });
    sizeRows.sort((a, b) => String(b.announced || '').localeCompare(String(a.announced || '')));
    styleRows.sort((a, b) => String(b.announced || '').localeCompare(String(a.announced || '')));
    const rows = showStyle ? sizeRows.concat(styleRows) : sizeRows;
    if (!sizeRows.length && !styleRows.length) {
      return '<p class="muted">No news index notes.</p>';
    }
    const styleToggle =
      styleRows.length && !showStyle
        ? `<p class="muted" style="margin:8px 0">
            ${styleRows.length} style/subset note${styleRows.length === 1 ? '' : 's'} hidden
            (Growth/Value/Defensive/2500/Top 50 — no size-migration flow).
            <button type="button" class="index-toggle-style" style="margin-left:6px;font:inherit;cursor:pointer">Show style notes</button>
          </p>`
        : styleRows.length && showStyle
          ? `<p class="muted" style="margin:8px 0">
              Showing style/subset notes.
              <button type="button" class="index-toggle-style" style="margin-left:6px;font:inherit;cursor:pointer">Hide style notes</button>
            </p>`
          : '';
    if (!rows.length) {
      return `<h4 style="margin:16px 0 6px;font-size:13px">News notes (unconfirmed)</h4>${styleToggle}`;
    }
    const body = rows
      .slice(0, 40)
      .map((r) => {
        const related =
          r.related_indexes && r.related_indexes.length
            ? ` <span class="muted" title="Collapsed related indexes">(+${e(
                r.related_indexes.filter((x) => x !== r.index).join(', ')
              )})</span>`
            : '';
        const label = r.style_subset ? 'style/subset' : r.confidence || 'news';
        const src =
          r.source_url && linkHtml ? linkHtml(r.source_url, label) : e(label);
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.index)}${related}</td>
          <td>${e(r.action)}</td>
          ${renderPctFloatCell(r.fi)}
          <td class="mono">${e(r.announced || '—')}</td>
          <td class="mono">${e(r.effective || 'unknown')}</td>
          <td>${src}</td>
        </tr>`;
      })
      .join('');
    return `<h4 style="margin:16px 0 6px;font-size:13px">News notes (unconfirmed)</h4>
      ${styleToggle}
      <table class="insights-table"><thead><tr>
      <th>Ticker</th><th>Index</th><th>Action</th><th>% float</th><th>Announced</th><th>Effective</th><th>Source</th>
    </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderFloatImpactRows(rows, byTicker, escapeHtml) {
    const e = escapeHtml || esc;
    return rows
      .slice(0, 40)
      .map((r) => {
        const entry = byTicker[r.ticker] || {};
        const fi = primaryFloatImpact(entry) || r;
        const showCliff =
          r.is_russell_breakpoint_migration &&
          r.float_flag === 'float_adj' &&
          r.hk_weight_cliff_ratio != null;
        const cliff = showCliff
          ? `<span class="badge badge-warn" title="HK weight cliff">~${e(
              Number(r.hk_weight_cliff_ratio).toFixed(1)
            )}×</span>`
          : '—';
        const inferred = r.assumed_graduation
          ? ' <span class="badge badge-purple" title="R2000 exit inferred from mcap">pair inferred</span>'
          : '';
        const src = r.confidence || '—';
        return `<tr>
          <td class="mono">${e(r.ticker)}${inferred}</td>
          <td>${e(r.primary_index || '—')}</td>
          <td>${e(r.action || '—')}</td>
          ${renderPctFloatCell(Object.assign({}, fi, r))}
          <td class="mono">${r.pct_of_adv_days == null ? '—' : e(Number(r.pct_of_adv_days).toFixed(2))}</td>
          <td>${cliff}</td>
          <td>${e(src)}</td>
          <td>${renderFlowBridge(fi, e)}</td>
        </tr>`;
      })
      .join('');
  }

  function renderPredictorWatchlist(summary, escapeHtml) {
    const e = escapeHtml || esc;
    const rows = summary.predictor_watch || [];
    if (!rows.length) {
      return `<h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Predictor</h3>
        <p class="muted">No near-boundary predicted adds/deletes. Refresh float/ADV for candidates and append provisional lists to <span class="mono">index_recon_watch.jsonl</span>.</p>`;
    }
    const body = rows
      .slice(0, 40)
      .map((r) => {
        const recon =
          RECON_LABEL[r.recon_status] ||
          RECON_LABEL[r.report_tier] ||
          r.recon_status ||
          '—';
        const next = r.next_calendar_event;
        const nextLabel = next
          ? `${next.label || next.id} (${next.days_out != null ? next.days_out + 'd' : '—'})`
          : '—';
        const fi = {
          pct_of_float_base: r.pct_of_float_base,
          float_flag: r.float_flag,
          status: r.pct_of_float_base == null ? 'n_a' : 'ok',
        };
        return `<tr>
          <td class="mono">${e(r.ticker)}</td>
          <td>${e(r.index || '—')}</td>
          <td>${renderBadge(r.status, { distance: r.distance_to_boundary_pct })}</td>
          <td class="muted">${e(recon)}</td>
          <td class="mono">${r.distance_to_boundary_pct == null ? '—' : e(Number(r.distance_to_boundary_pct).toFixed(1) + '%')}</td>
          ${renderPctFloatCell(fi)}
          <td class="mono">${r.priority_score == null ? '—' : e(Number(r.priority_score).toFixed(2))}</td>
          <td>${e(r.inclusion_probability_band || '—')}</td>
          <td>${e(r.report_tier || '—')}</td>
          <td>${e(nextLabel)}</td>
        </tr>`;
      })
      .join('');
    return `<h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Predictor</h3>
      <p class="muted" style="margin-bottom:8px">Single pre-announcement watchlist: likely adds, banding holds, committee watch, and deletion risks. Expected % float is speculative (asterisk if float unknown). Style/subset headlines never appear here.</p>
      <table class="insights-table"><thead><tr>
        <th>Ticker</th><th>Index</th><th>Status</th><th>Recon</th><th>Distance</th><th>Expected % float</th><th>Priority</th><th>Prob</th><th>Report</th><th>Next event</th>
      </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderFloatImpactsTable(summary, byTicker, escapeHtml) {
    const e = escapeHtml || esc;
    const rows = summary.top_float_impacts || [];
    const stale = summary.aum_stale
      ? ` <span class="badge badge-warn">AUM stale (as-of ${e(summary.aum_as_of || '?')})</span>`
      : summary.aum_as_of
        ? ` <span class="muted">AUM as-of ${e(summary.aum_as_of)}</span>`
        : '';
    if (!rows.length) {
      return `<h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Float impact (forced flow)</h3>
        <p class="muted" style="margin-bottom:8px">Confirmed size-migration events with float-adjusted inputs only. Predicted names are in Predictor below.${stale}</p>
        <p class="muted">No float-adjusted confirmed size-migration impacts yet.</p>`;
    }
    const body = renderFloatImpactRows(rows, byTicker, e);
    return `<h3 style="margin:16px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Float impact (forced flow)</h3>
      <p class="muted" style="margin-bottom:8px">Confirmed net index demand as % of company float. Negative = net forced selling. Predicted / near-boundary names are not listed here.${stale}</p>
      <table class="insights-table"><thead><tr>
        <th>Ticker</th><th>Index</th><th>Action</th><th>% float</th><th>ADV days</th><th>HK cliff</th><th>Conf</th><th>Detail</th>
      </tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderIndexWatch(payload, options) {
    const escapeHtml = (options && options.escapeHtml) || esc;
    const linkHtml = options && options.linkHtml;
    const showStyleSubset = !!(options && options.showStyleSubset);
    const summary = (payload && payload.portfolio_summary) || {};
    const caption =
      (payload && payload.caption) ||
      'The average large-cap S&P 500 index effect has fallen to near zero since 2010; treat these as research triggers, weighted by demand-shock size, not mechanical trades. Migrations across the Russell 1000/2000 breakpoint are typically net-negative for the promoted stock (Horizon Kinetics 2013).';
    const byTicker = (payload && payload.by_ticker) || {};
    const calendar = (payload && payload.calendar) || [];
    const floatCount = (summary.top_float_impacts || []).length;
    const watchCount = (summary.predictor_watch || []).length;
    const stats = [
      `Watch: <strong>${watchCount}</strong>`,
      `Deletion risks: <strong>${(summary.deletion_risks || []).length}</strong>`,
      `Confirmed ≤30d: <strong>${(summary.confirmed_next_30d || []).length}</strong>`,
      `Size events: <strong>${summary.quality_gated_events != null ? summary.quality_gated_events : '—'}</strong>`,
      `News notes: <strong>${summary.news_notes != null ? summary.news_notes : '—'}</strong>` +
        (summary.style_subset_notes
          ? ` <span class="muted">(${summary.style_subset_notes} style)</span>`
          : ''),
      `Float impacts: <strong>${floatCount}</strong>`,
    ].join(' · ');

    return `<div class="index-watch-panel" data-show-style="${showStyleSubset ? '1' : '0'}">
      <p class="muted" style="margin-bottom:8px">${escapeHtml(caption)}</p>
      <p style="margin-bottom:8px">${stats}</p>
      <h3 style="margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Reconstitution calendar</h3>
      ${renderCalendarStrip(calendar, escapeHtml)}
      ${renderFloatImpactsTable(summary, byTicker, escapeHtml)}
      ${renderPredictorWatchlist(summary, escapeHtml)}
      <h3 style="margin:12px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-secondary)">Index events</h3>
      <p class="muted" style="margin-bottom:6px">Size events = provider notices or headlines with an explicit parent-index add/delete cue. Style/subset notes (Growth/Value/Defensive/2500) are hidden by default and never drive float impact. % float = base-case net forced flow / company float (signed).</p>
      ${renderConfirmedTable(byTicker, escapeHtml, linkHtml)}
      ${renderNewsNotesTable(byTicker, escapeHtml, linkHtml, { showStyleSubset })}
    </div>`;
  }

  function bindIndexWatchToggles(root, payload, options) {
    if (!root || !payload) return;
    const opts = options || {};
    const panel = root.querySelector('.index-watch-panel');
    if (!panel) return;
    const rerender = (patch) => {
      const next = {
        ...opts,
        showStyleSubset: !!(patch.showStyleSubset != null
          ? patch.showStyleSubset
          : panel.getAttribute('data-show-style') === '1'),
      };
      const wrap = document.createElement('div');
      wrap.innerHTML = renderIndexWatch(payload, next);
      const fresh = wrap.firstElementChild;
      if (fresh) panel.replaceWith(fresh);
      bindIndexWatchToggles(root, payload, next);
    };
    panel.querySelectorAll('.index-toggle-style').forEach((btn) => {
      btn.addEventListener('click', () => {
        rerender({ showStyleSubset: panel.getAttribute('data-show-style') !== '1' });
      });
    });
  }

  global.IndexViz = {
    renderBadge,
    renderHoldingsCell,
    renderIndexWatch,
    bindIndexWatchToggles,
    renderCalendarStrip,
    BADGE_CLASS,
    STATUS_LABEL,
  };
})(window);
