/* Complete company libraries. Sources are rendered as text; source markup is never executed. */
(function (global) {
  'use strict';
  const BASE = 'data/company-research/';
  const categories = {calls:'Expert calls & meetings',letters:'Fund commentary',analysis:'Research & analysis',filings:'Filings & company materials',models:'Models & data',industry:'Industry & commodity research',media:'Other relevant sources'};
  const cache = new Map();
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const words = value => [...new Set(String(value).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().match(/[a-z0-9]+/g)||[])];
  const safeURL = value => { try { const url=new URL(value,global.location?.href || 'https://research.invalid/'); return ['https:','http:'].includes(url.protocol) ? url.href : ''; } catch { return ''; } };
  function asset(path) {
    if (!/^[A-Za-z0-9._/-]+\.json$/.test(path) || path.includes('..')) throw new Error('Invalid research asset path');
    if (!cache.has(path)) cache.set(path,fetch(BASE+path,{credentials:'same-origin',cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('Research library unavailable. Retry after the next source update.');return r.json();}).catch(e=>{cache.delete(path);throw e;}));
    return cache.get(path);
  }
  async function searchIndex(path) {
    const result=await asset(path),index={};
    if(result.__parts){for(let i=0;i<result.__parts.length;i+=4){for(const part of await Promise.all(result.__parts.slice(i,i+4).map(asset)))Object.assign(index,part);}}
    else Object.assign(index,result);
    delete index.__ids;delete index.__parts;
    if(result.__ids)for(const word of Object.keys(index))index[word]=index[word].map(i=>result.__ids[i]);
    return index;
  }
  const manifest = ticker => asset(`companies/${encodeURIComponent(ticker)}.json`);
  const sourceURL = row => {const loc=(row.locations||[]).find(x=>safeURL(x.url)); return loc?safeURL(loc.url):'';};
  function referencesHTML(refs) {
    if(!refs)return '';
    const values=(Array.isArray(refs)?refs:[refs]).filter(ref=>ref!==null&&ref!==undefined);
    return `<details><summary>Model inputs and references</summary><ul>${values.map(ref=>{
      const raw=typeof ref==='string'?ref:(ref.url||ref.href||'');
      const url=/^https?:\/\//i.test(raw)?safeURL(raw):'';
      const label=typeof ref==='string'?ref:(ref.title||ref.name||ref.label||JSON.stringify(ref));
      return `<li>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:esc(label)}</li>`;
    }).join('')}</ul></details>`;
  }
  function filter(rows, state, index) {
    const terms=words(state.query||'');
    const matches=terms.length&&index?terms.map(t=>new Set(index[t]||[])):null;
    return rows.filter(r=> (state.versions!=='current'||r.is_latest!==false) && (!state.category||r.category===state.category) && (!state.relation||r.relationship===state.relation)
      && (!state.author||String(r.author).toLowerCase().includes(state.author.toLowerCase()))
      && (!state.from||r.date&&r.date>=state.from) && (!state.to||r.date&&r.date.slice(0,10)<=state.to)
      && (!terms.length || matches ? !terms.length||matches.every(ids=>ids.has(r.id)) : terms.every(t=>words(`${r.title} ${r.author} ${r.reason}`).includes(t))))
      .sort((a,b)=>state.sort==='date'?String(b.date||'').localeCompare(String(a.date||'')):Number(b.relationship==='direct')-Number(a.relationship==='direct')||String(b.date||'').localeCompare(String(a.date||''))||a.title.localeCompare(b.title));
  }
  function coverage(meta) {
    const c=meta.coverage||{};
    return `Library checked ${esc(String(c.checked_at||'unknown').slice(0,10))} · ${Number(meta.total||0).toLocaleString()} sources${c.pending?` · ${Number(c.pending).toLocaleString()} awaiting text processing`:''}${c.review_count?` · ${Number(c.review_count).toLocaleString()} possible matches awaiting review`:''}${c.status==='partial'?' · Coverage incomplete':''}`;
  }
  function rowHTML(row) {
    const url=sourceURL(row);
    const passages=(row.passages||[]).map(p=>`<blockquote><p>${esc(p.text)}</p><cite>${esc(p.locator)}${p.timestamp?` · ${esc(p.timestamp)}`:''}</cite></blockquote>`).join('');
    const links=(row.locations||[]).filter(l=>safeURL(l.url)).map(l=>`<a href="${esc(safeURL(l.url))}" target="_blank" rel="noopener noreferrer">${esc(l.label||l.kind)}</a>`).join(' · ');
    return `<article class="cr-source"><div class="cr-source-main"><div><h4>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(row.title)}</a>`:esc(row.title)}</h4><p class="cr-meta">${row.author?`${esc(row.author)} · `:''}${esc(String(row.date||'Undated').slice(0,10))} · ${esc(categories[row.category]||row.category)}${row.version_count>1?` · ${row.version_count} versions`:''}${row.relationship!=='direct'?' · Related business research':''}</p>${row.relationship!=='direct'?`<p>${esc(row.reason)}</p>`:''}</div><button type="button" data-cr-read="${esc(row.id)}">Read${row.processing_status==='indexed'?' passage':' details'}</button></div><details><summary>Source details${row.availability!=='available'?` · ${esc(String(row.availability).replaceAll('_',' '))}`:''}</summary>${passages||'<p class="cr-meta">Company-specific collection or reviewed business-driver link. Open the original for context.</p>'}<p>${links||'Original link unavailable.'}</p>${row.period?`<p>Reporting period: ${esc(row.period)}</p>`:''}${row.revision?`<p>Version: ${esc(row.revision)}</p>`:''}${row.model_purpose?`<p>Purpose: ${esc(row.model_purpose)}</p>`:''}${row.assumptions?`<details><summary>Model assumptions</summary><pre>${esc(JSON.stringify(row.assumptions,null,2))}</pre></details>`:''}${referencesHTML(row.source_refs)}${row.extraction_review?`<p class="cr-meta">${esc(row.extraction_review)}</p>`:''}<p class="cr-meta">${row.processing_status==='indexed'?'Text indexed for search':esc(row.processing_status.replaceAll('_',' '))}</p></details></article>`;
  }
  async function read(row, host) {
    const request={};host._readRequest=request;
    const output=host.querySelector('[data-cr-reader]');
    if(!output)return;
    output.hidden=false; output.innerHTML='<p>Loading source…</p>';
    try {
      const bundle=await asset(row.content_path); const doc={...bundle[row.id]};
      if(doc.text_parts?.length){const parts=[];for(let i=0;i<doc.text_parts.length;i+=4){parts.push(...await Promise.all(doc.text_parts.slice(i,i+4).map(asset)));}doc.text=parts.map(p=>p.text).join('');}
      if(!host.isConnected||host._readRequest!==request)return;if(!bundle[row.id])throw new Error('Source content is unavailable.');
      output.innerHTML=`<div class="cr-reader-head"><h3>${esc(doc.title)}</h3><button type="button" data-cr-close>Close source</button></div>${(row.passages||[]).map(p=>`<blockquote>${esc(p.text)}<cite>${esc(p.locator)}</cite></blockquote>`).join('')}<p>${(doc.locations||[]).filter(l=>safeURL(l.url)).map(l=>`<a href="${esc(safeURL(l.url))}" target="_blank" rel="noopener noreferrer">${esc(l.label||'Open original')}</a>`).join(' · ')}</p><details${(row.passages||[]).length?'':' open'}><summary>Full source text</summary><pre>${esc(doc.text||'Text is not yet available. Use the original link above.')}</pre></details>`;
      output.querySelector('[data-cr-close]').onclick=()=>{output.hidden=true;host.querySelector(`[data-cr-read="${row.id}"]`)?.focus();};
      output.scrollIntoView({block:'nearest'});
      output.querySelector('[data-cr-close]').focus({preventScroll:true});
    }catch(e){output.textContent=e.message;}
  }
  async function mount(host,ticker,options={}) {
    const request={}; host._companyRequest=request;
    const live=()=>host.isConnected&&host._companyRequest===request;
    host.innerHTML='<p class="cr-meta" role="status">Loading company sources…</p>';
    try {
      const meta=await manifest(ticker); if(!live())return;
      if(options.summary) {
        host.innerHTML=`<div class="cr-overview-heading"><h3>Research library</h3><button type="button" data-rw-go="sources">All ${Number(meta.total).toLocaleString()} sources</button></div><p class="cr-meta">${coverage(meta)}</p><div class="cr-categories">${Object.entries(categories).map(([id,label])=>`<button type="button" data-cr-category="${id}">${esc(label)} <strong>${meta.categories?.[id]||0}</strong></button>`).join('')}</div><h3>Essential reading</h3><ul class="cr-reading">${(meta.featured||[]).map(r=>`<li>${sourceURL(r)?`<a href="${esc(sourceURL(r))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`:esc(r.title)}<span>${esc(String(r.date||'Undated').slice(0,10))}</span></li>`).join('')||'<li>No qualifying sources indexed yet.</li>'}</ul>`;
        host.onclick=e=>{const c=e.target.closest('[data-cr-category]');if(c){global.CompanyResearch.pendingCategory=c.dataset.crCategory;global.ResearchWorkspace?.activate('sources');host.closest('.research-workspace')?.querySelector('[data-company-library="sources"]')?._setCategory?.(c.dataset.crCategory);}};
        return;
      }
      const state={category:options.models?'models':(global.CompanyResearch.pendingCategory||''),query:'',relation:'',sort:'relevance',versions:'current',page:0};global.CompanyResearch.pendingCategory='';
      host.innerHTML=`<p class="cr-meta">${coverage(meta)}</p><form class="cr-filters" role="search"><label>Search this company’s sources<input name="query" type="search" placeholder="Search all indexed text"></label><label>Source type<select name="category"><option value="">All sources (${meta.total})</option>${Object.entries(categories).map(([id,label])=>`<option value="${id}">${esc(label)} (${meta.categories?.[id]||0})</option>`).join('')}</select></label><details class="cr-filter-more"><summary>More filters &amp; history</summary><div class="cr-filter-fields"><label>Relevance<select name="relation"><option value="">Company + related research</option><option value="direct">Company research</option><option value="industry_context">Related business research</option></select></label><label>Author or provider<input name="author" type="search"></label><label>Versions<select name="versions"><option value="current">Latest versions</option><option value="all">All versions &amp; history</option></select></label><label>From<input name="from" type="date"></label><label>To<input name="to" type="date"></label><label>Sort<select name="sort"><option value="relevance">Relevance, then newest</option><option value="date">Newest first</option></select></label></div></details></form><p class="cr-meta" aria-live="polite" data-cr-status>Loading complete inventory…</p><section data-cr-reader class="cr-reader" hidden aria-label="Source reader"></section><div data-cr-results></div><nav class="cr-pages" aria-label="Source pages"><button type="button" data-cr-prev>Previous</button><span data-cr-page></span><button type="button" data-cr-next>Next</button></nav><details class="cr-coverage"><summary>Coverage and processing details</summary>${meta.coverage?.unassigned_pending?`<p>${Number(meta.coverage.unassigned_pending).toLocaleString()} files across the archive still need text processing before company relevance can be checked.</p>`:''}${(meta.coverage?.receipts||[]).filter(r=>!r.collection.startsWith('company:')||r.collection==='company:'+ticker).map(r=>`<p>${esc(r.collection)} · ${Number(r.discovered)} discovered · ${esc(r.status)}${r.detail?` · ${esc(r.detail)}`:''}</p>`).join('')}</details>`;
      const form=host.querySelector('form');form.elements.category.value=state.category;form.onsubmit=e=>e.preventDefault();
      const rows=[];
      // Bounded concurrent requests; every manifest page is consumed without a result cutoff.
      for(let i=0;i<meta.pages.length;i+=6){const batch=await Promise.all(meta.pages.slice(i,i+6).map(asset));rows.push(...batch.flat());if(!live())return;}
      let index=null,version=0;
      async function render(){const v=++version;Object.assign(state,Object.fromEntries(new FormData(form)));if(state.query&&!index){host.querySelector('[data-cr-status]').textContent='Searching full source text…';index=await searchIndex(meta.search_path);}if(!live()||v!==version)return;const found=filter(rows,state,index);const pages=Math.max(1,Math.ceil(found.length/25));state.page=Math.min(state.page,pages-1);host.querySelector('[data-cr-results]').innerHTML=found.slice(state.page*25,(state.page+1)*25).map(rowHTML).join('')||'<p>No sources match these filters.</p>';host.querySelector('[data-cr-status]').textContent=`${found.length.toLocaleString()} of ${meta.total.toLocaleString()} sources${meta.coverage.pending?' · Some source text is still awaiting processing':''}`;host.querySelector('[data-cr-page]').textContent=`Page ${state.page+1} of ${pages}`;host.querySelector('[data-cr-prev]').disabled=state.page===0;host.querySelector('[data-cr-next]').disabled=state.page>=pages-1;}
      const redraw=()=>render().catch(e=>{if(live())host.querySelector('[data-cr-status]').textContent=e.message;});
      host._setCategory=value=>{form.elements.category.value=value;state.page=0;global.CompanyResearch.pendingCategory='';redraw();};
      form.oninput=()=>{state.page=0;redraw();};
      host.querySelector('[data-cr-prev]').onclick=()=>{state.page--;redraw();};host.querySelector('[data-cr-next]').onclick=()=>{state.page++;redraw();};
      host.onclick=e=>{const button=e.target.closest('[data-cr-read]');if(button){const row=rows.find(r=>r.id===button.dataset.crRead);if(row)read(row,host);}};
      await render();
    }catch(e){if(live()){host.innerHTML=`<p class="cr-meta">${esc(e.message)}</p><button type="button" data-cr-retry>Retry library</button>`;host.querySelector('button').onclick=()=>mount(host,ticker,options);}}
  }
  global.CompanyResearch={mount,filter,words,safeURL,rowHTML,categories,pendingCategory:''};
  if(typeof module!=='undefined')module.exports=global.CompanyResearch;
})(typeof window!=='undefined'?window:globalThis);
