(function (global) {
  'use strict';

  const CUSTOM_KEY = 'ssi_short_alpha_custom_v2';
  const CHECKINS_KEY = 'ssi_short_alpha_checkins_v2';
  const FILTER_KEY = 'ssi_short_alpha_filter_v2';
  const REMOVED_KEY = 'ssi_short_alpha_removed_v2';
  const SELECTED_KEY = 'ssi_short_alpha_selected_v2';
  const REPO_BASE = 'https://github.com/magis-capital-partners/single-stock-investments/blob/main/';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; } catch (_) { return fallback; }
  }
  function write(key, value) { localStorage.setItem(key, JSON.stringify(value)); }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function price(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('en-US', { minimumFractionDigits: n < 2 ? 3 : 2, maximumFractionDigits: 4 }) : '—';
  }
  function frameworkMap(payload) { return Object.fromEntries((payload.frameworks || []).map(row => [row.id, row])); }
  function sourceTypeMap(payload) { return Object.fromEntries((payload.source_types || []).map(row => [row.id, row])); }
  function removedSet() { return new Set(read(REMOVED_KEY, [])); }
  function applyCheckins(row) {
    const overlays = read(CHECKINS_KEY, {});
    const all = [...(row.check_ins || []), ...(overlays[row.ticker] || [])]
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    if (!all.length) return row;
    const latest = all[all.length - 1];
    row.check_ins = all;
    row.outcome = {
      latest_date: latest.date,
      latest_price: Number(latest.price),
      hypothesis_state: latest.hypothesis_state || 'open',
      check_in_count: all.length,
    };
    return row;
  }
  function getCandidates(payload) {
    const removed = removedSet();
    return [...(payload.candidates || []), ...read(CUSTOM_KEY, [])]
      .filter(row => row && row.ticker && !removed.has(row.ticker))
      .map(row => clone(row));
  }
  function getPositions(payload) {
    const removed = removedSet();
    const drafts = read(CUSTOM_KEY, []).filter(row => row && row.position);
    return [...(payload.positions || payload.ideas || []), ...drafts]
      .filter(row => row && row.ticker && !removed.has(row.ticker) && row.position)
      .map(row => applyCheckins(clone(row)));
  }
  function linkFor(source) {
    if (!source) return '';
    if (source.url) {
      try {
        const parsed = new URL(source.url);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
      } catch (_) { return ''; }
    }
    if (!source.ref) return '';
    return REPO_BASE + String(source.ref).split('/').map(encodeURIComponent).join('/');
  }
  // Entry contract (Michael's Short-Selling desk, _system/research/short-alpha/README.md):
  // category, source, tags, summary, note_ref and the six rsdb lens reviews.
  const CATEGORY_LABELS = {
    accounting: 'Accounting',
    'shitco-concept': 'Shitco / concept',
    'supply-side': 'Supply-side / competition',
    'share-supply': 'Share supply',
    'reverse-split': 'Reverse split',
    'activist-short': 'Activist short',
    'borrow-squeeze': 'Borrow / squeeze risk',
    playbook: 'Playbook',
  };
  const LENS_STATUS_LABELS = { unreviewed: 'Unreviewed', unresolved: 'Unresolved', supported: 'Supported', contradicted: 'Contradicted' };
  const VAULT_PREFIX = 'research-vault/';
  const SSI_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9_][A-Za-z0-9_./-]*$/;
  function categoryLabel(id) { return CATEGORY_LABELS[id] || String(id || '').replace(/-/g, ' '); }
  function noteRefHtml(ref) {
    const text = String(ref || '').trim();
    if (!text) return '';
    if (text.startsWith(VAULT_PREFIX)) {
      return `<span class="short-note-ref is-vault" title="Narrative lives in the private research vault; it is not in this repository">${esc(text)}</span>`;
    }
    if (SSI_PATH.test(text)) {
      const href = REPO_BASE + text.split('/').map(encodeURIComponent).join('/');
      return `<a class="short-note-ref" href="${esc(href)}" target="_blank" rel="noopener">${esc(text)}</a>`;
    }
    return `<span class="short-note-ref">${esc(text)}</span>`;
  }
  function lensStatus(review) {
    const status = String((review || {}).status || '');
    return LENS_STATUS_LABELS[status] ? status : 'unreviewed';
  }
  function lensStrip(reviews) {
    if (!Array.isArray(reviews) || !reviews.length) return '';
    const recorded = reviews.filter(review => lensStatus(review) !== 'unreviewed').length;
    const cells = reviews.map(review => {
      const status = lensStatus(review);
      const name = String(review.lens_id || 'lens').replace(/_/g, ' ');
      const when = review.reviewed_at ? ` · ${review.reviewed_at}` : '';
      return `<i class="is-${status}" title="${esc(`${name}: ${LENS_STATUS_LABELS[status]}${when}`)}"></i>`;
    }).join('');
    return `<span class="short-lens-strip" role="img" aria-label="${recorded} of ${reviews.length} lens reviews recorded" title="${recorded} of ${reviews.length} lens reviews recorded">${cells}</span>`;
  }
  function entryMeta(row) {
    const bits = [];
    if (row.category) bits.push(`<span class="short-chip is-category" title="Category">${esc(categoryLabel(row.category))}</span>`);
    if (row.source) bits.push(`<span class="short-chip is-source" title="Filed by">${esc(row.source)}</span>`);
    for (const tag of row.tags || []) bits.push(`<span class="short-chip is-tag">#${esc(tag)}</span>`);
    return bits.length ? `<div class="short-meta">${bits.join('')}</div>` : '';
  }
  function entryCard(row) {
    const has = row.category || row.source || row.added_on || row.updated_on || (row.tags || []).length || row.note_ref;
    if (!has) return '';
    const rows = [
      row.category ? `<dt>Category</dt><dd>${esc(categoryLabel(row.category))}</dd>` : '',
      row.source ? `<dt>Source</dt><dd>${esc(row.source)}</dd>` : '',
      row.added_on || row.updated_on ? `<dt>Dates</dt><dd>added ${esc(row.added_on || '—')} · updated ${esc(row.updated_on || '—')}</dd>` : '',
      (row.tags || []).length ? `<dt>Tags</dt><dd>${(row.tags || []).map(tag => `<span class="short-chip is-tag">#${esc(tag)}</span>`).join(' ')}</dd>` : '',
      row.note_ref ? `<dt>Note</dt><dd>${noteRefHtml(row.note_ref)}</dd>` : '',
    ].join('');
    return `<div class="short-detail-card short-entry-card"><h4>Entry</h4><dl>${rows}</dl></div>`;
  }
  function lensTable(reviews) {
    if (!Array.isArray(reviews) || !reviews.length) return '';
    const body = reviews.map(review => {
      const status = lensStatus(review);
      const evidence = (review.supporting_evidence || []).length + (review.contradictory_evidence || []).length;
      return `<tr>
        <td>${esc(String(review.lens_id || '').replace(/_/g, ' '))}</td>
        <td><span class="short-lens-status is-${status}">${esc(LENS_STATUS_LABELS[status])}</span></td>
        <td>${esc(review.mechanism || '—')}</td>
        <td>${esc(review.falsifier || '—')}</td>
        <td>${esc(review.reviewed_at || review.known_at || '—')}${evidence ? ` · ${evidence} items` : ''}</td>
      </tr>`;
    }).join('');
    return `<div class="short-detail-card short-lens-card"><h4>Lens reviews ${lensStrip(reviews)}</h4>
      <table class="short-lens-table"><thead><tr><th>Lens</th><th>Status</th><th>Mechanism</th><th>Falsifier</th><th>Reviewed</th></tr></thead><tbody>${body}</tbody></table>
      <p class="form-hint">Six dated reviews from the reverse-split process. A blank review is unreviewed, never supported.</p></div>`;
  }
  function matchesFramework(candidate, frameworkId, frameworks) {
    if (!frameworkId || frameworkId === 'all') return true;
    const ids = new Set([...(candidate.effective_frameworks || candidate.frameworks || []), ...(candidate.gate_hits || [])]);
    if (ids.has(frameworkId)) return true;
    return (frameworks || []).some(row => row.parent === frameworkId && ids.has(row.id));
  }
  function sourceLabel(candidate, sourceTypes) {
    const all = candidate.sources || [];
    const first = all[0];
    if (!first) return candidate.origin === 'reverse_split_research' ? 'Reverse-split engine lead' : (candidate.origin || '—');
    const kind = sourceTypes[first.type]?.label || first.type || 'Source';
    return `${kind}: ${first.label || candidate.origin || '—'}${all.length > 1 ? ` (+${all.length - 1} more)` : ''}`;
  }
  function frameworkOptions(payload, selected) {
    const groups = payload.groups || [];
    const byGroup = new Map(groups.map(group => [group.id, []]));
    const loose = [];
    for (const row of payload.frameworks || []) {
      if (byGroup.has(row.group)) byGroup.get(row.group).push(row);
      else loose.push(row);
    }
    const html = groups.map(group => {
      const rows = byGroup.get(group.id) || [];
      if (!rows.length) return '';
      const options = rows.map(row => `<option value="${esc(row.id)}" ${row.id === selected ? 'selected' : ''}>${esc(row.label)}</option>`).join('');
      return `<optgroup label="${esc(group.label)}">${options}</optgroup>`;
    }).join('');
    return html + loose.map(row => `<option value="${esc(row.id)}" ${row.id === selected ? 'selected' : ''}>${esc(row.label)}</option>`).join('');
  }
  function renderFrameworkBoard(payload, active) {
    const groups = payload.groups || [];
    const coverage = payload.summary?.framework_coverage || {};
    const cards = (rows) => rows.map(row => {
      const stat = coverage[row.id] || { names: 0, positions: 0, status: row.empty_label || 'Unscored' };
      const empty = stat.names === 0;
      return `<button type="button" class="short-framework-card${active === row.id ? ' active' : ''}${empty ? ' is-unscored' : ''}" data-short-framework-card="${esc(row.id)}" title="${esc(row.question)}">
        <strong>${esc(row.label)}</strong>
        <small>${esc(row.question)}</small>
        <em>${empty ? esc(stat.status) : `${stat.names} names · ${stat.positions} live`}</em>
      </button>`;
    }).join('');
    return groups.map(group => {
      const rows = (payload.frameworks || []).filter(row => row.group === group.id);
      if (!rows.length) return '';
      return `<section class="short-framework-group"><h3>${esc(group.label)}</h3><p>${esc(group.reading || '')}</p><div class="short-framework-cards">${cards(rows)}</div></section>`;
    }).join('');
  }
  function scoreOf(row) {
    // `quant` is null for a name outside the screen universe; Number(null) is 0, so test the object first.
    const n = row && row.quant ? Number(row.quant.score) : NaN;
    return Number.isFinite(n) ? n : null;
  }
  function byScore(left, right) {
    const a = scoreOf(left);
    const b = scoreOf(right);
    if (a == null && b == null) return String(left.ticker).localeCompare(String(right.ticker));
    if (a == null) return 1;
    if (b == null) return -1;
    return b - a;
  }
  // The live book first, then names under research, then leads; within a stage by score.
  const STAGE_RANK = { live: 0, ic: 1, researching: 2, lead: 3, closed: 4, rejected: 5 };
  function byStageThenScore(left, right) {
    const a = STAGE_RANK[left.stage] ?? 9;
    const b = STAGE_RANK[right.stage] ?? 9;
    return a !== b ? a - b : byScore(left, right);
  }
  // Borrow as the payload states it: a fee, no shares, not in IBKR's file, or pending a refresh.
  function borrowCell(borrow, htbPct) {
    const b = borrow || {};
    const when = b.as_of ? ` · ${String(b.as_of).slice(0, 16).replace('T', ' ')} UTC` : '';
    if (b.status === 'not_in_file') return { text: 'Not in file', cls: 'is-none', title: `${b.message || "Not in IBKR's short-stock file"}${when}` };
    if (b.status === 'none_available') return { text: 'None', cls: 'is-none', title: `IBKR quotes no shares available${when}` };
    if (b.rate_pct == null) return { text: 'Pending', cls: 'is-pending', title: b.message || 'Awaiting the next IBKR borrow refresh' };
    const fee = Number(b.rate_pct);
    const shares = b.shares != null ? `${b.at_least ? '>' : ''}${Number(b.shares).toLocaleString()} shares available` : 'availability not quoted';
    return { text: `${fee.toFixed(fee < 10 ? 2 : 0)}%`, cls: fee >= (htbPct || 10) ? 'is-htb' : '', title: `${fee}% a year · ${shares}${when} · a reading, not a locate` };
  }
  function dtcCell(crowding) {
    const c = crowding || {};
    if (c.days_to_cover == null) return { text: '—', title: 'No short-interest observation' };
    const share = c.short_percent_float != null ? ` · ${(Number(c.short_percent_float) * 100).toFixed(1)}% of float short` : '';
    return { text: `${Number(c.days_to_cover).toFixed(1)}d`, title: `FINRA short interest, settlement ${c.settlement_ymd || '—'}${share} · context, not a reason to short` };
  }
  function scoreBadge(quant) {
    const n = quant ? Number(quant.score) : NaN;
    if (!Number.isFinite(n)) return `<span class="short-score is-empty" title="${esc(quant ? `${quant.evidence_count || 0} fundamental signals; three are needed` : 'Not in the screen universe')}">—</span>`;
    const tier = n >= 40 ? 'high' : (n >= 25 ? 'mid' : 'low');
    const title = `decay ${fmtShare(quant.decay)} · tape ${fmtShare(quant.tape)} · risk ${fmtShare(quant.risk)} · ${quant.evidence_count} signals`;
    return `<span class="short-score is-${tier}" title="${esc(title)}">${n.toFixed(0)}</span>`;
  }
  function fmtShare(value) {
    const n = Number(value);
    return Number.isFinite(n) ? `${Math.round(n * 100)}%` : '—';
  }
  function fmtSignal(key, row) {
    const v = row.value;
    if (v == null || !Number.isFinite(Number(v))) return row.note ? '' : 'n/a';
    const n = Number(v);
    if (key === 'cash_burn') return `${n.toFixed(1)} years of cash`;
    if (key === 'illiquidity') return `$${(n / 1e6).toFixed(1)}M a day`;
    if (key === 'volatility') return `${n.toFixed(0)}% realized${row.beta != null ? `, beta ${Number(row.beta).toFixed(1)}` : ''}`;
    if (key === 'trend_broken' || key === 'parabolic') return `${n > 0 ? '+' : ''}${n.toFixed(0)}% vs 200d${row.momentum_12_1_pct != null ? `, 12-1 ${Number(row.momentum_12_1_pct).toFixed(0)}%` : ''}`;
    if (key === 'crowding') return `${(n * 100).toFixed(1)}% of float${row.days_to_cover != null ? `, ${Number(row.days_to_cover).toFixed(1)}d to cover` : ''}`;
    if (key === 'leverage') return `debt ${(n * 100).toFixed(0)}% of assets`;
    if (key === 'insider_selling') return row.basis === 'market_cap' ? `${(n * 100).toFixed(2)}% of cap sold net` : `$${(Number(row.net_usd || 0) / 1e6).toFixed(1)}M sold net`;
    if (key === 'margin_trend') return `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)} pp`;
    return `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)}%`;
  }
  function quantCard(quant, payload, maps) {
    if (!quant) return '';
    const readings = (payload.quant_screen && payload.quant_screen.signals) || {};
    const group = (title, rows) => {
      const items = Object.entries(rows || {}).sort((a, b) => Number(b[1].score || 0) - Number(a[1].score || 0)).map(([key, row]) => {
        const meta = readings[key] || {};
        const lens = maps[meta.framework]?.label || meta.framework || '';
        const score = Number(row.score);
        return `<li class="${Number.isFinite(score) && score >= 0.5 ? 'is-hot' : ''}"><b>${esc(key.replace(/_/g, ' '))}</b><i style="width:${Number.isFinite(score) ? Math.round(score * 100) : 0}%"></i><span>${esc(fmtSignal(key, row))}${row.note ? ` · ${esc(row.note)}` : ''}</span><small>${esc(lens)}</small></li>`;
      }).join('');
      return items ? `<div><h5>${title}</h5><ul class="short-signal-list">${items}</ul></div>` : '';
    };
    const score = Number(quant.score);
    const headline = Number.isFinite(score)
      ? `${score.toFixed(0)} of 100 · decay ${fmtShare(quant.decay)}, tape ${fmtShare(quant.tape)}, risk ${fmtShare(quant.risk)} · ${quant.evidence_count} fundamental signals${quant.rank ? ` · rank ${quant.rank}` : ''}`
      : `Unscored · ${quant.evidence_count || 0} fundamental signals, three are needed${quant.facts && quant.facts.stale ? ' · filings older than 400 days' : ''}`;
    const profile = [quant.sic_description ? `SIC ${quant.sic || ''} ${quant.sic_description}`.trim() : '', quant.profile_note || ''].filter(Boolean).join(' · ');
    return `<div class="short-detail-card short-quant-card"><h4>Quant screen</h4><p class="short-quant-head">${esc(headline)}${profile ? `<br><span class="form-hint">${esc(profile)}</span>` : ''}</p>
      <div class="short-quant-groups">${group('Decay', quant.signals?.fundamental)}${group('Tape', quant.signals?.tape)}${group('Risk', quant.signals?.risk)}</div></div>`;
  }
  function renderScreen(payload, selected) {
    const screen = payload.quant_screen;
    if (!screen) return '';
    const maps = frameworkMap(payload);
    const rows = screen.rows || [];
    if (!rows.length) return `<section class="short-section"><h3 class="short-section-title">Quant screen</h3><p class="short-alpha-note">Every scored name is already tracked.</p></section>`;
    const body = rows.map(row => `<tr class="${selected === `screen:${row.ticker}` ? 'is-selected' : ''}" data-short-select="screen:${esc(row.ticker)}" tabindex="0">
        <td class="num">${row.rank ?? '—'}</td>
        <td class="short-symbol">${esc(row.ticker)}</td>
        <td>${esc(row.company || '')}</td>
        <td class="num">${scoreBadge(row)}</td>
        <td><span class="short-mini-bars" title="decay · tape · risk"><i style="width:${Math.round((row.decay || 0) * 100)}%"></i><i class="is-tape" style="width:${Math.round((row.tape || 0) * 100)}%"></i><i class="is-risk" style="width:${Math.round((row.risk || 0) * 100)}%"></i></span></td>
        <td>${(row.implied_frameworks || []).map(id => esc(maps[id]?.label || id)).join(', ') || '—'}</td>
        <td><button type="button" class="short-track" data-short-track="${esc(row.ticker)}" data-short-track-name="${esc(row.company || row.ticker)}" data-short-track-framework="${esc((row.implied_frameworks || [])[0] || '')}">Track</button></td>
      </tr>`).join('');
    const picked = rows.find(row => `screen:${row.ticker}` === selected);
    return `<section class="short-section"><h3 class="short-section-title">Quant screen <span>${rows.length}</span></h3>
      <p class="short-alpha-note">${esc(screen.methodology?.composite || '')} ${esc(screen.methodology?.minimum_evidence || '')} ${screen.scored_count != null ? `${screen.scored_count} of ${screen.universe_count} names scored as of ${esc(screen.generated_at || '—')}.` : ''} Names already in the ledger are left off this table and carry their score in the table above.</p>
      <div class="short-names-wrap"><table class="short-names short-screen">
        <thead><tr><th>#</th><th>Ticker</th><th>Name</th><th>Score</th><th>Decay · tape · risk</th><th>Lenses the numbers point at</th><th></th></tr></thead>
        <tbody>${body}</tbody></table></div>
      ${picked ? `<section class="short-name-detail"><h3>${esc(picked.ticker)} · ${esc(picked.company || '')}</h3><p>Screen hit. ${esc(screen.methodology?.reading || '')}</p>${quantCard({ ...picked, score: picked.score }, payload, maps)}</section>` : ''}
    </section>`;
  }
  function renderNames(candidates, payload, selected) {
    const sourceTypes = sourceTypeMap(payload);
    const maps = frameworkMap(payload);
    if (!candidates.length) return '<div class="short-alpha-empty">No names match this partition.</div>';
    const htb = payload.borrow_meta?.htb_fee_pct;
    const body = candidates.slice().sort(byStageThenScore).map(row => {
      const tags = (row.effective_frameworks || row.frameworks || []).map(id => esc(maps[id]?.label || id)).join(', ') || '<span class="form-hint">No lens yet</span>';
      const borrowView = borrowCell(row.borrow, htb);
      const dtcView = dtcCell(row.crowding);
      return `<tr class="${selected === row.ticker ? 'is-selected' : ''}" data-short-select="${esc(row.ticker)}" tabindex="0">
        <td class="short-symbol">${esc(row.ticker)}</td>
        <td>${esc(row.security_name || '')}${row.summary ? `<small class="short-summary" title="${esc(row.summary)}">${esc(row.summary)}</small>` : ''}${entryMeta(row)}</td>
        <td><span class="short-stage" data-stage="${esc(row.stage || '')}">${esc(row.stage || '—')}</span>${lensStrip(row.lens_reviews)}</td>
        <td class="num">${scoreBadge(row.quant)}</td>
        <td>${tags}</td>
        <td>${esc(sourceLabel(row, sourceTypes))}</td>
        <td>${esc(row.research?.next_step || '—')}</td>
        <td class="num short-borrow ${borrowView.cls}" title="${esc(borrowView.title)}">${esc(borrowView.text)}</td>
        <td class="num" title="${esc(dtcView.title)}">${esc(dtcView.text)}</td>
      </tr>`;
    }).join('');
    return `<div class="short-names-wrap"><table class="short-names">
      <thead><tr><th>Ticker</th><th>Name</th><th>Stage</th><th>Score</th><th>Frameworks</th><th>Source</th><th>Next gate</th><th>Borrow</th><th>Days to cover</th></tr></thead>
      <tbody>${body}</tbody>
    </table></div>`;
  }
  function renderDetail(candidate, payload) {
    if (!candidate) return '';
    const sourceTypes = sourceTypeMap(payload);
    const maps = frameworkMap(payload);
    const list = rows => (rows || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>Not recorded yet.</li>';
    const sources = (candidate.sources || []).map(source => {
      const href = linkFor(source);
      const label = `${sourceTypes[source.type]?.label || source.type}: ${source.label || 'Source'}`;
      return href ? `<a class="short-source" href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>` : `<span class="short-source">${esc(label)}</span>`;
    }).join('');
    const lenses = (candidate.effective_frameworks || []).map(id => {
      const row = maps[id];
      return `<li><strong>${esc(row?.label || id)}</strong> ${esc(row?.question || '')}</li>`;
    }).join('') || '<li>No lens yet. No lens has been written for this name.</li>';
    const furnace = (candidate.furnace_hits || []).map(hit => `<li>${esc(hit.short_impact || 'event')} · ${esc(hit.tag)} · ${esc(hit.claim || 'Filing event')}</li>`).join('');
    const hypothesis = String(candidate.hypothesis || '').trim();
    return `<section class="short-name-detail">
      <h3>${esc(candidate.ticker)} · ${esc(candidate.security_name || '')}</h3>
      ${entryMeta(candidate)}
      <p>${hypothesis ? esc(hypothesis) : 'Lead only. A publisher hit or filing event is not a thesis. Write the market belief, the variant view, one catalyst, and one falsifier before promoting it.'}</p>
      ${candidate.summary ? `<p class="short-entry-summary">${esc(candidate.summary)}</p>` : ''}
      ${candidate.research?.review_note ? `<p class="form-hint">${esc(candidate.research.review_note)}</p>` : ''}
      <div class="short-detail-grid">
        <div class="short-detail-card"><h4>Lenses</h4><ul>${lenses}</ul></div>
        <div class="short-detail-card"><h4>What should break</h4><ul>${list(candidate.catalysts)}</ul></div>
        <div class="short-detail-card"><h4>What proves us wrong</h4><ul>${list(candidate.falsifiers)}</ul></div>
        ${entryCard(candidate)}
      </div>
      <div class="short-sources">${sources || '<span class="form-hint">No sources linked.</span>'}</div>
      ${lensTable(candidate.lens_reviews)}
      ${quantCard(candidate.quant, payload, maps)}
      ${furnace ? `<div class="short-detail-card"><h4>Filing events</h4><ul>${furnace}</ul></div>` : ''}
    </section>`;
  }
  function renderAddForm(payload) {
    return `<details class="short-alpha-add">
      <summary>+ Track a name</summary>
      <form class="short-alpha-add-form" data-short-add-form>
        <label>Ticker<input name="ticker" required maxlength="14" placeholder="XYZ"></label>
        <label>Security name<input name="security_name" required placeholder="Company or instrument"></label>
        <label>Shares short <span class="form-hint">optional</span><input name="shares" type="number" min="1" step="any" placeholder="Leave blank to track a lead"></label>
        <label>Opened price<input name="opened_price" type="number" min="0.0001" step="any" placeholder="Required only with shares"></label>
        <label>Primary framework<select name="framework">${frameworkOptions(payload)}</select></label>
        <label>Instrument<select name="instrument_type"><option value="operating_company">Operating company</option><option value="holding_company">Holding company</option><option value="leveraged_etf">Leveraged ETF</option><option value="etf">ETF</option><option value="other">Other</option></select></label>
        <label>Source type<select name="source_type">${(payload.source_types || []).map(row => `<option value="${esc(row.id)}">${esc(row.label)}</option>`).join('')}</select></label>
        <label>Source URL<input name="source_url" type="url" placeholder="https://…"></label>
        <label class="full">Hypothesis<textarea name="hypothesis" required rows="2" placeholder="What does the market believe, why is it wrong, and what changes the price?"></textarea></label>
        <div class="full"><button type="submit">Save browser draft</button> <span class="form-hint" data-short-add-status>Saved in this browser until exported into candidates.json. Shares are optional. A name without shares stays off the open book.</span></div>
      </form>
    </details>`;
  }
  function renderPosition(idea, maps) {
    const outcome = idea.outcome || {};
    const completion = Number(idea.artifact_status?.completion_pct || 0);
    const sourceTypes = sourceTypeMap(maps.payload);
    const tags = (idea.effective_frameworks || idea.frameworks || []).map(id => `<span class="short-tag" title="${esc(maps.frameworks[id]?.question || '')}">${esc(maps.frameworks[id]?.label || id)}</span>`).join('');
    const list = rows => (rows || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>Not recorded yet.</li>';
    const sources = (idea.sources || []).map(source => {
      const href = linkFor(source);
      const label = `${sourceTypes[source.type]?.label || source.type}: ${source.label}`;
      return href ? `<a class="short-source" href="${esc(href)}" target="_blank" rel="noopener">${esc(label)}</a>` : `<span class="short-source">${esc(label)}</span>`;
    }).join('');
    const latest = (idea.check_ins || [])[idea.check_ins.length - 1] || {};
    const opened = idea.position?.opened_date || idea.position?.baseline_date || '—';
    const borrowView = borrowCell(idea.borrow, maps.payload?.borrow_meta?.htb_fee_pct);
    const dtcView = dtcCell(idea.crowding);
    const ageDays = outcome.latest_date ? Math.floor((Date.now() - Date.parse(outcome.latest_date)) / 86400000) : null;
    const stale = idea.position_status !== 'closed' && ageDays != null && ageDays > 30
      ? `<p class="short-stale-checkin">No check-in since ${esc(outcome.latest_date)} (${ageDays} days): the observed price below is the last recorded one, not today's.</p>` : '';
    const closedNote = idea.position_status === 'closed'
      ? `<p class="short-stale-checkin">Closed: ${esc(idea.research?.review_note || 'no longer a live short.')}</p>` : '';
    return `<details class="short-alpha-row" data-short-ticker="${esc(idea.ticker)}">
      <summary>
        <div class="short-name"><span class="short-symbol">${esc(idea.ticker)}</span><span class="short-security"><strong>${esc(idea.security_name)}</strong><small>${esc(String(idea.instrument_type || '').replace(/_/g, ' '))}${idea.underlying ? ` · underlying ${esc(idea.underlying)}` : ''}</small></span></div>
        <div class="short-frameworks">${tags}</div>
        <div class="short-metric">$${price(idea.position?.split_adjusted_open_price || idea.position?.opened_price)}<small>split-adjusted entry</small></div>
        <div class="short-metric" title="${esc(borrowView.title)}">${esc(borrowView.text)}<small>borrow</small></div>
        <div class="short-metric" title="${esc(dtcView.title)}">${esc(dtcView.text)}<small>days to cover</small></div>
        <div class="short-metric">${completion}%<small>research</small></div>
      </summary>
      <div class="short-alpha-detail">
        ${closedNote}${stale}
        <div class="short-hypothesis-flow">
          <div class="short-flow-block"><h4>Hypothesis · ${esc(opened)}</h4><p>${esc(idea.hypothesis || 'No hypothesis recorded.')}</p></div>
          <div class="short-flow-arrow" aria-hidden="true">→</div>
          <div class="short-flow-block"><h4>Observed · ${esc(outcome.latest_date || '—')}</h4><p><strong>${esc(outcome.hypothesis_state || 'open')}</strong> at $${price(outcome.latest_price)}. ${esc(latest.note || 'Add a check-in to compare evidence with the original claim.')}</p></div>
        </div>
        <div class="short-detail-grid">
          <div class="short-detail-card"><h4>What should break</h4><ul>${list(idea.catalysts)}</ul></div>
          <div class="short-detail-card"><h4>What proves us wrong</h4><ul>${list(idea.falsifiers)}</ul></div>
          <div class="short-detail-card"><h4>Evidence and next gate</h4><div class="short-sources">${sources || '<span class="form-hint">No sources linked.</span>'}</div><p class="form-hint" style="margin-top:8px">${esc(idea.research?.next_step || 'Define the next research gate.')}</p></div>
        </div>
        <details class="short-checkin"><summary>+ Record actual outcome</summary>
          <form class="short-checkin-form" data-short-checkin-form data-ticker="${esc(idea.ticker)}">
            <label>Date<input name="date" required type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
            <label>Price<input name="price" required type="number" min="0.0001" step="any" value="${esc(outcome.latest_price || idea.position?.opened_price || '')}"></label>
            <label>Hypothesis state<select name="state"><option value="open">Open</option><option value="strengthened">Strengthened</option><option value="weakened">Weakened</option><option value="falsified">Falsified</option><option value="realized">Realized</option><option value="closed_risk">Closed for risk</option></select></label>
            <label>What actually happened<textarea name="note" required rows="1" placeholder="Evidence, borrow, catalyst, or falsifier"></textarea></label>
            <button type="submit">Save check-in</button>
          </form>
        </details>
        <button type="button" class="short-remove" data-short-remove="${esc(idea.ticker)}">Hide in this browser</button>
      </div>
    </details>`;
  }
  function render(payload) {
    const maps = { frameworks: frameworkMap(payload), payload };
    const saved = read(FILTER_KEY, { query: '', framework: 'all', stage: 'all' });
    const selected = read(SELECTED_KEY, '');
    const candidates = getCandidates(payload).filter(row => {
      const hay = `${row.ticker} ${row.security_name} ${row.hypothesis} ${row.origin || ''} ${row.category || ''} ${row.source || ''} ${(row.tags || []).join(' ')} ${row.summary || ''}`.toLowerCase();
      const stageOk = saved.stage === 'all' || row.stage === saved.stage;
      return (!saved.query || hay.includes(saved.query.toLowerCase()))
        && stageOk
        && matchesFramework(row, saved.framework, payload.frameworks);
    });
    const allPositions = getPositions(payload).filter(row => {
      const hay = `${row.ticker} ${row.security_name} ${row.hypothesis}`.toLowerCase();
      const stageOk = saved.stage === 'all' || row.stage === saved.stage;
      return (!saved.query || hay.includes(saved.query.toLowerCase()))
        && stageOk
        && matchesFramework(row, saved.framework, payload.frameworks);
    });
    const positions = allPositions.filter(row => row.position_status !== 'closed');
    const closedPositions = allPositions.filter(row => row.position_status === 'closed');
    const selectedRow = getCandidates(payload).find(row => row.ticker === selected) || null;
    const summary = payload.summary || {};
    const bm = payload.borrow_meta || {};
    const cm = payload.crowding_meta || {};
    const borrowNote = bm.as_of
      ? `Borrow: IBKR's public short-stock file, read ${String(bm.as_of).slice(0, 16).replace('T', ' ')} UTC; ${bm.quoted ?? '—'} of ${summary.candidate_count ?? candidates.length} names quoted, ${bm.not_in_file ?? 0} not in the file, ${bm.pending ?? 0} pending. Fee is % a year; a reading is not a locate; ${bm.htb_fee_pct ?? 10}% or more is marked hard to borrow.`
      : 'Borrow: no IBKR file has been loaded yet.';
    const crowdNote = cm.settlement
      ? ` Days to cover: FINRA short interest settled ${cm.settlement}, ${cm.covered ?? 0} names. Context, not a reason to short.`
      : '';
    const stages = ['all', 'lead', 'researching', 'ic', 'live', 'closed', 'rejected'];
    return `<div class="short-alpha-header">
      <div><div class="short-alpha-kicker">Short Alpha</div><h2>Frameworks, names that fit, and the open book</h2><p>Every lens from the short library, every name that fits one, and the positions we have actually borrowed. A publisher hit is a lead. It is not a thesis.</p></div>
      <div class="short-alpha-rail"><span>Framework</span><i></i><span>Name</span><i></i><span>Position</span></div>
    </div>
    <div class="short-alpha-summary">
      <div class="short-alpha-stat"><span>Names</span><strong>${summary.candidate_count ?? candidates.length}</strong><small>${summary.lead_count ?? 0} leads</small></div>
      <div class="short-alpha-stat"><span>Open book</span><strong>${summary.position_count ?? positions.length}</strong><small>borrowed shorts</small></div>
      <div class="short-alpha-stat"><span>Research complete</span><strong>${summary.research_complete_count ?? 0}/${summary.position_count ?? positions.length}</strong><small>open positions; artifact gate, not an IC decision</small></div>
      <div class="short-alpha-stat"><span>Quant screen</span><strong>${payload.quant_screen ? (payload.quant_screen.scored_count ?? '—') : '—'}</strong><small>${payload.quant_screen ? `scored of ${payload.quant_screen.universe_count ?? '—'} names` : 'not built on this checkout'}</small></div>
    </div>
    <section class="short-section"><h3 class="short-section-title">Frameworks</h3>${renderFrameworkBoard(payload, saved.framework)}</section>
    <div class="short-alpha-toolbar">
      <input class="search" data-short-search placeholder="Search ticker, name, or thesis…" value="${esc(saved.query)}" aria-label="Search short names">
      <select class="short-alpha-filter" data-short-framework aria-label="Filter by short framework"><option value="all">All frameworks</option>${frameworkOptions(payload, saved.framework)}</select>
      <select class="short-alpha-filter" data-short-stage aria-label="Filter by stage">${stages.map(stage => `<option value="${stage}" ${saved.stage === stage ? 'selected' : ''}>${stage === 'all' ? 'All stages' : stage}</option>`).join('')}</select>
      <div class="short-alpha-actions"><button type="button" data-short-export>Export ledger</button><button type="button" data-short-reset title="Remove browser-only drafts and check-ins">Reset browser drafts</button></div>
    </div>
    ${renderAddForm(payload)}
    <section class="short-section"><h3 class="short-section-title">Names tracked <span>${candidates.length}</span></h3>
      <p class="short-alpha-note">${esc(borrowNote)}${esc(crowdNote)} Missing is never zero.</p>
      ${renderNames(candidates, payload, selected)}
      ${renderDetail(selectedRow && candidates.some(row => row.ticker === selectedRow.ticker) ? selectedRow : null, payload)}
    </section>
    ${renderScreen(payload, selected)}
    <section class="short-section"><h3 class="short-section-title">Open book <span>${positions.length}</span></h3>
      <div class="short-alpha-book">${positions.length ? positions.map(row => renderPosition(row, maps)).join('') : '<div class="short-alpha-empty">No borrowed shorts in this partition.</div>'}</div>
      ${closedPositions.length ? `<h4 class="short-closed-title">Closed <span>${closedPositions.length}</span></h4><div class="short-alpha-book is-closed">${closedPositions.map(row => renderPosition(row, maps)).join('')}</div>` : ''}
    </section>
    <section class="short-section short-reverse-splits" data-short-reverse-splits hidden>
      <h3 class="short-section-title">Reverse splits</h3>
      <div data-short-reverse-splits-body></div>
    </section>
    <p class="short-alpha-note">${['borrow', 'crowding', 'leads', 'reverse_splits', 'quant', 'excluded', 'desk_notes'].map(key => esc(payload.methodology?.[key] || '')).filter(Boolean).join(' ')}</p>`;
  }
  // The Reverse splits sub-section is filled by index.html from data/reverse_splits.json
  // through window.ReverseSplitsViz.render(doc) (dashboard/reverse-splits-viz.js). The
  // section stays hidden when the file is absent or the renderer is not loaded.
  function mountReverseSplits(container, doc) {
    const section = container && container.querySelector('[data-short-reverse-splits]');
    if (!section) return false;
    const body = section.querySelector('[data-short-reverse-splits-body]');
    const viz = global.ReverseSplitsViz;
    if (!doc || typeof doc !== 'object' || !viz || typeof viz.render !== 'function') {
      section.hidden = true;
      if (body) body.innerHTML = '';
      return false;
    }
    let html = '';
    try { html = String(viz.render(doc, { hideTitle: true }) || ''); } catch (error) { html = `<div class="short-alpha-empty">Reverse splits view failed: ${esc(error && error.message)}</div>`; }
    if (!html.trim()) { section.hidden = true; return false; }
    if (body) body.innerHTML = html;
    section.hidden = false;
    if (typeof viz.attach === 'function') {
      try { viz.attach(body || section, doc); } catch (_) { /* optional */ }
    }
    return true;
  }
  function mergedExport(payload) {
    const out = clone(payload);
    out.candidates = getCandidates(payload);
    out.positions = getPositions(payload);
    out.ideas = out.positions;
    out.exported_at = new Date().toISOString();
    return out;
  }
  function attach(container, payload, rerender) {
    const search = container.querySelector('[data-short-search]');
    const framework = container.querySelector('[data-short-framework]');
    const stage = container.querySelector('[data-short-stage]');
    const updateFilter = restoreFocus => {
      write(FILTER_KEY, {
        query: search.value.trim(),
        framework: framework.value,
        stage: stage.value,
      });
      rerender();
      if (restoreFocus) {
        const nextSearch = container.querySelector('[data-short-search]');
        if (nextSearch) { nextSearch.focus(); nextSearch.setSelectionRange(nextSearch.value.length, nextSearch.value.length); }
      }
    };
    search?.addEventListener('input', () => updateFilter(true));
    framework?.addEventListener('change', () => updateFilter(false));
    stage?.addEventListener('change', () => updateFilter(false));
    container.querySelectorAll('[data-short-framework-card]').forEach(button => button.addEventListener('click', () => {
      const id = button.dataset.shortFrameworkCard;
      const current = read(FILTER_KEY, { query: search.value.trim(), framework: 'all', stage: stage.value });
      current.framework = current.framework === id ? 'all' : id;
      current.query = search.value.trim();
      current.stage = stage.value;
      write(FILTER_KEY, current);
      rerender();
    }));
    const selectTicker = ticker => {
      write(SELECTED_KEY, ticker);
      rerender();
    };
    container.querySelectorAll('[data-short-select]').forEach(row => {
      row.addEventListener('click', () => selectTicker(row.dataset.shortSelect));
      row.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectTicker(row.dataset.shortSelect);
        }
      });
    });
    container.querySelectorAll('[data-short-track]').forEach(button => button.addEventListener('click', event => {
      event.stopPropagation();
      const box = container.querySelector('.short-alpha-add');
      const form = container.querySelector('[data-short-add-form]');
      if (!box || !form) return;
      box.open = true;
      form.querySelector('[name="ticker"]').value = button.dataset.shortTrack || '';
      form.querySelector('[name="security_name"]').value = button.dataset.shortTrackName || '';
      const lens = form.querySelector('[name="framework"]');
      if (lens && button.dataset.shortTrackFramework && [...lens.options].some(option => option.value === button.dataset.shortTrackFramework)) lens.value = button.dataset.shortTrackFramework;
      const source = form.querySelector('[name="source_type"]');
      if (source && [...source.options].some(option => option.value === 'internal_analysis')) source.value = 'internal_analysis';
      box.scrollIntoView({ behavior: 'smooth', block: 'start' });
      form.querySelector('[name="hypothesis"]')?.focus();
    }));
    container.querySelector('[data-short-add-form]')?.addEventListener('submit', event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const ticker = String(form.get('ticker') || '').trim().toUpperCase();
      const sharesRaw = String(form.get('shares') || '').trim();
      const shares = sharesRaw ? Number(sharesRaw) : 0;
      const openedRaw = String(form.get('opened_price') || '').trim();
      const openedPrice = openedRaw ? Number(openedRaw) : 0;
      const status = event.currentTarget.querySelector('[data-short-add-status]');
      if (!ticker) return;
      if ((payload.candidates || []).some(row => row.ticker === ticker) || (payload.positions || []).some(row => row.ticker === ticker)) {
        if (status) status.textContent = `${ticker} is already in the repository ledger.`;
        return;
      }
      if (sharesRaw && !(shares > 0 && openedPrice > 0)) {
        if (status) status.textContent = 'A borrowed short needs a share count and an opened price.';
        return;
      }
      const frameworkId = String(form.get('framework'));
      const sourceUrl = String(form.get('source_url') || '').trim();
      const today = new Date().toISOString().slice(0, 10);
      const draft = {
        ticker,
        security_name: String(form.get('security_name') || ticker),
        instrument_type: String(form.get('instrument_type') || 'operating_company'),
        stage: shares > 0 ? 'researching' : 'lead',
        origin: 'browser_draft',
        frameworks: [frameworkId],
        primary_framework: frameworkId,
        effective_frameworks: [frameworkId],
        hypothesis: String(form.get('hypothesis') || ''),
        catalysts: [],
        falsifiers: [],
        research: { status: 'browser_draft', ic: 'not_ready', next_step: 'Promote the exported draft into candidates.json.' },
        sources: sourceUrl ? [{ type: String(form.get('source_type') || 'internal_analysis'), label: 'Initial source', url: sourceUrl }] : [],
        gates: { path_and_timing: 'unscored', issuer_retaliation: 'unscored' },
        gate_hits: [],
        furnace_hits: [],
        borrow: { status: 'pending', source: 'IBKR borrow feed', message: 'Awaiting the next IBKR borrow refresh.' },
        crowding: null,
        artifact_status: { completion_pct: 0 },
        has_position: shares > 0,
      };
      if (shares > 0) {
        draft.position = { shares: -Math.abs(shares), opened_price: openedPrice, opened_date: today, split_adjustment_factor: 1, split_adjusted_open_price: openedPrice };
        draft.check_ins = [{ date: today, price: openedPrice, hypothesis_state: 'open', note: 'Browser draft baseline.' }];
        draft.outcome = { latest_date: today, latest_price: openedPrice, hypothesis_state: 'open', check_in_count: 1 };
      }
      const custom = read(CUSTOM_KEY, []).filter(row => row.ticker !== ticker);
      custom.push(draft);
      write(CUSTOM_KEY, custom);
      rerender();
    });
    container.querySelectorAll('[data-short-checkin-form]').forEach(node => node.addEventListener('submit', event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const ticker = event.currentTarget.dataset.ticker;
      const overlays = read(CHECKINS_KEY, {});
      overlays[ticker] = overlays[ticker] || [];
      overlays[ticker].push({ date: String(form.get('date')), price: Number(form.get('price')), hypothesis_state: String(form.get('state')), note: String(form.get('note')) });
      write(CHECKINS_KEY, overlays);
      rerender();
    }));
    container.querySelector('[data-short-export]')?.addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(mergedExport(payload), null, 2) + '\n'], { type: 'application/json' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `short-alpha-ledger-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    });
    container.querySelector('[data-short-reset]')?.addEventListener('click', () => {
      if (!window.confirm('Remove all browser-only Short Alpha drafts and check-ins? The repository ledger is unchanged.')) return;
      localStorage.removeItem(CUSTOM_KEY);
      localStorage.removeItem(CHECKINS_KEY);
      localStorage.removeItem(REMOVED_KEY);
      localStorage.removeItem(SELECTED_KEY);
      rerender();
    });
    container.querySelectorAll('[data-short-remove]').forEach(button => button.addEventListener('click', () => {
      const ticker = button.dataset.shortRemove;
      if (!window.confirm(`Hide ${ticker} in this browser? The repository ledger is unchanged. Reset browser drafts restores it.`)) return;
      write(REMOVED_KEY, [...new Set([...read(REMOVED_KEY, []), ticker])]);
      rerender();
    }));
  }
  global.ShortAlphaViz = { render, attach, getCandidates, getPositions, mountReverseSplits, lensStrip, noteRefHtml, entryMeta };
})(window);
