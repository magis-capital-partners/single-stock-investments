/* One publication supplies the list, drill-downs, peer statistics and stock summaries. */
(function (global) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const profileNames = {operating:'Operating companies', bank:'Banks', property:'Property companies', fund:'Funds',
    insurance:'Insurers', holding:'Holding companies', infrastructure:'Infrastructure', development:'Development companies',
    cyclical:'Cyclicals', preferred:'Preferred shares', debenture:'Debentures', claim:'Contractual claims'};
  let pending;
  const draws = new WeakMap();
  const state = {mode:'quarter', profile:'all', columns:'auto', filter:'all', sort:'ticker', dir:1, page:0};
  try {
    const saved=JSON.parse(localStorage.getItem('financial-changes-view') || '{}');
    if (['quarter','ttm'].includes(saved.mode)) state.mode=saved.mode;
    if (['all','divergence','gaps'].includes(saved.filter)) state.filter=saved.filter;
    if (Object.hasOwn(profileNames,saved.profile)) state.profile=saved.profile;
    if (['level','change'].includes(saved.measure)) state.measure=saved.measure;
    if (typeof saved.sort==='string') state.sort=saved.sort;
    if ([-1,1].includes(saved.dir)) state.dir=saved.dir;
    if (saved.columns==='auto' || Object.hasOwn(profileNames,saved.columns)) state.columns=saved.columns;
  } catch {}
  function save() { try {localStorage.setItem('financial-changes-view',JSON.stringify(state));} catch {} }
  async function load() {
    if (!pending) pending=(async () => {
      for (const url of ['/api/v1/research/data?view=changes','data/research-explorer/changes.json']) {
        try {
          const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});
          if (!r.ok) continue;
          const data=await r.json();
          if (data.version===1 && data.rows && data.profiles && data.registered) return data;
        } catch {}
      }
      throw Error('The financial comparison release is unavailable.');
    })().catch(err=>{pending=null;throw err;});
    return pending;
  }
  const modeOptions=[['quarter','Fiscal quarter'],['ttm','Trailing 12 months']];
  const options = (list, selected) => list.map(([v,l])=>'<option value="'+esc(v)+'"'+(v===selected?' selected':'')+'>'+esc(l)+'</option>').join('');
  const select=(field,label,list,current)=>'<label>'+label+'<select data-field="'+field+'">'+options(list,current)+'</select></label>';
  function format(v,u,compact=true) {
    if (!Number.isFinite(v)) return '—';
    const n=new Intl.NumberFormat('en-US',{notation:compact && Math.abs(v)>=10000?'compact':'standard',
      maximumFractionDigits:u==='percent' && Math.abs(v)<.1?4:u==='bp'?0:2}).format(v);
    return n+(u==='percent'?'%':u==='bp'?' bp':u==='multiple'?'×':u?' '+u:'');
  }
  function delta(c) {
    if (!Number.isFinite(c?.prior) || !Number.isFinite(c?.value)) return null;
    const diff=c.value-c.prior;
    if (c.unit==='percent') return {v:diff*100,u:'bp'};
    if (c.unit==='multiple') return {v:diff,u:'multiple'};
    if (c.prior<=0 || c.value<0) return {v:diff,u:c.unit};
    return {v:diff/c.prior*100,u:'percent'};
  }
  function signed(d) {return d?(d.v>0?'+':'')+format(d.v,d.u):'—';}
  function refLinks(row,ids) {
    return (ids||[]).map(i=>row.sources[i]).filter(u=>/^https:\/\//i.test(u)).map(u=>{
      const host=new URL(u).hostname.replace(/^www\./,'');
      return '<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(host)+'</a>';
    }).join(' · ');
  }
  function spark(cell) {
    const pts=cell.trend||[];
    if(pts.length<2)return '';
    const values=pts.map(p=>p[1]), low=Math.min(...values), high=Math.max(...values);
    const dates=pts.map(p=>Date.parse(p[0])), span=dates.at(-1)-dates[0]||1;
    const xy=pts.map((p,i)=>[2+66*(dates[i]-dates[0])/span,high===low?11:20-18*(p[1]-low)/(high-low)]);
    const frequency=cell.range || cell.unit==='multiple' || cell.price_basis?'monthly':cell.cadence;
    const limit=frequency==='monthly'?65:frequency==='annual'?390:125;
    const path=xy.map(([x,y],i)=>(!i || dates[i]-dates[i-1]>limit*86400000?'M':'L')+x.toFixed(1)+' '+y.toFixed(1)).join(' ');
    const marks=xy.map(([x,y])=>'<circle cx="'+x+'" cy="'+y+'" r="1.45"/>').join('');
    return '<svg class="fc-spark" viewBox="0 0 70 22" role="img" aria-label="'+esc(pts.map(([d,v])=>d+' '+format(v,cell.unit)).join(', '))+'"><path d="'+path+'"/>'+marks+'</svg>';
  }
  function quantile(ordered,p) {
    const i=(ordered.length-1)*p,lo=Math.floor(i);
    return ordered[lo]+(ordered[Math.ceil(i)]-ordered[lo])*(i-lo);
  }
  function peerStats(data,ticker,key,mode,measure='change') {
    const row=data.rows[ticker], base=row?.[mode]?.[key], observations=[];
    if (base?.status!=='ok') return null;
    const own=measure==='change'?delta(base):{v:base.value,u:base.unit};
    if (!own) return null;
    for(const [t,reason] of Object.entries(row.peers||{})) {
      const c=data.rows[t]?.[mode]?.[key];
      if(c?.status!=='ok' || c.cadence!==base.cadence || Math.abs(Date.parse(base.period)-Date.parse(c.period))>45*86400000) continue;
      const value=measure==='change'?delta(c):{v:c.value,u:c.unit};
      if(!value || value.u!==own.u) continue;
      if(measure==='change' && Math.abs(Date.parse(base.prior_period)-Date.parse(c.prior_period))>45*86400000) continue;
      observations.push({ticker:t,value:value.v,reason,period:c.period});
    }
    const vals=observations.map(x=>x.value).sort((a,b)=>a-b);
    return {observations,n:vals.length,unit:own.u,median:vals.length>=3?quantile(vals,.5):null,
      low:vals.length>=3?quantile(vals,.25):null,high:vals.length>=3?quantile(vals,.75):null};
  }
  function peersHtml(data,ticker,key,mode) {
    const stats=peerStats(data,ticker,key,mode);
    if(!stats) return '<p>Peer comparison needs a current, comparable year-over-year change.</p>';
    const eligible=Object.keys(data.rows[ticker].peers||{}).length;
    const details=stats.observations.map(x=>esc(x.ticker)+' '+format(x.value,stats.unit)+' · '+esc(x.period)+' · '+esc(x.reason)).join('<br>');
    return '<h4>Peer changes</h4><p>'+stats.n+' of '+eligible+' peers have matching units and reporting windows.'+
      (stats.n>=3?' Median <b>'+format(stats.median,stats.unit)+'</b> · middle 50% '+format(stats.low,stats.unit)+' to '+format(stats.high,stats.unit)+'.':' Three comparable issuers are required for a range.')+'</p>'+details;
  }
  function reason(c) {return !c?'Not applicable':c.reason || ({missing:'Source needed',stale:'Stale observation',ok:'Comparable year-ago figure unavailable'})[c.status];}
  function evidence(host,data,ticker,key) {
    const row=data.rows[ticker],c=row?.[state.mode]?.[key],dialog=document.createElement('dialog');
    const title=ticker+' · '+data.labels[key];
    const windowLabel=['claim','preferred','debenture'].includes(row.profile)?'Security terms and quotes':
      state.mode==='ttm'?'Trailing 12 months':row.profile==='fund'?'Completed calendar quarter':'Fiscal quarter';
    const trend=c?.trend||[];
    dialog.className='fc-proof';dialog.setAttribute('aria-label',title);
    dialog.innerHTML='<header><h3>'+esc(title)+'</h3><button type="button" autofocus>Close</button></header>'+
      '<p>'+esc(windowLabel)+' · release '+esc(data.as_of)+'</p>'+
      (row.profile==='fund'?'<p>Distribution history '+esc(row.distribution_status||'unavailable')+(key==='relative_return'?' · benchmark '+esc(row.benchmark||'unavailable'):'')+'</p>':'')+
      (c?.period?'<table><thead><tr><th>Observation</th><th>Date</th><th>Value</th><th>Evidence</th></tr></thead><tbody>'+
        '<tr><th>Latest</th><td>'+esc(c.period)+'</td><td>'+format(c.value,c.unit,false)+'</td><td>'+refLinks(row,c.sources)+'</td></tr>'+
        (c.prior_period?'<tr><th>Year ago</th><td>'+esc(c.prior_period)+'</td><td>'+format(c.prior,c.unit,false)+'</td><td>'+refLinks(row,c.prior_sources)+'</td></tr>':'')+'</tbody></table>':'')+
      (c?.status==='ok'&&delta(c)?'<p>Year-over-year change <b>'+signed(delta(c))+'</b></p>':'<p>'+esc(reason(c))+'</p>'+(!c?.period?refLinks(row,c?.sources):''))+
      (c?.range?'<p>Five-year window ending '+esc(c.period)+' · '+c.range[3]+' observed months · low / median / high '+c.range.slice(0,3).map(v=>format(v,c.unit)).join(' / ')+'</p>':'')+
      (delta(c) && c.unit!=='percent' && c.unit!=='multiple' && (c.prior<=0 || c.value<0)?'<p>Change is shown in reporting units because the comparison includes a zero base or a negative value.</p>':'')+
      (trend.length?'<details><summary>Trend values</summary>'+trend.map(p=>esc(p[0])+' · '+format(p[1],c.unit,false)).join('<br>')+'</details>':'')+
      peersHtml(data,ticker,key,state.mode);
    host.append(dialog);
    dialog.querySelector('button').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.showModal();
  }
  function rangeBand(c) {
    const [low,median,high]=c.range;
    const pos=v=>high>low?4+92*(v-low)/(high-low):50;
    const label='Five-year window ending '+c.period+'; latest '+format(c.value,c.unit)+', median '+format(median,c.unit);
    return '<svg class="fc-band" viewBox="0 0 100 14" role="img" aria-label="'+esc(label)+'">'+
      '<path d="M4 7H96" stroke="currentColor" opacity=".4" stroke-width="3"/>'+
      '<path d="M'+pos(median)+' 2v10" stroke="currentColor"/>'+
      '<circle cx="'+pos(c.value)+'" cy="7" r="3.5" fill="currentColor"/></svg>';
  }
  function cellHtml(data,ticker,key) {
    const c=data.rows[ticker]?.[state.mode]?.[key];
    if (!c) return '<span class="fc-muted">N/A</span>';
    const label=esc(data.labels[key]);
    let body=c.status==='na'?'N/A':format(c.value,c.unit);
    if(c.status==='missing')body=c.reason?.startsWith('Issuer identity conflict')?'Verify issuer':
      c.reason?.includes('share basis')?'Verify share basis':'Source needed';
    if (c.period) body+='<small>'+esc(c.period)+(c.status==='stale'?' · stale':'')+'</small>'+spark(c)+'<small>'+signed(delta(c))+' YoY</small>';
    if(c.range)body+=rangeBand(c)+'<small>5Y '+format(c.range[0],c.unit)+' – '+format(c.range[2],c.unit)+'</small>';
    const peers=peerStats(data,ticker,key,state.mode);
    if(peers?.n>=3)body+='<small>Peer median '+signed({v:peers.median,u:peers.unit})+' YoY · n='+peers.n+'</small>';
    return '<button type="button" class="fc-cell" data-proof="'+esc(key)+'" data-t="'+esc(ticker)+'" aria-label="'+esc(ticker)+' '+label+' figures and filings">'+body+'</button>';
  }
  const datesText=r=>'Fiscal '+esc(r?.fiscal_date||'unavailable')+' · Price '+esc(r?.price_date||'unavailable');
  function summaryView(host,data,ticker) {
    const t=data.aliases[ticker]||ticker,r=data.rows[t];
    if(!r){host.innerHTML='<h3>What changed?</h3><p>Financial sources pending for '+esc(ticker)+' · '+esc(data.as_of)+'</p>';return;}
    const keys=data.profiles[r.profile],aliases=Object.keys(data.aliases).filter(a=>data.aliases[a]===t);
    host.innerHTML='<div class="fc-head"><div><h3>What changed?</h3><p>'+esc(profileNames[r.profile])+
      (aliases.length?' · formerly '+esc(aliases.join(', ')):'')+' · '+datesText(r)+'</p></div>'+
      select('mode','Window',modeOptions,state.mode)+'</div><div class="fc-strip">'+keys.map(k=>'<div><strong>'+esc(data.labels[k])+'</strong>'+cellHtml(data,t,k)+'</div>').join('')+'</div>'+
      (r.profile==='fund'?'<small>Completed calendar quarters · broad-market comparison '+esc(r.benchmark||'unavailable')+' · distribution verification '+esc(r.distribution_status||'unavailable')+'</small>':'');
  }
  function sortValue(data,t,k,measure) {
    const c=data.rows[t]?.[state.mode]?.[k];
    if(c?.status!=='ok')return null;
    const d=measure==='change'?delta(c):{v:c.value,u:c.unit};
    return d && Number.isFinite(d.v)?d:null;
  }
  function sortTickers(data,tickers,key,dir,measure) {
    return [...tickers].sort((a,b)=>{
      if(key==='ticker')return dir*a.localeCompare(b);
      const p=sortValue(data,a,key,measure),q=sortValue(data,b,key,measure);
      if(!p || !q)return Number(!p)-Number(!q)||a.localeCompare(b);
      // Original currency amounts and negative-base absolute changes form separate unit groups.
      return String(p.u).localeCompare(String(q.u)) || dir*(p.v-q.v) || a.localeCompare(b);
    });
  }
  function matchesDivergence(row,mode) {
    const rev=row?.[mode]?.revenue,m=row?.[mode]?.operating_margin;
    return rev?.status==='ok' && m?.status==='ok' && rev.prior>0 && rev.value>rev.prior && delta(m)?.v<0 &&
      rev.period===m.period && rev.prior_period===m.prior_period;
  }
  function showList(host,data,context) {
    const grouped=state.profile==='all' && state.columns==='auto';
    const keys=data.profiles[state.profile==='all'?state.columns:state.profile]||data.profiles.operating;
    if(!grouped && !keys.includes(state.sort))state.sort='ticker';
    const all=new Set([...Object.keys(data.rows),...Object.keys(data.missing)]);
    const allowed=new Set(context.rows.map(r=>r.ticker)), names=new Map(context.rows.map(r=>[r.ticker,r.company]));
    const q=context.query.trim().toUpperCase();
    const aliases=new Map();
    for(const [a,t] of Object.entries(data.aliases)) aliases.set(t,[...(aliases.get(t)||[]),a]);
    const eligible=[...all].filter(t=>(allowed.has(t)||(!context.restricted && (q===''||[t,data.missing[t],...(aliases.get(t)||[])].some(v=>String(v||'').toUpperCase().includes(q))))));
    const filtered=eligible.filter(t=>{
      const r=data.rows[t];
      return (state.profile==='all'||r?.profile===state.profile) && (state.filter==='all'||
        (state.filter==='divergence'?matchesDivergence(r,state.mode):!r||Object.values(r[state.mode]).some(c=>c.status!=='na' && (c.status!=='ok'||!Number.isFinite(c.prior)))));
    });
    const sorted=sortTickers(data,filtered,state.sort,state.dir,state.measure||'change');
    const pages=Math.max(1,Math.ceil(sorted.length/40));state.page=Math.min(pages-1,state.page);
    const page=sorted.slice(state.page*40,state.page*40+40);
    const registered=new Set(data.registered.map(t=>data.aliases[t]||t));
    const coverage={current:0,stale:0,missing:0};
    for(const ticker of registered) {
      const cells=Object.values(data.rows[ticker]?.[state.mode]||{});
      if(cells.some(c=>c.status==='ok'))coverage.current++;
      else if(cells.some(c=>c.status==='stale'))coverage.stale++;
      else coverage.missing++;
    }
    const table=(members,keys)=>'<div class="fc-scroll"><table><thead><tr>'+['ticker',...keys].map(k=>'<th scope="col" aria-sort="'+(state.sort===k?(state.dir===1?'ascending':'descending'):'none')+'"><button type="button" data-sort="'+esc(k)+'">'+esc(k==='ticker'?'Company':data.labels[k])+(state.sort===k?(state.dir===1?' ↑':' ↓'):'')+'</button></th>').join('')+'</tr></thead><tbody>'+
      members.map(t=>{const r=data.rows[t];return '<tr><th scope="row">'+(allowed.has(t)?'<a href="#/research/changes/'+encodeURIComponent(t)+'?section=overview">'+esc(t)+'</a>':esc(t))+
        (aliases.has(t)?'<small>Formerly '+esc(aliases.get(t).join(', '))+'</small>':'')+'<small>'+esc(names.get(t)||data.missing[t]||'')+'</small><small>'+datesText(r)+'</small></th>'+
        (r?keys.map(k=>'<td>'+cellHtml(data,t,k)+'</td>').join(''):'<td colspan="'+keys.length+'">Registered · financial publication pending as of '+esc(data.as_of)+'</td>')+'</tr>';}).join('')+'</tbody></table></div>';
    const tables=grouped ? [...new Set(page.map(t=>data.rows[t]?.profile||'pending'))].map(kind=>
      '<h3 class="fc-group">'+esc(profileNames[kind]||'Pending publication')+'</h3>'+
      table(page.filter(t=>(data.rows[t]?.profile||'pending')===kind),data.profiles[kind]||keys)
    ).join('') : table(page,keys);
    host.innerHTML='<div class="fc-head"><div><h2>What changed?</h2><p>'+esc(data.as_of)+' · '+data.registered_count+' registered symbols · '+registered.size+' distinct listings · '+coverage.current+' with current headline figures · '+coverage.stale+' with stale figures only · '+coverage.missing+' awaiting sources</p></div></div>'+
      '<div class="fc-controls">'+select('profile','Stock type',[['all','All types'],...Object.entries(profileNames)],state.profile)+
      (state.profile==='all'?select('columns','Metric columns',[['auto','Match each stock type'],...Object.entries(profileNames)],state.columns):'')+
      select('mode','Window',modeOptions,state.mode)+select('filter','Screen',[['all','All listings'],['divergence','Sales up, margin down'],['gaps','Needs financial data']],state.filter)+
      select('measure','Sort headers by',[['change','Year-over-year change'],['level','Latest figure']],state.measure||'change')+'</div>'+
      '<p class="fc-muted">Select a column to sort, or a figure for periods, filings and peers. Monetary values sort within currency.</p>'+
      tables+
      (!sorted.length?'<p>No matching listings.</p>':'')+'<div class="fc-pager"><button type="button" data-page="-1" '+(state.page===0?'disabled':'')+'>Previous</button>'+
      '<span role="status">'+sorted.length+' matches · page '+(state.page+1)+' of '+pages+'</span><button type="button" data-page="1" '+(state.page+1===pages?'disabled':'')+'>Next</button></div>';
  }
  async function mount(host,context,ticker) {
    if(context) {
      const signature=context.query+'|'+context.rows.map(r=>r.ticker).join(',');
      if(host._financialQuery!==signature)state.page=0;
      host._financialQuery=signature;
    }
    const token={};draws.set(host,token);
    if(!host.hasChildNodes())host.textContent='Loading financial changes…';
    try {
      const data=await load();if(draws.get(host)!==token||!host.isConnected)return;
      const redraw=()=>ticker?summaryView(host,data,ticker):showList(host,data,context);
      redraw();
      host.onchange=e=>{
        const key=e.target.dataset.field;
        if(!key)return;
        state[key]=e.target.value; state.page=0;save();redraw();
        host.querySelector('[data-field="'+key+'"]')?.focus();
      };
      host.onclick=e=>{
        const target=e.target.closest('button');if(!target)return;
        if(target.dataset.proof)evidence(host,data,target.dataset.t,target.dataset.proof);
        if(target.dataset.sort){const k=target.dataset.sort;state.dir=state.sort===k?-state.dir:k==='ticker'?1:-1;state.sort=k;state.page=0;save();redraw();host.querySelector('[data-sort="'+k+'"]')?.focus();}
        if(target.dataset.page){state.page+=Number(target.dataset.page);redraw();}
      };
    }catch(err){
      if(draws.get(host)!==token)return;
      host.innerHTML='<p>'+esc(err.message)+'</p><button type="button">Retry financial changes</button>';
      host.querySelector('button').onclick=()=>mount(host,context,ticker);
    }
  }
  global.FinancialChanges={load,mount,peerStats,sortTickers,matchesDivergence,delta};
  if(typeof module!=='undefined')module.exports=global.FinancialChanges;
})(typeof window!=='undefined'?window:globalThis);
