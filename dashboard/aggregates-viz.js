/* One aggregates screen, with explicit periods, peers and source evidence. */
(function(global){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=v=>typeof v==='number'&&Number.isFinite(v);
  const show=(v,unit='')=>!number(v)?'—':unit==='USD'?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:1}).format(v):(unit==='$'?'$':'')+v.toLocaleString('en-US',{maximumFractionDigits:2})+(unit==='%'?'%':unit==='x'?'x':'');
  const PEERS={aggregates_focused:'Aggregates focused',integrated_materials:'Integrated materials',contractors_asphalt:'Contractors / asphalt',cement:'Cement',lime:'Lime'};
  const COLUMNS={
    ev:['EV / EBITDA','x'],fcf:['FCF yield','%'],price_growth:['Price growth','%'],volume:['Organic volume','%'],profit:['Cash GP / ton','$'],profit_change:['Cash GP / ton change','$'],leverage:['Net debt / EBITDA','x'],
    shipments:['Shipments · M tons',''],price:['Price / ton','$'],cost:['Cash cost / ton','$'],spread:['Price less cost change','$'],segment_margin:['Segment EBITDA margin','%'],incremental:['Incremental margin','%'],
    reserves:['Reserves · M tons',''],life:['Reserve life · years',''],permitted:['Permitted life · years',''],quarries:['Active quarries',''],terminals:['Terminals / yards',''],
    cash_conversion:['FCF conversion','%'],capex:['Capex / revenue','%'],roic:['ROIC · average capital','%'],maintenance:['Maintenance capex','USD'],growth_capex:['Growth capex','USD'],backlog:['Contracting backlog','USD'],acquisitions:['Acquisition intensity','%']
  };
  const VIEWS={overview:['ev','fcf','price_growth','volume','profit','profit_change','leverage'],operations:['shipments','price','price_growth','volume','profit','cost','spread','segment_margin','incremental'],reserves:['reserves','life','permitted','quarries','terminals','backlog'],capital:['ev','fcf','cash_conversion','capex','roic','leverage','maintenance','growth_capex','acquisitions']};
  const DEFAULT={query:'',peer:'peers',period:'FY',preset:'peers',view:'overview',sort:'profit_change',direction:'desc',leverage:2.5,ev:15,life:30};
  function period(row,kind){return row.operating_latest?.[kind] || null;}
  function value(row,key,kind='FY'){
    const p=period(row,kind),m=p?.metrics||{},op=k=>m[k]?.value??null;
    const financial=kind==='FY'&&row.financial_status==='verified';
    return ({ev:financial?row.ev_ebitda:null,fcf:financial?row.fcf_yield_pct:null,price_growth:p?.changes?.price_per_ton?.growth_pct??null,volume:op('organic_volume_growth_pct'),profit:op('cash_gp_per_ton'),profit_change:p?.changes?.cash_gp_per_ton?.delta??null,
      leverage:financial?row.net_debt_ebitda:null,shipments:op('shipments_million_tons'),price:op('price_per_ton'),cost:op('cash_cost_per_ton'),spread:p?.price_cost_spread_change??null,segment_margin:p?.segment_ebitda_margin_pct??null,incremental:p?.incremental_margin_pct??null,
      reserves:op('reserves_million_tons'),life:op('reserve_life_years'),permitted:op('permitted_reserve_life_years'),quarries:op('quarries'),terminals:op('terminals'),backlog:op('backlog_usd'),cash_conversion:financial?row.fcf_conversion_pct:null,capex:financial?row.capex_pct_revenue:null,roic:financial?row.roic_average_pct:null,maintenance:op('maintenance_capex_usd'),growth_capex:op('growth_capex_usd'),acquisitions:financial&&row.cfo_usd>0&&number(row.acquisitions_usd)?100*row.acquisitions_usd/row.cfo_usd:null})[key]??null;
  }
  function presetMatch(row,s){
    const v=k=>value(row,k,s.period);
    switch(s.preset){
      case 'pricing':return v('price_growth')>0&&v('profit_change')>0&&v('volume')!==null;
      case 'improving':return v('spread')>0&&v('profit_change')>0;
      case 'cash':return v('fcf')>0&&v('leverage')!==null&&v('leverage')<=Number(s.leverage);
      case 'value':return v('ev')!==null&&v('ev')>0&&v('ev')<=Number(s.ev)&&v('fcf')>0;
      case 'reserves':return v('life')!==null&&v('life')>=Number(s.life);
      case 'gaps':return (row.operating_coverage?.required_missing||[]).length>0||row.financial_status!=='verified';
      default:return true;
    }
  }
  function filterRows(rows,s){
    return rows.filter(r=>(r.ticker+' '+r.company).toLowerCase().includes(s.query.toLowerCase())&&(s.peer==='all'||s.peer==='peers'&&['aggregates_focused','integrated_materials'].includes(r.peer_group)||r.peer_group===s.peer)&&presetMatch(r,s)).sort((a,b)=>{
      const av=value(a,s.sort,s.period),bv=value(b,s.sort,s.period);
      if(av===null&&bv===null)return a.ticker.localeCompare(b.ticker);if(av===null)return 1;if(bv===null)return -1;
      return (av-bv)*(s.direction==='asc'?1:-1)||a.ticker.localeCompare(b.ticker);
    });
  }
  function chart(periods,key){
    const points=periods.filter(p=>number(p.metrics?.[key]?.value));if(points.length<2)return '<p class="aggregates-muted">At least two comparable observations are needed for a trend.</p>';
    const groups=new Set(points.map(p=>JSON.stringify(['business_segment','geography','freight_basis','sales_scope','perimeter_basis'].map(k=>p.metrics[key][k]))));
    if(groups.size>1)return '<p class="aggregates-muted">Definitions differ across this history; inspect the source rows before comparing.</p>';
    const values=points.map(p=>p.metrics[key].value),lo=Math.min(...values),range=Math.max(...values)-lo||1;
    const line=values.map((v,i)=>`${12+i*476/(values.length-1)},${90-(v-lo)*65/range}`).join(' ');
    return `<svg viewBox="0 0 500 120" role="img" aria-label="${esc(key.replace(/_/g,' '))} historical trend"><polyline points="${line}" fill="none" stroke="currentColor" stroke-width="2.5"/><text x="12" y="115">${esc(points[0].period_end)}</text><text x="400" y="115">${esc(points.at(-1).period_end)}</text></svg>`;
  }
  function mount(host,payload,options={}){
    let saved;try{saved=JSON.parse(localStorage.getItem('ssi-aggregates-screen-v2')||'{}');}catch{saved={};}
    let state={...DEFAULT,...saved},selected=null,ticket=0,detailCache=new Map();
    const save=()=>{try{localStorage.setItem('ssi-aggregates-screen-v2',JSON.stringify(state));}catch{}};
    const choices=(items,active)=>items.map(([k,label])=>`<option value="${esc(k)}"${k===active?' selected':''}>${esc(label)}</option>`).join('');
    host.className='aggregates-screen';
    host.innerHTML=`<header class="aggregates-hero"><div><span class="workspace-eyebrow">Materials · local economics</span><h3>Aggregates</h3><p>Pricing, quarry profitability and capital discipline. Every operating metric keeps its own period and definition.</p></div><span>${(payload.rows||[]).length} producers<small>Evidence snapshot ${esc(String(payload.generated_at||payload.built_at||'unavailable').slice(0,10))}</small></span></header>
      <div class="workspace-filter"><label class="workspace-search">Find a producer<input type="search" data-ag-query placeholder="Ticker or company" value="${esc(state.query)}"></label><label>Peers<select data-ag-peer>${choices([['peers','Aggregates peers'],['all','All materials'],...Object.entries(PEERS)],state.peer)}</select></label><label>Period<select data-ag-period>${choices([['FY','Full year'],['Q','Latest quarter · YoY'],['TTM','Trailing 12 months']],state.period)}</select></label><label>Screen<select data-ag-preset>${choices([['peers','All peers'],['pricing','Pricing power'],['improving','Improving economics'],['cash','Cash and resilience'],['value','Value to investigate'],['reserves','Reserve strength'],['gaps','Research gaps']],state.preset)}</select></label></div>
      <div class="aggregates-toolbar"><nav class="workspace-pills" aria-label="Aggregates columns">${[['overview','Overview'],['operations','Unit economics'],['reserves','Reserves and markets'],['capital','Cash and capital']].map(([key,label])=>`<button type="button" data-ag-view="${key}" aria-pressed="${state.view===key}">${label}</button>`).join('')}</nav><details class="aggregates-options"><summary>Sort and thresholds</summary><div class="workspace-filter"><label>Sort by<select data-ag-sort>${choices(Object.entries(COLUMNS).map(([k,v])=>[k,v[0]]),state.sort)}</select></label><label>Order<select data-ag-direction>${choices([['desc','Highest first'],['asc','Lowest first']],state.direction)}</select></label><label>Maximum leverage<input type="number" step=".5" min="0" max="20" data-ag-leverage value="${esc(state.leverage)}"></label><label>Maximum EV / EBITDA<input type="number" step="1" min="1" max="100" data-ag-ev value="${esc(state.ev)}"></label><label>Minimum reserve life<input type="number" min="1" max="300" data-ag-life value="${esc(state.life)}"></label><button type="button" data-ag-reset>Reset</button></div></details></div>
      <p class="aggregates-muted" data-ag-count aria-live="polite"></p><div class="workspace-scroll" data-ag-results></div><div data-ag-detail></div>
      <details class="workspace-fold"><summary>Definitions and demand context</summary><p class="aggregates-muted">Price growth may include mix and acquisitions. Organic volume is shown only when disclosed. Corporate EV / EBITDA uses a financial proxy and is never divided by segment profit. Reserve life does not establish permit life. Missing data stays out of numeric filters.</p><p><a href="#/insights/tickers">Open the aggregates and infrastructure theme</a></p><div data-ag-demand></div></details>`;
    const results=host.querySelector('[data-ag-results]'),detail=host.querySelector('[data-ag-detail]');
    async function select(row){
      selected=row.ticker;const request=++ticket;
      detail.innerHTML='<div class="aggregates-detail">Loading company evidence.</div>';
      try{
        if(!/^aggregates\/details\/[A-Z]+-[a-f0-9]{20}\.json$/.test(row.detail_ref||''))throw new Error('Rebuild the evidence snapshot to open company detail.');
        if(!detailCache.has(row.detail_ref))detailCache.set(row.detail_ref,fetch('data/'+row.detail_ref).then(async r=>{if(!r.ok)throw new Error('Company evidence could not be loaded.');return r.json();}));
        const d=await detailCache.get(row.detail_ref);if(request!==ticket||!host.isConnected)return;
        if(d.ticker!==row.ticker)throw new Error('Company evidence identity does not match.');
        const periods=(d.operating_history||[]).filter(p=>p.period_type===state.period),last=periods.at(-1);
        const sources=last?Object.values(last.metrics):[];
        detail.innerHTML=`<section class="aggregates-detail" tabindex="-1"><header class="workspace-heading"><div><span class="workspace-eyebrow">${esc(PEERS[row.peer_group]||'Producer')}</span><h3>${esc(row.ticker)} · ${esc(row.company)}</h3><p>Operations ${esc(last?.period_end||'unavailable')} · Financials ${esc(row.financial_as_of||'unavailable')} · Balance sheet ${esc(row.balance_as_of||'unavailable')}</p></div><button type="button" data-ag-close>Close</button></header><nav class="aggregates-detail-links"><a href="#/research/coverage/${encodeURIComponent(row.ticker)}">Company research</a><a href="#/research/coverage/${encodeURIComponent(row.ticker)}?section=buyback">Buyback evidence</a>${!row.in_holdings?'<button type="button" data-ag-watch>Add to watchlist</button>':''}</nav>
          <div class="aggregates-trends"><article><h4>Cash gross profit / ton</h4>${chart(periods,'cash_gp_per_ton')}</article><article><h4>Price / ton</h4>${chart(periods,'price_per_ton')}</article></div>
          <details class="workspace-fold" open><summary>Operating history · ${periods.length} periods</summary><div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Period</th><th>Shipments · M tons</th><th>Price / ton</th><th>Cash GP / ton</th><th>Cost / ton</th><th>Reserve life</th></tr></thead><tbody>${periods.slice(-20).reverse().map(p=>`<tr><td>${esc(p.period_end)}</td>${['shipments_million_tons','price_per_ton','cash_gp_per_ton','cash_cost_per_ton','reserve_life_years'].map(k=>`<td>${show(p.metrics[k]?.value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>
          <details class="workspace-fold"><summary>Cash generation and valuation history</summary><p class="aggregates-muted">Valuation date: ${esc(d.quote?.as_of||'No verified quote')}. Financial flows retain FY or quarter basis. ROIC uses a 21% tax assumption.</p><div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Period</th><th>Basis</th><th>Revenue</th><th>EBITDA proxy</th><th>FCF</th><th>Capex / revenue</th></tr></thead><tbody>${(d.financial_history||[]).slice(-30).reverse().map(r=>`<tr><td>${esc(r.period_end)}</td><td>${esc(r.period_type)}</td><td>${show(r.revenue_usd,'USD')}</td><td>${show(r.ebitda_usd,'USD')}</td><td>${show(r.fcf_usd,'USD')}</td><td>${show(r.capex_pct_revenue,'%')}</td></tr>`).join('')}</tbody></table></div><h4>Monthly valuation history</h4><p class="aggregates-muted">Only filings public by each mark enter these FY-based comparisons.</p><div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Date</th><th>Financial period</th><th>EV / EBITDA proxy</th><th>FCF yield</th></tr></thead><tbody>${(d.valuation_history||[]).slice(-60).reverse().map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.financial_period_end)}</td><td>${show(r.ev_ebitda,'x')}</td><td>${show(r.fcf_yield_pct,'%')}</td></tr>`).join('')}</tbody></table></div>${(d.warnings||[]).map(w=>`<p class="aggregates-muted">${esc(w)}</p>`).join('')}</details>
          <details class="workspace-fold"><summary>Footprint, reserves and research gaps</summary>${(d.footprint||[]).map(r=>`<p>${esc(r.region)} · ${esc(r.description)} · ${esc(r.as_of)} <a href="${esc(r.source_url)}" target="_blank" rel="noopener">Source</a></p>`).join('')}${sources.filter(r=>/reser|quarr|terminal|backlog/.test(r.metric)).map(r=>`<p>${esc(r.metric.replace(/_/g,' '))}: ${show(r.value)} ${esc(r.unit)} · ${esc(r.notes||'')}</p>`).join('')}<ul>${(d.research_tasks||[]).map(r=>`<li>${esc(r.metric.replace(/_/g,' '))}: ${esc(r.reason)}. ${esc(r.next_action)}</li>`).join('')}</ul></details>
          <details class="workspace-fold"><summary>Primary sources and definitions</summary>${sources.map(r=>`<article class="aggregates-evidence"><a href="${esc(/^https:\/\//.test(r.source_url)?r.source_url:'#')}" target="_blank" rel="noopener">${esc(r.metric.replace(/_/g,' '))}</a><p>${esc(r.locator)} · ${esc(r.status)} · ${esc(r.period_start)} to ${esc(r.period_end)}</p><p>${esc(r.freight_basis)} · ${esc(r.sales_scope)} · ${esc(r.perimeter_basis)} · published/verified ${esc(r.published_at)}</p></article>`).join('')}${(d.financial_sources||[]).map(r=>`<p><a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.metric)} · ${esc(r.locator)}</a></p>`).join('')}</details></section>`;
        detail.querySelector('[data-ag-close]').onclick=()=>{selected=null;ticket++;detail.replaceChildren();};
        detail.querySelector('[data-ag-watch]')?.addEventListener('click',()=>options.onWatch?.(row));
        detail.querySelector('section').focus({preventScroll:true});detail.scrollIntoView({block:'start'});
      }catch(e){detailCache.delete(row.detail_ref);if(request===ticket)detail.textContent=e.message;}
    }
    function paint(){
      const rows=filterRows(payload.rows||[],state),columns=VIEWS[state.view]||VIEWS.overview;
      const base=(payload.rows||[]).filter(r=>(r.ticker+' '+r.company).toLowerCase().includes(state.query.toLowerCase())&&(state.peer==='all'||state.peer==='peers'&&['aggregates_focused','integrated_materials'].includes(r.peer_group)||r.peer_group===state.peer));
      const missing=base.filter(r=>columns.some(k=>value(r,k,state.period)===null)).length;
      host.querySelector('[data-ag-count]').textContent=`${rows.length} matching producers · ${missing} have missing fields in this view. Missing values sort last and cannot pass numeric thresholds.`;
      results.innerHTML=`<table class="workspace-table aggregates-table"><thead><tr><th>Company / peer</th>${columns.map(k=>`<th>${COLUMNS[k][0]}</th>`).join('')}<th>Evidence</th></tr></thead><tbody>${rows.map(row=>{const p=period(row,state.period);return `<tr><td><button type="button" data-ag-ticker="${esc(row.ticker)}">${esc(row.ticker)}${['VMC','MLM'].includes(row.ticker)?' <span class="aggregates-benchmark">Benchmark</span>':''}</button><small>${esc(row.company)}</small><small>${esc(PEERS[row.peer_group]||row.rock_type_label)}</small></td>${columns.map(k=>`<td class="aggregates-number">${show(value(row,k,state.period),COLUMNS[k][1])}</td>`).join('')}<td><span class="workspace-state ${!p?'is-warning':''}">${p?'Sourced':'Needs evidence'}</span><small>Operations ${esc(p?.period_end||'not published')}</small><small>Financials ${esc(row.financial_as_of||'unavailable')}${row.financial_status==='verified'?'':' · requires refresh'}</small></td></tr>`;}).join('')}</tbody></table>${rows.length?'':'<div class="workspace-empty">No producers meet this screen. Try All peers or review missing evidence.</div>'}`;
      results.querySelectorAll('[data-ag-ticker]').forEach(b=>b.onclick=()=>select(rows.find(r=>r.ticker===b.dataset.agTicker)));
      host.querySelectorAll('[data-ag-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.agView===state.view)));
    }
    for(const key of ['query','peer','period','preset','sort','direction','leverage','ev','life']){
      const el=host.querySelector('[data-ag-'+key+']');el.addEventListener(key==='query'?'input':'change',()=>{state[key]=el.value;save();paint();if(selected&&key==='period')void select(payload.rows.find(r=>r.ticker===selected));});
    }
    host.querySelectorAll('[data-ag-view]').forEach(b=>b.onclick=()=>{state.view=b.dataset.agView;save();paint();});
    host.querySelector('[data-ag-reset]').onclick=()=>{state={...DEFAULT};save();mount(host,payload,options);};paint();
    const renderDemand=doc=>{
      const strip=doc?.strip || {},nodes=Array.isArray(strip.industry_nodes)?strip.industry_nodes:Object.values(strip.industry_nodes || {});
      const themes=nodes.filter(r=>/aggregates|construction materials/i.test(JSON.stringify(r)));
      const hostSlot=host.querySelector('[data-ag-demand]');if(!hostSlot || !host.isConnected)return;
      hostSlot.innerHTML=`<p class="aggregates-muted">Theme observations as of ${esc(strip.as_of || 'unavailable')}. Company demand weights require disclosed regional exposure.</p>${themes.map(r=>`<article class="aggregates-evidence"><strong>${esc(r.label || r.name || r.id || 'Aggregates / construction materials')}</strong><p>${esc(r.summary || r.status || r.description || '')}</p></article>`).join('') || '<p class="aggregates-muted">Open Ticker insights for the existing industry theme and source ledger.</p>'}`;
    };
    if(options.worldModel)renderDemand(options.worldModel);else fetch('data/world_model.json').then(r=>r.ok?r.json():null).then(renderDemand).catch(()=>{});

  }
  global.AggregatesViz={mount,filterRows,value,period,presetMatch,DEFAULT,COLUMNS};
})(window);
