(function(global){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite=v=>v!=null&&Number.isFinite(Number(v));
  const pct=v=>finite(v)?`${v>0?'+':''}${(100*v).toFixed(Math.abs(v)<.0001?3:2)}%`:'—';
  const unsigned=v=>finite(v)?`${(Math.abs(100*v)).toFixed(Math.abs(v)<.0001?3:2)}%`:'—';
  const ratio=v=>finite(v)?Number(v).toFixed(2):'—';
  const cash=v=>finite(v)?`${v<0?'−':''}$${Math.abs(v).toLocaleString('en-US',{maximumFractionDigits:0})}`:'—';
  const num=v=>finite(v)?Number(v).toLocaleString('en-US',{maximumFractionDigits:0}):'—';
  const tone=v=>v<0?'ss-negative':v>0?'ss-positive':'';
  const metric=(label,value,detail='')=>`<div><dt>${esc(label)}</dt><dd>${value}</dd>${detail?`<small>${esc(detail)}</small>`:''}</div>`;
  let loading;
  function render(){return '<section class="ss-sleeve" data-short-sleeve><p role="status">Loading portfolio-sleeve research…</p></section>';}
  function chart(el,series,{percent=true,zero=false,band=null}={}){
    if(!el||!series.length||!series[0].points.length)return;
    const w=Math.max(280,el.clientWidth),h=220,L=58,R=15,T=20,B=30,points=series.flatMap(s=>s.points);
    let values=points.map(p=>p.y).filter(Number.isFinite);if(band)values.push(...band.flatMap(p=>[p.low,p.high]));if(zero)values.push(0);
    let lo=Math.min(...values),hi=Math.max(...values);const pad=Math.max((hi-lo)*.12,percent ? .00001 : 1);lo-=pad;hi+=pad;
    if(zero&&values.every(v=>v<=0))hi=0;
    if(zero&&values.every(v=>v>=0))lo=0;
    if(hi===lo)hi=lo+pad;
    const n=series[0].points.length,x=i=>L+i/Math.max(1,n-1)*(w-L-R),y=v=>T+(hi-v)/(hi-lo)*(h-T-B);
    const line=ps=>ps.map((p,i)=>`${i?'L':'M'}${x(i)},${y(p.y)}`).join('');
    const ticks=[0,.5,1].map(t=>{const v=lo+t*(hi-lo);return `<line x1="${L}" x2="${w-R}" y1="${y(v)}" y2="${y(v)}" class="ss-gridline"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end">${esc(percent?pct(v):cash(v))}</text>`;}).join('');
    const labels=[0,Math.floor((n-1)/2),n-1].map(i=>`<text x="${x(i)}" y="${h-8}" text-anchor="${i===0?'start':i===n-1?'end':'middle'}">${esc(series[0].points[i].label)}</text>`).join('');
    let area='';if(band){const ps=band.map((p,i)=>`${x(i)},${y(p.low)}`).concat(band.map((p,i)=>`${x(i)},${y(p.high)}`).reverse());area=`<polygon points="${ps.join(' ')}" class="ss-fan-band"/>`;}
    el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(el.dataset.label||'Portfolio chart')}">${ticks}${zero?`<line x1="${L}" x2="${w-R}" y1="${y(0)}" y2="${y(0)}" class="ss-zero"/>`:''}${area}${series.map((s,i)=>`<path d="${line(s.points)}" class="ss-line ss-line-${i}"/>`).join('')}${labels}</svg>`;
  }
  async function attach(container){
    const host=container.querySelector('[data-short-sleeve]');if(!host||host.dataset.mounted)return;host.dataset.mounted='true';
    try {
      loading ||= fetch('data/short_sleeve.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw new Error(`Research feed (${r.status})`);return r.json();}).catch(e=>{loading=null;throw e;});
      const doc=await loading;if(!host.isConnected)return;
      if(doc.schema_version!=='short_sleeve.v1')throw new Error('Unsupported portfolio research version');
      mount(host,doc);
    } catch(error){host.innerHTML=`<p role="alert">Portfolio research is unavailable: ${esc(error.message)}. Reload to retry.</p>`;}
  }
  function mount(host,doc){
    let state={...doc.defaults},mc=null,worker=null,request=0,cache=new Map();
    const saved=(()=>{try{return JSON.parse(sessionStorage.getItem('short-sleeve-v1')||'null');}catch(_){return null;}})();
    if(saved&&doc.navs.includes(saved.nav)&&doc.weights.includes(saved.bps)&&doc.horizons.includes(saved.horizon)&&doc.cases.some(c=>c.id===saved.scenario)&&typeof saved.capacity==='boolean')state=saved;
    const selectedModels=()=>doc.models.filter(m=>m.nav===state.nav&&m.bps===state.bps&&m.horizon===state.horizon&&m.capacity===state.capacity);
    const selected=()=>selectedModels().find(m=>m.scenario===state.scenario);
    const key=()=>[state.nav,state.bps,state.horizon,state.capacity].join('/');
    function plots(){
      const m=selected();if(!m)return;
      chart(host.querySelector('[data-ss-equity]'),[{points:[{label:'Start',y:0},...m.monthly.map(r=>({label:r[0].slice(0,7),y:r[1]}))]}],{zero:true});
      chart(host.querySelector('[data-ss-dd]'),[{points:[{label:'Start',y:0},...m.monthly.map(r=>({label:r[0].slice(0,7),y:r[2]}))]}],{zero:true});
      const monthPeaks=new Map();m.series.forEach(r=>{const k=doc.days[r[0]].slice(0,7),p=monthPeaks.get(k)||[0,0];monthPeaks.set(k,[Math.max(p[0],r[2]),Math.max(p[1],r[3])]);});
      chart(host.querySelector('[data-ss-margin]'),[0,1].map(j=>({points:m.monthly.map(r=>({label:r[0].slice(0,7),y:(monthPeaks.get(r[0].slice(0,7))||[0,0])[j]}))})),{zero:true});
      const sim=mc?.[state.scenario];if(sim)chart(host.querySelector('[data-ss-fan]'),[{points:sim.fan.map(r=>({label:`Year ${ratio(r.month/12)}`,y:r.p50-1}))}],{zero:true,band:sim.fan.map(r=>({low:r.p05-1,high:r.p95-1}))});
    }
    function paint(){
      const m=selected();if(!m){host.innerHTML='<p role="alert">This research scenario is unavailable.</p>';return;}
      const p=m.metrics,sim=mc?.[state.scenario],cases=doc.cases;
      const options=(values,current,format)=>values.map(v=>`<option value="${v}"${v===current?' selected':''}>${esc(format(v))}</option>`).join('');
      const groupRows=doc.groups.filter(r=>r.horizon===state.horizon).map(r=>`<tr><th scope="row">${esc(r.label)}<small>${num(r.issuers)} issuers${r.missing?` · ${num(r.missing)} missing paths`:''}</small></th><td>${num(r.n)}</td><td class="${tone(r.mean)}">${pct(r.mean)}</td><td>${pct(r.median)}</td><td>${unsigned(r.win_rate)}</td><td>${unsigned(r.sd)}</td><td>${unsigned(r.es95)}</td><td class="ss-negative">${pct(r.worst)}</td></tr>`).join('');
      const history=selectedModels().map(r=>{const q=r.metrics,s=mc?.[r.scenario];return `<tr${r.scenario===state.scenario?' class="ss-selected-row"':''}><th scope="row">${esc(cases.find(c=>c.id===r.scenario).label)}</th><td>${pct(q.cagr)}</td><td>${unsigned(q.max_drawdown)}</td><td>${ratio(q.calmar)}</td><td>${s?pct(s.cagr.p50):'…'}</td><td>${s?unsigned(s.max_drawdown.p95):'…'}</td></tr>`;}).join('');
      const g=doc.groups.find(r=>r.horizon===state.horizon&&r.id==='primary');
      const bins=g.histogram.counts,max=Math.max(1,...bins);
      const labels=['−2000 to −500%','−500 to −200%','−200 to −100%','−100 to −50%','−50 to −20%','−20 to −10%','−10 to 0%','0 to +10%','+10 to +20%','+20 to +50%','+50 to +100%'];
      const histogram=bins.map((v,i)=>`<div class="ss-hist-row"><span>${labels[i]}</span><div><i style="width:${v/max*100}%" class="${i<7?'ss-loss-bar':'ss-gain-bar'}"></i></div><b>${num(v)}</b></div>`).join('');
      const trade=p.trade_stats||{};
      host.innerHTML=`<header class="ss-heading"><div><p class="ss-eyebrow">Shorts · portfolio research</p><h2>What could this add to the portfolio?</h2><p>Incremental returns on total portfolio NAV. Michael’s existing investments are held flat in this illustration.</p></div><span class="ss-status">Indicative · not live performance</span></header>
        <div class="ss-controls"><label>Total portfolio NAV<select data-ss-control="nav">${options(doc.navs,state.nav,v=>cash(v))}</select></label><label>Target per name<select data-ss-control="bps">${options(doc.weights,state.bps,v=>`${v} bps · ${unsigned(v/10000)}`)}</select></label><label>Holding period<select data-ss-control="horizon">${options(doc.horizons,state.horizon,v=>v===1?'Same-day close':`${v} sessions`)}</select></label><label>Position sizing<select data-ss-control="capacity"><option value="true"${state.capacity?' selected':''}>Capacity-aware</option><option value="false"${!state.capacity?' selected':''}>Full target · hypothetical</option></select></label></div>
        <div class="ss-case-row"><div class="ss-case-buttons" role="group" aria-label="Combined execution and borrow case">${cases.map(c=>`<button type="button" data-ss-case="${c.id}" aria-pressed="${c.id===state.scenario}">${esc(c.label)}</button>`).join('')}</div><p>Each case pairs execution + borrowing. <strong>${unsigned(cases.find(c=>c.id===state.scenario).execution_fraction)} round trip</strong> + commissions · <strong>${unsigned(cases.find(c=>c.id===state.scenario).borrow_annual)} annual borrow</strong>.</p></div>
        <p class="ss-sizing-note${!state.capacity?' ss-warning':''}">${state.capacity?`Target ${cash(state.nav*state.bps/10000)} per name; historical volume reduces the modeled average to ${cash(p.mean_actual_weight*state.nav)} (${ratio(p.mean_actual_weight*10000)} bps of NAV).`:'Full target sizing ignores historical capacity. These orders may not be fillable at the modeled costs.'}${state.bps>25?' The target exceeds the existing 50 bp name-loss allowance under a +200% squeeze.':''}</p>
        <div class="ss-section-label"><span>Historical replay · modeled net</span><span>${doc.days[0]} → ${doc.days.at(-1)}</span></div>
        <dl class="ss-kpis" aria-live="polite">${metric('Added CAGR',`<span class="${tone(p.cagr)}">${pct(p.cagr)}</span>`,'Against total starting NAV')}${metric('Maximum drawdown',unsigned(p.max_drawdown),'Daily closing equity')}${metric('Calmar',ratio(p.calmar),'CAGR ÷ maximum drawdown')}${metric('Sharpe',ratio(p.sharpe),'Zero risk-free rate')}${metric('Sortino',ratio(p.sortino),'Zero downside target')}${metric('Annual volatility',unsigned(p.annual_volatility))}</dl>
        <p class="ss-summary">${num(p.entered)} entries · ${ratio(p.trades_per_year)} per year · ${num(p.partial)} below target size · ${num(p.idle_sessions)} idle sessions · <strong>${cash(p.net_pnl)} modeled net P&L</strong></p>
        ${p.unresolved||p.missing_mark_days?`<p class="ss-warning">${num(p.unresolved)} positions remain unresolved at the cutoff; ${num(p.missing_mark_days)} position-days carry the last observed mark. ${num(p.delayed_covers)} covers waited for a later observed close. Risk may be understated between observations.</p>`:''}
        <div class="ss-chart-grid"><figure><figcaption>Added portfolio growth</figcaption><div data-ss-equity data-label="Historical incremental portfolio return"></div></figure><figure><figcaption>Drawdown from the prior peak</figcaption><div data-ss-dd data-label="Historical month-end drawdown"></div></figure></div><p class="ss-caption">Charts show month ends; maximum drawdown and ratios use every trading session. Fixed starting-NAV dollar sizes; no assumed core-portfolio return or cash interest.</p>
        <section class="ss-section"><div class="ss-section-label"><span>Five-year Monte Carlo · ${num(sim?.trials||2000)} paths</span><span>${sim?'Historical month blocks':'Calculating…'}</span></div><p class="ss-mc-summary" role="status">${sim?`Median added CAGR <strong>${pct(sim.cagr.p50)}</strong> · 95th-percentile maximum drawdown <strong>${unsigned(sim.max_drawdown.p95)}</strong> · probability of ending below the starting NAV <strong>${unsigned(sim.loss_probability)}</strong>.`:'Resampling complete historical months, including clustered losses and idle days…'}</p><div data-ss-fan data-label="Monte Carlo median and 5th to 95th percentile portfolio growth"></div><p class="ss-caption">Line: median. Band: 5th–95th percentile. These are conditional resampled outcomes, not a forecast or a bound on unseen squeezes. Insolvency probability: ${sim?unsigned(sim.ruin_probability):'…'}.</p>
        <div class="ss-table-scroll"><table class="ss-table"><caption>Three combined cost cases</caption><thead><tr><th>Case</th><th>Historical CAGR</th><th>Max DD</th><th>Calmar</th><th>MC median CAGR</th><th>MC 95% max DD</th></tr></thead><tbody>${history}</tbody></table></div></section>
        <section class="ss-section"><div class="ss-section-label"><span>Observed price returns · before costs</span><span>${state.horizon} session${state.horizon===1?'':'s'}</span></div><p class="ss-caption">What actually happened to the price cohorts. These distributions assume neither approved borrowing nor executable fills. The sleeve replay uses the known-before-entry, unrestricted cohort.</p><div class="ss-table-scroll"><table class="ss-table"><thead><tr><th>Group</th><th>Events</th><th>Mean</th><th>Median</th><th>Win rate</th><th>Std. dev.</th><th>Worst 5% avg. loss</th><th>Worst trade</th></tr></thead><tbody>${groupRows}</tbody></table></div><details class="ss-details"><summary>See the return distribution and annual results</summary><div class="ss-chart-grid"><div><h3>All priced splits · trade returns</h3><div class="ss-hist">${histogram}</div></div><div><h3>Modeled portfolio contribution by year</h3><table class="ss-table"><thead><tr><th>Year</th><th>Net return on NAV</th></tr></thead><tbody>${m.annual.map(r=>`<tr><th>${r[0]}</th><td class="${tone(r[1])}">${pct(r[1])}</td></tr>`).join('')}</tbody></table></div></div></details></section>
        <section class="ss-section"><div class="ss-section-label"><span>Hypothetical margin & collateral</span><span>Core portfolio excluded</span></div><dl class="ss-financing">${metric('Peak equity margin',unsigned(p.peak_margin),cash(p.peak_margin*state.nav))}${metric('Peak borrow collateral',unsigned(p.peak_collateral),cash(p.peak_collateral*state.nav))}${metric('+200% squeeze reserve',unsigned(p.stress_reserve_200),cash(p.stress_reserve_200*state.nav))}</dl><div data-ss-margin data-label="Monthly peak equity margin and borrow collateral as fractions of starting portfolio NAV"></div><p class="ss-caption"><span class="ss-legend ss-legend-0"></span> Equity margin <span class="ss-legend ss-legend-1"></span> Borrow collateral · monthly peaks at opening/closing marks; intraday requirements may be higher. Collateral includes restricted short-sale proceeds; do not add collateral and equity margin as separate cash needs.</p><p class="ss-caption">Margin uses a hypothetical 100% house floor and per-share maintenance minimums. Squeeze reserve adds a +200% price loss to post-shock margin at a 200% house requirement. No probability is assigned. Broker requirements and Michael’s actual excess liquidity can differ. The replay does not force liquidation for margin calls.</p><p class="ss-caption">${sim?`Monte Carlo 95th-percentile peak: equity margin ${unsigned(sim.peak_margin.p95)} (${cash(sim.peak_margin.p95*state.nav)}); borrow collateral ${unsigned(sim.peak_collateral.p95)} (${cash(sim.peak_collateral.p95*state.nav)}).`:""}</p></section>
        <details class="ss-details"><summary>Assumptions, full statistics & sources</summary><div class="ss-chart-grid"><dl class="ss-facts">${[['Total net return',pct(p.total_return)],['Trade win rate',unsigned(trade.win_rate)],['Trade profit factor',ratio(trade.profit_factor)],['Mean net trade',pct(trade.mean)],['Worst day',pct(p.worst_day)],['Best day',pct(p.best_day)],['Longest drawdown',`${num(p.longest_drawdown_sessions)} sessions`],['Ulcer index',unsigned(p.ulcer_index)],['Execution costs',cash(p.execution_cost)],['Commissions',cash(p.commission_cost)],['Borrow costs',cash(p.borrow_cost)],['Closed / unresolved',`${num(p.closed)} / ${num(p.unresolved)}`]].map(([l,v])=>`<div><dt>${esc(l)}</dt><dd>${v}</dd></div>`).join('')}</dl><div>${Object.entries(doc.method).map(([k,v])=>`<p><strong>${esc(k.replaceAll('_',' '))}.</strong> ${esc(v)}</p>`).join('')}</div></div><p>Execution calibration: ${num(doc.calibration.paired_quotes)} cached quote pairs; borrow indications dated ${esc(doc.calibration.borrow_as_of)}. The bear/base/bull execution costs use the 75th/50th/25th spread percentiles plus the measured mean displayed-depth cost; borrow uses the 90th percentile / mean / median fee. Missing inventory is not an approved locate. Multi-session covers and larger tickets remain cost sensitivities.</p><p>Two-session price returns are a new retrospective endpoint diagnostic. Other all-split horizons retain their original observed cohorts, which differ in coverage. Month blocks resample P&amp;L rather than rebuilding positions across block boundaries. Recalls, buy-ins, dividends, financing interest and unobserved intraday gaps are not modeled. Short losses have no fixed upper bound.</p><p>Financing conventions: <a href="https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210" target="_blank" rel="noopener">FINRA margin floors</a> | <a href="https://www.interactivebrokers.com/campus/glossary-terms/collateral-short-sale/" target="_blank" rel="noopener">IBKR borrow collateral</a> | <a href="https://www.interactivebrokers.com/en/pricing/commissions-stocks.php" target="_blank" rel="noopener">IBKR commission schedule</a>. Regulatory charges are not separately modeled. No production threshold changes, broker connection or order is implied.</p><a href="data/short_sleeve.json" download>Download aggregate research</a></details>`;
      host.querySelectorAll('[data-ss-control]').forEach(el=>el.addEventListener('change',()=>{const k=el.dataset.ssControl;state[k]=k==='capacity'?el.value==='true':Number(el.value);persist();mc=cache.get(key())||null;paint();if(!mc)simulate();}));
      host.querySelectorAll('[data-ss-case]').forEach(el=>el.addEventListener('click',()=>{state.scenario=el.dataset.ssCase;persist();paint();}));
      plots();
    }
    function persist(){try{sessionStorage.setItem('short-sleeve-v1',JSON.stringify(state));}catch(_){}}
    function simulate(){
      const id=++request,k=key(),models=selectedModels();worker?.terminate();
      const complete=results=>{cache.set(k,results);if(request!==id||!host.isConnected)return;mc=results;paint();};
      try {worker=new Worker('short-sleeve-worker.js');worker.onmessage=e=>{if(e.data.error){fail(e.data.error);return;}complete(e.data.results);};worker.onerror=()=>fallback();worker.postMessage({id,days:doc.days,models});}
      catch(_){fallback();}
      function fallback(){worker?.terminate();setTimeout(()=>{try{complete(global.ShortSleeveEngine.monteCarlo(doc.days,models));}catch(e){fail(e.message);}},0);}
      function fail(message){if(request!==id)return;const el=host.querySelector('.ss-mc-summary');if(el){el.setAttribute('role','alert');el.textContent=`Simulation unavailable: ${message}`;}}
    }
    paint();simulate();
    if(global.ResizeObserver){const observer=new ResizeObserver(()=>{if(host.isConnected)plots();else{observer.disconnect();worker?.terminate();}});observer.observe(host);}
  }
  global.ShortSleeveViz={render,attach,mount};
})(window);
