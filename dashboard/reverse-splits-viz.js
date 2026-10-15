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
  const SOURCE_LABEL = {
    databento_price_jump: 'Databento price jump',
    yfinance: 'yfinance seed',
    edgar_search: 'EDGAR',
  };
  const EX_STATUS_LABEL = { scheduled: 'scheduled', effective: 'effective', cancelled: 'cancelled' };
  const RATIO_FLAG_LABEL = {
    extreme: 'Worse than 1-for-500: verify against the filing text before using it.',
    disagrees_with_announced: 'Differs by more than 10% from the ratio parsed from the announcement: verify against the filing text.',
  };
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

  /** `opts.hideTitle` drops the panel's own h2 when the host section already titles it. */
  function renderHead(doc, opts) {
    const health = doc.health || {};
    const status = health.status || 'unknown';
    const problems = [...(health.structural_errors || []), ...(health.problems || [])];
    const healthBadge = badge(status === 'healthy' ? 'badge-ok' : 'badge-bad', `feed ${status}`, problems.join('\n') || 'No problems reported');
    const ledger = doc.ledger || {};
    const stamp = ledger.exported_at ? `ledger exported ${String(ledger.exported_at).slice(0, 10)}` : 'ledger stamp missing';
    return `<div class="rs-head">
      ${opts && opts.hideTitle ? '' : '<h2>Reverse splits</h2>'}
      ${badge('badge-purple', 'research only', 'authority: none; not in base IRR')}
      ${healthBadge}
      <span class="muted mono">as of ${esc(doc.as_of || '—')} · ${esc(stamp)}</span>
    </div>
    <p class="subhead">${esc(doc.definition || '')}</p>`;
  }

  function coverageNames(doc) {
    const cov = doc.coverage || {};
    const names = { listed: 'listed', otc: 'OTC', unknown: 'unclassified' };
    return (cov.skewed_classes || []).map((k) => names[k] || String(k)).join(' and ');
  }

  function renderTiles(doc) {
    const c = doc.counts || {};
    const book = doc.book || {};
    // Headline the predeclared baseline, not whichever scenario was persisted last.
    const headline = book.headline_run || book.latest_run || null;
    const dec = doc.decisions_summary || {};
    const span = c.first_ex_date && c.last_ex_date ? `ex dates ${String(c.first_ex_date).slice(0, 4)}-${String(c.last_ex_date).slice(0, 4)}` : 'events with an ex date';
    const partial = coverageNames(doc);
    const recent90 = isNum(c.announcement_issuers_last_90_days) ? `announcements · ${fmtInt(c.announcement_issuers_last_90_days)} issuers` : 'announcements';
    const tiles = [
      { n: c.events, label: 'Split events and candidates', note: partial ? `${span} · ${partial} partial` : span, title: (doc.coverage && doc.coverage.note) || 'Includes events requiring source review' },
      { n: c.announcements, label: 'Announcements', note: doc.ledger && doc.ledger.announcements_since ? `since ${doc.ledger.announcements_since}` : 'phrase hits that did not print' },
      { n: c.announcements_last_90_days, label: 'Last 90 days', note: recent90 },
      { n: isNum(c.upcoming_effective) ? c.upcoming_effective : (doc.upcoming_effective || []).length, label: 'Upcoming ex dates', note: 'known or announced' },
      { n: c.repeat_issuers, label: 'Repeat issuers', note: c.duplicate_event_rows ? `second or later split · ${fmtInt(c.duplicate_event_rows)} duplicate rows merged` : 'second or later split' },
      { n: dec.count, label: 'Decisions', note: dec.latest_at ? `latest ${String(dec.latest_at).slice(0, 10)}` : 'append-only journal' },
    ];
    const html = tiles.map((t) => `<div class="rs-tile"${t.title ? ` title="${esc(t.title)}"` : ''}><strong>${fmtInt(t.n)}</strong><small>${esc(t.label)}</small><em>${esc(t.note)}</em></div>`).join('');
    let bookTile = '<div class="rs-tile"><strong>—</strong><small>Latest book run</small><em>no persisted runs</em></div>';
    if (headline) {
      const tag = headline.superseded ? 'superseded' : headline.baseline ? 'baseline' : 'latest';
      const range = Array.isArray(book.batch_net_range) && book.batch_net_range.length === 2
        ? `Scenarios that traded in this batch: ${fmtMoney(book.batch_net_range[0])} to ${fmtMoney(book.batch_net_range[1])}.`
        : '';
      const tip = [headline.label || '', headline.superseded || '', range].filter(Boolean).join(' ');
      bookTile = `<div class="rs-tile" title="${esc(tip)}"><strong>${esc(fmtMoney(headline.net_pnl))}</strong><small>Latest book run</small><em>${esc(tag)} · ${esc(headline.label || '—')} · ${fmtInt(headline.taken)} trades</em></div>`;
    }
    return `<div class="rs-tiles">${html}${bookTile}</div>`;
  }

  function renderCounts(doc) {
    const c = doc.counts || {};
    const part = (title, table, map) => {
      const rows = Object.entries(table || {});
      if (!rows.length) return '';
      return `<span><strong>${esc(title)}:</strong> ${rows.map(([k, v]) => `${esc(label(map || {}, k, k))} ${fmtInt(v)}`).join(' · ')}</span>`;
    };
    const statuses = Object.entries(c.events_by_status || {}).map(([k, v]) => `${k.replaceAll('_', ' ')} ${fmtInt(v)}`).join(' · ');
    const review = isNum(c.events_needs_review)
      ? `<span title="${esc(`Rows with needs_review = 1: found in printed prices or an EDGAR search and not yet confirmed by a person. Status: ${statuses || 'not reported'}`)}"><strong>Needs review:</strong> ${fmtInt(c.events_needs_review)} of ${fmtInt(c.events)}</span>`
      : '';
    return `<div class="rs-counts">
      ${part('Source', c.events_by_source, SOURCE_LABEL)}
      ${review}
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

  /** An announced-only row with neither a ratio nor an ex date is a phrase hit, not a schedule. */
  function isPhraseHit(r) {
    if (typeof r.phrase_hit === 'boolean') return r.phrase_hit;
    return (r.outcome || 'announced_only') === 'announced_only' && !isNum(r.ratio) && !r.announced_ex_date;
  }
  /** A date before the as-of date reads as effective, never as scheduled. */
  function exDateCell(r, asOf) {
    if (!r.announced_ex_date) return '—';
    let status = r.ex_date_status;
    if (!status) status = r.outcome === 'cancelled' ? 'cancelled' : (asOf && String(r.announced_ex_date) < String(asOf) ? 'effective' : 'scheduled');
    const before = r.ex_date_before_filing ? ' title="This date precedes the filing: the filing reports a split already in effect, or quotes an older one."' : '';
    return `<span${before}>${esc(r.announced_ex_date)}</span> <span class="muted">${esc(label(EX_STATUS_LABEL, status, ''))}</span>`;
  }

  function renderRecent(doc, opts) {
    const rows = doc.recent_announcements || [];
    const c = doc.counts || {};
    const max = opts.maxRecent == null ? 25 : opts.maxRecent;
    if (!rows.length) return '<section><h3>Recent announcements</h3><p class="muted">No 8-K/6-K reverse-split filings in the last 90 days of the ledger.</p></section>';
    const line = (r) => {
      const phrase = isPhraseHit(r);
      const outcome = phrase
        ? badge('badge-muted', 'Phrase hit', 'Reverse-split words in an 8-K/6-K with no ratio and no ex date parsed: not a schedule.')
        : badge(OUTCOME_BADGE[r.outcome] || 'badge-purple', label(OUTCOME_LABEL, r.outcome, 'announced'));
      const filings = isNum(r.filings_in_window) && Number(r.filings_in_window) > 1 ? ` · ${fmtInt(r.filings_in_window)} filings in 90 days` : '';
      return `<tr>
        <td class="mono">${esc(r.announce_date || '—')}</td>
        <td class="mono">${link(r.url, r.ticker || '—')}</td>
        <td>${esc(r.company || '—')}</td>
        <td>${esc(label(CLASS_LABEL, r.exchange_class))}</td>
        <td class="mono">${esc(fmtRatio(r.ratio))}</td>
        <td class="mono">${exDateCell(r, doc.as_of)}</td>
        <td>${outcome}</td>
        <td class="muted">${esc(label(QUALITY_LABEL, r.date_quality, '—'))}${r.form ? ` · ${esc(r.form)}` : ''}${esc(filings)}</td>
      </tr>`;
    };
    const head = '<thead><tr><th>Filed</th><th>Ticker</th><th>Company</th><th>Exchange</th><th>Ratio</th><th>Ex date</th><th>Outcome</th><th>Evidence</th></tr></thead>';
    const shown = rows.slice(0, max).map(line).join('');
    const rest = rows.slice(max);
    const total = isNum(c.announcements_last_90_days) ? Number(c.announcements_last_90_days) : null;
    const issuers = isNum(c.announcement_issuers_last_90_days) ? ` from ${fmtInt(c.announcement_issuers_last_90_days)} issuers` : '';
    const perIssuer = rows.some((r) => r.filings_in_window != null) ? ', one row per issuer' : ', newest first';
    const scope = total == null
      ? `showing newest ${fmtInt(rows.length)}${perIssuer}`
      : `${fmtInt(total)} filings${issuers} in 90 days · showing newest ${fmtInt(rows.length)}${perIssuer}`;
    const more = rest.length
      ? `<details style="margin-top:6px"><summary style="cursor:pointer;font-size:12px">${fmtInt(rest.length)} more of the newest ${fmtInt(rows.length)}</summary><table class="insights-table" style="margin-top:6px">${head}<tbody>${rest.map(line).join('')}</tbody></table></details>`
      : '';
    return `<section><h3>Recent announcements <span class="muted" style="font-weight:normal;text-transform:none;letter-spacing:0">(${esc(scope)})</span></h3>
      <table class="insights-table">${head}<tbody>${shown}</tbody></table>${more}
      <p class="muted" style="margin-top:4px;font-size:11px">Outcome comes from the parsed filing where text was read: <em>Mention</em> is reverse-split language without an action, <em>Cancelled</em> an abandonment, <em>Phrase hit</em> an announced-only row with no ratio and no ex date. An ex date before the as-of date reads as effective. Accept-clock rows have not been read.</p>
    </section>`;
  }

  function renderRepeat(doc) {
    const rows = doc.repeat_splitters || [];
    if (!rows.length) return '';
    const merged = rows.reduce((n, r) => n + (isNum(r.duplicates_merged) ? Number(r.duplicates_merged) : 0), 0);
    const body = rows.map((r) => {
      const company = r.cik_source === 'announcement_ticker'
        ? `<span title="Issuer matched by ticker to the announcement ledger; the event row carries no CIK.">${esc(r.company || '—')}*</span>`
        : esc(r.company || '—');
      const flag = r.ratio_flag ? ` ${badge('badge-warn', 'verify', RATIO_FLAG_LABEL[r.ratio_flag] || String(r.ratio_flag))}` : '';
      return `<tr>
        <td class="mono">${link(r.url, r.ticker || '—')}</td>
        <td>${company}</td>
        <td class="mono">${fmtInt(r.prior_rs_count)}</td>
        <td>${esc(label(COHORT_LABEL, r.cohort))}</td>
        <td class="mono">${esc(r.last_ex_date || '—')}</td>
        <td class="mono">${esc(fmtRatio(r.last_ratio))}${flag}</td>
        <td>${esc(label(CLASS_LABEL, r.exchange_class))}</td>
      </tr>`;
    }).join('');
    return `<section><h3>Repeat splitters</h3>
      <table class="insights-table"><thead><tr><th>Ticker</th><th>Company</th><th>Prior splits</th><th>Cohort</th><th>Last ex date</th><th>Last ratio</th><th>Exchange (current)</th></tr></thead><tbody>${body}</tbody></table>
      <p class="muted" style="margin-top:4px;font-size:11px">Prior count is by CIK where known, else by ticker; a ticker reused by another issuer can inflate it. The same split recorded twice (same issuer, ratio within 10%, ex dates within ten days) counts once${merged ? `; ${fmtInt(merged)} such row${merged === 1 ? '' : 's'} merged here` : ''}. Exchange is today's SEC listing, not the listing on the ex date. <em>verify</em> marks a ratio worse than 1-for-500 or one that disagrees with the announcement. Most recent first, capped at ${rows.length}.</p>
    </section>`;
  }

  function renderBook(doc) {
    const book = doc.book || {};
    const batch = book.latest_batch || [];
    if (!batch.length) return '<section><h3>Book</h3><p class="muted">No persisted book runs in the ledger.</p></section>';
    const tag = (r) => {
      if (r.superseded) return ` ${badge('badge-bad', 'superseded', r.superseded)}`;
      if (r.baseline) return ` ${badge('badge-ok', 'baseline', 'The predeclared comparator the tile headlines.')}`;
      return '';
    };
    const body = batch.map((r) => `<tr>
        <td>${esc(r.label || '—')}${tag(r)}</td>
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

  function renderExpansion(doc) {
    const study = doc.expansion;
    if (!study || !study.counts) return '';
    const c = study.counts;
    const rows = [
      ['Catalogued events and candidates', c.discovered_events],
      ['Actions matched to primary schedules or structured records', c.verified_actions],
      ['Verified actions with next-session entry and five-session exit prices', c.complete_verified_price_paths],
      ['Processed filing disclosures', c.processed_disclosures],
      ['Prepared announcement disclosures', c.prepared_disclosures],
      ['Prepared disclosures with historical fundamental score ≥60', c.prepared_fundamental_60],
      ['Prepared next-session events', c.prepared_post_split_events],
      ['Next-session events with historical fundamental score ≥60', c.post_split_fundamental_60],
      ['Prepared disclosures below $1', c.sub_dollar_prepared],
    ].map(([name,n]) => `<tr><td>${esc(name)}</td><td class="mono">${fmtInt(n)}</td></tr>`).join('');
    const percent = n => isNum(n) ? `${(Number(n)*100).toFixed(1)}%` : '—';
    const cohortName = key => {
      const h = String(key).match(/_h(\d+)$/);
      const first = key.startsWith('ex_close') ? 'Split-day close (overnight)' : key.includes('_close_') ? 'Next-session close (overnight)' : key.startsWith('ex_plus_0') ? 'Split-day open' : key.startsWith('ex_plus_1') ? 'Next-session open' : 'Five sessions later';
      return `${first} · ${h ? h[1] : '—'} sessions`;
    };
    const caseName = c => `${c.stage === 'post_split_1' ? 'Next session' : c.stage === 'authorization_or_proposal' ? 'Proposal / authorization' : c.stage === 'unscheduled_board_action' ? 'Board action' : 'Scheduled split'} · ${c.selector === 'fundamental_60' ? 'score ≥60' : 'all eligible'} · ${c.horizon_sessions} sessions · ${c.rate_basis || `${Math.round(c.fee_annual*100)}% annual fee`}${c.borrow_policy === 'strict' ? ' · dated execution evidence' : c.execution === 'economic' ? ' · cost-budget check' : ''}`;
    const capitalRisk=((doc.execution_research || {}).capital_risk || {}), legacyCapital=Object.fromEntries((capitalRisk.legacy_accounts || []).map(r=>[r.case_id,r])), priceMargin=Object.fromEntries((capitalRisk.expanded_price_cohorts || []).map(r=>[r.cohort,r.margin_returns]));
    const price = (study.event_study || []).filter(r => r.tier === 'verified_actions').map(r => `<tr>
      <td>${esc(cohortName(r.cohort))}</td><td class="mono">${fmtInt(r.events)}</td><td class="mono">${fmtInt(r.issuers)}</td>
      <td class="mono">${esc(percent(r.mean_gross_short_return))}</td><td class="mono">${esc(percent(priceMargin[r.cohort] && priceMargin[r.cohort].mean))}<br><small>${fmtInt(priceMargin[r.cohort] && priceMargin[r.cohort].n)} priced entries</small></td><td class="mono">${esc(percent(r.median_gross_short_return))}</td>
      <td class="mono">${esc(percent(r.positive_share))}</td><td class="mono">${esc(percent(r.issuer_interval && r.issuer_interval.low))} to ${esc(percent(r.issuer_interval && r.issuer_interval.high))}</td></tr>`).join('');
    const accounts = (study.accounts || []).map(r => `<tr><td>${esc(caseName(r.case))}</td><td class="mono">${fmtInt(r.eligible_episodes)}</td>
      <td class="mono">${fmtInt(r.metrics.taken)}</td><td class="mono">${fmtInt(r.metrics.unique_issuers)}</td>
      <td class="mono">${r.status === 'evidence_unavailable' ? '—' : esc(fmtMoney(r.metrics.net))}</td><td>${esc(percent(legacyCapital[r.case.id] && legacyCapital[r.case.id].net_return_on_gross))}</td><td>${esc(percent(legacyCapital[r.case.id] && legacyCapital[r.case.id].net_return_on_margin))}</td><td class="mono">${fmtInt(r.metrics.unresolved)}</td><td>${esc(r.status)}</td></tr>`).join('');
    const gaps = Object.entries(study.announcement_exclusions || {}).sort((a,b) => b[1]-a[1]).slice(0,12)
      .map(([name,n]) => `<li>${esc(name.replaceAll('_',' '))}: ${fmtInt(n)}</li>`).join('');
    return `<section><h3>Expanded reverse-split study</h3>
      <p class="subhead">${esc(study.start)} through ${esc(study.cutoff)} · ${fmtInt(c.unique_issuer_keys)} issuer or unresolved security keys.
      ${study.full_universe_complete ? 'Coverage reconciled for the declared universe.' : 'Coverage remains partial; unresolved identities and missing histories remain in the catalogue.'}</p>
      <table class="insights-table"><thead><tr><th>Coverage</th><th>Count</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="muted">Event counts, filing disclosures and portfolio trades have different denominators. Repeated entry settings do not create additional independent events.</p>
      ${renderOneDay(doc)}
      ${renderUniverse(doc.expansion_catalogue || [])}
      <details open><summary>Observed prices around verified actions</summary>
      <div style="overflow:auto"><table class="insights-table"><thead><tr><th>Entry / hold cohort</th><th>Events</th><th>Issuer keys</th><th>Mean / gross</th><th>Mean / margin</th><th>Median / gross</th><th>Positive paths</th><th>Issuer 95% interval / gross</th></tr></thead><tbody>${price || '<tr><td colspan="8">Complete verified price paths unavailable.</td></tr>'}</tbody></table></div>
      <p class="muted">Gross price behavior before fills, borrow, commissions and margin. Missing exits are unavailable, never zero returns.</p></details>
      <details><summary>Declared announcement and next-session account scenarios</summary>
      <table class="insights-table"><thead><tr><th>Declared scenario</th><th>Eligible episodes</th><th>Trades</th><th>Issuers</th><th>Marked net P&amp;L</th><th>Net / gross</th><th>Net / margin</th><th>Unresolved positions</th><th>Status</th></tr></thead><tbody>${accounts}</tbody></table>
      <p class="muted">Conditional models on one hypothetical $50k account. Unresolved liabilities prevent a realized-profit claim. Strict cases require dated evidence; public availability indications are not approved locates.</p></details>
      <details><summary>Missing evidence and exclusions</summary><ul class="rs-limits">${gaps}</ul>
      <p class="muted">${fmtInt(study.collection && study.collection.pending_accessions)} discovered filing accessions await full-text processing. Earlier unpriced history is an inventory, not a trade sample.</p>
      <ul class="rs-limits">${(study.limits || []).map(l => `<li>${esc(l)}</li>`).join('')}</ul></details>
      <p class="muted">Run ${esc(study.run_id)} · built ${esc(String(study.built_at || '').slice(0,19))} UTC · forward validation starts ${esc(study.forward_validation_starts || '—')}.</p></section>`;
  }

  function renderExecutionResearch(doc) {
    const e=doc.execution_research;
    if (!e) return '';
    const pct=n=>isNum(n) ? `${(Number(n)*100).toFixed(2)}%` : '—';
    const money=n=>isNum(n) ? esc(fmtMoney(n)) : '—';
    const capitalCell=c=>c ? `${money(c.dollars)}<br><small>${esc(pct(c.on_gross))} gross · ${esc(pct(c.on_margin))} margin</small>` : '—';
    const names={primary:'All observed split events',eligible:'Known before entry; SSR not observed',fundamental:'Fixed fundamental score ≥60',account:'Original account positions'};
    const quoteRows=(e.populations || []).filter(r=>r.schema==='bbo-1s').map(r=>`<tr><td>${esc(names[r.cohort] || r.cohort)}</td><td>${fmtInt(r.entry_seconds_after_open)} sec</td><td>${fmtInt(r.paired_quotes)} / ${fmtInt(r.target_events)}</td><td>${esc(pct(r.round_trip_half_spreads && r.round_trip_half_spreads.median))}</td><td>${esc(pct(r.round_trip_half_spreads && r.round_trip_half_spreads.mean))}</td><td>${esc(pct(r.round_trip_half_spreads_on_margin && r.round_trip_half_spreads_on_margin.mean))}</td><td>${esc(pct(r.round_trip_half_spreads && r.round_trip_half_spreads.p90))}</td></tr>`).join('');
    const cases=(e.fixed_position_scenarios || []).map(r=>{
      const t=r.totals || {};
      const c=r.capital || {}, k=c.components || {}, combined={dollars:(t.borrow || 0)+(t.commission || 0),on_gross:c.gross_entry_exposure ? ((t.borrow || 0)+(t.commission || 0))/c.gross_entry_exposure : null,on_margin:c.summed_entry_margin ? ((t.borrow || 0)+(t.commission || 0))/c.summed_entry_margin : null};
      return `<tr><td>${r.execution_mode==='routed-mbp-10' ? 'Listing + Arca + EDGX' : 'Listing venue'}</td><td>${fmtInt(r.entry_seconds_after_open)} sec</td><td>${fmtInt(r.additional_bps_per_side)} bp</td><td>${fmtInt(r.both_sides_fit)} / ${fmtInt(r.target_positions)}</td><td>${money(c.gross_entry_exposure)}<br><small>Margin ${money(c.summed_entry_margin)}</small></td><td>${capitalCell(k.raw_auction_pnl)}</td><td>${capitalCell(k.quoted_half_spread_cost)}</td><td>${capitalCell(k.displayed_depth_cost)}</td><td>${capitalCell(k.timing_difference)}</td><td>${capitalCell(k.additional_slippage)}</td><td>${capitalCell(combined)}</td><td>${capitalCell(k.net)}</td></tr>`;
    }).join('');
    const capacity=(e.populations || []).filter(r=>r.schema==='mbp-10').flatMap(r=>(r.capacity || []).map(c=>`<tr><td>${fmtInt(r.entry_seconds_after_open)} sec</td><td>${money(c.notional_usd)}</td><td>${fmtInt(c.both_sides_fit)} / ${fmtInt(r.paired_quotes)}</td><td>${fmtInt(c.insufficient_entry_depth)}</td><td>${fmtInt(c.insufficient_exit_depth)}</td></tr>`)).join('');
    const bps=n=>isNum(n) ? `${(Number(n)*10000).toFixed(1)} bp` : '—';
    const latency=(e.latency_quote_changes || []).map(r=>`<tr><td>${r.execution_mode==='routed-mbp-10' ? 'Listing + Arca + EDGX' : 'Listing venue'}</td><td>${fmtInt(r.entry_seconds_after_open)} sec</td><td>${fmtInt(r.delay_milliseconds)} ms</td><td>${fmtInt(r.pairs)}</td><td>${esc(bps(r.additional_round_trip_cost.mean))}</td><td>${esc(bps(r.additional_round_trip_cost_on_margin && r.additional_round_trip_cost_on_margin.mean))}</td><td>${esc(bps(r.additional_round_trip_cost.median))}</td><td>${esc(bps(r.additional_round_trip_cost.p90))}</td></tr>`).join('');
    return `<section style="border:1px solid currentColor;padding:12px;margin:16px 0"><h3>Earlier quote study · listing venue and initial three-venue comparison</h3>
      <p><strong>The previous daily-range spread estimate is uncalibrated.</strong> The measurements below use Databento’s historical bid, ask and displayed order-book depth. Short at the quoted bid; cover at the quoted ask.</p>
      <p>Entry is measured 1 or 30 seconds after the scheduled open. Cover is measured one second before the scheduled close, including early closes. These are continuous-trading scenarios. Auction participation requires its own fill evidence.</p>
      <div style="overflow:auto"><table class="insights-table"><thead><tr><th>Quote sample</th><th>Entry after open</th><th>Paired quotes / targets</th><th>Median cost / gross</th><th>Mean cost / gross</th><th>Mean cost / margin</th><th>90th percentile / gross</th></tr></thead><tbody>${quoteRows}</tbody></table></div>
      <p class="muted">Round-trip spread cost = half the observed entry spread plus half the observed exit spread, divided by the entry midpoint. This excludes depth, timing changes, borrowing, commissions and additional latency/impact. Quotes are from the historical listing venue; a smart router may find better prices elsewhere. Missing pairs remain disclosed.</p>
      <details open><summary>Original position sizes: dollars, return on gross and return on margin</summary><div style="overflow:auto"><table class="insights-table"><thead><tr><th>Venues</th><th>Entry after open</th><th>Extra cost per side</th><th>Both books fit / positions</th><th>Summed entry gross / margin</th><th>Gross price P&amp;L</th><th>Quoted spread</th><th>Beyond best price</th><th>Timing difference</th><th>Extra cost</th><th>Borrow + commission</th><th>Conditional net</th></tr></thead><tbody>${cases}</tbody></table></div>
      <p>The original ${fmtInt(e.sample && e.sample.account_positions)} entries and share sizes are held fixed, with full same-session covers where the displayed books fit. The previous volume-cap model delayed part of six covers until the following day, so its exit paths differ. A static sweep through up to ten displayed price levels per venue estimates cost beyond the best quote. The additional-venue sensitivity combines available books among the listing venue, NYSE Arca and Cboe EDGX, falling back to a single valid venue when needed; this is a subset of venues, not full NBBO.</p>
      <p>Timing difference measures price movement between the official auctions and the chosen trade times; it can help or hurt. The extra 5, 10 or 25 basis points per side are explicit assumptions about remaining latency and impact.</p>
      <p><strong>These are results for positions with both books available, sufficient depth and affirmative cached trading status.</strong> The entry must also be unrestricted under SSR. Missing or insufficient exit books prevent a complete-account profit claim. Retrospective complete-pair selection, unchanged historical position selection and assumed borrowing remain limitations. Displayed liquidity does not guarantee a broker fill.</p></details>
      <details open><summary>Measured quote changes during execution delays</summary><table class="insights-table"><thead><tr><th>Venues</th><th>Entry after open</th><th>Delay on each leg</th><th>Pairs</th><th>Mean cost / gross</th><th>Mean cost / margin</th><th>Median / gross</th><th>90th percentile / gross</th></tr></thead><tbody>${latency}</tbody></table><p class="muted">Compare the size-adjusted displayed execution price at the decision time with the quote 10, 100 or 500 milliseconds later on both legs. Positive values mean worse execution; negative values mean improvement. These are observed market movements without our orders. They do not measure our causal market impact, the broker’s actual delay, or guarantee a delayed fill. One basis point is 0.01%.</p></details>
      ${renderCapitalTail(doc)}
      <details><summary>How position size affects available liquidity</summary><table class="insights-table"><thead><tr><th>Entry after open</th><th>Target notional</th><th>Both sides fit / paired books</th><th>Entry too large</th><th>Exit too large</th></tr></thead><tbody>${capacity}</tbody></table><p class="muted">Historical displayed depth on one venue at the sampled times. A larger order can consume several price levels. Exit depth is a retrospective diagnostic and cannot be used to select trades in advance.</p></details>
      <p class="muted">${fmtInt(e.collection && e.collection.requests)} requested windows · ${(Number(e.collection && e.collection.quoted_usd) || 0).toFixed(4)} USD quoted data cost · source study ${esc(e.source_run_id)}.</p>
    </section>`;
  }

  function renderCapitalTail(doc) {
    const e=doc.execution_research, risk=e && e.capital_risk;
    if (!risk) return '';
    const pct=n=>isNum(n) ? `${(Number(n)*100).toFixed(2)}%` : '—', cash=n=>isNum(n) ? esc(fmtMoney(n)) : '—';
    const selected=(e.fixed_position_scenarios || []).filter(r=>r.additional_bps_per_side===0);
    const averages=selected.map(r=>{const c=r.capital || {}, ci=(r.tail || {}).mean_return_interval || {};return `<tr><td>${r.execution_mode==='routed-mbp-10' ? 'Listing + Arca + EDGX' : 'Listing venue'} · ${fmtInt(r.entry_seconds_after_open)} sec</td><td>${esc(pct(c.net_return_on_gross))}</td><td>${esc(pct(c.net_return_on_margin))}</td><td>${esc(pct(c.equal_weighted_net_return_on_gross))}</td><td>${esc(pct(ci.low))} to ${esc(pct(ci.high))}</td><td>${esc(pct(c.net_return_on_50k_equity))}</td></tr>`;}).join('');
    const tails=selected.map(r=>{
      const t=r.tail || {}, g=t.gross || {}, m=t.margin || {}, path=t.intraday || {};
      return `<tr><td>${r.execution_mode==='routed-mbp-10' ? 'Listing + Arca + EDGX' : 'Listing venue'} · ${fmtInt(r.entry_seconds_after_open)} sec</td><td>${fmtInt(r.both_sides_fit)}</td><td>${esc(pct(g.worst_return))}<br><small>${esc(pct(m.worst_return))} margin</small></td><td>${esc(pct(g.loss_var_95))}<br><small>${esc(pct(m.loss_var_95))} margin</small></td><td>${esc(pct(g.loss_es_95))}<br><small>${esc(pct(m.loss_es_95))} margin · ${fmtInt(g.tail_observations_95)} observations</small></td><td>${fmtInt(path.paths)} paths<br>${esc(pct(path.worst_adverse_price_bound))} price rise<br><small>${esc(pct(path.worst_loss_on_margin_bound))} loss / margin</small></td><td>${esc(pct(t.close_of_day_drawdown_on_50k))}</td></tr>`;
    }).join('');
    const margins=selected.flatMap(r=>(r.margin_sensitivities || []).map(s=>`<tr><td>${r.execution_mode==='routed-mbp-10' ? 'Listing + Arca + EDGX' : 'Listing venue'} · ${fmtInt(r.entry_seconds_after_open)} sec</td><td>${esc(pct(s.house_fraction))}</td><td>${cash(s.summed_margin)}</td><td>${esc(pct(r.capital && r.capital.net_return_on_gross))}</td><td>${esc(pct(s.net_return_on_margin))}</td><td>${cash(s.maximum_same_day_entry_margin)}</td></tr>`)).join('');
    const shocks=(risk.squeeze_stresses || []).map(s=>`<tr><td>${s.basket==='largest_observed_position' ? 'Largest position' : 'Three largest together · hypothetical'}</td><td>+${esc(pct(s.price_rise))}</td><td>${esc(pct(s.house_fraction_after_squeeze))}</td><td>${fmtInt(s.calendar_borrow_days)} days · ${fmtInt(s.fee_multiple)}× fee · ${esc(pct(s.cover_cost_fraction))} cover cost</td><td>${cash(s.pnl)}</td><td>${esc(pct(s.return_on_gross))}</td><td>${esc(pct(s.return_on_margin))}</td><td>${cash(s.stressed_margin_requirement)}</td><td>${cash(s.loss_plus_margin_budget)}</td><td>${esc(pct(s.loss_on_50k_equity))}</td></tr>`).join('');
    const broad=(risk.price_cohorts || []).filter(r=>r.house_fraction===1 && ['primary','eligible','fundamental','current_cap50'].includes(r.cohort)).map(r=>`<tr><td>${esc(({primary:'All observed actions',eligible:'Known before entry; opening SSR not observed',fundamental:'Fixed fundamental score ≥60',current_cap50:'Current rate ≤50% · retrospective'})[r.cohort])}</td><td>${fmtInt(r.gross_returns.n)}</td><td>${esc(pct(r.gross_returns.mean))}</td><td>${esc(pct(r.margin_returns.mean))}</td><td>${esc(pct(r.gross_tail.worst_return))}</td><td>${esc(pct(r.gross_tail.loss_es_95))}</td><td>${esc(pct(r.gross_tail.loss_es_99))}</td></tr>`).join('');
    return `<section><h3>Capital required and tail risk</h3><p><strong>Return on gross = P&amp;L ÷ short exposure. Return on margin = P&amp;L ÷ modeled required equity.</strong> Short-sale proceeds stay encumbered. The main view uses a 100% house requirement plus the per-share floors; a $2 stock can require $2.50 per share, so return on margin can be lower than return on gross.</p>
      <p class="muted">${esc(risk.definitions.aggregation)} Cost cells above show dollars and the fraction of each capital denominator consumed. Margin is modeled; dated broker requirements are unavailable. <a href="https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210" target="_blank" rel="noopener">FINRA margin floors</a>.</p>
      <details open><summary>Capital-weighted totals and equal-weighted trades</summary><table class="insights-table"><thead><tr><th>Scenario · zero extra cost</th><th>Net / summed gross</th><th>Net / summed margin</th><th>Mean net trade / gross</th><th>Issuer 95% interval for mean trade</th><th>Net / $50k starting equity</th></tr></thead><tbody>${averages}</tbody></table><p class="muted">Original share sizes give trades different weights. Positive total P&amp;L can coexist with a negative equal-weighted mean. These historical returns are not annualized or a forecast. Peak simultaneous entry capital is listed below; it excludes the additional liquidity and squeeze reserves.</p></details>
      <details open><summary>What the historical losses show</summary><div style="overflow:auto"><table class="insights-table"><thead><tr><th>Execution scenario · zero extra cost</th><th>Positions</th><th>Worst net trade / gross</th><th>95% loss percentile / gross</th><th>Average worst 5% / gross</th><th>Worst intraday bound</th><th>Closing drawdown / $50k</th></tr></thead><tbody>${tails}</tbody></table></div><p class="muted">Loss percentiles are empirical sample statistics. The execution sample has fewer than 100 observations, so 99% loss estimates are withheld. Each 95% tail is only about two trades. Intraday values use regular-session minute highs and include ambiguous boundary minutes; interior-minute values are retained in the data. They are marks, not cover fills or guaranteed stop losses.</p></details>
      <details><summary>Broad price sample: gross and margin returns before costs</summary><table class="insights-table"><thead><tr><th>Cohort</th><th>Events</th><th>Mean / gross</th><th>Mean / margin</th><th>Worst / gross</th><th>Average worst 5% / gross</th><th>Average worst 1% / gross</th></tr></thead><tbody>${broad}</tbody></table><p class="muted">Equal event weights. These are descriptive auction-price results before execution costs, borrowing and approved locates. Repeated issuers and missing histories limit the loss-tail estimates.</p></details>
      <details open><summary>Margin sensitivity: 50%, 100% and 200%</summary><table class="insights-table"><thead><tr><th>Scenario</th><th>House assumption</th><th>Summed entry margin</th><th>Net / gross</th><th>Net / margin</th><th>Peak simultaneous entry margin</th></tr></thead><tbody>${margins}</tbody></table><p class="muted">All sensitivities retain the per-share and initial-margin floors. A 50% house assumption does not automatically double returns for these low-priced stocks. P&amp;L is held fixed; admissions and quantities are not resized.</p></details>
      <details open><summary>Squeeze, fee increase and delayed-exit stresses</summary><div style="overflow:auto"><table class="insights-table"><thead><tr><th>Basket</th><th>Price rise</th><th>Stressed house margin</th><th>Exit / fee assumptions</th><th>P&amp;L</th><th>Return / gross</th><th>Return / original margin</th><th>Stressed margin</th><th>Loss + margin reserve</th><th>Loss / $50k equity</th></tr></thead><tbody>${shocks}</tbody></table></div><p><strong>A one-day target does not cap the loss if the stock cannot be covered. Short losses have no finite upper bound.</strong> Stress probabilities are not assigned. The largest +500% example is not a maximum possible loss. The three-position basket is a hypothetical correlated squeeze.</p><p class="muted">${esc(risk.definitions.tail)} ${esc(risk.limits[3])} Intraday collection: ${fmtInt(risk.intraday_collection.observed_paths)} observed paths; ${(Number(risk.intraday_collection.quoted_usd)||0).toFixed(4)} USD quoted.</p></details></section>`;
  }

  function renderOneDay(doc) {
    const study=doc.expansion, day=study.one_day;
    if (!day) return '';
    const p=day.primary || {}, pct=n=>isNum(n) ? `${Number(n)>=0 ? '+' : ''}${(Number(n)*100).toFixed(2)}%` : '—';
    const interval=s=>s && isNum(s.low) && isNum(s.high) ? `${pct(s.low)} to ${pct(s.high)}` : 'Unavailable';
    const risk=((doc.execution_research || {}).capital_risk || {}), marginCohorts=Object.fromEntries((risk.price_cohorts || []).filter(r=>r.house_fraction===1).map(r=>[r.cohort,r])), legacyCapital=Object.fromEntries((risk.legacy_accounts || []).map(r=>[r.case_id,r])), expandedMargin=Object.fromEntries((risk.expanded_price_cohorts || []).map(r=>[r.cohort,r.margin_returns]));
    const rows=[['All verified actions with both benchmarks',p,'primary'],['Known before entry; SSR not observed',day.available_before_entry_and_SSR_not_observed,'eligible'],['Same eligibility + fixed fundamental score ≥60',day.fundamental_60_fixed,'fundamental'],['Prior uncalibrated cost / capacity stress screen',day.cost_capacity_subset,'cost_capacity'],['Current available rate ≤50% · retrospective illustration',study.current_borrow_sensitivities && study.current_borrow_sensitivities.current_cap50_gross,'current_cap50']]
      .map(([name,s,key])=>`<tr><td>${esc(name)}</td><td class="mono">${fmtInt(s && s.events)}</td><td class="mono">${fmtInt(s && s.issuers)}</td><td class="mono">${esc(pct(s && s.mean))}</td><td>${esc(pct(marginCohorts[key] && marginCohorts[key].margin_returns.mean))}</td><td class="mono">${esc(pct(s && s.median))}</td><td class="mono">${esc(pct(s && s.positive_share))}</td><td class="mono">${esc(interval(s && s.issuer_interval))}</td></tr>`).join('');
    const yearlyMargin=Object.fromEntries(((marginCohorts.primary || {}).by_year || []).map(r=>[r.year,r.margin_returns]));
    const annual=(day.by_year || []).map(s=>`<tr><td>${esc(s.year)}</td><td>${fmtInt(s.events)}</td><td>${esc(pct(s.mean))}</td><td>${esc(pct(yearlyMargin[s.year] && yearlyMargin[s.year].mean))}</td><td>${esc(pct(s.positive_share))}</td></tr>`).join('');
    const accounts=(study.accounts || []).filter(r=>r.case.stage==='post_split_1' && r.case.horizon_sessions===1).map(r=>{
      const m=r.metrics,k=m.costs || {}, cost=(k.spread_cost || 0)+(k.slippage_cost || 0)+(k.borrow || 0)+(k.commission || 0);
      const prefix=r.case.selector==='fundamental_60' ? 'Score ≥60' : 'All eligible';
      const name=r.case.borrow_policy==='strict' ? 'Dated execution evidence required · 50% rate cap' : r.case.current_rate_cap!=null ? `${prefix} · current per-name rate ≤50% · 1% cost limit · illustration` : r.case.rate_basis ? `${prefix} · ${r.case.rate_basis}` : r.case.execution==='one_day_budget' ? 'Score ≥60 · conservative sizing · 1% cost limit' : `${prefix} · ${Math.round(r.case.fee_annual*100)}% annual borrowing assumption`;
      const c=legacyCapital[r.case.id] || {};
      return `<tr><td>${esc(name)}</td><td>${fmtInt(m.taken)}</td><td>${r.status==='evidence_unavailable' ? '—' : `${esc(fmtMoney(k.raw_price_pnl))}<br><small>${esc(pct(c.gross_price_return_on_gross))} gross · ${esc(pct(c.gross_price_return_on_margin))} margin</small>`}</td><td>${r.status==='evidence_unavailable' ? '—' : `${esc(fmtMoney(cost))}<br><small>${esc(pct(c.cost_return_on_gross))} gross · ${esc(pct(c.cost_return_on_margin))} margin</small>`}</td><td>${r.status==='evidence_unavailable' ? '—' : `${esc(fmtMoney(m.net))}<br><small>${esc(pct(c.net_return_on_gross))} gross · ${esc(pct(c.net_return_on_margin))} margin</small>`}</td><td>${fmtInt(m.unresolved)}</td><td>${esc(r.status.replaceAll('_',' '))}</td></tr>`;
    }).join('');
    const controls=study.matched_controls || {}, excess=controls.excess_gross || {};
    const audit=study.exit_reconciliation || {}, borrow=study.borrow_economics || {};
    const gaps=Object.entries(audit.by_category || {}).map(([reason,n])=>`<li>${esc(reason.replaceAll('_',' '))}: ${fmtInt(n)} paths</li>`).join('');
    const paths=(audit.paths || []).map(r=>`<tr><td class="mono">${esc(r.ticker)}<br><small>CIK ${esc(r.cik)}</small></td><td>${esc(r.entry_date)}</td><td>${esc(r.planned_exit || 'Pending')}</td><td>${esc(r.category.replaceAll('_',' '))}</td><td>${r.exit_price_observation ? 'Close observed' : 'Close unavailable'}</td><td>${(r.subsequent_verified_actions || []).map(a=>`${esc(a.date)} · ${esc(fmtRatio(a.ratio))}`).join('<br>') || 'None verified through cutoff'}</td><td><details><summary>${fmtInt(r.cases.length)} case quantities</summary>${r.cases.map(c=>`<p>${esc(c.case.replaceAll('_',' '))}<br>Earlier residual ${esc(c.old_remaining_shares)} → revised ${esc(c.new_remaining_shares == null ? 'Not taken' : Number(c.new_remaining_shares).toPrecision(5))}; share factor ${esc(c.new_share_factor)}; modeled last cover ${esc(c.new_cover_date || 'Unavailable')}. ${esc(c.status && c.status.replaceAll('_',' '))}</p>`).join('')}</details></td><td>${(r.evidence || []).map(e=>link(e.source_url,'Primary filing')).join(' · ') || 'Further evidence needed'}</td></tr>`).join('');
    const current=study.current_borrow_sensitivities || {}, rateRows=(current.populations || []).map(r=>`<tr><td>${esc(r.population.replaceAll('_',' '))}</td><td>${fmtInt(r.quoted_available_names)} / ${fmtInt(r.target_names)}</td><td>${esc(pct(r.median_annual_fraction))}</td><td>${esc(pct(r.mean_annual_fraction))}</td><td>${esc(pct(r.p90_annual_fraction))}</td><td>${fmtInt(r.missing_names)}</td></tr>`).join('');
    const overnight=(study.event_study || []).filter(r=>r.tier==='verified_actions' && ['ex_close_h1','ex_plus_1_close_h1'].includes(r.cohort)).map(r=>`<tr><td>${r.cohort==='ex_close_h1' ? 'Split-day close → next-session close' : 'Next-session close → following close'}</td><td>${fmtInt(r.events)}</td><td>${esc(pct(r.mean_gross_short_return))}</td><td>${esc(pct(expandedMargin[r.cohort] && expandedMargin[r.cohort].mean))}</td><td>${esc(pct(r.positive_share))}</td><td>${esc(interval(r.issuer_interval))}</td></tr>`).join('');
    const forward=doc.forward_status || {}, validation=forward.validation || study.forward_validation || {}, protocol=validation.protocol || {};
    const pending=(forward.registry || []).map(r=>{
      const review=r.source_review, indication=r.public_borrow_indication;
      const reviewed=review ? `<p class="muted">${esc(review.summary)}</p>` : '';
      const quoted=indication ? `<p class="muted">Current public indication: ${esc(pct(indication.fee_annual_fraction))} annual · ${fmtInt(indication.available_shares)} shares · ${esc(indication.as_of)}. Not an approved locate.</p>` : '';
      return `<tr><td>${link(r.source_url,r.ticker || `CIK ${r.cik}`)}</td><td>${esc(r.ex_date)}</td><td>${esc(r.next_session || 'Outside calendar')}</td><td>${esc(String(r.status || '').replaceAll('_',' '))}${reviewed}${quoted}</td></tr>`;
    }).join('');
    return `<div style="border-top:2px solid currentColor;padding-top:12px;margin:16px 0">
      <h3>One-day gross shorting · next session open → close</h3>
      <p style="font-size:26px;margin:8px 0"><strong>${esc(pct(p.mean))}</strong> <span style="font-size:14px">average gross return · ${fmtInt(p.events)} events · ${fmtInt(p.issuers)} issuers</span></p>
      <p>Average price return on modeled margin: <strong>${esc(pct(marginCohorts.primary && marginCohorts.primary.margin_returns.mean))}</strong> · 100% house assumption with per-share floors · before costs.</p>
      <p>${isNum(p.mean) && p.mean>0 ? 'The observed one-day gross price return is positive.' : 'The observed one-day gross price return is not positive.'} This is before trading costs and borrowing. It does not establish an executable net profit.</p>
      <p class="muted">Short at the official opening benchmark in the session after the split; cover at that session’s official closing benchmark. Gross return = 1 − closing price / opening price. Equal weight per event; one session includes both entry and exit. Overnight holds are separate cohorts below.</p>
      <p>Issuer 95% interval: <strong>${esc(interval(p.issuer_interval))}</strong>. Year 95% interval: ${esc(interval(p.year_interval))}. These intervals describe the observed sample; missing OTC histories and security selection still limit representativeness.</p>
      ${renderExecutionResearch(doc)}
      <div style="overflow:auto"><table class="insights-table"><thead><tr><th>One-day sample</th><th>Events</th><th>Issuers</th><th>Mean / gross</th><th>Mean / margin</th><th>Median / gross</th><th>Positive paths</th><th>Issuer 95% interval / gross</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="muted">The fundamental threshold stays at 60 with at least three observed signals and a latest period no older than 200 days. Observed SSR causes a skipped one-day entry; unknown status remains conditional. ${esc(day.cost_screen_basis)}</p>
      <details><summary>Zero to one overnight: compare the price patterns</summary><table class="insights-table"><thead><tr><th>One overnight</th><th>Events</th><th>Mean / gross</th><th>Mean / margin</th><th>Positive paths</th><th>Issuer 95% interval / gross</th></tr></thead><tbody>${overnight}</tbody></table><p class="muted">The headline holds zero overnights. Closing-to-closing results above hold one overnight. An overnight can accrue several calendar days of borrowing across weekends; the account scenarios also show next-session open through the following close.</p></details>
      <details><summary>Previous daily-range cost stress scenarios · uncalibrated</summary><div style="overflow:auto"><table class="insights-table"><thead><tr><th>Scenario</th><th>Trades</th><th>Gross price P&amp;L</th><th>Modeled costs</th><th>Net P&amp;L</th><th>Residuals</th><th>Status</th></tr></thead><tbody>${accounts}</tbody></table></div>
      <p class="muted">These previous scenarios assume spreads from daily high-low ranges plus additional slippage. Their net results are stress sensitivities; they are not measured execution estimates. Smaller sizing stress-tests a +200% price move, triple fees and a seven-day exit delay. Historical approved borrowing and actual fills are incomplete.</p></details>
      ${(study.accounts || []).some(r=>r.case.id==='post_split_fundamental_60_h1_one_day_budget' && r.metrics.taken===0) ? '<p><strong>The conservative 1% cost version admits no trades in this $50k model.</strong> The 0.5% loss budget under a +200% squeeze limits a position to roughly $125; a $2 round-trip minimum commission already exceeds 1%. Positive gross returns do not resolve this sizing constraint. The prior cost / capacity sample above uses a larger notional envelope and is a descriptive screen.</p>' : ''}
      <details><summary>Year by year: concentration and stability</summary><table class="insights-table"><thead><tr><th>Year</th><th>Events</th><th>Mean / gross</th><th>Mean / margin</th><th>Positive paths</th></tr></thead><tbody>${annual}</tbody></table></details>
      <details open><summary>Does the split add information beyond financial weakness?</summary><p>${fmtInt(excess.events)} matched split events · ${fmtInt(excess.issuers)} issuers. Average split-event gross: <strong>${esc(pct(controls.subject_gross && controls.subject_gross.mean))}</strong>; weak-company controls: <strong>${esc(pct(controls.control_gross && controls.control_gross.mean))}</strong>; excess: <strong>${esc(pct(excess.mean))}</strong> (${esc(interval(excess.issuer_interval))}).</p>
      <p>On modeled margin: split-event mean ${esc(pct(risk.matched_controls_on_margin && risk.matched_controls_on_margin.subject.mean))}; control mean ${esc(pct(risk.matched_controls_on_margin && risk.matched_controls_on_margin.control.mean))}; excess ${esc(pct(risk.matched_controls_on_margin && risk.matched_controls_on_margin.excess.mean))} (${esc(interval(risk.matched_controls_on_margin && risk.matched_controls_on_margin.excess_interval))}); ${fmtInt(risk.matched_controls_on_margin && risk.matched_controls_on_margin.events)} paired margin observations.</p>
      <p class="muted">${esc(controls.matching)} ${esc(controls.universe)} ${esc(controls.limitations)}</p></details>
      <details><summary>Exit reconciliation: ${fmtInt(audit.audited_paths)} earlier residual paths</summary><ul class="rs-limits">${gaps}</ul><div style="overflow:auto"><table class="insights-table"><thead><tr><th>Name / issuer</th><th>Entry</th><th>Planned exit</th><th>Finding</th><th>Planned exit data</th><th>Known share adjustments through cutoff</th><th>Quantity / cover audit</th><th>Evidence</th></tr></thead><tbody>${paths}</tbody></table></div>
      <p class="muted">${esc(audit.policy)} Baseline run ${esc(audit.baseline_run_id)}. ACON’s April 8 detection was rejected using its quarterly filing and venue evidence; DBGI’s OTC transition leaves missing prices visible.</p></details>
      <details open><summary>Current IBKR rates and borrowing sensitivity</summary><p>Public inventory timestamp: ${esc(current.as_of || 'Unavailable')}. ${fmtInt(borrow.dated_fee_records)} historical fee records · ${fmtInt(borrow.approved_locates)} approved locates · ${fmtInt(borrow.loan_event_records)} loan events.</p><table class="insights-table"><thead><tr><th>Current population</th><th>Available quotes / names</th><th>Median annual rate</th><th>Mean annual rate</th><th>90th percentile</th><th>Missing</th></tr></thead><tbody>${rateRows}</tbody></table><p>${esc(current.assumption)}</p><p class="muted">${esc(borrow.basis)} The public inventory archive records quantity and indicative fee vintages. It is not approval to short. <a href="https://www.interactivebrokers.com/en/pricing/short-sale-cost.php" target="_blank" rel="noopener">IBKR short-sale cost conventions</a>.</p></details>
      <details open><summary>Frozen validation · ${esc(protocol.version)} · starts ${esc(protocol.validation_starts)}</summary><p><strong>${fmtInt(validation.completed && validation.completed.events)} completed new-cohort results</strong>. ${fmtInt((forward.registry || []).length)} provisional scheduled-disclosure candidates enrolled for review; these are not verified trades.</p>
      <p>${esc(protocol.entry)} ${esc(protocol.exit)}</p><p>Annual borrowing cap ${esc(pct(protocol.maximum_borrow_annual_fraction))}; total expected cost limit ${esc(pct(protocol.maximum_expected_cost_fraction))} of notional; prior ADV participation ${esc(pct(protocol.maximum_prior_ADV_participation))}; position cap ${esc(pct(protocol.maximum_position_fraction))}; ${fmtInt(protocol.maximum_names)} simultaneous names. ${esc(protocol.approval)}</p>
      <p class="muted">${esc(protocol.review)} ${esc(forward.limits || '')}</p><details><summary>Enrolled disclosures awaiting evidence</summary><div style="overflow:auto"><table class="insights-table"><thead><tr><th>Name</th><th>Disclosed date</th><th>Next session</th><th>Evidence status</th></tr></thead><tbody>${pending || '<tr><td colspan="4">No candidates enrolled yet.</td></tr>'}</tbody></table></div></details></details>
    </div>`;
  }

  function universeRows(rows) {
    return rows.map(r => `<tr><td class="mono">${link(r.action_review && r.action_review.source_url || r.source_url,r.ticker)}${r.new_ticker && r.new_ticker !== r.ticker ? ` → ${esc(r.new_ticker)}` : ''}</td>
      <td>${esc(r.company || '—')}</td><td class="mono">${esc(r.ex_date)}</td><td>${esc(fmtRatio(r.ratio))}</td>
      <td>${esc(r.exchange_class)}</td><td>${esc(r.action_review && r.action_review.decision==='not_corporate_action' ? 'Rejected price-jump candidate' : String(r.verification || '').replaceAll('_',' '))}</td>
      <td>${esc(String(r.price_path || '').replaceAll('_',' '))}</td></tr>`).join('') || '<tr><td colspan="7">No names match these filters.</td></tr>';
  }
  function renderUniverse(rows) {
    return `<details data-rs-universe><summary>Browse the expanded universe (${fmtInt(rows.length)} events and candidates)</summary>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0"><input type="search" data-rs-query aria-label="Search reverse-split names" placeholder="Search ticker, company or CIK">
      <select data-rs-market aria-label="Filter market"><option value="">All markets</option><option value="listed">Listed</option><option value="otc">OTC</option><option value="unknown">Unclassified</option></select>
      <select data-rs-evidence aria-label="Filter evidence"><option value="">All evidence</option><option value="verified">Action corroborated</option><option value="review">Needs action review</option><option value="rejected">Rejected detection</option><option value="priced">Complete five-session price path</option><option value="missing">Missing five-session price path</option></select></div>
      <p data-rs-result-count class="muted">Showing ${Math.min(75,rows.length)} of ${fmtInt(rows.length)} events</p>
      <div style="overflow:auto"><table class="insights-table"><thead><tr><th>Ticker</th><th>Company</th><th>Action date</th><th>Ratio</th><th>Market</th><th>Action evidence</th><th>Next-session / five-session prices</th></tr></thead><tbody data-rs-rows>${universeRows(rows.slice(0,75))}</tbody></table></div>
      <button type="button" data-rs-previous disabled>Previous</button> <button type="button" data-rs-next ${rows.length <= 75 ? 'disabled' : ''}>Next</button>
      <p class="muted">Each row is an action or candidate, not necessarily an independent company or a feasible short.</p></details>`;
  }
  function attach(container,doc) {
    const panel=container.querySelector('[data-rs-universe]');
    if (!panel) return;
    const rows=doc.expansion_catalogue || [];
    let page=0;
    const input=panel.querySelector('[data-rs-query]'), market=panel.querySelector('[data-rs-market]'), evidence=panel.querySelector('[data-rs-evidence]');
    const previous=panel.querySelector('[data-rs-previous]'), next=panel.querySelector('[data-rs-next]');
    function update(reset) {
      if (reset) page=0;
      const q=input.value.trim().toLowerCase();
      const filtered=rows.filter(r => {
        const verified=['primary_schedule_matched','structured_corporate_action'].includes(r.verification);
        const priced=r.price_path==='observed_price_path';
        const rejected=r.action_review && r.action_review.decision==='not_corporate_action';
        return (!q || [r.ticker,r.new_ticker,r.company,r.cik].some(v => String(v || '').toLowerCase().includes(q))) &&
          (!market.value || r.exchange_class===market.value) &&
          (!evidence.value || (evidence.value==='verified' && verified) || (evidence.value==='review' && !verified && !rejected) || (evidence.value==='rejected' && rejected) ||
           (evidence.value==='priced' && priced) || (evidence.value==='missing' && !priced));
      });
      page=Math.max(0,Math.min(page,Math.ceil(filtered.length/75)-1));
      panel.querySelector('[data-rs-rows]').innerHTML=universeRows(filtered.slice(page*75,(page+1)*75));
      panel.querySelector('[data-rs-result-count]').textContent=`Showing ${filtered.length ? page*75+1 : 0}–${Math.min((page+1)*75,filtered.length)} of ${filtered.length.toLocaleString('en-US')} events`;
      previous.disabled=page===0; next.disabled=(page+1)*75>=filtered.length;
    }
    input.addEventListener('input',()=>update(true));market.addEventListener('change',()=>update(true));evidence.addEventListener('change',()=>update(true));
    previous.addEventListener('click',()=>{page--;update(false);});next.addEventListener('click',()=>{page++;update(false);});
    update(true);
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
   * caps the visible recent-announcement rows (the rest fold into a details);
   * `opts.hideTitle` omits the panel's own "Reverse splits" h2 for a host
   * section that already titles it. Returns HTML; the caller mounts it.
   */
  function renderForwardSummary(doc) {
    const forward=doc.forward_status || {}, validation=forward.validation || {}, protocol=validation.protocol || {};
    const rows=(forward.registry || []).map(r=>`<tr><th scope="row">${link(r.source_url,r.ticker || `CIK ${r.cik}`)}</th><td>${esc(r.ex_date)}</td><td>${esc(r.next_session || 'Requires calendar review')}</td><td>${esc(String(r.status || '').replaceAll('_',' '))}${r.source_review ? `<p class="muted">${esc(r.source_review.summary)}</p>` : ''}${r.public_borrow_indication ? `<p class="muted">Current public indication: ${fmtNum(100*r.public_borrow_indication.fee_annual_fraction)}% annual · ${fmtInt(r.public_borrow_indication.available_shares)} shares · ${esc(r.public_borrow_indication.as_of)}. Not an approved locate.</p>` : ''}</td></tr>`).join('');
    return `<p>Frozen rules start ${esc(protocol.validation_starts || '—')}. ${fmtInt((forward.registry || []).length)} provisional disclosure records remain subject to review; enrollment is not a trade.</p><p>${esc(protocol.entry || '')} ${esc(protocol.exit || '')}</p><p class="muted">${esc(protocol.approval || '')} ${esc(protocol.review || '')}</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th scope="col">Name</th><th scope="col">Disclosed date</th><th scope="col">Next session</th><th scope="col">Evidence status</th></tr></thead><tbody>${rows || '<tr><td colspan="4">No provisional disclosures enrolled.</td></tr>'}</tbody></table></div>`;
  }

  function render(doc, options) {
    const opts = options || {};
    if (!doc || typeof doc !== 'object') {
      return `${STYLE}<div class="rs-panel"><p class="muted">Reverse-split feed not loaded.</p></div>`;
    }
    if (doc.schema_version && doc.schema_version !== 'reverse_splits.v1') {
      return `${STYLE}<div class="rs-panel"><p class="muted">Unexpected reverse-split schema ${esc(doc.schema_version)}; expected reverse_splits.v1.</p></div>`;
    }
    if(doc.portfolio_research && global.ReverseSplitsPortfolioViz){
      const completed=doc.forward_status?.validation?.completed?.events;
      return `${STYLE}<div class="rs-panel" data-schema="${esc(doc.schema_version || '')}">
        ${doc.net_edge_research && global.ShortsNetEdgeViz ? `${global.ShortsNetEdgeViz.render(doc.net_edge_research)}<details class="rsp-fold"><summary>RSI-1.0 · original shorts backtest<small>Existing account results and execution research</small></summary>${global.ReverseSplitsPortfolioViz.render(doc)}</details>` : global.ReverseSplitsPortfolioViz.render(doc)}
        <details class="rsp-fold"><summary>Forward validation · ${fmtInt(completed)} completed observations<small>Frozen rules, new disclosures and missing broker evidence</small></summary>${renderForwardSummary(doc)}</details>
        <details class="rsp-fold"><summary>Event registry and upcoming actions<small>Filing sources, inventory coverage, scheduled actions and repeat splitters</small></summary>${renderHead(doc,opts)}${renderTiles(doc)}${renderCounts(doc)}${renderUpcoming(doc)}${renderRecent(doc,opts)}${renderRepeat(doc)}</details>
        <details class="rsp-fold"><summary>Earlier studies, methods and unresolved exits<small>Original price benchmarks, cost studies, controls, books and process rules</small></summary>${renderExpansion(doc)}${renderBook(doc)}${renderProcess(doc)}${renderLimits(doc)}<p class="subhead">${esc(doc.caption || '')}</p></details>
      </div>`;
    }
    return `${STYLE}<div class="rs-panel" data-schema="${esc(doc.schema_version || '')}">
      ${renderHead(doc, opts)}
      ${renderTiles(doc)}
      ${renderCounts(doc)}
      ${renderExpansion(doc)}
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
    attach,
    fmtRatio,
    fmtMoney,
    OUTCOME_LABEL,
    CLASS_LABEL,
    COHORT_LABEL,
    SOURCE_LABEL,
  };
})(window);
