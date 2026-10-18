// Buyback vector on the holdings table and the ticker page.
// Yield is a percent of market value, not a return per year.
(function () {
  function pct(value, digits) {
    if (value == null || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return n.toFixed(digits == null ? 1 : digits) + '%';
  }

  function paceLabel(pace) {
    if (!pace) return '—';
    return String(pace).replace(/_/g, ' ');
  }

  function renderHoldingsCell(row, escapeHtml) {
    const b = row && row.buyback;
    if (!b || (b.grade == null && b.retired_since_peak_pct == null && b.buyback_yield_pct == null && !b.pace)) {
      return '<td><span style="color:var(--text-muted)">—</span></td>';
    }
    const grade = b.grade || '—';
    const retired = b.retired_since_peak_pct == null ? '—' : pct(b.retired_since_peak_pct, 0) + ' retired';
    const yld = b.buyback_yield_pct == null ? '—' : pct(b.buyback_yield_pct, 1) + ' yield';
    const pace = paceLabel(b.pace);
    const title = `Grade ${grade}. Retired since peak ${retired}. Buyback yield ${yld} of market value. Not a return per year. Pace ${pace}.`;
    return `<td class="buyback-cell" title="${escapeHtml(title)}"><span class="badge">${escapeHtml(grade)}</span> <span class="mono" style="font-size:11px">${escapeHtml(retired)}</span><div class="irr-sub">${escapeHtml(pace)} · ${escapeHtml(yld)}</div></td>`;
  }

  function renderDetail(row, escapeHtml) {
    const b = row && row.buyback;
    if (!b) return '';
    const cells = [
      ['Retired since peak', b.retired_since_peak_pct == null ? '—' : pct(b.retired_since_peak_pct, 1)],
      ['Buyback yield', b.buyback_yield_pct == null ? '—' : pct(b.buyback_yield_pct, 2) + ' of market value'],
      ['Pace', paceLabel(b.pace)],
      ['Grade', b.grade || '—'],
      ['Five-year share change', b.change_5y_pct == null ? '—' : pct(b.change_5y_pct, 1)],
      ['One-year share change', b.change_1y_pct == null ? '—' : pct(b.change_1y_pct, 1)],
    ];
    return `<details class="detail-section" open><summary>Buyback · ${escapeHtml(b.grade || 'ungraded')}${b.as_of ? ` · shares ${escapeHtml(b.as_of)}` : ''}</summary>
      <div class="research-box" style="margin-top:10px">
        <div class="hr-line">Share count retired since the peak fiscal year, the last year's repurchase cash as a percent of market value, the pace versus this company's own five-year pace, and an A–E grade. The yield is not a return per year.</div>
        ${b.split_review ? '<div class="hr-line">Split review: a one-year share-count jump was not a listed split. Read the series before treating the retired percent as a buyback.</div>' : ''}
        ${cells.map(([label, value]) => `<div class="hr-line"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</div>`).join('')}
      </div>
    </details>`;
  }

  window.BuybackViz = { renderHoldingsCell, renderDetail };
})();
