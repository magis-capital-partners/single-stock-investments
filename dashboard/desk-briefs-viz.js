// Desk briefs block for the Ideas > Inbox view. Reads dashboard/data/desk_briefs.json
// (built by _system/scripts/build_desk_briefs.py; contract in
// _system/data/desk_briefs/README.md). One card per desk, owner and desk filter chips,
// items table (ticker, headline, one number, confidence, evidence, next) and the input
// ages. Every string from the payload is escaped. Mirrors special-situations-viz.js.
(function (global) {
  'use strict';

  const state = {
    owner: 'all',
    desk: 'all',
  };

  const esc = (value) => String(value == null ? '' : value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const DESK_ORDER = ['special_situations', 'activism', 'fundamentals', 'nol_tax_assets', 'tape_index', 'stahl', 'short_selling'];
  const DESK_LABELS = {
    special_situations: 'Special Situations',
    activism: 'Activism',
    fundamentals: 'Fundamentals',
    nol_tax_assets: 'NOL and Tax Assets',
    tape_index: 'Index, forced flow and tape',
    stahl: 'Murray Stahl',
    short_selling: 'Short Selling',
  };
  const OWNER_LABELS = { drew: 'Drew', michael: 'Michael' };

  function deskLabel(doc, id) {
    const labels = (doc && doc.desk_labels) || {};
    return labels[id] || DESK_LABELS[id] || String(id || '').replaceAll('_', ' ');
  }

  function ownerLabel(id) {
    return OWNER_LABELS[id] || String(id || '').replaceAll('_', ' ');
  }

  function isNum(value) {
    return value != null && value !== '' && Number.isFinite(Number(value));
  }

  /** Hours as a short age: 0.4 -> "<1h", 14.2 -> "14h", 61 -> "3d". */
  function age(hours) {
    if (!isNum(hours)) return 'age unknown';
    const h = Number(hours);
    if (h < 1) return '<1h';
    if (h < 48) return `${Math.round(h)}h`;
    return `${Math.round(h / 24)}d`;
  }

  function shortStamp(value) {
    if (!value) return 'no stamp';
    const text = String(value);
    return text.length > 16 ? `${text.slice(0, 16)}Z`.replace('ZZ', 'Z') : text;
  }

  function basename(path) {
    const text = String(path || '');
    return text.slice(text.lastIndexOf('/') + 1) || text;
  }

  function selectDesks(doc) {
    const desks = Array.isArray(doc && doc.desks) ? doc.desks : [];
    return desks
      .filter((d) => (state.owner === 'all' || d.owner === state.owner) && (state.desk === 'all' || d.desk === state.desk))
      .sort((a, b) => DESK_ORDER.indexOf(a.desk) - DESK_ORDER.indexOf(b.desk));
  }

  function evidenceCell(item) {
    const rows = Array.isArray(item.evidence) ? item.evidence : [];
    if (!rows.length) return '<span class="muted">none</span>';
    return rows.map((e) => {
      const kind = e && e.kind ? `<span class="idea-type">${esc(e.kind)}</span> ` : '';
      const ref = esc((e && e.ref) || 'Source');
      const url = e && typeof e.url === 'string' && /^https?:\/\//i.test(e.url) ? e.url : '';
      return `<div class="desk-brief-evidence">${kind}${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${ref}</a>` : ref}</div>`;
    }).join('');
  }

  function itemRow(item, doc) {
    const handoff = item.handoff ? `<div class="desk-brief-handoff">Hand off: ${esc(deskLabel(doc, item.handoff))}</div>` : '';
    const lane = item.lane ? `<div class="desk-brief-lane">${esc(String(item.lane).replaceAll('_', ' '))}</div>` : '';
    return `<tr>
      <td class="mono"><strong>${esc(item.ticker || 'unresolved')}</strong>${lane}</td>
      <td>${esc(item.headline)}</td>
      <td class="desk-brief-number">${esc(item.one_number)}</td>
      <td><span class="idea-type">${esc(item.confidence || 'unstated')}</span></td>
      <td>${evidenceCell(item)}</td>
      <td>${esc(item.next || '')}${handoff}</td>
    </tr>`;
  }

  function inputsLine(entry) {
    const inputs = Array.isArray(entry.inputs_read) ? entry.inputs_read : [];
    if (!inputs.length) return '<div><strong>Inputs.</strong> none recorded</div>';
    const parts = inputs.map((i) => {
      const missing = i.exists === false ? ' <span class="badge badge-warn">missing</span>' : '';
      const ageText = isNum(i.age_hours_at_read) ? `${age(i.age_hours_at_read)} old at read` : 'no stamp';
      return `<code title="${esc(i.path || '')}">${esc(basename(i.path))}</code> (${esc(shortStamp(i.generated_at))}, ${esc(ageText)})${missing}`;
    });
    return `<div><strong>Inputs.</strong> ${parts.join(' · ')}</div>`;
  }

  function cardHtml(entry, doc) {
    const items = Array.isArray(entry.items) ? entry.items : [];
    const stale = entry.stale ? ' <span class="badge badge-warn" title="Older than the stale window">stale</span>' : '';
    const screens = (entry.screens_empty || []).length
      ? `<div><strong>Screens empty.</strong> ${esc(entry.screens_empty.map((s) => String(s).replaceAll('_', ' ')).join(', '))}</div>`
      : '';
    const notes = entry.notes ? `<div><strong>Notes.</strong> ${esc(entry.notes)}</div>` : '';
    return `<article class="desk-brief-card${entry.stale ? ' is-stale' : ''}" data-desk-brief="${esc(entry.desk)}">
      <header>
        <h3>${esc(deskLabel(doc, entry.desk))}</h3>
        <span class="desk-brief-owner">${esc(ownerLabel(entry.owner))}</span>
        <span class="desk-brief-meta">by <code>${esc(entry.author)}</code> · as of ${esc(entry.as_of)} · ${esc(age(entry.age_hours))} ago${stale}</span>
        <span class="desk-brief-meta desk-brief-count">${items.length} item${items.length === 1 ? '' : 's'}</span>
      </header>
      <div class="ideas-table-wrap"><table class="ideas-table desk-brief-table"><thead><tr><th>Ticker</th><th>Headline</th><th>One number</th><th>Confidence</th><th>Evidence</th><th>Next</th></tr></thead><tbody>${items.length ? items.map((item) => itemRow(item, doc)).join('') : '<tr><td colspan="6">No ranked items. The desk filed an empty run.</td></tr>'}</tbody></table></div>
      <div class="desk-brief-foot">${inputsLine(entry)}${screens}${notes}<div><strong>File.</strong> <code>${esc(entry.path || '')}</code></div></div>
    </article>`;
  }

  function chips(doc) {
    const desks = Array.isArray(doc.desks) ? doc.desks : [];
    const ownerCounts = { drew: 0, michael: 0 };
    desks.forEach((d) => { if (Object.hasOwn(ownerCounts, d.owner)) ownerCounts[d.owner] += 1; });
    const ownerChips = [['all', 'All owners', desks.length]].concat(Object.keys(ownerCounts).map((o) => [o, ownerLabel(o), ownerCounts[o]]));
    const deskIds = DESK_ORDER.filter((id) => desks.some((d) => d.desk === id));
    const deskChips = [['all', 'All desks', desks.length]].concat(deskIds.map((id) => [id, deskLabel(doc, id), desks.filter((d) => d.desk === id).length]));
    const chip = (attr, key, label, count, active) => `<button type="button" class="${active ? 'active' : ''}" ${attr}="${esc(key)}">${esc(label)} · ${count}</button>`;
    return `<div class="desk-briefs-filters" aria-label="Desk brief filters">
      <span class="k">Owner</span><div class="screen-switcher">${ownerChips.map(([k, l, c]) => chip('data-desk-brief-owner', k, l, c, state.owner === k)).join('')}</div>
      <span class="k">Desk</span><div class="screen-switcher">${deskChips.map(([k, l, c]) => chip('data-desk-brief-desk', k, l, c, state.desk === k)).join('')}</div>
    </div>`;
  }

  function healthHtml(doc) {
    const health = (doc && doc.health) || {};
    const lines = [].concat(health.structural_errors || [], health.problems || []);
    if (!lines.length || health.status === 'healthy') return '';
    return `<div class="desk-brief-health"><strong>${esc(health.status || 'degraded')}.</strong> ${lines.map((l) => esc(l)).join(' · ')}</div>`;
  }

  function render(payload, options) {
    const opts = options || {};
    if (opts.owner) state.owner = opts.owner;
    if (opts.desk) state.desk = opts.desk;
    const doc = payload || {};
    const all = Array.isArray(doc.desks) ? doc.desks : [];
    const shown = selectDesks(doc);
    const without = Array.isArray(doc.desks_without_brief) ? doc.desks_without_brief : [];
    const generated = doc.generated_at ? `Built ${esc(String(doc.generated_at).slice(0, 16).replace('T', ' '))}Z` : 'Not built yet';
    const body = all.length
      ? (shown.length ? shown.map((entry) => cardHtml(entry, doc)).join('') : '<div class="desk-briefs-empty">No brief matches these filters.</div>')
      : `<div class="desk-briefs-empty"><strong>No desk briefs filed yet.</strong> A desk bot files <code>_system/data/desk_briefs/&lt;desk&gt;/&lt;YYYY-MM-DD&gt;.json</code> by pull request; the check and the builder put it here.${doc.error ? ` <span class="muted">(${esc(doc.error)})</span>` : ''}</div>`;
    const missing = all.length && without.length
      ? `<div class="desk-brief-foot desk-briefs-missing"><strong>No brief yet.</strong> ${esc(without.map((id) => deskLabel(doc, id)).join(', '))}</div>`
      : '';
    return `<section class="desk-briefs" data-desk-briefs aria-label="Desk briefs">
      <div class="ideas-surface-head desk-briefs-head"><div><strong>Desk briefs</strong> <span>${esc(doc.caption || 'Ranked output from the Magis desk bots. Research only.')}</span></div><span class="ideas-asof">${generated}</span></div>
      <div class="desk-briefs-body">
        ${all.length ? chips(doc) : ''}
        ${healthHtml(doc)}
        ${body}
        ${missing}
      </div>
    </section>`;
  }

  function attach(container, payload, hooks) {
    const refresh = () => {
      if (hooks && hooks.onChange) hooks.onChange();
    };
    container.querySelectorAll('[data-desk-brief-owner]').forEach((button) => {
      button.addEventListener('click', () => {
        state.owner = button.dataset.deskBriefOwner;
        if (hooks && hooks.onFilter) hooks.onFilter({ owner: state.owner, desk: state.desk });
        refresh();
      });
    });
    container.querySelectorAll('[data-desk-brief-desk]').forEach((button) => {
      button.addEventListener('click', () => {
        state.desk = button.dataset.deskBriefDesk;
        if (hooks && hooks.onFilter) hooks.onFilter({ owner: state.owner, desk: state.desk });
        refresh();
      });
    });
  }

  global.DeskBriefsViz = { render, attach };
})(window);
