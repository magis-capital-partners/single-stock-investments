// Darwin Covered Call: which calls on S&P 500 stocks are worth selling against a long position.
// Renders dashboard/data/darwin_cc.json (build_darwin_covered_call.py). Pure string rendering plus
// one bind() for the screener filters; index.html owns loading, routing and the stale badge.
(function () {
  'use strict';

  const CONDITION_LABELS = {
    low_beta: 'Low beta',
    rich_call_skew: 'Rich call skew',
    iv_above_forecast: 'IV above forecast',
    near_52w_high: 'Near 52w high',
  };
  const TENOR_ORDER = ['7d', '14d', '21d', '35d', '42d'];
  const state = { search: '', minScore: 0, tenor: 'all', maxDelta: 0.5, positiveOnly: true };

  const pct = (v, digits = 2) => (v == null || !Number.isFinite(Number(v)) ? '—' : `${Number(v).toFixed(digits)}%`);
  const signedPct = (v, digits = 2) => {
    if (v == null || !Number.isFinite(Number(v))) return '—';
    const n = Number(v);
    return `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toFixed(digits)}%`;
  };
  const evClass = (v) => (v == null ? '' : v > 0 ? 'dcc-pos' : v < 0 ? 'dcc-neg' : '');

  function chips(conditions, esc) {
    const list = Array.isArray(conditions)
      ? conditions
      : Object.keys(conditions || {}).filter((k) => conditions[k]);
    if (!list.length) return '<span class="dcc-muted">none</span>';
    return list.map((k) => `<span class="dcc-chip">${esc(CONDITION_LABELS[k] || k)}</span>`).join('');
  }

  function confidence(t) {
    if (t == null) return '<span class="dcc-muted">—</span>';
    const cls = t >= 2 ? 'badge-ok' : t >= 1 ? 'badge-warn' : 'badge-bad';
    return `<span class="badge ${cls}" title="t-statistic of this cell's 2016–2026 average, one observation per month">t ${Number(t).toFixed(1)}</span>`;
  }

  function callCells(c, esc) {
    return `<td class="mono">${esc(c.expiry)} <span class="dcc-muted">${c.dte}d</span></td>
      <td class="mono">${esc(String(c.strike))} <span class="dcc-muted">${c.otm_pct >= 0 ? '+' : ''}${Number(c.otm_pct).toFixed(1)}%</span></td>
      <td class="mono" title="A call's delta is roughly its chance of finishing in the money and calling the stock away">${Math.round(c.delta * 100)}Δ <span class="dcc-muted">~${Math.round(c.delta * 100)}% called</span></td>
      <td class="mono">${pct(c.premium_pct)}</td>
      <td class="mono ${evClass(c.ev_bp)}">${signedPct(c.ev_bp / 100)}</td>
      <td class="mono ${evClass(c.ev_annual_pct)}">${signedPct(c.ev_annual_pct, 1)}</td>
      <td>${confidence(c.cell_t)}</td>`;
  }

  function topTable(doc, esc) {
    const rows = doc.top || [];
    if (!rows.length) {
      return `<div class="operator-empty"><strong>No call clears the bar tonight</strong>
        <span>Every candidate was negative, illiquid, behind an earnings date, or in a cell without enough history.</span></div>`;
    }
    return `<div class="dcc-scroll"><table class="darwin-table">
      <thead><tr><th>Stock</th><th>Expiry</th><th>Strike · vs spot</th><th>Delta</th><th>Premium</th>
        <th>Expected per call</th><th>Per year if rolled</th><th>Confidence</th><th>Score</th><th>Conditions</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td class="mono"><strong>${esc(r.symbol)}</strong></td>${callCells(r, esc)}
        <td class="mono">${r.score}/4</td><td>${chips(r.conditions, esc)}</td></tr>`).join('')}</tbody>
    </table></div>`;
  }

  function screenerRows(doc) {
    const q = state.search.trim().toUpperCase();
    return (doc.names || [])
      .filter((n) => n.status === 'ok')
      .filter((n) => !q || n.symbol.includes(q))
      .filter((n) => (n.score || 0) >= state.minScore)
      .map((n) => {
        const calls = (n.calls || []).filter((c) => (state.tenor === 'all' || c.tenor === state.tenor) && c.delta <= state.maxDelta + 1e-9);
        return { n, best: calls[0] || null };
      })
      .filter(({ best }) => !state.positiveOnly || (best && best.ev_bp > 0))
      .sort((a, b) => ((b.best && b.best.ev_annual_pct) ?? -1e9) - ((a.best && a.best.ev_annual_pct) ?? -1e9));
  }

  function screener(doc, esc) {
    const rows = screenerRows(doc);
    const shown = rows.slice(0, 150);
    return `<div class="dcc-filters" role="group" aria-label="Screener filters">
        <label>Ticker <input id="dcc-search" type="search" value="${esc(state.search)}" placeholder="e.g. KO" autocomplete="off"></label>
        <label>Minimum score <select id="dcc-min-score">${[0, 1, 2, 3, 4].map((s) => `<option value="${s}"${state.minScore === s ? ' selected' : ''}>${s}</option>`).join('')}</select></label>
        <label>Tenor <select id="dcc-tenor"><option value="all"${state.tenor === 'all' ? ' selected' : ''}>Any</option>${TENOR_ORDER.map((t) => `<option value="${t}"${state.tenor === t ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
        <label>Max delta <select id="dcc-max-delta">${[0.1, 0.2, 0.3, 0.4, 0.5].map((d) => `<option value="${d}"${Math.abs(state.maxDelta - d) < 1e-9 ? ' selected' : ''}>${Math.round(d * 100)}Δ</option>`).join('')}</select></label>
        <label class="dcc-check"><input id="dcc-positive" type="checkbox"${state.positiveOnly ? ' checked' : ''}> Positive expected value only</label>
        <span class="dcc-muted">${rows.length} stock${rows.length === 1 ? '' : 's'}${rows.length > shown.length ? ` · showing ${shown.length}` : ''}</span>
      </div>
      ${shown.length ? `<div class="dcc-scroll"><table class="darwin-table">
        <thead><tr><th>Stock</th><th>Score</th><th>Conditions</th><th>Next earnings</th><th>Best call: expiry</th><th>Strike</th><th>Delta</th><th>Premium</th><th>Expected</th><th>Per year</th><th>Confidence</th></tr></thead>
        <tbody>${shown.map(({ n, best }) => `<tr>
          <td class="mono"><strong>${esc(n.symbol)}</strong></td>
          <td class="mono">${n.score}/4</td>
          <td>${chips(n.conditions, esc)}</td>
          <td class="mono">${esc(n.next_earnings || '—')}${n.vetoed_calls ? ` <span class="badge badge-warn" title="Calls expiring after this date were removed">veto ${n.vetoed_calls}</span>` : ''}</td>
          ${best ? callCells(best, esc) : '<td colspan="7" class="dcc-muted">No call in this tenor passes</td>'}
        </tr>`).join('')}</tbody></table></div>`
        : '<div class="operator-empty"><strong>No stocks match these filters</strong><span>Lower the minimum score, widen the tenor, or untick “Positive expected value only”.</span></div>'}`;
  }

  function evidence(doc, esc) {
    const m = doc.method || {};
    const v = m.validation || {};
    const exp = v.deciles_expected_bp || [];
    const real = v.deciles_realized_bp || [];
    const s4 = v.score4_weekly_2week_20_30d || {};
    const s3 = v.score3_weekly_2week_20_30d || {};
    return `<div class="dcc-two">
      <div>
        <h3>How the score works</h3>
        <p class="dcc-text">Selling a call against stock you hold adds the premium and gives up any rise above the strike.
          Over 2016–2026 that cost the holder money on monthly calls (a 30Δ call 35 days out averaged
          ${signedPct((v.unconditional_35d_30d_bp ?? -26.4) / 100)} per call) and was about break-even on weeklies.
          The calls were fairly priced; the loss was upside handed away. Four conditions, each with the same sign
          in 2016–20 and 2021–26, separated the calls that paid:</p>
        <ul class="dcc-list">${Object.entries(m.conditions || {}).map(([k, text]) => `<li><strong>${esc(CONDITION_LABELS[k] || k)}</strong>: ${esc(text)}</li>`).join('')}</ul>
        <p class="dcc-text">A call held through an earnings report is never shown: that was the largest single drag
          (−0.44% vs −0.09% per 35-day call). The expected value is the historical average for calls with the same tenor,
          delta and score, net of a quarter of the bid-ask spread and $0.65 a contract.</p>
        <p class="dcc-text dcc-muted">${esc(v.note || '')}</p>
      </div>
      <div>
        <h3>Did the score hold up on unseen years?</h3>
        <p class="dcc-text">Walk-forward 2019–2026: each year scored with cell averages from earlier years only.
          Weekly and two-week 20–30Δ calls on score-4 stocks earned ${signedPct((s4.realized_bp ?? 0) / 100)} per call
          (t ${Number(s4.t ?? 0).toFixed(1)}); score 3, ${signedPct((s3.realized_bp ?? 0) / 100)} (t ${Number(s3.t ?? 0).toFixed(1)}).</p>
        ${exp.length ? `<div class="dcc-scroll"><table class="darwin-table">
          <thead><tr><th>Decile of expected value</th>${exp.map((_, i) => `<th>${i + 1}</th>`).join('')}</tr></thead>
          <tbody>
            <tr><td>Expected</td>${exp.map((x) => `<td class="mono ${evClass(x)}">${signedPct(x / 100)}</td>`).join('')}</tr>
            <tr><td>Realized</td>${real.map((x) => `<td class="mono ${evClass(x)}">${signedPct(x / 100)}</td>`).join('')}</tr>
          </tbody></table></div>` : ''}
        <p class="dcc-text dcc-muted">This is income, not protection: covered calls helped in 2018 and 2022 and did nothing in
          March 2020. An assigned call sells the stock, which can realize a large taxable gain. Early assignment ahead of an
          ex-dividend date is not modelled.</p>
      </div>
    </div>`;
  }

  function render(doc, h) {
    const esc = h.escapeHtml;
    const u = doc.universe || {};
    const hist = doc.score_histogram || {};
    const horizon = new Date(Date.parse(`${doc.trading_date || ''}T00:00:00Z`) + 14 * 86400000).toISOString().slice(0, 10);
    const reportingSoon = (doc.names || []).filter((n) => n.next_earnings && n.next_earnings >= (doc.trading_date || '') && n.next_earnings <= horizon).length;
    return `<h2>Darwin Covered Call</h2>
      <p class="subhead">Which calls on S&amp;P 500 stocks are worth selling against shares you hold ·
        quotes ${esc(doc.trading_date || '—')} (Cboe, about 15 minutes delayed) ·
        built ${esc(doc.generated_at || '—')}${h.staleBadge(doc.generated_at)}</p>
      <div class="dcc-cards">
        <div class="summary-card"><div class="label">Stocks scored</div><div class="value">${u.scored ?? '—'}</div><div class="sub">of ${u.count ?? '—'} S&amp;P 500 members</div></div>
        <div class="summary-card"><div class="label">Pass all four conditions</div><div class="value">${hist['4'] ?? 0}</div><div class="sub">3 of 4: ${hist['3'] ?? 0} · 2: ${hist['2'] ?? 0}</div></div>
        <div class="summary-card"><div class="label">Calls worth writing</div><div class="value">${(doc.top || []).length}</div><div class="sub">score 3–4, liquid, clearly positive</div></div>
        <div class="summary-card"><div class="label">Reporting within 2 weeks</div><div class="value">${reportingSoon}</div><div class="sub">calls spanning a report are never shown</div></div>
      </div>
      <section class="detail-section">
        <h3>Best call per stock, ranked</h3>
        <p class="dcc-text dcc-muted">One call per stock, for stocks passing at least three of the four conditions: the highest expected
          value per year among liquid calls (open interest ≥ 500, spread ≤ 25% of mid) whose historical cell was clearly positive (t ≥ 1.5). Expected per call is the 2016–2026 average for calls like it;
          per year assumes it could be rolled at that rate, which overstates what one position can do. Higher-delta calls earned more but
          are called away more often (delta ≈ the chance): use the screener's tenor filter, or pick a lower delta, if you want to keep the shares.</p>
        ${topTable(doc, esc)}
      </section>
      <section class="detail-section">
        <h3>Screener</h3>
        <div id="dcc-screener">${screener(doc, esc)}</div>
      </section>
      <section class="detail-section">${evidence(doc, esc)}</section>
      ${(u.missing || []).length ? `<p class="dcc-text dcc-muted">Not scored tonight (no chain, no technicals, or no sellable call): ${u.missing.map(esc).join(', ')}.</p>` : ''}`;
  }

  function bind(root, doc, h) {
    const host = root.querySelector('#dcc-screener');
    if (!host) return;
    const rerender = () => {
      host.innerHTML = screener(doc, h.escapeHtml);
      wire();
    };
    function wire() {
      const search = host.querySelector('#dcc-search');
      search?.addEventListener('input', (e) => {
        state.search = e.target.value;
        const caret = e.target.selectionStart;
        rerender();
        const next = host.querySelector('#dcc-search');
        next.focus();
        next.setSelectionRange(caret, caret);
      });
      host.querySelector('#dcc-min-score')?.addEventListener('change', (e) => { state.minScore = Number(e.target.value); rerender(); });
      host.querySelector('#dcc-tenor')?.addEventListener('change', (e) => { state.tenor = e.target.value; rerender(); });
      host.querySelector('#dcc-max-delta')?.addEventListener('change', (e) => { state.maxDelta = Number(e.target.value); rerender(); });
      host.querySelector('#dcc-positive')?.addEventListener('change', (e) => { state.positiveOnly = e.target.checked; rerender(); });
    }
    wire();
  }

  window.DarwinCCViz = Object.freeze({ render, bind, CONDITION_LABELS });
})();
