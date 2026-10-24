(function(global) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const types = ['long','short','update','postmortem','special_situation','credit','private','unnamed','sector','macro','portfolio','factual_note'];
  const checks = {complete_document:'Read the complete letter, including tables and footnotes',idea_coverage:'Every substantive idea is accounted for',claim_accuracy:'Arguments and attribution reconcile to evidence',numerical_accuracy:'Figures, currencies, units and periods are accurate',original_writing:'Writing is original and source overlap has been reviewed',historical_dates:'Dates and historical context are supported'};
  const paragraphs = text => String(text || '').split(/\n\s*\n/).filter(Boolean).map(p => `<p>${escape(p)}</p>`).join('');
  const label = value => String(value || '').replace(/_/g,' ');
  const period = letter => `${letter.reporting_period || 'Period unavailable'} · ${letter.letter_date ? `Letter dated ${letter.letter_date}` : 'Exact letter date unavailable'}`;
  async function api(args, payload) {
    const response = await fetch('/api/fund-letters?' + new URLSearchParams(args), {cache:'no-store',credentials:'same-origin',...(payload ? {method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)} : {})});
    const result = await response.json();
    if (!response.ok) throw new Error([result.error,...(result.errors || [])].filter(Boolean).join(' '));
    return result;
  }
  const states = new WeakMap();
  async function mount(root, options = {}) {
    states.get(root)?.dispose();
    const embedded = Boolean(options.embedded);
    let params = new URLSearchParams(embedded ? sessionStorage.getItem('fl-reader-state') || '' : location.search);
    let funds = [], role = 'reader', next = null, loading = false, sequence = 0, disposed = false, observer, pages = 0, restoring = false;
    const abort = new AbortController();
    const controller = { dispose() {disposed = true; sequence++; observer?.disconnect(); abort.abort();} };
    states.set(root, controller);
    root.classList.add('fl-reader');
    root.innerHTML = `<a class="fl-skip" href="#fl-reading">Skip to letters</a><header class="fl-masthead"><div><div class="fl-wordmark">MAGIS / RESEARCH LIBRARY</div><h1>Fund Letters</h1><p>Investment arguments, in the manager’s own historical context.</p></div><div class="fl-owner-tools"></div></header>
      <form class="fl-filters" role="search"><label>Company, ticker or investment argument<input name="q" type="search" placeholder="Search all funds and all ideas" autocomplete="off"></label><label>Idea type<select name="type"><option value="">All ideas</option>${types.map(t=>`<option value="${t}">${escape(label(t))}</option>`).join('')}</select></label><label>From<input name="from" type="date"></label><label>To<input name="to" type="date"></label><label class="fl-mobile-select">Fund<select name="fund"><option value="">All funds</option></select></label><button type="submit">Search</button><button type="button" data-reset class="fl-reset">Reset</button></form>
      <div class="fl-grid"><aside class="fl-directory" aria-label="Fund directory"><h2>Funds <span class="fl-directory-count"></span></h2><input type="search" aria-label="Find a fund" placeholder="Find a fund"><ul></ul></aside><div id="fl-reading" class="fl-reading" tabindex="-1" aria-live="polite"><p role="status">Loading the archive…</p></div></div><dialog aria-labelledby="fl-review-title"></dialog>`;
    const reading = root.querySelector('.fl-reading'), form = root.querySelector('form'), directory = root.querySelector('.fl-directory'), dialog = root.querySelector('dialog');
    const on = (el,event,fn) => el.addEventListener(event,fn,{signal:abort.signal});
    const link = extra => '/fund-letters/?' + new URLSearchParams({...Object.fromEntries(params),...extra});
    const showError = error => {if(!disposed) reading.innerHTML = `<div class="fl-error" role="alert">${escape(error.message)}</div><button type="button" data-retry>Try again</button>`;};
    function remember() {
      if (embedded) sessionStorage.setItem('fl-reader-state',params.toString());
      else history.replaceState({...history.state, flScroll:global.scrollY,flPages:pages},'',location.href);
    }
    function navigate(change, push = true) {
      remember();
      for (const [key,value] of Object.entries(change)) value ? params.set(key,value) : params.delete(key);
      if (embedded) sessionStorage.setItem('fl-reader-state',params.toString());
      else if (push) history.pushState({flScroll:0},'', '?' + params.toString());
      load();
    }
    function drawDirectory(filter = '') {
      const query = filter.toLowerCase();
      const rows = funds.filter(f => `${f.name} ${f.manager} ${f.strategy}`.toLowerCase().includes(query));
      directory.querySelector('ul').innerHTML = `<li><a href="${escape(link({fund:'',letter:'',idea:'',mode:''}))}" data-fund="" aria-current="${!params.get('fund')}"><strong>All funds</strong><small>All published investment ideas</small></a></li>` + rows.map(f => `<li><a href="${escape(link({fund:f.id,letter:'',idea:'',mode:''}))}" data-fund="${escape(f.id)}" aria-current="${params.get('fund')===f.id}"><strong>${escape(f.name)}</strong>${f.manager?`<small>${escape(f.manager)}</small>`:''}<small>${f.letter_count} letters · latest ${escape(f.latest || 'undated')}</small></a></li>`).join('');
      directory.querySelector('.fl-directory-count').textContent = `(${funds.length})`;
      form.elements.fund.innerHTML = '<option value="">All funds</option>' + funds.map(f=>`<option value="${escape(f.id)}">${escape(f.name)} (${f.letter_count})</option>`).join('');
      form.elements.fund.value = params.get('fund') || '';
    }
    function resultHtml(item) {
      return `<article class="fl-result"><div class="fl-meta">${escape(item.fund)} · ${escape(item.reporting_period || 'Undated')} · ${escape(label(item.idea_type))}${item.ticker?' · '+escape(item.ticker):''}</div><h3><a href="${escape(link({fund:item.fund_id,letter:item.letter_id,idea:item.id}))}" data-open-letter="${escape(item.letter_id)}" data-open-fund="${escape(item.fund_id)}" data-open-idea="${escape(item.id)}">${escape(item.title)}</a></h3>${paragraphs(item.summary.split(/\n\s*\n/)[0])}</article>`;
    }
    function letterHtml(letter) {
      return `<article class="fl-letter" id="fl-letter-${escape(letter.id)}"><header><div><div class="fl-date">${escape(period(letter))}</div><h3>${escape(letter.fund)}</h3></div>${role==='owner'?`<button type="button" data-source="${escape(letter.id)}">Source & revisions</button>`:''}</header><div class="fl-overview">${paragraphs(letter.overview)}</div>${letter.ideas.length?`<nav class="fl-contents" aria-label="Ideas in this letter"><h4>In this letter</h4><ul>${letter.ideas.map(i=>`<li><a href="${escape(link({fund:letter.fund_id,letter:letter.id,idea:i.id}))}" data-jump="fl-idea-${escape(letter.id)}-${escape(i.id)}">${escape(i.title)}</a></li>`).join('')}</ul></nav>`:''}
        ${letter.ideas.map(i=>`<section class="fl-idea" id="fl-idea-${escape(letter.id)}-${escape(i.id)}"><div class="fl-meta">${escape(label(i.idea_type))}${i.ticker?' · '+escape(i.ticker):''}${i.activity?' · '+escape(i.activity):''}</div><h4>${escape(i.title)}</h4>${paragraphs(i.summary)}${i.evolution?`<h4>What changed</h4>${paragraphs(i.evolution)}<a href="${escape(link({fund:letter.fund_id,letter:i.compared_letter_id,idea:''}))}" data-open-fund="${escape(letter.fund_id)}" data-open-letter="${escape(i.compared_letter_id)}">Earlier discussion</a>`:''}</section>`).join('')}
        <footer class="fl-revision">Attributed to ${escape(letter.fund)} · ${escape(letter.reporting_period || 'Period unavailable')}${letter.summary_published_at?` · Summary published ${escape(letter.summary_published_at.slice(0,10))}`:''}${letter.summary_revised_at?` · Revision ${escape(letter.summary_revised_at.slice(0,10))}`:''}</footer></article>`;
    }
    function moreButton() {
      reading.querySelector('[data-more]')?.remove(); observer?.disconnect();
      if (next === null) return;
      const button = document.createElement('button'); button.type='button'; button.className='fl-more'; button.dataset.more=''; button.textContent=params.get('fund')&&!hasFilters()?'Load older letters':'Load more results'; reading.append(button);
      if ('IntersectionObserver' in global && !restoring) {observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)&&!loading)load(true);},{rootMargin:'200px'});observer.observe(button);}
    }
    function hasFilters() {return ['q','type','from','to'].some(k=>params.get(k));}
    async function load(append = false, restoreScroll = null) {
      if (loading && append) return;
      const ticket = ++sequence;
      loading=true; observer?.disconnect();
      if(!append) {next=null;pages=0;reading.innerHTML='<p class="fl-status" role="status">Loading letters…</p>';}
      else {const btn=reading.querySelector('[data-more]');if(btn){btn.disabled=true;btn.textContent='Loading…';}}
      for(const key of ['q','type','from','to','fund']) form.elements[key].value=params.get(key)||'';
      const reviewing=params.get('mode')==='review'&&role==='owner';
      for(const key of ['type','from','to','fund'])form.elements[key].closest('label').hidden=reviewing;
      form.elements.q.closest('label').firstChild.textContent=reviewing?'Fund, letter or review issue':'Company, ticker or investment argument';
      form.elements.q.placeholder=reviewing?'Find a fund or review issue':'Search all funds and all ideas';
      if(reviewing)form.elements.q.value=params.get('review_q')||'';
      drawDirectory(directory.querySelector('input').value);
      try {
        const args={...Object.fromEntries(params),offset:append?String(next):'0'};
        if (params.get('mode')==='review' && role==='owner') {
          const data=await api({...args,action:'review'}); if(ticket!==sequence||disposed)return;
          if(!append)reading.innerHTML=`<header><h2>Review queue</h2><p class="fl-notice">${data.coverage?.published||0} of ${data.coverage?.letters||0} letters published. Readers see published summaries only.</p></header><section data-items></section>`;
          reading.querySelector('[data-items]').insertAdjacentHTML('beforeend',data.reviews.map(r=>`<article class="fl-review-item"><div class="fl-meta">${escape(label(r.kind))}</div><strong>${escape(r.fund)} · ${escape(r.reporting_period || 'Undated')}</strong><p>${escape(r.detail)}</p><button type="button" data-source="${escape(r.letter_id)}">Review letter</button></article>`).join('') || '<p>No unresolved reviews.</p>');
          next=data.next_offset;
        } else if(params.get('fund') && (!hasFilters() || params.get('letter'))) {
          const data=await api({...args,action:'letters'}); if(ticket!==sequence||disposed)return;
          const fund=funds.find(f=>f.id===params.get('fund'));
          if(!append)reading.innerHTML=`<header class="fl-fund-header"><div class="fl-meta">Fund archive</div><h2>${escape(fund?.name || 'Fund')}</h2>${fund?.manager?`<p>${escape(fund.manager)}</p>`:''}${fund?.strategy?`<p>${escape(fund.strategy)}</p>`:''}<div class="fl-archive-links"><span class="fl-date">${fund?.letter_count||0} published letters</span>${params.get('letter')?'<button type="button" data-archive>Complete archive</button>':''}${hasFilters()?'<button type="button" data-results>Back to search results</button>':''}</div><select class="fl-letter-select" aria-label="Choose a letter"><option value="">Choose a letter from the archive</option></select></header><section data-items></section>`;
          const items=reading.querySelector('[data-items]');items.insertAdjacentHTML('beforeend', data.letters.map(letterHtml).join('') || '<div class="fl-empty"><h2>No published letters here yet</h2><p>Choose another fund or return to all funds.</p></div>');
          next=data.next_offset;
          // Separate lightweight selector endpoint covers the entire archive, including unloaded letters.
          if(!append) api({action:'archive',fund:params.get('fund')}).then(archive=>{if(ticket!==sequence||disposed)return;const select=reading.querySelector('.fl-letter-select');if(select)select.innerHTML='<option value="">Choose a letter</option>'+archive.letters.map(l=>`<option value="${escape(l.id)}"${l.id===params.get('letter')?' selected':''}>${escape(period(l))}</option>`).join('');}).catch(()=>{});
        } else {
          const data=await api({...args,action:'search'});if(ticket!==sequence||disposed)return;
          if(!append) reading.innerHTML=`<header><div class="fl-meta">${hasFilters()?'Search the archive':'Across the library'}</div><h2>${hasFilters()?'Investment ideas':'Recent investment arguments'}</h2><p class="fl-date">${params.get('fund')?escape(funds.find(f=>f.id===params.get('fund'))?.name || ''):'All funds'} · ${params.get('type')?escape(label(params.get('type'))):'All ideas'}</p></header><section data-items></section>`;
          reading.querySelector('[data-items]').insertAdjacentHTML('beforeend',data.results.map(resultHtml).join('') || `<div class="fl-empty"><h2>${funds.length?'No matching ideas':'The archive is being prepared'}</h2><p>${funds.length?'Try a different company, date range or idea type. Reset filters to explore every published idea.':'Letters will appear here after their summaries have completed review.'}</p></div>`);
          next=data.next_offset;
        }
        pages++;moreButton();
        if(!append && params.get('idea')) root.querySelector(`#fl-idea-${CSS.escape(params.get('letter'))}-${CSS.escape(params.get('idea'))}`)?.scrollIntoView();
        if(restoreScroll!==null)global.scrollTo(0,restoreScroll);
      }catch(error){if(ticket===sequence)showError(error);}finally{if(ticket===sequence)loading=false;}
    }
    async function review(letterId, revisionId = '') {
      dialog.innerHTML='<p role="status">Loading private review…</p>';if(!dialog.open)dialog.showModal();
      try {
        const [source,versions,draftResult]=await Promise.all([api({action:'source',letter:letterId,revision:revisionId}),api({action:'revisions',letter:letterId}),api({action:'draft',letter:letterId,revision:revisionId})]);
        let revision=draftResult.draft, draft=revision?.content;
        const validationErrors = revision ? (JSON.parse(revision.checks_json || '{}').errors || []) : [];
        const sourceUrl=source.source.source_url;
        const validUrl=sourceUrl && /^https:\/\//.test(sourceUrl);
        dialog.innerHTML=`<header><div><div class="fl-meta">Owner review</div><h2 id="fl-review-title">Letter sources & revisions</h2></div><button type="button" data-close aria-label="Close review">Close</button></header>${validUrl?`<p><a href="${escape(sourceUrl)}" target="_blank" rel="noopener noreferrer">Open original letter</a></p>`:'<p>The original is available through the private research vault.</p>'}<p><a href="/api/fund-letters?action=document&amp;letter=${encodeURIComponent(letterId)}" target="_blank" rel="noopener noreferrer">Read full source text</a></p><details><summary>Private references & evidence</summary><pre>${escape(JSON.stringify(source,null,2))}</pre></details><label>Revision<select data-revision><option value="">Choose a revision</option>${versions.revisions.map(v=>`<option value="${escape(v.id)}"${v.id===revision?.id?' selected':''}>${escape(v.created_at)} · ${escape(v.status)} · ${escape(v.author)}</option>`).join('')}</select></label>
          ${validationErrors.length?`<div class="fl-error">${validationErrors.map(escape).join('<br>')}</div>`:''}
          ${draft?`<label>Overview<textarea data-overview>${escape(draft.overview)}</textarea></label>${draft.ideas.map((i,n)=>`<fieldset data-idea="${n}"><legend>${escape(i.title)}</legend><label>Idea title<input data-idea-field="title" value="${escape(i.title)}"></label><label>Company or ticker<input data-idea-field="ticker" value="${escape(i.ticker)}"></label><label>Idea type<select data-idea-field="idea_type">${types.map(t=>`<option value="${t}"${i.idea_type===t?' selected':''}>${escape(label(t))}</option>`).join('')}</select></label><label>Position activity<input data-idea-field="activity" value="${escape(i.activity)}"></label><label>Summary<textarea data-idea-field="summary">${escape(i.summary)}</textarea></label><details><summary>Update a comparison with an earlier letter</summary><label>What changed<textarea data-idea-field="evolution">${escape(i.evolution)}</textarea></label><label>Earlier published letter ID<input data-idea-field="compared_letter_id" value="${escape(i.compared_letter_id)}"></label></details></fieldset>`).join('')}<details><summary>Completeness checklist & draft evidence</summary><pre>${escape(JSON.stringify({checklist:draft.checklist,ideas:draft.ideas.map(i=>({title:i.title,evidence:i.evidence}))},null,2))}</pre></details><fieldset class="fl-checks"><legend>Editorial review</legend>${Object.entries(checks).map(([key,text])=>`<label><input type="checkbox" name="${key}">${escape(text)}</label>`).join('')}</fieldset><div class="fl-dialog-actions"><button type="button" data-save>Save new revision</button><button type="button" data-publish class="fl-primary">Publish selected revision</button></div>`:'<p class="fl-notice">No summary draft yet. This letter is queued for full document synthesis.</p>'}
          <details><summary>Resolve an archive issue</summary><label>Issue<select data-kind>${['identity','extraction','duplicate_sources','date'].map(k=>`<option value="${k}">${escape(label(k))}</option>`).join('')}</select></label><label>Decision and supporting evidence<textarea data-reason></textarea></label><label>Verified letter date (leave blank if unavailable)<input type="date" data-date></label><button type="button" data-resolve>Record review decision</button></details><p class="fl-dialog-status" role="status"></p>`;
        dialog.querySelector('[data-close]').onclick=()=>dialog.close();
        const status=dialog.querySelector('.fl-dialog-status');
        const busy=async fn=>{try{status.textContent='Saving…';await fn();}catch(error){status.textContent=error.message;}};
        dialog.querySelector('[data-resolve]').onclick=()=>busy(async()=>{const kind=dialog.querySelector('[data-kind]').value;await api({}, {action:kind==='date'?'date':'resolve',letter_id:letterId,kind,reason:dialog.querySelector('[data-reason]').value,letter_date:dialog.querySelector('[data-date]').value||null});status.textContent='Review decision recorded.';});
        const select=dialog.querySelector('[data-revision]');
        select.onchange=()=>{if(select.value)review(letterId,select.value);};
        if(draft){
          const readEdits=()=>{const edited=structuredClone(draft);edited.overview=dialog.querySelector('[data-overview]').value;dialog.querySelectorAll('[data-idea]').forEach(group=>group.querySelectorAll('[data-idea-field]').forEach(el=>{const idea=edited.ideas[Number(group.dataset.idea)],key=el.dataset.ideaField;if(el.value||Object.hasOwn(idea,key))idea[key]=el.value||(key==='summary'||key==='title'?'':null);}));return edited;};
          dialog.querySelector('[data-save]').onclick=()=>busy(async()=>{const result=await api({}, {action:'draft',letter_id:letterId,draft:readEdits()});await review(letterId,result.revision_id);});
          dialog.querySelector('[data-publish]').onclick=()=>busy(async()=>{if(JSON.stringify(readEdits())!==JSON.stringify(draft))throw new Error('Save your changes as a new revision before publishing.');const attestations=Object.fromEntries(Object.keys(checks).map(k=>[k,dialog.querySelector(`[name="${k}"]`).checked]));await api({}, {action:'publish',letter_id:letterId,revision_id:revision.id,expected_revision:source.source.published_revision,attestations});status.textContent='Published. The previous revision remains available.';source.source.published_revision=revision.id;load();});
        }
      }catch(error){dialog.innerHTML=`<h2 id="fl-review-title">Review unavailable</h2><p>${escape(error.message)}</p><button data-close type="button">Close</button>`;dialog.querySelector('button').onclick=()=>dialog.close();}
    }
    on(form,'submit',e=>{e.preventDefault();if(params.get('mode')==='review'&&role==='owner'){navigate({review_q:form.elements.q.value,letter:'',idea:''});return;}navigate(Object.fromEntries(['q','type','from','to','fund'].map(k=>[k,form.elements[k].value]).concat([['letter',''],['idea',''],['mode','']])));});
    on(form.querySelector('[data-reset]'),'click',()=>navigate({q:'',type:'',from:'',to:'',fund:'',letter:'',idea:'',mode:''}));
    on(form.elements.fund,'change',()=>navigate({fund:form.elements.fund.value,letter:'',idea:'',mode:''}));
    on(directory.querySelector('input'),'input',e=>drawDirectory(e.target.value));
    on(root,'click',e=>{
      const target=e.target.closest('a,button');if(!target||e.ctrlKey||e.metaKey||e.shiftKey)return;
      if(target.hasAttribute('data-fund')){e.preventDefault();navigate({fund:target.dataset.fund,letter:'',idea:'',mode:''});}
      if(target.dataset.openLetter){e.preventDefault();navigate({fund:target.dataset.openFund,letter:target.dataset.openLetter,idea:target.dataset.openIdea||''});}
      if(target.dataset.jump){e.preventDefault();const destination=new URL(target.href).searchParams;navigate({fund:destination.get('fund'),letter:destination.get('letter'),idea:destination.get('idea')});}
      if(target.hasAttribute('data-more'))load(true);
      if(target.hasAttribute('data-retry'))load();
      if(target.hasAttribute('data-archive'))navigate({letter:'',idea:'',q:'',type:'',from:'',to:''});
      if(target.hasAttribute('data-results'))navigate({letter:'',idea:''});
      if(target.dataset.source)review(target.dataset.source);
      if(target.hasAttribute('data-review-queue'))navigate({mode:params.get('mode')==='review'?'':'review',letter:'',idea:''});
    });
    on(root,'change',e=>{if(e.target.matches('.fl-letter-select')&&e.target.value)navigate({letter:e.target.value,idea:''});});
    if(!embedded)on(global,'popstate',async e=>{params=new URLSearchParams(location.search);restoring=true;await load();for(let n=1;n<(e.state?.flPages||1)&&next!==null;n++)await load(true);restoring=false;moreButton();global.scrollTo(0,e.state?.flScroll||0);});
    try {
      const [session,catalog]=await Promise.all([api({action:'session'}),api({action:'funds'})]);
      if(disposed)return;
      role=session.role;funds=catalog.funds;
      if(role==='owner')root.querySelector('.fl-owner-tools').innerHTML=`<a href="/">Dashboard</a><button type="button" data-review-queue>Review queue</button>`;
      await load();
      if(role==='owner'&&params.get('review'))await review(params.get('review'));
    }catch(error){showError(error);}
    return controller;
  }
  global.FundLettersReader={mount,unmount:root=>states.get(root)?.dispose()};
  if(document.getElementById('fund-letters-app'))mount(document.getElementById('fund-letters-app'));
})(window);
