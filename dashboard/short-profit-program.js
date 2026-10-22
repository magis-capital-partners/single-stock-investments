(function (global) {
  'use strict';
  const ROOT = 'data/short_profit_program/';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = v => v !== null && v !== undefined && Number.isFinite(Number(v));
  const cash = v => finite(v) ? `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString('en-US', {maximumFractionDigits:0})}` : '—';
  const num = v => finite(v) ? Number(v).toLocaleString('en-US', {maximumFractionDigits:0}) : '—';
  const pct = v => finite(v) ? `${(100 * v).toFixed(2)}%` : '—';
  const ratio = v => finite(v) ? Number(v).toFixed(2) : '—';
  const tone = v => v < 0 ? 'spp-negative' : v > 0 ? 'spp-positive' : '';
  const link = (url, label) => /^https:\/\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label);
  const metric = (label, value, hint = '', className = '') => `<div><dt>${esc(label)}</dt><dd class="${className}">${value}</dd><small>${esc(hint)}</small></div>`;
  let loading;
  const files = new Map();

  async function checked(file, expected) {
    if (!/^[\w.-]+$/.test(file)) throw new Error('Invalid research file');
    const response = await fetch(ROOT + file, {cache:'no-cache'});
    if (!response.ok) throw new Error(`Research file unavailable (${response.status})`);
    const text = await response.text();
    if (expected && global.crypto?.subtle) {
      const digest = await global.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
      const hash = Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('');
      if (hash !== expected) throw new Error('Research files are from different builds. Reload after publication finishes.');
    }
    return JSON.parse(text);
  }

  function getFile(part) {
    const key = part.file + '/' + part.sha256;
    if (!files.has(key)) files.set(key, checked(part.file, part.sha256).catch(error => { files.delete(key); throw error; }));
    return files.get(key);
  }

  function select(key, label, choices, value) {
    return `<label>${esc(label)}<select data-spp-control="${key}">${choices.map(([v,t]) => `<option value="${esc(v)}"${String(v) === String(value) ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  }

  function chart(points, {field = 1, label = '', bars = false, dollars = true, fan = false} = {}) {
    if (!points.length) return '<p class="spp-empty">No observations for this comparison.</p>';
    const w = 700, h = 220, L = 65, R = 16, T = 18, B = 32;
    const all = points.flatMap(p => fan ? p.slice(1,4) : [p[field]]).filter(finite);
    if (!all.length) return '<p class="spp-empty">No finite observations.</p>';
    let lo = Math.min(0, ...all), hi = Math.max(0, ...all); if (hi === lo) hi = lo + 1;
    const x = i => L + i / Math.max(1, points.length - 1) * (w - L - R);
    const y = v => T + (hi - v) / (hi - lo) * (h - T - B);
    const path = f => points.map((p,i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[f]).toFixed(1)}`).join(' ');
    const ticks = [0,.5,1].map(q => {const v = lo + (hi-lo)*q; return `<line x1="${L}" x2="${w-R}" y1="${y(v)}" y2="${y(v)}" class="spp-grid"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end">${esc(dollars ? cash(v) : pct(v))}</text>`;}).join('');
    let body;
    if (fan) {
      const upper = points.map((p,i) => `${x(i)},${y(p[3])}`).join(' '), lower = points.map((p,i) => `${x(i)},${y(p[1])}`).reverse().join(' ');
      body = `<polygon points="${upper} ${lower}" class="spp-band"/><path d="${path(2)}" class="spp-line"/>`;
    } else if (bars) {
      const width = Math.max(1, (w-L-R)/points.length * .75);
      body = points.map((p,i) => `<rect x="${x(i)-width/2}" y="${Math.min(y(0),y(p[field]))}" width="${width}" height="${Math.max(.8,Math.abs(y(p[field])-y(0)))}" class="${p[field]<0?'spp-loss-bar':'spp-gain-bar'}"/>`).join('');
    } else body = `<path d="${path(field)}" class="spp-line"/>`;
    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">${ticks}<line x1="${L}" x2="${w-R}" y1="${y(0)}" y2="${y(0)}" class="spp-zero"/>${body}<text x="${L}" y="${h-6}">${esc(points[0][0])}</text><text x="${w-R}" y="${h-6}" text-anchor="end">${esc(points.at(-1)[0])}</text></svg>`;
  }

  function resultTable(models, state) {
    const rows = models.filter(m => m.signal === state.signal && m.target === state.target && m.sizing === state.sizing && m.horizon === state.horizon && m.exit_policy === 'time');
    return `<div class="spp-scroll"><table><caption>Three joint execution and borrow assumptions</caption><thead><tr><th>Case</th><th>Annual net P&amp;L</th><th>Avg filled</th><th>Max drawdown</th><th>Entered / closed</th><th>Open liability</th></tr></thead><tbody>${rows.map(m => `<tr${m.case===state.case?' class="spp-selected"':''}><th scope="row">${esc(m.case)}</th><td class="${tone(m.annual_pnl)}">${cash(m.annual_pnl)}</td><td>${cash(m.mean_position)}</td><td>${cash(Math.abs(m.max_drawdown_dollars))}</td><td>${num(m.entered)} / ${num(m.modeled_closed)}</td><td>${cash(m.open_liability)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function observedGroups(doc) {
    const s=doc.study_aggregates;
    const row=(label,d)=>`<tr><th>${esc(label)}</th><td>${num(d?.n)}</td><td>${pct(d?.mean)}</td><td>${pct(d?.median)}</td><td>${pct(d?.p05)} / ${pct(d?.p95)}</td></tr>`;
    const table=(caption,body)=>`<div class="spp-scroll"><table><caption>${esc(caption)}</caption><thead><tr><th>Group / sessions</th><th>Observed paths</th><th>Mean</th><th>Median</th><th>5th / 95th percentile</th></tr></thead><tbody>${body}</tbody></table></div>`;
    return `<details class="spp-details"><summary>What actually happened to the stocks? Source-group statistics</summary><p>These are stock returns in the supplied studies. A negative stock return can favor a short, but these figures include no execution, borrow or capital constraints. Split returns start at the pre-split close; the strategy replay starts only after public availability and completion. They therefore answer different questions.</p>${table('Reverse splits · provider pre-split-close returns',Object.entries(s.split).map(([h,d])=>row(h+' sessions',d)).join(''))}${table('Listing notices · provider filing-window returns',Object.entries(s.deficiency).flatMap(([h,groups])=>Object.entries(groups).map(([kind,d])=>row(kind+' · '+h+' sessions',d))).join(''))}${table('Prior financing around reverse splits · unmatched descriptive groups',s.prior_financing.flatMap(d=>[row('Prior financing · '+d.horizon,d.yes),row('No prior financing · '+d.horizon,d.no)]).join(''))}<p>${esc(s.method)} Notice rows include repeated issuers and are not independent trades. Denominators change by horizon. These are descriptive comparisons, not matched causal estimates or a forecast of net short returns.</p></details>`;
  }

  function results(doc, state) {
    const m = doc.models.find(m => m.signal===state.signal && m.horizon===state.horizon && m.target===state.target && m.case===state.case && m.sizing===state.sizing && m.exit_policy==='time');
    if (!m) return '<p role="alert">This registered comparison is unavailable.</p>';
    const c = doc.cases.find(c => c.id === state.case);
    const controls = `${select('signal','Opportunity',doc.signals.map(s=>[s.id,s.label]),state.signal)}${select('horizon','Hold',[2,5,10,20].map(v=>[v,`${v} sessions`]),state.horizon)}${select('target','Target per company',[[25000,'$25,000'],[50000,'$50,000']],state.target)}${select('case','Joint cost case',doc.cases.map(c=>[c.id,c.label]),state.case)}`;
    const f=m.funnel||{}, mc=m.monte_carlo;
    const funnel = [['Selected events',f.selected_discoveries||0],['Price + liquidity',Math.max(0,(f.selected_discoveries||0)-(f.missing_price_or_liquidity||0))],['Modeled entries',m.entered],['Modeled fully covered',m.modeled_closed],['Observed fills',doc.evidence.observed_fills]];
    const holding = doc.models.filter(x=>x.signal===state.signal && x.target===state.target && x.case===state.case && x.sizing===state.sizing && x.exit_policy==='time');
    return `<div class="spp-controls">${controls}</div><div class="spp-mode">${select('sizing','Sizing rule',[['fixed','Fixed target, limited by liquidity'],['net_edge','Choose size by prior net edge']],state.sizing)}<p>Targets are ceilings. The $10m portfolio is hypothetical. ${esc(c.label)} borrow assumption: ${pct(c.borrow_apr)} a year; ${pct(c.ssr_capture)} restricted-flow capture. Replay: ${esc(m.start)} to ${esc(m.end)}; newer discoveries await prices.</p></div>
    <dl class="spp-metrics" aria-live="polite">${metric('Annual net P&L',cash(m.annual_pnl),'Historical marked total ÷ elapsed years',tone(m.annual_pnl))}${metric('Worst drawdown',cash(Math.abs(m.max_drawdown_dollars)),'Every session close; excludes unseen intraday losses')}${metric('Average filled short',cash(m.mean_position),`${cash(m.target)} target`)}${metric('Open short liability',cash(m.open_liability),`${num(m.unresolved_positions)} unfinished positions`)}${metric('Modeled trades per year',ratio(m.trades_per_year),`${num(m.distinct_issuers)} issuers`)}${metric('Observed broker fills',num(doc.evidence.observed_fills),'Modeled fills are separate')}</dl>
    <div class="spp-funnel" aria-label="Event-to-execution evidence funnel">${funnel.map(([label,value])=>`<div><strong>${num(value)}</strong><span>${esc(label)}</span></div>`).join('')}</div>
    <p class="spp-note"><strong>Conditional trading P&amp;L, before unverified charges and business overhead.</strong> Daily prices, 5% recorded-volume capacity, spreads, impact and borrowing are modeled. Locates, dividends and corporate-action cash need actual records. Uncompleted covers remain in marked P&amp;L. After a price gap longer than seven calendar days, later ticker prints require security-continuity evidence. ${m.entered ? `${num(m.overdue_cover_positions)} positions outlasted the intended exit; ${num(m.stale_mark_sessions)} sessions include stale liability marks.` : 'No entries pass this comparison. Reconciled supply tests require verified deal terms; net-edge sizing also needs enough earlier other-issuer outcomes.'}</p>
    <div class="spp-charts"><figure><figcaption>Cumulative net P&amp;L</figcaption>${chart(m.monthly,{field:2,label:'Monthly cumulative conditional net trading P&L'})}</figure><figure><figcaption>Monthly net P&amp;L</figcaption>${chart(m.monthly,{field:1,bars:true,label:'Monthly conditional net trading profit and loss'})}</figure></div>
    ${resultTable(doc.models,state)}
    <div class="spp-scroll"><table><caption>Does more holding time improve net dollars? Same size, case and rule.</caption><thead><tr><th>Sessions</th><th>Annual net P&amp;L</th><th>Max DD</th><th>Calmar</th><th>Win rate, closed</th><th>Unfinished</th></tr></thead><tbody>${holding.map(r=>`<tr${r.horizon===state.horizon?' class="spp-selected"':''}><th>${r.horizon}</th><td class="${tone(r.annual_pnl)}">${cash(r.annual_pnl)}</td><td>${cash(Math.abs(r.max_drawdown_dollars))}</td><td>${ratio(r.calmar)}</td><td>${pct(r.win_rate_closed)}</td><td>${num(r.unresolved_positions)}</td></tr>`).join('')}</tbody></table></div>
    <details class="spp-details"><summary>Risk, funding, costs and selection details</summary><dl class="spp-stats">${[['Added CAGR on $10m',pct(m.cagr)],['Max drawdown on $10m',pct(Math.abs(m.max_drawdown))],['Calmar',ratio(m.calmar)],['Sharpe / Sortino',`${ratio(m.sharpe)} / ${ratio(m.sortino)}`],['Annual volatility',pct(m.annual_volatility)],['Worst day',cash(m.worst_day)],['Daily 95% expected shortfall',cash(m.expected_shortfall_95_dollars)],['Worst marked trade',cash(m.worst_marked_trade)],['Worst issuer',cash(m.worst_issuer)],['Annual P&L excluding best issuer',cash(m.annual_pnl_ex_best_issuer)],['Profit factor, closed',ratio(m.profit_factor_closed)],['Losing months',pct(m.losing_month_fraction)],['Peak session-close margin estimate',cash(m.peak_margin)],['Peak trade-date collateral estimate',cash(m.peak_collateral)],['+200% squeeze loss',cash(m.squeeze_loss_200)],['Execution-cost drag',cash(m.totals.execution_cost)],['Commissions and fees',cash(m.totals.commissions_and_fees)],['Borrow charged',cash(m.totals.borrow_cost)],['Proceeds-interest credit',cash(m.totals.proceeds_interest)],['Repeated issuer entries skipped',num(f.overlapping_issuer||0)],['No prior net edge',num(f.no_prior_net_edge||0)],['Risk / liquidity skips',num(f.no_fill_or_risk_capacity||0)],['Fractional action liabilities',num(m.fractional_action_liabilities)],['Unresolved action records',num(m.unresolved_corporate_action_positions)],['Unresolved security continuity',num(m.unresolved_security_identity_positions)],['Unknown SSR entries',num(m.counts.ssr_unknown_entries||0)],['Median / 95th cover days',`${ratio(m.liquidation_calendar_days?.median)} / ${ratio(m.liquidation_calendar_days?.p95)}`],['95th extra cover days',ratio(m.late_cover_calendar_days?.p95)],['Longest drawdown, sessions',num(m.longest_drawdown_sessions)]].map(([a,b])=>metric(a,b)).join('')}</dl><p>Case labels describe assumptions; changing fill quantities can reverse the ordering of portfolio returns. Margin uses a 100% house sensitivity plus low-price floors, with a joint +200% loss reserve. Collateral is restricted funding, not an expense. Neither is an account-specific IBKR quote; intraday house calls and settlement funding can differ. Closed-trade statistics exclude unfinished trades; marked account P&amp;L includes them. Borrow and credit use current-rate sensitivities; regulatory fees use the dated schedule. Cash pressure means the last available reported cash covers at most one year of negative trailing operating cash flow.</p></details>
    ${mc?`<details class="spp-details"><summary>Five-year Monte Carlo · conditional historical blocks</summary><p>${num(mc.trials)} paths resample ${mc.block_sessions}-session calendar blocks. The shaded band is the 5th–95th percentile; the line is the median.</p>${chart(mc.fan,{fan:true,label:'Five-year conditional portfolio Monte Carlo fan in dollars'})}<dl class="spp-stats">${metric('Median annual net dollars',cash(mc.annual_net_dollars.p50))}${metric('5th / 95th annual dollars',`${cash(mc.annual_net_dollars.p05)} / ${cash(mc.annual_net_dollars.p95)}`)}${metric('Severe drawdown, 5th percentile',cash(Math.abs(mc.max_drawdown_dollars.p05)))}${metric('Five-year loss frequency',pct(mc.loss_probability))}${metric('Frequency ≥ $240k annual average',pct(mc.probability_annual_at_least_240k))}${metric('95th-percentile peak margin',cash(mc.peak_margin?.p95))}</dl><p>${esc(mc.limitations)}</p></details>`:''}
    <details class="spp-details"><summary>Stops and progressive covers · fixed five-session comparator</summary><p>Time exits are primary. This predeclared comparison uses a 20% stop / 20% target with adverse stop-first daily-bar ordering, or progressive covers starting before the deadline. Gaps and limited volume can prevent completion; a stop is an instruction, not a loss cap.</p><div class="spp-scroll"><table><thead><tr><th>Opportunity</th><th>Exit</th><th>Annual net P&amp;L</th><th>Max DD</th><th>Unfinished</th></tr></thead><tbody>${doc.models.filter(r=>r.target===state.target&&r.case===state.case&&r.sizing==='fixed'&&r.exit_policy!=='time').map(r=>`<tr><td>${esc(doc.signals.find(s=>s.id===r.signal)?.label||r.signal)}</td><td>${esc(r.exit_policy)}</td><td>${cash(r.annual_pnl)}</td><td>${cash(Math.abs(r.max_drawdown_dollars))}</td><td>${num(r.unresolved_positions)}</td></tr>`).join('')}</tbody></table></div></details>${observedGroups(doc)}`;
  }

  function execution(doc) {
    const repair=doc.patient_liability_replay;
    return `<h3>Can the short actually be closed?</h3><p>The older patient model priced unsupported cover shares as if they all filled at the last ask plus a surcharge. The corrected ledger keeps the short open. Compare the same entries below, before considering any increase in size. Funding statistics use session marks; intraday peaks and the live account need separate evidence.</p>
    ${repair?`<div class="spp-scroll"><table><caption>Patient-entry liability replay · 5% recorded flow</caption><thead><tr><th>Target / case</th><th>Old annual P&amp;L</th><th>Repaired annual marked P&amp;L</th><th>Open liability</th><th>Unfinished</th></tr></thead><tbody>${repair.models.map(r=>`<tr><th>${cash(r.target)} / ${esc(r.case)}</th><td>${cash(r.legacy_annual_pnl)}</td><td>${cash(r.annual_pnl)}</td><td>${cash(r.open_liability)}</td><td>${num(r.unresolved_positions)}</td></tr>`).join('')}</tbody></table></div><p>${esc(repair.method)}</p>`:'<p class="spp-note">The new daily replays retain residual liabilities. The separate intraday frozen-entry liability replay is not available in this build.</p>'}
    <h3>What do we know about costs?</h3><dl class="spp-stats">${metric('Quoted spread proxy, round trip',pct(doc.cost_evidence.quoted_spread_roundtrip),'Multi-venue samples; not verified NBBO')}${metric('Base static-book anchor at $25k',pct(doc.cost_evidence.base_roundtrip_25k),'Conditional both-side completion sample')}${metric('Observed execution fills',num(doc.evidence.observed_fills))}${metric('Verified-NBBO matched fills',num(doc.evidence.nbbo_matched_fills))}</dl><p>${esc(doc.cost_evidence.basis)}</p><p>${esc(doc.cost_evidence.borrow_basis)} ${esc(doc.cost_evidence.proceeds_interest_basis)}</p><p>${esc(doc.cost_evidence.other_fee_allowance)}</p>
    <p>Import actual order, quote, fill, borrow and cash-flow files to calibrate implementation shortfall. The collector never connects to a brokerage account. A quote is not a fill, public borrow is not an approved locate, and an absent exit is not a zero-price cover.</p><details class="spp-details"><summary>Cost sources and frozen assumptions</summary><ul>${doc.cost_evidence.sources.map(url=>`<li>${link(url,new URL(url).hostname+' · '+new URL(url).pathname.split('/').at(-1))}</li>`).join('')}</ul><pre>${esc(JSON.stringify(doc.protocol.protocol,null,2))}</pre></details>`;
  }

  function evidence(doc) {
    return `<h3>What is complete, and what still needs evidence?</h3><div class="spp-stages">${doc.stages.map(s=>`<article><div><h4>${esc(s.label)}</h4><span>${esc(s.status.replaceAll('_',' '))}</span></div><p>${esc(s.detail)}</p></article>`).join('')}</div><p>The review panel was selected by event hashes within event-type strata, without using subsequent returns. A source passage is a lead; it does not verify all financing terms or a tradable thesis.</p><button type="button" data-spp-review>Open the 100-event review panel</button><div data-spp-review-body></div><details class="spp-details"><summary>Corporate-action reconciliation</summary><p>${esc(doc.corporate_actions.priority)}</p><p>${num(doc.corporate_actions.automatically_corroborated_primary_repairs)} primary-clause reconciliations; ${num(doc.corporate_actions.verified_catalogue_actions)} verified catalogue rows; ${num(doc.corporate_actions.explicit_vendor_actions)} explicit vendor action rows. These are mechanical share adjustments, not financing approvals.</p><button type="button" data-spp-actions>Inspect the repaired action sources</button><div data-spp-actions-body></div></details><details class="spp-details"><summary>Literature and audit corrections</summary><button type="button" data-spp-literature>Load the 187-item source ledger</button><div data-spp-literature-body></div><p><a href="${ROOT}audit-2026-10-21.pdf" target="_blank" rel="noopener">Read the original 52-page audit and plan</a></p></details><details class="spp-details"><summary>Coverage limits and source proof</summary><ul>${doc.limitations.map(t=>`<li>${esc(t)}</li>`).join('')}</ul><p>Dataset version: <code>${esc(doc.dataset_version)}</code>. Each shard is checked against its recorded SHA-256 when supported by the browser.</p><ul>${doc.sources.map(s=>`<li>${link(s.url,s.label)}</li>`).join('')}</ul><pre>${esc(JSON.stringify({sources:doc.source_manifest,public_collection:doc.public_discovery},null,2))}</pre></details>`;
  }

  function render() { return '<section class="spp" data-short-profit-program><p role="status">Loading the short-strategy dataset…</p></section>'; }

  function mount(host,doc) {
    let state={...doc.defaults,tab:'results',family:'financing',year:Math.max(...doc.parts.map(p=>Number(p.year))).toString(),query:'',page:0};
    let request=0, loaded=[];
    const count = Object.values(doc.counts).reduce((a,b)=>a+b,0);
    const tabs=[['results','Results'],['dataset','Dataset'],['execution','Execution'],['evidence','Evidence']];
    function paint() {
      request++;
      host.innerHTML=`<header class="spp-header"><div><p class="spp-eyebrow">Short alpha · strategy lab</p><h2>Find the edge. Count the costs.</h2><p>${num(count)} source records across ${num(doc.issuers)} issuers. Financing, listing stress and reverse splits in one research dataset.</p></div><span class="spp-status">Research · no trading authority</span></header><nav class="spp-tabs" aria-label="Short strategy lab">${tabs.map(([id,label])=>`<button type="button" data-spp-tab="${id}" aria-pressed="${state.tab===id}">${label}</button>`).join('')}</nav><div data-spp-body>${state.tab==='results'?results(doc,state):state.tab==='execution'?execution(doc):state.tab==='evidence'?evidence(doc):datasetShell()}</div><p class="spp-footnote">Built ${esc(doc.built_at.slice(0,10))} · All registered settings retained · ${num(doc.evidence.observed_fills)} observed fills · $0 new paid downloads</p>`;
      if(state.tab==='dataset')loadDataset();
    }
    function datasetShell() {
      return `<h3>Trace every event to its source</h3><p>Display names and symbols may reflect current provider mappings. Original filing links, clocks and coverage are shown for review. These records are discoveries, not approved trades.</p><div class="spp-controls">${select('family','Event type',[['all','All types'],['financing','Financing'],['deficiency','Listing deficiency'],['split','Reverse split']],state.family)}${select('year','Year',[['all','All years'],...Array.from(new Set(doc.parts.map(p=>p.year))).sort().reverse().map(y=>[y,y])],state.year)}<label>Search these records<input type="search" data-spp-query placeholder="Ticker, company, CIK or term" value="${esc(state.query)}"></label></div><p data-spp-dataset-status role="status">Loading source records…</p><div data-spp-dataset-rows></div><div class="spp-pagination"><button type="button" data-spp-prev>Previous</button><button type="button" data-spp-next>Next</button><button type="button" data-spp-export>Download these records as JSON</button></div><div data-spp-event-detail></div>`;
    }
    async function loadDataset() {
      const token=++request;
      try {
        const parts=doc.parts.filter(p=>(state.family==='all'||p.family===state.family)&&(state.year==='all'||p.year===state.year));
        const docs=await Promise.all(parts.map(getFile));
        if(token!==request||!host.isConnected)return;
        if(docs.some(d=>d.dataset_version!==doc.dataset_version))throw new Error('Source records do not match this dataset version.');
        loaded=docs.flatMap(d=>d.events).sort((a,b)=>b.event_date.localeCompare(a.event_date));paintRows();
      }catch(error){const target=host.querySelector('[data-spp-dataset-status]');if(target&&token===request)target.textContent=error.message;}
    }
    function filtered() { const q=state.query.trim().toLowerCase();return loaded.filter(e=>!q||[e.ticker,e.name,e.cik,e.event_status,...(e.features?.financing_types||[])].join(' ').toLowerCase().includes(q)); }
    function paintRows() {
      const target=host.querySelector('[data-spp-dataset-rows]');if(!target)return;
      const rows=filtered(), pages=Math.max(1,Math.ceil(rows.length/40));state.page=Math.min(state.page,pages-1);
      host.querySelector('[data-spp-dataset-status]').textContent=`${num(rows.length)} records · page ${state.page+1} of ${pages}`;
      target.innerHTML=`<div class="spp-scroll"><table><thead><tr><th>Company</th><th>Event / public clock</th><th>Type and status</th><th>Cash runway</th><th>Price coverage</th><th>Evidence</th></tr></thead><tbody>${rows.slice(state.page*40,state.page*40+40).map(e=>`<tr><th>${esc(e.ticker||'CIK '+e.cik)}<small>${esc(e.name)}</small></th><td>${esc(e.event_date)}<small>${esc((e.known_at||'Unknown').slice(0,19))}</small></td><td>${esc(e.family)}<small>${esc(e.event_status.replaceAll('_',' '))}</small></td><td>${finite(e.financials?.runway_years)?`${ratio(e.financials.runway_years)} years`:'Unknown'}</td><td>${e.price_coverage?.status==='ready_for_conditional_daily_replay'?'Daily proxy available':'Incomplete'}</td><td><button type="button" data-spp-event="${esc(e.id)}">Inspect</button></td></tr>`).join('')||'<tr><td colspan="6">No matching records.</td></tr>'}</tbody></table></div>`;
      host.querySelector('[data-spp-prev]').disabled=state.page===0;host.querySelector('[data-spp-next]').disabled=state.page>=pages-1;
    }
    host.addEventListener('change',event=>{
      const el=event.target.closest('[data-spp-control]');if(!el)return;
      const key=el.dataset.sppControl;state[key]=['horizon','target'].includes(key)?Number(el.value):el.value;state.page=0;paint();
      host.querySelector(`[data-spp-control="${key}"]`)?.focus();
    });
    host.addEventListener('input',event=>{if(event.target.matches('[data-spp-query]')){state.query=event.target.value;state.page=0;paintRows();}});
    host.addEventListener('click',async event=>{
      const tab=event.target.closest('[data-spp-tab]');if(tab){state.tab=tab.dataset.sppTab;paint();return;}
      if(event.target.closest('[data-spp-prev]')){state.page--;paintRows();}
      if(event.target.closest('[data-spp-next]')){state.page++;paintRows();}
      const entry=event.target.closest('[data-spp-event]');
      if(entry){const e=loaded.find(e=>e.id===entry.dataset.sppEvent);host.querySelector('[data-spp-event-detail]').innerHTML=`<article class="spp-event"><h3>${esc(e.ticker)} · ${esc(e.event_date)}</h3><p>${link(e.source_url,'Open original filing')} · ${esc(e.source_locator)}</p><p>${esc(e.clock_basis)} · ${esc(e.review_status)}</p>${(e.passages||[]).map(p=>`<blockquote>${esc(p.excerpt)}</blockquote><small>${esc(p.locator)}</small>`).join('')}<details><summary>All event fields</summary><pre>${esc(JSON.stringify(e,null,2))}</pre></details></article>`;}
      const exportButton=event.target.closest('[data-spp-export]');
      if(exportButton){const blob=new Blob([JSON.stringify({dataset_version:doc.dataset_version,events:filtered()},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='short-alpha-events.json';a.click();URL.revokeObjectURL(url);}
      const review=event.target.closest('[data-spp-review]'), literature=event.target.closest('[data-spp-literature]');
      if(event.target.closest('[data-spp-actions]')){
        const target=host.querySelector('[data-spp-actions-body]');
        try{const data=await getFile(doc.files.find(f=>f.file==='corporate-actions.json'));if(!target.isConnected)return;target.innerHTML=`<div class="spp-scroll"><table><thead><tr><th>Action</th><th>Primary source</th><th>Source clause</th></tr></thead><tbody>${data.rows.map(r=>`<tr><th>${esc(r.ticker)}<small>${esc(r.ex_date)} · ${ratio(r.price_factor)} price factor</small></th><td>${link(r.source_url,'Original filing')}<small>${esc(r.verification.replaceAll('_',' '))}</small></td><td><small>${esc(r.clause)}</small></td></tr>`).join('')}</tbody></table></div>`;}catch(error){if(target.isConnected)target.textContent=error.message;}
      }
      if(review||literature){
        const kind=review?'review-queue.json':'literature.json', part=doc.files.find(f=>f.file===kind);const target=host.querySelector(review?'[data-spp-review-body]':'[data-spp-literature-body]');
        try {const data=await getFile(part);if(!target.isConnected)return;target.innerHTML=`<div class="spp-scroll"><table><thead><tr><th>${review?'Event':'Source'}</th><th>Evidence</th><th>Status / audit note</th></tr></thead><tbody>${data.rows.map(r=>review?`<tr><th>${esc(r.ticker)}<small>${esc(r.date)}</small></th><td>${link(r.source_url,'Original filing')}<small>${esc(r.locator)}</small></td><td>${esc(r.status.replaceAll('_',' '))}</td></tr>`:`<tr><th>${esc(r.id)}<small>${esc(r.year)}</small></th><td>${link(r.url,r.title)}<small>${esc(r.authors)}</small></td><td>${r.available_in_supplied_pack?'Supplied':'Catalog only'}${r.audit_note?`<small>${esc(r.audit_note)}</small>`:''}</td></tr>`).join('')}</tbody></table></div>`;}catch(error){if(target.isConnected)target.textContent=error.message;}
      }
    });
    paint();
  }

  async function attach(container) {
    const host=container.querySelector('[data-short-profit-program]');if(!host||host.dataset.mounted)return;host.dataset.mounted='true';
    try {
      loading ||= checked('manifest.json').then(async manifest=>{const doc=await checked('summary.json',manifest.summary_sha256);if(doc.schema_version!=='short_profit_program.v1'||doc.dataset_version!==manifest.dataset_version)throw new Error('Unsupported or mixed strategy dataset');doc.files=manifest.files;return doc;}).catch(error=>{loading=null;throw error;});
      const doc=await loading;if(host.isConnected)mount(host,doc);
    } catch(error){if(host.isConnected)host.innerHTML=`<p role="alert">Short strategy research is unavailable: ${esc(error.message)} Reload to retry.</p>`;}
  }
  const api={render,attach,mount,results,chart,esc,checked};
  global.ShortProfitProgram=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
