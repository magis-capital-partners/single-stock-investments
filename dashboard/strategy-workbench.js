/* Dedicated research strategies. Data stays in its existing versioned publications. */
(function (global) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = value => Number.isFinite(Number(value)) && value !== null && value !== '' ? new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(Number(value)) : 'Unknown';
  const pct = value => typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('en-US', {style:'percent', maximumFractionDigits:1}).format(value) : 'Awaiting evidence';
  const date = value => value && !Number.isNaN(Date.parse(value)) ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(String(value).length===10 ? value+'T12:00:00Z' : value)) : 'Undated';
  const BIO = 'biotech-quant', SHORT = 'systematic-shorts';
  const sections = {
    [BIO]: [['overview','Overview'],['signals','Signals'],['portfolio','Portfolio'],['backtest','Backtest'],['risk','Risk & data'],['research','Research']],
    [SHORT]: [['overview','Overview'],['signals','Signals'],['backtest','Backtest'],['portfolio','Portfolio & risk'],['forward','Forward paper'],['research','Research & data']],
  };
  const cache = new Map();
  const requests = new WeakMap();
  async function json(path) {
    if (!cache.has(path)) cache.set(path, global.fetch(path, {cache:'no-cache'}).then(r => {
      if (!r.ok) throw Error(`Publication unavailable (${r.status})`);
      return r.json();
    }).then(doc => { if (doc.private_snapshot) throw Error('The authorized publication is unavailable in this preview.'); return doc; }).catch(error => {cache.delete(path);throw error;}));
    return cache.get(path);
  }
  function parseRoute(hash) {
    const [path, query=''] = String(hash || '').split('?');
    const legacy = /^#\/ideas\/short-alpha\/(backtest|announcement|forward)$/i.exec(path);
    const oldBio = /^#\/insights\/memory\/biotech$/i.test(path) || (path==='#/insights/memory' && new URLSearchParams(query).get('memory')==='biotech');
    const hit = /^#\/strategies\/(systematic-shorts|biotech-quant)(?:\/(overview|signals|portfolio|backtest|risk|forward|research|announcement))?$/i.exec(path);
    if (!hit && !legacy && !oldBio) return null;
    const kind = hit ? hit[1].toLowerCase() : legacy ? SHORT : BIO;
    const section = hit ? (hit[2] || 'overview').toLowerCase() : legacy ? legacy[1].toLowerCase() : 'overview';
    const valid = sections[kind].some(([id])=>id===section) || (kind===SHORT && section==='announcement');
    if (!valid) return null;
    return {view:kind, strategySection:section, query, ticker:null, watchlistSub:null, canonical:Boolean(legacy || oldBio)};
  }
  function stateFromHash(hash) {
    const route = parseRoute(hash);
    const params = new URLSearchParams(String(hash || '').split('?')[1] || '');
    return {kind:route?.view || BIO, section:route?.strategySection || 'overview', query:params.get('q')||'',
      scope:params.get('scope')||'universe', direction:params.get('direction')||'all',
      size:params.get('size')||'all', flag:params.get('flag')||'all',
      page:Math.max(0,Number(params.get('page'))||0), ticker:params.get('ticker')||''};
  }
  function route(kind, section, params={}) {
    const normalized={...params}; if ('query' in normalized) { normalized.q=normalized.query; delete normalized.query; } delete normalized.kind; delete normalized.section;
    const query = new URLSearchParams(Object.entries(normalized).filter(([,v])=>v!=='' && v!==null && v!==undefined && v!==0));
    return `#/strategies/${kind}/${section}${query.size ? '?'+query : ''}`;
  }
  function table(headers, rows, label) {
    return `<div class="strategy-table-scroll" tabindex="0" aria-label="${esc(label)}"><table class="strategy-table"><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows || `<tr><td colspan="${headers.length}">No records in this publication.</td></tr>`}</tbody></table></div>`;
  }
  function disclosure(title, body, open=false) { return `<details class="strategy-disclosure"${open?' open':''}><summary>${esc(title)}</summary>${body}</details>`; }
  function empty(text) { return `<div class="strategy-empty" role="status">${esc(text)}</div>`; }
  function header(kind, section, asOf) {
    const name = kind===BIO ? 'Biotech Quant' : 'Systematic Shorts';
    return `<header class="strategy-header"><div><p class="strategy-eyebrow">Strategies / ${kind===BIO?'Sector factors':'Rules and evidence'}</p><h1>${name}</h1><p>${kind===BIO?'Specialist ownership, spend value, and a portfolio built from dated evidence.':'Quantitative short selection, historical studies, and independent forward observations.'}</p></div><div class="strategy-publication"><span class="strategy-status">Research & paper</span>${asOf?`<span>Published ${date(asOf)}</span>`:''}</div></header><nav class="strategy-tabs" aria-label="${name}">${sections[kind].map(([id,label])=>`<a href="${route(kind,id)}"${section===id?' aria-current="page"':''}>${label}</a>`).join('')}</nav>`;
  }
  function sourceLink(item) {
    const ref = item.ref || item.path || '';
    const url = /^https:\/\//.test(ref) ? ref : `https://github.com/magis-capital-partners/single-stock-investments/blob/main/${ref.split('/').map(encodeURIComponent).join('/')}`;
    return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(item.title || item.label || 'Open source')} ↗</a>`;
  }
  function factorTable(doc) {
    return table(['Factor','Role','Coverage','Observation','State'], (doc.coverage||[]).map(c=>`<tr><th scope="row">${esc(c.label)}</th><td>${esc(c.role)}</td><td>${num(c.populated)} / ${num(c.universe)}<small>${num(c.zeros)} recorded zero values</small></td><td>${date(c.observed_at)}<small>Built ${date(c.built_at)}</small></td><td><span class="strategy-state ${c.status==='current'?'':'is-pending'}">${esc(c.status)}</span></td></tr>`).join(''), 'Factor coverage and observation dates');
  }
  function bioOverview(doc) {
    const s=doc.summary||{}, history=doc.history||{};
    return `<div class="strategy-overview"><section class="strategy-thesis"><p class="strategy-eyebrow">The hypothesis</p><h2>Do specialists and spend value improve biotech selection?</h2><p>${esc(doc.protocol?.hypothesis || '')}</p><p>Begin with a diversified ownership-and-value baseline. Test insider buying and clinical peers as separate additions.</p><a class="strategy-primary" href="${route(BIO,'signals')}">Explore ${num(s.scored)} scored companies →</a></section><aside class="strategy-readiness"><h2>Evidence to build next</h2><dl><div><dt>Ownership history</dt><dd>${num(history.dated_quarters)} dated quarters</dd></div><div><dt>Current universe</dt><dd>${num(s.universe)} issuers · ${esc(s.quarter || 'quarter unavailable')}</dd></div><div><dt>Independent forward outcomes</dt><dd>${num(s.independent_forward_outcomes)}</dd></div></dl><a href="${route(BIO,'risk')}">Inspect coverage and missing inputs →</a></aside></div><section class="strategy-section"><h2>Factor readiness</h2>${factorTable(doc)}</section>${disclosure('Research limits and next evidence', `<ul>${(doc.warnings||[]).map(w=>`<li>${esc(w)}</li>`).join('')}</ul>`)}`;
  }
  function bioFiltered(doc, state) {
    const q=state.query.trim().toLowerCase();
    return (doc.signals||[]).filter(r=> (state.flag==='identity' ? r.eligible===false : r.eligible!==false) && (!q || `${r.ticker} ${r.company||r.issuer||''}`.toLowerCase().includes(q))
      && (state.scope!=='book' || r.in_book)
      && (state.size==='all' || r.issuer_size_bucket===state.size)
      && (state.flag!=='convergence' || r.convergence_flag)
      && (state.flag!=='initiation' || r.initiation_signal)
      && (state.flag!=='coverage' || (r.missing_required||[]).length)
      && (state.direction!=='short' || (r.short_candidate_score||0)>0)
      && (state.direction!=='long' || r.strategy_score>=70));
  }
  function select(label, key, value, options) {
    return `<label>${esc(label)}<select data-strategy-filter="${key}">${options.map(([id,name])=>`<option value="${esc(id)}"${value===id?' selected':''}>${esc(name)}</option>`).join('')}</select></label>`;
  }
  function bioSignals(doc, state) {
    const rows=bioFiltered(doc,state), pages=Math.max(1,Math.ceil(rows.length/40)), page=Math.min(state.page,pages-1), visible=rows.slice(page*40,(page+1)*40);
    const chosen=(doc.signals||[]).find(r=>r.ticker===state.ticker);
    return `<form class="strategy-toolbar" data-strategy-filters><label class="strategy-search">Company<input type="search" name="q" value="${esc(state.query)}" placeholder="Ticker or company…" autocomplete="off" spellcheck="false"></label>${select('Scope','scope',state.scope,[['universe','Full universe'],['book','In our book']])}${select('Candidates','direction',state.direction,[['all','All candidates'],['long','Higher-ranked longs'],['short','Short research candidates']])}<button type="submit">Search</button><a href="${route(BIO,'signals')}">Reset</a><details><summary>More filters</summary>${select('Issuer size','size',state.size,[['all','All sizes'],['small','Small'],['mid','Mid'],['large','Large'],['unknown','Unknown']])}${select('Flag','flag',state.flag,[['all','All flags'],['convergence','Convergence'],['initiation','Initiation'],['coverage','Missing required inputs'],['identity','Excluded identities and scope']])}</details></form><p class="strategy-result-count" role="status">${num(rows.length)} matching companies · showing ${num(visible.length)} · page ${page+1} of ${pages}. Scores range from 0–100; input dates still require verification. ${num(doc.summary?.excluded_for_review)} identities or out-of-scope issuers are excluded from ranking.</p>${table(['Company','Baseline score','Specialists','Spend value','Why review'],visible.map(r=>`<tr${r.ticker===state.ticker?' class="is-selected"':''}><th scope="row"><a href="${route(BIO,'signals',{...state,kind:undefined,section:undefined,ticker:r.ticker,page})}">${esc(r.ticker)}</a><small>${esc(r.company||r.issuer||'')}</small></th><td>${num(r.strategy_score)}<small>${esc((r.missing_required||[]).join(', '))}</small></td><td>${num(r.specialist_holder_count)}<small>${r.holder_count_qoq!=null?'Change '+num(r.holder_count_qoq):''}</small></td><td>${num(r.spend_value)}<small>market cap / cumulative spend</small></td><td>${esc([r.convergence_flag?'Convergence':'',r.initiation_signal?'New specialist interest':'',r.exit_signal?'Specialist exit':''].filter(Boolean).join(' · ')||'Ranked research candidate')}</td></tr>${r.ticker===state.ticker?`<tr><td colspan="5">${bioCompanyDetail(r,doc)}</td></tr>`:''}`).join(''),'Ranked biotech research candidates')}<nav class="strategy-pagination" aria-label="Biotech results pages">${page>0?`<a href="${route(BIO,'signals',{...state,kind:undefined,section:undefined,page:page-1})}">← Previous</a>`:'<span>Previous</span>'}${page+1<pages?`<a href="${route(BIO,'signals',{...state,kind:undefined,section:undefined,page:page+1})}">Next →</a>`:'<span>Next</span>'}<button type="button" data-strategy-export>Download filtered signals</button></nav>${chosen?'':'<p class="strategy-note">Select a company for its factor breakdown and linked company research.</p>'}`;
  }
  function bioCompanyDetail(row, doc) {
    return `<section class="strategy-company"><h3>${esc(row.ticker)} · factor evidence</h3><dl>${Object.entries(row.factor_ranks||{}).map(([k,v])=>`<div><dt>${esc(k.replaceAll('_',' '))}</dt><dd>${num(v)}</dd></div>`).join('')}<div><dt>Insider score</dt><dd>${num(row.insider_score)}</dd></div><div><dt>Clinical peer momentum</dt><dd>${num(row.peer_momentum_12m)}</dd></div><div><dt>Short interest</dt><dd>${num(row.short_interest_pct)}</dd></div></dl><p>${esc((row.review_reasons||[]).join(' · '))}</p><a href="#/research/coverage/${encodeURIComponent(row.ticker)}?section=evidence">Open shared company evidence →</a><details><summary>All recorded factor inputs</summary><pre>${esc(JSON.stringify(row,null,2))}</pre></details></section>`;
  }
  function bioPortfolio(doc) {
    const p=doc.paper||{}, legacy=doc.legacy_paper||{};
    const history=doc.paper_history||[];
    return `<section class="strategy-section"><h2>Forward paper portfolio</h2><p>Model capital: ${num(p.initial_capital)} USD · hypothetical · ${esc(p.status?.replaceAll('_',' ')||'Awaiting a dated rebalance')}</p><p>Target weights become paper positions only after the input and fill rules pass. Current cash weight: ${pct(p.cash_weight)}.</p>${table(['Company','Shares','Mark date','Mark'],(p.positions||[]).map(r=>`<tr><th scope="row">${esc(r.ticker)}</th><td>${num(r.shares)}</td><td>${date(r.mark_date)}</td><td>${num(r.mark)}</td></tr>`).join(''),'Current paper positions')}<p>Cash: ${num(p.cash)} USD · Account value: ${num(p.nav)} USD · Net return: ${pct(p.total_return)}</p>${disclosure('Rebalance changes',table(['Company','Share change','Notional','State'],(p.orders||[]).map(r=>`<tr><th scope="row">${esc(r.ticker)}</th><td>${num(r.shares_change)}</td><td>${num(r.notional)}</td><td>${esc(r.status)}</td></tr>`).join(''),'Simulated paper orders'))}${table(['Date','State','Orders','Independent outcomes'],history.map(r=>`<tr><th scope="row">${date(r.as_of)}</th><td>${esc(r.status?.replaceAll('_',' '))}</td><td>${num((r.orders||[]).length)}</td><td>${num(r.independent_outcomes)}</td></tr>`).join(''),'Paper portfolio history')}${disclosure('Abstentions and missing evidence',table(['Company','Reason'],(p.abstentions||[]).map(r=>`<tr><th scope="row">${esc(r.ticker)}</th><td>${esc(r.reason.replaceAll('_',' '))}</td></tr>`).join(''),'Paper abstentions'))}</section>${disclosure(`Earlier candidate list · ${date(legacy.as_of)}`,`<p>Preserved research selection. This list contains no verified fills or return history.</p>${table(['Side','Company','Recorded score'],['long','short'].flatMap(side=>(legacy[side]||[]).map(r=>`<tr><td>${side}</td><th scope="row">${esc(r.ticker)}</th><td>${num(r.composite_score??r.short_candidate_score)}</td></tr>`)).join(''),'Earlier paper candidates')}`)}${disclosure('Portfolio construction and rebalance protocol',`<pre>${esc(JSON.stringify(doc.protocol,null,2))}</pre>`)}`;
  }
  function bioBacktest(doc) {
    const b=doc.backtest||{}, variants=b.variants||[];
    return `<section class="strategy-section"><h2>Compare selection, hedging, and individual shorts</h2><p>${esc(b.status==='awaiting_dated_inputs'?'No performance is published until dated features and total-return marks are supplied.':`Exploratory observations ${date(b.first_date)}–${date(b.last_date)}. These dates are not an untouched holdout.`)}</p>${table(['Portfolio','Evidence','Net return','Maximum drawdown','Observations'],variants.map(v=>`<tr><th scope="row">${esc(v.id.replaceAll('_',' '))}</th><td>${esc(v.metrics?.status?.replaceAll('_',' '))}</td><td>${pct(v.metrics?.total_return)}</td><td>${pct(v.metrics?.max_drawdown)}</td><td>${num(v.metrics?.observations)}</td></tr>`).join(''),'Biotech portfolio comparisons')}<h3>Registered experiments</h3>${table(['Experiment','State'],(doc.experiments||[]).map(r=>`<tr><th scope="row">${esc(r.label)}</th><td>${esc(r.status.replaceAll('_',' '))}</td></tr>`).join(''),'Registered biotech hypotheses')}<p class="strategy-note">${num(b.variants_registered)} registered comparisons · ${num(b.variants_tested)} tested · protocol ${esc(b.protocol_id||'unavailable')} · independent validation ${esc(b.validation?.status||'pending')}</p></section>${disclosure('Costs, turnover, and tail losses',table(['Portfolio','CAGR','Volatility','Sharpe','Worst session','Turnover','Cost fractions'],variants.map(v=>`<tr><th scope="row">${esc(v.id.replaceAll('_',' '))}</th><td>${pct(v.metrics?.cagr)}</td><td>${pct(v.metrics?.volatility)}</td><td>${num(v.metrics?.sharpe)}</td><td>${pct(v.metrics?.worst_session)}</td><td>${num(v.metrics?.turnover)}</td><td>${pct(v.metrics?.cost_fraction_sum)}</td></tr>`).join(''),'Performance and friction detail')+'<p>Cost fractions and turnover are summed session fractions. Historical dates remain exploratory.</p>')}${disclosure('Cost sensitivity',table(['One-way cost','Long-only net return','Evidence'],(b.cost_sensitivity||[]).map(r=>`<tr><th scope="row">${num(r.one_way_bps)} bps</th><td>${pct(r.long_only_metrics?.total_return)}</td><td>${esc(r.long_only_metrics?.status)}</td></tr>`).join(''),'Predeclared cost sensitivity'))}${disclosure('Full dated account comparisons',`<pre>${esc(JSON.stringify(b.variants||[],null,2))}</pre>`)}${disclosure('Reproducible run and cost assumptions',`<pre>${esc(JSON.stringify({protocol_sha256:doc.protocol_sha256,costs:doc.protocol?.costs,inputs:doc.input_manifest,run:doc.run_manifest},null,2))}</pre>`)}`;
  }
  function bioRisk(doc) {
    return `<section class="strategy-section"><h2>Input coverage and portfolio constraints</h2>${factorTable(doc)}<h3>Paper portfolio risk</h3><p>Gross exposure: ${pct(doc.risk?.gross_exposure)} · Net exposure: ${pct(doc.risk?.net_exposure)} · Largest name: ${pct(doc.risk?.largest_name)} · Combined tail stress: ${pct(doc.risk?.combined_tail_stress)}</p><p>Stress assumes 70% long losses and 300% short price increases. State: ${esc(doc.risk?.status?.replaceAll('_',' ')||'Awaiting inputs')}.</p>${table(['Company','Weight','Days to exit at 1% ADV','Cash runway months','Missing evidence'],(doc.risk?.positions||[]).map(r=>`<tr><th scope="row">${esc(r.ticker)}</th><td>${pct(r.weight)}</td><td>${num(r.days_to_exit_at_one_percent_adv)}</td><td>${num(r.cash_runway_months)}</td><td>${esc(r.missing.join(', '))}</td></tr>`).join(''),'Risk and capacity evidence')}<ul class="strategy-warning-list">${(doc.warnings||[]).map(w=>`<li>${esc(w)}</li>`).join('')}</ul><h3>Historical ownership coverage</h3>${table(['Quarter','Fund filings'],Object.entries(doc.history?.quarters||{}).map(([q,n])=>`<tr><th scope="row">${esc(q)}</th><td>${num(n)}</td></tr>`).join(''),'Dated ownership history')}<p>${num(doc.history?.broader_book_files)} broader full-book files available for mapping and timestamp audit.</p><h3>Risk evidence required before a position</h3><p>Verify security identity, liquidity and participation, cash runway, clinical-catalyst concentration, financing needs, and source dates. Stock shorts also require dated borrow cost and availability, recall scenarios, and squeeze-loss limits.</p></section>`;
  }
  function bioResearch(doc) {
    return `<section class="strategy-section"><h2>Research library</h2><ul class="strategy-library">${(doc.library||doc.research||[]).map(r=>`<li>${sourceLink(r)}</li>`).join('')}</ul><p>Research findings define hypotheses. Strategy results come from the registered tests and paper ledger.</p></section>${disclosure('Methodology claims',`<ul>${(doc.methodology_claims||[]).map(c=>`<li>${esc(c.claim)} ${sourceLink({...c,label:'Source'})}</li>`).join('')}</ul>`)}${disclosure('Factor definitions and original specification',`<pre>${esc(JSON.stringify(doc.factor_specification||{},null,2))}</pre>`)}${disclosure('Specialist fund registry',table(['Fund','Specialty','Role','Notes'],(doc.funds||[]).map(f=>`<tr><th scope="row">${esc(f.fund||f.name)}</th><td>${esc(f.specialty||'biotech')}</td><td>${esc(f.signal_role||'specialist')}</td><td>${esc(f.notes||'')}</td></tr>`).join(''),'Specialist fund registry'))}${disclosure('Knowledge changes since the prior snapshot',`<pre>${esc(JSON.stringify(doc.knowledge_delta||{},null,2))}</pre>`)}${disclosure('Factor specification and methodology',`<pre>${esc(JSON.stringify(doc.protocol,null,2))}</pre>`)}${disclosure('Source publication coverage',table(['Fund','Quarter','Available','Reconciled'],(doc.history?.filings||[]).map(f=>`<tr><th scope="row">${esc(f.fund)}</th><td>${esc(f.quarter)}</td><td>${date(f.known_at)}</td><td>${f.complete?'Yes':'Review required'}</td></tr>`).join(''),'Historical source publication clocks'))}`;
  }
  function renderBio(doc, state) {
    const views={overview:bioOverview,signals:bioSignals,portfolio:bioPortfolio,backtest:bioBacktest,risk:bioRisk,research:bioResearch};
    return header(BIO,state.section,doc.as_of) + (views[state.section]||bioOverview)(doc,state);
  }
  function shortBacktest() {
    return `<div class="strategy-study-links"><a href="${route(SHORT,'announcement')}">Compare announcement-time entries →</a><a href="${route(SHORT,'forward')}">Follow frozen forward policies →</a></div>${global.ThirdPlusStudyViz?.render() || empty('The current short-study renderer is unavailable.')}<details class="strategy-disclosure" data-third-plus-legacy><summary>Earlier portfolio, execution, and event studies</summary><section data-short-reverse-splits><p data-short-reverse-status role="status">Open this section to load the preserved studies.</p><div data-short-reverse-splits-body></div></section></details>`;
  }
  function shortOverview(summary, forward) {
    return `<div class="strategy-overview"><section class="strategy-thesis"><p class="strategy-eyebrow">From selection to net results</p><h2>Which short rules survive costs and portfolio risk?</h2><p>Compare financing, listing stress, reverse splits, and the announcement-time studies. Every version keeps its own universe, entry clock, execution assumptions, and unresolved liabilities.</p><a class="strategy-primary" href="${route(SHORT,'backtest')}">Explore the backtests →</a></section><aside class="strategy-readiness"><h2>Independent evidence</h2><dl><div><dt>Forward observations</dt><dd>${num(forward?.independent_forward_outcomes)}</dd></div><div><dt>Coverage</dt><dd>${forward?.coverage_complete===true?'Complete within declared scope':'Incomplete / review required'}</dd></div><div><dt>Recorded source events</dt><dd>${num(Object.values(summary?.counts||{}).reduce((a,b)=>a+Number(b),0))}</dd></div></dl><a href="${route(SHORT,'forward')}">Inspect forward paper policies →</a></aside></div><section class="strategy-section"><h2>Research workspaces</h2><div class="strategy-directory"><a href="${route(SHORT,'signals')}"><strong>Signals</strong><span>Quant screens and systematic candidate selection</span></a><a href="${route(SHORT,'portfolio')}"><strong>Portfolio & risk</strong><span>Account replays, execution costs, capacity, and borrow</span></a><a href="${route(SHORT,'research')}"><strong>Research & data</strong><span>Registered hypotheses, evidence, and source events</span></a></div></section><p class="strategy-note">Company theses and discretionary positions remain in <a href="#/ideas/short-alpha">Fundamental Shorts</a>.</p>`;
  }
  function renderShort(section, summary={}, forward={}) {
    const views={overview:()=>shortOverview(summary,forward),backtest:shortBacktest,
      announcement:()=>global.ThirdPlusAnnouncement?.render()||empty('Announcement study unavailable.'),
      forward:()=>global.ThirdPlusForward?.render()||empty('Forward paper publication unavailable.'),
      signals:()=>'<div data-strategy-short-signals role="status">Loading quantitative signals…</div>',
      portfolio:()=>global.ShortSleeveViz?.render()||empty('Portfolio simulation unavailable.'),
      research:()=>global.ShortProfitProgram?.render()||empty('Systematic research publication unavailable.')};
    return header(SHORT,section,summary.built_at)+(views[section]||views.overview)();
  }
  async function open(kind, container, helpers={}) {
    if (!container) return;
    const token={};requests.set(container,token);
    const state=stateFromHash(global.location.hash);
    state.kind=kind;
    const current=()=>requests.get(container)===token && container.isConnected && !container.closest('section:not(.active)[data-strategy-panel]');
    container.innerHTML=header(kind,state.section)+empty('Loading strategy evidence…');
    try {
      if (kind===BIO) {
        const doc=await json('data/biotech_quant.json');
        if (!current()) return;
        container.innerHTML=renderBio(doc,state);
        container.querySelector('[data-strategy-filters]')?.addEventListener('submit',event=>{
          event.preventDefault();const form=event.currentTarget, next={...state,page:0,kind:undefined,section:undefined};
          next.q=form.elements.q.value;delete next.query;
          form.querySelectorAll('[data-strategy-filter]').forEach(el=>{next[el.dataset.strategyFilter]=el.value;});
          global.location.hash=route(BIO,'signals',next);
        });
        container.querySelectorAll('[data-strategy-filter]').forEach(el=>el.addEventListener('change',()=>container.querySelector('[data-strategy-filters]').requestSubmit()));
        container.querySelector('[data-strategy-export]')?.addEventListener('click',()=>{
          const blob=new Blob([JSON.stringify(bioFiltered(doc,state),null,2)],{type:'application/json'}), url=URL.createObjectURL(blob), a=document.createElement('a');
          a.href=url;a.download='biotech-research-signals.json';a.click();URL.revokeObjectURL(url);
        });
      } else {
        const [summary,forward]=await Promise.all([json('data/short_profit_program/summary.json').catch(()=>({})),json('data/short_forward/status.json').catch(()=>({}))]);
        if (!current()) return;
        container.innerHTML=renderShort(state.section,summary,forward);
        if(state.section==='backtest') {
          global.ThirdPlusStudyViz?.attach(container);
          const earlier=container.querySelector('[data-third-plus-legacy]');
          earlier?.addEventListener('toggle',()=>{if(earlier.open)helpers.mountLegacy?.(container);});
        }
        if(state.section==='announcement')global.ThirdPlusAnnouncement?.attach(container);
        if(state.section==='forward')global.ThirdPlusForward?.attach(container);
        if(state.section==='portfolio')global.ShortSleeveViz?.attach(container);
        if(state.section==='research')global.ShortProfitProgram?.attach(container);
        if(state.section==='signals') {
          const doc=await (helpers.loadShortSignals?.()||json('data/short_alpha.json'));
          if(!current())return;
          container.querySelector('[data-strategy-short-signals]').innerHTML=global.ShortAlphaViz?.renderSystematicSignals(doc)||empty('Quantitative screen unavailable.');
          global.ShortAlphaViz?.attachSystematicSignals?.(container,doc);
        }
      }
    } catch(error) {
      if(current())container.innerHTML=header(kind,state.section)+empty(error.message+' Open Data status to inspect the publication.')+'<p><a href="#/data-status">Data status →</a> <button type="button" data-strategy-retry>Retry</button></p>';
      container.querySelector('[data-strategy-retry]')?.addEventListener('click',()=>open(kind,container,helpers));
    }
  }
  global.StrategyWorkbench={parseRoute,stateFromHash,route,renderBio,renderShort,bioFiltered,open};
  if(typeof module!=='undefined')module.exports=global.StrategyWorkbench;
})(typeof window==='undefined'?globalThis:window);
