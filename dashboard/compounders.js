(function (global) {
  'use strict';
  let roster = null, pending = null;
  const filters = {group:'all', status:'all', sort:'distance', query:''};
  const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = n => typeof n === 'number' && Number.isFinite(n) ? n : null;
  const pct = n => global.DashboardFormat.percentValue(n);
  function load() {
    if (!pending) pending = fetch('data/compounders.json').then(r=>{if(!r.ok)throw Error('Company list unavailable');return r.json();}).then(d=>{roster=d;return d;}).catch(e=>{pending=null;throw e;});
    return pending;
  }
  function member(ticker) { return roster?.companies.find(r=>r.ticker===ticker || r.aliases?.includes(ticker)); }
  function rows(tickers) {
    return (roster?.companies || []).map(c=>{
      const t=tickers.find(t=>t.ticker===c.ticker) || tickers.find(t=>c.aliases?.includes(t.ticker)) || {};
      const d=global.ValuationViz?.decisionOf?.(t) || t.valuation_decision || {}, f=t.shared_forecast;
      // Consume the same publication decision as the company page; never resurrect a withheld return.
      const verified=Boolean(d.research_return_available ?? d.return_publishable);
      const price=verified ? num(d.price_per_share ?? f?.quote?.value) : null;
      const entries=verified ? (f?.status==='available'?f.buy_prices || []:d.buy_prices || (t.pricing_analysis?.buy_zones?.status==='available'?t.pricing_analysis.buy_zones.zones:[]) || []) : [];
      const entry=entries.find(z=>z.hurdle_pct===12) || entries[0];
      const target=num(entry?.prices?.base ?? entry?.price);
      const distance=price>0 && target>0 ? 100*(price/target-1) : null;
      const irr=verified ? num(d.forward_return_at_price_pct?.base) : null;
      const status=distance===null ? 'needs_evidence' : distance<=0 ? 'entry_zone' : 'watch';
      return {...c, record:t, ticker:t.ticker || c.ticker, price,target,distance,irr,status,entry};
    });
  }
  function render(host,tickers) {
    if (!host) return;
    const all=rows(tickers);
    const chosen=all.filter(r=>(filters.group==='all'||r.group===filters.group)&&(filters.status==='all'||r.status===filters.status)&&(!filters.query||`${r.ticker} ${r.name}`.toLowerCase().includes(filters.query.toLowerCase())));
    chosen.sort((a,b)=>{
      const av=filters.sort==='buybacks'?global.BuybackViz?.metric(global.BuybackViz.company(a.ticker),'net_reduction_1y').value:filters.sort==='irr'?a.irr:a.distance;
      const bv=filters.sort==='buybacks'?global.BuybackViz?.metric(global.BuybackViz.company(b.ticker),'net_reduction_1y').value:filters.sort==='irr'?b.irr:b.distance;
      return av==null && bv==null ? a.ticker.localeCompare(b.ticker) : av==null?1:bv==null?-1:(av-bv)*(filters.sort==='distance'?1:-1);
    });
    const money=(n,r)=>n===null?'—':global.DashboardFormat?.quote ? esc(global.DashboardFormat.quote(n,r.record.units || {currency:r.record.shared_forecast?.quote?.currency || r.record.currency || 'USD'})) : new Intl.NumberFormat(undefined,{maximumFractionDigits:2}).format(n);
    host.innerHTML=`<section class="compounder-desk"><header class="compounder-head"><div><span class="desk-eyebrow">Quality businesses · patient entries</span><h1>Long Term Compounders</h1><p>Your dedicated watchlist for attractive long-term buys.</p></div><a href="#/ideas/buybacks">Explore buyback radar →</a></header><div class="desk-stats"><div><strong>${all.length}</strong><span>Companies to follow</span></div><div><strong>${all.filter(r=>r.status==='entry_zone').length}</strong><span>At a research entry threshold</span></div><div><strong>${all.filter(r=>r.status==='needs_evidence').length}</strong><span>Awaiting comparable valuation</span></div></div><div class="desk-controls"><label>Find a company<input type="search" data-comp-query value="${esc(filters.query)}" placeholder="Ticker or company"></label><label>Business group<select data-comp-group><option value="all">All groups</option>${(roster.groups||[]).map(g=>`<option value="${esc(g.id)}"${filters.group===g.id?' selected':''}>${esc(g.label)}</option>`).join('')}</select></label><label>Entry status<select data-comp-status>${[['all','All companies'],['entry_zone','At an entry threshold'],['watch','Above entry threshold'],['needs_evidence','Valuation needs evidence']].map(([k,v])=>`<option value="${k}"${filters.status===k?' selected':''}>${v}</option>`).join('')}</select></label><label>Order by<select data-comp-sort>${[['distance','Closest to entry'],['irr','Base research return'],['buybacks','Share reduction · 1Y']].map(([k,v])=>`<option value="${k}"${filters.sort===k?' selected':''}>${v}</option>`).join('')}</select></label></div><p class="desk-caption">Research thresholds use the company’s published forecast and listing currency. They are comparison points, not automatic buy instructions. Missing or withheld estimates remain blank.</p><div class="desk-table" tabindex="0" role="region" aria-label="Long Term Compounders"><table><thead><tr><th>Company</th><th>Entry status</th><th>Price / entry</th><th>Above entry</th><th>Base IRR</th><th>Shares reduced · 1Y</th></tr></thead><tbody>${chosen.map(r=>`<tr><td><a class="desk-ticker" href="#/research/compounders/${encodeURIComponent(r.ticker)}">${esc(r.ticker)}</a><small>${esc(r.name)}</small><small>${esc(roster.groups.find(g=>g.id===r.group)?.label)}</small></td><td><span class="desk-status ${r.status}">${{entry_zone:'At entry threshold',watch:'Watching price',needs_evidence:'Needs valuation'}[r.status]}</span><small>${esc(r.record.valuation_decision?.dates?.model_as_of || 'No dated model')}</small></td><td>${money(r.price,r)}<small>Entry ${money(r.target,r)}${r.entry?.hurdle_pct?' · '+esc(r.entry.hurdle_pct)+'% hurdle':''}</small></td><td>${pct(r.distance)}</td><td>${pct(r.irr)}</td><td><a href="#/research/compounders/${encodeURIComponent(r.ticker)}?section=models&focus=buyback">${pct(global.BuybackViz?.metric(global.BuybackViz.company(r.ticker),'net_reduction_1y').value)}</a><small>Net share count change</small></td></tr>`).join('')}</tbody></table>${chosen.length?'':'<p class="desk-empty">No companies match these filters.</p>'}</div><p role="status" class="desk-caption">${chosen.length} of ${all.length} companies · Membership is maintained in one shared list.</p></section>`;
    ['group','status','sort'].forEach(key=>host.querySelector('[data-comp-'+key+']').addEventListener('change',e=>{filters[key]=e.target.value;render(host,tickers);}));
    host.querySelector('[data-comp-query]').addEventListener('input',e=>{const at=e.target.selectionStart;filters.query=e.target.value;render(host,tickers);const input=host.querySelector('[data-comp-query]');input.focus();input.setSelectionRange(at,at);});
  }
  async function mount(host,tickers,loadDetail) {
    const version=String(Number(host.dataset.version||0)+1);host.dataset.version=version;
    try {
      await load();await global.BuybackViz?.load();
      if(!host.isConnected||host.dataset.version!==version)return;
      render(host,tickers);
      const queue=rows(tickers).filter(r=>r.record.detail_shard&&!r.record.__detail).map(r=>r.ticker);
      if(loadDetail)await Promise.all(Array.from({length:4},async()=>{while(queue.length && host.dataset.version===version && !host.hidden){const ticker=queue.shift();await loadDetail(ticker).catch(()=>{});}}));
      if(host.isConnected&&host.dataset.version===version&&!host.hidden)render(host,tickers);
    }catch(e){if(host.isConnected&&host.dataset.version===version)host.textContent=e.message;}
  }
  global.Compounders={load,member,rows,mount};
})(window);
