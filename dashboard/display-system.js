/* Source-aware presentation shared by all dashboard workspaces. No broker access. */
(function (global) {
  'use strict';
  const observed = new Map();
  let registry = null, publication = null, activeHash = '', request = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pathOf = value => { try { const u=new URL(value,global.location.href); return u.pathname.replace(/^\//,'')+(u.pathname.startsWith('/api/')&&u.searchParams.has('producer')?'?producer='+u.searchParams.get('producer'):''); } catch { return String(value).split('?')[0].replace(/^\//,''); } };
  const findStamp = doc => doc?.observed_at || doc?.observation_date || doc?.snapshot?.as_of || doc?.as_of || doc?.generated_at || doc?.generatedAt || doc?.built_at || doc?.generated || null;
  function stateFor(row, now=Date.now()) {
    if (!row) return 'unknown';
    if (row.private_snapshot) return 'unauthorized';
    if (row.exists===false) return ['unauthorized','failed'].includes(row.status)?row.status:'missing';
    if (['failed','unauthorized','processing'].includes(row.status)) return row.status;
    if (row.kind==='api' && !row.stamp) return 'unknown';
    const state=global.DashboardFormat.feedState(row.stamp,row.max_age_hours,{exists:row.exists!==false,empty:row.status==='empty',now});
    if (state==='fresh' && (['degraded','partial','unknown'].includes(row.status) || row.coverage?.incomplete_rows>0)) return 'partial';
    return state;
  }
  function record(url, doc, error=null) {
    const path=pathOf(url);
    observed.set(path,{stamp:findStamp(doc),document:doc,exists:!error,status:error?(error.status===401||error.status===403?'unauthorized':'failed'):doc?.private_snapshot?'unauthorized':['degraded','partial','processing','failed','unknown'].includes(doc?.status)?doc.status:null,private_snapshot:doc?.private_snapshot===true});
    if (request) refresh();
  }
  function updatePublication(status) { publication=status; refresh(); }
  function sourceRow(id) {
    const base=(publication?.surfaces||[]).find(row=>row.id===id);
    if (!base) return {id,label:id,status:'unknown',exists:true,kind:'file'};
    const live=observed.get(pathOf(base.artifact?.replace(/^dashboard\//,'') || base.api || ''));
    if (!live) return base;
    // An explicitly absent observation clock must not inherit an old artifact clock.
    return {...base,...live,status:live.status || base.status,coverage:base.coverage};
  }
  function pageFor(hash) {
    const path=String(hash||'#/research/coverage').split('?')[0];
    return (registry?.views||[]).filter(view=>path===view.path || (view.prefix && path.startsWith(view.path+'/'))).sort((a,b)=>b.path.length-a.path.length)[0];
  }
  function refresh() {
    const host=global.document?.getElementById('display-context');
    if (!host || !registry) return;
    const page=pageFor(activeHash || global.location.hash);
    if (!page) { host.hidden=true;return; }
    const rows=(page.sources||[]).map(sourceRow);
    const problems=rows.filter(row=>!['fresh','empty'].includes(stateFor(row)));
    const unchecked=rows.filter(row=>stateFor(row)==='unknown');
    const status=problems.length?(unchecked.length===rows.length?'unknown':'partial'):'fresh';
    const label=page.frozen?'Frozen historical study':!rows.length?'Source details in this view':unchecked.length===rows.length?'Observation dates not yet verified':problems.length?`${problems.length} of ${rows.length} sources need review`:'Sources current';
    const dates=rows.map(row=>row.stamp).filter(Boolean).map(Date.parse).filter(Number.isFinite);
    const date=dates.length?`Oldest source ${global.DashboardFormat.date(new Date(Math.min(...dates)).toISOString(),{timeZone:'UTC'})}`:'';
    host.hidden=false;
    const content=host.querySelector('[data-display-context-main]');
    content.innerHTML=`<strong>${esc(page.title)}</strong><span class="display-context-meta">${esc(page.purpose)}</span><a class="display-state" data-state="${status}" href="#/data-status" title="Inspect each source, observation date and missing input">${esc(label)}</a>${date?`<span class="display-context-meta">${esc(date)}</span>`:''}`;
  }
  function activate(hash, status) {
    activeHash=hash || global.location.hash;
    if (status) publication=status;
    refresh();
  }
  function setDensity(value) {
    const density=value==='compact'?'compact':'comfortable';
    global.document.documentElement.dataset.density=density;
    if(global.PortfolioViz?.state)global.PortfolioViz.state.density=density;
    for(const table of global.document.querySelectorAll('.ph-table'))table.classList.toggle('compact',density==='compact');
    for(const button of global.document.querySelectorAll('[data-ph-density]'))button.textContent=density==='compact'?'Comfortable rows':'Compact rows';
    const select=global.document.querySelector('[data-display-density]');if(select)select.value=density;
    try{localStorage.setItem('ssi-display-density',density);}catch(_){}
  }
  function chartTheme(chart) {
    const style=global.getComputedStyle(global.document.documentElement);
    const color=style.getPropertyValue('--text-secondary').trim(),border=style.getPropertyValue('--border').trim();
    for(const axis of Object.values(chart.options.scales||{})) {
      if(axis.ticks)axis.ticks.color=color;if(axis.grid)axis.grid.color=border;if(axis.title)axis.title.color=color;
    }
    const legend=chart.options.plugins?.legend;if(legend?.labels)legend.labels.color=color;
  }
  function setTheme(value) {
    const theme=value==='light'?'light':'dark';global.document.documentElement.dataset.theme=theme;
    global.document.documentElement.style.colorScheme=theme;
    const select=global.document.querySelector('[data-display-theme]');if(select)select.value=theme;
    try{localStorage.setItem('ssi-display-theme',theme);}catch(_){}
    const style=global.getComputedStyle(global.document.documentElement);
    const meta=global.document.querySelector('meta[name="theme-color"]');if(meta)meta.content=style.getPropertyValue('--bg-primary').trim();
    if(global.Chart){Chart.defaults.color=style.getPropertyValue('--text-secondary').trim();Chart.defaults.font.size=12;Chart.defaults.font.family="'DM Sans',sans-serif";for(const chart of Object.values(Chart.instances||{})){chartTheme(chart);chart.update('none');}}
  }
  async function start() {
    if (request) return request;
    const host=global.document?.getElementById('display-context');
    if (!host) return;
    let density='comfortable';
    try { density=localStorage.getItem('ssi-display-density')||density; } catch (_) { /* storage optional */ }
    if (!['comfortable','compact'].includes(density)) density='comfortable';
    setDensity(density);
    host.innerHTML='<div class="display-context-main" data-display-context-main></div><div class="display-tools"><label>Theme <select data-display-theme aria-label="Dashboard theme"><option value="dark">Dark</option><option value="light">Light</option></select></label><label>Table density <select data-display-density aria-label="Table density"><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label><a href="#/data-status">Coverage & sources</a></div>';
    const select=host.querySelector('[data-display-density]');
    select.value=density;
    select.addEventListener('change',()=>setDensity(select.value));
    let theme='dark';try{theme=localStorage.getItem('ssi-display-theme')||theme;}catch(_){}
    setTheme(theme);host.querySelector('[data-display-theme]').addEventListener('change',event=>setTheme(event.target.value));
    if(global.Chart)Chart.register({id:'ssi-display-theme',beforeUpdate:chartTheme});
    request=fetch('display-registry.json',{credentials:'same-origin',cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('Display registry unavailable');return r.json();}).then(doc=>{registry=doc;refresh();}).catch(()=>{request=null;host.hidden=true;});
    global.addEventListener('hashchange',()=>{activeHash=global.location.hash;refresh();});
    return request;
  }
  global.DashboardDisplay={start,activate,record,updatePublication,stateFor,sourceRow,pageFor,findStamp,setDensity,setTheme,registry:()=>registry};
})(window);
