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
    add: 'badge-ok',
    discussed: 'badge-us',
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

  function evidenceLink(ref, linkHtml, ghRepo) {
    if (!ref) return '—';
    if (ref.startsWith('http')) return linkHtml(ref, 'Open');
    return linkHtml(`https://github.com/${ghRepo}/blob/main/${ref}`, 'Extract');
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
      classification.investment_sleeve_label && classification.investment_sleeve_label !== '—'
        ? classification.investment_sleeve_label
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

  function renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo) {
    if (!discussants?.length) return '';
    return `
      <div class="detail-section tier-3">
        <h3>Who discusses this</h3>
        <ul class="context-list">
          ${discussants.slice(0, 8).map(d => {
            const action = d.action || 'discussed';
            const badge = STANCE_BADGE[action] || 'badge-us';
            const snippet = escapeHtml((d.commentary || '').slice(0, 200));
            const link = d.source_file
              ? ` · ${linkHtml(`https://github.com/${ghRepo}/blob/main/${d.source_file}`, 'letter')}`
              : '';
            return `<li>
              <span class="badge ${badge}">${escapeHtml(action)}</span>
              <strong>${escapeHtml(d.fund)}</strong>
              <span class="tier-sub">${escapeHtml(d.quarter || '')} · ${escapeHtml(d.letter_date || '')}</span>
              ${snippet ? `<div style="font-size:12px;margin-top:4px;color:var(--text-secondary)">"${snippet}"</div>` : ''}
              ${link}
            </li>`;
          }).join('')}
        </ul>
      </div>`;
  }

  function renderExternalContext(insights, filter, escapeHtml, linkHtml, discussants, ghRepo) {
    const letterBlock = discussants?.length
      ? renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo)
      : '';
    const rows = filterInsights(insights, filter).slice(0, 6);
    const pills = [
      { id: 'letters', label: 'Letters' },
      { id: 'macro', label: 'Macro' },
      { id: 'insider', label: 'Insider' },
      { id: 'all', label: 'All' },
    ];
    const otherBlock = `
      <div class="detail-section tier-3${letterBlock ? '' : ''}">
        <h3>External context</h3>
        <nav class="source-pills">
          ${pills.map(p => `<button type="button" class="filter-btn source-pill${filter === p.id ? ' active' : ''}" data-insight-filter="${p.id}">${p.label}</button>`).join('')}
        </nav>
        ${rows.length ? `<ul class="context-list">
          ${rows.map(r => {
            const src = SOURCE_LABEL[r.source] || r.source;
            const fund = r.fund ? `${escapeHtml(r.fund)} · ` : '';
            const ref = r.ref ? `${escapeHtml(r.ref)} · ` : '';
            const claim = escapeHtml((r.claim || '').slice(0, 160));
            const link = r.evidence_url
              ? ` · ${linkHtml(r.evidence_url, '↗ extract')}`
              : '';
            const action = r.action ? `<span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action)}</span> ` : '';
            return `<li><span class="badge badge-us context-src">${escapeHtml(src)}</span> ${action}${fund}${ref}"${claim}"${link}</li>`;
          }).join('')}
        </ul>` : '<p class="tier-sub">No matching context for this filter.</p>'}
      </div>`;
    return letterBlock + (filter === 'letters' && letterBlock ? '' : otherBlock);
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

  function renderThemeRankings(themes, escapeHtml) {
    if (!themes?.length) {
      return '<p class="subhead">No superinvestor letter themes yet — run make persona-fetch-letters</p>';
    }
    return `
      <table class="darwin-table" id="insights-theme-table">
        <thead><tr><th>Theme</th><th>Letters</th><th>Bull</th><th>Bear</th><th>Neutral</th><th>Top tickers</th></tr></thead>
        <tbody>
          ${themes.map(t => `
            <tr>
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

  function renderLetterIndex(rows, escapeHtml, linkHtml, ghRepo, onFundClick) {
    if (!rows?.length) {
      return '<p class="subhead">No letters indexed yet.</p>';
    }
    return `
      <table class="darwin-table" id="insights-letter-table">
        <thead><tr><th>Date</th><th>Fund</th><th>Quarter</th><th>Themes</th><th>Tickers</th><th>Our overlap</th><th>Summary</th></tr></thead>
        <tbody>
          ${rows.slice(0, 80).map(r => `
            <tr class="clickable-row" data-fund-id="${escapeHtml(r.fund_id || '')}">
              <td class="mono">${escapeHtml(r.letter_date || '—')}</td>
              <td>${onFundClick ? `<button type="button" class="linkish" data-fund-id="${escapeHtml(r.fund_id || '')}">${escapeHtml(r.fund)}</button>` : escapeHtml(r.fund)}</td>
              <td class="mono">${escapeHtml(r.quarter || '—')}</td>
              <td style="font-size:11px">${(r.themes || []).slice(0, 4).join(', ') || '—'}</td>
              <td class="mono" style="font-size:11px">${(r.tickers || []).slice(0, 5).join(', ') || '—'}</td>
              <td class="mono" style="font-size:11px;color:var(--accent-cyan)">${(r.our_overlap || []).join(', ') || '—'}</td>
              <td style="font-size:11px;max-width:240px">${escapeHtml((r.lead_summary || '').slice(0, 120))}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      ${rows.length > 80 ? `<p class="tier-sub">${rows.length - 80} more letters — use fund search</p>` : ''}`;
  }

  function renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo, bookOnly) {
    if (!funds?.length) {
      return '<p class="subhead">No fund letter registry yet.</p>';
    }
    let list = funds;
    if (bookOnly) {
      list = list.filter(f => (f.our_ticker_count || 0) > 0);
    }
    return `
      <table class="darwin-table" id="insights-fund-table">
        <thead><tr><th>Fund</th><th>Quarter</th><th>In our book</th><th>Themes</th><th>Personas</th><th></th></tr></thead>
        <tbody>
          ${list.slice(0, 60).map(f => `
            <tr class="clickable-row" data-fund-id="${escapeHtml(f.fund_id || '')}">
              <td>
                <button type="button" class="linkish" data-fund-id="${escapeHtml(f.fund_id || '')}">${escapeHtml(f.fund)}</button>
                ${f.manager ? `<div class="tier-sub">${escapeHtml(f.manager)}</div>` : ''}
              </td>
              <td class="mono">${escapeHtml(f.quarter || '—')}</td>
              <td class="mono">${(f.our_tickers || []).join(', ') || '—'}</td>
              <td style="font-size:11px">${(f.themes || []).slice(0, 4).join(', ') || '—'}</td>
              <td style="font-size:11px">${(f.maps_to_persona || []).join(', ') || '—'}</td>
              <td>${evidenceLink(f.evidence_ref, linkHtml, ghRepo)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      ${list.length > 60 ? `<p class="tier-sub">${list.length - 60} more — refine search</p>` : ''}
      ${bookOnly && !list.length ? '<p class="subhead">No funds with overlap to your holdings this quarter.</p>' : ''}`;
  }

  function renderFundDetail(profile, escapeHtml, linkHtml, ghRepo) {
    if (!profile) return '';
    const latest = (profile.letters || [])[0] || {};
    const themes = (latest.themes || []).map(t =>
      `<span class="badge badge-us">${escapeHtml(t.theme)}</span> ${escapeHtml(t.stance || '')}`
    ).join(' · ');
    const positions = (latest.positions || []).slice(0, 15);
    const risks = latest.risks || [];
    const catalysts = latest.catalysts || [];
    return `
      <div class="detail-section fund-detail">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <button type="button" class="filter-btn" data-insights-back>← Back</button>
          <h3 style="margin:0">${escapeHtml(profile.fund)}</h3>
        </div>
        ${profile.manager ? `<p class="tier-sub">Manager: ${escapeHtml(profile.manager)}</p>` : ''}
        ${(profile.maps_to_persona || []).length ? `<p class="tier-sub">Persona map: ${profile.maps_to_persona.map(p => escapeHtml(p)).join(', ')}</p>` : ''}
        ${(profile.our_tickers || []).length ? `<p class="tier-sub">Discusses our book: <span class="mono">${profile.our_tickers.join(', ')}</span></p>` : ''}
        ${latest.lead_summary ? `<p style="font-size:13px;line-height:1.5;margin:10px 0">${escapeHtml(latest.lead_summary)}</p>` : ''}
        ${themes ? `<div style="margin:8px 0"><strong>Themes:</strong> ${themes}</div>` : ''}
        ${risks.length ? `<div style="margin:8px 0"><strong>Risks:</strong><ul class="dev-list">${risks.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul></div>` : ''}
        ${catalysts.length ? `<div style="margin:8px 0"><strong>Catalysts:</strong><ul class="dev-list">${catalysts.map(c => `<li>${escapeHtml(c)}</li>`).join('')}</ul></div>` : ''}
        ${positions.length ? `
        <h4 style="margin-top:14px;font-size:12px;color:var(--text-muted)">TICKER COMMENTARY</h4>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Action</th><th>Commentary</th></tr></thead>
          <tbody>
            ${positions.map(p => `
              <tr>
                <td class="mono">${escapeHtml(p.ticker)}</td>
                <td><span class="badge ${STANCE_BADGE[p.action] || 'badge-us'}">${escapeHtml(p.action || '—')}</span></td>
                <td style="font-size:12px">${escapeHtml((p.commentary || p.thesis || '').slice(0, 220))}</td>
              </tr>`).join('')}
          </tbody>
        </table>` : ''}
        <p class="tier-sub" style="margin-top:10px">
          ${(profile.letters || []).length} letter(s) · latest ${escapeHtml(latest.quarter || '—')} · ${evidenceLink(latest.source_file, linkHtml, ghRepo)}
        </p>
      </div>`;
  }

  function filterLetterIndex(rows, opts) {
    const { quarter, search, bookOnly } = opts || {};
    let list = rows || [];
    if (quarter && quarter !== 'all') {
      list = list.filter(r => r.quarter === quarter);
    }
    if (bookOnly) {
      list = list.filter(r => (r.our_overlap || []).length > 0);
    }
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(r =>
        (r.fund || '').toLowerCase().includes(q)
        || (r.tickers || []).some(t => t.toLowerCase().includes(q))
        || (r.our_overlap || []).some(t => t.toLowerCase().includes(q))
        || (r.themes || []).some(t => t.toLowerCase().includes(q))
      );
    }
    return list;
  }

  function renderInsightsPanel(insights, options) {
    const {
      escapeHtml,
      linkHtml,
      ghRepo = 'GoldmanDrew/single-stock-investments',
      quarter = 'all',
      fundSearch = '',
      bookOnly = false,
      selectedFundId = null,
      activeSection = 'themes',
    } = options || {};

    const profiles = insights?.fund_profiles || {};
    if (selectedFundId && profiles[selectedFundId]) {
      return renderFundDetail(profiles[selectedFundId], escapeHtml, linkHtml, ghRepo);
    }

    const byQ = insights?.theme_rankings_by_quarter || {};
    const quarters = Object.keys(byQ).filter(q => q !== 'all').sort().reverse();
    const themes = byQ[quarter] || insights?.theme_rankings || [];
    let funds = insights?.fund_registry || [];
    let letters = filterLetterIndex(insights?.letter_index || [], { quarter, search: fundSearch, bookOnly });

    if (fundSearch) {
      const q = fundSearch.toLowerCase();
      funds = funds.filter(f =>
        (f.fund || '').toLowerCase().includes(q)
        || (f.our_tickers || []).some(t => t.toLowerCase().includes(q))
        || (f.themes || []).some(t => t.toLowerCase().includes(q))
      );
    }
    if (bookOnly) {
      funds = funds.filter(f => (f.our_ticker_count || 0) > 0);
    }
    if (quarter && quarter !== 'all') {
      funds = funds.filter(f => f.quarter === quarter);
    }

    const qTabs = [{ id: 'all', label: 'All' }, ...quarters.map(q => ({ id: q, label: q }))];
    const sections = [
      { id: 'themes', label: 'Themes' },
      { id: 'letters', label: 'Letter index' },
      { id: 'funds', label: 'Funds' },
    ];

    let body = '';
    if (activeSection === 'themes') {
      body = renderThemeRankings(themes, escapeHtml);
    } else if (activeSection === 'letters') {
      body = renderLetterIndex(letters, escapeHtml, linkHtml, ghRepo, true);
    } else {
      body = renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo, false);
    }

    return `
      <h2 style="font-size:18px;margin-bottom:6px">Insights</h2>
      <p class="subhead" style="margin-bottom:14px">
        Portfolio context only · ${insights?.letter_count || 0} letters · ${insights?.record_count || 0} records · never in house IRR
      </p>
      <nav class="view-tabs" id="insights-section-tabs" style="margin-bottom:10px">
        ${sections.map(s => `<button type="button" class="view-tab${activeSection === s.id ? ' active' : ''}" data-insights-section="${s.id}">${s.label}</button>`).join('')}
      </nav>
      <div class="detail-section" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px">
        <nav class="view-tabs" id="insights-quarter-tabs">
          ${qTabs.map(t => `<button type="button" class="view-tab${quarter === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <label class="tier-sub" style="display:flex;align-items:center;gap:6px">
          <input type="checkbox" id="insights-book-only" ${bookOnly ? 'checked' : ''} />
          In our book only
        </label>
        <input class="search" id="fund-registry-search" placeholder="Search fund, ticker, theme…" value="${escapeHtml(fundSearch)}" style="max-width:280px" />
      </div>
      ${body}`;
  }

  global.InsightsViz = {
    renderDecisionSummary,
    renderIdentityLine,
    renderActiveLensChips,
    renderExternalContext,
    renderConsensusDetail,
    renderInsightsPanel,
    renderLetterDiscussants,
    filterInsights,
    STANCE_BADGE,
  };
})(window);
