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
      let state = row.status || 'unknown';
      const stamp = Date.parse(row.stamp || '');
      if (row.exists === false) state = 'missing';
      else if (row.kind === 'api' && !row.stamp && ['api','fresh'].includes(state)) state = 'api';
      else if (Number.isFinite(stamp) && now-stamp > (row.max_age_hours || 48)*3600000) state = 'stale';
      else if (state === 'fresh' || state === 'empty') state = 'current';
      rows.set(row.id, {...row, state, date:row.stamp || null, details:[]});
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
    if(['api','live'].includes(row.state))return 'Open the workspace to check observation dates.';
    if(['missing','unavailable'].includes(row.state))return 'Restore or connect this source.';
    if(['degraded','failed','unreadable'].includes(row.state))return 'Review source exceptions and the next scheduled refresh.';
    if(['stale','lagging'].includes(row.state))return 'Await refreshed source observations.';
    return 'No action required.';
  }
  function coverageMarkup(row){
    const c=row.coverage;
    const fields=c?Object.entries(c.missing_by_field||{}).filter(([,n])=>n>0).map(([key,n])=>`${esc(key.replace(/_/g,' '))}: ${esc(n)}`).join(' · '):'';
    const dates=Object.entries(row.observation_dates||{}).filter(([,d])=>d).map(([key,d])=>`${esc(key)}: ${esc(d)}`).join(' · ');
    return `${c?`<p>${esc(c.complete_rows)} of ${esc(c.total_rows)} rows complete${c.coverage_pct==null?'':` (${esc(c.coverage_pct)}%)`}.</p>${fields?`<p>Missing or pending: ${fields}</p>`:''}`:''}${dates?`<p>Source observations · ${dates}</p>`:''}`;
  }
  function renderStatus(status, health) {
    const rows=sourceRows(status,health), bad=rows.filter(r=>!['current','fresh','empty','live','api','ok'].includes(r.state));
    const table=list=>`<div class="workspace-scroll"><table class="workspace-table"><thead><tr><th>Source</th><th>Status</th><th>Observation / artifact date</th><th>Next action</th></tr></thead><tbody>${list.map(r=>`<tr><td><a href="${esc(url(r.hash))}">${esc(r.label || r.id)}</a><details><summary>Source details</summary><p>${esc(r.artifact || r.api || r.id)}</p><p>Owner: ${esc(r.lane || 'source publisher')}</p><p>Last receipt: ${esc(r.lane_receipt_at || 'unavailable')}</p>${coverageMarkup(r)}<p>${esc(r.next_action || '')}</p>${r.details.map(d=>`<p>${esc(d.notes || d.path || '')}</p>`).join('')}</details></td><td><span class="workspace-state ${['stale','failed','missing','degraded','unreadable','lagging','unavailable','unknown'].includes(r.state)?'is-warning':''}">${esc(r.label_text || r.state)}</span></td><td>${esc(r.date || (r.kind==='api'?'Check within the workspace':'Not published'))}</td><td>${esc(actionFor(r))}</td></tr>`).join('')}</tbody></table></div>`;
    return `<section class="data-status"><header class="workspace-heading"><div><span class="workspace-eyebrow">Dashboard sources</span><h2>Data status</h2><p>${bad.length} source${bad.length===1?'':'s'} need attention. Observation dates and build receipts describe different things.</p></div><a href="#/insights/overview">Back to insights</a></header>${rows.length?`${bad.length?table(bad):'<div class="workspace-empty">No published source exceptions.</div>'}<details class="workspace-fold"><summary>All sources · ${rows.length}</summary>${table(rows)}</details>`:'<div class="workspace-empty">Source status has not been published.</div>'}</section>`;
  }
  function mountStatus(host, status, health) { host.innerHTML=renderStatus(status,health); }
  global.WorkspaceTools={investorNav,sourceRows,renderStatus,mountStatus};
})(window);
