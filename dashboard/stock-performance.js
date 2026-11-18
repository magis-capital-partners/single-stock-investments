/* Dated shareholder history. Presentation only; never used by the valuation model. */
(function (global) {
  'use strict';
  const states = new Map(), charts = new WeakMap();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct = value => Number.isFinite(value) ? new Intl.NumberFormat(undefined, {style:'percent',maximumFractionDigits:1}).format(value) : '—';
  const money = (value, currency='USD', compact=false) => new Intl.NumberFormat(undefined, {style:'currency',currency,maximumFractionDigits:0,notation:compact?'compact':'standard'}).format(value);
  const day = value => new Intl.DateTimeFormat(undefined, {year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(value));
  const history = t => t.one_pager?.performance?.points?.length ? t.one_pager.performance : t.total_return_panel?.history;
  const state = t => {
    if (!states.has(t.ticker)) states.set(t.ticker, {period:'all',scale:'logarithmic',view:'wealth',benchmark:true,price:false});
    return states.get(t.ticker);
  };

  function windowData(record, period='all') {
    const valid = (record?.points || []).filter(p => /^\d{4}-\d{2}-\d{2}$/.test(p[0]) && Number.isFinite(p[1]) && p[1]>0 && Number.isFinite(p[2]) && p[2]>=0);
    if (valid.length < 2) return null;
    const end = new Date(valid.at(-1)[0]);
    let cutoff = '';
    if (period !== 'all') {end.setUTCFullYear(end.getUTCFullYear()-Number(period));cutoff=end.toISOString().slice(0,10);}
    let points = valid.filter(p => p[0]>=cutoff);
    const benchmark = record.benchmark?.currency===record.currency ? record.benchmark : null;
    const bench = new Map((benchmark?.points || []).map(p=>[p[0],p[2]]));
    // Comparisons begin and end on the same observed sessions, never on an
    // interpolated price or a separately rebased benchmark date.
    if (benchmark) {
      const common=points.filter(p=>Number.isFinite(bench.get(p[0])) && bench.get(p[0])>0);
      if(common.length>=2)points=points.filter(p=>p[0]>=common[0][0] && p[0]<=common.at(-1)[0]);
    }
    if (points.length<2 || points[0][2]<=0) return null;
    const first=points[0], last=points.at(-1), base=first[2], priceBase=first[1], benchBase=bench.get(first[0]);
    let peak=base, drawdown=0;
    for(const p of points){peak=Math.max(peak,p[2]);drawdown=Math.min(drawdown,p[2]/peak-1);}
    const years=(new Date(last[0])-new Date(first[0]))/86400000/365.2425;
    const ratio=last[2]/base;
    return {points, start:first[0], end:last[0], total:ratio-1, cagr:years>0?Math.pow(ratio,1/years)-1:null,
      drawdown, ending:10000*ratio, benchmark:benchmark&&benchBase>0?benchmark:null,
      values:points.map(p=>({date:p[0],total:10000*p[2]/base,price:10000*p[1]/priceBase,
        benchmark:benchBase>0&&Number.isFinite(bench.get(p[0]))?10000*bench.get(p[0])/benchBase:null}))};
  }

  function markup(t,h={}) {
    const record=history(t), s=state(t), data=windowData(record,s.period);
    if(!data)return '<p class="perf-empty">Comparable shareholder-return history is not available.</p>';
    const currency=record.currency||'USD', initial=money(10000,currency);
    const links=[['Stock history',record.source_url], ...(data.benchmark?[['Benchmark history',data.benchmark.source_url]]:[])];
    const sourceLink=(label,url)=>h.linkHtml?h.linkHtml(url,esc(label)):`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
    const annual=data.values.filter((p,i,all)=>i===0 || i===all.length-1 || p.date.slice(0,4)!==all[i+1]?.date.slice(0,4));
    return `<div class="perf-heading"><div><h3>Long-term shareholder returns</h3><p>${esc(day(data.start))} – ${esc(day(data.end))} · ${esc(currency)} · dividends reinvested</p></div><span class="perf-basis">${record.status==='complete'?'Distribution history reconciled':'Distribution verification incomplete'}</span></div>
      <div class="perf-toolbar"><div class="perf-periods" role="group" aria-label="Performance period">${[['1','1Y'],['5','5Y'],['10','10Y'],['all','All history']].map(([v,label])=>`<button type="button" data-perf-period="${v}" aria-pressed="${s.period===v}">${label}</button>`).join('')}</div>
      <label>Show<select data-perf-control="view"><option value="wealth"${s.view==='wealth'?' selected':''}>Growth of ${esc(initial)}</option><option value="return"${s.view==='return'?' selected':''}>Cumulative return %</option></select></label>
      <label>Scale<select data-perf-control="scale"><option value="logarithmic"${s.scale==='logarithmic'?' selected':''}>Logarithmic</option><option value="linear"${s.scale==='linear'?' selected':''}>Linear</option></select></label></div>
      <dl class="perf-stats"><div><dt>Ending value of ${esc(initial)}</dt><dd>${esc(money(data.ending,currency))}</dd></div><div><dt>Total return</dt><dd>${esc(pct(data.total))}</dd></div><div><dt>Annualized return</dt><dd>${esc(pct(data.cagr))}</dd></div><div><dt>Largest decline from a peak</dt><dd>${esc(pct(data.drawdown))}</dd></div></dl>
      <div class="perf-legend"><span class="perf-stock-line">${esc(t.ticker)} total return</span>${data.benchmark?`<label class="perf-benchmark"><input type="checkbox" data-perf-control="benchmark"${s.benchmark?' checked':''}> S&P 500 ETF (SPY)</label>`:''}<label class="perf-price"><input type="checkbox" data-perf-control="price"${s.price?' checked':''}> ${esc(t.ticker)} price only</label></div>
      <div class="perf-canvas"><canvas role="img" aria-label="${esc(t.ticker)} shareholder return from ${data.start} to ${data.end}. Annual values and source definitions follow." data-perf-chart></canvas></div>
      <p class="perf-footnote">${s.scale==='logarithmic'?'Equal vertical distances represent equal percentage changes. ':''}Hover or tap the chart for a date and value. Each selected period starts at ${esc(initial)}. Pre-tax; excludes fees and inflation. ${data.benchmark?'SPY includes reinvested distributions and uses the same comparison dates.':''}</p>
      <details class="perf-details"><summary>Annual values, sources and return definitions</summary><p>${esc(record.basis||'Split-adjusted prices with cash distributions reinvested.')}</p><p>${esc(record.coverage?.note||'Review distribution and corporate-action coverage against primary reports.')}</p><p>${links.filter(([,url])=>/^https?:\/\//.test(url||'')).map(([label,url])=>sourceLink(label,url)).join(' · ')}</p><div class="perf-table-scroll"><table><caption>Values rebased to ${esc(initial)} at the selected start date.</caption><thead><tr><th scope="col">Date</th><th scope="col">${esc(t.ticker)} total return</th><th scope="col">Price only</th>${data.benchmark?'<th scope="col">SPY total return</th>':''}</tr></thead><tbody>${annual.map(p=>`<tr><th scope="row">${esc(p.date)}</th><td>${esc(money(p.total,currency))}</td><td>${esc(money(p.price,currency))}</td>${data.benchmark?`<td>${p.benchmark===null?'—':esc(money(p.benchmark,currency))}</td>`:''}</tr>`).join('')}</tbody></table></div></details>`;
  }
  function render(t,h) {return windowData(history(t))?`<section class="stock-performance" data-stock-performance>${markup(t,h)}</section>`:'';}
  function draw(host,t) {
    charts.get(host)?.destroy(); charts.delete(host);
    const record=history(t),s=state(t),data=windowData(record,s.period),canvas=host.querySelector('[data-perf-chart]');
    if(!canvas||!data||!global.Chart)return;
    const style=getComputedStyle(host), text=style.getPropertyValue('--text-secondary').trim()||'#9aabc4',
      cyan=style.getPropertyValue('--accent-cyan').trim()||'#55d6ec', border=style.getPropertyValue('--border').trim()||'#334155';
    const datasets=[{label:t.ticker+' total return',data:data.values.map(p=>p.total),borderColor:cyan,borderWidth:2.5,fill:false}];
    if(s.benchmark&&data.benchmark)datasets.push({label:'S&P 500 ETF (SPY)',data:data.values.map(p=>p.benchmark),borderColor:text,borderDash:[6,4],borderWidth:1.8});
    if(s.price)datasets.push({label:t.ticker+' price only',data:data.values.map(p=>p.price),borderColor:'#c89137',borderDash:[2,3],borderWidth:1.8});
    const logarithmic=s.scale==='logarithmic'&&datasets.every(d=>d.data.every(v=>v===null||v>0));
    const chart=new global.Chart(canvas,{type:'line',data:{labels:data.values.map(p=>p.date),datasets:datasets.map(d=>({...d,pointRadius:0,pointHitRadius:16,pointHoverRadius:4,tension:0,spanGaps:false}))},options:{responsive:true,maintainAspectRatio:false,animation:false,normalized:true,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{displayColors:true,callbacks:{title:items=>items.length?day(items[0].label):'',label:ctx=>`${ctx.dataset.label}: ${money(ctx.raw,record.currency)} (${pct(ctx.raw/10000-1)})`}}},scales:{x:{grid:{display:false},ticks:{color:text,maxTicksLimit:7,maxRotation:0,font:{size:12},callback:function(index){return this.getLabelForValue(index).slice(0,4);}}},y:{type:logarithmic?'logarithmic':'linear',grid:{color:border},ticks:{color:text,maxTicksLimit:6,font:{size:12},callback:value=>s.view==='return'?pct(value/10000-1):money(value,record.currency,true)},title:{display:true,text:s.view==='return'?'Cumulative return':'Growth of '+money(10000,record.currency),color:text,font:{size:12}}}}}});
    charts.set(host,chart);
  }
  function mount(root,t,h) {
    for(const host of root.querySelectorAll('[data-stock-performance]')) {
      draw(host,t);
      const redraw=selector=>{charts.get(host)?.destroy();charts.delete(host);host.innerHTML=markup(t,h);draw(host,t);host.querySelector(selector)?.focus({preventScroll:true});};
      host.onclick=event=>{const button=event.target.closest('[data-perf-period]');if(button){state(t).period=button.dataset.perfPeriod;redraw(`[data-perf-period="${button.dataset.perfPeriod}"]`);}};
      host.onchange=event=>{const key=event.target.dataset.perfControl;if(key){state(t)[key]=event.target.type==='checkbox'?event.target.checked:event.target.value;redraw(`[data-perf-control="${key}"]`);}};
    }
  }
  function destroy(root) {for(const host of root?.querySelectorAll('[data-stock-performance]')||[]){charts.get(host)?.destroy();charts.delete(host);}}
  global.StockPerformance={render,mount,destroy,windowData};
  if(typeof module!=='undefined')module.exports=global.StockPerformance;
})(typeof window!=='undefined'?window:globalThis);
