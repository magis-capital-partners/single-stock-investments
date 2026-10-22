/* One buyback record, evidence view, and snapshot across Coverage, Events, and Shorts. */
(function (global) {
  'use strict';
  var state = { promise: null, snapshot: null, byTicker: {}, error: '', details: new Map() };
  var FILTER_KEY = 'ssi-buyback-coverage-v2', DISPOSITION_KEY = 'ssi-buyback-dispositions-v2';
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function(c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function num(v) { return typeof v === 'number' && Number.isFinite(v); }
  function pct(v) { return num(v) ? v.toFixed(1) + '%' : '—'; }
  function cash(v) { return num(v) ? new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:1}).format(v) : '—'; }
  function label(s) { return String(s || 'unavailable').replace(/_/g, ' '); }
  function safeUrl(url) { return /^https?:\/\//i.test(String(url || '')) ? String(url) : ''; }
  function read(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (_) { return fallback; } }
  function write(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch (_) { return false; } }
  function coverageState() { return read(FILTER_KEY, {filter:'all',sort:'net_reduction_1y'}); }
  function snapshotExpired() {
    var m=state.snapshot && state.snapshot.manifest;if(!m)return false;
    var stamp=Date.parse(m.generated_at || (m.as_of ? m.as_of+'T00:00:00Z' : ''));
    return !Number.isFinite(stamp) || Date.now()-stamp>102*3600000;
  }
  function metric(b, key) {
    var m = b && b.metrics && b.metrics[key];
    return b && b.data_status === 'verified' && !snapshotExpired() && !['fetch_failed','failed'].includes(b.refresh_status) && m && ['verified','derived'].includes(m.status) && num(m.value) ? m : {value:null,reason:(m && m.reason) || (b && b.data_reason)};
  }
  function sourceLink(s, title) {
    var url = safeUrl(typeof s === 'string' ? s : s && s.url);
    return url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(title || 'Source') + '</a>' : '';
  }
  function tickerLink(ticker, text) { return '<a href="#/research/coverage/' + encodeURIComponent(ticker) + '?section=buyback">' + esc(text || ticker) + '</a>'; }
  function status(b) {
    var value = snapshotExpired() ? 'snapshot_overdue' : b && ['fetch_failed','failed'].includes(b.refresh_status) ? 'refresh_failed' : b && b.data_status || 'unavailable';
    return '<span class="bb-status bb-status-' + esc(value) + '" title="' + esc(label(b && b.data_reason)) + '">' + esc(label(value)) + '</span>';
  }
  async function json(path) {
    var r = await fetch('data/' + path, {cache: path.includes('buyback_snapshots/') ? 'default' : 'no-store'});
    if (!r.ok) throw new Error('Buyback data unavailable (' + r.status + ')');
    return r.json();
  }
  async function load(force, retry) {
    if (force) { state.promise = null; state.snapshot = null; state.details.clear(); }
    if (!state.promise) state.promise = (async function() {
      try {
        var manifest = await json('buyback_manifest.json');
        if (manifest.schema_version !== 'buyback_manifest.v2') throw new Error('Verified buyback snapshot has not been published');
        var paths = ['companies','events','summary'];
        paths.forEach(function(k) { if (!/^buyback_snapshots\/[a-f0-9]{20}\/[a-z]+\.json$/.test(manifest[k] || '')) throw new Error('Invalid buyback snapshot path'); });
        var docs = await Promise.all(paths.map(function(k) { return json(manifest[k]); }));
        if (docs.some(function(d) { return d.snapshot_id !== manifest.snapshot_id; })) throw new Error('Buyback snapshots are out of sync. Reload data.');
        state.snapshot = {manifest:manifest,companies:docs[0],events:docs[1],summary:docs[2]};
        state.byTicker = {};
        (docs[0].companies || []).forEach(function(r) { [r.ticker].concat(r.aliases || []).forEach(function(t) { state.byTicker[String(t).toUpperCase()] = r; }); });
        state.error = snapshotExpired() ? 'Buyback snapshot is overdue. Current rankings are withheld; historical evidence remains available.' : '';
      } catch (e) {
        if(!retry && /out of sync/.test(e.message))return load(true,true);
        state.snapshot = null; state.byTicker = {}; state.error = e.message;
      }
      return state.snapshot;
    })();
    return state.promise;
  }
  function company(ticker) { return state.byTicker[String(ticker || '').toUpperCase()] || null; }
  function currentEvents() { return state.snapshot ? (state.snapshot.events.events || []).map(function(e){return snapshotExpired() && e.book==='ranked' ? Object.assign({},e,{book:'discovery',status:'needs_review',review_reason:'snapshot_overdue'}) : e;}) : []; }
  function eventsFor(ticker) {
    var row = company(ticker);
    return state.snapshot ? currentEvents().filter(function(e) { return row ? e.issuer_id === row.issuer_id : e.ticker === ticker; }) : [];
  }
  function renderHoldingsCell(row) {
    var b = row && row.buyback;
    if (!b || b.schema_version !== 'buyback.v2') return '<td class="buyback-cell"><span class="bb-muted">Awaiting verified data</span></td>';
    var net = metric(b,'net_reduction_1y'), gross = metric(b,'gross_cash_ratio');
    var headline = net.value === null ? label(b.data_reason || net.reason) : pct(net.value) + ' net reduced · 1Y';
    return '<td class="buyback-cell">' + status(b) + '<strong>' + esc(headline) + '</strong><small>' +
      esc(label(b.pace || 'pace unavailable')) + ' · ' + esc(pct(gross.value)) + ' cash ' + esc(gross.period_label || b.yield_period || '') +
      '</small><small>Shares ' + esc(b.shares_end || 'unavailable') + '</small></td>';
  }
  function chart(rows, title) {
    rows = (rows || []).filter(function(r) { return r.end && num(r.value); });
    if (title.indexOf('Weighted')===0) { var byEnd={};rows.forEach(function(r){var n=(Date.parse(r.end)-Date.parse(r.start))/86400000;var old=byEnd[r.end];if(!old || n<(Date.parse(old.end)-Date.parse(old.start))/86400000)byEnd[r.end]=r;});rows=Object.values(byEnd).sort(function(a,b){return a.end.localeCompare(b.end);}); }
    if (!rows.length) return '<p class="bb-muted">' + esc(title) + ': observations unavailable.</p>';
    var values = rows.map(function(r) { return r.value; }), lo = Math.min.apply(null,values), hi = Math.max.apply(null,values), span = hi-lo || Math.abs(hi)*.1 || 1;
    var first = Date.parse(rows[0].end), last = Date.parse(rows[rows.length-1].end), path = '', connected = false;
    rows.forEach(function(r) {
      if (r.status !== 'verified') { connected = false; return; }
      var x = 12 + (Date.parse(r.end)-first)/(last-first || 1)*336, y = 110-(r.value-lo)/span*92;
      path += (connected ? ' L' : ' M') + x.toFixed(1) + ' ' + y.toFixed(1); connected = true;
    });
    var table = rows.map(function(r) { return '<tr><td>' + esc(r.end) + '</td><td>' + esc(Math.round(r.value).toLocaleString('en-US')) + '</td><td>' + esc(label(r.status)) + '</td><td>' + sourceLink(r,r.filed || 'Filing') + '</td></tr>'; }).join('');
    return '<figure class="bb-chart"><figcaption>' + esc(title) + '</figcaption><svg viewBox="0 0 360 130" role="img" aria-label="' + esc(title + ', ' + rows[0].end + ' to ' + rows[rows.length-1].end) + '"><title>' + esc(title) + '</title><path d="' + path + '" fill="none" stroke="currentColor" stroke-width="2"/></svg><small>' + esc(rows[0].end) + ' — ' + esc(rows[rows.length-1].end) + '</small><details><summary>Observations and sources</summary><div class="bb-scroll"><table><thead><tr><th>Date</th><th>Shares</th><th>Status</th><th>Evidence</th></tr></thead><tbody>' + table + '</tbody></table></div></details></figure>';
  }
  function evidence(sources) {
    var seen = new Set(), rows = [];
    (sources || []).forEach(function(s) {
      var key = [s.url,s.accn,s.tag,s.start,s.end].join('|');
      if (seen.has(key)) return; seen.add(key);
      rows.push('<li>' + sourceLink(s,s.accn || 'Filing') + ' · ' + esc(s.start || s.end || '') + (s.start ? ' to ' + esc(s.end || '') : '') + ' · filed ' + esc(s.filed || 'unknown') +
        '<details><summary>Calculation input</summary><code>' + esc(s.tag || s.scope || '') + '</code></details></li>');
    });
    return rows.length ? '<details class="bb-evidence"><summary>Evidence and calculation inputs</summary><ul>' + rows.join('') + '</ul></details>' : '<p class="bb-muted">Source evidence requires review.</p>';
  }
  function assessment(b) {
    var components = b.assessment && b.assessment.components || {};
    return '<p class="bb-muted">Assessment period: '+esc(b.assessment_period?.start || 'unavailable')+' to '+esc(b.assessment_period?.end || 'unavailable')+'</p><div class="bb-grid">' + ['execution','funding','valuation'].map(function(k) {
      var p = components[k] || {};
      return '<div class="bb-assessment"><strong>' + esc(label(k)) + '</strong><span>' + (num(p.score) ? esc(p.score + ' / 2') : 'Unrated') + '</span><small>' +
        esc(p.reason ? label(p.reason) : num(p.retention) ? pct(p.retention*100) + ' retirement efficiency' : num(p.coverage) ? p.coverage.toFixed(2) + '× cash coverage' : num(p.price_to_value) ? p.price_to_value.toFixed(2) + '× dated value' : '') + '</small></div>';
    }).join('') + '</div>';
  }

  function shareBridge(b) {
    if (!b) return '<p class="bb-muted">Matching share bridge unavailable.</p>';
    var rows=[['Beginning outstanding',b.beginning],['Gross repurchased',b.gross_repurchased],['Unexplained net additions / adjustments',b.unexplained_net_additions],['Ending outstanding',b.ending]];
    return '<h4>Share bridge / '+esc((b.start || '?')+' to '+(b.end || '?'))+'</h4><table><tbody>'+rows.map(function(r){return '<tr><th>'+esc(r[0])+'</th><td>'+esc(num(r[1]) ? r[1].toLocaleString('en-US') : 'Unavailable')+'</td></tr>';}).join('')+'</tbody></table><p class="bb-muted">'+esc(b.reason)+'</p>';
  }
  function actionTable(actions) {
    return (actions || []).length ? '<h4>Corporate actions</h4><ul>'+actions.map(function(a){return '<li>'+esc(a.effective)+' / '+esc(label(a.type))+' / ratio '+esc(a.ratio)+' / '+sourceLink(a.source)+'</li>';}).join('')+'</ul>' : '';
  }
  function tenderScenario(v) {
    if (![v.purchase,v.offer,v.unaccepted,v.fees,v.days,v.acceptance].every(num) || v.purchase<=0 || v.offer<0 || v.unaccepted<0 || v.fees<0 || v.days<=0 || v.acceptance<0 || v.acceptance>1) return null;
    var proceeds=v.acceptance*v.offer+(1-v.acceptance)*v.unaccepted-v.fees;
    return {proceeds:proceeds,gain:proceeds-v.purchase,return_pct:100*(proceeds/v.purchase-1)};
  }
  function epsScenario(v) {
    if (![v.shares,v.earnings,v.retire,v.issue,v.earnings_change].every(num) || v.shares<=0 || v.retire<0 || v.issue<0 || v.shares-v.retire+v.issue<=0 || v.earnings===0 || v.earnings_change<=-100) return null;
    var before=v.earnings/v.shares,after=v.earnings*(1+v.earnings_change/100)/(v.shares-v.retire+v.issue);
    return {before:before,after:after,change_pct:100*(after/before-1)};
  }
  function scenarioForm(e) {
    if (e.event_type!=='issuer_tender') return '';
    var fields=[['purchase','Purchase price',''],['offer','Tender price',e.price_low],['acceptance','Accepted fraction (0-1)',''],['unaccepted','Unaccepted share value',''],['fees','Fees per purchased share',''],['days','Settlement days','']];
    return '<details class="bb-scenario"><summary>Tender payoff assumptions</summary><form data-bb-scenario="tender"><p>Acceptance, unaccepted-share value, fees and timing are assumptions. Odd-lot status does not guarantee acceptance.</p><div class="bb-grid">'+fields.map(function(f){return '<label>'+f[1]+'<input name="'+f[0]+'" type="number" step="any" required value="'+esc(f[2] == null ? '' : f[2])+'"></label>';}).join('')+'</div><button type="submit">Calculate scenario</button><output aria-live="polite"></output></form></details>';
  }
  function epsForm() {
    return '<details class="bb-scenario"><summary>Mechanical EPS scenario</summary><form data-bb-scenario="eps"><p>This illustration holds earnings assumptions explicit. It is not a return forecast and is not added to the dashboard IRR.</p><div class="bb-grid">'+[['shares','Beginning shares'],['earnings','Beginning earnings'],['retire','Shares repurchased'],['issue','Shares issued'],['earnings_change','Earnings change (%)']].map(function(f){return '<label>'+f[1]+'<input name="'+f[0]+'" type="number" step="any" required></label>';}).join('')+'</div><button type="submit">Calculate EPS</button><output aria-live="polite"></output></form></details>';
  }
  function attachScenarios(container) {
    container.querySelectorAll('[data-bb-scenario]').forEach(function(form){
      if(form.dataset.attached)return;form.dataset.attached='true';
      form.addEventListener('submit',function(event){event.preventDefault();var v={};form.querySelectorAll('input').forEach(function(i){v[i.name]=i.value==='' ? NaN : Number(i.value);});
        var r=form.dataset.bbScenario==='tender' ? tenderScenario(v) : epsScenario(v);
        form.querySelector('output').textContent=!r ? 'Enter valid assumptions.' : form.dataset.bbScenario==='tender' ? 'Scenario gain per share: '+cash(r.gain)+'; holding-period return '+pct(r.return_pct)+' over '+v.days+' assumed days. No annualized return is implied.' : 'EPS '+r.before.toFixed(3)+' to '+r.after.toFixed(3)+'; change '+pct(r.change_pct)+'.';
      });
    });
  }

  function renderEventDetails(e) {
    var rows = [['Status',label(e.status)],['Amount',cash(e.usd)],['Timing',e.ends_label || e.date_label || 'Requires review'],
      ['Terms verified',e.terms_verified ? 'Yes' : 'Review required'],['Last checked',e.last_verified || 'Unverified'],['Announcement',e.announced || 'Unverified']];
    if (e.event_type === 'issuer_tender') rows.push(['Price / range',num(e.price_low) ? cash(e.price_low) + (e.price_high !== e.price_low ? '–' + cash(e.price_high) : '') : 'Unverified'],['Odd-lot priority',e.odd_lot === true ? 'Verified in offer terms' : e.odd_lot === false ? 'No priority' : 'Unverified']);
    if (num(e.remaining_authorization_usd)) rows.push(['Remaining authorization',cash(e.remaining_authorization_usd) + ' reported ' + (e.remaining_as_of || 'date unavailable')]);
    Object.entries(e.terms || {}).forEach(function(p) { rows.push([label(p[0]),p[1] || 'Unverified']); });
    var corrections = (e.corrections || []).map(function(c) { return '<p class="bb-notice">Correction: ' + esc(c.reason || 'Terms reconciled to source') + ' · ' + sourceLink(c.source) + '</p>'; }).join('');
    return '<div class="bb-event-terms"><dl>' + rows.map(function(r) { return '<div><dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd></div>'; }).join('') + '</dl>' + corrections +
      '<p>' + esc(e.next || 'Verify the next disclosure.') + '</p>' + sourceLink(e.url,'Primary filing') + (e.evidence_excerpt ? '<details><summary>Term evidence</summary><p>' + esc(e.evidence_excerpt) + '</p></details>' : '') + scenarioForm(e) + '</div>';
  }
  function renderDetail(row) {
    var b = row && row.buyback;
    if (!b || b.schema_version !== 'buyback.v2') return '<section class="detail-section bb-panel"><h3>Buyback</h3><p>' + esc(state.error || 'Awaiting a verified snapshot.') + '</p></section>';
    var metrics = [['Net reduction · 1Y','net_reduction_1y'],['Net reduction · 3Y','net_reduction_3y'],['Net reduction · 5Y','net_reduction_5y'],['Gross repurchase cash ratio','gross_cash_ratio'],['Net cash repurchase ratio','net_cash_ratio'],['Shares down from observed peak','since_peak'],['Net retirement efficiency','retirement_efficiency'],['Remaining authorization / market value','remaining_authorization_ratio']];
    var cards = metrics.map(function(r) { var m = metric(b,r[1]); return '<div class="bb-stat"><span>' + esc(r[0]) + '</span><strong>' + esc(pct(m.value)) + '</strong><small>' +
      esc(m.start && m.end ? m.start + ' → ' + m.end : label(m.reason || b.data_reason)) +(num(m.annualized_pct) ? ' / '+pct(m.annualized_pct)+' annualized' : '')+ '</small>'+evidence(m.sources)+'</div>'; }).join('');
    var events = eventsFor(row.ticker);
    var out = '<details class="detail-section bb-panel" data-buyback-detail="' + esc(b.issuer_id) + '" data-bb-ticker="' + esc(row.ticker) + '" open><summary>Buyback · ' + esc((snapshotExpired() ? 'snapshot overdue' : label(b.data_status))) + ' · shares ' + esc(b.shares_end || 'unavailable') + '</summary>' +
      '<div class="bb-heading">' + status(b) + '<span>Confidence: ' + esc(label(b.confidence)) + '</span><a href="#/ideas/situations/buyback-events/' + encodeURIComponent(row.ticker) + '">Buyback events</a><a href="#/ideas/short-alpha?buyback=' + encodeURIComponent(row.ticker) + '">Issuance research</a></div>' +
      (state.error ? '<p class="bb-notice">'+esc(state.error)+'</p>' : '') +
      (b.price_warning ? '<p class="bb-notice">Quote date: '+esc(b.price_as_of)+'. '+esc(label(b.price_warning))+'.</p>' : '') +
      (b.refresh_reason ? '<p class="bb-notice">'+esc(b.refresh_reason)+'</p>' : '') +
      (b.explanation ? '<p>' + esc(b.explanation) + ' ' + sourceLink(b.explanation_source) + '</p>' : '') +
      (b.last_change ? '<p class="bb-notice">' + esc(label(b.last_change.kind)) + ' · ' + esc(b.last_change.reason || '') + '</p>' : '') +
      '<div class="bb-grid bb-metrics">' + cards + '</div><p class="bb-muted">Positive net reduction means fewer shares. Cash repurchase ratios describe the stated FY or TTM period; they are not investment returns.</p>' + assessment(b) + epsForm() + researchNote(b) +
      '<div data-bb-history="' + esc(b.issuer_id) + '" aria-live="polite">Loading share history…</div>' +
      (events.length ? '<details><summary>Programs and events · ' + events.length + '</summary>' + events.map(function(e) { return '<article class="bb-event"><h4>' + esc(e.what) + '</h4>' + renderEventDetails(e) + '</article>'; }).join('') + '</details>' : '<p class="bb-muted">No verified event or review item in this snapshot.</p>') + evidence(b.sources) + '</details>';
    if (typeof queueMicrotask === 'function') queueMicrotask(hydrateAll);
    return out;
  }
  async function hydrateAll() {
    if (typeof document === 'undefined') return;
    attachScenarios(document);
    attachOutcomes(document);
    for (var host of document.querySelectorAll('[data-bb-history]')) {
      if (host.dataset.loaded) continue;
      var ticker = host.closest('[data-bb-ticker]').dataset.bbTicker, b = company(ticker);
      host.dataset.loaded = 'true';
      if (!b || !b.detail_ref) { host.textContent = 'Normalized history is unavailable. ' + label(b && b.data_reason); continue; }
      try {
        if (!/^buyback_snapshots\/[a-f0-9]{20}\/details\/[A-Za-z0-9_-]+\.json$/.test(b.detail_ref)) throw new Error('Invalid history reference');
        if (!state.details.has(b.detail_ref)) state.details.set(b.detail_ref,json(b.detail_ref));
        var d = await state.details.get(b.detail_ref);
        if (d.snapshot_id !== b.snapshot_id || d.issuer_id !== b.issuer_id) throw new Error('History does not match the selected snapshot');
        if (!host.isConnected) continue;
        host.innerHTML = '<div class="bb-grid">' + chart(d.series && d.series.actual,'Actual outstanding shares') + chart(d.series && d.series.diluted,'Weighted diluted shares') + '</div>' +
          '<p class="bb-muted">Actual ownership and weighted EPS counts use separate bases. Gaps indicate observations requiring review.</p>' +
          '<details><summary>Cash flows and share bridge evidence</summary>' + flowTable(d) + reportedPeriods(d) + '</details>';
      } catch(e) { state.details.delete(b.detail_ref); host.textContent = 'History unavailable: ' + e.message; }
      if (/[?&]section=buyback(?:&|$)/.test(location.hash)) { host.closest('details').open = true; host.closest('details').scrollIntoView({block:'start'}); }
    }
  }
  function reportedPeriods(d) {
    var rows=[];
    ['repurchases','issuance'].forEach(function(kind){(d.flows?.[kind] || []).slice(-20).forEach(function(r){
      var days=(Date.parse(r.end)-Date.parse(r.start))/86400000+1;
      rows.push('<tr><td>'+esc(label(kind))+'</td><td>'+esc(r.start)+' to '+esc(r.end)+'</td><td>'+cash(r.value)+'</td><td>'+esc(days>=70 && days<=110 ? 'Reported quarter' : days>=330 ? 'Reported FY' : 'Reported cumulative period')+'</td><td>'+sourceLink(r)+'</td></tr>');
    });});
    return '<h4>Recent reported repurchase and issuance periods</h4><p class="bb-muted">Cumulative and annual periods can overlap. They are shown separately and are not added together.</p><div class="bb-scroll"><table><thead><tr><th>Flow</th><th>Period</th><th>Cash</th><th>Basis</th><th>Source</th></tr></thead><tbody>'+rows.join('')+'</tbody></table></div>';
  }
  function flowTable(d) {
    var rows = [];
    Object.entries(d.cash_periods || {}).forEach(function(pair) { var m = pair[1]; rows.push('<tr><td>' + esc(label(pair[0])) + '</td><td>' + esc(m.unit === 'shares' && num(m.value) ? Math.round(m.value).toLocaleString('en-US') : cash(m.value)) + '</td><td>' + esc((m.start || '') + ' → ' + (m.end || '')) + '</td><td>' + esc(m.period_label || label(m.reason)) + '</td></tr>'); });
    return shareBridge(d.share_bridge) + actionTable(d.actions) + '<div class="bb-scroll"><table><thead><tr><th>Flow</th><th>Amount</th><th>Period</th><th>Basis</th></tr></thead><tbody>' + rows.join('') + '</tbody></table></div><p class="bb-muted">A share bridge requires matching beginning and ending outstanding counts and reported gross issuance/repurchases. Unexplained changes remain unresolved.</p>';
  }
  function paceValue(b) { return b && b.rank_eligible ? {accelerating:3,steady:2,stopped:1,issuing_again:0}[b.pace] ?? null : null; }
  function compareRows(a,b,key,asc) {
    key = key === 'retired_since_peak_pct' ? 'net_reduction_1y' : key;
    var av = key === 'pace' ? paceValue(a.buyback) : key === 'quality' ? (a.buyback && a.buyback.rank_eligible ? 1 : null) : metric(a.buyback,key).value;
    var bv = key === 'pace' ? paceValue(b.buyback) : key === 'quality' ? (b.buyback && b.buyback.rank_eligible ? 1 : null) : metric(b.buyback,key).value;
    if(snapshotExpired()) { av=null;bv=null; }
    if (av == null && bv == null) return String(a.ticker).localeCompare(String(b.ticker));
    if (av == null) return 1;
    if (bv == null) return -1;
    return (av-bv)*(asc ? 1 : -1) || String(a.ticker).localeCompare(String(b.ticker));
  }
  function matches(row,filter) {
    var b = row.buyback || {}, net = metric(b,'net_reduction_1y').value;
    switch(filter || coverageState().filter) {
      case 'verified': return b.rank_eligible && net > 0;
      case 'accelerating': return !snapshotExpired() && b.rank_eligible && b.pace === 'accelerating';
      case 'offset': return metric(b,'gross_cash_ratio').value > 0 && net != null && net <= 0;
      case 'events': return eventsFor(row.ticker).some(function(e) { return e.book === 'ranked'; });
      case 'review': return snapshotExpired() || !b.rank_eligible || b.refresh_status === 'fetch_failed';
      default: return true;
    }
  }
  var SCREEN_SORTS = [['net_reduction_1y','Net reduction · 1Y'],['net_reduction_3y','Net reduction · 3Y'],['gross_cash_ratio','Buyback cash'],['net_cash_ratio','Net cash ratio'],['retirement_efficiency','Retirement efficiency'],['remaining_authorization_ratio','Remaining capacity'],['pace','Execution pace'],['quality','Evidence eligibility']];
  function screenSortKey() {
    var saved = coverageState();
    return saved.sort || 'net_reduction_1y';
  }
  function screenRows() {
    var saved = coverageState();
    var rows = ((state.snapshot && state.snapshot.companies && state.snapshot.companies.companies) || []).map(function(row) {
      return { ticker: row.ticker, company: row.company, buyback: row };
    }).filter(function(row) { return matches(row, saved.filter); });
    var key = screenSortKey();
    rows.sort(function(a, b) { return compareRows(a, b, key, false); });
    return rows;
  }
  function paintScreenTable(table) {
    var rows = screenRows();
    var total = ((state.snapshot && state.snapshot.companies && state.snapshot.companies.companies) || []).length;
    var body = rows.map(function(row) {
      var record = row.buyback;
      var net = metric(record, 'net_reduction_1y');
      var spent = metric(record, 'gross_cash_ratio');
      return '<tr><td>' + tickerLink(row.ticker) + '</td><td>' + esc(row.company) + '</td><td>' + status(record) + '</td><td>' + esc(net.value == null ? label(net.reason) : pct(net.value)) + '</td><td>' + esc(pct(metric(record, 'net_reduction_3y').value)) + '</td><td>' + esc(label(record.pace || 'unavailable')) + '</td><td>' + esc(spent.value == null ? '—' : pct(spent.value)) + '</td><td>' + esc(record.shares_end || '—') + '</td></tr>';
    }).join('');
    table.innerHTML = '<p class="bb-muted">Showing ' + rows.length + ' of ' + total + ' issuers.</p>' +
      (rows.length ? '<div class="bb-scroll"><table><thead><tr><th>Ticker</th><th>Company</th><th>Data</th><th>Net reduction · 1Y</th><th>Net reduction · 3Y</th><th>Pace</th><th>Buyback cash</th><th>Shares as of</th></tr></thead><tbody>' + body + '</tbody></table></div>' : '<p>No issuers match this screen.</p>');
  }
  function mountScreen(host) {
    if (!host) return;
    var saved = coverageState();
    var sortKey = screenSortKey();
    if (!saved.sort) { saved.sort = sortKey; write(FILTER_KEY, saved); }
    var el = document.createElement('div');
    el.id = 'buyback-screen-controls';
    el.className = 'bb-controls';
    el.innerHTML = '<label>Buyback screen <select data-bb-filter aria-label="Buyback screen">' + [['all','All companies'],['verified','Verified share reducers'],['accelerating','Accelerating'],['offset','Dilution offsets repurchases'],['events','Active events'],['review','Data requires review']].map(function(o) { return '<option value="' + o[0] + '"' + (saved.filter === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') +
      '</select></label><label>Buyback sort <select data-bb-sort aria-label="Buyback sort">' + SCREEN_SORTS.map(function(o) { return '<option value="' + o[0] + '"' + (sortKey === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') + '</select></label>' +
      '<small>' + esc(state.error || (state.snapshot ? state.snapshot.manifest.counts.verified + ' verified issuers · snapshot ' + state.snapshot.manifest.as_of : 'Awaiting verified data')) + '</small>';
    var screenKey = 'ssi-buyback-saved-screens-v2', screens = read(screenKey, {});
    el.innerHTML += '<label>Saved buyback screen<select data-bb-saved><option value="">Choose a saved screen</option>' + Object.keys(screens).sort().map(function(name) { return '<option value="' + esc(name) + '">' + esc(name) + '</option>'; }).join('') + '</select></label><label>Screen name<input data-bb-screen-name maxlength="60" aria-label="Buyback screen name"></label><button type="button" data-bb-screen-save>Save screen</button><button type="button" data-bb-screen-delete disabled>Delete selected screen</button><small data-bb-screen-message aria-live="polite"></small>';
    el.innerHTML += changeDigest();
    var table = document.createElement('div');
    table.className = 'bb-panel';
    host.replaceChildren(el, table);
    function refreshSaved(selectedName) {
      var select = el.querySelector('[data-bb-saved]');
      select.innerHTML = '<option value="">Choose a saved screen</option>' + Object.keys(screens).sort().map(function(name) { return '<option value="' + esc(name) + '">' + esc(name) + '</option>'; }).join('');
      select.value = selectedName || '';
      el.querySelector('[data-bb-screen-delete]').disabled = !select.value;
    }
    function applyScreen() {
      el.querySelector('[data-bb-filter]').value = saved.filter || 'all';
      el.querySelector('[data-bb-sort]').value = screenSortKey();
      paintScreenTable(table);
    }
    el.querySelector('[data-bb-filter]').addEventListener('change', function(e) { saved.filter = e.target.value; write(FILTER_KEY, saved); applyScreen(); });
    el.querySelector('[data-bb-sort]').addEventListener('change', function(e) { saved.sort = e.target.value; saved.activeSort = true; write(FILTER_KEY, saved); paintScreenTable(table); });
    el.querySelector('[data-bb-screen-save]').addEventListener('click', function() {
      var input = el.querySelector('[data-bb-screen-name]'), name = input.value.trim();
      if (!name) { input.focus(); return; }
      saved.sort = screenSortKey();
      saved.activeSort = true;
      screens[name] = Object.assign({}, saved);
      var ok = write(screenKey, screens);
      refreshSaved(name);
      el.querySelector('[data-bb-screen-message]').textContent = ok ? 'Buyback filter and sort saved on this browser.' : 'Browser storage is unavailable.';
    });
    el.querySelector('[data-bb-saved]').addEventListener('change', function(e) {
      el.querySelector('[data-bb-screen-delete]').disabled = !e.target.value;
      if (!screens[e.target.value]) return;
      saved = Object.assign({}, screens[e.target.value]);
      write(FILTER_KEY, saved);
      applyScreen();
    });
    el.querySelector('[data-bb-screen-delete]').addEventListener('click', function() {
      var select = el.querySelector('[data-bb-saved]'), name = select.value;
      if (!name) return;
      delete screens[name];
      write(screenKey, screens);
      refreshSaved('');
      el.querySelector('[data-bb-screen-message]').textContent = 'Saved screen deleted.';
    });
    paintScreenTable(table);
  }
  function eventRow(e) {
    return {id:e.id,lane:'buyback_events',lanes:['buyback_events'],book:e.book,ticker:e.ticker,company:e.company,what:e.what,
      ends:e.ends,ends_label:e.ends_label || e.date_label || 'Requires review',evidence_url:e.url,evidence_label:'Primary filing',evidence_kind:'filing',
      source_feed:'buyback_radar',as_of:e.filed,next:e.next,status:e.status,research_only:true,event_type:e.event_type,buyback_event:e};
  }
  function projectSituations(doc) {
    var out = Object.assign({},doc);
    ['rows','discovery','history'].forEach(function(k) { out[k] = (doc[k] || []).filter(function(r) { return r.lane !== 'buyback_events'; }); });
    var events = currentEvents();
    events.forEach(function(e) { if (e.book !== 'mentions') out[e.book === 'ranked' ? 'rows' : e.book === 'history' ? 'history' : 'discovery'].push(eventRow(e)); });
    out.buyback_mentions = events.filter(function(e) { return e.book === 'mentions'; }).map(function(e) { return {ticker:e.ticker,line:e.mention || e.what,filed:e.filed,url:e.url}; });
    out.buyback_snapshot = state.snapshot && state.snapshot.manifest; out.buyback_error = state.error;
    out.counts = Object.assign({},doc.counts);
    ['rows','discovery','history'].forEach(function(k) { var key = k === 'rows' ? 'ranked' : k; out.counts[key] = Object.assign({},doc.counts && doc.counts[key],{buyback_events:out[k].filter(function(r) { return r.lane === 'buyback_events'; }).length}); });
    return out;
  }

  function signalKey(r) { return [r.issuer_id || r.ticker,r.shares_end,Math.round(r.change_1y_pct*10),r.issuance_cause].join('|'); }
  function renderSignals(rows,filters) {
    filters = filters || {};
    if (filters.framework && !['all','dilution_financing'].includes(filters.framework)) return '';
    if (filters.stage && !['all','lead'].includes(filters.stage)) return '';
    var saved=read(DISPOSITION_KEY,{}), query=String(filters.query || '').toLowerCase();
    var controls=read('ssi-buyback-signal-controls-v2',{sort:'issuance',disposition:'all'});
    rows=(rows || []).filter(function(r){
      var d=saved[signalKey(r)] || {};
      return r.data_status==='verified' && (!query || [r.ticker,r.company,r.issuance_cause,r.explanation].join(' ').toLowerCase().includes(query)) && (controls.disposition==='all' || (d.status || 'investigate')===controls.disposition);
    });
    rows.sort(function(a,b){return controls.sort==='date' ? String(b.shares_end).localeCompare(String(a.shares_end)) : (b.change_1y_pct-a.change_1y_pct) || String(a.ticker).localeCompare(String(b.ticker));});
    var options=function(list,key){return list.map(function(o){return '<option value="'+o[0]+'"'+(controls[key]===o[0] ? ' selected' : '')+'>'+o[1]+'</option>';}).join('');};
    var toolbar='<div class="bb-controls"><label>Signal order <select data-bb-signal-sort>'+options([['issuance','Largest issuance'],['date','Latest observation']],'sort')+'</select></label><label>Investigation <select data-bb-signal-filter>'+options([['all','All dispositions'],['investigate','Investigate'],['explained','Explained'],['monitor','Monitor'],['dismiss','Dismissed']],'disposition')+'</select></label></div>';
    var html=rows.map(function(r){
      var key=signalKey(r), d=saved[key] || {status:'investigate'};
      return '<tr data-bb-signal="'+esc(key)+'"><td>'+tickerLink(r.ticker)+'<small>'+esc(r.company)+'</small></td><td>'+esc(pct(r.change_1y_pct))+'<small>after '+esc(pct(-r.change_5y_pct))+' reduced over 5Y</small><small>Gross repurchases '+cash(r.repurchase_fy_usd)+' through '+esc(r.repurchase_end || '?')+'</small></td><td>'+esc(label(r.issuance_cause))+'<small>'+esc(r.explanation || 'Cause requires investigation.')+'</small><small>'+esc(label(r.issuance_persistence || 'first_observation'))+'</small>'+sourceLink(r.explanation_source)+'</td><td>'+esc(r.shares_end)+'</td><td><select data-bb-disposition aria-label="Investigation status for '+esc(r.ticker)+'">'+['investigate','explained','monitor','dismiss'].map(function(v){return '<option value="'+v+'"'+(v===d.status ? ' selected' : '')+'>'+esc(label(v))+'</option>';}).join('')+'</select><label>Reason<input data-bb-reason type="text" maxlength="500" value="'+esc(d.reason || '')+'" aria-label="Reason for '+esc(r.ticker)+'"></label><button type="button" data-bb-save-disposition>Save</button><small>'+esc(d.updated ? 'Saved '+d.updated.slice(0,10) : 'Not yet saved')+'</small></td></tr>';
    }).join('');
    return '<section class="short-section bb-panel"><h3>Issuing again / '+rows.length+'</h3><p>Verified prior repurchases and share shrink followed by issuance. A research lead; the cause determines its meaning.</p>'+toolbar+(rows.length ? '<div class="bb-scroll"><table><thead><tr><th>Issuer</th><th>Share change</th><th>Cause</th><th>Observed</th><th>Investigation</th></tr></thead><tbody>'+html+'</tbody></table></div>' : '<p class="bb-muted">No verified issuance reversals match these filters. Unresolved and stale observations are excluded.</p>')+'<small>Dispositions and dated reasons are saved on this browser. A material new observation reopens the investigation.</small></section>';
  }
  function attachSignals(container,rerender) {
    container.querySelectorAll('[data-bb-save-disposition]').forEach(function(button){button.addEventListener('click',function(){
      var host=button.closest('[data-bb-signal]'), select=host.querySelector('[data-bb-disposition]'), input=host.querySelector('[data-bb-reason]');
      if(['explained','dismiss'].includes(select.value) && !input.value.trim()){input.setCustomValidity('Add a reason for this disposition.');input.reportValidity();return;}
      input.setCustomValidity('');var saved=read(DISPOSITION_KEY,{});
      saved[host.dataset.bbSignal]={status:select.value,reason:input.value.trim(),updated:new Date().toISOString()};
      write(DISPOSITION_KEY,saved);if(rerender)rerender();
    });});
    [['[data-bb-signal-sort]','sort'],['[data-bb-signal-filter]','disposition']].forEach(function(pair){
      container.querySelector(pair[0])?.addEventListener('change',function(e){var s=read('ssi-buyback-signal-controls-v2',{sort:'issuance',disposition:'all'});s[pair[1]]=e.target.value;write('ssi-buyback-signal-controls-v2',s);if(rerender)rerender();});
    });
  }
  function changeDigest() {
    var summary=state.snapshot && state.snapshot.summary;
    if(!summary)return '';
    var rows=(summary.changes || []).map(function(c){return '<li>'+tickerLink(c.ticker)+' / '+esc(label(c.kind))+' / '+esc(c.reason)+'</li>';});
    return '<details class="bb-panel bb-changes"><summary>Snapshot changes / '+(summary.changes_count || 0)+'</summary><ul>'+rows.join('')+'</ul>'+(summary.changes_count>rows.length ? '<small>Showing the first '+rows.length+' changes.</small>' : '')+'</details>';
  }
  function researchNote(b) {
    var records=read('ssi-buyback-research-outcomes-v2',[]).filter(function(r){return r.issuer_id===b.issuer_id;});
    var latest=records[records.length-1];
    return '<details class="bb-outcome"><summary>Research disposition and outcomes</summary><p>Save a dated research note against this frozen snapshot. Records are stored on this browser.</p><form data-bb-outcome="'+esc(b.ticker)+'"><label>Disposition<select name="disposition"><option>monitor</option><option>investigate</option><option>confirmed</option><option>dismiss</option><option>outcome</option></select></label><label>Evidence or outcome<textarea name="note" maxlength="2000" required></textarea></label><button>Save research note</button><output aria-live="polite"></output></form>'+(latest ? '<p>Latest: '+esc(latest.saved_at.slice(0,10))+' / '+esc(latest.disposition)+' / '+esc(latest.note)+'</p>' : '')+'<button type="button" data-bb-export-outcomes>Export saved research</button></details>';
  }
  function attachOutcomes(container) {
    container.querySelectorAll('[data-bb-outcome]').forEach(function(form){
      if(form.dataset.attached)return;form.dataset.attached='true';
      form.addEventListener('submit',function(e){e.preventDefault();var b=company(form.dataset.bbOutcome);if(!b)return;
        var rows=read('ssi-buyback-research-outcomes-v2',[]);rows.push({issuer_id:b.issuer_id,ticker:b.ticker,snapshot_id:b.snapshot_id,as_of:b.as_of,shares_end:b.shares_end,metrics:b.metrics,saved_at:new Date().toISOString(),disposition:form.elements.disposition.value,note:form.elements.note.value.trim()});
        var saved=write('ssi-buyback-research-outcomes-v2',rows);form.querySelector('output').textContent=saved ? 'Research note saved with this snapshot.' : 'Browser storage is unavailable. Export or copy this note before leaving.';
      });
    });
    container.querySelectorAll('[data-bb-export-outcomes]').forEach(function(button){if(button.dataset.attached)return;button.dataset.attached='true';button.addEventListener('click',function(){
      var blob=new Blob([JSON.stringify(read('ssi-buyback-research-outcomes-v2',[]),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='buyback-research-outcomes.json';a.click();URL.revokeObjectURL(url);
    });});
  }

  function projectShorts(doc) { return Object.assign({},doc,{buyback_issuance_signals:state.snapshot && !snapshotExpired() ? state.snapshot.companies.issuance_signals || [] : [],buyback_snapshot:state.snapshot && state.snapshot.manifest,buyback_error:state.error}); }
  global.BuybackViz = {load:load,company:company,renderHoldingsCell:renderHoldingsCell,renderDetail:renderDetail,renderEventDetails:renderEventDetails,projectSituations:projectSituations,projectShorts:projectShorts,renderSignals:renderSignals,attachSignals:attachSignals,mountScreen:mountScreen,matches:matches,compareRows:compareRows,metric:metric,hydrateAll:hydrateAll,attachScenarios:attachScenarios,tenderScenario:tenderScenario,epsScenario:epsScenario};
})(window);
