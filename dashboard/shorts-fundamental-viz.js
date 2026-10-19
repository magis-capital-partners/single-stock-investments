/* Matched fundamental-policy comparisons; all performance fields remain visible. */
(function (global) {
  'use strict';
  const esc = v => String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const words = v => String(v).replaceAll('_', ' ').replaceAll('.', ' / ');
  const pct = v => v == null ? '—' : `${(v * 100).toFixed(3)}%`;
  const num = v => v == null ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: 3});
  let data, period = 'recent', records = [], page = 0, query = '', generation = 0;
  const cache = new Map();
  const label = {trades: 'Closed trades', admitted: 'Admitted trades', issuers: 'Companies', decisions: 'Entry decisions',
    unresolved: 'Unresolved admitted positions', performance_valid: 'Account performance valid',
    'performance.net_pnl': 'Net account profit', 'performance.total_return': 'Total account return',
    'performance.cagr': 'Annualized account return', 'performance.calmar_full_period': 'Calmar · full period',
    'performance.max_drawdown': 'Maximum daily closing drawdown', 'trade_statistics.win_rate': 'Net win rate',
    'trade_statistics.profit_factor': 'Profit factor', 'trade_statistics.expectancy_dollars': 'Average net profit per closed trade'};
  const safe = v => { try { const u = new URL(v); return u.protocol === 'https:' ? esc(u.href) : '#'; } catch { return '#'; } };
  function flatten(value, prefix = '', result = {}) {
    if (value && typeof value === 'object') {
      Object.entries(value).forEach(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k, result));
    } else result[prefix] = value;
    return result;
  }
  function format(value, key) {
    if (value == null) return '—';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value !== 'number') return esc(words(value));
    if (/(_pnl|equity$|average_win$|average_loss$|expectancy_dollars|summed_entry_exposure|(?:^|\.)costs\.)/.test(key)) return `${value < 0 ? '−' : ''}$${num(Math.abs(value))}`;
    if (/(return|cagr|drawdown|volatility|worst_day|best_day|win_rate|loss_var|loss_es|loss_frequency|share_of_positive_pnl|ulcer_index|issuer_clustered_mean_interval\.(low|high))/.test(key) && !/(clusters|observations|draws|years)/.test(key)) return pct(value);
    return num(value);
  }
  function comparison(rows, fields) {
    const flat = rows.map(r => flatten(r));
    const keys = fields || [...new Set(flat.flatMap(r => Object.keys(r)))];
    return `<div class="rsp-scroll sfv-scroll"><table class="insights-table sfv-table"><thead><tr><th scope="col">Statistic</th>${data.cases.map(c => `<th scope="col">${esc(c.label)}</th>`).join('')}</tr></thead><tbody>${keys.map(k => `<tr><th scope="row">${esc(label[k] || words(k))}</th>${flat.map(r => `<td>${format(r[k], k)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function windows() { return data.cases.map(c => c.windows[period]); }
  function stats() {
    const rows = windows();
    const invalid = rows.some(r => !r.performance_valid);
    const allRows = rows.map(({annual, ...rest}) => rest);
    const years = [...new Set(rows.flatMap(r => (r.annual || []).map(a => a.year)))].sort();
    const annual = years.map(year => `<h4>${esc(year)} account results</h4>${comparison(rows.map(r => (r.annual || []).find(a => a.year === year) || {}))}`).join('');
    return `${invalid ? '<p class="rsp-evidence">At least one policy has an unresolved liability or a margin breach. Its account returns and Calmar are withheld; its closed-trade statistics describe an incomplete subset.</p>' : ''}${comparison(rows, ['trades', 'admitted', 'issuers', 'performance.net_pnl', 'performance.total_return', 'performance.cagr', 'performance.max_drawdown', 'performance.calmar_full_period', 'trade_statistics.win_rate', 'trade_statistics.profit_factor', 'trade_statistics.expectancy_dollars', 'unresolved'])}
      <details open><summary>Every account, trade, cost, risk and exclusion statistic</summary><p>Returns are on funded account equity unless the label says trade return or exposure. Closed-trade statistics exclude any outstanding liability. A dash means unavailable. Joint daily-high risk is a conservative bound.</p>${comparison(allRows)}</details><details open><summary>Year-by-year account results</summary>${annual}</details>`;
  }
  function robustness() {
    const fields = ['start', 'end', 'trades', 'issuers', 'performance.net_pnl', 'performance.cagr', 'performance.max_drawdown', 'performance.calmar_full_period', 'unresolved', 'margin_breach_days'];
    const groups = [
      ...data.cases[0].chronological_periods.map((r, i) => [`${r.start} → ${r.end}`, data.cases.map(c => c.chronological_periods[i])]),
      ...data.cases[0].cost_sensitivities.map((r, i) => [words(r.scenario), data.cases.map(c => c.cost_sensitivities[i])]),
      ['Remove each policy’s largest positive issuer · retrospective sensitivity', data.cases.map(c => c.without_top_issuer)]
    ];
    return `<details open><summary>Chronological periods, cost stresses and concentration</summary>${groups.map(([title, rows]) => `<h4>${esc(title)}</h4>${comparison(rows, fields)}<details><summary>Every statistic for this check</summary>${comparison(rows)}</details>`).join('')}<h4>Declared qualification checks</h4>${comparison(data.cases.map(c => c.qualification || {qualified: null}))}</details>`;
  }
  async function verified(spec, expected) {
    if (spec.url !== expected) throw new Error('Unexpected study path');
    const response = await fetch(`${expected}?v=${spec.sha256.slice(0, 12)}`);
    if (!response.ok) throw new Error('Study unavailable');
    const bytes = await response.arrayBuffer();
    const hash = Array.from(new Uint8Array(await global.crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    if (hash !== spec.sha256) throw new Error('Study hash mismatch');
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  async function part(index) {
    const spec = data.packets[index];
    if (!/^data\/shorts_fundamental_packets\/part-\d{3}\.json$/.test(spec.url)) throw new Error('Unexpected packet path');
    if (!cache.has(index)) cache.set(index, verified(spec, spec.url).then(doc => {
      if (doc.schema_version !== 'shorts_fundamental_packet_part.v1' || !Array.isArray(doc.records)) throw new Error('Invalid evidence packet');
      return doc;
    }).catch(e => { cache.delete(index); throw e; }));
    return cache.get(index);
  }
  function queue() {
    const matching = records.filter(r => `${r.ticker} ${r.issuer} ${r.financials.status}`.toLowerCase().includes(query.toLowerCase()));
    const start = page * 25;
    return `<p>${num(matching.length)} loaded matches · page ${num(page + 1)}</p><div class="rsp-scroll"><table class="insights-table"><thead><tr><th>Name / announcement</th><th>Reported score</th><th>Financial coverage</th><th>Recent entry decisions</th></tr></thead><tbody>${matching.slice(start, start + 25).map(r => `<tr><th scope="row"><button class="sne-name" data-key="${esc(r.key)}" onclick="ShortsFundamentalViz.inspect(this.dataset.key)">${esc(r.ticker)}</button><small>${esc(r.known_at.slice(0, 10))}</small></th><td>${num(r.score)}</td><td>${esc(words(r.financials.status))}</td><td>${data.cases.map(c => `${esc(c.label)}: ${esc(words(r.decisions[c.id].recent))}`).join('<br>')}</td></tr>`).join('')}</tbody></table></div><button onclick="ShortsFundamentalViz.move(-1)" ${page === 0 ? 'disabled' : ''}>Previous</button> <button onclick="ShortsFundamentalViz.move(1)" ${start + 25 >= matching.length ? 'disabled' : ''}>Next</button>`;
  }
  async function open(spec) {
    const mount = document.getElementById('sev-fundamental-research');
    mount.innerHTML = '<p>Loading the matched fundamental comparison…</p>';
    try {
      const doc = await verified(spec, 'data/shorts_fundamental_research.json');
      if (doc.schema_version !== 'shorts_fundamental_study.v1' || doc.authority !== 'none' || doc.production_policy_changed !== false || doc.data_cost_usd !== 0 || doc.bindings.research_summary_sha256 !== spec.base_summary_sha256 || doc.cases.map(c => c.id).join(',') !== 'unfiltered,score60,score50,score60_or_distress') throw new Error('Invalid matched study');
      data = doc; period = 'recent'; records = []; page = 0; query = ''; cache.clear(); generation++;
      const selection = doc.selection;
      mount.innerHTML = `<section class="sfv-study"><h3>No fundamentals versus fundamental policies</h3><p>Same next-session entry, 10-session maximum, 20% target / 20% stop, $50,000 account, $100 minimum and 0.1% prior share-volume limit. Every policy uses the full planned horizon for its cost reserve and ranks concurrent entries by prior liquidity. The unfiltered case needs no financial score or payoff forecast. The final nine entry sessions are excluded for every policy so a full horizon can mature.</p><p class="rsp-evidence">${selection.paper_candidate ? `Historical paper candidate: ${esc(selection.paper_candidate)}.` : 'No fundamental policy cleared every declared robustness requirement.'} No production policy changed. Earlier 49 / 89 results used a different forecast-dependent reserve and remain a separate reference.</p><label class="rsp-select">Comparison period<select aria-label="Fundamental comparison period" onchange="ShortsFundamentalViz.change(this.value)"><option value="recent">October 2023–October 2026</option><option value="full">May 2018–October 2026</option></select></label><div id="sfv-statistics" aria-live="polite">${stats()}</div>${robustness()}<details><summary>Source recovery, financial coverage and frozen protocol</summary><pre class="sfv-protocol">${esc(JSON.stringify({coverage: doc.coverage, plan: doc.plan, acquisition: {...doc.acquisition, uncached_sources_pending: doc.acquisition.uncached_sources_pending?.length}, forward_validation: doc.forward_validation}, null, 2))}</pre></details><details><summary>Inspect financial evidence and policy exclusions</summary><label>Find a ticker, issuer or financial gap<input type="search" aria-label="Search fundamental evidence" oninput="ShortsFundamentalViz.search(this.value)"></label><div id="sfv-queue" aria-live="polite"></div><div id="sfv-detail" aria-live="polite"></div></details><details><summary>Interpretation and remaining limitations</summary><ul>${doc.limits.map(v => `<li>${esc(v)}</li>`).join('')}</ul><p>The cash-distress route requires fresh reported cash, TTM and latest-quarter cash runways each at most one year, operating losses, and a reported twelve-month debt maturity greater than cash. Financing passages alone do not qualify. Missing debt stays unknown; older annual statements do not silently qualify.</p></details></section>`;
      const first = await part(0); records = first.records;
      document.getElementById('sfv-queue').innerHTML = queue();
    } catch { mount.innerHTML = '<p>The fundamental comparison could not be verified. Reload to retry.</p>'; }
  }
  function change(value) { if (!['recent', 'full'].includes(value)) return; period = value; document.getElementById('sfv-statistics').innerHTML = stats(); }
  async function search(value) {
    query = value; page = 0; const request = ++generation;
    document.getElementById('sfv-queue').innerHTML = '<p>Searching every source packet…</p>';
    try {
      const all = [];
      for (let i = 0; i < data.packets.length; i += 4) all.push(...await Promise.all(data.packets.slice(i, i + 4).map((_, j) => part(i + j))));
      if (request !== generation) return;
      records = all.flatMap(p => p.records); document.getElementById('sfv-queue').innerHTML = queue();
    } catch { document.getElementById('sfv-queue').innerHTML = '<p>The evidence packets could not be verified.</p>'; }
  }
  function move(delta) { page = Math.max(0, page + delta); document.getElementById('sfv-queue').innerHTML = queue(); }
  function inspect(key) {
    const r = records.find(r => r.key === key); if (!r) return;
    const f = r.financials;
    document.getElementById('sfv-detail').innerHTML = `<article class="sne-detail"><h4>${esc(r.ticker)} · ${esc(r.known_at.slice(0, 10))}</h4><p>Score ${num(r.score)} · ${esc(words(f.status))}. Independent signal families: ${esc((f.coverage?.families || []).join(', '))}.</p><pre class="sfv-protocol">${esc(JSON.stringify({coverage: f.coverage, liquidity: f.liquidity, supplemental: f.supplemental, policies: r.policies}, null, 2))}</pre><h4>As-filed sources</h4><ul>${(f.evidence || []).map(e => `<li>${esc(e.tag)} · ${esc(e.start ? e.start+' → '+e.end : e.end)} · ${num(e.val)} ${esc(e.unit)} · <a href="${safe(e.source_url)}" target="_blank" rel="noopener">${esc(e.known_at || e.filed)}</a></li>`).join('')}</ul></article>`;
  }
  global.ShortsFundamentalViz = {open, change, search, move, inspect};
})(window);
