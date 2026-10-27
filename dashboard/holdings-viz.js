/* Held-by panel. 13F context only. It does not feed the base return. */
(function () {
  let summary = null;
  let summaryPromise = null;

  function dataUrl(path) {
    const base = window.location.pathname.replace(/\/index\.html$/i, "").replace(/\/$/, "");
    return `${base}/${path}`;
  }

  function ensureSummary() {
    if (summary) return Promise.resolve(summary);
    if (!summaryPromise) {
      summaryPromise = fetch(dataUrl("data/fund_holdings_summary.json"))
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
          summary = payload;
          return payload;
        })
        .catch(() => null);
    }
    return summaryPromise;
  }

  function badgeHtml(ticker) {
    const row = summary && summary.tickers && summary.tickers[ticker];
    if (!row || !row.holder_count) return "";
    const mark = row.net === "add" ? "▲" : row.net === "trim" ? "▼" : "";
    const title = "Tracked 13F holders. Context only. Not an input to the base return.";
    return ` <span class="badge" title="${title}">H:${row.holder_count}${mark}</span>`;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));
  }

  function secLink(url) {
    if (!/^https:\/\/(www\.)?sec\.gov\//.test(url || "")) return "";
    return ` · <a href="${escapeHtml(url)}" target="_blank" rel="noopener">SEC filing</a>`;
  }

  function money(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    if (Math.abs(number) >= 1e9) return `$${(number / 1e9).toFixed(1)}b`;
    if (Math.abs(number) >= 1e6) return `$${(number / 1e6).toFixed(1)}m`;
    return `$${Math.round(number).toLocaleString("en-US")}`;
  }

  function shares(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    return number.toLocaleString("en-US");
  }

  function renderTicker(ticker, escapeHtml) {
    const safe = escapeHtml(ticker);
    return `<details class="detail-section" id="held-by" data-ticker="${safe}"><summary>Held by</summary><div class="held-by-body" style="margin-top:10px">Loading 13F holders…</div></details>`;
  }

  function fillTicker(ticker) {
    const slot = document.querySelector("#held-by .held-by-body");
    const root = document.getElementById("held-by");
    if (!slot || !root || root.dataset.ticker !== ticker) return;
    fetch(dataUrl(`data/holdings/by_ticker/${encodeURIComponent(ticker)}.json`))
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (root.dataset.ticker !== ticker) return;
        if (!payload || !(payload.holders || []).length) {
          slot.textContent = "No tracked manager reported this stock in the latest 13F books on file.";
          return;
        }
        const lines = payload.holders.slice(0, 25).map((holder) => {
          const change = holder.change_type ? ` · ${escapeHtml(holder.change_type)}` : "";
          const weight = holder.weight_pct != null ? ` · ${escapeHtml(holder.weight_pct)}% of book` : "";
          const when = holder.period_end ? ` · as of ${escapeHtml(holder.period_end)}` : "";
          const filed = holder.filed_at ? `, filed ${escapeHtml(holder.filed_at)}` : "";
          return `<div class="hr-line"><strong>${escapeHtml(holder.name)}</strong> · ${shares(holder.shares)} shares · ${money(holder.value_usd)}${weight}${change}${when}${filed}${secLink(holder.source_url)}</div>`;
        });
        const extra = payload.holders.length > 25 ? `<div class="tier-sub">${payload.holders.length - 25} more holders in the file.</div>` : "";
        slot.innerHTML = `<p class="tier-sub">${payload.context || ""}</p>${lines.join("")}${extra}`;
      })
      .catch(() => {
        if (root.dataset.ticker === ticker) slot.textContent = "13F holders could not be loaded.";
      });
  }

  function renderManagersPage() {
    return (window.WorkspaceTools ? WorkspaceTools.investorNav(true) : '<h2>Investors</h2>') + '<div id="managers-page" aria-live="polite">Loading the investor directory.</div>';
  }

  async function fillManagersPage() {
    if (window.InvestorHistory) return window.InvestorHistory.fill();
    const root=document.getElementById('managers-page'); if(!root)return;
    try {
      const response=await fetch(dataUrl('data/holdings/managers_index.json'));
      if(!response.ok)throw new Error('Directory unavailable');
      const index=await response.json(); if(!root.isConnected)return;
      const managers=index.managers || [], quarters=[...new Set(managers.map(r=>r.quarter).filter(Boolean))].sort().reverse();
      const coverage=Object.fromEntries(quarters.map(q=>[q,managers.filter(r=>r.quarter===q).length]));
      const broadest=quarters.slice().sort((a,b)=>coverage[b]-coverage[a])[0] || '';
      let query='',quarter=broadest,overlap=true,page=0,request=0;
      root.innerHTML=`<p class="investor-context">Quarter-end US holdings from 13F filings. Filings arrive after the holdings date; positions do not reveal current exposure or trade intent.</p>
        <div class="workspace-filter"><label class="workspace-search">Find an investor<input type="search" data-manager-search placeholder="Manager name"></label>
        <label>Holdings quarter<select data-manager-quarter>${quarters.map(q=>`<option value="${escapeHtml(q)}"${q===quarter?' selected':''}>${escapeHtml(q)} · ${coverage[q]} filed</option>`).join('')}</select></label>
        <label><span>Portfolio relevance</span><select data-manager-overlap><option value="book">Overlaps our book</option><option value="all">All investors</option></select></label></div>
        <div class="investor-directory"><div><p data-manager-count class="investor-context"></p><div class="workspace-scroll" data-manager-list></div><div class="workspace-filter"><button type="button" data-manager-prev>Previous</button><span data-manager-page></span><button type="button" data-manager-next>Next</button></div></div>
        <aside class="investor-detail" data-manager-detail tabindex="-1" aria-label="Investor details"><h3>Select an investor</h3><p>Holdings and changes appear here with their reporting quarter.</p></aside></div>`;
      const list=root.querySelector('[data-manager-list]'),detail=root.querySelector('[data-manager-detail]');
      async function selectManager(id) {
        const ticket=++request;detail.innerHTML='<p>Loading filing details.</p>';
        try {
          const response=await fetch(dataUrl(`data/holdings/by_manager/${encodeURIComponent(id)}.json`));
          if(!response.ok)throw new Error('No verified filing page is available.');
          const d=await response.json();if(ticket!==request || !root.isConnected)return;
          const positions=(d.positions || []).slice().sort((a,b)=>(b.weight_pct || 0)-(a.weight_pct || 0));
          detail.innerHTML=`<h3>${escapeHtml(d.name)}</h3><p>Holdings: ${escapeHtml(d.period_end || d.quarter || 'undated')}<br>Filed: ${escapeHtml(d.filed_at || d.filing_date || 'See SEC filing history')}</p>
            <p><a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${encodeURIComponent(d.cik || '')}&type=13F-HR" target="_blank" rel="noopener">SEC filing history</a></p>
            <div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Position</th><th>Weight</th><th>Value</th></tr></thead><tbody>${positions.map(r=>`<tr><td>${escapeHtml(r.ssi_ticker || r.ticker || r.issuer)}<small>${escapeHtml(r.issuer)}</small></td><td>${r.weight_pct==null?'—':Number(r.weight_pct).toFixed(1)+'%'}</td><td>${money(r.value_usd)}</td></tr>`).join('')}</tbody></table></div>
            <details class="workspace-fold"><summary>Changes in our book · ${(d.ssi_changes || []).length}</summary>${(d.ssi_changes || []).map(r=>`<p>${escapeHtml(r.change_type)} ${escapeHtml(r.ticker)}</p>`).join('') || '<p>No changes recorded.</p>'}</details>
            ${d.watchlist ? `<details class="workspace-fold"><summary>All reported changes · ${(d.changes || []).length}</summary>${(d.changes || []).map(r=>`<p>${escapeHtml(r.change_type)} ${escapeHtml(r.ticker || r.issuer || r.cusip || "position")}${r.shares_delta_pct==null?'':` ${Number(r.shares_delta_pct).toFixed(1)}%`}</p>`).join('') || '<p>No changes at the reporting threshold.</p>'}</details>` : ''}`;
          detail.focus({preventScroll:true});if(window.innerWidth<900)detail.scrollIntoView({block:'start'});
        } catch(e) { if(ticket===request && root.isConnected)detail.textContent=e.message; }
      }
      function paint() {
        const rows=managers.filter(r=>(!quarter || r.quarter===quarter) && (!overlap || r.ssi_overlap>0) && r.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>(b.ssi_overlap || 0)-(a.ssi_overlap || 0) || a.name.localeCompare(b.name));
        page=Math.max(0,Math.min(page,Math.ceil(rows.length/25)-1));
        root.querySelector('[data-manager-count]').textContent=`${rows.length} investors · sorted by portfolio overlap`;
        list.innerHTML=`<table class="workspace-table"><thead><tr><th>Investor</th><th>In our book</th><th>Positions</th><th>Holdings date</th></tr></thead><tbody>${rows.slice(page*25,(page+1)*25).map(r=>`<tr><td><button type="button" data-manager="${escapeHtml(r.manager_id)}">${escapeHtml(r.name)}</button><small>${escapeHtml(r.top_ticker || r.top_issuer || '')}${r.top_weight_pct==null?'':' · '+Number(r.top_weight_pct).toFixed(1)+'% top position'}</small></td><td>${r.ssi_overlap || 0}</td><td>${r.positions || 0}</td><td>${escapeHtml(r.period_end || r.quarter)}</td></tr>`).join('')}</tbody></table>${rows.length?'':'<div class="workspace-empty">No investors match these filters.</div>'}`;
        root.querySelector('[data-manager-page]').textContent=`Page ${page+1} of ${Math.max(1,Math.ceil(rows.length/25))}`;
        root.querySelector('[data-manager-prev]').disabled=page===0;root.querySelector('[data-manager-next]').disabled=(page+1)*25>=rows.length;
        list.querySelectorAll('[data-manager]').forEach(button=>button.addEventListener('click',()=>selectManager(button.dataset.manager)));
      }
      root.querySelector('[data-manager-search]').addEventListener('input',e=>{query=e.target.value;page=0;paint();});
      root.querySelector('[data-manager-quarter]').addEventListener('change',e=>{quarter=e.target.value;page=0;paint();});
      root.querySelector('[data-manager-overlap]').addEventListener('change',e=>{overlap=e.target.value==='book';page=0;paint();});
      root.querySelector('[data-manager-prev]').addEventListener('click',()=>{page--;paint();});root.querySelector('[data-manager-next]').addEventListener('click',()=>{page++;paint();});paint();
    } catch(e) { if(root.isConnected)root.textContent='Investor filings could not be loaded. '+e.message; }
  }

  ensureSummary();
  window.FundHoldings = { renderTicker, fillTicker, badgeHtml, ensureSummary, renderManagersPage, fillManagersPage };
})();
