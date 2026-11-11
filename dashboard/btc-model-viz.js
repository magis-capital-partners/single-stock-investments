/* Dated BTC research context. No valuation, order, or account API access. */
(function (global) {
  'use strict';
  const documents = new Map();
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const usd = value => value == null || !Number.isFinite(Number(value)) ? '—' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:0}).format(value);
  const num = (value, digits=2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits);
  const iso = value => Date.parse(String(value) + 'T00:00:00Z');
  const colors = {spot:'#60a5fa', demand:'#fbbf24', free:'#a5b4fc', cost:'#f87171', reference:'#f472b6', proxy:'#2dd4bf', fees:'#c084fc'};
  const source = (url, label) => /^https:\/\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label);
  const refs = doc => (doc.hk_reference?.vintages || []).flatMap(v => (v.references || []).map(r => ({...r, vintage:v.label, url:v.url})));
  const lensCopy = horizon => horizon === 'near'
    ? 'Near term: lead with production economics through the estimated 2028 halving. Demand remains a separate comparison.'
    : 'Long term: lead with demand scenarios through 2033. Production cost remains visible as dynamic economic support.';
  function ageStatus(row, now) {
    const age = Number.isFinite(iso(row.observed_through)) ? Math.floor((now - iso(row.observed_through))/86400000) : null;
    return {age, stale:age == null || age > row.max_age_days || row.stale};
  }
  function chart(doc, state={}) {
    const horizon = state.horizon || 'long';
    const demand = doc.demand || {}, supply = doc.supply || {};
    const end = iso(horizon === 'near' ? '2028-04-15' : (doc.horizon || '2033-12-31'));
    const start = iso(state.full ? (demand.actual_path?.[0]?.d || '2011-01-01') : '2017-01-01');
    const observedEnd = iso(doc.as_of);
    const w=state.width || 960, h=w<600?360:450, pad={l:w<600?52:64,r:20,t:24,b:48};
    const floor = (state.power === 'proxy' ? supply.electricity_history?.cost_path : supply.cost_path) || [];
    const series = [
      {name:'Observed BTC', color:colors.spot, rows:demand.actual_path || [], observedOnly:true},
      {name:'Our constrained demand', color:colors.demand, rows:demand.model_path || [], width:horizon === 'long' ? 3 : 2},
      {name:state.power === 'proxy' ? 'Production cost · power proxy' : 'Production cost · $0.05/kWh', color:state.power === 'proxy' ? colors.proxy : colors.cost, rows:floor, width:horizon === 'near' ? 3 : 2},
    ];
    if (state.free) series.push({name:'Unconstrained demand diagnostic',color:colors.free,rows:demand.unconstrained_path || [],width:2});
    if (state.layers && state.power !== 'proxy') {
      const costRows=supply.cost_path || [];
      series.push({name:'Cost +75% illustration',color:'#34d399',rows:costRows.map(p=>({...p,v:p.premium_band_usd})),width:1.5});
      series.push({name:'Electricity only',color:'#fb923c',rows:costRows.map(p=>({...p,v:p.electricity_only_usd})),width:1.5});
      series.push({name:'Legacy SOTA +25% return',color:colors.fees,rows:costRows.filter(p=>p.sota_roic_usd!=null).map(p=>({...p,v:p.sota_roic_usd})),width:1.5});
    }
    const filter = rows => rows.map(p => ({...p, d:p.d || p.date, v:Number(p.v ?? p.all_in_cost_usd)}))
      .filter(p => Number.isFinite(p.v) && p.v > 0 && iso(p.d) >= start && iso(p.d) <= end);
    series.forEach(s => {s.rows=filter(s.rows);});
    const markers = refs(doc).filter(r => r.date && iso(r.date) >= start && iso(r.date) <= end);
    const million = refs(doc).find(r => r.id === 'q3_demand');
    const values=series.flatMap(s=>s.rows.map(p=>p.v)).concat(markers.flatMap(r=>[r.value,r.low,r.high]).filter(v=>v>0));
    if (horizon === 'long' && million) values.push(million.value);
    if (!values.length) return '<p>Price paths are temporarily unavailable.</p>';
    const lo=Math.log10(Math.min(...values))-.08, hi=Math.log10(Math.max(...values))+.16;
    const x=t=>pad.l+(t-start)/(end-start)*(w-pad.l-pad.r);
    const y=v=>pad.t+(hi-Math.log10(v))/(hi-lo)*(h-pad.t-pad.b);
    const line=(rows,color,width,dash,label)=>rows.length ? `<path d="${rows.map((p,i)=>`${i?'L':'M'}${x(iso(p.d)).toFixed(2)},${y(p.v).toFixed(2)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="${width || 2}" ${dash?'stroke-dasharray="7 5"':''}><title>${esc(label)}</title></path>`:'';
    const ticks=[];
    for(let p=Math.floor(lo);p<=Math.ceil(hi);p++) for(const m of [1,2,5]) {const v=m*10**p;if(Math.log10(v)>lo&&Math.log10(v)<hi)ticks.push(v);}
    const tickLabel=v=>v>=1e6?`${num(v/1e6, v%1e6?1:0)}M`:v>=1000?`${num(v/1000,0)}k`:num(v,0);
    const years=[];
    for(let year=new Date(start).getUTCFullYear();year<=2033;year++) {
      const t=iso(year+'-01-01');
      const step=w<600?4:(state.full?2:1);
      if(t>=start&&t<=end&&(year-new Date(start).getUTCFullYear())%step===0)years.push(`<text x="${x(t).toFixed(1)}" y="${h-15}" text-anchor="middle">${year}</text>`);
    }
    const cut=Math.max(start,Math.min(observedEnd,end));
    const forecast=`<rect x="${x(cut)}" y="${pad.t}" width="${Math.max(0,x(end)-x(cut))}" height="${h-pad.t-pad.b}" fill="currentColor" opacity=".035"/><text x="${x(cut)+8}" y="${pad.t+12}">Scenarios →</text>`;
    const paths=series.map(s=> {
      if(s.observedOnly)return line(s.rows,s.color,2.5,false,s.name);
      const historical=s.rows.filter(p=>iso(p.d)<=observedEnd), future=s.rows.filter(p=>iso(p.d)>observedEnd);
      if(historical.length&&future.length)future.unshift(historical[historical.length-1]);
      return line(historical,s.color,s.width,false,s.name+' · history')+line(future,s.color,s.width,true,s.name+' · scenario');
    }).join('');
    const guides=['2028-04-15','2032-04-20'].filter(d=>iso(d)>=start&&iso(d)<=end).map((d,i)=>`<line x1="${x(iso(d))}" x2="${x(iso(d))}" y1="${pad.t}" y2="${h-pad.b}" stroke="currentColor" opacity=".25" stroke-dasharray="3 5"/><text x="${x(iso(d))-6}" y="${h-pad.b-8-(w<600?i*16:0)}" text-anchor="end">${d.slice(0,4)} halving*</text>`).join('');
    const dots=markers.map(r=> {
      const xx=x(iso(r.date)), title=`${r.vintage} · ${r.kind.replace(/_/g,' ')} · ${r.value?usd(r.value):`${usd(r.low)}–${usd(r.high)}`}`;
      return `${r.low&&r.high?`<line x1="${xx}" x2="${xx}" y1="${y(r.low)}" y2="${y(r.high)}" stroke="${colors.reference}" stroke-width="${r.id==='q3_supply'?7:3}" opacity=".5"><title>${esc(title)}</title></line>`:''}${r.value?`<circle cx="${xx}" cy="${y(r.value)}" r="${r.id==='q3_supply'?5:4}" fill="${colors.reference}"><title>${esc(title)}</title></circle>`:''}`;
    }).join('');
    // Q3 specifies a year, not a day: a year-wide guide avoids false precision.
    const yearMarker=horizon==='long'&&million?`<line x1="${x(iso('2033-01-01'))}" x2="${x(end)}" y1="${y(million.value)}" y2="${y(million.value)}" stroke="${colors.reference}" stroke-width="4"><title>HK Q3: approximately $1M by 2033; no precise target day published</title></line><text x="${x(end)-3}" y="${y(million.value)-9}" text-anchor="end" fill="${colors.reference}">HK Q3 ≈ $1M · 2033</text>`:'';
    return `<svg class="btc-model-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Bitcoin observed prices, independent demand fits and production-cost scenarios through ${horizon==='near'?'2028':'2033'}">
      ${forecast}${ticks.map(v=>`<line x1="${pad.l}" x2="${w-pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="currentColor" opacity=".1"/><text x="${pad.l-9}" y="${y(v)+4}" text-anchor="end">$${tickLabel(v)}</text>`).join('')}${years.join('')}${guides}${paths}${dots}${yearMarker}</svg>
      <div class="btc-model-legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}<span><i style="background:${colors.reference}"></i>HK published references</span></div>
      <p class="tier-sub">Log USD scale. Solid lines: historical reconstruction. Dashed lines: scenarios. *Future halving dates are estimates. ${state.power==='proxy'?'Power proxy: US industrial prices indexed to Cambridge’s June-2024 miner survey; retrospective, not an observed global tariff series.':'Power case matches HK’s $0.05/kWh comparison.'}</p>`;
  }
  function render(doc) {
    if(!doc?.demand)return '<details class="wm-panel hk-snowball"><summary>BTC model</summary><p>BTC research context is temporarily unavailable.</p></details>';
    const key=String(doc.generated_at || doc.as_of || 'legacy');
    documents.set(key,doc);
    if(documents.size>12)documents.delete(documents.keys().next().value);
    const d=doc.demand, s=doc.supply || {}, bands=s.bands || {}, fit=d.fit || {};
    const targets=d.horizon_values || [], long=targets.find(p=>p.date==='2033-12-31') || {};
    const near=s.scenarios?.mixed_base?.['2028'] || {};
    const freshness=doc.freshness || {}, now=Date.now();
    const inputs=freshness.inputs || [];
    const stale=inputs.filter(r=>ageStatus(r,now).stale).length;
    const rigs=s.rig_comparison || {}, power=s.electricity_history || {}, fees=s.fees || {};
    const free=d.fit_unconstrained || {}, diag=d.diagnostics || {};
    const table=(headers, rows)=>`<div class="btc-model-table-wrap" tabindex="0"><table class="darwin-table wm-table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
    const cell=value=>`<td>${value}</td>`;
    const row=values=>`<tr>${values.map(cell).join('')}</tr>`;
    const references=refs(doc);
    const referenceRows=references.map(r=>row([source(r.url+'#page='+r.page,r.vintage+' · p. '+r.page),esc(r.kind.replace(/_/g,' ')),esc(r.time_label || (r.year?`By ${r.year} (approximate year)`:r.date)),r.value?usd(r.value):'—',r.low?`${usd(r.low)}–${usd(r.high)}`:'—']));
    const feeRows=(fees.scenarios || []).map(r=>row([esc(r.horizon),esc(r.scenario.replace(/_/g,' ')),num(r.fee_btc_per_block,4),usd(r.production_cost_usd),usd(r.fee_adjusted_breakeven_usd),num(r.fee_share_pct,1)+'%',usd(r.security_revenue_daily_usd),usd(r.price_assumption_usd)]));
    const freshnessRows=inputs.map(r=>{const status=ageStatus(r,now);return row([esc(r.label),esc(r.observed_through || 'Missing'),status.age==null?'—':esc(status.age+' days'),`<span class="badge ${status.stale?'badge-warn':'badge-ok'}">${status.stale?'Stale':'Current'}</span>${r.refresh_error?` · ${esc(r.refresh_error)}`:''}`]);});
    const rigRows=(rigs.rigs || []).map(r=>row([source(r.source_url,r.name),esc(r.cooling || '—'),num(r.j_th_nameplate,1),num(r.th_s,0)+' TH/s / '+num(r.watts,0)+' W',usd(r.equipment_usd_per_th)+' / TH · '+esc(r.price_status.replace(/_/g,' '))+(r.price_date?' · '+esc(r.price_date):''),usd(r.electricity_usd),usd(r.ancillary_opex_usd),usd(r.depreciation_usd),usd(r.required_profit_usd),usd(r.plus_25pct_return_usd)]));
    const rigSens=(rigs.rigs || []).map(r=>row([esc(r.name),usd(r.sensitivities.power_004_usd),usd(r.sensitivities.power_006_usd),usd(r.sensitivities.life_2years_usd),usd(r.sensitivities.utilization_085_usd),usd(r.sensitivities.equipment_price_plus_50pct_usd)]));
    const horizonRows=targets.map(r=>row([esc(r.date),usd(r.constrained_usd),usd(r.unconstrained_usd)]));
    const note=fit.k_constrained?'Exponent is at an imposed bound. The historical data did not select this constrained value.':'Exponent is inside the allowed range.';
    const lenses=`<div class="btc-model-controls" role="group" aria-label="BTC model horizon"><button type="button" class="filter-btn" data-btc-horizon="near" aria-pressed="false">Supply through 2028</button><button type="button" class="filter-btn active" data-btc-horizon="long" aria-pressed="true">Demand through 2033</button><label>Power case <select data-btc-power aria-label="BTC power case"><option value="hk">HK comparison · $0.05/kWh</option><option value="proxy" ${power.cost_path?.length?'':'disabled'}>Historical miner power proxy</option></select></label><label><input type="checkbox" data-btc-free> Show free fit</label><label><input type="checkbox" data-btc-layers> Cost layers (HK power)</label><label><input type="checkbox" data-btc-full> Full history</label></div>`;
    return `<details class="wm-panel hk-snowball btc-model" data-btc-panel="${esc(key)}" open>
      <summary>BTC supply and demand <span class="tier-sub">2028 mining economics · 2033 demand context</span></summary>
      <p class="hk-snowball-lede">Our demand fit and HK’s published outlook are independent. Production cost is dynamic economic support, not a guaranteed minimum price.</p>
      <div class="btc-model-cards">
        <div><span>Production cost now · HK power case</span><strong>${usd(bands.all_in_usd || s.as_of_cost_usd)}</strong><small>Fee-adjusted breakeven ${usd(fees.current_breakeven_usd)} · fleet ${num(s.assumptions?.efficiency_j_th,1)} J/TH</small></div>
        <div><span>Our 2028 supply scenario</span><strong>${usd(near.all_in_usd)}</strong><small>Mixed watts / electricity assumptions · includes halving</small></div>
        <div><span>Our demand · end of 2033</span><strong>${usd(long.constrained_usd)}</strong><small>Free fit ${usd(long.unconstrained_usd)} · k ${num(fit.k)} / ${num(free.k)}</small></div>
        <div class="btc-model-reference"><span>HK Q3 · by 2033</span><strong>≈ $1 million</strong><small>Published reference · ${source(references.find(r=>r.id==='q3_demand')?.url+'#page=5','Q3 letter, p. 5')}</small></div>
      </div>
      <p class="tier-sub"><strong>HK Q3 · April 2028:</strong> ≈ $130,000, range $117,000–$149,000. Q2’s references retain their original dates and cost bases in the comparison below.</p>
      ${lenses}<p class="tier-sub" data-btc-lens>${lensCopy('long')}</p>
      <div data-btc-chart>${chart(doc)}</div>
      <p class="btc-model-fit-note"><strong>Fit boundary:</strong> ${esc(note)} ${esc(d.interpretation || '')}</p>
      <details><summary>Published references and model comparison</summary>
        ${table(['Source','Basis','Horizon','Reference','Range'],referenceRows)}
        <p class="tier-sub">${esc(doc.hk_reference?.interpretation || '')} Q3’s exact model-to-model transition date is not published; the horizon views are our presentation choice.</p>
        ${table(['Our model date','Constrained demand','Unconstrained diagnostic'],horizonRows)}
        <p class="tier-sub">HK’s full demand equation is unavailable. No continuous HK curve has been fabricated. Combining Q2/Q3 anchors gives origin- and date-dependent implied exponents; it is not HK’s fitted exponent.</p>
        ${table(['Illustrative time origin','Illustrative day within 2033','Anchor-implied k'],(diag.hk_anchor_implied?.values || []).map(r=>row([esc(r.origin),esc(r.illustrative_2033_date),num(r.k,3)])))}
      </details>
      <details><summary>Demand fit sensitivity and historical forecast checks</summary>
        <p class="tier-sub">${esc(diag.default_policy || '')} These checks measure historical forecast error; a high in-sample R² is not forecast validation.</p>
        ${table(['Time origin','Fit window starts','Free k','2033 scenario'],(diag.sensitivity || []).map(r=>row([esc(r.origin),esc(r.window_start),num(r.fit?.k,3),usd(r.price_2033)])))}
        ${table(['Training cutoff','Held-out observation','Fit','k','Forecast','Actual','Absolute error'],(diag.one_year_holdouts || []).map(r=>row([esc(r.cutoff),esc(r.target),esc(r.fit_kind),num(r.k,3),usd(r.prediction),usd(r.actual),num(r.absolute_error_pct,1)+'%'])))}
      </details>
      <details><summary>Hardware costs and the $117k–$149k comparison</summary>
        <p class="tier-sub">Legacy SOTA + return: ${usd(bands.sota_roic_usd)}. This uses the 60% power gross-up and a return on equipment capital. The explicit schedule below instead separates cash operating costs, depreciation and return on installed capital.</p>
        ${table(['Manufacturer model','Cooling','J/TH','Rated performance','Equipment price','Electricity / BTC','Other opex / BTC','Depreciation / BTC','25% return / BTC','Total / BTC'],rigRows)}
        <p class="tier-sub">Assumptions: $0.05/kWh; PUE ${num(rigs.assumptions?.pue)}; utilization 95%; ancillary opex 15% of power; three-year straight-line depreciation; zero salvage; installed infrastructure $2/TH air or $5/TH hydro. Return means 25% annually on installed capital, not a 25% price markup. Prices labeled assumptions are not live quotes.</p>
        ${table(['Model','Power $0.04','Power $0.06','Two-year life','85% utilization','Equipment +50%'],rigSens)}
        <p class="tier-sub">${esc(rigs.reconciliation || '')}</p>
        <p class="tier-sub">${esc(rigs.fleet_limitation || '')} Fleet J/TH with 3/5/7-year survival: ${[3,5,7].map(n=>num(s.fleet_survival_sensitivity?.[n],1)).join(' / ')}. Cambridge ${esc(s.cbeci_comparison?.date || 'unavailable')}: ${num(s.cbeci_comparison?.j_th,1)} J/TH versus same-date vintage mix ${num(s.cbeci_comparison?.same_date_mix_j_th,1)} J/TH.</p>
        <ul>${(rigs.rigs || []).map(r=>`<li>${esc(r.name)}: ${esc(r.release_basis || '')}</li>`).join('')}</ul>
      </details>
      <details><summary>Historical power-price proxy</summary>
        <p>${esc(power.label || 'Proxy unavailable')}. Latest ${num(power.latest_usd_kwh,4)} USD/kWh; source observation ${esc(power.through || 'missing')}.</p>
        <p class="tier-sub">${esc(power.method || '')}. ${esc(power.limitations || '')}</p>
        <p class="tier-sub">${(power.sources || []).map(r=>source(r.url,r.series || 'Cambridge miner survey')).join(' · ')}. ${esc(power.release_lag_assumption || '')}</p>
      </details>
      ${doc.criticality?`<details><summary>Log-periodic research diagnostic</summary><p class="tier-sub">${esc(doc.criticality.direction || doc.criticality.status || 'Unavailable')}. ${esc(doc.criticality.reason || doc.criticality.claim || '')} Research context only.</p></details>`:''}
      <details><summary>Fees, breakeven and security revenue</summary>
        <p class="tier-sub">Fees observed ${esc(fees.observed_on || 'unavailable')}: ${usd(fees.fee_usd_per_block)} per block, ${num(fees.fee_btc_per_block,4)} BTC at the dated conversion price (${esc(fees.conversion_price_date || 'unavailable')}). ${esc(fees.issuance_note || '')}</p>
        ${table(['Horizon','Fee scenario','BTC fees / block','Cost / issued BTC','Fee-adjusted breakeven','Fee share','Security revenue / day','Assumed BTC price'],feeRows)}
        <p class="tier-sub">${esc(fees.assumptions || '')}</p>
        <p class="tier-sub">${esc(fees.historical_data_note || '')}</p>
      </details>
      <details ${stale?'open':''}><summary>Data freshness · ${stale?stale+' inputs stale':'inputs current'}</summary>
        <p class="tier-sub">Snapshot built ${esc(doc.as_of)}; spot observed ${esc(doc.spot?.observed_on || doc.as_of)}. Ages below are evaluated when this panel is rendered.</p>
        ${table(['Input','Observed through','Age','Status'],freshnessRows)}
        ${freshness.cost_refresh?.power_history?.refresh_error?`<p class="tier-sub">Power refresh failed; dated cache retained: ${esc(freshness.cost_refresh.power_history.refresh_error)}</p>`:''}
      </details>
      <p class="tier-sub">${esc(s.dynamic_support_note || '')} Context only. No valuation authority. Not a trade signal. Not in base IRR.</p>
    </details>`;
  }
  function attach(container) {
    container.querySelectorAll('[data-btc-panel]').forEach(root=> {
      if(root.dataset.btcBound)return;
      root.dataset.btcBound='true';
      const doc=documents.get(root.getAttribute('data-btc-panel'));
      if(!doc)return;
      const state={horizon:'long',power:'hk',free:false,full:false,layers:false};
      const redraw=()=> {state.width=Math.max(280,Math.min(960,root.querySelector('[data-btc-chart]').clientWidth));root.querySelector('[data-btc-chart]').innerHTML=chart(doc,state);root.querySelector('[data-btc-lens]').textContent=lensCopy(state.horizon);};
      redraw();
      if(typeof ResizeObserver!=='undefined') {
        const observer=new ResizeObserver(()=> {
          if(!root.isConnected){observer.disconnect();return;}
          const width=Math.max(280,Math.min(960,root.querySelector('[data-btc-chart]').clientWidth));
          if(width!==state.width)redraw();
        });
        observer.observe(root);
      }
      root.addEventListener('click',event=> {
        const button=event.target.closest('[data-btc-horizon]');
        if(!button)return;
        event.preventDefault();
        state.horizon=button.dataset.btcHorizon;
        root.querySelectorAll('[data-btc-horizon]').forEach(b=> {b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
        redraw();
      });
      root.addEventListener('change',event=> {
        if(event.target.matches('[data-btc-power]'))state.power=event.target.value;
        if(event.target.matches('[data-btc-free]'))state.free=event.target.checked;
        if(event.target.matches('[data-btc-full]'))state.full=event.target.checked;
        if(event.target.matches('[data-btc-layers]'))state.layers=event.target.checked;
        redraw();
      });
    });
  }
  const api={render,attach,chart,ageStatus};
  global.BTCModelViz=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
