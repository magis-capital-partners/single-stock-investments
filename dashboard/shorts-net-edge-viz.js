/* RSI-2.0: frozen evidence -> payoff distribution -> cost -> bounded position. */
(function(global) {
  'use strict';
  const esc = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
  const num = (v,d=1) => v == null || !Number.isFinite(v) ? '—' : Number(v).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
  const pct = v => v == null ? '—' : `${num(v*100,2)}%`;
  const money = v => v == null ? '—' : `${v<0?'−':''}$${num(Math.abs(v),0)}`;
  const label = v => String(v ?? '').replaceAll('_',' ');
  const variant = {baseline:'Equal size · common forecastable cohort',fundamental:'Fundamental filter · equal size',net_edge:'Net-edge sizing · screen only',strict:'Full framework + dated borrow'};
  let data;
  let state = {exit:'bracket',days:'0',query:'',filter:'all'};

  function render(doc) {
    if(!doc || doc.schema_version !== 'shorts_net_edge.v2') return '';
    data=doc;
    state={exit:'bracket',days:'0',query:'',filter:'all'};
    return `<section class="sne" aria-labelledby="sne-title">
      <div class="sne-heading"><div><span class="sne-eyebrow">RSI-2.0 · additional sizing filter</span><h2 id="sne-title">How much edge survives the costs?</h2><p>Freeze the evidence at announcement. Estimate the payoff and time to exit. Size the short from what remains.</p></div><span class="sne-status">Conditional research</span></div>
      <div class="sne-equation" aria-label="Net edge formula"><span>Fundamentals <small>+ documented share dilution</small></span><b>→</b><span>Gross edge</span><b>−</b><span>Slippage <small>and commissions</small></span><b>−</b><span>Holding-period borrow</span><b>=</b><strong>Net edge</strong></div>
      <p class="sne-note">A reverse split changes the share count and price proportionally. Only actual issuance or other financing terms enter dilution. Unknown dilution stays unknown.</p>
      <div class="sne-coverage"><span><b>${num(doc.coverage.numeric_conviction,0)}/${num(doc.coverage.events,0)}</b> announcement-time fundamental ratings</span><span><b>${num(doc.coverage.full_framework_conviction,0)}</b> complete framework ratings</span><span><b>${num(doc.coverage.reconciled_dilution,0)}</b> reconciled dilution packages</span><span><b>${num(doc.coverage.dated_approved_locates,0)}</b> dated approved locates</span></div>
      <p class="sne-evidence">${doc.coverage.full_framework_conviction ? 'Full conviction uses dated reviews across the short framework.' : 'Full conviction remains unscored where dated framework reviews are missing.'} Screen-only results assume borrowing access. The full-framework row excludes names without the required evidence.</p>
      <div class="sne-controls"><label>Exit policy<select onchange="ShortsNetEdgeViz.change('exit',this.value)"><option value="bracket">10% profit take / 20% stop / close</option><option value="time60">60-minute hold</option><option value="close">Hold to close</option></select></label><label>Borrow billing<select onchange="ShortsNetEdgeViz.change('days',this.value)"><option value="0">Matched same-day settlement · 0 days</option><option value="1">Pre-borrow sensitivity · at least 1 day</option></select></label></div>
      <div id="sne-results">${results()}</div>
      <details class="sne-method"><summary>How conviction, dilution, skew and carry enter sizing</summary><dl>${Object.entries(doc.definitions).map(([k,v])=>`<dt>${esc(label(k))}</dt><dd>${esc(v)}</dd>`).join('')}</dl><p>${doc.sources.map(s=>`<a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(' · ')}</p></details>
      <section class="sne-audit" aria-labelledby="sne-audit-title"><h3 id="sne-audit-title">Name-by-name decision audit</h3><p class="sne-note">Primary policy: 10% profit take / 20% stop / close, ordinary same-day borrowing. Ratings and forecasts are frozen at announcement; entry follows the existing first-session-after-split schedule.</p><div class="sne-controls"><label>Find a name<input type="search" placeholder="Ticker" aria-label="Search decision audit by ticker" oninput="ShortsNetEdgeViz.change('query',this.value)"></label><label>Show<select onchange="ShortsNetEdgeViz.change('filter',this.value)"><option value="all">All announcements in priced sample</option><option value="included">Included names</option><option value="excluded">Excluded names</option><option value="forecast">Names with an edge estimate</option></select></label></div><div id="sne-names">${names()}</div><div id="sne-name-detail" aria-live="polite"></div></section>
      <details class="sne-method"><summary>Research limits and evidence gaps</summary><ul>${doc.limits.map(v=>`<li>${esc(v)}</li>`).join('')}</ul></details>
    </section>`;
  }

  function safeUrl(v) {
    try {const u=new URL(v);return u.protocol==='https:'?esc(u.href):'#';}catch{return '#';}
  }

  function results() {
    const rows=data.cases.filter(r=>r.exit===state.exit && String(r.minimum_billed_days)===state.days);
    const primary=rows.find(r=>r.variant==='net_edge');
    const table=rows.map(r=>`<tr class="${r.variant==='net_edge'?'sne-primary':''}"><th scope="row">${esc(variant[r.variant])}</th><td>${num(r.trades,0)}</td><td>${money(r.portfolio.net_pnl)}</td><td>${r.trades?pct(r.portfolio.cagr):'—'}</td><td>${r.trades?pct(r.portfolio.max_drawdown):'—'}</td><td>${money(r.costs.borrow)}</td></tr>`).join('');
    return `<div class="rsp-scroll"><table class="insights-table sne-compare"><caption>${esc(primary?.portfolio.start)} → ${esc(primary?.portfolio.end)} · $50,000 starting equity · identical entry, capital and exit rules · forecastable cohort only</caption><thead><tr><th scope="col">Sizing / exclusion rule</th><th scope="col">Trades</th><th scope="col">Net P&amp;L</th><th scope="col">Account CAGR</th><th scope="col">Closing drawdown</th><th scope="col">Borrow paid*</th></tr></thead><tbody>${table}</tbody></table></div>
      <p class="sne-note">*Modeled carry at a 50% annual rate where historical terms are absent. A billed day is a calendar day, not a fraction of the trading session. All variants retain commission minima and the same +200% squeeze loss budget.</p>
      ${primary?curve(primary):''}
      <details class="sne-method"><summary>Why the net-edge case excluded names</summary><div class="sne-exclusions">${Object.entries(primary?.skipped || {}).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<span>${esc(label(k))}<b>${num(v,0)}</b></span>`).join('')}</div><p class="sne-note">${num(primary?.estimated_fills,0)} included trades use estimated fills; ${num(primary?.missing_exit_quotes,0)} lack an observed exit quote. Closing drawdown does not measure intraday margin survival.</p></details>`;
  }

  function curve(row) {
    if(!row.trades)return '<p class="sne-empty"><strong>No names survive these settings.</strong> Capital remains idle. Zero admitted trades is a filter result; it does not establish profitable performance.</p>';
    const values=row.equity_curve, W=850,H=180,pad=30;
    const low=Math.min(...values.map(d=>d.equity)),high=Math.max(...values.map(d=>d.equity));
    const lo=low===high?low-1:low,hi=high===low?high+1:high;
    const start=Date.parse(values[0].date),end=Date.parse(values.at(-1).date);
    const points=values.map(d=>`${pad+(Date.parse(d.date)-start)/Math.max(1,end-start)*(W-2*pad)},${H-pad-(d.equity-lo)/(hi-lo)*(H-2*pad)}`).join(' ');
    return `<figure class="sne-curve"><figcaption>Net-edge account · ${num(row.trades,0)} modeled trades · ${money(row.portfolio.ending_equity)} ending equity</figcaption><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Account equity from ${esc(values[0].date)} to ${esc(values.at(-1).date)}, ending ${money(row.portfolio.ending_equity)}"><line x1="${pad}" x2="${W-pad}" y1="${H-pad}" y2="${H-pad}"/><polyline points="${points}"/><text x="${pad}" y="18">${money(hi)}</text><text x="${pad}" y="${H-5}">${esc(values[0].date)}</text><text x="${W-pad}" y="${H-5}" text-anchor="end">${esc(values.at(-1).date)}</text></svg></figure>`;
  }

  function names() {
    const rows=data.names.filter(r=>(!state.query || r.ticker.toLowerCase().includes(state.query.toLowerCase())) &&
      (state.filter==='all'||state.filter==='included'&&r.decision?.reason==='included'||state.filter==='excluded'&&r.decision?.reason!=='included'||state.filter==='forecast'&&r.estimate.net_edge!=null));
    if(!rows.length)return '<p class="sne-empty">No names match these filters.</p>';
    return `<p class="sne-note">${num(rows.length,0)} names · select a ticker for its edge calculation and evidence coverage.</p><div class="rsp-scroll sne-name-scroll"><table class="insights-table"><thead><tr><th scope="col">Name / entry</th><th scope="col">Screen conviction</th><th scope="col">Gross edge</th><th scope="col">Costs</th><th scope="col">Net edge</th><th scope="col">Net skew</th><th scope="col">Gain / loss</th><th scope="col">Expected hold</th><th scope="col">Shares / reason</th></tr></thead><tbody>${rows.map(r=>{const e=r.estimate;return `<tr><th scope="row"><button class="sne-name" data-key="${esc(r.key)}" onclick="ShortsNetEdgeViz.inspect(this.dataset.key)">${esc(r.ticker)}</button><small>${esc(r.date)}</small></th><td>${num(r.screen_rating)}<small>${r.conviction?.rating==null?'Provisional':'Full '+num(r.conviction.rating)}</small></td><td>${pct(e.gross_edge)}</td><td>${e.net_edge==null?'—':pct(e.expected_slippage+e.expected_commission+e.expected_borrow)}</td><td class="sne-edge">${pct(e.net_edge)}</td><td>${num(e.net?.skewness,2)}</td><td>${num(e.net?.gain_loss_ratio,2)}</td><td>${num(e.expected_hold_minutes,0)} min</td><td>${r.decision?.shares?num(r.decision.shares,0):esc(label(r.decision?.reason||'unavailable'))}</td></tr>`;}).join('')}</tbody></table></div>`;
  }

  function inspect(key) {
    const r=data.names.find(r=>r.key===key),mount=document.getElementById('sne-name-detail');
    if(!r || !mount)return;
    const e=r.estimate,f=r.conviction?.framework;
    mount.innerHTML=`<article class="sne-detail"><h4>${esc(r.ticker)} · what was knowable at announcement</h4><p>${esc(r.announcement||'No verified clock')} · latest fundamental period ${esc(r.fundamental_period||'unknown')} ${r.source_url?`· <a href="${safeUrl(r.source_url)}" target="_blank" rel="noopener">Primary announcement</a>`:''}</p><div class="sne-waterfall"><span>Gross <b>${pct(e.gross_edge)}</b></span><span>− Slippage <b>${pct(e.expected_slippage)}</b></span><span>− Commission <b>${pct(e.expected_commission)}</b></span><span>− Borrow <b>${pct(e.expected_borrow)}</b></span><strong>Net edge <b>${pct(e.net_edge)}</b></strong></div><p>${num(e.donors,0)} prior independent issuer observations · last payoff observation ${esc(e.latest_training_exit||'unavailable')} · expected hold ${num(e.expected_hold_minutes,0)} minutes · expected billed days ${num(e.expected_billed_days,2)}.</p><p>Actual dilution: ${r.dilution?.ownership_dilution==null?'unreconciled':pct(r.dilution.ownership_dilution)}. Mechanical dilution from the reverse split: 0%. Borrow: ${r.historical_locate?'dated approved locate':'assumed availability; no historical approved locate'}.</p><div class="sne-lenses">${(f?.lenses||[]).map(l=>`<span>${esc(l.label)}<b>${num(l.reviewed,0)}/${num(l.total,0)} reviewed</b></span>`).join('')}</div><p class="sne-note">${num(f?.reviewed,0)}/${num(f?.total,0)} framework routes have dated evidence. A numeric deterioration screen does not establish a qualitative thesis.</p></article>`;
    mount.scrollIntoView({block:'nearest',behavior:'instant'});
  }

  function change(key,value) {
    if(!data)return;
    state[key]=value;
    const mount=document.getElementById(key==='query'||key==='filter'?'sne-names':'sne-results');
    if(mount)mount.innerHTML=key==='query'||key==='filter'?names():results();
  }
  function teaser(doc) {
    const d=doc?.net_edge_research;
    if(!d)return '';
    const c=d.cases.find(r=>r.id===d.primary_case);
    return `<aside class="rsp-teaser"><div><p class="rsp-kicker">Shorts backtest · RSI-2.0</p><h2>Conviction, costs and position size.</h2><p>${num(d.coverage.events,0)} priced events · evidence frozen at announcement · conditional research</p></div><dl><div><dt>Fundamental ratings</dt><dd>${num(d.coverage.numeric_conviction,0)}</dd></div><div><dt>Names passing net-edge sizing</dt><dd>${num(c?.trades,0)}</dd></div></dl><a class="rsp-action" href="#/strategies/systematic-shorts/backtest">Open shorts backtest <span aria-hidden="true">↗</span></a></aside>`;
  }
  global.ShortsNetEdgeViz={render,change,inspect,teaser};
})(window);
