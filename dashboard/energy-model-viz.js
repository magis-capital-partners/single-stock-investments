/* Public gas → power → BTC research workspace. No external chart dependencies. */
(function (root) {
  'use strict';
  let model = null, bridge = null, refreshStatus = null;
  const state = {scenario: 'reference', year: '2030', region: 'ercot', linked: false, dynamic: false, search: ''};
  const colors = {reference: '#60a5fa', letter: '#fbbf24', relief: '#34d399', stress: '#fb7185'};
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (value, digits = 1) => Number.isFinite(value) ? value.toLocaleString('en-US', {minimumFractionDigits:digits, maximumFractionDigits:digits}) : '—';
  const usd = (value, digits = 0) => Number.isFinite(value) ? '$' + num(value, digits) : '—';
  const url = value => /^https:\/\//.test(String(value)) ? esc(value) : '#';
  const sourceLink = (source, label) => `<a href="${url(source)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  const atYear = rows => (rows || []).find(r => r.period === state.year + '-12') || (rows || []).filter(r => r.period.startsWith(state.year)).slice(-1)[0];
  const bridgeOK = () => Boolean(bridge && bridge.available && bridge.schema_version === '1.0' && bridge.model_id === model.model_id && bridge.in_base_irr === false);
  const metric = (label, value, note) => `<div class="em-metric"><label>${esc(label)}</label><div class="em-number">${value}</div><small>${esc(note)}</small></div>`;
  function chart(series, unit, title, zero = true) {
    const points = series.flatMap(s => s.points).filter(p => Number.isFinite(p.v));
    if (!points.length) return '<p class="em-note">No data available for this comparison.</p>';
    const periods = [...new Set(points.map(p => p.period))].sort();
    const values = points.map(p => p.v);
    const low = zero ? Math.min(0, ...values) : Math.min(...values) * .92;
    const high = Math.max(...values) * 1.08 || 1, range = high - low || 1;
    const w = 560, h = 220, l = 55, r = 12, t = 18, b = 30;
    const x = p => l + periods.indexOf(p) * (w-l-r) / Math.max(1, periods.length-1);
    const y = v => h-b - (v-low) * (h-t-b) / range;
    let svg = `<svg class="em-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(title)}"><title>${esc(title)} (${esc(unit)})</title>`;
    for (let i=0;i<4;i++) {
      const v=low+range*i/3, yy=y(v);
      svg += `<line x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}" stroke="#23314a"/><text x="${l-8}" y="${yy+4}" text-anchor="end">${esc(Math.abs(v)>=10000?num(v/1000,0)+'k':num(v,Math.abs(v)<10?1:0))}</text>`;
    }
    const ticks = [...new Set([0, Math.floor((periods.length-1)/3), Math.floor(2*(periods.length-1)/3), periods.length-1])];
    ticks.forEach(i => { svg += `<text x="${x(periods[i])}" y="${h-8}" text-anchor="middle">${esc(periods[i])}</text>`; });
    series.forEach(s => {
      const valid = s.points.filter(p => Number.isFinite(p.v));
      svg += `<path d="${valid.map((p,i)=>(i?'L':'M')+x(p.period).toFixed(1)+','+y(p.v).toFixed(1)).join(' ')}" fill="none" stroke="${s.color}" stroke-width="${s.width||2}" ${s.dash?'stroke-dasharray="5 4"':''}/>`;
      valid.forEach(p => { svg += `<circle cx="${x(p.period)}" cy="${y(p.v)}" r="4" fill="transparent"><title>${esc(s.label)} · ${esc(p.period)}: ${num(p.v,2)} ${esc(unit)}</title></circle>`; });
    });
    return svg + '</svg><div class="em-legend">' + series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join('') + '</div>';
  }
  const series = (label, rows, key, color, extras={}) => ({label, points:rows.map(r=>({period:r.period,v:r[key]})),color,...extras});
  function assetRows(kind) {
    const all = kind === 'lng' ? (model.assets.lng || {}).trains || [] : (model.assets.gas_generators || {}).planned || [];
    return all.filter(r => JSON.stringify(r).toLowerCase().includes(state.search.toLowerCase()));
  }
  function assetTable(kind) {
    const rows = assetRows(kind);
    const lng = kind === 'lng';
    return `<div class="em-asset-count">${rows.length} matching ${lng?'LNG trains':'planned gas generators'} · showing up to 80 · export includes all records</div><div class="em-table-scroll"><table class="em-table"><thead><tr><th>${lng?'Project / train':'Plant / generator'}</th><th>State</th><th>${lng?'Baseload Bcf/day':'Nameplate MW'}</th><th>Reported start</th><th>Status</th></tr></thead><tbody>${rows.slice(0,80).map(r=>`<tr><td>${esc(lng?r.id:r.plant+' / '+r.generator)}</td><td>${esc(r.state)}</td><td class="num">${num(lng?r.baseload_bcf_day:r.nameplate_mw,lng?2:0)}</td><td>${esc(r.start_period||'Undated')}${lng && r.date_precision!=='reported_month'?' (window end)':''}</td><td>${esc(r.status)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function body() {
    if (!model || model.schema_version !== '1.0' || !Array.isArray(model.scenarios) || !model.scenarios.length) return `<div class="em-empty"><h3>Energy → Power → BTC</h3><p class="em-note">Energy data is temporarily unavailable. The BTC model below remains available.</p><button class="em-btn" data-em-action="retry">Retry energy data</button></div>`;
    const scenario = model.scenarios.find(s=>s.id===state.scenario) || model.scenarios[0];
    state.scenario = scenario.id;
    const row = atYear(scenario.rows), latest = model.history[model.history.length-1];
    const powerPoint = atYear(scenario.power), region = powerPoint.regions.find(r=>r.region===state.region) || powerPoint.regions[0];
    const ok = bridgeOK(), linked = ok && state.linked;
    const costRows = ok ? (bridge.scenarios.find(s=>s.id===scenario.id)||{}).rows||[] : [];
    const cost = atYear(costRows);
    const asset = atYear(scenario.asset_comparison.rows);
    const annual = scenario.summary.annual.find(r=>String(r.year)===state.year);
    const warnings = [...(model.warnings||[])];
    if (refreshStatus && refreshStatus.status === 'failed') warnings.push('The last energy refresh failed. Showing the last published results from ' + model.as_of + '. ' + (refreshStatus.error || ''));
    const modelAge = (Date.now() - Date.parse(model.as_of + 'T00:00:00Z')) / 86400000;
    if (modelAge > 14) warnings.push('These energy results are more than 14 days old. Review the source dates before using the scenarios.');
    if (bridge && bridge.model_id !== model.model_id) warnings.push('The energy and BTC files come from different builds. The cost overlay is disabled until they match.');
    if (!ok) warnings.push((bridge||{}).reason || 'The optional BTC energy overlay is unavailable.');
    const storageSeries = [series('Observed US storage',model.history.filter(r=>r.period>='2019-01'),'working_storage','#b7c3d7')];
    model.scenarios.forEach(s=>storageSeries.push(series(s.label,s.rows,'working_storage',colors[s.id],{width:s.id===scenario.id?3:1,dash:s.id!==scenario.id})));
    const years=[...new Set(scenario.rows.map(r=>r.period.slice(0,4)))];
    const options=(rows,value,label,key)=>rows.map(r=>`<option value="${esc(r[key])}" ${String(r[key])===String(value)?'selected':''}>${esc(r[label])}</option>`).join('');
    return `<header class="em-head"><div><div class="em-eyebrow">World Model / Energy systems</div><h3>Gas balance. Power cost. Bitcoin.</h3><p>Explore four gas scenarios and trace how electricity prices could affect Bitcoin mining costs.</p></div><span class="em-tag assumed">Research scenarios · outside base IRR</span></header>
      <div class="em-tools"><label>Scenario<select data-em-control="scenario" aria-label="Energy scenario">${options(model.scenarios,state.scenario,'label','id')}</select></label><label>Year-end view<select data-em-control="year" aria-label="Energy projection year">${years.map(y=>`<option ${y===state.year?'selected':''}>${y}</option>`).join('')}</select></label><label>Power region<select data-em-control="region" aria-label="Power region">${options(model.power_regions,state.region,'label','id')}</select></label><label class="em-check"><input type="checkbox" data-em-control="linked" ${linked?'checked':''} ${!ok?'disabled':''}>Apply energy to BTC comparison</label></div>
      <div class="em-body">${warnings.length?`<div class="em-warning" role="status">${warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</div>`:''}
      <p class="em-note"><strong>${esc(scenario.label)}</strong> · ${esc(scenario.description)} Values below are December ${esc(state.year)} scenarios. Observed national gas data ends ${esc(latest.period)}. The region control changes the displayed power price; mining costs use the full assumed regional mix.</p>
      <p class="em-caption">LATEST OBSERVED · US dry production ${num(latest.dry_production,1)} Bcf/day · LNG exports ${num(latest.lng_exports,1)} Bcf/day · working storage ${num(latest.working_storage,0)} Bcf · ${esc(latest.period)}</p>
      ${model.weekly_storage?`<p class="em-caption">${sourceLink(model.weekly_storage.source_url,'WEEKLY STORAGE')} · Lower 48 ${num(model.weekly_storage.total.working_storage_bcf,0)} Bcf on ${esc(model.weekly_storage.total.period)} · ${num(model.weekly_storage.total.vs_five_year_pct,1)}% vs five-year average · ${model.weekly_storage.stale?'stale release':'released '+esc(model.weekly_storage.published_at)}. Different geography; not spliced into the US monthly model.</p>`:''}
      <div class="em-metrics">${metric('Dry gas production',num(row.dry_production)+' <small>Bcf/day</small>','December exit rate · scenario')}${metric('Total gas balance',num(row.balance_bcf_day)+' <small>Bcf/day</small>','Supply less domestic use and exports')}${metric('Working storage',num(row.working_storage,0)+' <small>Bcf</small>','US total · operating limits applied')}${metric('Unserved demand',num(annual.unmet_demand_bcf,0)+' <small>Bcf</small>','Whole selected year · before market response')}</div>
      <div class="em-flow"><div><span>Henry Hub gas · assumed</span><strong>${usd(row.henry_hub_usd_mmbtu,2)} / MMBtu</strong><span>Explicit scenario price path</span></div><div><span>${esc(region.label)} wholesale · modeled</span><strong>${usd(region.wholesale_usd_mwh,1)} / MWh</strong><span>Regional heat rate and pass-through</span></div><div><span>Global miner tariff · assumed mix</span><strong>${cost?num((linked?cost.effective_power_usd_kwh:bridge.parameters.baseline_usd_kwh)*100,2):'—'} ¢ / kWh</strong><span>${linked?'Contracts and regional exposure':'Fixed baseline · overlay is off'}</span></div><div><span>Total mining cost · modeled</span><strong>${cost?usd(linked?cost.total_cost_usd_btc:cost.baseline_total_cost_usd_btc):'—'} / BTC</strong><span>${linked?'Electricity changes; other costs separate':'Baseline power with hash / efficiency path'}</span></div></div>
      <div class="em-grid"><div class="em-card"><h4>Storage shows the pressure point</h4><p class="em-note">${scenario.summary.first_shortfall?'First unmet demand: '+esc(scenario.summary.first_shortfall):'No modeled unmet demand through 2032'}. Storage stops at the assumed operating minimum; shortages remain explicit.</p>${chart(storageSeries,'Bcf','US gas storage scenarios')}</div><div class="em-card"><h4>Supply meets a seasonal demand curve</h4><p class="em-note">Bcf/day. Historical seasonality shapes the published near-term outlook and longer-term assumptions.</p>${chart([series('Supply',scenario.rows,'supply_bcf_day','#34d399'),series('Demand',scenario.rows,'demand_bcf_day','#fbbf24')],'Bcf/day','Scenario gas supply and demand',false)}</div></div>
      <div class="em-grid"><div class="em-card"><h4>What changes for Bitcoin</h4><p class="em-note">Constant BTC price and fees. Halvings change issuance; efficiency and hashrate follow stated assumptions. The BTC demand curve below is unchanged.</p>${chart(costRows.length?[series('Baseline power',costRows,'baseline_total_cost_usd_btc','#94a3b8'),...(linked?[series('Energy-linked total',costRows,'total_cost_usd_btc','#34d399'),series('Electricity only',costRows,'electricity_cost_usd_btc','#60a5fa')]:[])]:[],'USD/BTC','Bitcoin mining cost sensitivity')}<p class="em-note">${cost && linked?`Energy adds ${usd(cost.cost_delta_usd_btc)} per BTC (${num(cost.cost_delta_pct)}%) in December ${esc(state.year)}.`:'Enable the energy comparison to see its incremental effect.'} Mining cost is not a BTC price floor.</p></div><div class="em-card"><h4>Project inventory cross-check</h4><div class="em-metrics" style="grid-template-columns:1fr 1fr;margin:14px 0">${metric('LNG baseload',num(asset.reported_lng_baseload_bcf_day,1),'Bcf/day · reported, dated trains')}${metric('Planned gas generation',num(asset.planned_gas_generator_mw == null ? null : asset.planned_gas_generator_mw/1000,1),'GW · cumulative planned additions')}</div><p class="em-note">At ${num(scenario.assumptions.project_utilization*100,0)}% utilization, dated LNG capacity supports ${num(asset.lng_utilized_output_bcf_day,1)} Bcf/day of LNG output versus ${num(row.lng_exports,1)} Bcf/day in this export scenario. Feedgas and LNG output differ.</p><p class="em-note">Reported planned gas generators imply ${num(asset.illustrative_generator_burn_bcf_day,1)} Bcf/day at assumed 50% dispatch and 7.5 MMBtu/MWh. This cross-check is not added a second time to national demand.</p><p class="em-caption">Project delay assumption: ${scenario.assumptions.project_delay_months} months. Reported dates are estimates, not commitments.</p></div></div>
      <h4>Compare all four cases · December ${esc(state.year)}</h4><div class="em-table-scroll"><table class="em-table"><thead><tr><th>Scenario</th><th>Production Bcf/d</th><th>LNG exports Bcf/d</th><th>Storage Bcf</th><th>Unserved Bcf / year</th><th>Energy cost Δ / BTC</th></tr></thead><tbody>${model.scenarios.map(s=>{const p=atYear(s.rows),a=s.summary.annual.find(v=>String(v.year)===state.year),c=ok?atYear((bridge.scenarios.find(v=>v.id===s.id)||{}).rows):null;return `<tr class="${s.id===scenario.id?'selected':''}"><td>${esc(s.label)}</td><td class="num">${num(p.dry_production)}</td><td class="num">${num(p.lng_exports)}</td><td class="num">${num(p.working_storage,0)}</td><td class="num">${num(a.unmet_demand_bcf,0)}</td><td class="num">${c?usd(c.cost_delta_usd_btc):'—'}</td></tr>`;}).join('')}</tbody></table></div><p class="em-caption">The comparison always reports each case’s conditional energy effect; the switch controls the selected BTC chart. Cases are hypotheses with no assigned probabilities.</p>
      <details class="em-details"><summary>Power contracts and miner exposure</summary><p class="em-note">Verified contract coverage: ${ok?bridge.verified_contract_coverage_pct:0}%. These cohorts are stated research assumptions, not a survey of the Bitcoin network. Unknown foreign exposure is held at its baseline tariff.</p><div class="em-table-scroll"><table class="em-table"><thead><tr><th>Cohort</th><th>Hash share</th><th>Fixed share at year-end</th><th>Assumed expiry</th><th>Modeled tariff</th><th>Evidence</th></tr></thead><tbody>${ok?bridge.miner_cohorts.map(c=>{const x=cost.cohorts.find(v=>v.id===c.id);return `<tr><td>${esc(c.label)}</td><td class="num">${num(c.hash_share*100,0)}%</td><td class="num">${num(x.fixed_share*100,0)}%</td><td>${esc(c.contract_end)}</td><td class="num">${num(x.effective_usd_kwh*100,2)} ¢/kWh</td><td>${esc(c.status.replaceAll('_',' '))}</td></tr>`;}).join(''):'<tr><td colspan="6">BTC bridge unavailable.</td></tr>'}</tbody></table></div><label class="em-check"><input type="checkbox" data-em-control="dynamic" ${state.dynamic?'checked':''}> Show experimental shutdown sensitivity</label>${state.dynamic && cost?`<div class="em-warning">Under the constant BTC price assumption, ${num(cost.network_response.curtailed_hash_share*100,1)}% of illustrative hash share cannot cover modeled operating costs. Immediate block rate: ${num(cost.network_response.immediate_blocks_per_day,1)}/day; after a hypothetical completed difficulty adjustment: ${num(cost.network_response.after_retarget_blocks_per_day,0)}/day. This two-state experiment does not predict shutdown timing, re-entry, or migration.</div>`:''}</details>
      <details class="em-details" data-em-detail="assets"><summary>LNG trains and planned gas generators</summary><p class="em-note">${sourceLink((model.assets.lng||{}).source_url,'LNG source workbook')} · ${sourceLink((model.assets.gas_generators||{}).source_url,'Generator source workbook')}. Undated approved LNG projects are excluded from the capacity path.</p><input class="em-search" data-em-control="search" aria-label="Search energy projects" placeholder="Search project, state, operator, or status" value="${esc(state.search)}"><div data-em-assets>${assetTable('lng')}${assetTable('generators')}</div></details>
      <details class="em-details"><summary>Assumptions, equations, and validation</summary><div class="em-methods"><div><h4>Gas conservation</h4><p class="em-note"><code>Storage change = (supply − demand) × days + unmet demand − excess supply</code></p><p class="em-note">Working-capacity assumption: ${num(model.storage_parameters.working_capacity_bcf,0)} Bcf, rising to ${num(model.storage_parameters.capacity_2030_bcf,0)} Bcf. Minimum: ${num(model.storage_parameters.operating_minimum_bcf,0)} Bcf. Historical statistical differences remain visible in the export.</p><h4>Power and mining</h4><p class="em-note"><code>Fuel cost ($/MWh) = gas ($/MMBtu) × heat rate (MMBtu/MWh)</code><br><code>kWh/day = EH/s × effective J/TH × 24,000</code><br><code>Total cost/BTC = (electricity + separate nonpower cost) / issued BTC</code></p><p class="em-note">PUE is included once in effective J/TH. Fees affect revenue and revenue breakeven, not physical cost. Network hashrate is already realized; availability is not applied twice.</p></div><div><h4>Validation status: research</h4><p class="em-note">${model.validation.n_months} observed months. Historical reconciliation residual MAE: ${num(model.validation.statistical_difference_mae_bcf,1)} Bcf/month. Seasonal naive storage benchmark MAE: ${num(model.validation.seasonal_naive_storage_mae_bcf,0)} Bcf. Neither establishes predictive skill.</p>${model.limitations.map(v=>`<p class="em-note">• ${esc(v)}</p>`).join('')}<p class="em-note">${sourceLink(model.reference.source_url,model.reference.label)} published ${esc(model.reference.published_at)}. The 132 Bcf/day production ceiling and LNG path are scenario assumptions; proprietary well and acreage data were not reproduced.</p></div></div><div class="em-table-scroll"><table class="em-table"><thead><tr><th>Parameter</th><th>Selected value</th><th>Basis</th></tr></thead><tbody>${Object.entries(scenario.assumptions.terminal_2030).map(([k,v])=>`<tr><td>${esc(k.replaceAll('_',' '))}</td><td class="num">${num(v,2)} Bcf/day</td><td>2030 scenario anchor${['dry_production','lng_exports'].includes(k)?' · December exit':' · annualized'}</td></tr>`).join('')}${ok?Object.entries(bridge.parameters).filter(([k,v])=>typeof v==='number').map(([k,v])=>`<tr><td>${esc(k.replaceAll('_',' '))}</td><td class="num">${num(v,4)}</td><td>BTC sensitivity assumption</td></tr>`).join(''):''}</tbody></table></div></details>
      <details class="em-details"><summary>What would weaken the scarcity thesis?</summary><p class="em-note">Research review conditions, not automatic investment signals. Review at each monthly balance update; thresholds are analyst choices and persistence requires accumulated observations.</p><div class="em-table-scroll"><table class="em-table"><thead><tr><th>Condition</th><th>Metric</th><th>Review trigger</th></tr></thead><tbody>${(model.falsification||[]).map(r=>`<tr><td>${esc(r.condition)}</td><td>${sourceLink(r.source_url,r.metric)}</td><td>${esc(r.threshold)}</td></tr>`).join('')}</tbody></table></div></details>
      <details class="em-details"><summary>Data sources and release dates</summary><p class="em-note">Current revised history; each row retains its acquisition and publication vintage. Dates are not backfilled to create a historical information set.</p><div class="em-table-scroll"><table class="em-table"><thead><tr><th>Series</th><th>Latest month</th><th>Published</th><th>Units</th><th>Status</th></tr></thead><tbody>${model.sources.map(s=>`<tr><td>${sourceLink(s.source_url,s.label)}</td><td>${esc(s.latest_period)}</td><td>${esc(s.published_at)}</td><td>${esc(s.unit.replaceAll('_',' '))}</td><td>${s.stale?'Stale':'Observed · revised'}</td></tr>`).join('')}</tbody></table></div>${ok?`<p class="em-note">BTC input observation dates: ${Object.entries(bridge.snapshot.dates).map(([k,v])=>esc(k.replaceAll('_',' '))+': '+esc(v||'missing')).join(' · ')}.</p>`:''}</details>
      <footer class="em-footer"><div class="em-caption">Built ${esc(model.as_of)} · model ${esc(model.model_version)} · ${esc(model.model_id)}<br>Scenario prices and costs inform research; they do not alter the BTC demand fit or base IRR.</div><div class="em-actions"><a class="em-btn" data-em-export="csv" href="data/energy_exports/${esc(state.scenario)}.csv" download="energy-${esc(state.scenario)}-${esc(model.as_of)}.csv">Export selected case</a><a class="em-btn" data-em-export="json" href="data/energy_exports/full_model.json" download="energy-model-${esc(model.as_of)}.json">Export full model</a><button class="em-btn" data-em-action="retry">Reload data</button></div></footer></div>`;
  }
  function render(doc, overlay, refresh) {
    model=doc;bridge=overlay;refreshStatus=refresh;
    let content;
    try { content=body(); }
    catch(error) { console.warn('Energy artifact is incomplete; preserving the BTC view.',error);model=null;bridge=null;content=body(); }
    return `<section class="energy-model" id="energy-model-panel" aria-label="Energy and Bitcoin model">${content}</section>`;
  }
  function bind(container) {
    const panel=container.querySelector('#energy-model-panel');
    if(!panel||panel.dataset.bound)return;
    panel.dataset.bound='true';
    function update(key) {
      const open=[...panel.querySelectorAll('details')].map(d=>d.open);
      panel.innerHTML=body();
      panel.querySelectorAll('details').forEach((d,i)=>d.open=Boolean(open[i]));
      const control=panel.querySelector(`[data-em-control="${key}"]`);if(control)control.focus();
    }
    panel.addEventListener('change',event=>{
      const key=event.target.dataset.emControl;if(!key||key==='search')return;
      state[key]=event.target.type==='checkbox'?event.target.checked:event.target.value;update(key);
    });
    panel.addEventListener('input',event=>{
      if(event.target.dataset.emControl!=='search')return;
      state.search=event.target.value;
      const target=panel.querySelector('[data-em-assets]');if(target)target.innerHTML=assetTable('lng')+assetTable('generators');
    });
    panel.addEventListener('click',event=>{
      const button=event.target.closest('[data-em-action]');if(!button)return;
      const action=button.dataset.emAction;
      if(action==='retry'){root.dispatchEvent(new CustomEvent('energy-model-retry'));return;}
    });
  }
  const api={render,bind};
  root.EnergyModelViz=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
