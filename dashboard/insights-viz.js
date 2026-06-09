/** Insights tab + persona lens detail rendering for portfolio dashboard. */
(function (global) {
  const STANCE_BADGE = {
    accumulate: 'badge-ok',
    core: 'badge-ok',
    hold: 'badge-us',
    watch: 'badge-warn',
    pass: 'badge-bad',
    trim: 'badge-bad',
    exit: 'badge-bad',
    pending: 'badge-warn',
    silent: 'badge-warn',
  };

  const SOURCE_LABEL = {
    superinvestor_letter: 'letter',
    macro: 'macro',
    insider: 'insider',
    third_party: 'third_party',
    theme: 'theme',
    news: 'news',
  };

  function fmtPct(v, digits) {
    if (v == null || Number.isNaN(v)) return '—';
    const d = digits != null ? digits : (Math.abs(v % 1) > 0.01 ? 1 : 0);
    return `${Number(v).toFixed(d)}%`;
  }

  function renderDecisionSummary(ds, humanReview, helpers) {
    if (!ds) return '';
    const { escapeHtml, renderIrrCell, classification } = helpers;
    const stanceBadge = STANCE_BADGE[ds.stance] || 'badge-warn';
    let stanceHtml = `<span class="badge ${stanceBadge}">${escapeHtml(ds.stance || '—')}</span>`;
    if (ds.stance_source === 'approved' && ds.lens_stance && ds.lens_stance !== ds.stance) {
      stanceHtml += `<div class="tier-sub">lens: ${escapeHtml(ds.lens_stance)}</div>`;
    } else if (humanReview?.approved_stance) {
      stanceHtml += `<div class="tier-sub">approved</div>`;
    }
    const band = ds.lens_band_pct;
    const blendStr = ds.lens_blend_pct != null
      ? `${fmtPct(ds.lens_blend_pct)}${band ? ` [${fmtPct(band[0])}–${fmtPct(band[1])}]` : ''}`
      : '—';
    const dissent = ds.top_dissent;
    const dissentStr = dissent
      ? `${escapeHtml(dissent.label || dissent.persona)} ${escapeHtml(dissent.verdict || '')}`
      : '—';
    const houseWarn = ds.divergence ? ' <span class="divergence-flag" title="House IRR diverges from lens blend">⚠</span>' : '';
    const houseHtml = classification
      ? renderIrrCell({ classification }) + houseWarn
      : fmtPct(ds.house_irr_pct) + houseWarn;
    return `
      <div class="detail-section tier-0">
        <div class="metric-grid metric-grid-3">
          <div class="metric"><div class="k">Stance</div><div class="v">${stanceHtml}</div></div>
          <div class="metric"><div class="k">House IRR</div><div class="v">${houseHtml}</div></div>
          <div class="metric"><div class="k">Lens blend</div><div class="v mono">${blendStr}</div></div>
          <div class="metric"><div class="k">Agreement</div><div class="v">${ds.agreement_pct != null ? ds.agreement_pct + '%' : '—'}</div></div>
          <div class="metric"><div class="k">Dissent</div><div class="v" style="font-size:12px">${dissentStr}</div></div>
          <div class="metric"><div class="k">As of</div><div class="v mono">${escapeHtml(ds.as_of || '—')}</div></div>
        </div>
      </div>`;
  }

  function renderIdentityLine(classification, escapeHtml) {
    if (!classification) return '';
    const parts = [
      classification.archetype,
      classification.moat ? `moat ${classification.moat}` : null,
      classification.dhando ? `dhando ${classification.dhando}` : null,
      classification.lawrence_bucket && classification.lawrence_bucket !== '—'
        ? `${classification.lawrence_bucket} lens`
        : null,
      classification.cycle && classification.cycle !== '-' && classification.cycle !== '—'
        ? `cycle ${classification.cycle}`
        : null,
    ].filter(Boolean);
    if (!parts.length) return '';
    return `
      <div class="detail-section tier-1">
        <div class="identity-line">${parts.map(p => escapeHtml(p)).join(' · ')}</div>
      </div>`;
  }

  function renderActiveLensChips(activeLenses, silentCount, expandedPersona, lenses, escapeHtml) {
    if (!activeLenses?.length && !silentCount) return '';
    const chips = (activeLenses || []).map(l => {
      const short = (l.label || l.persona || '').split(' ')[0];
      const active = expandedPersona === l.persona ? ' lens-chip-active' : '';
      return `<button type="button" class="lens-chip${active}" data-lens-persona="${escapeHtml(l.persona)}">${escapeHtml(short)} ${escapeHtml(l.verdict)} ${l.return_pct != null ? fmtPct(l.return_pct) : ''}</button>`;
    }).join('');
    const silent = silentCount > 0
      ? `<span class="lens-chip-silent">+${silentCount} silent</span>`
      : '';
    let expand = '';
    if (expandedPersona && lenses?.personas) {
      const p = lenses.personas.find(x => x.persona === expandedPersona)
        || (activeLenses || []).find(x => x.persona === expandedPersona);
      if (p) {
        expand = `
          <div class="lens-expand">
            <div class="metric-grid" style="margin-top:8px">
              <div class="metric"><div class="k">Verdict</div><div class="v"><span class="badge ${STANCE_BADGE[p.verdict] || 'badge-warn'}">${escapeHtml(p.verdict)}</span></div></div>
              <div class="metric"><div class="k">Return</div><div class="v">${p.return_pct != null ? fmtPct(p.return_pct) : '—'}</div></div>
              <div class="metric"><div class="k">Relevance</div><div class="v">${p.relevance != null ? p.relevance : '—'}</div></div>
              <div class="metric"><div class="k">Horizon</div><div class="v">${p.horizon_yrs || '—'} yr</div></div>
            </div>
            ${(p.key_metrics || []).length ? `<ul class="dev-list" style="margin-top:8px">${p.key_metrics.map(m => `<li><span class="mono">${escapeHtml(m.name)}</span>: ${escapeHtml(String(m.value ?? '—'))}</li>`).join('')}</ul>` : ''}
            ${p.falsifier ? `<p class="tier-sub" style="margin-top:6px">Falsifier: ${escapeHtml(p.falsifier)}</p>` : ''}
          </div>`;
      }
    }
    return `
      <div class="detail-section tier-2">
        <h3>Active lenses</h3>
        <div class="lens-chips">${chips}${silent}</div>
        ${expand}
      </div>`;
  }

  function filterInsights(insights, filter) {
    if (!insights?.length) return [];
    if (!filter || filter === 'all') return insights;
    const map = {
      letters: 'superinvestor_letter',
      macro: 'macro',
      insider: 'insider',
      third_party: 'third_party',
    };
    const src = map[filter] || filter;
    return insights.filter(r => r.source === src);
  }

  function renderExternalContext(insights, filter, escapeHtml, linkHtml) {
    const rows = filterInsights(insights, filter).slice(0, 3);
    const pills = [
      { id: 'letters', label: 'Letters' },
      { id: 'macro', label: 'Macro' },
      { id: 'insider', label: 'Insider' },
      { id: 'all', label: 'All' },
    ];
    return `
      <div class="detail-section tier-3">
        <h3>External context</h3>
        <nav class="source-pills">
          ${pills.map(p => `<button type="button" class="filter-btn source-pill${filter === p.id ? ' active' : ''}" data-insight-filter="${p.id}">${p.label}</button>`).join('')}
        </nav>
        ${rows.length ? `<ul class="context-list">
          ${rows.map(r => {
            const src = SOURCE_LABEL[r.source] || r.source;
            const fund = r.fund ? `${escapeHtml(r.fund)} · ` : '';
            const ref = r.ref ? `${escapeHtml(r.ref)} · ` : '';
            const claim = escapeHtml((r.claim || '').slice(0, 120));
            const link = r.evidence_url
              ? ` · ${linkHtml(r.evidence_url, '↗ extract')}`
              : '';
            return `<li><span class="badge badge-us context-src">${escapeHtml(src)}</span> ${fund}${ref}"${claim}"${link}</li>`;
          }).join('')}
        </ul>` : '<p class="tier-sub">No matching context for this filter.</p>'}
      </div>`;
  }

  function renderConsensusDetail(lenses, escapeHtml) {
    if (!lenses?.valuation_blend) return '';
    const blend = lenses.valuation_blend;
    const cons = lenses.consensus || {};
    const contributors = (blend.contributors || []).slice(0, 8);
    return `
      <details class="detail-section tier-4">
        <summary>Persona consensus detail</summary>
        <div class="metric-grid" style="margin-top:10px">
          <div class="metric"><div class="k">Blend</div><div class="v">${blend.blended_return_pct != null ? fmtPct(blend.blended_return_pct) : '—'}</div></div>
          <div class="metric"><div class="k">Band</div><div class="v">${blend.band_pct ? blend.band_pct.map(fmtPct).join('–') : '—'}</div></div>
          <div class="metric"><div class="k">Stance</div><div class="v"><span class="badge ${STANCE_BADGE[cons.stance] || 'badge-warn'}">${escapeHtml(cons.stance || '—')}</span></div></div>
        </div>
        ${contributors.length ? `
        <table class="darwin-table" style="margin-top:10px">
          <thead><tr><th>Persona</th><th>Return</th><th>Verdict</th><th>Rel</th></tr></thead>
          <tbody>
            ${contributors.map(c => `
              <tr>
                <td>${escapeHtml((c.label || c.persona || '').split('/')[0])}</td>
                <td class="mono">${c.return_pct != null ? fmtPct(c.return_pct) : '—'}</td>
                <td>${escapeHtml(c.verdict || '—')}</td>
                <td class="mono">${c.relevance != null ? c.relevance : '—'}</td>
              </tr>`).join('')}
          </tbody>
        </table>` : ''}
        ${(cons.dissents || []).length ? `<p class="tier-sub" style="margin-top:8px"><strong>Dissents:</strong> ${cons.dissents.map(d => escapeHtml(`${d.persona}: ${d.verdict}`)).join(' · ')}</p>` : ''}
      </details>`;
  }

  function renderThemeRankings(themes, escapeHtml, onThemeClick) {
    if (!themes?.length) {
      return '<p class="subhead">No superinvestor letter themes yet — run make persona-fetch-letters</p>';
    }
    return `
      <table class="darwin-table" id="insights-theme-table">
        <thead><tr><th>Theme</th><th>Letters</th><th>Bull</th><th>Bear</th><th>Neutral</th><th>Top tickers</th></tr></thead>
        <tbody>
          ${themes.map(t => `
            <tr${onThemeClick ? ` class="clickable-row" data-theme="${escapeHtml(t.theme)}"` : ''}>
              <td>${escapeHtml(t.theme)}</td>
              <td class="mono">${t.letter_count ?? t.fund_count ?? 0}</td>
              <td>${t.bullish || 0}</td>
              <td>${t.bearish || 0}</td>
              <td>${t.neutral || 0}</td>
              <td class="mono" style="font-size:11px">${(t.top_tickers || []).slice(0, 6).join(', ') || '—'}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  function renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo) {
    if (!funds?.length) {
      return '<p class="subhead">No fund letter registry yet.</p>';
    }
    const blob = (ref) => {
      if (!ref) return '—';
      if (ref.startsWith('http')) return linkHtml(ref, 'Open');
      return linkHtml(`https://github.com/${ghRepo}/blob/main/${ref}`, 'Extract');
    };
    return `
      <table class="darwin-table" id="insights-fund-table">
        <thead><tr><th>Fund</th><th>Quarter</th><th>In our book</th><th>Sample claim</th><th>Extract</th></tr></thead>
        <tbody>
          ${funds.slice(0, 50).map(f => `
            <tr>
              <td>${escapeHtml(f.fund)}</td>
              <td class="mono">${escapeHtml(f.quarter || '—')}</td>
              <td class="mono">${(f.our_tickers || []).join(', ') || '—'}</td>
              <td style="font-size:12px;max-width:280px">${escapeHtml((f.sample_claim || '').slice(0, 100))}</td>
              <td>${blob(f.evidence_ref)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      ${funds.length > 50 ? `<p class="tier-sub">${funds.length - 50} more funds — refine search in a future pass</p>` : ''}`;
  }

  function renderInsightsPanel(insights, options) {
    const {
      escapeHtml,
      linkHtml,
      ghRepo = 'GoldmanDrew/single-stock-investments',
      quarter = 'all',
      fundSearch = '',
    } = options || {};
    const byQ = insights?.theme_rankings_by_quarter || {};
    const quarters = Object.keys(byQ).filter(q => q !== 'all').sort().reverse();
    const themes = byQ[quarter] || insights?.theme_rankings || [];
    let funds = insights?.fund_registry || [];
    if (fundSearch) {
      const q = fundSearch.toLowerCase();
      funds = funds.filter(f =>
        (f.fund || '').toLowerCase().includes(q)
        || (f.our_tickers || []).some(t => t.toLowerCase().includes(q))
      );
    }
    const qTabs = [{ id: 'all', label: 'All' }, ...quarters.map(q => ({ id: q, label: q }))];
    return `
      <h2 style="font-size:18px;margin-bottom:6px">Insights</h2>
      <p class="subhead" style="margin-bottom:14px">
        Portfolio context only · ${insights?.record_count || 0} records · letters never in house IRR
      </p>
      <div class="detail-section">
        <h3>Letter themes</h3>
        <nav class="view-tabs" id="insights-quarter-tabs" style="margin-bottom:10px">
          ${qTabs.map(t => `<button type="button" class="view-tab${quarter === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        ${renderThemeRankings(themes, escapeHtml)}
      </div>
      <details class="detail-section" open>
        <summary><h3 style="display:inline">Fund registry</h3></summary>
        <input class="search" id="fund-registry-search" placeholder="Search fund or ticker…" value="${escapeHtml(fundSearch)}" style="margin:10px 0;max-width:320px" />
        ${renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo)}
      </details>`;
  }

  global.InsightsViz = {
    renderDecisionSummary,
    renderIdentityLine,
    renderActiveLensChips,
    renderExternalContext,
    renderConsensusDetail,
    renderInsightsPanel,
    filterInsights,
    STANCE_BADGE,
  };
})(window);
