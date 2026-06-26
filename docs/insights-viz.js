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
    superinvestor_letter: 'Letter',
    filing: 'Filing',
    earnings: 'Earnings',
    macro: 'Macro',
    insider: 'Insider',
    sumzero_research: 'SumZero',
    third_party: 'Research',
    company_document: 'Company',
    pdf: 'PDF',
    theme: 'Theme',
    news: 'News',
  };

  const AXIS_LABEL = {
    fundamentals: 'fundamentals',
    ownership: 'ownership',
    catalyst: 'catalyst',
    risk: 'risk',
    macro: 'macro',
    capital_allocation: 'capital allocation',
    variant_view: 'variant view',
    context: 'context',
  };

  function fmtPct(v, digits) {
    if (v == null || Number.isNaN(v)) return '—';
    const d = digits != null ? digits : (Math.abs(v % 1) > 0.01 ? 1 : 0);
    return `${Number(v).toFixed(d)}%`;
  }

  function evidenceLabel(ref, fallback) {
    if (fallback) return fallback;
    const clean = (ref || '').split('#')[0].toLowerCase();
    if (clean.endsWith('.pdf')) return 'PDF';
    if (clean.endsWith('.htm') || clean.endsWith('.html')) return 'HTML';
    if (clean.startsWith('http')) return 'Open';
    if (clean.endsWith('.json')) return 'Index';
    return 'Open';
  }

  function evidenceLink(ref, linkHtml, ghRepo, label) {
    if (!ref) return '—';
    const text = evidenceLabel(ref, label);
    if (ref.startsWith('http')) return linkHtml(ref, text, 'source-open-link');
    return linkHtml(`https://github.com/${ghRepo}/blob/main/${ref}`, text, 'source-open-link');
  }

  function recordEvidenceLink(row, linkHtml, ghRepo) {
    const ref = row?.evidence_url || row?.source_document || row?.evidence_ref || row?.source_file;
    if (!ref) return '';
    return evidenceLink(ref, linkHtml, ghRepo, row.evidence_label);
  }

  function sourceBadgeClass(source) {
    if (source === 'news') return 'badge-ok';
    if (source === 'superinvestor_letter') return 'badge-purple';
    if (source === 'third_party' || source === 'sumzero_research') return 'badge-us';
    if (source === 'insider') return 'badge-warn';
    return 'badge-us';
  }

  function cleanText(value, limit = 220) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    return text.length > limit ? text.slice(0, limit - 1).trim() + '...' : text;
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
      filings: 'filing',
      earnings: 'earnings',
      macro: 'macro',
      insider: 'insider',
      ownership: 'insider',
      news: 'news',
      sumzero: 'sumzero_research',
      company: 'company_document',
      research: ['third_party', 'sumzero_research', 'research'],
      third_party: 'third_party',
    };
    const src = map[filter] || filter;
    if (filter === 'vic') {
      return insights.filter(r =>
        r.source === 'third_party'
        && [r.publisher, r.source_name, r.source_path, r.evidence_ref, r.evidence_url]
          .join(' ')
          .toLowerCase()
          .includes('vic')
      );
    }
    if (Array.isArray(src)) return insights.filter(r => src.includes(r.source));
    return insights.filter(r => r.source === src);
  }

  function renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo) {
    if (!discussants?.length) return '';
    return `
      <div class="detail-section tier-3">
        <h3>Who discusses this</h3>
        <ul class="source-stack">
          ${discussants.slice(0, 8).map(d => {
            const action = d.action || 'discussed';
            const badge = STANCE_BADGE[action] || 'badge-us';
            const snippet = escapeHtml(cleanText(d.commentary, 220));
            const link = recordEvidenceLink(d, linkHtml, ghRepo);
            return `<li class="source-card">
              <div class="source-card-head">
                <div class="source-card-badges">
                  <span class="badge ${sourceBadgeClass('superinvestor_letter')}">Letter</span>
                  <span class="badge ${badge}">${escapeHtml(action)}</span>
                </div>
                <span class="source-date mono">${escapeHtml(d.letter_date || '')}</span>
              </div>
              <div class="source-card-title">${escapeHtml(d.fund || 'Investor letter')}</div>
              ${snippet ? `<div class="source-card-body">${snippet}</div>` : ''}
              <div class="source-card-footer">
                <span>${escapeHtml(d.quarter || '—')}</span>
                ${link}
              </div>
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
      { id: 'filings', label: 'Filings' },
      { id: 'company', label: 'Company' },
      { id: 'vic', label: 'VIC' },
      { id: 'sumzero', label: 'SumZero' },
      { id: 'research', label: 'Research' },
      { id: 'news', label: 'News' },
      { id: 'all', label: 'All' },
    ];
    const otherBlock = `
      <div class="detail-section tier-3${letterBlock ? '' : ''}">
        <h3>External context</h3>
        <nav class="source-pills">
          ${pills.map(p => `<button type="button" class="filter-btn source-pill${filter === p.id ? ' active' : ''}" data-insight-filter="${p.id}">${p.label}</button>`).join('')}
        </nav>
        ${rows.length ? `<ul class="source-stack">
          ${rows.map(r => {
            const src = SOURCE_LABEL[r.source] || r.source;
            const sourceName = r.source_name || r.fund || r.publisher || '';
            const date = r.date || r.as_of || r.observed_at || '';
            const title = cleanText(r.title || sourceName || src, 110);
            const claim = escapeHtml(cleanText(r.summary || r.claim, 220));
            const link = recordEvidenceLink(r, linkHtml, ghRepo);
            const action = r.action ? `<span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action)}</span> ` : '';
            const directionClass = r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us');
            return `<li class="source-card">
              <div class="source-card-head">
                <div class="source-card-badges">
                  <span class="badge ${sourceBadgeClass(r.source)}">${escapeHtml(src)}</span>
                  ${action || `<span class="badge ${directionClass}">${escapeHtml(r.direction || 'neutral')}</span>`}
                  ${r.confidence ? `<span class="badge badge-us">${escapeHtml(r.confidence)}</span>` : ''}
                </div>
                <span class="source-date mono">${escapeHtml(date || '')}</span>
              </div>
              <div class="source-card-title">${escapeHtml(title)}</div>
              ${sourceName ? `<div class="source-card-meta">${escapeHtml(sourceName)}</div>` : ''}
              ${claim ? `<div class="source-card-body">${claim}</div>` : ''}
              <div class="source-card-footer">
                <span>${escapeHtml(AXIS_LABEL[r.impact_axis] || r.event_type || r.ref || 'context')}</span>
                ${link}
              </div>
            </li>`;
          }).join('')}
        </ul>` : '<p class="tier-sub">No matching context for this filter.</p>'}
      </div>`;
    return letterBlock + (filter === 'letters' && letterBlock ? '' : otherBlock);
  }

  function insightToneClass(tone) {
    if (tone === 'bullish') return 'badge-ok';
    if (tone === 'risk') return 'badge-bad';
    if (tone === 'ownership') return 'badge-purple';
    if (tone === 'stale') return 'badge-warn';
    return 'badge-us';
  }

  function renderInsightItem(item, escapeHtml, linkHtml) {
    if (!item) return '<span class="tier-sub">No signal</span>';
    const directionClass = item.direction === 'bullish'
      ? 'badge-ok'
      : (item.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = item.evidence_url ? ` ${linkHtml(item.evidence_url, evidenceLabel(item.evidence_url, item.evidence_label), 'source-open-link')}` : '';
    return `
      <div class="essential-item">
        <div>
          <span class="badge ${directionClass}">${escapeHtml(item.direction || 'neutral')}</span>
          <span class="badge badge-us">${escapeHtml(item.source_label || item.source || 'source')}</span>
          <span class="badge badge-us">${escapeHtml(item.confidence || 'med')}</span>
          ${item.date ? `<span class="mono tier-sub">${escapeHtml(item.date)}</span>` : ''}
        </div>
        <div class="essential-title">${escapeHtml(item.title || 'Insight')}${link}</div>
        ${item.summary ? `<div class="tier-sub">${escapeHtml(item.summary)}</div>` : ''}
      </div>`;
  }

  function renderEssentialInsights(essential, escapeHtml, linkHtml) {
    if (!essential || !(essential.bullets || []).length) {
      return `
        <div class="detail-section tier-2">
          <h3>Essential insights</h3>
          <div class="research-box">
            <div class="tier-sub">No ranked insight is attached to this ticker yet.</div>
          </div>
        </div>`;
    }
    const status = essential.status || {};
    const sourceMix = (essential.source_mix || []).map(s => SOURCE_LABEL[s] || s).join(', ') || 'none';
    return `
      <div class="detail-section tier-2">
        <h3>Essential insights</h3>
        <div class="research-box essential-box">
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px">
            <span class="badge ${insightToneClass(status.tone)}">${escapeHtml(status.label || 'Covered')}</span>
            <span class="tier-sub">${essential.freshness_days != null ? `${essential.freshness_days}d old` : 'undated'} · ${escapeHtml(sourceMix)}</span>
          </div>
          ${(essential.bullets || []).slice(0, 3).map(item => renderInsightItem(item, escapeHtml, linkHtml)).join('')}
        </div>
      </div>`;
  }

  function renderMemoryClaim(claim, escapeHtml, linkHtml) {
    if (!claim) return '';
    const directionClass = claim.direction === 'bullish'
      ? 'badge-ok'
      : (claim.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = claim.evidence_url
      ? ` ${linkHtml(claim.evidence_url, evidenceLabel(claim.evidence_url, claim.evidence_label), 'source-open-link')}`
      : '';
    return `<li class="source-card">
      <div class="source-card-head">
        <div class="source-card-badges">
          <span class="badge ${directionClass}">${escapeHtml(claim.direction || 'neutral')}</span>
          <span class="badge badge-us">${escapeHtml(claim.claim_type || 'claim')}</span>
        </div>
        <span class="source-date mono">${escapeHtml(claim.date || '')}</span>
      </div>
      <div class="source-card-title">${escapeHtml(claim.claim || 'Research claim')}${link}</div>
      <div class="source-card-footer">
        <span>${escapeHtml(claim.source_title || claim.source_type || 'source')}</span>
        <span class="mono">${Number(claim.confidence_score || 0)}</span>
      </div>
    </li>`;
  }

  function renderResearchMemory(memory, escapeHtml, linkHtml) {
    if (!memory || !memory.claim_count) {
      return `
        <div class="detail-section tier-2">
          <h3>Research memory</h3>
          <div class="research-box"><div class="tier-sub">No cross-referenced claims attached yet.</div></div>
        </div>`;
    }
    const biotech = memory.biotech || {};
    const sourceMix = (memory.source_mix || []).map(s => SOURCE_LABEL[s] || String(s).replace(/_/g, ' ')).join(', ') || 'none';
    const inflectionClaims = memory.inflection_claims || [];
    const riskClaims = memory.risk_claims || [];
    const topClaims = memory.top_claims || [];
    const biotechHtml = biotech.is_biotech_related ? `
      <div class="memory-biotech">
        <span class="badge badge-purple">Biotech</span>
        <span class="tier-sub">${biotech.tracked_specialist_fund_count || 0} specialist funds tracked · ${biotech.ownership_records?.length || 0} 13F records loaded</span>
      </div>` : '';
    return `
      <div class="detail-section tier-2">
        <h3>Research memory</h3>
        <div class="research-box essential-box">
          <div class="memory-score-row">
            <div class="metric"><div class="k">Claims</div><div class="v mono">${memory.claim_count}</div></div>
            <div class="metric"><div class="k">Sources</div><div class="v mono">${memory.source_count}</div></div>
            <div class="metric"><div class="k">Evidence</div><div class="v mono">+${memory.confirming_count || 0} / -${memory.disconfirming_count || 0}</div></div>
          </div>
          <div class="tier-sub" style="margin:8px 0">${escapeHtml(sourceMix)}</div>
          ${biotechHtml}
          ${inflectionClaims.length ? `<h3 style="margin-top:12px">Inflection claims</h3><ul class="source-stack">${inflectionClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml)).join('')}</ul>` : ''}
          ${riskClaims.length ? `<h3 style="margin-top:12px">Risks / disconfirming</h3><ul class="source-stack">${riskClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml)).join('')}</ul>` : ''}
          ${!inflectionClaims.length && !riskClaims.length ? `<ul class="source-stack">${topClaims.slice(0, 3).map(c => renderMemoryClaim(c, escapeHtml, linkHtml)).join('')}</ul>` : ''}
        </div>
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
        <thead><tr><th>Date</th><th>Fund</th><th>Quarter</th><th>Themes</th><th>Tickers</th><th>Our overlap</th><th>Summary</th><th>Source</th></tr></thead>
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
              <td>${recordEvidenceLink(r, linkHtml, ghRepo)}</td>
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
              <td>${evidenceLink(f.evidence_url || f.evidence_ref, linkHtml, ghRepo, f.evidence_label)}</td>
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
          ${(profile.letters || []).length} letter(s) · latest ${escapeHtml(latest.quarter || '—')} · ${evidenceLink(latest.evidence_url || latest.source_document || latest.source_file, linkHtml, ghRepo, latest.evidence_label)}
        </p>
      </div>`;
  }

  function filterEvents(events, opts) {
    const { search, bookOnly } = opts || {};
    let list = events || [];
    if (bookOnly) {
      list = list.filter(e => e.in_our_book || e.portfolio_relevance >= 1);
    }
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(e =>
        (e.ticker || '').toLowerCase().includes(q)
        || (e.title || '').toLowerCase().includes(q)
        || (e.summary || '').toLowerCase().includes(q)
        || (e.source_label || e.source || '').toLowerCase().includes(q)
        || (e.impact_axis || '').toLowerCase().includes(q)
      );
    }
    return list;
  }

  function renderEventQueue(events, escapeHtml, linkHtml, ghRepo, opts) {
    const rows = filterEvents(events, opts).slice(0, 120);
    if (!rows.length) {
      return '<p class="subhead">No ranked events match this view.</p>';
    }
    return `
      <table class="darwin-table" id="insights-event-table">
        <thead><tr><th>Score</th><th>Date</th><th>Ticker</th><th>Source</th><th>Axis</th><th>Event</th><th></th></tr></thead>
        <tbody>
          ${rows.map(e => {
            const directionClass = e.direction === 'bullish' ? 'badge-ok' : (e.direction === 'bearish' ? 'badge-bad' : 'badge-us');
            const ticker = e.ticker ? `<span class="mono">${escapeHtml(e.ticker)}</span>` : '<span class="tier-sub">portfolio</span>';
            return `
              <tr>
                <td class="mono">${Number(e.score || 0)}</td>
                <td class="mono">${escapeHtml(e.observed_at || 'n/a')}</td>
                <td>${ticker}</td>
                <td><span class="badge badge-us">${escapeHtml(e.source_label || SOURCE_LABEL[e.source] || e.source || 'source')}</span></td>
                <td>${escapeHtml(AXIS_LABEL[e.impact_axis] || e.impact_axis || 'context')}</td>
                <td style="min-width:280px">
                  <div><span class="badge ${directionClass}">${escapeHtml(e.direction || 'neutral')}</span> <strong>${escapeHtml(e.title || 'Insight')}</strong></div>
                  <div class="tier-sub" style="margin-top:4px">${escapeHtml((e.summary || '').slice(0, 220))}</div>
                </td>
                <td>${evidenceLink(e.evidence_url || e.evidence_ref, linkHtml, ghRepo, e.evidence_label)}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>
      ${(events || []).length > rows.length ? `<p class="tier-sub">${(events || []).length - rows.length} more events outside the current table window.</p>` : ''}`;
  }

  function filterTickerEssentials(tickers, opts) {
    const { search, bookOnly } = opts || {};
    let rows = tickers || [];
    if (bookOnly) {
      rows = rows.filter(t => t.essential_insights && !t.essential_insights.needs_work);
    }
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(t => {
        const e = t.essential_insights || {};
        const text = [
          t.ticker,
          t.company,
          e.status?.label,
          ...(e.source_mix || []),
          ...((e.bullets || []).map(b => `${b.title || ''} ${b.summary || ''}`)),
        ].join(' ').toLowerCase();
        return text.includes(q);
      });
    }
    return rows;
  }

  function renderTickerEssentials(tickers, escapeHtml, linkHtml, opts) {
    const rows = filterTickerEssentials(tickers, opts).slice(0, 160);
    if (!rows.length) return '<p class="subhead">No ticker essentials match this view.</p>';
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Status</th><th>Fresh</th><th>Latest</th><th>Bull</th><th>Bear/Risk</th><th>Owner</th></tr></thead>
        <tbody>
          ${rows.map(t => {
            const e = t.essential_insights || {};
            const status = e.status || {};
            return `
              <tr>
                <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button><div class="tier-sub">${escapeHtml(t.company || '')}</div></td>
                <td><span class="badge ${insightToneClass(status.tone)}">${escapeHtml(status.label || 'No insight')}</span></td>
                <td class="mono">${e.freshness_days != null ? `${e.freshness_days}d` : 'n/a'}</td>
                <td>${renderInsightItem(e.latest, escapeHtml, linkHtml)}</td>
                <td>${renderInsightItem(e.bull, escapeHtml, linkHtml)}</td>
                <td>${renderInsightItem(e.bear, escapeHtml, linkHtml)}</td>
                <td>${renderInsightItem(e.owner, escapeHtml, linkHtml)}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  function renderSourceHealth(health, escapeHtml) {
    const rows = Object.entries(health || {});
    if (!rows.length) {
      return '<p class="subhead">No source health data yet.</p>';
    }
    return `
      <table class="darwin-table" id="insights-source-table">
        <thead><tr><th>Source</th><th>Status</th><th>Records</th><th>Items</th><th>As of</th><th>Notes</th></tr></thead>
        <tbody>
          ${rows.map(([key, h]) => {
            const status = h.status || 'unknown';
            const cls = status === 'ok' ? 'badge-ok' : (status === 'missing' || status === 'forbidden' ? 'badge-warn' : 'badge-us');
            const notes = h.notes || (h.warnings ? `${h.warnings} warning(s)` : (h.path || ''));
            return `
              <tr>
                <td>${escapeHtml(key.replace(/_/g, ' '))}</td>
                <td><span class="badge ${cls}">${escapeHtml(status)}</span></td>
                <td class="mono">${h.records ?? 'n/a'}</td>
                <td class="mono">${h.items ?? 'n/a'}</td>
                <td class="mono">${escapeHtml(h.as_of || 'n/a')}</td>
                <td class="tier-sub">${escapeHtml(notes)}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  function renderDataSourceCandidates(candidates, escapeHtml) {
    const tools = candidates?.selected_tools || [];
    if (!tools.length) return '<p class="subhead">No TerminalValue candidate source registry yet.</p>';
    return `
      <div class="detail-section">
        <h3>TerminalValue candidate feeds</h3>
        <p class="tier-sub" style="margin-bottom:8px">
          ${escapeHtml(candidates.source_label || 'TerminalValue.io')} · reviewed ${escapeHtml(candidates.reviewed_at || 'n/a')} · ${tools.length} selected feeds
        </p>
        <table class="darwin-table">
          <thead><tr><th>Provider</th><th>Role</th><th>Status</th><th>Priority</th><th>Credential</th><th>Target</th></tr></thead>
          <tbody>
            ${tools.map(t => `
              <tr>
                <td>${escapeHtml(t.name || 'Provider')}</td>
                <td>${escapeHtml(t.dashboard_role || '')}</td>
                <td><span class="badge ${t.integration_status === 'live' ? 'badge-ok' : 'badge-warn'}">${escapeHtml(t.integration_status || 'candidate')}</span></td>
                <td>${escapeHtml(t.priority || 'medium')}</td>
                <td>${t.credential_required ? 'required' : 'not required'}</td>
                <td class="mono" style="font-size:11px">${escapeHtml(t.target_pipeline || '')}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  }

  function filterDocumentCatalog(catalog, opts) {
    const { search = '', quarter = 'all', bookOnly = false } = opts || {};
    const q = search.toLowerCase();
    let rows = catalog?.documents || [];
    if (quarter && quarter !== 'all') {
      const label = quarter.replace(/^(\d{4})Q([1-4])$/, '$1 Q$2');
      rows = rows.filter(r => !r.quarter || r.quarter === label || r.quarter === quarter);
    }
    if (bookOnly) {
      rows = rows.filter(r => r.ticker);
    }
    if (q) {
      rows = rows.filter(r => [
        r.ticker,
        r.title,
        r.source_label,
        r.source_type,
        r.quarter,
        r.drive_folder_path,
      ].join(' ').toLowerCase().includes(q));
    }
    return rows;
  }

  function renderDocumentCatalog(catalog, escapeHtml, linkHtml, opts) {
    const rows = filterDocumentCatalog(catalog, opts).slice(0, 300);
    const summary = catalog?.summary || {};
    const bySource = summary.by_source_type || {};
    const cards = Object.entries(bySource)
      .sort((a, b) => b[1] - a[1])
      .map(([source, count]) => `<span class="badge badge-us">${escapeHtml(SOURCE_LABEL[source] || source.replace(/_/g, ' '))}: ${count}</span>`)
      .join('');
    if (!catalog) {
      return '<p class="subhead">PDF catalog not built. Run: python _system/scripts/build_dashboard_data.py</p>';
    }
    return `
      <div class="detail-section">
        <h3>PDF library</h3>
        <p class="tier-sub" style="margin-bottom:8px">
          ${summary.document_count || 0} documents · ${summary.uploaded_count || 0} uploaded · ${summary.pending_upload_count || 0} pending
        </p>
        <div class="source-card-badges" style="margin-bottom:10px">${cards}</div>
        <table class="darwin-table" id="insights-document-catalog">
          <thead><tr><th>Source</th><th>Ticker</th><th>Quarter</th><th>Title</th><th>Folder</th><th></th></tr></thead>
          <tbody>
            ${rows.map(r => `
              <tr>
                <td><span class="badge badge-us">${escapeHtml(r.source_label || r.source_type || 'PDF')}</span></td>
                <td class="mono">${escapeHtml(r.ticker || '—')}</td>
                <td class="mono">${escapeHtml(r.quarter || '—')}</td>
                <td style="min-width:280px">${escapeHtml(r.title || 'Untitled')}</td>
                <td class="tier-sub">${escapeHtml(r.drive_folder_path || '')}</td>
                <td>${r.drive_web_view_link ? linkHtml(r.drive_web_view_link, 'PDF', 'source-open-link') : '—'}</td>
              </tr>`).join('')}
          </tbody>
        </table>
        ${(catalog.documents || []).length > rows.length ? `<p class="tier-sub">${(catalog.documents || []).length - rows.length} more documents outside the current table window.</p>` : ''}
      </div>`;
  }

  function renderMemoryLedger(memory, escapeHtml, linkHtml, opts) {
    const { search = '', bookOnly = false } = opts || {};
    const q = search.toLowerCase();
    let rows = memory?.claim_ledger || [];
    if (bookOnly) {
      rows = rows.filter(r => r.claim_type === 'inflection' || r.claim_type === 'risk' || r.claim_type === 'ownership' || r.direction === 'bearish');
    }
    if (q) {
      rows = rows.filter(r => [r.ticker, r.claim, r.claim_type, r.source_title, r.source_type].join(' ').toLowerCase().includes(q));
    }
    rows = rows.slice(0, 160);
    if (!rows.length) return '<p class="subhead">No research-memory claims match this view.</p>';
    return `
      <table class="darwin-table">
        <thead><tr><th>Ticker</th><th>Type</th><th>Direction</th><th>Claim</th><th>Source</th><th></th></tr></thead>
        <tbody>${rows.map(r => {
          const cls = r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us');
          return `<tr>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td><span class="badge badge-us">${escapeHtml(r.claim_type || 'claim')}</span></td>
            <td><span class="badge ${cls}">${escapeHtml(r.direction || 'neutral')}</span></td>
            <td style="min-width:320px">${escapeHtml(r.claim || '')}</td>
            <td>${escapeHtml(r.source_title || r.source_type || 'source')}</td>
            <td>${r.evidence_url ? linkHtml(r.evidence_url, evidenceLabel(r.evidence_url, r.evidence_label), 'source-open-link') : '—'}</td>
          </tr>`;
        }).join('')}</tbody>
      </table>`;
  }

  function renderMemoryReviewQueue(memory, escapeHtml) {
    const rows = (memory?.review_queue || []).slice(0, 160);
    if (!rows.length) return '<p class="subhead">No memory review items.</p>';
    return `
      <div class="detail-section">
        <h3>Review queue</h3>
        <table class="darwin-table">
          <thead><tr><th>Priority</th><th>Ticker</th><th>Reason</th></tr></thead>
          <tbody>${rows.map(r => `<tr>
            <td><span class="badge ${r.priority === 'high' ? 'badge-bad' : 'badge-warn'}">${escapeHtml(r.priority || 'medium')}</span></td>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td>${escapeHtml(r.reason || '')}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  }

  function renderBiotechMemory(memory, escapeHtml, linkHtml) {
    const funds = memory?.biotech?.specialist_funds || [];
    const tickers = Object.values(memory?.by_ticker || {}).filter(t => t.biotech?.is_biotech_related);
    return `
      <div class="detail-section">
        <h3>Biotech specialist registry</h3>
        <p class="tier-sub" style="margin-bottom:8px">${funds.length} specialist funds tracked for 13F ingestion · ${tickers.length} biotech-related tickers detected in current book/watchlist.</p>
        <table class="darwin-table">
          <thead><tr><th>Fund</th><th>Specialty</th><th>Role</th><th>Notes</th></tr></thead>
          <tbody>${funds.map(f => `<tr>
            <td>${escapeHtml(f.fund || '')}</td>
            <td><span class="badge badge-purple">${escapeHtml(f.specialty || 'biotech')}</span></td>
            <td>${escapeHtml(f.signal_role || 'specialist_13f')}</td>
            <td class="tier-sub">${escapeHtml(f.notes || '')}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="detail-section">
        <h3>Biotech-related ticker queue</h3>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Claims</th><th>Evidence</th><th>13F status</th><th>Top claim</th></tr></thead>
          <tbody>${tickers.map(t => {
            const top = (t.top_claims || [])[0] || {};
            return `<tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button><div class="tier-sub">${escapeHtml(t.company || '')}</div></td>
              <td class="mono">${t.claim_count || 0}</td>
              <td class="mono">+${t.confirming_count || 0} / -${t.disconfirming_count || 0}</td>
              <td><span class="badge ${(t.biotech?.ownership_records || []).length ? 'badge-ok' : 'badge-warn'}">${(t.biotech?.ownership_records || []).length ? 'loaded' : 'ready'}</span></td>
              <td>${escapeHtml((top.claim || '').slice(0, 180))} ${top.evidence_url ? linkHtml(top.evidence_url, evidenceLabel(top.evidence_url, top.evidence_label), 'source-open-link') : ''}</td>
            </tr>`;
          }).join('')}</tbody>
        </table>
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
      activeSection = 'events',
      tickers = [],
      memory = null,
      documentCatalog = null,
    } = options || {};

    const profiles = insights?.fund_profiles || {};
    if (selectedFundId && profiles[selectedFundId]) {
      return renderFundDetail(profiles[selectedFundId], escapeHtml, linkHtml, ghRepo);
    }

    const byQ = insights?.theme_rankings_by_quarter || {};
    const letterIndex = insights?.letter_index || [];
    const quarterSet = new Set([
      ...Object.keys(byQ).filter(q => q && q !== 'all'),
      ...letterIndex.map(r => r.quarter).filter(Boolean),
    ]);
    const quarters = Array.from(quarterSet).sort().reverse();
    const effectiveQuarter = quarter === 'latest' ? (quarters[0] || 'all') : quarter;
    const themes = byQ[effectiveQuarter] || insights?.theme_rankings || [];
    let funds = insights?.fund_registry || [];
    let letters = filterLetterIndex(letterIndex, { quarter: effectiveQuarter, search: fundSearch, bookOnly });

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
    if (effectiveQuarter && effectiveQuarter !== 'all') {
      funds = funds.filter(f => f.quarter === effectiveQuarter);
    }

    const qTabs = [{ id: 'all', label: 'All' }, ...quarters.map(q => ({ id: q, label: q }))];
    const sections = [
      { id: 'overview', label: 'Overview' },
      { id: 'events', label: 'What changed' },
      { id: 'letters', label: 'Letters' },
      { id: 'funds', label: 'Funds' },
      { id: 'documents', label: 'PDF library' },
      { id: 'tickers', label: 'Ticker insights' },
      { id: 'memory', label: 'Research memory' },
      { id: 'themes', label: 'Themes' },
      { id: 'sources', label: 'Pipeline status' },
    ];

    let body = '';
    if (activeSection === 'overview') {
      body = renderSourceHealth(insights?.source_health || {}, escapeHtml);
    } else if (activeSection === 'events') {
      body = renderEventQueue(insights?.events || [], escapeHtml, linkHtml, ghRepo, { search: fundSearch, bookOnly });
    } else if (activeSection === 'letters') {
      const scope = effectiveQuarter && effectiveQuarter !== 'all' ? effectiveQuarter : 'all quarters';
      body = `<p class="tier-sub" style="margin-bottom:8px">${letters.length} letter(s) · ${escapeHtml(scope)}${bookOnly ? ' · overlap with our book only' : ''}</p>`
        + renderLetterIndex(letters, escapeHtml, linkHtml, ghRepo, true);
    } else if (activeSection === 'funds') {
      body = renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo, bookOnly);
    } else if (activeSection === 'documents') {
      body = renderDocumentCatalog(documentCatalog, escapeHtml, linkHtml, { search: fundSearch, quarter: effectiveQuarter, bookOnly });
    } else if (activeSection === 'tickers') {
      body = renderTickerEssentials(tickers, escapeHtml, linkHtml, { search: fundSearch, bookOnly });
    } else if (activeSection === 'memory') {
      body = renderMemoryLedger(memory, escapeHtml, linkHtml, { search: fundSearch, bookOnly })
        + '<div style="height:14px"></div>'
        + renderMemoryReviewQueue(memory, escapeHtml);
    } else if (activeSection === 'themes') {
      body = renderThemeRankings(themes, escapeHtml);
    } else {
      body = renderSourceHealth(insights?.source_health || {}, escapeHtml)
        + renderDataSourceCandidates(insights?.data_source_candidates || {}, escapeHtml);
    }

    return `
      <h2 style="font-size:18px;margin-bottom:6px">Insights</h2>
      <p class="subhead" style="margin-bottom:14px">
        Portfolio context only · ${insights?.event_count || 0} events · ${insights?.letter_count || 0} letters · ${insights?.front_record_count || 0} front records · ${insights?.archived_record_count || 0} archived
      </p>
      <nav class="view-tabs" id="insights-section-tabs" style="margin-bottom:10px">
        ${sections.map(s => `<button type="button" class="view-tab${activeSection === s.id ? ' active' : ''}" data-insights-section="${s.id}">${s.label}</button>`).join('')}
      </nav>
      <div class="detail-section" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px">
        <nav class="view-tabs" id="insights-quarter-tabs">
          ${qTabs.map(t => `<button type="button" class="view-tab${effectiveQuarter === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <label class="tier-sub" style="display:flex;align-items:center;gap:6px">
          <input type="checkbox" id="insights-book-only" ${bookOnly ? 'checked' : ''} />
          High-signal only
        </label>
        <input class="search" id="fund-registry-search" placeholder="Search ticker, event, fund, theme..." value="${escapeHtml(fundSearch)}" style="max-width:280px" />
      </div>
      ${body}`;
  }

  global.InsightsViz = {
    renderDecisionSummary,
    renderIdentityLine,
    renderActiveLensChips,
    renderExternalContext,
    renderConsensusDetail,
    renderEssentialInsights,
    renderResearchMemory,
    renderInsightsPanel,
    renderLetterDiscussants,
    filterInsights,
    STANCE_BADGE,
  };
})(window);
