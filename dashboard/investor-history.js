/* Historical manager directory. Dates and fund scopes remain distinct. */
(function () {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url = path => `${(window.location?.pathname || '').replace(/\/index\.html$/i, '').replace(/\/$/, '')}/${path}`;
  const money = value => value == null ? '—' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:0}).format(value);
  const quarterOf = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? `${value.slice(0,4)}Q${Math.ceil(Number(value.slice(5,7))/3)}` : '';
  const historyFor = manager => manager.history || (manager.quarter ? [{quarter:manager.quarter, period_end:manager.period_end, positions:manager.positions,ssi_overlap:manager.ssi_overlap}] : []);
  function directoryRows(managers, {quarter='latest',query='',overlap=false,source='all'}={}) {
    return managers.flatMap(manager => {
      const history = historyFor(manager);
      const pending=manager.identity_status==='unverified_document_identity';
      if(source==='review' ? !pending : pending) return [];
      const record = quarter === 'latest' ? history.at(-1) : history.find(row => row.quarter === quarter);
      const disclosed = (manager.disclosure_quarters || []).includes(quarter) || quarter === 'latest' && manager.disclosure_count > 0;
      const gap=quarter!=='latest' && (manager.filing_gaps || []).some(row=>quarterOf(row.period_end)===quarter);
      if (quarter !== 'latest' && !record && !disclosed && !gap) return [];
      if (source === '13f' && !record && !gap || source === 'disclosures' && !disclosed) return [];
      const row = {...manager,...record,...(quarter!=='latest' && !record ? {quarter,positions:null,ssi_overlap:null,period_end:null} : {})};
      if (overlap && !(row.ssi_overlap > 0)) return [];
      if (!`${row.name} ${row.manager_id}`.toLowerCase().includes(query.toLowerCase())) return [];
      return [row];
    }).sort((a,b) => Number(Boolean(historyFor(b).length || b.disclosure_count))-Number(Boolean(historyFor(a).length || a.disclosure_count)) || (b.ssi_overlap || 0)-(a.ssi_overlap || 0) || a.name.localeCompare(b.name));
  }
  function availablePeriods(manager, source='all') {
    return [...new Set([...(source==='disclosures' ? [] : [...historyFor(manager).map(row=>row.quarter),...(manager.filing_gaps || []).map(row=>quarterOf(row.period_end))]),...(source==='13f' ? [] : manager.disclosure_quarters || [])])].filter(Boolean).sort().reverse();
  }
  function sourceLink(href, label) {
    try {
      const resolved = new URL(href, window.location?.origin || 'https://localhost');
      if (!['https:','http:'].includes(resolved.protocol)) return '';
      return `<a href="${esc(resolved.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
    } catch { return ''; }
  }
  function positionsTable(rows, {basis=''}={}) {
    if (!rows.length) return '<p>No disclosed positions for this snapshot.</p>';
    return `<div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Position</th><th>Weight${basis ? `<small>${esc(basis)}</small>` : ''}</th><th>Value (USD)</th></tr></thead><tbody>${[...rows].sort((a,b)=>(b.value_usd || 0)-(a.value_usd || 0) || (b.weight_pct || 0)-(a.weight_pct || 0)).map(row => {
      const kind = [row.title_of_class,row.put_call,(row.position_side==='Short' ? 'Short position' : ''),(row.sh_prn === 'PRN' ? 'Principal amount' : '')].filter(Boolean).join(' · ');
      const weight = row.weight_pct == null ? '—' : `${Number(row.weight_pct).toFixed(2)}%`;
      const weightBasis = {fund_net_assets:'Fund NAV',reported_13f_equities:'Reported 13F book',reported_13f_non_option_book:'Reported 13F book',unspecified_disclosed_weight:'As disclosed; basis unspecified'}[row.weight_basis] || '';
      return `<tr><td>${esc(row.ticker || row.issuer || row.isin || row.cusip)}${row.ticker && row.issuer && row.ticker!==row.issuer ? `<small>${esc(row.issuer)}</small>` : ''}${kind ? `<small>${esc(kind)}</small>` : ''}${row.country || row.currency ? `<small>${esc([row.country,row.currency].filter(Boolean).join(' · '))}</small>` : ''}</td><td>${weight}${weightBasis ? `<small>${esc(weightBasis)}</small>` : ''}</td><td>${money(row.value_usd)}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }
  async function read(path) {
    const response = await fetch(url(path));
    if (!response.ok) throw new Error(`Holdings data unavailable (${response.status})`);
    const result = await response.json();
    if (result.private_snapshot) throw new Error('The authorized holdings snapshot has not been restored.');
    return result;
  }
  async function fill() {
    const root = document.getElementById('managers-page');
    if (!root) return;
    let legacy = false, index;
    try { index = await read('data/holdings/directory_index.json'); }
    catch { index = await read('data/holdings/managers_index.json'); legacy = true; }
    if (!root.isConnected) return;
    const managers = index.managers || [];
    const quarters = [...new Set(managers.flatMap(m => availablePeriods(m)))].filter(Boolean).sort().reverse();
    let quarter='latest',query='',overlap=false,source='all',page=0,ticket=0,selected=null;
    root.innerHTML = `<p class="investor-context">Explore dated public filings and fund disclosures. A 13F covers reportable US-listed securities. International disclosures may cover only part of a fund and use different reporting dates.</p>
      <div class="workspace-filter"><label class="workspace-search">Find an investor<input type="search" data-history-search placeholder="Manager name"></label>
      <label>Holdings quarter<select data-history-quarter><option value="latest">Latest available per investor</option>${quarters.map(q=>`<option value="${esc(q)}">${esc(q)}</option>`).join('')}</select></label>
      <label>Sources<select data-history-source><option value="all">All holdings sources</option><option value="13f">13F filings</option><option value="disclosures">Fund disclosures</option><option value="review">Fund names to review</option></select></label>
      <label>Portfolio relevance<select data-history-overlap><option value="all">All investors</option><option value="book">Overlaps our book</option></select></label></div>
      <p class="investor-context" data-history-coverage></p>
      <div class="investor-directory"><div><p data-history-count class="investor-context"></p><div class="workspace-scroll" data-history-list></div>
      <div class="workspace-filter"><button type="button" data-history-prev>Previous</button><span data-history-page></span><button type="button" data-history-next>Next</button></div></div>
      <aside class="investor-detail" data-history-detail tabindex="-1" aria-label="Investor details"><h3>Select an investor</h3><p>Explore their filing history and dated fund disclosures.</p></aside></div>`;
    const list=root.querySelector('[data-history-list]'), detail=root.querySelector('[data-history-detail]');
    const failures = (index.coverage?.unresolved_count || 0) + (index.disclosure_coverage?.unresolved_sources || 0);
    const credible=directoryRows(managers).length, pending=managers.filter(m=>m.identity_status==='unverified_document_identity').length;
    root.querySelector('[data-history-coverage]').textContent = `${credible} investors · ${quarters.length} reporting quarters${pending ? ` · ${pending} source names await identity review` : ''}${failures ? ` · ${failures} source records need review` : ''}. ${index.coverage?.complete ? 'Discovered filings processed.' : index.coverage?.backfill_processed ? 'All discovered filings processed; source review remains.' : 'Historical backfill and source review are in progress.'}`;
    async function select(id, requested=quarter) {
      selected=id;
      const current=++ticket, manager=managers.find(m=>m.manager_id===id);
      detail.innerHTML='<p>Loading dated holdings.</p>';
      try {
        const history=historyFor(manager);
        const period=requested==='latest' ? history.at(-1)?.quarter : requested;
        const filingMeta=history.find(row=>row.quarter===period);
        const booksPromise=filingMeta && source!=='disclosures' ? read(legacy ? `data/holdings/by_manager/${encodeURIComponent(id)}.json` : `data/holdings/${filingMeta.book_path || `history/${encodeURIComponent(period)}/${encodeURIComponent(id)}.json`}`).then(async value=>{
          const book=value.quarters ? value.quarters[period] : value;
          if (!book) throw new Error('Selected historical quarter is unavailable.');
          if (book.positions_parts) {
            const parts=await Promise.all(book.positions_parts.map(path=>read(`data/holdings/${path}`)));
            book.positions=parts.flatMap(part=>part.positions || []);
          }
          return book;
        }) : Promise.resolve(null);
        const disclosurePromise=manager.disclosure_count && source!=='13f' ? read(`data/holdings/disclosures/${encodeURIComponent(id)}.json`).then(async manifest=>{
          if (!manifest.quarters) return manifest;
          const wanted=requested==='latest' ? [...manifest.latest_quarters,'undated'] : [requested];
          const paths=[...new Set(wanted.flatMap(q=>manifest.quarters[q] || []))];
          const parts=await Promise.all(paths.map(path=>read(`data/holdings/${path}`)));
          const snapshots=parts.flatMap(part=>part.snapshots || []);
          await Promise.all(snapshots.map(async snapshot=>{
            if (snapshot.positions_parts) {
              const positions=await Promise.all(snapshot.positions_parts.map(path=>read(`data/holdings/${path}`)));
              snapshot.positions=positions.flatMap(part=>part.positions || []);
            }
          }));
          if (requested==='latest') {
            const dates=new Map();
            const key=d=>(d.quarter || quarterOf(d.period_end) || quarterOf(d.disclosed_at))+(d.period_end || d.disclosed_at || '')+(d.filed_at || '')+(d.source_kind==='nport' ? d.id : '');
            for(const d of snapshots) dates.set(d.vehicle_id, [dates.get(d.vehicle_id) || '',key(d)].sort().at(-1));
            return {snapshots:snapshots.filter(d=>key(d)===dates.get(d.vehicle_id))};
          }
          return {snapshots};
        }) : Promise.resolve({snapshots:[]});
        const results=await Promise.allSettled([booksPromise,disclosurePromise]);
        if (current!==ticket || !root.isConnected) return;
        const book=results[0].status==='fulfilled' ? results[0].value : null;
        const disclosures=results[1].status==='fulfilled' ? results[1].value.snapshots || [] : [];
        const targetDisclosure=requested==='latest' ? disclosures.map(d=>d.quarter || quarterOf(d.period_end) || quarterOf(d.disclosed_at)).filter(Boolean).sort().at(-1) : requested;
        const visible=requested==='latest' ? disclosures : disclosures.filter(d=>(d.quarter || quarterOf(d.period_end) || quarterOf(d.disclosed_at))===targetDisclosure);
        const periods=availablePeriods(manager,source);
        detail.innerHTML=`<h3>${esc(manager.name)}</h3><div class="workspace-filter"><label>Reporting quarter<select data-detail-quarter><option value="latest">Latest available by source</option>${periods.map(q=>`<option value="${esc(q)}" ${q===requested?'selected':''}>${esc(q)}</option>`).join('')}</select></label></div>
          ${manager.identity_status==='unverified_document_identity' ? '<p class="investor-context">Fund name from a document; manager identity needs review.</p>' : ''}
          <p class="investor-context">${history.length} 13F quarters${history.length ? ` · ${esc(history[0].quarter)}–${esc(history.at(-1).quarter)}` : ''} · ${manager.disclosure_count || 0} fund disclosures</p>
          ${(manager.fund_ids || []).map(fund=>sourceLink(`/fund-letters/?fund=${encodeURIComponent(fund)}`,'Read fund letters')).join(' · ')}
          ${results[0].status==='rejected' ? '<p>The selected historical filing could not be loaded. Try again.</p>' : ''}
          ${source==='disclosures' ? '' : book ? `<h4>13F holdings · ${esc(book.period_end || period)}</h4><p>Filed ${esc(book.filed_at || 'date unavailable')}${book.partial ? ' · Partial or awaiting reconciliation' : ''}${book.confidential_omitted ? ' · Confidential positions omitted' : ''}</p>${positionsTable(book.positions || [],{basis:'Reported 13F book, excluding options'})}<details class="workspace-fold"><summary>Filing sources and amendments</summary>${(book.filings || []).map(f=>`<p>${esc(f.form)} · ${esc(f.filed_at)} · ${sourceLink(f.source_url,f.accession)}</p>`).join('')}</details>` : '<p>No 13F book is available for this selection. This does not mean the investor held no positions.</p>'}
          ${(manager.filing_gaps || []).length ? `<details class="workspace-fold"><summary>${manager.filing_gaps.length} historical filing records await review</summary>${manager.filing_gaps.map(f=>`<p>${esc(f.period_end || 'Reporting date unavailable')} · ${sourceLink(f.source_url,f.accession)} · ${esc(f.reason)}</p>`).join('')}</details>` : ''}
          <h4>Fund disclosures</h4><p class="investor-context">Each fund and date is shown separately. Disclosed positions do not establish a complete manager portfolio.</p>
          ${results[1].status==='rejected' ? '<p>Fund disclosures could not be loaded. Try again.</p>' : visible.map(d=>`<details class="workspace-fold" open><summary>${esc(d.vehicle_name || manager.name)} · ${esc(d.period_end || d.disclosed_at || d.quarter || 'date unavailable')}</summary><p>${d.partial ? 'Partial disclosure' : 'Registered fund portfolio'}${!d.period_end ? ' · Holdings as-of date not established' : ''}${d.filed_at ? ` · Filed ${esc(d.filed_at)}` : ''} ${d.source_url ? sourceLink(d.source_url,'Source disclosure') : ''}</p>${d.adviser_relationship_observed_at ? `<p class="investor-context">Adviser link observed ${esc(d.adviser_relationship_observed_at)} · ${sourceLink(d.adviser_relationship_source,'Adviser disclosure')}</p>` : ''}${positionsTable(d.positions || [])}</details>`).join('') || '<p>No fund disclosure is available for this selection.</p>'}`;
        detail.querySelector('[data-detail-quarter]').addEventListener('change',event=>select(id,event.target.value));
        detail.focus({preventScroll:true});if(window.innerWidth<900)detail.scrollIntoView({block:'start'});
      } catch(error) { if(current===ticket) detail.textContent=error.message; }
    }
    function paint() {
      const rows=directoryRows(managers,{quarter,query,overlap,source});
      if(selected && !rows.some(row=>row.manager_id===selected)) {
        selected=null;
        ticket++;
        detail.innerHTML='<h3>Select an investor</h3><p>Explore their filing history and dated fund disclosures.</p>';
      }
      page=Math.max(0,Math.min(page,Math.max(0,Math.ceil(rows.length/25)-1)));
      root.querySelector('[data-history-count]').textContent=`${rows.length} investors · sorted by portfolio overlap`;
      list.innerHTML=`<table class="workspace-table"><thead><tr><th>Investor</th><th>In our book</th><th>Positions</th><th>Coverage</th></tr></thead><tbody>${rows.slice(page*25,(page+1)*25).map(row=>`<tr><td><button type="button" data-history-manager="${esc(row.manager_id)}">${esc(row.name)}</button><small>${esc(row.first_quarter || 'History not loaded')}${row.quarter ? `–${esc(row.quarter)}` : ''}</small></td><td>${row.ssi_overlap ?? '—'}</td><td>${row.positions ?? '—'}</td><td>${historyFor(row).length} 13F quarters${row.disclosure_count ? `<small>${row.disclosure_count} disclosures</small>` : ''}${row.coverage_status==='partial' ? '<small>Source review pending</small>' : ''}</td></tr>`).join('')}</tbody></table>${rows.length ? '' : '<p>No investors match these filters. Choose all sources or another reporting quarter.</p>'}`;
      root.querySelector('[data-history-page]').textContent=`Page ${page+1} of ${Math.max(1,Math.ceil(rows.length/25))}`;
      root.querySelector('[data-history-prev]').disabled=page===0;
      root.querySelector('[data-history-next]').disabled=(page+1)*25>=rows.length;
      list.querySelectorAll('[data-history-manager]').forEach(button=>button.addEventListener('click',()=>select(button.dataset.historyManager)));
    }
    root.querySelector('[data-history-search]').addEventListener('input',event=>{query=event.target.value;page=0;paint();});
    root.querySelector('[data-history-quarter]').addEventListener('change',event=>{quarter=event.target.value;page=0;paint();if(selected)select(selected);});
    root.querySelector('[data-history-overlap]').addEventListener('change',event=>{overlap=event.target.value==='book';page=0;paint();});
    root.querySelector('[data-history-source]').addEventListener('change',event=>{source=event.target.value;page=0;paint();if(selected)select(selected);});
    root.querySelector('[data-history-prev]').addEventListener('click',()=>{page--;paint();});
    root.querySelector('[data-history-next]').addEventListener('click',()=>{page++;paint();});
    paint();
  }
  window.InvestorHistory = {fill:()=>fill().catch(error=>{const root=document.getElementById('managers-page');if(root)root.textContent=error.message;}),directoryRows,positionsTable,sourceLink,availablePeriods};
})();
