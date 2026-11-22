(function (global) {
  'use strict';
  const edits = new Map();
  const escape = x => String(x ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const names = {bear:'Bear',base:'Base',bull:'Bull'};
  const fields = {
    owner_cash:[['reinvestment','Additional cash reinvested','percent'],['incremental_roic','Return on new investment','percent'],['exit_multiple','Exit owner-cash multiple','multiple']],
    earnings:[['growth','Annual earnings growth','percent'],['payout','Earnings distributed','percent'],['exit_multiple','Exit P/E','multiple']],
    book:[['roe','Annual return on opening equity','percent'],['payout','Earnings distributed','percent'],['exit_multiple','Exit price / book','multiple']],
    nav:[['growth','Annual asset value growth, after costs','percent'],['distribution_yield','Annual distribution / opening assets','percent'],['exit_multiple','Exit price / asset value','multiple']],
    transition:[['growth','Annual revenue growth','percent'],['target_margin','Exit net profit margin','percent'],['dilution','Annual share dilution','percent'],['exit_multiple','Exit P/E','multiple']],
    payoff:[['payoff','Future equity proceeds / share','money'],['payoff_date','Payoff date','date']],
    dated_cashflows:[['scale','Recorded cash-flow scale','percent']],
    preferred:[['coupon_paid','Contract distribution assumed paid','percent'],['exit_price','Assumed preferred sale price / share','money']]
  };
  const modelOf = t => t.one_pager?.valuation_model;
  const local = t => edits.get(t.ticker) || {};
  const money = (value, m) => typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat(undefined,{style:'currency',currency:/^[A-Z]{3}$/.test(m.currency)?m.currency:'USD',maximumFractionDigits:2}).format(value) : '—';
  const percent = value => typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat(undefined,{style:'percent',maximumFractionDigits:1}).format(value) : '—';
  function link(ref,h,label) {
    const raw = typeof ref === 'string' ? ref : ref?.url || ref?.source_url || ref?.ref;
    const url = global.SourceLinks ? global.SourceLinks.reference(raw) : /^https?:\/\//.test(raw||'') ? raw : null;
    return url ? h.linkHtml(url,escape(label)) : escape(label);
  }
  const date = x => x ? escape(x) : 'date missing';
  function compact(t,h) {
    const m=modelOf(t);if(!m||!global.StockValuation)return '';
    const r=global.StockValuation.calculate(m,local(t)),b=r.cases.base;
    const timing=m.method==='dated_cashflows'?' · original cash-flow dates':m.method==='payoff'?' · payoff '+date(m.cases.base.payoff_date):' · '+r.inputs.horizon+' years';
    return `<div class="sv-compact"><p class="sp-eyebrow">Research scenario · needs review</p><strong>${escape(m.label)}</strong><dl><div><dt>Base scenario PV</dt><dd>${money(b.value,m)}</dd></div><div><dt>Annual IRR</dt><dd>${percent(b.irr)}</dd></div></dl><p class="sp-muted">${b.gaps.length?escape(b.gaps[0]):'Entry '+money(r.inputs.entry_price,m)+' · '+date(r.inputs.entry_date)+timing}</p></div>`;
  }
  function input(name,label,value,kind='number') {
    const isDate=kind==='date',shown=kind==='percent'&&typeof value==='number'?Number((value*100).toFixed(6)):kind==='money'&&typeof value==='number'?Number(Math.abs(value)>=1?value.toFixed(4):value.toPrecision(6)):value;
    return `<input aria-label="${escape(label)}" name="${escape(name)}" type="${isDate?'date':'number'}" ${isDate?'':'step="any"'} value="${escape(shown??'')}"${kind==='percent'?' data-vm-percent="true"':''}>${kind==='percent'?'<span aria-hidden="true">%</span>':kind==='multiple'?'<span aria-hidden="true">×</span>':''}`;
  }
  function render(t,h) {
    const m=modelOf(t);if(!m||!global.StockValuation)return '<p class="sp-empty">The stock valuation worksheet is loading.</p>';
    const e=local(t),r=global.StockValuation.calculate(m,e),a=m.anchor,changed=Object.keys(e).length>0;
    const assumptions=fields[m.method]||[];
    const c=name=>({...m.cases[name],...e.cases?.[name]});
    const anchors=a?.calculation_inputs||[];
    const anchorTable=anchors.length?`<div class="sp-table-scroll"><table><caption>Reported inputs behind the per-share anchor. Currency amounts and share counts are in millions.</caption><thead><tr><th scope="col">Reported input</th><th scope="col">Amount</th><th scope="col">Unit</th><th scope="col">Period</th><th scope="col">Evidence</th></tr></thead><tbody>${anchors.map(p=>`<tr><th scope="row">${escape(String(p.label||'Input').replaceAll('_',' '))}</th><td>${escape(new Intl.NumberFormat(undefined,{maximumFractionDigits:6}).format(p.value/1e6))}</td><td>${escape(p.unit==='shares'?'million shares':p.unit+' millions')}</td><td>${date(p.period)}</td><td>${link(p.source,h,'Source')}</td></tr>`).join('')}</tbody></table></div>`:'';
    const common=[['entry_price','Entry price / share',r.inputs.entry_price,'money'],['entry_date','Entry date',r.inputs.entry_date,'date'],...(['payoff','dated_cashflows'].includes(m.method)?[]:[['anchor',m.anchor_label,r.inputs.anchor,'money'],['horizon','Forecast years',r.inputs.horizon,'number']]),['discount_rate','Required annual return',r.inputs.discount_rate,'percent']];
    return `<section class="sv-workbench" aria-label="Research valuation model"><div class="sv-heading"><div><p class="sp-eyebrow">Editable research model · needs review</p><h3>${escape(m.label)}</h3><p>Bear, base and bull show what these assumptions imply. This worksheet does not change the approved investment case.</p></div>${changed?'<span class="sv-edited" role="status">Your edited assumptions</span>':''}</div>
      <p class="sp-muted">Entry: ${money(m.quote?.value,m)} · ${date(m.quote?.as_of)} · ${link(m.quote,h,'Price source')}. ${a?`Anchor: ${money(a.value,m)} · period ${date(a.period)} · ${link(a.source||(a.source_refs||[])[0],h,'Financial source')}.`:m.source_forecast?'Source cash-flow model: '+date(m.source_forecast.model_as_of)+'.':m.method==='payoff'?'Payoff amounts and dates are explicit scenario inputs.':'A sourced financial anchor is still required.'}</p>
      <div class="sv-cases">${global.StockValuation.cases.map(name=>{const s=r.cases[name];return `<article class="sv-case${name==='base'?' sv-base':''}"><h4>${names[name]}</h4><dl><div><dt>Scenario present value / share</dt><dd>${money(s.value,m)}</dd></div><div class="sv-return"><dt>Annual IRR</dt><dd>${percent(s.irr)}</dd></div><div><dt>Exit equity proceeds / share</dt><dd>${money(s.terminal,m)}</dd></div></dl>${s.gaps.length?`<p class="sv-gap">Needs input: ${escape(s.gaps[0])}</p>`:''}</article>`;}).join('')}</div>
      <p class="sp-muted">${m.method==='dated_cashflows'?'The source model keeps its original cash-flow dates.':m.method==='payoff'?'Payoff dates are explicit; they are not reset when you open the stock.':`${r.inputs.horizon} annual periods from the dated entry. Forecast proceeds are scenarios, not declared distributions.`} Present value uses a ${percent(r.inputs.discount_rate)} required return. IRR includes the exit sale and interim distributions; it is not annualized upside to present value.</p>
      <form data-vm-form><fieldset><legend>Check the starting inputs</legend><div class="sv-common">${common.map(([key,label,value,kind])=>`<label>${escape(label)}<span class="sv-input">${input('inputs.'+key,label,value,kind)}</span></label>`).join('')}</div><div class="sp-table-scroll"><table class="sv-input-table"><caption>Starting ranges need company-specific review. Edit a value and apply to recalculate.</caption><thead><tr><th scope="col">Assumption</th>${global.StockValuation.cases.map(n=>`<th scope="col">${names[n]}</th>`).join('')}</tr></thead><tbody>${assumptions.map(([key,label,kind])=>`<tr><th scope="row">${escape(label)}</th>${global.StockValuation.cases.map(name=>`<td><span class="sv-input">${input('cases.'+name+'.'+key,names[name]+' '+label,c(name)[key],kind)}</span></td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="sv-actions"><button type="submit" class="sv-apply">Apply assumptions</button><button type="button" data-vm-reset>Reset to published inputs</button><span class="sp-muted">Edits stay in this view. Reset or reload to restore published inputs.</span></div></fieldset></form>
      ${r.ready?`<div class="sp-reading-grid sv-figures"><figure class="sp-chart"><figcaption><strong>${escape(m.method==='payoff'?'Dated equity payoff':m.method==='transition'?'Exit earnings capacity per existing share':m.anchor_label)}</strong><span>${escape(m.currency)} per share · bear / base / bull</span></figcaption><div class="sp-canvas"><canvas data-vm-chart="anchor" role="img" aria-label="Bear, base and bull model trajectory; exact amounts follow below"></canvas></div></figure><figure class="sp-chart"><figcaption><strong>When the shareholder receives value</strong><span>Base case · distributions and exit equity sale · ${escape(m.currency)} per share</span></figcaption><div class="sp-canvas"><canvas data-vm-chart="cash" role="img" aria-label="Base-case distributions and terminal equity sale; exact amounts follow below"></canvas></div></figure></div>`:''}
      ${!r.ready?`<div class="sv-gaps"><h4>What is needed to calculate this model</h4><ul>${[...new Set(Object.values(r.cases).flatMap(c=>c.gaps))].map(g=>`<li>${escape(g)}</li>`).join('')}</ul></div>`:''}
      <details class="sp-method"><summary>Yearly forecast, cash flows and calculation</summary>${global.StockValuation.cases.map(name=>`<div class="sp-table-scroll"><table><caption>${names[name]} · ${escape(m.currency)} per share</caption><thead><tr><th scope="col">Date</th><th scope="col">${escape(m.method==='transition'?'Earnings at exit margin':'Model anchor')}</th><th scope="col">Distribution</th><th scope="col">Exit sale</th><th scope="col">Total proceeds</th></tr></thead><tbody>${r.cases[name].flows.map(p=>`<tr><th scope="row">${date(p.date)}</th><td>${money(p.anchor,m)}</td><td>${money(p.distribution,m)}</td><td>${money(p.terminal,m)}</td><td>${money(p.amount,m)}</td></tr>`).join('')||'<tr><td colspan="5">Complete the required inputs to calculate the cash-flow schedule.</td></tr>'}</tbody></table></div>`).join('')}<p>IRR solves entry price = Σ(proceeds ÷ (1 + IRR)<sup>days / 365.25</sup>). Scenario present value uses the required return in the same equation.</p></details>
      <details class="sp-method"><summary>Sources, definitions and model limitations</summary>${anchorTable}${a?`<p><strong>Anchor basis:</strong> ${escape(a.basis||'Reported annual financials')} · ${date(a.period)}${a.source?.filed?' · filed '+date(a.source.filed):''}.</p>${a.split_adjustment?`<p>Per-share anchor adjusted for a ${escape(a.split_adjustment.ratio)}× split after source date ${date(a.split_adjustment.after_source_date)}.</p>`:''}<ul>${(a.source_refs||[a.source]).filter(Boolean).map((s,i)=>`<li>${link(s,h,'Financial evidence '+(i+1))}${s.locator?' · '+escape(s.locator):''}</li>`).join('')}</ul>`:''}${m.notes.map(note=>`<p>${escape(note)}</p>`).join('')}${m.recorded_model?`<p>Recorded source model: ${escape(m.recorded_model.method||'method not recorded')} · ${date(m.recorded_model.as_of)} · ${link(m.recorded_model.source_ref,h,'Open source model')}. Its original dates and underwriting status are retained below.</p>`:''}</details></section>`;
  }
  function hydrate(panel,t,h,redraw) {
    const form=panel.querySelector('[data-vm-form]');if(!form)return [];
    form.addEventListener('submit',event=>{
      event.preventDefault();const e={inputs:{},cases:{bear:{},base:{},bull:{}}};
      for(const el of form.querySelectorAll('input[name]')) {
        const keys=el.name.split('.');let value=el.type==='date'?el.value:el.value===''?null:Number(el.value);
        if(el.dataset.vmPercent&&value!==null)value/=100;
        if(keys[0]==='inputs')e.inputs[keys[1]]=value;else e.cases[keys[1]][keys[2]]=value;
      }
      edits.set(t.ticker,e);redraw('.sv-apply');
    });
    panel.querySelector('[data-vm-reset]')?.addEventListener('click',()=>{edits.delete(t.ticker);redraw('.sv-apply');});
    if(!global.Chart)return [];
    const r=global.StockValuation.calculate(modelOf(t),local(t));if(!r.ready)return [];
    const style=getComputedStyle(panel),fg=style.getPropertyValue('--text-secondary').trim()||'#9baec7',accent=style.getPropertyValue('--accent-cyan').trim()||'#2abbd5',amber=style.getPropertyValue('--accent-amber').trim()||'#e5a04b',grid=style.getPropertyValue('--border').trim()||'#334155';
    return [...panel.querySelectorAll('[data-vm-chart]')].map(canvas=>{
      const cash=canvas.dataset.vmChart==='cash',labels=[...new Set(global.StockValuation.cases.flatMap(c=>r.cases[c].flows.map(p=>p.date)))].sort();
      const datasets=cash?[{label:'Distributions',data:r.cases.base.flows.map(p=>p.distribution),backgroundColor:accent},{label:'Exit equity sale',data:r.cases.base.flows.map(p=>p.terminal),backgroundColor:amber}]:global.StockValuation.cases.map((c,i)=>({label:names[c],data:labels.map(d=>r.cases[c].flows.find(p=>p.date===d)?.anchor??null),borderColor:[fg,accent,amber][i],backgroundColor:[fg,accent,amber][i],borderWidth:2,pointRadius:3,tension:0,borderDash:i===0?[4,4]:[]}));
      return new global.Chart(canvas,{type:cash?'bar':'line',data:{labels:cash?r.cases.base.flows.map(p=>p.date):labels,datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{labels:{color:fg}},tooltip:{callbacks:{label:ctx=>ctx.dataset.label+': '+money(ctx.raw,modelOf(t))}}},scales:{x:{stacked:cash,grid:{display:false},ticks:{color:fg,maxRotation:0,maxTicksLimit:5}},y:{stacked:cash,grid:{color:grid},ticks:{color:fg},title:{display:true,text:modelOf(t).currency+' per share',color:fg}}}}});
    });
  }
  function current(t) {const m=modelOf(t),e=local(t);return JSON.parse(JSON.stringify({...m,inputs:{...m.inputs,...e.inputs},cases:Object.fromEntries(global.StockValuation.cases.map(c=>[c,{...m.cases[c],...e.cases?.[c]}]))}));}
  function apply(t,saved) {const m=modelOf(t);if(!saved||saved.ticker!==t.ticker||saved.method!==m.method)throw new Error('The saved scenario belongs to a different company or model method.');edits.set(t.ticker,{inputs:{...saved.inputs},cases:JSON.parse(JSON.stringify(saved.cases))});}
  global.StockValuationView={render,compact,hydrate,current,apply};
  if(typeof module!=='undefined')module.exports=global.StockValuationView;
})(typeof window!=='undefined'?window:globalThis);
