/* Shared investor navigation and one source-status registry. */
(function (global) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url = v => /^(https?:\/\/|#\/)/.test(String(v || '')) ? v : '#/insights/overview';
  function investorNav(directory) {
    return `<header class="workspace-heading"><div><span class="workspace-eyebrow">Investor intelligence</span><h2>Investors</h2><p>Research signals and dated institutional holdings, in one workspace.</p></div><nav class="workspace-pills" aria-label="Investors"><a ${!directory?'aria-current="page"':''} href="#/insights/investors/signals">Signals</a><a ${directory?'aria-current="page"':''} href="#/insights/investors/directory">Directory</a></nav></header>`;
  }
  function sourceRows(status, health = {}, now = Date.now()) {
    const rows = new Map();
    for (const row of status?.surfaces || []) {
      const current=global.DashboardDisplay?.sourceRow(row.id) || row;
      let state = row.status || 'unknown';
      const stamp = Date.parse(row.stamp || '');
      if (row.exists === false) state = 'missing';
      else if (row.kind === 'api' && !row.stamp && ['api','fresh'].includes(state)) state = 'api';
      else if (Number.isFinite(stamp) && now-stamp > (row.max_age_hours || 48)*3600000) state = 'stale';
      else if (state === 'fresh' || state === 'empty') state = 'current';
      if (global.DashboardDisplay) {
        state=global.DashboardDisplay.stateFor(current,now);
        if(state==='fresh')state='current';
      }
      rows.set(row.id, {...current, state, date:current.stamp || null, details:[]});
    }
    for (const [key, value] of Object.entries(health || {})) {
      const id = key.replace(/_/g,'-');
      const match = rows.get(id) || [...rows.values()].find(r=>r.artifact && value.path && r.artifact === value.path);
      if (match) match.details.push(value);
      else rows.set(id,{id,label:key.replace(/_/g,' '),state:value.status==='ok'?'current':value.status || 'unknown',date:value.as_of || null,next_action:value.notes || 'Review the source publication.',details:[value]});
    }
    const rank = s => ['missing','unreadable','stale','degraded','failed','unknown'].includes(s)?0:1;
    return [...rows.values()].sort((a,b)=>rank(a.state)-rank(b.state) || String(a.label).localeCompare(String(b.label)));
  }
  function actionFor(row){
    if(row.coverage?.next_action && row.coverage.incomplete_rows>0)return row.coverage.next_action;
    if(['api','live'].includes(row.state))return 'Open the workspace to check observation dates.';
    if(['missing','unavailable'].includes(row.state))return 'Restore or connect this source.';
    if(['degraded','failed','unreadable'].includes(row.state))return 'Review source exceptions and the next scheduled refresh.';
    if(['stale','lagging'].includes(row.state))return 'Await refreshed source observations.';
    return 'No action required.';
  }
  function renderStatus(status, health) {
    const rows=sourceRows(status,health), bad=rows.filter(r=>!['current','fresh','empty','live','api','ok'].includes(r.state));
    const covered=rows.filter(r=>r.coverage), gaps=covered.filter(r=>r.coverage.incomplete_rows>0);
    const fmt=global.DashboardFormat;
    const date=value=>value?(fmt?.timestamp?fmt.timestamp(value):value):'Observation date unavailable';
    const coverage=r=>!r.coverage?'Not measured':`${r.coverage.complete_rows} / ${r.coverage.total_rows}${r.coverage.coverage_pct==null?'':` · ${r.coverage.coverage_pct}%`}<small>${esc(r.coverage.kind.replaceAll('_',' '))}</small><details><summary>Required evidence</summary><p>${esc(r.coverage.definition)}</p>${Object.entries(r.coverage.missing_by_field||{}).map(([k,n])=>`<p>${esc(k.replaceAll('_',' '))}: ${n} missing</p>`).join('')}<p>Field coverage is separate from investment approval.</p>${r.coverage.backlog?.length?`<details><summary>Issuer repair queue (${r.coverage.backlog.length})</summary>${r.coverage.backlog.map(b=>`<p><strong>${esc(b.entity)}</strong> · ${esc(b.missing.join(", ").replaceAll("_"," "))}<br>${esc(typeof b.reason==="string"?b.reason:JSON.stringify(b.reason))}${b.checked_at?`<br>Checked ${esc(date(b.checked_at))}`:""}</p>`).join("")}</details>`:""}</details>`;
    const table=list=>`<div class="workspace-scroll"><table class="workspace-table"><thead><tr><th scope="col">Source</th><th scope="col">Freshness</th><th scope="col">Source date</th><th scope="col">Evidence coverage</th><th scope="col">Next action</th></tr></thead><tbody>${list.map(r=>`<tr><th scope="row"><a href="${esc(url(r.hash))}">${esc(r.label || r.id)}</a><details><summary>Source details</summary><p>${esc(r.artifact || r.api || r.id)}</p><p>Owner: ${esc(r.lane || 'source publisher')}</p><p>Last successful receipt: ${esc(r.lane_receipt_at || 'unavailable')}</p><p>${esc(r.next_action || '')}</p>${r.details.map(d=>`<p>${esc(d.notes || d.path || '')}</p>`).join('')}</details></th><td><span class="display-state" data-state="${esc(r.state)}">${esc(r.state==='current'?'Current':fmt?.feedLabel(r.state)||r.state)}</span></td><td>${esc(date(r.date))}</td><td class="${r.coverage?.incomplete_rows?'coverage-missing':''}">${coverage(r)}</td><td>${esc(actionFor(r))}</td></tr>`).join('')}</tbody></table></div>`;
    const registry=global.DashboardDisplay?.registry();
    const inventory=registry?`<details class="workspace-fold"><summary>Workspace coverage · ${registry.cases.length} routes and variants</summary><div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Workspace</th><th>View</th><th>Source owners</th></tr></thead><tbody>${registry.views.map(v=>`<tr><th scope="row"><a href="${esc(v.path)}">${esc(v.title)}</a></th><td>${esc(v.purpose)}</td><td>${esc(v.sources.join(', '))}</td></tr>`).join('')}</tbody></table></div></details>`:'';
    return `<section class="data-status"><header class="workspace-heading"><div><span class="workspace-eyebrow">Dashboard sources</span><h2>Data status</h2><p>Observation dates, evidence completeness and processing receipts describe different things.</p></div><a href="#/insights/overview">Back to insights</a></header><div class="coverage-summary"><div><strong>${rows.length}</strong><span>Registered sources</span></div><div><strong>${bad.length}</strong><span>Source dates or availability need review</span></div><div><strong>${gaps.length}</strong><span>Sources with measured evidence gaps</span></div></div>${rows.length?`${bad.length?table(bad):'<div class="workspace-empty">No published source exceptions.</div>'}<details class="workspace-fold"${bad.length?'':' open'}><summary>All sources · ${rows.length}</summary>${table(rows)}</details>${gaps.length?`<details class="workspace-fold" open><summary>Evidence completion backlog · ${gaps.length} sources</summary><p class="coverage-method">Counts use each source’s declared universe and required fields. Unsupported instruments, missing facts and unpublished research must remain distinguishable.</p>${table(gaps)}</details>`:''}${inventory}`:'<div class="workspace-empty">Source status has not been published.</div>'}</section>`;
  }
  function mountStatus(host, status, health) { host.innerHTML=renderStatus(status,health); }
  global.WorkspaceTools={investorNav,sourceRows,renderStatus,mountStatus};
})(window);
