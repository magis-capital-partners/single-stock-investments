/* Focused stock briefs. All valuation figures come from the existing published decision. */
(function (global) {
  'use strict';
  const tabs = [['overview','Summary'],['financials','Financials'],['business','Business & KPIs'],['valuation','Valuation'],['sources','Research'],['updates','Risks & updates']];
  const states = new Map();
  const charts = new WeakMap();
  const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clean = value => String(value ?? '').replace(/\*\*|\[(Fact|Inference|Assumption)\]/g,'').replace(/_/g,' ').trim();
  const dateLabel = value => {const parsed=new Date(value);return value&&Number.isFinite(+parsed)?new Intl.DateTimeFormat(undefined,{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}).format(parsed):'Date unavailable';};
  const isPilot = value => typeof value==='string' ? value.length>0 : value?.one_pager?.schema_version==='stock-one-pager.v1';
  const validTab = value => tabs.some(([id])=>id===value)?value:({models:'valuation',buyback:'business',evidence:'sources',summary:'overview',risks:'updates'})[value]||'overview';
  function state(t) {if(!states.has(t.ticker))states.set(t.ticker,{frequency:t.one_pager.financials.series.some(r=>r.annual?.length)?'annual':'quarterly',statement:'income',history:'recent',metric:t.one_pager.profile.chart_metrics.find(id=>seriesOf(t,id)),case:'base'});return states.get(t.ticker);}
  function format(value,unit='USD',compact=false) {
    if(numeric(value)===null)return value!=null&&typeof value==='object'?JSON.stringify(value):'—';
    if(unit==='percent')return new Intl.NumberFormat(undefined,{maximumFractionDigits:1}).format(value)+'%';
    if(unit==='ratio')return new Intl.NumberFormat(undefined,{maximumFractionDigits:1}).format(value*100)+'%';
    if(/^[A-Z]{3}(\/shares|_per_share)$/.test(unit))return new Intl.NumberFormat(undefined,{style:'currency',currency:unit.slice(0,3),maximumFractionDigits:2}).format(value);
    return new Intl.NumberFormat(undefined,{maximumFractionDigits:2,notation:compact?'compact':'standard'}).format(value);
  }
  function source(ref,h,label='Source') {
    const raw=typeof ref==='string'?ref:ref?.url||ref?.ref;
    const url=global.SourceLinks?global.SourceLinks.reference(raw):/^https?:\/\//.test(raw||'')?raw:null;
    return url?h.linkHtml(url,esc(label)):`<span class="sp-muted">${esc(label)} unavailable</span>`;
  }
  function seriesOf(t,id) {return t.one_pager?.financials?.series?.find(row=>row.id===id);}
  function pointsOf(t,id,frequency='annual') {
    const row=seriesOf(t,id);if(!row)return [];
    if(frequency!=='ttm')return row[frequency]||[];
    if(row.statement==='balance')return row.quarterly||[];
    if(row.unit==='percent') {
      if(id==='operating_margin') {
        const numerator=new Map(pointsOf(t,'operating_income','ttm').map(p=>[p.period,p]));
        return pointsOf(t,'revenue','ttm').filter(p=>p.value&&numerator.has(p.period)).map(p=>({...p,value:numerator.get(p.period).value/p.value*100}));
      }
      return [];
    }
    const observations=row.quarterly||[],result=[];
    for(let i=3;i<observations.length;i++) {
      const group=observations.slice(i-3,i+1);
      const indices=group.map(p=>{const d=new Date(p.period);return d.getUTCFullYear()*4+Math.floor(d.getUTCMonth()/3);});
      if(!indices.every((x,j)=>!j||x-indices[j-1]===1))continue;
      let value=group.reduce((sum,p)=>sum+p.value,0);
      if(row.unit==='shares') {
        if(!group.every(p=>p.start))continue;
        const days=group.map(p=>(new Date(p.period)-new Date(p.start))/86400000+1);
        value=group.reduce((sum,p,j)=>sum+p.value*days[j],0)/days.reduce((a,b)=>a+b,0);
      }
      result.push({...group[3],value,basis:row.unit==='shares'?'TTM weighted average':'Four consecutive quarters',source_refs:group.map(p=>p.source)});
    }
    return result;
  }
  function periodLabel(period,frequency,t) {
    if(frequency==='annual')return 'FY '+period.slice(0,4);
    return dateLabel(period)+(frequency==='ttm'?' TTM':'');
  }
  const isMoney = unit => /^[A-Z]{3}$/.test(unit||'');
  const axisUnit = unit => isMoney(unit)?unit+' millions':unit==='shares'?'Millions of shares':unit;
  const modelUnit = t => (t.one_pager.model.currency||t.units?.currency||t.shared_forecast?.quote?.currency||'USD')+'/shares';
  function chart(t,id,h,options={}) {
    const s=state(t),row=seriesOf(t,id),frequency=options.frequency||s.frequency;
    let points=pointsOf(t,id,frequency);if(s.history!=='all')points=points.slice(frequency==='annual'?-5:-12);
    if(!row||!points.length)return '<p class="sp-empty">No comparable sourced history is available for this metric.</p>';
    const caption=options.title||row.label;
    return `<figure class="sp-chart"><figcaption><strong>${esc(caption)}</strong><span>${esc(axisUnit(row.unit))} · ${esc(frequency==='ttm'?'Trailing twelve months':frequency==='annual'?'Fiscal years':'Fiscal quarters')}</span></figcaption><div class="sp-canvas"><canvas data-sp-chart="${esc(id)}" data-sp-frequency="${frequency}" role="img" aria-label="${esc(caption+' from '+points[0].period+' to '+points.at(-1).period+'; exact values and sources follow')}"></canvas></div><details class="sp-values"><summary>Values & sources</summary><div class="sp-table-scroll"><table><thead><tr><th scope="col">Period</th><th scope="col">Value (${esc(row.unit)})</th><th scope="col">Source</th></tr></thead><tbody>${points.map(p=>`<tr><th scope="row">${esc(periodLabel(p.period,frequency,t))}</th><td>${esc(format(p.value,row.unit))}</td><td>${source(p.source,h)}<small>${esc(p.basis||'Reported')}</small></td></tr>`).join('')}</tbody></table></div></details></figure>`;
  }
  function chartData(t,id,frequency) {
    const s=state(t),row=seriesOf(t,id);let points=pointsOf(t,id,frequency);
    if(s.history!=='all')points=points.slice(frequency==='annual'?-5:-12);
    const scale=isMoney(row?.unit)||row?.unit==='shares'?1e6:1;
    return {row,points,scale};
  }
  function metricSummary(t,ids,h) {
    return `<dl class="sp-metrics">${ids.map(id=>{const row=seriesOf(t,id);const annual=pointsOf(t,id,'annual'),frequency=annual.length?'annual':'quarterly';const points=annual.length?annual:pointsOf(t,id,'quarterly');const p=points.at(-1);return row&&p?`<div><dt>${esc(row.label)}</dt><dd>${esc(format(p.value,row.unit,true))}${isMoney(row.unit)?' <small>'+esc(row.unit)+'</small>':''}</dd><small>${esc(periodLabel(p.period,frequency,t))} · ${source(p.source,h)}</small></div>`:'';}).join('')}</dl>`;
  }
  function intro(title,body) {return `<div class="sp-section-heading"><h3>${esc(title)}</h3>${body?`<p>${esc(body)}</p>`:''}</div>`;}
  function summary(t,h) {
    const p=t.one_pager,profile=p.profile;
    const first=profile.chart_metrics.find(id=>seriesOf(t,id));
    const question=p.risks[0]||profile.countercase;
    return `<p class="sp-eyebrow">${esc(profile.type)}</p>${intro('The business',profile.description)}<div class="sp-reading-grid"><section>${intro('What needs to be true',profile.focus)}<p class="sp-counter"><strong>The counterargument.</strong> ${esc(profile.countercase)}</p><button type="button" class="sp-text-link" data-rw-go="business">Understand the business drivers</button></section><section class="sp-question"><h3>What to watch</h3><p>${esc(typeof question==='string'?question:question.falsifier||question.description||profile.countercase)}</p><button type="button" class="sp-text-link" data-rw-go="updates">Risks and latest developments</button></section></div>${metricSummary(t,profile.kpis.filter(id=>{const r=seriesOf(t,id),p=(r?.annual?.length?r.annual:r?.quarterly)?.at(-1);return p&&(!t.one_pager.financials.latest_period||(new Date(t.one_pager.financials.latest_period)-new Date(p.period))/86400000<730);}).slice(0,3),h)}${global.StockPerformance?.render(t,h)||''}<div class="sp-reading-grid sp-summary-figures"><section>${global.ResearchWorkspace?.range(t,h)||''}<button type="button" class="sp-text-link" data-rw-go="valuation">Explore the valuation and assumptions</button></section><section>${first?chart(t,first,h,{frequency:pointsOf(t,first,'annual').length?'annual':'quarterly'}):''}<button type="button" class="sp-text-link" data-rw-go="financials">All financial statements and history</button></section></div><section class="sp-essential" data-company-library="summary"></section>`;
  }
  function financialControls(t) {
    const s=state(t);
    return `<div class="sp-controls"><label>Period<select data-sp-control="frequency">${[['annual','Annual'],['quarterly','Quarterly'],['ttm','Trailing twelve months']].map(([v,l])=>`<option value="${v}"${s.frequency===v?' selected':''}>${l}</option>`).join('')}</select></label><label>Statement<select data-sp-control="statement">${[['income','Income statement'],['balance','Balance sheet'],['cashflow','Cash flow']].map(([v,l])=>`<option value="${v}"${s.statement===v?' selected':''}>${l}</option>`).join('')}</select></label><label>History<select data-sp-control="history"><option value="recent"${s.history==='recent'?' selected':''}>Recent history</option><option value="all"${s.history==='all'?' selected':''}>All available history</option></select></label></div>`;
  }
  function financialTable(t,h) {
    const s=state(t),rows=t.one_pager.financials.series.filter(r=>r.statement===s.statement);
    let periods=[...new Set(rows.flatMap(r=>pointsOf(t,r.id,s.frequency).map(p=>p.period)))].sort();
    if(s.history!=='all')periods=periods.slice(s.frequency==='annual'?-5:-12);
    if(!periods.length)return '<p class="sp-empty">No sourced statement history is available for this selection.</p>';
    return `<div class="sp-table-scroll" role="region" aria-label="Financial statement history" tabindex="0"><table class="sp-financial-table"><caption>${esc(t.one_pager.financials.currency)} millions and millions of shares, except per-share figures and percentages. Select a metric to chart it.</caption><thead><tr><th scope="col">Metric</th>${periods.map(d=>`<th scope="col">${esc(periodLabel(d,s.frequency,t))}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>{const values=new Map(pointsOf(t,r.id,s.frequency).map(p=>[p.period,p]));const scale=isMoney(r.unit)||r.unit==='shares'?1e6:1;return `<tr${r.id===s.metric?' class="sp-selected-row"':''}><th scope="row"><button type="button" data-sp-metric="${esc(r.id)}" aria-pressed="${r.id===s.metric}">${esc(r.label)}</button></th>${periods.map(d=>{const p=values.get(d);const value=p?format(p.value/scale,r.unit):'—';return `<td>${p?source(p.source,h,value):value}</td>`;}).join('')}</tr>`;}).join('')}</tbody></table></div>`;
  }
  function financials(t,h) {
    const s=state(t),all=t.one_pager.financials;
    if(!all.series.some(r=>r.id===s.metric&&r.statement===s.statement))s.metric=all.series.find(r=>r.statement===s.statement)?.id;
    return `${intro('Financial history',`${all.latest_fiscal_year_end?'Latest sourced fiscal year ended '+dateLabel(all.latest_fiscal_year_end)+'.':all.fiscal_year_end?'Fiscal year ends '+all.fiscal_year_end+'.':'Fiscal year boundary is not recorded; use the dated periods.'} Latest sourced observation: ${dateLabel(all.latest_period)}. Actuals retain their original reporting periods.`)}${financialControls(t)}${s.metric?chart(t,s.metric,h):''}${financialTable(t,h)}<details class="sp-method"><summary>Definitions and reporting basis</summary>${all.notes.map(note=>`<p>${esc(note)}</p>`).join('')}${t.ticker==='FRMO'?'<p>FRMO equity and income are attributable to parent shareholders. Revenue including investment gains and operating revenue are separate series because the presentation changed. Historical quarters may precede later annual revisions; use the cited version.</p>':''}${t.ticker==='TBBK'?'<p>Net interest income and non-interest income are separate. Their sum is labelled explicitly; it is not mixed with vendor revenue estimates. Operating cash flow for a bank is not distributable owner earnings.</p>':''}</details>`;
  }
  function business(t,h,renderers) {
    const p=t.one_pager;
    return `${intro('How the business creates value',p.profile.focus)}<ul class="sp-driver-list">${p.profile.drivers.map(label=>`<li>${esc(label)}</li>`).join('')}</ul>${metricSummary(t,p.profile.kpis,h)}<div class="sp-reading-grid">${p.profile.chart_metrics.filter(id=>seriesOf(t,id)).slice(0,2).map(id=>`<section>${chart(t,id,h,{frequency:pointsOf(t,id,'annual').length?'annual':'quarterly'})}</section>`).join('')}</div>${t.dossier?.industry?`<section>${intro('Industry and competitors',t.dossier.industry.structure||'')}${t.dossier.industry.trend?`<p>${esc(t.dossier.industry.trend)}</p>`:''}${t.dossier.industry.peers?.length?`<p><strong>Peers:</strong> ${esc(t.dossier.industry.peers.join(', '))}</p>`:''}</section>`:''}<details class="sp-method"><summary>Operating observations, capital allocation and source gaps</summary>${renderers.business?.()||'<p>No additional operating observations are published.</p>'}</details>`;
  }
  function inputValue(value,unit) {
    if(numeric(value)!==null)return format(value,unit||'number');
    return typeof value==='object'?JSON.stringify(value):String(value??'—');
  }
  function presentModelRef(t) {return t.one_pager.model.source_ref;}
  const inputLabel = r => ({revenue_factor:'Revenue versus reported baseline',equity_margin:'Shareholder profit margin',cash_conversion:'Cash conversion of earnings',maintenance_multiplier:'Maintenance spending versus baseline',discount_rate:'Required annual return',growth_rate:'Annual earnings growth',terminal_multiple:'Exit earnings multiple',enhancement_failure_probability:'Credit enhancement failure probability'})[r.id] || clean(r.label);
  function assumptions(t,h,rows) {
    return `<div class="sp-table-scroll"><table class="sp-assumptions"><thead><tr><th scope="col">Input and rationale</th><th scope="col">Bear</th><th scope="col">Base</th><th scope="col">Bull</th><th scope="col">Evidence</th></tr></thead><tbody>${rows.map(r=>`<tr><th scope="row">${esc(inputLabel(r))}<small>${esc(clean(r.component))} · ${esc(r.kind)}${r.unit?' · '+esc(clean(r.unit)):''}</small>${r.rationale?`<details><summary>Why this input</summary><p>${esc(r.rationale)}</p></details>`:''}</th>${['low','base','high'].map(c=>`<td>${esc(inputValue(r.values[c]??(r.kind==='fact'?r.values.base:undefined),r.unit))}</td>`).join('')}<td>${r.source?.ref||r.source?.url?source(r.source,h):source(presentModelRef(t),h,'House assumption')}${r.source?.as_of?`<small>${esc(dateLabel(r.source.as_of))}</small>`:''}${r.source?.locator?`<details><summary>Source passage</summary><p>${esc(r.source.locator)}</p></details>`:''}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function modelFigure(t) {
    const schedule=t.shared_forecast?.forward_cashflow_schedule;
    const hasSchedule=t.shared_forecast?.status==='available'&&['low','base','high'].some(c=>schedule?.[c]?.length);
    if(!hasSchedule&&!t.one_pager.model.components.some(c=>c.treatment!=='embedded'&&numeric(c.range?.base)!==null))return '<p class="sp-empty">A sourced cash-flow schedule or component valuation has not been published yet.</p>';
    return `<figure class="sp-chart"><figcaption><strong>${hasSchedule?'Modeled shareholder cash flows':'Source model component values'}</strong><span>${esc(modelUnit(t).replace('/shares',' per share'))} · ${hasSchedule?'forecast, not declared dividends':'additive components only'} · ${esc(dateLabel(hasSchedule?t.shared_forecast.model_as_of:t.one_pager.model.as_of))}</span></figcaption><div class="sp-canvas"><canvas data-sp-model="${hasSchedule?'cashflows':'components'}" role="img" aria-label="${hasSchedule?'Bear, base and bull dated shareholder cash flow forecast; amounts remain in the full model below':'Component values from the source model; exact values appear in the component table below'}"></canvas></div></figure>`;
  }
  function valuation(t,h,renderers) {
    const p=t.one_pager,rows=p.model.assumptions;
    const priority=p.profile.key_inputs||[];
    const top=rows.filter(r=>r.kind!=='fact').sort((a,b)=>{const score=r=>priority.includes(r.id)?priority.indexOf(r.id):priority.length;return score(a)-score(b);}).slice(0,5);
    return `${intro('Valuation and model assumptions',p.profile.model_note)}<p class="sp-muted">Model ${esc(dateLabel(p.model.as_of))} · financial history through ${esc(dateLabel(p.financials.latest_period))}. Dates are shown separately; a new filing does not automatically revise a model.</p>${p.model.reference_only?'<p class="sp-counter">The input reference and published valuation are different model versions. Read each date before comparing the figures.</p>':''}${global.ResearchWorkspace?.range(t,h)||''}${global.ResearchWorkspace?.scenarios(t,h)||''}${modelFigure(t)}<section class="sp-section">${intro('The assumptions to examine first','Inputs below come from the dated source model. House assumptions show their rationale; reported facts link to their evidence.')}${top.length?assumptions(t,h,top):'<p class="sp-empty">No sourced input schedule is currently published. Open the model and research below for the recorded gaps.</p>'}</section><details class="sp-method"><summary>All ${rows.length} model inputs and historical anchors</summary>${assumptions(t,h,rows)}</details><section class="sp-section">${intro('What is included in value')}<div class="sp-table-scroll"><table><thead><tr><th scope="col">Component</th><th scope="col">Method</th><th scope="col">Treatment</th><th scope="col">Base value / share</th></tr></thead><tbody>${p.model.components.map(c=>`<tr><th scope="row">${esc(clean(c.label||c.id))}</th><td>${esc(clean(c.method))}</td><td>${esc(c.treatment||'Unspecified')}${c.included_in?' in '+esc(c.included_in):''}</td><td>${esc(format(c.range?.base,modelUnit(t)))}</td></tr>`).join('')}</tbody></table></div></section><details class="sp-method"><summary>Full model, scenarios and calculation trail</summary>${renderers.valuation?.()||'<p>No additional model detail is published.</p>'}</details>`;
  }
  function research(t,h) {
    const seen=new Set();const views=(t.insights||[]).filter(r=>{const key=(r.summary||r.claim||r.evidence_url||r.title||'').replace(/\.(pdf|txt|md)(?=$|#)/g,'');if(!key||seen.has(key))return false;seen.add(key);return true;});
    const letters=(t.letter_discussants||[]).slice(0,8);
    return `${intro('Research and outside perspectives','Read the argument, its date and its evidence. Fund commentary, reported ownership and the house model are different kinds of information.')}<div class="sp-research-views">${views.slice(0,6).map(r=>`<article><p class="sp-eyebrow">${esc(clean(r.source==='superinvestor_letter'?'Fund letter':r.source||'Research'))} · ${esc(dateLabel(r.date||r.as_of))}</p><h4>${r.evidence_url?h.linkHtml(r.evidence_url,esc((r.title||r.fund||'Open source')+(r.quarter?' · '+r.quarter:''))):esc(r.title||r.fund||'Research')}</h4><p>${esc(clean(r.summary||r.claim||'Open the original discussion for the argument and context.'))}</p></article>`).join('')||'<p class="sp-empty">No company-specific outside-view summary is published. Search the complete library below for letters, podcasts and primary reports.</p>'}</div>${letters.length?`<details class="sp-method"><summary>Funds with recorded company discussions</summary><ul>${letters.map(r=>`<li>${esc(r.fund||r.name||r.fund_name||'Fund discussion')}${r.latest_date?' · '+esc(dateLabel(r.latest_date)):''}</li>`).join('')}</ul><p class="sp-muted">A discussion or a historical holding does not establish a current recommendation.</p></details>`:''}<section data-company-library="sources"></section>`;
  }
  function updates(t,h,renderers) {
    const risks=t.one_pager.risks;
    return `${intro('Risks and what would change the view',t.one_pager.profile.countercase)}<section class="sp-section"><h3>Conditions to monitor</h3><ul class="sp-risk-list">${risks.map(r=>`<li>${esc(typeof r==='string'?r:r.falsifier||r.description||r.metric||'Review the source condition')}</li>`).join('')||`<li>${esc(t.one_pager.profile.countercase)}</li>`}</ul></section><section class="sp-section"><h3>Latest recorded developments</h3><ol class="sp-update-list">${(h.developments||[]).slice(0,12).map(r=>`<li><time>${esc(dateLabel(r.date||r.as_of))}</time><div>${r.url?h.linkHtml(r.url,esc(r.label||r.title||'Development')):esc(r.label||r.title||'Development')}</div></li>`).join('')||'<li>No dated development is currently published.</li>'}</ol></section><details class="sp-method"><summary>Research revisions, prior views and decision history</summary>${renderers.evidence?.()||'<p>No earlier review is published.</p>'}</details>`;
  }
  function render(tab,t,h,renderers) {
    return `<div class="sp-content">${({overview:summary,financials,business,valuation,sources:research,updates})[validTab(tab)](t,h,renderers)}</div>`;
  }
  function hydrate(panel,t,h,renderers,tab) {
    const old=charts.get(panel)||[];old.forEach(c=>c.destroy());const instances=[];charts.set(panel,instances);
    if(global.Chart)for(const canvas of panel.querySelectorAll('[data-sp-chart]')) {
      const frequency=canvas.dataset.spFrequency||state(t).frequency;
      const {row,points,scale}=chartData(t,canvas.dataset.spChart,frequency);
      if(!points.length)continue;
      const style=getComputedStyle(panel),foreground=style.getPropertyValue('--text-secondary').trim()||'#8a9bb5',accent=style.getPropertyValue('--accent-cyan').trim()||'#2abbd5',grid=style.getPropertyValue('--border').trim()||'#334155';
      instances.push(new global.Chart(canvas, {
        type:'line',
        data:{labels:points.map(p=>periodLabel(p.period,frequency,t)),datasets:[{label:row.label,data:points.map(p=>p.value/scale),borderColor:accent,backgroundColor:accent,pointRadius:3,pointHoverRadius:5,borderWidth:2,tension:0,spanGaps:false}]},
        options:{
          responsive:true,maintainAspectRatio:false,animation:false,
          plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>row.label+': '+format(ctx.raw*scale,row.unit,true)}}},
          scales:{
            x:{ticks:{color:foreground,maxTicksLimit:5,maxRotation:0,font:{size:12}},grid:{display:false}},
            y:{ticks:{color:foreground,font:{size:12}},grid:{color:grid},title:{display:true,text:axisUnit(row.unit),color:foreground}}
          }
        }
      }));
    }
    if(global.Chart)for(const canvas of panel.querySelectorAll('[data-sp-model]')) {
      const style=getComputedStyle(panel),foreground=style.getPropertyValue('--text-secondary').trim(),accent=style.getPropertyValue('--accent-cyan').trim(),grid=style.getPropertyValue('--border').trim();
      let labels,datasets;
      if(canvas.dataset.spModel==='cashflows') {
        const schedule=t.shared_forecast.forward_cashflow_schedule;
        labels=[...new Set(['low','base','high'].flatMap(c=>(schedule[c]||[]).map(p=>p.date).filter(Boolean)))].sort();
        datasets=['low','base','high'].map((c,index)=>({label:['Bear','Base','Bull'][index],data:labels.map(d=>schedule[c]?.length?schedule[c].filter(p=>p.date===d).reduce((sum,p)=>sum+(numeric(p.amount_per_share)||0),0):null),borderColor:[foreground,accent,style.getPropertyValue('--accent-amber').trim()][index],backgroundColor:[foreground,accent,style.getPropertyValue('--accent-amber').trim()][index],borderWidth:2,borderDash:index===0?[5,4]:[],pointRadius:4,tension:0}));
      } else {
        const components=t.one_pager.model.components.filter(c=>c.treatment!=='embedded'&&numeric(c.range?.base)!==null);
        labels=components.map(c=>c.label||c.id);datasets=[{label:'Base value per share',data:components.map(c=>c.range.base),backgroundColor:accent}];
      }
      instances.push(new global.Chart(canvas,{type:canvas.dataset.spModel==='cashflows'?'line':'bar',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:datasets.length>1,labels:{color:foreground}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+format(ctx.raw,modelUnit(t))}}},scales:{x:{ticks:{color:foreground,maxRotation:0,font:{size:12},callback:function(v){const s=String(this.getLabelForValue(v));return s.length>24?s.slice(0,22)+'…':s;}},grid:{display:false}},y:{ticks:{color:foreground},grid:{color:grid},title:{display:true,text:modelUnit(t).replace('/shares',' per share'),color:foreground}}}}}));
    }
    const redraw=selector=>{panel.innerHTML=render(tab,t,h,renderers);hydrate(panel,t,h,renderers,tab);panel.querySelector(selector)?.focus({preventScroll:true});};
    panel.onchange=event=>{const key=event.target.dataset.spControl;if(key){state(t)[key]=event.target.value;redraw(`[data-sp-control="${key}"]`);}};
    panel.onclick=event=>{const button=event.target.closest('[data-sp-metric]');if(button){state(t).metric=button.dataset.spMetric;redraw(`[data-sp-metric="${button.dataset.spMetric}"]`);}};
  }
  function destroy(root) {root?.querySelectorAll('.rw-panel').forEach(panel=>(charts.get(panel)||[]).forEach(c=>c.destroy()));}
  global.StockOnePager={tabs,isPilot,validTab,render,hydrate,destroy,pointsOf,format};
  if(typeof module!=='undefined')module.exports=global.StockOnePager;
})(typeof window!=='undefined'?window:globalThis);
