/**
 * Separations — split-offs, spin-offs, carve-outs, retained-stake sales.
 *
 * Renders the per-ticker attach (`row.separation` from core.json / ticker
 * shards, schema in _system/data/separations/README.md) as a compact card, the
 * odd-lot badge for held parents with an open exchange offer, and a flow-legs
 * table drawn the way index-viz.js draws the Index Watch flow bridge (same
 * classes, same footnote discipline). Everything is escaped; nothing here
 * invents a number: a missing input renders as a dash with its reason.
 *
 * Research-only. No output of this file changes intrinsic value or an IRR.
 */
(function (global) {
  'use strict';

  const esc = (value) => String(value == null ? '' : value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const KIND_LABEL = {
    split_off: 'Split-off',
    spin_off: 'Spin-off',
    carve_out_ipo: 'Carve-out IPO',
    clean_up_spin: 'Clean-up distribution',
    retained_stake_sale: 'Retained-stake sale',
    reverse_morris_trust: 'Reverse Morris Trust',
  };

  const STATUS_LABEL = {
    announced: 'Announced',
    filed: 'Filed',
    when_issued: 'When-issued',
    offer_open: 'Offer open',
    valuation_period: 'Valuation period',
    completed: 'Completed',
    withdrawn: 'Withdrawn',
  };

  const STATUS_BADGE = {
    offer_open: 'badge-warn',
    valuation_period: 'badge-warn',
    when_issued: 'badge-us',
    announced: 'badge-purple',
    filed: 'badge-purple',
    completed: 'badge-ok',
    withdrawn: 'badge-bad',
  };

  const ROLE_LABEL = { parent: 'Parent', spinco: 'SpinCo' };

  const LEG_LABEL = {
    index_exclusion_sale: 'Index exclusion sale',
    index_add_buy: 'Index add buy',
    mandate_mismatch_sale: 'Mandate mismatch sale',
    arb_unwind_sale: 'Arb unwind sale',
    unaccepted_parent_return: 'Unaccepted parent return',
    retained_stake_overhang: 'Retained-stake overhang',
    clean_up_distribution: 'Clean-up distribution',
    parent_share_retirement: 'Parent share retirement',
  };

  const LANE_SLUG = { split_off: 'split-offs', reverse_morris_trust: 'split-offs' };

  function label(table, key, fallback) {
    if (key == null || key === '') return fallback == null ? '—' : fallback;
    return table[key] || String(key).replaceAll('_', ' ');
  }

  function isNum(value) {
    return value != null && value !== '' && Number.isFinite(Number(value));
  }

  function fmtPct(value, digits) {
    if (!isNum(value)) return '—';
    const n = Number(value);
    const d = digits == null ? 1 : digits;
    return `${n > 0 ? '+' : ''}${n.toFixed(d)}%`;
  }

  function fmtShares(value) {
    if (!isNum(value)) return '—';
    const n = Number(value);
    const abs = Math.abs(n);
    const sign = n < 0 ? '-' : (n > 0 ? '+' : '');
    if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}k`;
    return `${sign}${abs.toFixed(0)}`;
  }

  function windowLabel(start, end) {
    if (start && end) return `${start} → ${end}`;
    if (end) return `through ${end}`;
    if (start) return `from ${start}`;
    return 'window not stated';
  }

  /** One line: "-3.4% of float · 1.8 days ADV · through 2023-09-08 · estimate". */
  function flowLine(flow) {
    if (!flow) return 'No flow modelled.';
    const parts = [];
    parts.push(isNum(flow.pct_of_float_base) ? `${fmtPct(flow.pct_of_float_base)} of float` : 'float impact —');
    if (isNum(flow.pct_of_adv_days)) parts.push(`${Number(flow.pct_of_adv_days).toFixed(1)} days ADV`);
    parts.push(windowLabel(flow.window_start, flow.window_end));
    if (flow.confidence) parts.push(String(flow.confidence).replaceAll('_', ' '));
    return parts.join(' · ');
  }

  /**
   * Legs table, drawn the way index-viz.js renderFlowBridge draws the Index
   * Watch bridge: a <details> whose summary carries the band, an
   * `insights-table` of legs, a muted footnote. Sell legs are negative.
   */
  function renderFlowLegs(flowBlock, options) {
    const opts = options || {};
    const e = opts.escapeHtml || esc;
    const fi = flowBlock;
    if (!fi || fi.status === 'n_a') {
      const why = fi && fi.reason ? fi.reason : 'no separation flow modelled';
      return `<p class="muted" title="${e(why)}">— (${e(why)})</p>`;
    }
    const legs = Array.isArray(fi.legs) ? fi.legs : [];
    if (!legs.length) return '<p class="muted">No flow legs.</p>';
    const body = legs.map((lg) => {
      const base = isNum(lg.shares_base) ? Number(lg.shares_base) : null;
      const dir = lg.direction || (base != null && base < 0 ? 'sell' : (base != null && base > 0 ? 'buy' : '—'));
      const conf = lg.confidence ? String(lg.confidence).replaceAll('_', ' ') : '—';
      const na = lg.confidence === 'n_a';
      return `<tr${na ? ' class="muted"' : ''}>
          <td>${e(lg.label || LEG_LABEL[lg.leg] || lg.leg || '—')}</td>
          <td class="mono">${e(dir)}</td>
          <td class="mono">${na ? '—' : e(fmtShares(lg.shares_base))}</td>
          <td class="mono">${na ? '—' : e(fmtPct(lg.pct_of_float_base))}</td>
          <td class="mono">${e(windowLabel(lg.window_start, lg.window_end))}</td>
          <td class="mono">${e(conf)}</td>
          <td class="muted">${e(lg.reason || lg.source || '')}</td>
        </tr>`;
    }).join('');
    const band = isNum(fi.pct_of_float_base)
      ? `low ${fmtPct(fi.pct_of_float_low)} · base ${fmtPct(fi.pct_of_float_base)} · high ${fmtPct(fi.pct_of_float_high)} of float`
      : 'band not stated';
    const adv = isNum(fi.pct_of_adv_days) ? ` · ${Number(fi.pct_of_adv_days).toFixed(2)} days ADV` : '';
    const side = fi.side ? ` · ${label(ROLE_LABEL, fi.side)}${fi.ticker ? ` ${fi.ticker}` : ''}` : '';
    const stamp = fi.run_date ? ` · run ${fi.run_date}` : '';
    return `<details class="separation-legs" style="margin-top:4px"${opts.open ? ' open' : ''}>
      <summary style="cursor:pointer;font-size:12px">Who must sell${e(side)} · ${e(band)}${e(adv)}${e(stamp)}</summary>
      <table class="insights-table" style="margin-top:6px"><thead><tr>
        <th>Leg</th><th>Dir</th><th>Shares (base)</th><th>% float</th><th>Window</th><th>Confidence</th><th>Basis</th>
      </tr></thead><tbody>${body}</tbody></table>
      <p class="muted" style="margin-top:6px;font-size:var(--font-caption,12px)">Negative % float = net forced selling. Both sides of the separation are modelled. An <em>n a</em> leg had a missing input and carries its reason instead of a number. Research only; changes no value and no IRR.</p>
    </details>`;
  }

  /** "Odd-lot · expires YYYY-MM-DD" when a sleeve can take the odd-lot priority. */
  function renderOddLotBadge(attach, options) {
    const opts = options || {};
    const e = opts.escapeHtml || esc;
    const odd = attach && attach.odd_lot;
    const owners = odd && Array.isArray(odd.eligible_owners) ? odd.eligible_owners.filter(Boolean) : [];
    if (!owners.length) return '';
    const expires = odd.expiration ? `expires ${odd.expiration}` : 'expiry not stated';
    const tip = `Odd-lot priority: holders of ${odd.max_shares || 99} or fewer shares are accepted before proration. Eligible: ${owners.join(', ')}. Opens a human ticket; never prefills an order.`;
    return `<span class="badge badge-warn odd-lot-badge" title="${e(tip)}">Odd-lot · ${e(expires)}</span>`;
  }

  function roleHref(role, opts) {
    const slug = LANE_SLUG[role.kind] || 'spinoffs';
    if (opts && typeof opts.situationHref === 'function') return opts.situationHref(slug, role.counterparty, role);
    const focus = role.counterparty ? `/${encodeURIComponent(role.counterparty)}` : '';
    return `#/ideas/situations/${slug}${focus}`;
  }

  /**
   * Compact "Separation" card for the ticker detail panel. `attach` is
   * `row.separation`: `{ roles: [...], odd_lot: {...} }`. Empty string when
   * there is nothing to show, so the caller can inline it unconditionally.
   */
  function renderTickerCard(attach, options) {
    const opts = options || {};
    const e = opts.escapeHtml || esc;
    const roles = attach && Array.isArray(attach.roles) ? attach.roles.filter(Boolean) : [];
    if (!roles.length) return '';
    const rows = roles.map((role) => {
      const statusCls = STATUS_BADGE[role.status] || 'badge-purple';
      const counter = role.counterparty
        ? `<a class="separation-counterparty" href="${e(roleHref(role, opts))}" title="Open on the Special Situations desk">${e(role.counterparty)}</a>`
        : '<span class="muted">counterparty not named</span>';
      const ends = role.ends_label || (role.ends ? `Ends ${role.ends}` : 'End date not stated');
      const legs = role.flow && Array.isArray(role.flow.legs) && role.flow.legs.length ? renderFlowLegs(role.flow, opts) : '';
      return `<div class="separation-role" data-separation-id="${e(role.separation_id || '')}">
        <span class="badge badge-purple">${e(label(ROLE_LABEL, role.role, 'Party'))}</span>
        <span class="separation-kind">${e(label(KIND_LABEL, role.kind, 'Separation'))}</span>
        <span class="badge ${statusCls}">${e(label(STATUS_LABEL, role.status, 'Status not stated'))}</span>
        <span class="separation-with">${role.role === 'spinco' ? 'from' : 'with'} ${counter}</span>
        <span class="separation-ends mono">${e(ends)}</span>
        <div class="separation-flow">${e(flowLine(role.flow))}</div>
        ${legs}
      </div>`;
    }).join('');
    const badge = renderOddLotBadge(attach, opts);
    return `<div class="detail-section separation-card">
      <h3>Separation${badge ? ` ${badge}` : ''}</h3>
      ${rows}
      <p class="subhead" style="margin-top:6px">Forced selling is a research trigger and a timing input. It does not change intrinsic value.</p>
    </div>`;
  }

  global.SeparationsViz = {
    renderTickerCard,
    renderOddLotBadge,
    renderFlowLegs,
    flowLine,
    fmtPct,
    KIND_LABEL,
    STATUS_LABEL,
  };
})(window);
