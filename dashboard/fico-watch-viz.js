/* FICO fundamentals watch. The payload decides the verdict. This file only paints it. */
(function () {
  function esc(escapeHtml, value) {
    const text = value == null ? '' : String(value);
    return escapeHtml ? escapeHtml(text) : text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toneClass(tone) {
    if (tone === 'pass') return 'pass';
    if (tone === 'watch') return 'watch';
    return 'fail';
  }

  function rowHtml(row, escapeHtml) {
    const status = row.status || 'context';
    return `
      <div class="fico-row fico-row-${esc(escapeHtml, status)}">
        <div>
          <div class="fico-label">${esc(escapeHtml, row.label)}</div>
          <div class="fico-note">${esc(escapeHtml, row.note)}</div>
        </div>
        <div class="fico-value">${esc(escapeHtml, row.display)}</div>
        <div class="fico-pill fico-pill-${esc(escapeHtml, status)}">${esc(escapeHtml, row.pill || status)}</div>
      </div>`;
  }

  function renderDetail(payload, escapeHtml) {
    if (!payload || !payload.verdict) {
      return `
        <section class="fico-watch fico-watch-fail">
          <p class="fico-kicker">FICO watch</p>
          <h3>The FICO watch file is missing</h3>
          <p class="fico-detail">Do not treat this name as monitored. The nightly build did not leave dashboard/data/fico_watch.json.</p>
        </section>`;
    }
    const tone = toneClass(payload.verdict.tone);
    const groups = (payload.groups || []).map((group) => `
      <section class="fico-group">
        <h4>${esc(escapeHtml, group.label)}</h4>
        ${(group.rows || []).map((row) => rowHtml(row, escapeHtml)).join('')}
      </section>`).join('');
    const freshness = payload.freshness ? payload.freshness.detail : '';
    return `
      <section class="fico-watch fico-watch-${tone}">
        <p class="fico-kicker">FICO watch · fundamentals</p>
        <h3>${esc(escapeHtml, payload.verdict.title)}</h3>
        <p class="fico-detail">${esc(escapeHtml, payload.verdict.detail)}</p>
        ${groups}
        <p class="fico-trust">${esc(escapeHtml, payload.trust)}</p>
        <p class="fico-trust">${esc(escapeHtml, freshness)}</p>
      </section>`;
  }

  function mountBanner(payload) {
    const el = document.getElementById('fico-watch-banner');
    if (!el) return;
    el.hidden = false;
    if (!payload || !payload.banner) {
      el.className = 'fico-banner fico-banner-fail';
      el.innerHTML = `
        <div>
          <strong>FICO watch is not loaded</strong>
          <p>Do not treat Fair Isaac as monitored until dashboard/data/fico_watch.json is on this page.</p>
        </div>`;
      return;
    }
    const tone = toneClass(payload.banner.tone);
    const detail = payload.verdict && payload.verdict.detail ? payload.verdict.detail : '';
    el.className = 'fico-banner fico-banner-' + tone;
    el.innerHTML = `
      <div>
        <strong>${esc(null, payload.banner.text)}</strong>
        <p>${esc(null, detail)}</p>
      </div>
      <button type="button" class="fico-open" data-fico-open>${esc(null, payload.banner.action || 'Open FICO')}</button>`;
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-fico-open]');
    if (!button || typeof selectTicker !== 'function') return;
    if (typeof setView === 'function') setView('holdings', { syncHash: false });
    selectTicker('FICO');
  });

  window.FicoWatch = { renderDetail, mountBanner };
})();
