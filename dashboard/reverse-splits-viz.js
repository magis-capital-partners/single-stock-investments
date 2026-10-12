/**
 * Reverse splits — discovery ledger, upcoming effective dates, repeat
 * splitters, the persisted book and the RSI-1.0 paper process.
 *
 * Renders `dashboard/data/reverse_splits.json` (schema
 * `reverse_splits.v1`, built by _system/scripts/build_reverse_splits_dashboard.py
 * from the JSONL ledger in _system/data/reverse_splits/) as one compact panel
 * in the style of short-alpha-viz.js: count tiles, a recent-announcements
 * table, upcoming effective dates, repeat splitters, the latest book runs, the
 * process rules as a definition list, the honest limits and the caption.
 * Everything is escaped; a missing number renders as a dash, never as zero.
 *
 * Research only. Nothing here changes a value, an IRR or a position. The
 * mount point lives with the Shorts tab; this file only exposes
 * `window.ReverseSplitsViz.render(doc, opts)` and returns HTML.
 */
(function (global) {
  'use strict';

  const esc = (value) => String(value == null ? '' : value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const OUTCOME_LABEL = {
    announced_only: 'Announced',
    mention: 'Mention',
    cancelled: 'Cancelled',
    effective: 'Effective',
  };
  const OUTCOME_BADGE = {
    announced_only: 'badge-warn',
    mention: 'badge-purple',
    cancelled: 'badge-bad',
    effective: 'badge-ok',
  };
  const QUALITY_LABEL = {
    filing_text: 'filing text',
    acceptance_time: 'accept clock',
    search_hit: 'phrase hit',
  };
  const CLASS_LABEL = { listed: 'Listed', otc: 'OTC', unknown: 'Unknown' };
  const COHORT_LABEL = { first: 'First', second: 'Second', third_plus: 'Third+' };
  const RULE_LABEL = {
    score_floor: 'Fundamental score floor (0-100)',
    fundamental_max_age_days: 'Latest period age, max days',
    announcement_max_age_days: 'Announcement age, max calendar days',
    max_hold_sessions: 'Maximum hold, sessions (incl. entry)',
    carry_calendar_days: 'Carry window, calendar days',
    max_names: 'Maximum names',
    name_loss_fraction: 'Name loss budget, fraction of equity',
    sleeve_loss_fraction: 'Sleeve loss budget, fraction of equity',
    notional_fraction: 'Notional cap, fraction of equity',
    participation: 'Participation, fraction of prior 20-session ADV',
    stress_price_increase: 'Stress price increase (2.0 = +200%)',
    margin_buffer: 'Margin buffer, fraction of equity',
    net_downside_floor: 'Net downside floor (after costs and carry)',
    gross_downside_floor: 'Gross downside floor',
    carry_fraction_ceiling: 'Carry ceiling, fraction of notional',
    minimum_notional: 'Minimum notional, USD',
    locate_max_age_hours: 'Locate age, max hours',
    quote_max_age_minutes: 'Quote age, max minutes',
  };

  function isNum(value) {
    return value != null && value !== '' && Number.isFinite(Number(value));
  }
  function label(table, key, fallback) {
    if (key == null || key === '') return fallback == null ? '—' : fallback;
    return table[key] || String(key).replaceAll('_', ' ');
  }
  function fmtInt(value) {
    return isNum(value) ? Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—';
  }
  function fmtMoney(value) {
    if (!isNum(value)) return '—';
    const n = Number(value);
    const body = Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
    return `${n < 0 ? '-' : n > 0 ? '+' : ''}$${body}`;
  }
  function fmtNum(value, digits) {
    return isNum(value) ? Number(value).toFixed(digits == null ? 2 : digits) : '—';
  }
  /** `ratio` is new/old: 0.1 is a 1-for-10. 1 means no ratio was parsed. */
  function fmtRatio(ratio) {
    if (!isNum(ratio)) return '—';
    const r = Number(ratio);
    if (r <= 0 || r >= 1) return '—';
    const old = 1 / r;
    const rounded = Math.abs(old - Math.round(old)) < 1e-6 ? Math.round(old).toString() : old.toFixed(2);
    return `1-for-${rounded}`;
  }
  function fmtRule(key, value) {
    if (!isNum(value)) return '—';
    const n = Number(value);
    if (/fraction|floor|ceiling|participation|buffer/.test(key) && n < 1) return `${(n * 100).toFixed(n * 100 < 1 ? 2 : 1)}%`;
    if (key === 'stress_price_increase') return `+${(n * 100).toFixed(0)}%`;
    if (key === 'minimum_notional') return `$${n.toLocaleString('en-US')}`;
    return n.toLocaleString('en-US');
  }
  function link(url, text) {
    if (!url) return esc(text);
    try {
      const parsed = new URL(String(url));
      if (!['http:', 'https:'].includes(parsed.protocol)) return esc(text);
      return `<a href="${esc(parsed.href)}" target="_blank" rel="noopener">${esc(text)}</a>`;
    } catch (_) {
      return esc(text);
    }
  }
  function badge(cls, text, title) {
    return `<span class="badge ${esc(cls)}"${title ? ` title="${esc(title)}"` : ''}>${esc(text)}</span>`;
  }

  const STYLE = `<style>
.rs-panel{font-size:13px}
.rs-panel .rs-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin-bottom:6px}
.rs-panel .rs-head h2{margin:0;font-size:16px}
.rs-panel .rs-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px;margin:8px 0 12px}
.rs-panel .rs-tile{border:1px solid rgba(127,127,127,.3);border-radius:8px;padding:8px 10px}
.rs-panel .rs-tile strong{display:block;font-size:18px;line-height:1.2}
.rs-panel .rs-tile small{display:block;opacity:.75;margin-top:2px}
.rs-panel .rs-tile em{display:block;font-size:11px;opacity:.7;font-style:normal;margin-top:2px}
.rs-panel section{margin-top:14px}
.rs-panel h3{margin:0 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;opacity:.8}
.rs-panel table.insights-table{width:100%}
.rs-panel dl.rs-rules{display:grid;grid-template-columns:minmax(220px,2fr) minmax(80px,1fr);gap:2px 12px;margin:4px 0}
.rs-panel dl.rs-rules dt{opacity:.8}
.rs-panel dl.rs-rules dd{margin:0;font-family:ui-monospace,Menlo,Consolas,monospace}
.rs-panel ul.rs-limits{margin:4px 0 0 18px;padding:0}
.rs-panel ul.rs-limits li{margin:2px 0}
.rs-panel .rs-counts{display:flex;flex-wrap:wrap;gap:14px;font-size:12px}
</style>`;

  function renderHead(doc) {
    const health = doc.health || {};
    const status = health.status || 'unknown';
    const problems = [...(health.structural_errors || []), ...(health.problems || [])];
    const healthBadge = badge(status === 'healthy' ? 'badge-ok' : 'badge-bad', `feed ${status}`, problems.join('\n') || 'No problems reported');
    const ledger = doc.ledger || {};
    const stamp = ledger.exported_at ? `ledger exported ${String(ledger.exported_at).slice(0, 10)}` : 'ledger stamp missing';
    return `<div class="rs-head">
      <h2>Reverse splits</h2>
      ${badge('badge-purple', 'research only', 'authority: none; not in base IRR')}
      ${healthBadge}
      <span class="muted mono">as of ${esc(doc.as_of || '—')} · ${esc(stamp)}</span>
    </div>
    <p class="subhead">${esc(doc.definition || '')}</p>`;
  }

  function renderTiles(doc) {
    const c = doc.counts || {};
    const book = doc.book || {};
    const latest = book.latest_run || null;
    const dec = doc.decisions_summary || {};
    const tiles = [
      { n: c.events, label: 'Completed splits', note: 'events with an ex date' },
      { n: c.announcements, label: 'Announcements', note: doc.ledger && doc.ledger.announcements_since ? `since ${doc.ledger.announcements_since}` : 'phrase hits that did not print' },
      { n: c.announcements_last_90_days, label: 'Last 90 days', note: 'announcements' },
      { n: (doc.upcoming_effective || []).length, label: 'Upcoming ex dates', note: 'known or announced' },
      { n: c.repeat_issuers, label: 'Repeat issuers', note: 'second or later split' },
      { n: dec.count, label: 'Decisions', note: dec.latest_at ? `latest ${String(dec.latest_at).slice(0, 10)}` : 'append-only journal' },
    ];
    const html = tiles.map((t) => `<div class="rs-tile"><strong>${fmtInt(t.n)}</strong><small>${esc(t.label)}</small><em>${esc(t.note)}</em></div>`).join('');
    const bookTile = latest
      ? `<div class="rs-tile" title="${esc(latest.label || '')}"><strong>${esc(fmtMoney(latest.net_pnl))}</strong><small>Latest book run</small><em>${esc(latest.label || '—')} · ${fmtInt(latest.taken)} trades</em></div>`
      : `<div class="rs-tile"><strong>—</strong><small>Latest book run</small><em>no persisted runs</em></div>`;
    return `<div class="rs-tiles">${html}${bookTile}</div>`;
  }

  function renderCounts(doc) {
    const c = doc.counts || {};
    const part = (title, table, map) => {
      const rows = Object.entries(table || {});
      if (!rows.length) return '';
      return `<span><strong>${esc(title)}:</strong> ${rows.map(([k, v]) => `${esc(label(map || {}, k, k))} ${fmtInt(v)}`).join(' · ')}</span>`;
    };
    return `<div class="rs-counts">
      ${part('Cohort', c.by_cohort, COHORT_LABEL)}
      ${part('Exchange', c.by_exchange_class, CLASS_LABEL)}
      ${part('Announcement outcome', c.announcements_by_outcome, OUTCOME_LABEL)}
      ${part('Ex year', c.by_year)}
    </div>`;
  }

  function renderUpcoming(doc) {
    const rows = doc.upcoming_effective || [];
    if (!rows.length) return '<section><h3>Upcoming effective dates</h3><p class="muted">None known or announced on or after the as-of date.</p></section>';
    const body = rows.map((r) => `<tr>
        <td class="mono">${esc(r.ex_date || '—')}</td>
        <td class="mono">${link(r.url, r.ticker || '—')}</td>
        <td>${esc(r.company || '—')}</td>
        <td class="mono">${esc(fmtRatio(r.ratio))}</td>
        <td>${esc(label(CLASS_LABEL, r.exchange_class))}</td>
        <td>${r.basis === 'event' ? badge('badge-ok', 'event', 'completed or candidate split in the events ledger') : badge(OUTCOME_BADGE[r.outcome] || 'badge-warn', `announced · ${label(OUTCOME_LABEL, r.outcome, 'announced')}`, 'schedule parsed from the filing text; the split may not print')}</td>
        <td class="mono">${esc(r.announce_date || '—')}</td>
      </tr>`).join('');
    return `<section><h3>Upcoming effective dates</h3>
      <table class="insights-table"><thead><tr><th>Ex date</th><th>Ticker</th><th>Company</th><th>Ratio</th><th>Exchange</th><th>Basis</th><th>Announced</th></tr></thead><tbody>${body}</tbody></table>
      <p class="muted" style="margin-top:4px;font-size:11px">An announced schedule is filing text, not an analyst-confirmed corporate action. The ratio is new/old shares; a dash means no ratio was parsed.</p>
    </section>`;
  }

  function renderRecent(doc, opts) {
    const rows = doc.recent_announcements || [];
    const max = opts.maxRecent == null ? 25 : opts.maxRecent;
    if (!rows.length) return '<section><h3>Recent announcements</h3><p class="muted">No 8-K/6-K reverse-split filings in the last 90 days of the ledger.</p></section>';
    const line = (r) => `<tr>
        <td class="mono">${esc(r.announce_date || '—')}</td>
        <td class="mono">${link(r.url, r.ticker || '—')}</td>
        <td>${esc(r.company || '—')}</td>
        <td>${esc(label(CLASS_LABEL, r.exchange_class))}</td>
        <td class="mono">${esc(fmtRatio(r.ratio))}</td>
        <td class="mono">${esc(r.announced_ex_date || '—')}</td>
        <td>${badge(OUTCOME_BADGE[r.outcome] || 'badge-purple', label(OUTCOME_LABEL, r.outcome, 'announced'))}</td>
        <td class="muted">${esc(label(QUALITY_LABEL, r.date_quality, '—'))}${r.form ? ` · ${esc(r.form)}` : ''}</td>
      </tr>`;
    const head = '<thead><tr><th>Filed</th><th>Ticker</th><th>Company</th><th>Exchange</th><th>Ratio</th><th>Scheduled</th><th>Outcome</th><th>Evidence</th></tr></thead>';
    const shown = rows.slice(0, max).map(line).join('');
    const rest = rows.slice(max);
    const more = rest.length
      ? `<details style="margin-top:6px"><summary style="cursor:pointer;font-size:12px">${rest.length} more in the last 90 days</summary><table class="insights-table" style="margin-top:6px">${head}<tbody>${rest.map(line).join('')}</tbody></table></details>`
      : '';
    return `<section><h3>Recent announcements <span class="muted" style="font-weight:normal;text-transform:none;letter-spacing:0">(${rows.length} in 90 days, newest first)</span></h3>
      <table class="insights-table">${head}<tbody>${shown}</tbody></table>${more}
      <p class="muted" style="margin-top:4px;font-size:11px">Outcome comes from the parsed filing where text was read: <em>Mention</em> is reverse-split language without an action, <em>Cancelled</em> an abandonment. Phrase hits and accept-clock rows have not been read.</p>
    </section>`;
  }

  function renderRepeat(doc) {
    const rows = doc.repeat_splitters || [];
    if (!rows.length) return '';
    const body = rows.map((r) => `<tr>
        <td class="mono">${link(r.url, r.ticker || '—')}</td>
        <td>${esc(r.company || '—')}</td>
        <td class="mono">${fmtInt(r.prior_rs_count)}</td>
        <td>${esc(label(COHORT_LABEL, r.cohort))}</td>
        <td class="mono">${esc(r.last_ex_date || '—')}</td>
        <td class="mono">${esc(fmtRatio(r.last_ratio))}</td>
        <td>${esc(label(CLASS_LABEL, r.exchange_class))}</td>
      </tr>`).join('');
    return `<section><h3>Repeat splitters</h3>
      <table class="insights-table"><thead><tr><th>Ticker</th><th>Company</th><th>Prior splits</th><th>Cohort</th><th>Last ex date</th><th>Last ratio</th><th>Exchange</th></tr></thead><tbody>${body}</tbody></table>
      <p class="muted" style="margin-top:4px;font-size:11px">Prior count is by CIK where known, else by ticker; a ticker reused by another issuer can inflate it. Most recent first, capped at ${rows.length}.</p>
    </section>`;
  }

  function renderBook(doc) {
    const book = doc.book || {};
    const batch = book.latest_batch || [];
    if (!batch.length) return '<section><h3>Book</h3><p class="muted">No persisted book runs in the ledger.</p></section>';
    const body = batch.map((r) => `<tr>
        <td>${esc(r.label || '—')}</td>
        <td class="mono">${fmtInt(r.taken)}</td>
        <td class="mono">${esc(fmtMoney(r.net_pnl))}</td>
        <td class="mono">${esc(fmtMoney(r.gross_after_fills))}</td>
        <td class="mono">${esc(fmtMoney(isNum(r.borrow) ? -Number(r.borrow) : null))}</td>
        <td class="mono">${esc(fmtMoney(isNum(r.commission) ? -Number(r.commission) : null))}</td>
        <td class="mono">${esc(fmtNum(r.profit_factor))}</td>
        <td class="mono">${fmtInt(r.losses_over_50pct)}</td>
        <td class="mono">${fmtInt(r.margin_breach_days)}</td>
      </tr>`).join('');
    const stamp = book.latest_run && book.latest_run.created_at ? String(book.latest_run.created_at) : '—';
    return `<section><h3>Book · latest persisted batch <span class="muted" style="font-weight:normal;text-transform:none;letter-spacing:0">(${esc(stamp)} · ${fmtInt(book.run_count)} runs on file)</span></h3>
      <table class="insights-table"><thead><tr><th>Scenario</th><th>Trades</th><th>Net P&amp;L</th><th>After fills</th><th>Borrow</th><th>Commission</th><th>Profit factor</th><th>Losses &gt;50%</th><th>Margin breach days</th></tr></thead><tbody>${body}</tbody></table>
      <p class="muted" style="margin-top:4px;font-size:11px">${esc(book.note || '')} Scenarios are predeclared sensitivities on one $50k account with assumed fees; <em>strict</em> and <em>verified_strict</em> are empty because no historical locate exists.</p>
    </section>`;
  }

  function renderProcess(doc) {
    const p = doc.process || {};
    const rules = p.rules || {};
    const dl = Object.keys(rules).map((k) => `<dt>${esc(label(RULE_LABEL, k, k))}</dt><dd>${esc(fmtRule(k, rules[k]))}</dd>`).join('');
    const gates = (p.gates || []).map((g) => `<li><strong>${esc(g.label || g.id || '—')}</strong>: ${esc(g.requires || '')}</li>`).join('');
    const policy = p.policy || {};
    const policyRows = ['entry', 'selection', 'payoff', 'sizing', 'exit'].filter((k) => policy[k]).map((k) => `<dt>${esc(k)}</dt><dd style="font-family:inherit">${esc(policy[k])}</dd>`).join('');
    const dec = doc.decisions_summary || {};
    const byDecision = Object.entries(dec.by_decision || {}).map(([k, v]) => `${esc(k)} ${fmtInt(v)}`).join(' · ');
    return `<section><h3>Process · ${esc(p.version || 'RSI-1.0')} <span class="muted" style="font-weight:normal;text-transform:none;letter-spacing:0">(${esc(p.mode || 'paper research')}, adopted ${esc(p.adopted_on || '—')})</span></h3>
      <p class="subhead">${esc(p.hypothesis || '')}</p>
      <dl class="rs-rules">${dl}</dl>
      <details style="margin-top:6px"><summary style="cursor:pointer;font-size:12px">Entry gates (${(p.gates || []).length}) and written policy</summary>
        <ol style="margin:6px 0 0 18px;padding:0">${gates}</ol>
        <dl class="rs-rules" style="grid-template-columns:minmax(70px,auto) 1fr;margin-top:8px">${policyRows}</dl>
      </details>
      <p class="muted" style="margin-top:6px;font-size:12px">Decision journal: ${fmtInt(dec.count)} record${dec.count === 1 ? '' : 's'}${byDecision ? ` (${byDecision})` : ''}${dec.latest_at ? `, latest ${esc(String(dec.latest_at).slice(0, 19).replace('T', ' '))} UTC` : ''}; hash chain ${dec.chain_valid === false ? badge('badge-bad', 'broken') : badge('badge-ok', 'intact')}. ${esc(dec.note || '')} Governance record: the 2026-10-11 hub proposal; operative doc: <span class="mono">${esc(p.doc || '_system/frameworks/reverse_split_short_process.md')}</span>.</p>
    </section>`;
  }

  function renderLimits(doc) {
    const limits = (doc.book && doc.book.honest_limits) || [];
    if (!limits.length) return '';
    return `<section><h3>Honest limits</h3><ul class="rs-limits">${limits.map((l) => `<li>${esc(l)}</li>`).join('')}</ul></section>`;
  }

  /**
   * Full panel. `doc` is the parsed reverse_splits.json; `opts.maxRecent`
   * caps the visible recent-announcement rows (the rest fold into a details).
   * Returns HTML; the caller mounts it.
   */
  function render(doc, options) {
    const opts = options || {};
    if (!doc || typeof doc !== 'object') {
      return `${STYLE}<div class="rs-panel"><p class="muted">Reverse-split feed not loaded.</p></div>`;
    }
    if (doc.schema_version && doc.schema_version !== 'reverse_splits.v1') {
      return `${STYLE}<div class="rs-panel"><p class="muted">Unexpected reverse-split schema ${esc(doc.schema_version)}; expected reverse_splits.v1.</p></div>`;
    }
    return `${STYLE}<div class="rs-panel" data-schema="${esc(doc.schema_version || '')}">
      ${renderHead(doc)}
      ${renderTiles(doc)}
      ${renderCounts(doc)}
      ${renderUpcoming(doc)}
      ${renderRecent(doc, opts)}
      ${renderRepeat(doc)}
      ${renderBook(doc)}
      ${renderProcess(doc)}
      ${renderLimits(doc)}
      <p class="subhead" style="margin-top:12px">${esc(doc.caption || '')}</p>
    </div>`;
  }

  global.ReverseSplitsViz = {
    render,
    fmtRatio,
    fmtMoney,
    OUTCOME_LABEL,
    CLASS_LABEL,
    COHORT_LABEL,
  };
})(window);
