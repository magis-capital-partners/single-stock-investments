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
    if (!b || (b.grade == null && b.retired_since_peak_pct == null && b.buyback_yield_pct == null && !b.pace && !b.non_operating)) {
      return '<td><span style="color:var(--text-muted)">—</span></td>';
    }
    if (b.non_operating) {
      const title = 'Fund, ETF, or other non-operating instrument. Creation units are not dilution, so pace and grade are blank.';
      return `<td class="buyback-cell" title="${escapeHtml(title)}"><span class="badge">Fund</span><div class="irr-sub">not dilution</div></td>`;
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
    const yieldText = b.buyback_yield_pct == null
      ? '—'
      : pct(b.buyback_yield_pct, 2) + ' of market value' + (b.repurchase_tag ? `, tag ${b.repurchase_tag}` : '');
    const cells = [
      ['Retired since peak', b.retired_since_peak_pct == null ? '—' : pct(b.retired_since_peak_pct, 1)],
      ['Buyback yield', yieldText],
      ['Pace', b.non_operating ? 'blank (creation units)' : paceLabel(b.pace)],
      ['Grade', b.non_operating ? 'blank (creation units)' : (b.grade || '—')],
      ['Five-year share change', b.change_5y_pct == null ? '—' : pct(b.change_5y_pct, 1)],
      ['One-year share change', b.change_1y_pct == null ? '—' : pct(b.change_1y_pct, 1)],
    ];
    const summary = b.non_operating ? 'Fund' : (b.grade || 'ungraded');
    return `<details class="detail-section" open><summary>Buyback · ${escapeHtml(summary)}${b.as_of ? ` · shares ${escapeHtml(b.as_of)}` : ''}</summary>
      <div class="research-box" style="margin-top:10px">
        <div class="hr-line">Share count retired since the peak fiscal year, the last year's repurchase cash as a percent of market value, the pace versus this company's own five-year pace, and an A–E grade. The yield is not a return per year.</div>
        ${b.non_operating ? '<div class="hr-line">This is a fund, ETF, or other non-operating instrument. Creation and redemption of units are not dilution, so pace and grade are blank.</div>' : ''}
        ${b.split_review ? '<div class="hr-line">Split review: a one-year share-count jump was not a listed split. Read the series before treating the retired percent as a buyback.</div>' : ''}
        ${cells.map(([label, value]) => `<div class="hr-line"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</div>`).join('')}
      </div>
    </details>`;
  }

  window.BuybackViz = { renderHoldingsCell, renderDetail };
})();
