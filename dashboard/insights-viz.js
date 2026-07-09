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
    third_party: 'VIC / third party',
    company_document: 'Company',
    research: 'Research',
    pdf: 'Other PDFs',
    theme: 'Theme',
    news: 'News',
  };

  const CATALOG_SOURCE_LABEL = {
    superinvestor_letter: 'Letters',
    company_document: 'Company',
    third_party: 'VIC / third party',
    sumzero_research: 'SumZero',
    research: 'Research',
    dropbox_ingestion: 'Dropbox ingestion',
    pdf: 'Other PDFs',
  };

  const CATALOG_SOURCE_SORT = {
    superinvestor_letter: 0,
    company_document: 1,
    third_party: 2,
    sumzero_research: 3,
    research: 4,
    dropbox_ingestion: 5,
    pdf: 6,
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

  function isDriveGoogleHost(hostname) {
    const host = String(hostname || '').toLowerCase();
    return host === 'drive.google.com' || host.endsWith('.drive.google.com');
  }

  function evidenceLabel(ref, fallback) {
    const clean = (ref || '').split('#')[0].toLowerCase();
    const url = String(ref || '');
    if (url.startsWith('http')) {
      try {
        const parsed = new URL(url);
        if (isDriveGoogleHost(parsed.hostname) && parsed.pathname.includes('/drive/folders/')) return 'Drive folder';
        if (isDriveGoogleHost(parsed.hostname)) return 'PDF';
      } catch (_) {
        /* fall through */
      }
    }
    if (fallback && fallback !== 'Text') return fallback;
    if (clean.endsWith('.pdf')) return 'PDF';
    if (clean.endsWith('.htm') || clean.endsWith('.html')) return 'HTML';
    if (clean.startsWith('http')) return 'Open';
    if (clean.endsWith('.json')) return 'Index';
    if (fallback) return fallback;
    return 'Open';
  }

  function evidenceLink(ref, linkHtml, ghRepo, label) {
    if (!ref) return '—';
    const text = evidenceLabel(ref, label);
    if (String(ref).startsWith('http')) return linkHtml(ref, text, 'source-open-link');
    return linkHtml(`https://github.com/${ghRepo}/blob/main/${ref}`, text, 'source-open-link');
  }

  function recordEvidenceLink(row, linkHtml, ghRepo) {
    const url = row?.evidence_url;
    if (url) {
      return linkHtml(url, evidenceLabel(url, row?.evidence_label), 'source-open-link');
    }
    const ref = row?.source_document || row?.evidence_ref || row?.source_file;
    if (!ref) return '—';
    return evidenceLink(ref, linkHtml, ghRepo, row?.evidence_label);
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

  function renderActiveLensChips(activeLenses, silentCount, expandedPersona, lenses, escapeHtml, powerZones) {
    if (!activeLenses?.length && !silentCount) return '';
    const inZoneIds = new Set((powerZones && powerZones.in_zone) || []);
    const hasZones = inZoneIds.size > 0;
    const lensChip = (l, inZone) => {
      const short = (l.label || l.persona || '').split(' ')[0];
      const active = expandedPersona === l.persona ? ' lens-chip-active' : '';
      const zoneMark = inZone ? ' <span title="In power zone: this persona framework fits this company type">⚡</span>' : '';
      return `<button type="button" class="lens-chip${active}" data-lens-persona="${escapeHtml(l.persona)}">${escapeHtml(short)}${zoneMark} ${escapeHtml(l.verdict)} ${l.return_pct != null ? fmtPct(l.return_pct) : ''}</button>`;
    };
    const zoned = hasZones ? (activeLenses || []).filter(l => inZoneIds.has(l.persona)) : (activeLenses || []);
    const outside = hasZones ? (activeLenses || []).filter(l => !inZoneIds.has(l.persona)) : [];
    const chips = zoned.map(l => lensChip(l, hasZones)).join('');
    const outsideBlock = outside.length
      ? `<details style="display:inline-block"><summary class="lens-chip-silent" style="cursor:pointer;list-style:none">+${outside.length} outside framework</summary>
          <div class="lens-chips" style="margin-top:6px">${outside.map(l => lensChip(l, false)).join('')}</div>
        </details>`
      : '';
    const primary = hasZones && zoned.length ? zoned[0] : null;
    const viewedThrough = primary
      ? `<p class="tier-sub" style="margin:2px 0 6px">Viewed through: <strong>${escapeHtml(primary.label || primary.persona)}</strong> (in power zone)${primary.return_pct != null ? ` — IRR ${fmtPct(primary.return_pct)}` : ''}</p>`
      : '';
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
        ${viewedThrough}
        <div class="lens-chips">${chips}${outsideBlock}${silent}</div>
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

  function renderInsightItem(item, escapeHtml, linkHtml, opts) {
    const emptyLabel = (opts && opts.emptyLabel) || 'No signal';
    if (!item) return `<span class="tier-sub">${emptyLabel}</span>`;
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
          <h3>External context</h3>
          <div class="research-box">
            <div class="tier-sub">No ranked external context yet. Use Insights → Ticker insights for the portfolio scan.</div>
          </div>
        </div>`;
    }
    const status = essential.status || {};
    const sourceMix = (essential.source_mix || []).map(s => SOURCE_LABEL[s] || s).join(', ') || 'none';
    const primary = (essential.bullets || [])[0];
    return `
      <div class="detail-section tier-2">
        <h3>External context</h3>
        <div class="research-box essential-box">
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px">
            <span class="badge ${insightToneClass(status.tone)}">${escapeHtml(status.label || 'Covered')}</span>
            <span class="tier-sub">${essential.freshness_days != null ? `${essential.freshness_days}d old` : 'undated'} · ${escapeHtml(sourceMix)}</span>
          </div>
          ${renderInsightItem(primary, escapeHtml, linkHtml)}
          <p class="tier-sub" style="margin-top:8px">Full scan: Insights → Ticker insights. Filtered letter/macro rows below.</p>
        </div>
      </div>`;
  }

  function renderMemoryClaim(claim, escapeHtml, linkHtml, ghRepo) {
    if (!claim) return '';
    const directionClass = claim.direction === 'bullish'
      ? 'badge-ok'
      : (claim.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = claim.evidence_url
      ? ` ${evidenceLink(claim.evidence_url, linkHtml, ghRepo, claim.evidence_label)}`
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

  function renderResearchMemory(memory, escapeHtml, linkHtml, ghRepo) {
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
        <span class="tier-sub">${biotech.tracked_specialist_fund_count || 0} specialist funds tracked · ${biotech.ownership_records?.length || 0} 13F records loaded${biotech.signals?.consensus_score != null ? ` · consensus ${biotech.signals.consensus_score}` : ''}</span>
      </div>` : '';
    const ownershipClaims = memory.ownership_claims || [];
    const specialistMentions = biotech.specialist_mentions || [];
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
          ${ownershipClaims.length ? `<h3 style="margin-top:12px">Ownership claims</h3><ul class="source-stack">${ownershipClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${inflectionClaims.length ? `<h3 style="margin-top:12px">Inflection claims</h3><ul class="source-stack">${inflectionClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${riskClaims.length ? `<h3 style="margin-top:12px">Risks / disconfirming</h3><ul class="source-stack">${riskClaims.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${specialistMentions.length ? `<h3 style="margin-top:12px">Specialist letter mentions</h3><ul class="source-stack">${specialistMentions.map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
          ${!inflectionClaims.length && !riskClaims.length && !ownershipClaims.length ? `<ul class="source-stack">${topClaims.slice(0, 3).map(c => renderMemoryClaim(c, escapeHtml, linkHtml, ghRepo)).join('')}</ul>` : ''}
        </div>
      </div>`;
  }

  const MEMORY_VIEW_TABS = [
    { id: 'ledger', label: 'Claim ledger' },
    { id: 'biotech', label: 'Biotech' },
    { id: 'review', label: 'Review queue' },
  ];

  const MEMORY_TYPE_FILTERS = [
    { id: 'all', label: 'All types' },
    { id: 'thesis', label: 'Thesis' },
    { id: 'variant_view', label: 'Variant' },
    { id: 'risk', label: 'Risk' },
    { id: 'ownership', label: 'Ownership' },
    { id: 'fundamentals', label: 'Fundamentals' },
    { id: 'deep_dive', label: 'Deep dive' },
  ];

  function memoryClaimMatchesType(row, typeFilter) {
    if (!typeFilter || typeFilter === 'all') return true;
    if (typeFilter === 'deep_dive') {
      return row.source_type === 'deep_dive' || row.source_type === 'adversarial_review';
    }
    return row.claim_type === typeFilter;
  }

  function renderMemorySubNav(activeView, escapeHtml) {
    const view = activeView || 'ledger';
    return `
      <nav class="view-tabs memory-sub-nav" id="memory-view-tabs" style="margin:12px 0 8px">
        ${MEMORY_VIEW_TABS.map(t => `<button type="button" class="view-tab${view === t.id ? ' active' : ''}" data-memory-view="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
      </nav>`;
  }

  function renderMemoryFilters(opts, escapeHtml) {
    const typeFilter = opts?.memoryTypeFilter || 'all';
    const biotechOnly = Boolean(opts?.memoryBiotechOnly);
    const activeView = opts?.memoryViewMode || 'ledger';
    if (activeView !== 'ledger') return '';
    return `
      <div class="memory-filter-row" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px">
        <nav class="source-pills" id="memory-type-tabs" style="margin:0">
          ${MEMORY_TYPE_FILTERS.map(t => `<button type="button" class="filter-btn source-pill${typeFilter === t.id ? ' active' : ''}" data-memory-type="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <label class="tier-sub" style="display:flex;align-items:center;gap:6px;margin-left:4px">
          <input type="checkbox" id="memory-biotech-only" ${biotechOnly ? 'checked' : ''} />
          Biotech names only
        </label>
      </div>
      <p class="tier-sub" style="margin-bottom:10px">Claims span all research dates. Use search, type filters, and holdings overlap above.</p>`;
  }

  function renderMemorySummary(memory, escapeHtml) {
    const summary = memory?.summary || {};
    if (!summary.claim_count) return '';
    return `
      <div class="metric-grid" style="margin-bottom:12px">
        <div class="metric"><div class="k">Claims</div><div class="v mono">${summary.claim_count || 0}</div></div>
        <div class="metric"><div class="k">Sources</div><div class="v mono">${summary.source_count || 0}</div></div>
        <div class="metric"><div class="k">Review queue</div><div class="v mono">${summary.review_queue_count || 0}</div></div>
        <div class="metric"><div class="k">13F records</div><div class="v mono">${summary.ownership_record_count || 0}</div></div>
        <div class="metric"><div class="k">Biotech names</div><div class="v mono">${summary.biotech_related_ticker_count || 0}</div></div>
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

  function renderPeriodEmptyState(activeSection, period, timeModel, escapeHtml) {
    const latestIndexed = timeModel?.latestIndexedQuarter;
    const latestLabel = latestIndexed ? quarterLabel(latestIndexed) : null;
    const emptyForPeriod = period && !period.all && latestIndexed && period.quarters?.[0] !== latestIndexed;
    if (activeSection === 'letters') {
      if (!emptyForPeriod) {
        return '<p class="subhead">No letters indexed yet — run make persona-fetch-letters</p>';
      }
      return `<p class="subhead">No letters indexed for ${escapeHtml(period.label)}. `
        + `${latestLabel ? `<button type="button" class="linkish" data-use-latest-quarter>Use ${escapeHtml(latestLabel)}</button> instead.` : ''}</p>`;
    }
    if (activeSection === 'themes') {
      if (!emptyForPeriod) {
        return '<p class="subhead">No superinvestor letter themes yet — run make persona-fetch-letters</p>';
      }
      return `<p class="subhead">No themes indexed for ${escapeHtml(period.label)}. `
        + `<button type="button" class="linkish" data-use-latest-quarter>Use ${escapeHtml(latestLabel)}</button> instead, `
        + `or open <strong>Letters</strong> for catalog-only PDFs.</p>`;
    }
    return `<p class="subhead">No data for ${escapeHtml(period?.label || 'this period')}.</p>`;
  }

  function themeSentimentBar(row) {
    const bull = Number(row.bullish || 0);
    const bear = Number(row.bearish || 0);
    const neutral = Number(row.neutral || 0);
    const total = bull + bear + neutral;
    if (!total) return '<span class="mono" style="color:var(--text-muted)">—</span>';
    const bp = Math.round((bull / total) * 100);
    const brp = Math.round((bear / total) * 100);
    const np = 100 - bp - brp;
    return `<span style="display:inline-flex;width:72px;height:8px;border-radius:4px;overflow:hidden;background:var(--border-subtle,#333)" title="bull ${bull} · bear ${bear} · neutral ${neutral}">
      <span style="width:${bp}%;background:var(--accent-green,#4ade80)"></span>
      <span style="width:${brp}%;background:var(--accent-red,#f87171)"></span>
      <span style="width:${np}%;background:var(--text-muted,#666)"></span>
    </span>`;
  }

  function filterThemesBySearch(themes, search) {
    if (!search) return themes || [];
    const q = String(search).trim().toLowerCase();
    if (!q) return themes || [];
    return (themes || []).filter(t => String(t.theme || '').toLowerCase().includes(q));
  }

  function themeQoqForPeriod(themeQoqByQ, period) {
    if (!themeQoqByQ || !period || period.all || period.quarters?.length !== 1) return null;
    return themeQoqByQ[period.quarters[0]] || null;
  }

  function renderThemeMomentum(shifts, priorLabel, escapeHtml, opts) {
    const { search } = opts || {};
    let rows = shifts || [];
    if (search) {
      const q = String(search).trim().toLowerCase();
      rows = rows.filter(r => String(r.theme || '').toLowerCase().includes(q));
    }
    if (!rows.length) {
      return '<p class="subhead">No quarter-over-quarter theme shifts for this period.</p>';
    }
    return `
      <p class="tier-sub" style="margin-bottom:8px">Fund-count change vs ${escapeHtml(priorLabel || 'prior quarter')} — macro momentum only (ticker shifts live in <strong>Consensus</strong>).</p>
      <table class="darwin-table" id="insights-theme-momentum-table">
        <thead><tr><th>Theme</th><th>Funds</th><th>Δ funds</th><th>Δ bull</th><th>Δ bear</th><th>Top tickers</th><th></th></tr></thead>
        <tbody>
          ${rows.slice(0, 40).map(r => `
            <tr>
              <td><button type="button" class="linkish" data-theme-drill="${escapeHtml(r.theme)}">${escapeHtml(r.theme)}</button></td>
              <td class="mono">${r.fund_count || 0}</td>
              <td>${formatConsensusDelta(r.delta_funds)}</td>
              <td>${formatConsensusDelta(r.delta_bullish)}</td>
              <td>${formatConsensusDelta(r.delta_bearish)}</td>
              <td class="mono" style="font-size:11px">${(r.top_tickers || []).slice(0, 5).join(', ') || '—'}</td>
              <td><button type="button" class="linkish" data-theme-drill="${escapeHtml(r.theme)}" style="font-size:11px">Letters</button></td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  function renderThemeRankings(themes, escapeHtml, opts) {
    const { period, timeModel, viewMode = 'snapshot', themeQoq = null, search = '', glossary = null } = opts || {};
    const viewTabs = [
      { id: 'snapshot', label: 'Snapshot' },
      { id: 'momentum', label: 'Momentum' },
    ];
    const tabNav = `<nav class="view-tabs" id="insights-theme-view-tabs" style="margin-bottom:10px">
      ${viewTabs.map(t => `<button type="button" class="view-tab${viewMode === t.id ? ' active' : ''}" data-theme-view-mode="${t.id}">${t.label}</button>`).join('')}
    </nav>`;

    if (viewMode === 'momentum') {
      const qoq = themeQoq;
      if (!qoq?.shifts?.length) {
        return tabNav + '<p class="subhead">Momentum view needs a single indexed quarter (try <strong>Latest</strong> or a specific Q).</p>';
      }
      return tabNav + renderThemeMomentum(qoq.shifts, quarterLabel(qoq.prior_quarter), escapeHtml, { search });
    }

    const filtered = filterThemesBySearch(themes, search);
    if (!filtered?.length) {
      return tabNav + renderPeriodEmptyState('themes', period, timeModel, escapeHtml);
    }
    const glossaryMap = glossary || {};
    return `
      ${tabNav}
      <p class="tier-sub" style="margin-bottom:10px">
        Macro themes from letter extractions — frequency and stance mix.
        Ticker agreement: <strong>Consensus</strong>. Source letters: <strong>Letters</strong>.
      </p>
      <table class="darwin-table" id="insights-theme-table">
        <thead><tr><th>Theme</th><th>Funds</th><th>Sentiment</th><th>Bull</th><th>Bear</th><th>Neutral</th><th>Top tickers</th><th></th></tr></thead>
        <tbody>
          ${filtered.map(t => {
            const kw = (glossaryMap[t.theme] || []).slice(0, 4).join(', ');
            const title = kw ? ` title="${escapeHtml(kw)}"` : '';
            return `
            <tr>
              <td><button type="button" class="linkish" data-theme-drill="${escapeHtml(t.theme)}"${title}>${escapeHtml(t.theme)}</button></td>
              <td class="mono">${t.letter_count ?? t.fund_count ?? 0}</td>
              <td>${themeSentimentBar(t)}</td>
              <td>${t.bullish || 0}</td>
              <td>${t.bearish || 0}</td>
              <td>${t.neutral || 0}</td>
              <td class="mono" style="font-size:11px">${(t.top_tickers || []).slice(0, 6).join(', ') || '—'}</td>
              <td><button type="button" class="linkish" data-theme-drill="${escapeHtml(t.theme)}" style="font-size:11px">Letters</button></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>`;
  }

  function filterThemesForBook(themes, letterIndex, period, bookOnly) {
    if (!bookOnly || !themes?.length) return themes || [];
    const activeThemes = new Set();
    filterLetterIndex(letterIndex, { period, bookOnly: true }).forEach(row => {
      (row.themes || []).forEach(theme => {
        const label = typeof theme === 'string' ? theme : theme?.theme;
        if (label) activeThemes.add(String(label).toLowerCase());
      });
    });
    if (!activeThemes.size) return [];
    return themes.filter(t => activeThemes.has(String(t.theme || '').toLowerCase()));
  }

  function themesForPeriod(byQ, fallback, period) {
    if (!period || period.all) return byQ?.all || fallback || [];
    if (period.quarters.length === 1 && byQ?.[period.quarters[0]]) return byQ[period.quarters[0]];
    const merged = new Map();
    period.quarters.forEach(qid => {
      (byQ?.[qid] || []).forEach(t => {
        const key = t.theme || 'Other';
        const row = merged.get(key) || {
          theme: key,
          letter_count: 0,
          fund_count: 0,
          bullish: 0,
          bearish: 0,
          neutral: 0,
          top_tickers: [],
          _tickers: new Set(),
        };
        row.letter_count += Number(t.letter_count || 0);
        row.fund_count += Number(t.fund_count || 0);
        row.bullish += Number(t.bullish || 0);
        row.bearish += Number(t.bearish || 0);
        row.neutral += Number(t.neutral || 0);
        (t.top_tickers || []).forEach(tk => row._tickers.add(tk));
        merged.set(key, row);
      });
    });
    return Array.from(merged.values())
      .map(row => ({ ...row, top_tickers: Array.from(row._tickers).slice(0, 8), _tickers: undefined }))
      .sort((a, b) => (b.letter_count - a.letter_count) || String(a.theme).localeCompare(String(b.theme)));
  }

  function renderLetterIndex(rows, escapeHtml, linkHtml, ghRepo, onFundClick, positionStats, period, timeModel) {
    if (!rows?.length) {
      return renderPeriodEmptyState('letters', period, timeModel, escapeHtml);
    }
    const statsLine = positionStats
      ? `<p class="tier-sub" style="margin-bottom:8px">${positionStats}</p>`
      : '';
    const fmtTickers = (list) => (list || []).slice(0, 5).join(', ') || '—';
    return `
      ${statsLine}
      <table class="darwin-table" id="insights-letter-table">
        <thead><tr><th>Date</th><th>Fund</th><th>Quarter</th><th>Themes</th><th>Tickers</th><th>New / Add</th><th>Trim / Exit</th><th>Our overlap</th><th>Summary</th><th>Source</th></tr></thead>
        <tbody>
          ${rows.slice(0, 80).map(r => `
            <tr class="clickable-row" data-fund-id="${escapeHtml(r.fund_id || '')}">
              <td class="mono">${escapeHtml(r.letter_date || '—')}</td>
              <td>${onFundClick ? `<button type="button" class="linkish" data-fund-id="${escapeHtml(r.fund_id || '')}">${escapeHtml(r.fund)}</button>` : escapeHtml(r.fund)}</td>
              <td class="mono">${escapeHtml(r.quarter || '—')}</td>
              <td style="font-size:11px">${(r.themes || []).slice(0, 4).join(', ') || '—'}</td>
              <td class="mono" style="font-size:11px">${(r.tickers || []).slice(0, 5).join(', ') || '—'}</td>
              <td class="mono" style="font-size:11px;color:var(--accent-green)">${fmtTickers(r.adds)}</td>
              <td class="mono" style="font-size:11px;color:var(--accent-amber)">${fmtTickers([...(r.trims || []), ...(r.exits || [])])}</td>
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
              <td>${recordEvidenceLink(f, linkHtml, ghRepo)}</td>
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
          ${(profile.letters || []).length} letter(s) · latest ${escapeHtml(latest.quarter || '—')} · ${recordEvidenceLink(latest, linkHtml, ghRepo)}
        </p>
      </div>`;
  }

  function parseQuarter(value) {
    const text = String(value || '').trim();
    if (!text) return null;
    let m = text.match(/(20\d{2})\s*Q([1-4])/i)
      || text.match(/(20\d{2})\s*([1-4])Q/i)
      || text.match(/(20\d{2})Q([1-4])/i);
    if (m) {
      const year = Number(m[1]);
      const quarter = Number(m[2]);
      return { id: `${year}Q${quarter}`, year, quarter, label: `Q${quarter} ${year}` };
    }
    m = text.match(/^(20\d{2})-(\d{2})-\d{2}/);
    if (m) {
      const year = Number(m[1]);
      const month = Number(m[2]);
      if (month >= 1 && month <= 12) {
        const quarter = Math.floor((month - 1) / 3) + 1;
        return { id: `${year}Q${quarter}`, year, quarter, label: `Q${quarter} ${year}` };
      }
    }
    return null;
  }

  function quarterLabel(id) {
    const q = parseQuarter(id);
    return q ? q.label : String(id || 'All history');
  }

  function addQuarter(map, value, meta) {
    const q = parseQuarter(value);
    if (!q) return null;
    const row = map.get(q.id) || {
      id: q.id,
      label: q.label,
      year: q.year,
      quarter: q.quarter,
      indexed_count: 0,
      document_count: 0,
      source_folder_count: 0,
      source_folder_url: null,
    };
    row.indexed_count += Number(meta?.indexed_count || 0);
    row.document_count += Number(meta?.document_count || 0);
    row.source_folder_count += Number(meta?.source_folder_count || 0);
    row.source_folder_url = row.source_folder_url || meta?.source_folder_url || null;
    map.set(q.id, row);
    return q.id;
  }

  function minIndexedYear(letterIndex) {
    let min = null;
    for (const row of letterIndex || []) {
      const q = parseQuarter(row.quarter || row.letter_date);
      if (q && (min === null || q.year < min)) min = q.year;
    }
    return min ?? 2011;
  }

  function quarterSortDesc(a, b) {
    return (b.year - a.year) || (b.quarter - a.quarter);
  }

  function collectIndexedQuarterIds(insights) {
    const ids = new Set();
    const fromPayload = insights?.time_periods?.indexed_quarters;
    if (Array.isArray(fromPayload) && fromPayload.length) {
      fromPayload.forEach(q => { if (q) ids.add(String(q)); });
      return ids;
    }
    (insights?.letter_index || []).forEach(row => {
      const q = parseQuarter(row.quarter || row.letter_date);
      if (q) ids.add(q.id);
    });
    Object.keys(insights?.theme_rankings_by_quarter || {}).forEach(q => {
      if (q && q !== 'all') ids.add(q);
    });
    Object.keys(insights?.consensus?.by_quarter || {}).forEach(q => {
      if (q && q !== 'all') ids.add(q);
    });
    return ids;
  }

  function resolveLatestIndexedQuarter(insights, indexedIds) {
    const explicit = insights?.time_periods?.latest_indexed_quarter;
    if (explicit && parseQuarter(explicit)) return explicit;
    return Array.from(indexedIds || [])
      .map(id => parseQuarter(id))
      .filter(Boolean)
      .sort(quarterSortDesc)[0]?.id || null;
  }

  function buildTimeModel(insights, documentCatalog) {
    const floorYear = minIndexedYear(insights?.letter_index);
    const map = new Map();
    const timePeriods = documentCatalog?.time_periods || {};
    (timePeriods.available_quarters || []).forEach(q => {
      if ((q.year || parseQuarter(q.id || q.label)?.year || 0) < floorYear) return;
      addQuarter(map, q.id || q.label, {
        document_count: q.document_count,
        source_folder_count: q.source_folder_count,
        source_folder_url: q.source_folder_url,
      });
    });
    Object.entries(insights?.theme_rankings_by_quarter || {})
      .filter(([q]) => q && q !== 'all')
      .forEach(([q]) => addQuarter(map, q, {}));
    (insights?.letter_index || []).forEach(r => addQuarter(map, r.quarter || r.letter_date, { indexed_count: 1 }));
    (insights?.fund_registry || []).forEach(r => addQuarter(map, r.quarter || r.letter_date, {}));
    (insights?.consensus?.quarters || []).forEach(q => addQuarter(map, q, {}));
    Object.entries((documentCatalog?.summary || {}).by_quarter || {})
      .forEach(([q, count]) => {
        if ((parseQuarter(q)?.year || 0) < floorYear) return;
        addQuarter(map, q, { document_count: count });
      });

    let quarters = Array.from(map.values())
      .filter(q => q.year >= floorYear)
      .sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    if (quarters.length && quarters.length < 12) {
      const latestYear = quarters[0].year;
      for (let year = latestYear - 1; year >= Math.max(latestYear - 12, floorYear); year -= 1) {
        for (let q = 4; q >= 1; q -= 1) addQuarter(map, `${year}Q${q}`, {});
      }
      quarters = Array.from(map.values())
        .filter(q => q.year >= floorYear)
        .sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    }
    const indexedQuarterSet = collectIndexedQuarterIds(insights);
    indexedQuarterSet.forEach(qid => {
      const row = map.get(qid);
      if (row && !row.indexed_count) row.indexed_count = 1;
    });
    quarters = Array.from(map.values())
      .filter(q => q.year >= floorYear)
      .sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    const latestIndexedQuarter = resolveLatestIndexedQuarter(insights, indexedQuarterSet);
    const latestCatalogQuarter = timePeriods.latest_catalog_quarter || timePeriods.latest_quarter || null;
    const indexedYears = Array.from(new Set(
      quarters.filter(q => indexedQuarterSet.has(q.id) || q.indexed_count > 0).map(q => q.year),
    )).sort((a, b) => b - a);
    const years = Array.from(new Set(quarters.map(q => q.year))).sort((a, b) => b - a);
    const byId = Object.fromEntries(quarters.map(q => [q.id, q]));
    return {
      quarters,
      years,
      indexedYears,
      indexedQuarterSet,
      byId,
      latestQuarter: latestIndexedQuarter || latestCatalogQuarter || quarters.find(q => q.indexed_count > 0)?.id || quarters[0]?.id || null,
      latestIndexedQuarter,
      latestCatalogQuarter,
      latestYear: (parseQuarter(latestIndexedQuarter) || quarters.find(q => indexedQuarterSet.has(q.id)) || quarters[0])?.year || null,
    };
  }

  function periodFromSelection(selection, timeModel) {
    const raw = selection || 'latest';
    const allQuarters = timeModel.quarters.map(q => q.id);
    let ids = [];
    let label = 'All history';
    let selectedYear = timeModel.latestYear;
    if (raw === 'latest') {
      ids = timeModel.latestQuarter ? [timeModel.latestQuarter] : allQuarters.slice(0, 1);
      label = ids[0] ? quarterLabel(ids[0]) : 'Latest quarter';
      selectedYear = parseQuarter(ids[0])?.year || selectedYear;
    } else if (raw === 'last4') {
      ids = allQuarters.slice(0, 4);
      label = 'Last 4 quarters';
    } else if (raw === 'last8') {
      ids = allQuarters.slice(0, 8);
      label = 'Last 8 quarters';
    } else if (raw === 'since2020') {
      ids = allQuarters.filter(id => (parseQuarter(id)?.year || 0) >= 2020);
      label = 'Since 2020';
    } else if (raw === 'all') {
      ids = allQuarters;
      label = 'All history';
    } else if (raw.startsWith('year:')) {
      selectedYear = Number(raw.split(':')[1]);
      ids = allQuarters.filter(id => parseQuarter(id)?.year === selectedYear);
      label = String(selectedYear);
    } else {
      const q = parseQuarter(raw);
      if (q) {
        ids = [q.id];
        label = q.label;
        selectedYear = q.year;
      }
    }
    return {
      id: raw,
      label,
      quarters: ids,
      quarterSet: new Set(ids),
      all: raw === 'all',
      selectedYear,
    };
  }

  function recordQuarterIds(record, fields) {
    const ids = new Set();
    for (const field of fields) {
      const q = parseQuarter(record?.[field]);
      if (q) ids.add(q.id);
    }
    return ids;
  }

  function periodMatchesRecord(record, period, fields) {
    if (!period || period.all) return true;
    const ids = recordQuarterIds(record, fields);
    if (!ids.size) return false;
    for (const qid of ids) {
      if (period.quarterSet.has(qid)) return true;
    }
    return false;
  }

  function periodCoverage(period, timeModel, letterIndex, funds) {
    const letters = (letterIndex || []).filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    const fundRows = (funds || []).filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    const quarterRows = period.all
      ? timeModel.quarters
      : period.quarters.map(id => timeModel.byId[id]).filter(Boolean);
    const folderCount = quarterRows.reduce((sum, q) => sum + (q.source_folder_count || 0), 0);
    const drivePdfCount = quarterRows.reduce((sum, q) => sum + (q.document_count || 0), 0);
    const indexedInPeriod = quarterRows.reduce((sum, q) => sum + (q.indexed_count || 0), 0);
    return {
      letters: letters.length,
      funds: fundRows.length,
      quarters: period.all ? timeModel.quarters.length : period.quarters.length,
      folderCount,
      drivePdfCount,
      indexedInPeriod,
    };
  }

  function dedupeEvents(events) {
    const best = new Map();
    for (const event of events || []) {
      const key = [
        event.source || '',
        event.ticker || '',
        event.event_type || '',
        event.observed_at || '',
        event.title || '',
      ].join('|');
      const prev = best.get(key);
      if (!prev || Number(event.score || 0) > Number(prev.score || 0)) {
        best.set(key, event);
      }
    }
    return Array.from(best.values());
  }

  function filterEvents(events, opts) {
    const { search, bookOnly, period, knownTickers, needsReviewOnly, eventTier } = opts || {};
    let list = dedupeEvents(events);
    if (period && !period.all) {
      list = list.filter(e => periodMatchesRecord(e, period, ['quarter', 'observed_at', 'date', 'as_of']));
    }
    if (bookOnly) {
      list = list.filter(e => e.in_our_book || e.portfolio_relevance >= 1);
    }
    if (needsReviewOnly) {
      list = list.filter(e => e.needs_review || e.triage_verdict === 'human_review');
    }
    const tier = eventTier || 'signal';
    if (tier === 'signal') {
      list = list.filter(e => e.tier === 'signal' && e.feed_eligible !== false);
    } else if (tier === 'context') {
      list = list.filter(e => e.tier === 'context' && e.feed_eligible !== false);
    } else if (tier === 'noise') {
      list = list.filter(e => e.tier === 'noise' || e.feed_eligible === false);
    }
    if (search) {
      const tickers = knownTickers || [];
      list = list.filter(e => SearchMatch.matchEvent(e, search, tickers));
    }
    list.sort((a, b) => {
      const da = a.observed_at || '';
      const db = b.observed_at || '';
      if (da !== db) return db.localeCompare(da);
      return Number(b.materiality || b.score || 0) - Number(a.materiality || a.score || 0);
    });
    return list;
  }

  function renderEventTierTabs(activeTier, summary, escapeHtml) {
    const counts = summary || {};
    const tiers = [
      { id: 'signal', label: `Signal (${counts.signal || 0})` },
      { id: 'context', label: `Context (${counts.context || 0})` },
      { id: 'all', label: 'All' },
      { id: 'noise', label: `Noise (${counts.noise || 0})` },
    ];
    return `<nav class="source-pills" id="insights-event-tier-tabs" style="margin-bottom:10px">
      ${tiers.map(t => `<button type="button" class="filter-btn source-pill${activeTier === t.id ? ' active' : ''}" data-event-tier="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
    </nav>`;
  }

  function eventTierBadge(event) {
    const tier = event.tier || 'context';
    if (tier === 'signal') return 'badge-ok';
    if (tier === 'noise') return 'badge-warn';
    return 'badge-us';
  }

  function parserConfidenceBadge(confidence) {
    const level = String(confidence || 'low').toLowerCase();
    if (level === 'high') return 'badge-ok';
    if (level === 'medium' || level === 'med') return 'badge-us';
    return 'badge-warn';
  }

  function fmtFilingValue(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    const num = Number(value);
    if (Math.abs(num) >= 1000) return num.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (Math.abs(num % 1) > 0.01) return num.toFixed(2);
    return String(num);
  }

  function renderFilingEvidenceLinks(event, linkHtml, ghRepo) {
    const links = [];
    const filingRef = event.source_filing_ref || (event.verification && event.verification.source_filing_ref);
    const extractRef = event.extract_ref || (event.verification && event.verification.extract_ref);
    const filingLabel = event.evidence_label || (event.verification && event.verification.source_label) || 'Filing';
    if (filingRef) {
      links.push(evidenceLink(filingRef, linkHtml, ghRepo, filingLabel));
    }
    if (extractRef) {
      links.push(evidenceLink(extractRef, linkHtml, ghRepo, event.extract_label || 'extract'));
    }
    if (!links.length) {
      return evidenceLink(event.evidence_url || event.evidence_ref, linkHtml, ghRepo, event.evidence_label);
    }
    return links.join(' ');
  }

  function renderEventVerificationStrip(event, escapeHtml) {
    const v = event.verification;
    if (!v || event.source !== 'filing') return '';
    const confClass = parserConfidenceBadge(v.parser_confidence || event.confidence);
    const confLabel = String(v.parser_confidence || event.confidence || 'low').toUpperCase();
    const parts = [
      v.filing_form ? `${v.filing_form}` : null,
      v.filing_date ? `filed ${v.filing_date}` : null,
      v.period_end ? `period ${v.period_end}` : null,
      v.xbrl_tag ? `tag ${v.xbrl_tag}` : null,
    ].filter(Boolean);
    const values = (v.prior_value != null && v.current_value != null)
      ? `Prior ${fmtFilingValue(v.prior_value)} → Current ${fmtFilingValue(v.current_value)} (${v.unit || 'USD thousands'})`
      : (v.current_value != null ? `Current ${fmtFilingValue(v.current_value)} (${v.unit || 'USD thousands'})` : '');
    const flags = (v.parser_flags || []).length
      ? `<span class="badge badge-warn" title="${escapeHtml((v.parser_flags || []).join(', '))}">review</span>`
      : '';
    const review = event.needs_review ? '<span class="badge badge-warn">needs review</span>' : '';
    return `
      <div class="tier-sub filing-verify-strip" style="margin-top:6px;line-height:1.45">
        ${parts.length ? `<span>${escapeHtml(parts.join(' · '))}</span>` : ''}
        ${values ? `<div>${escapeHtml(values)}</div>` : ''}
        <span class="badge ${confClass}" title="Parser confidence">${escapeHtml(confLabel)}</span>
        ${flags}
        ${review}
        ${v.extract_snippet ? `<button type="button" class="filter-btn source-pill filing-verify-btn" data-verify-event="${escapeHtml(event.id || '')}" style="margin-left:6px;padding:2px 8px;font-size:11px">Verify</button>` : ''}
      </div>`;
  }

  function renderFilingVerifyDrawer(events, escapeHtml, linkHtml, ghRepo) {
    const filingEvents = (events || []).filter(e => e.verification && e.source === 'filing');
    if (!filingEvents.length) return '';
    return `
      <div id="filing-verify-drawer" class="detail-section" style="display:none;margin-top:12px;border:1px solid var(--border);border-radius:8px;padding:12px;background:rgba(255,255,255,0.02)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <strong>Filing verification</strong>
          <button type="button" class="filter-btn" id="filing-verify-close">Close</button>
        </div>
        <div id="filing-verify-body"></div>
      </div>`;
  }

  function renderFilingVerifyBody(event, escapeHtml, linkHtml, ghRepo) {
    const v = event.verification || {};
    const snippet = String(v.extract_snippet || '').split('\n').map(line => escapeHtml(line)).join('<br>');
    const allValues = (v.all_values || []).map(val => escapeHtml(fmtFilingValue(val))).join(', ');
    return `
      <p class="tier-sub"><strong>${escapeHtml(event.ticker || '')}</strong> · ${escapeHtml(event.title || '')}</p>
      <p class="tier-sub">${escapeHtml((v.filing_form || 'Filing') + (v.filing_date ? ` filed ${v.filing_date}` : '') + (v.period_end ? ` · period ${v.period_end}` : ''))}</p>
      <div style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin-top:10px">
        <div class="research-box" style="margin:0">
          <div class="label" style="font-size:11px;color:var(--text-muted);margin-bottom:6px">Extract lines used</div>
          <pre style="white-space:pre-wrap;margin:0;font-size:12px">${snippet || '—'}</pre>
        </div>
        <div class="research-box" style="margin:0">
          <div class="label" style="font-size:11px;color:var(--text-muted);margin-bottom:6px">Parser context</div>
          <div class="tier-sub">Tag: <span class="mono">${escapeHtml(v.xbrl_tag || '—')}</span></div>
          <div class="tier-sub">Confidence: <span class="badge ${parserConfidenceBadge(v.parser_confidence)}">${escapeHtml(String(v.parser_confidence || 'low').toUpperCase())}</span></div>
          <div class="tier-sub">Flags: ${escapeHtml((v.parser_flags || []).join(', ') || 'none')}</div>
          <div class="tier-sub">All parsed values: ${allValues || '—'}</div>
          <div style="margin-top:8px">${renderFilingEvidenceLinks(event, linkHtml, ghRepo)}</div>
        </div>
      </div>`;
  }

  function attachFilingVerifyHandlers(container, events, escapeHtml, linkHtml, ghRepo) {
    if (!container) return;
    const drawer = container.querySelector('#filing-verify-drawer');
    const body = container.querySelector('#filing-verify-body');
    const closeBtn = container.querySelector('#filing-verify-close');
    const byId = Object.fromEntries((events || []).map(e => [e.id, e]));
    container.querySelectorAll('[data-verify-event]').forEach(btn => {
      btn.addEventListener('click', () => {
        const event = byId[btn.dataset.verifyEvent];
        if (!event || !drawer || !body) return;
        body.innerHTML = renderFilingVerifyBody(event, escapeHtml, linkHtml, ghRepo);
        drawer.style.display = 'block';
        drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    });
    if (closeBtn && drawer) {
      closeBtn.addEventListener('click', () => {
        drawer.style.display = 'none';
      });
    }
  }

  function renderEventQueue(events, escapeHtml, linkHtml, ghRepo, opts) {
    const eventTier = (opts && opts.eventTier) || 'signal';
    const triageSummary = (opts && opts.triageSummary) || {};
    const rows = filterEvents(events, opts).slice(0, 120);
    const tierTabs = renderEventTierTabs(eventTier, triageSummary, escapeHtml);
    if (!rows.length) {
      return `${tierTabs}<p class="subhead">No ranked events match this view.</p>`;
    }
    return `
      ${tierTabs}
      <table class="darwin-table" id="insights-event-table">
        <thead><tr><th>Relevance</th><th>Date</th><th>Ticker</th><th>Source</th><th>Axis</th><th>Event</th><th>Evidence</th></tr></thead>
        <tbody>
          ${rows.map(e => {
            const directionClass = e.direction === 'bullish' ? 'badge-ok' : (e.direction === 'bearish' ? 'badge-bad' : 'badge-us');
            const ticker = e.ticker ? `<span class="mono">${escapeHtml(e.ticker)}</span>` : '<span class="tier-sub">portfolio</span>';
            const confTip = e.verification
              ? ` title="Parser ${escapeHtml(String(e.verification.parser_confidence || e.confidence || 'med'))}${e.needs_review ? ' · needs review' : ''}"`
              : '';
            const tierLabel = String(e.tier || 'context');
            const reviewBadge = e.triage_verdict === 'human_review'
              ? ' <span class="badge badge-warn">review</span>'
              : '';
            return `
              <tr>
                <td class="mono"${confTip}><span class="badge ${eventTierBadge(e)}">${escapeHtml(tierLabel)}</span> ${Number(e.materiality || e.score || 0)}${reviewBadge}</td>
                <td class="mono">${escapeHtml(e.observed_at || 'n/a')}</td>
                <td>${ticker}</td>
                <td><span class="badge badge-us">${escapeHtml(e.source_label || SOURCE_LABEL[e.source] || e.source || 'source')}</span></td>
                <td>${escapeHtml(AXIS_LABEL[e.impact_axis] || e.impact_axis || 'context')}</td>
                <td style="min-width:280px">
                  <div><span class="badge ${directionClass}">${escapeHtml(e.direction || 'neutral')}</span> <strong>${escapeHtml(e.title || 'Insight')}</strong></div>
                  <div class="tier-sub" style="margin-top:4px">${escapeHtml((e.summary || '').slice(0, 220))}</div>
                  ${renderEventVerificationStrip(e, escapeHtml)}
                </td>
                <td>${renderFilingEvidenceLinks(e, linkHtml, ghRepo)}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>
      ${renderFilingVerifyDrawer(events, escapeHtml, linkHtml, ghRepo)}
      ${(events || []).length > rows.length ? `<p class="tier-sub">${(events || []).length - rows.length} more events outside the current table window.</p>` : ''}`;
  }

  function filterTickerEssentials(tickers, opts) {
    const { search, bookOnly, sourceFilter, knownTickers } = opts || {};
    let rows = tickers || [];
    if (bookOnly) {
      rows = rows.filter(t => t.in_holdings);
    }
    if (sourceFilter && sourceFilter !== 'all') {
      rows = rows.filter(t => {
        const e = t.essential_insights || {};
        const sources = new Set(e.source_mix || []);
        if (sourceFilter === 'ownership') {
          return sources.has('superinvestor_letter') || sources.has('insider') || e.owner;
        }
        if (sourceFilter === 'letters') {
          return sources.has('superinvestor_letter') || e.owner?.source === 'superinvestor_letter';
        }
        if (sourceFilter === 'macro') {
          return e.macro_only || sources.has('macro');
        }
        return sources.has(sourceFilter);
      });
    }
    if (search) {
      const tickers = knownTickers || [];
      rows = rows.filter(t => SearchMatch.matchTickerEssential(t, search, tickers));
    }
    return rows;
  }

  function renderPortfolioMacroStrip(portfolioMacro, escapeHtml, linkHtml) {
    const rows = portfolioMacro || [];
    if (!rows.length) return '';
    return `
      <div class="detail-section" style="margin-bottom:14px">
        <h3 style="font-size:14px;margin-bottom:8px">Portfolio macro (shown once)</h3>
        <div class="research-box essential-box">
          ${rows.slice(0, 4).map(item => renderInsightItem(item, escapeHtml, linkHtml)).join('')}
        </div>
        <p class="tier-sub">Macro indices are portfolio-wide context. Per-ticker rows link here when no ticker-specific signal exists.</p>
      </div>`;
  }

  function renderTickerSourceFilters(activeFilter, escapeHtml) {
    const filters = [
      { id: 'ownership', label: 'Letters + insider' },
      { id: 'letters', label: 'Letters' },
      { id: 'all', label: 'All sources' },
      { id: 'macro', label: 'Macro only' },
    ];
    return `
      <nav class="source-pills" id="insights-ticker-source-tabs" style="margin-bottom:10px">
        ${filters.map(f => `<button type="button" class="filter-btn source-pill${activeFilter === f.id ? ' active' : ''}" data-ticker-source-filter="${escapeHtml(f.id)}">${escapeHtml(f.label)}</button>`).join('')}
      </nav>`;
  }

  function renderSparkline(points, direction) {
    const values = (points || []).map(p => Number(p.value)).filter(v => Number.isFinite(v));
    if (values.length < 2) return '';
    const width = 90;
    const height = 22;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const step = width / (values.length - 1);
    const coords = values
      .map((v, i) => `${(i * step).toFixed(1)},${(height - 3 - ((v - min) / span) * (height - 6)).toFixed(1)}`)
      .join(' ');
    const color = direction === 'accelerating' ? '#34d399' : direction === 'decelerating' ? '#f87171' : '#818cf8';
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block">
      <polyline fill="none" stroke="${color}" stroke-width="1.5" points="${coords}" />
    </svg>`;
  }

  function trendBadge(direction, signalTier) {
    const tierHint = signalTier === 'confirmed' ? ' (confirmed)' : signalTier === 'emerging' ? ' (emerging)' : '';
    if (direction === 'accelerating' || direction === 'upshift') return `<span class="badge badge-ok" title="Growth accelerating${tierHint}">▲▲</span>`;
    if (direction === 'decelerating' || direction === 'downshift') return `<span class="badge badge-bad" title="Growth decelerating${tierHint}">▼▼</span>`;
    return '<span class="badge badge-us">steady</span>';
  }

  function leadershipRiskBadge(risk, escapeHtml) {
    if (!risk || !risk.level || risk.level === 'none') return '';
    const cls = risk.level === 'elevated' ? 'badge-bad' : 'badge-us';
    return `<span class="badge ${cls}" title="${escapeHtml(risk.label || risk.level)}">gov ${risk.level}</span>`;
  }

  function signalTierBadge(signalTier, escapeHtml) {
    if (signalTier === 'confirmed') return '<span class="badge badge-ok" title="Two consecutive quarters beyond noise">confirmed</span>';
    if (signalTier === 'emerging') return `<span class="badge badge-us" title="Latest quarter only">emerging</span>`;
    return '<span class="tier-sub">—</span>';
  }

  function strengthLabel(metric) {
    const s = metric.strength != null
      ? metric.strength
      : Math.abs(metric.accel || 0) / Math.max(metric.threshold || 1e-9, 1e-9);
    if (s >= 2) return `${s.toFixed(1)}× high`;
    if (s >= 1) return `${s.toFixed(1)}×`;
    return `${s.toFixed(1)}× weak`;
  }

  function dataTierBadge(trends, escapeHtml) {
    const tier = trends && trends.data_tier;
    if (!tier) return '';
    const meta = {
      sec_fundamentals: { label: 'SEC', title: 'Quarterly SEC XBRL fundamentals available', cls: 'badge-ok' },
      equity_model: { label: 'Model', title: 'Equity model / dossier KPI series', cls: 'badge-us' },
      sec_pending: { label: 'SEC pending', title: 'US CIK resolved but fundamentals not cached yet', cls: 'badge-warn' },
      news_governance: { label: 'News only', title: 'News/governance signals only — no financial trend series', cls: 'badge-warn' },
      none: { label: 'No trend data', title: 'No SEC, model, or dossier KPI series for this holding', cls: 'badge-warn' },
    }[tier] || { label: tier, title: tier, cls: 'badge-us' };
    return `<span class="badge ${meta.cls}" title="${escapeHtml(meta.title)}" style="margin-right:4px">${escapeHtml(meta.label)}</span>`;
  }

  function renderTickerTrendBadges(trends, escapeHtml) {
    const entry = trends || {};
    const parts = [];
    const tierBadge = dataTierBadge(entry, escapeHtml);
    if (tierBadge && !entry.has_trend_data) parts.push(tierBadge);
    const gov = leadershipRiskBadge(entry.leadership_risk, escapeHtml);
    if (gov) parts.push(gov);
    const bms = entry.business_momentum;
    if (bms && bms.direction && bms.direction !== 'steady') {
      parts.push(`<span title="${escapeHtml(bms.label || bms.direction)}" style="margin-right:4px">${trendBadge(bms.direction, 'confirmed')}</span>`);
    }
    const metrics = entry.metrics || [];
    const firing = metrics.filter(m => m.display && (m.direction === 'accelerating' || m.direction === 'decelerating' || m.direction === 'downshift' || m.direction === 'upshift'));
    if (!firing.length) {
      const fallback = metrics.filter(m => m.direction === 'accelerating' || m.direction === 'decelerating' || m.direction === 'downshift');
      if (!fallback.length) return parts.join('') || tierBadge;
      return parts.join('') + fallback.slice(0, 2).map(m =>
        `<span title="${escapeHtml(`${m.label || m.metric}: ${m.direction}`)}" style="margin-right:4px">${trendBadge(m.direction, m.signal_tier)}</span>`
      ).join('');
    }
    return parts.join('') + firing.slice(0, 2).map(m =>
      `<span title="${escapeHtml(`${m.label || m.metric}: ${m.direction}`)}" style="margin-right:4px">${trendBadge(m.direction, m.signal_tier)}</span>`
    ).join('');
  }

  function formatGrowth(metric) {
    const latest = metric.growth_latest;
    const prior = metric.growth_prior;
    if (latest == null || prior == null) return '—';
    if (metric.mode === 'diff') {
      return `${prior >= 0 ? '+' : ''}${prior} → ${latest >= 0 ? '+' : ''}${latest}`;
    }
    const pct = v => `${(v * 100).toFixed(1)}%`;
    const suffix = metric.basis === 'yoy' ? ' YoY' : '';
    return `${pct(prior)} → ${pct(latest)}${suffix}`;
  }

  const TREND_SOURCE_LABELS = {
    sec_fundamentals: { label: 'SEC XBRL', title: 'Quarterly fundamentals from SEC companyfacts (real fiscal periods, YoY basis)' },
    equity_model: { label: 'Equity model', title: 'Model observation series from equity_models.json' },
    news_flow: { label: 'News flow', title: 'Monthly news item counts (accumulated history)' },
    peer_relative: { label: 'Peer rel.', title: 'YoY growth vs investment-sleeve peers' },
    earnings_revision: { label: 'EPS rev.', title: 'Consensus EPS surprise / revision streak' },
  };

  function trendSourceBadge(source, escapeHtml) {
    const meta = TREND_SOURCE_LABELS[source] || { label: source || '?', title: source || '' };
    return `<span class="badge badge-us" title="${escapeHtml(meta.title)}">${escapeHtml(meta.label)}</span>`;
  }

  function renderInflectionCoverage(kpiTrends) {
    const cov = (kpiTrends && kpiTrends.coverage) || null;
    if (!cov) return '';
    const parts = [
      cov.resolvable_ciks != null
        ? `${cov.fundamentals_tickers || 0}/${cov.resolvable_ciks} SEC CIK fundamentals`
        : `${cov.fundamentals_tickers || 0}/${cov.universe || '?'} tickers with SEC quarterly fundamentals`,
      `${cov.analyzed_tickers || cov.universe || 0} in universe`,
    ];
    if (cov.displayed_count != null) parts.push(`${cov.displayed_count} displayed signals`);
    if (cov.confirmed_count != null) parts.push(`${cov.confirmed_count} confirmed`);
    if (cov.regime_downshift_count != null) parts.push(`${cov.regime_downshift_count} regime downshifts`);
    if (cov.stale_suppressed_count) parts.push(`${cov.stale_suppressed_count} stale series suppressed`);
    if (cov.leadership_risk_watch) parts.push(`${cov.leadership_risk_watch} leadership/gov watch`);
    if (cov.missing_fundamentals && cov.missing_fundamentals.length) {
      parts.push(`${cov.missing_fundamentals.length} resolvable CIK(s) missing fundamentals cache`);
    }
    if (cov.no_trend_data && cov.no_trend_data.length) {
      parts.push(`${cov.no_trend_data.length} without financial trend data`);
    }
    if (cov.peer_relative_count != null && cov.peer_relative_count) parts.push(`${cov.peer_relative_count} peer-relative`);
    if (cov.earnings_revision_count != null && cov.earnings_revision_count) parts.push(`${cov.earnings_revision_count} EPS revision`);
    if (cov.suspect_points_excluded) parts.push(`${cov.suspect_points_excluded} suspect datapoints excluded`);
    return `<p class="tier-sub" style="margin-bottom:4px">Coverage: ${parts.join(' · ')}. Operating flow metrics prioritized; balance-sheet drift hidden by default.</p>`;
  }

  function renderInflectionRollup(kpiTrends, escapeHtml) {
    const byTicker = (kpiTrends && kpiTrends.by_ticker) || {};
    const rows = Object.entries(byTicker)
      .map(([ticker, entry]) => {
        const bms = entry.business_momentum;
        const displayed = (entry.metrics || []).filter(m => m.display);
        if (!bms && !displayed.length) return null;
        const direction = (bms && bms.direction) || (displayed[0] && displayed[0].direction) || 'steady';
        if (direction !== 'accelerating' && direction !== 'decelerating') return null;
        const labels = displayed.map(m => m.label || m.metric).slice(0, 3);
        const score = bms && bms.score != null ? bms.score : null;
        return { ticker, direction, label: bms && bms.label, labels, score, strength: displayed[0] && displayed[0].strength };
      })
      .filter(Boolean)
      .sort((a, b) => Math.abs(b.score || b.strength || 0) - Math.abs(a.score || a.strength || 0))
      .slice(0, 24);
    if (!rows.length) return '';
    return `
      <div style="margin-bottom:12px">
        <h3 style="margin:0 0 6px;font-size:13px">Ticker momentum rollup</h3>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          ${rows.map(r => `
            <button type="button" class="badge ${r.direction === 'accelerating' ? 'badge-ok' : 'badge-bad'} linkish" data-select-ticker="${escapeHtml(r.ticker)}" title="${escapeHtml(r.label || r.labels.join(', '))}">
              ${escapeHtml(r.ticker)} ${r.direction === 'accelerating' ? '▲' : '▼'}${r.score != null ? ` ${r.score.toFixed(2)}` : ''}
            </button>`).join('')}
        </div>
      </div>`;
  }

  function inflectionTierTabs(activeTier, escapeHtml) {
    const tiers = [
      { id: 'displayed', label: 'Displayed' },
      { id: 'regime', label: 'Growth regime' },
      { id: 'peer', label: 'Peer / EPS' },
      { id: 'confirmed', label: 'Confirmed' },
      { id: 'emerging', label: 'Emerging' },
      { id: 'all', label: 'All signals' },
      { id: 'balance_sheet', label: 'Balance sheet' },
    ];
    return `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">
      ${tiers.map(t => `<button type="button" class="view-tab${activeTier === t.id ? ' active' : ''}" data-inflection-tier="${t.id}">${escapeHtml(t.label)}</button>`).join('')}
    </div>`;
  }

  function matchesInflectionTier(row, tier) {
    if (tier === 'all') {
      return row.direction === 'accelerating' || row.direction === 'decelerating' || row.direction === 'downshift' || row.direction === 'upshift';
    }
    if (tier === 'balance_sheet') {
      return (row.tier === 'excluded' || ['cash', 'total_assets', 'stockholders_equity', 'long_term_debt'].includes(String(row.metric || '').split('.').pop()))
        && (row.direction === 'accelerating' || row.direction === 'decelerating');
    }
    if (tier === 'regime') return row.signal_type === 'regime' && (row.direction === 'downshift' || row.direction === 'upshift');
    if (tier === 'peer') return row.signal_type === 'peer_relative' || row.signal_type === 'estimate_revision';
    if (tier === 'confirmed') return row.signal_tier === 'confirmed';
    if (tier === 'emerging') return row.signal_tier === 'emerging';
    return !!row.display;
  }

  function renderInflections(kpiTrends, escapeHtml, opts) {
    const byTicker = (kpiTrends && kpiTrends.by_ticker) || {};
    const search = ((opts && opts.search) || '').trim().toLowerCase();
    const tier = (opts && opts.inflectionTier) || 'displayed';
    const rows = [];
    Object.entries(byTicker).forEach(([ticker, entry]) => {
      (entry.metrics || []).forEach(m => {
        if (!['accelerating', 'decelerating', 'downshift', 'upshift'].includes(m.direction)) return;
        rows.push({ ticker, ...m });
      });
    });
    let filtered = rows.filter(r => matchesInflectionTier(r, tier));
    if (search) {
      filtered = filtered.filter(r => `${r.ticker} ${r.metric} ${r.label} ${r.source}`.toLowerCase().includes(search));
    }
    filtered.sort((a, b) => {
      const sa = a.strength != null ? a.strength : Math.abs(a.accel || 0) / Math.max(a.threshold || 1e-9, 1e-9);
      const sb = b.strength != null ? b.strength : Math.abs(b.accel || 0) / Math.max(b.threshold || 1e-9, 1e-9);
      return sb - sa;
    });
    if (!filtered.length) {
      if (!kpiTrends) {
        return `<p class="subhead">KPI trend data not built yet — run: python _system/scripts/build_fundamental_series.py then build_kpi_trends.py.</p>`;
      }
      return `${renderInflectionCoverage(kpiTrends)}${inflectionTierTabs(tier, escapeHtml)}<p class="subhead">No inflections match this filter — try All signals or Emerging.</p>`;
    }
    const accel = filtered.filter(r => r.direction === 'accelerating').length;
    const decel = filtered.length - accel;
    const cov = (kpiTrends && kpiTrends.coverage) || {};
    return `
      ${renderInflectionCoverage(kpiTrends)}
      ${inflectionTierTabs(tier, escapeHtml)}
      ${tier === 'displayed' || tier === 'confirmed' ? renderInflectionRollup(kpiTrends, escapeHtml) : ''}
      <p class="tier-sub" style="margin-bottom:8px">
        ${accel} accelerating · ${decel} decelerating · ${cov.displayed_count || 0} displayed total · YoY quarterly growth with smoothing, materiality gates, persistence confirmation, and TTM cross-check
      </p>
      <table class="darwin-table" id="insights-inflections-table">
        <thead><tr><th>Ticker</th><th>Metric</th><th>Trend</th><th>Tier</th><th>Growth (prior → latest)</th><th>Strength</th><th>2nd deriv</th><th>Last periods</th><th>Source</th></tr></thead>
        <tbody>
          ${filtered.slice(0, 120).map(r => `
            <tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
              <td>${escapeHtml(r.label || r.metric)}${r.composite && r.composite_members ? `<div class="tier-sub">${escapeHtml(r.composite_members.join(', '))}</div>` : ''}${r.stale ? '<div class="tier-sub">stale series</div>' : ''}${r.revenue_proxy ? '<div class="tier-sub">revenue proxy</div>' : ''}${r.signal_type === 'regime' ? '<div class="tier-sub">growth regime</div>' : ''}</td>
              <td>${trendBadge(r.direction, r.signal_tier)}</td>
              <td>${signalTierBadge(r.signal_tier, escapeHtml)}</td>
              <td class="mono">${escapeHtml(formatGrowth(r))}${r.ttm_agrees === true ? ' ✓TTM' : r.ttm_agrees === false ? ' ✗TTM' : ''}</td>
              <td class="mono">${escapeHtml(strengthLabel(r))}</td>
              <td class="mono">${r.accel != null ? (r.mode === 'diff' ? r.accel : `${(r.accel * 100).toFixed(1)}pp`) : '—'}</td>
              <td>${renderSparkline(r.points, r.direction)}</td>
              <td>${trendSourceBadge(r.source, escapeHtml)}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  function formatFreshnessDisplay(days) {
    if (days == null || !Number.isFinite(Number(days))) {
      return { label: '—', cls: 'tier-sub', stale: false };
    }
    const d = Number(days);
    if (d <= 7) return { label: `${d}d`, cls: 'fresh-ok', stale: false };
    if (d <= 30) return { label: `${d}d`, cls: 'fresh-recent', stale: false };
    if (d <= 365) {
      const mo = Math.max(1, Math.round(d / 30));
      return { label: `${mo}mo`, cls: 'fresh-muted', stale: false };
    }
    const yr = (d / 365).toFixed(1).replace(/\.0$/, '');
    return { label: `${yr}y`, cls: 'fresh-stale', stale: true };
  }

  function tickerAttentionScore(t) {
    const e = t.essential_insights || {};
    const status = e.status || {};
    let score = 0;
    if (e.needs_work) score += 1000;
    if (status.tone === 'risk') score += 500;
    if (status.tone === 'bullish') score += 400;
    if (status.tone === 'ownership') score += 200;
    if (e.freshness_days != null && e.freshness_days <= 30) score += 100;
    if (status.tone === 'stale') score += 80;
    if (e.freshness_days != null && e.freshness_days > 365) score += 60;
    return score;
  }

  function sortTickerEssentialsRows(rows, sortMode) {
    const list = [...(rows || [])];
    if (sortMode === 'alpha') {
      return list.sort((a, b) => String(a.ticker).localeCompare(String(b.ticker)));
    }
    if (sortMode === 'fresh') {
      return list.sort((a, b) => {
        const ad = a.essential_insights?.freshness_days;
        const bd = b.essential_insights?.freshness_days;
        if (ad == null && bd == null) return String(a.ticker).localeCompare(String(b.ticker));
        if (ad == null) return 1;
        if (bd == null) return -1;
        return ad - bd;
      });
    }
    if (sortMode === 'stale') {
      return list.sort((a, b) => {
        const ad = a.essential_insights?.freshness_days ?? -1;
        const bd = b.essential_insights?.freshness_days ?? -1;
        return bd - ad;
      });
    }
    return list.sort((a, b) => {
      const scoreDelta = tickerAttentionScore(b) - tickerAttentionScore(a);
      if (scoreDelta) return scoreDelta;
      const ad = a.essential_insights?.freshness_days;
      const bd = b.essential_insights?.freshness_days;
      if (ad != null && bd != null && ad !== bd) return ad - bd;
      return String(a.ticker).localeCompare(String(b.ticker));
    });
  }

  function pickPrimaryInsight(e) {
    if (!e) return null;
    if (e.macro_only) return { macroOnly: true };
    const status = e.status || {};
    const fresh = e.freshness_days != null && e.freshness_days <= 30;
    if (fresh && status.tone === 'risk' && e.bear) return e.bear;
    if (fresh && status.tone === 'bullish' && e.bull) return e.bull;
    if (e.owner) return e.owner;
    if (e.latest) {
      const ownerId = e.owner && e.owner.id;
      if (!ownerId || e.latest.id !== ownerId) return e.latest;
    }
    return e.bull || e.bear || null;
  }

  function renderInsightCompact(item, escapeHtml, linkHtml, opts) {
    const emptyLabel = (opts && opts.emptyLabel) || '—';
    if (!item) return `<span class="tier-sub">${emptyLabel}</span>`;
    if (item.macroOnly) {
      return '<span class="tier-sub" title="Portfolio-wide macro — see strip above">Macro context ↑</span>';
    }
    const directionClass = item.direction === 'bullish'
      ? 'badge-ok'
      : (item.direction === 'bearish' ? 'badge-bad' : 'badge-us');
    const link = item.evidence_url
      ? ` ${linkHtml(item.evidence_url, evidenceLabel(item.evidence_url, item.evidence_label), 'source-open-link')}`
      : '';
    const conf = item.confidence && item.confidence !== 'med'
      ? `<span class="badge badge-us">${escapeHtml(item.confidence)}</span>`
      : '';
    const title = escapeHtml(item.title || 'Insight');
    return `
      <div class="insight-compact">
        <div class="insight-compact-meta">
          <span class="badge ${directionClass}">${escapeHtml(item.direction || 'neutral')}</span>
          <span class="badge badge-us">${escapeHtml(item.source_label || item.source || 'source')}</span>
          ${conf}
          ${item.date ? `<span class="mono tier-sub">${escapeHtml(item.date)}</span>` : ''}
        </div>
        <div class="insight-compact-title" title="${title}">${title}${link}</div>
      </div>`;
  }

  function renderTickerSourceMix(e, escapeHtml) {
    const mix = (e.source_mix || []).map(s => SOURCE_LABEL[s] || s);
    if (!mix.length) return '';
    return `<span class="ticker-source-mix">${mix.slice(0, 3).map(s => escapeHtml(s)).join(' · ')}</span>`;
  }

  function filterTickerEssentialsForView(rows, viewMode) {
    if (viewMode === 'trends') {
      return rows.filter(t => {
        const kt = t.kpi_trends || {};
        if (kt.has_trend_data) return true;
        return (kt.metrics || []).some(m => m.direction === 'accelerating' || m.direction === 'decelerating' || m.direction === 'downshift');
      });
    }
    if (viewMode === 'gaps') {
      return rows.filter(t => {
        const e = t.essential_insights || {};
        return e.needs_work
          || e.status?.tone === 'stale'
          || (e.freshness_days != null && e.freshness_days > 365);
      });
    }
    if (viewMode === 'ownership') {
      return rows.filter(t => {
        const e = t.essential_insights || {};
        return e.owner || (t.letter_discussants || []).length;
      });
    }
    return rows;
  }

  function renderTickerInsightsDrawer(tickerRow, escapeHtml, linkHtml, ghRepo) {
    if (!tickerRow) return '';
    const t = tickerRow;
    const e = t.essential_insights || {};
    const events = (t.insight_events || []).slice(0, 12);
    const discussants = t.letter_discussants || [];
    const eventRows = events.map(r => `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.observed_at || r.date || '—')}</td>
        <td><span class="badge badge-us">${escapeHtml(r.source_label || SOURCE_LABEL[r.source] || r.source || '—')}</span></td>
        <td><span class="badge ${r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us')}">${escapeHtml(r.direction || 'neutral')}</span></td>
        <td style="font-size:11px">${escapeHtml((r.title || r.summary || '').slice(0, 120))}</td>
      </tr>`).join('');
    const trendHtml = t.kpi_trends?.has_trend_data
      ? `<div style="margin:8px 0">${renderTickerTrendBadges(t.kpi_trends, escapeHtml)}</div>`
      : '';
    const gapReasons = (e.needs_work_reasons || []).length
      ? `<p class="tier-sub">Gaps: ${e.needs_work_reasons.map(r => escapeHtml(r)).join(', ')}</p>`
      : '';
    const primary = pickPrimaryInsight(e);
    const primaryId = primary && primary.id;
    return `
      <div id="ticker-insights-drawer" class="detail-section ticker-insights-drawer">
        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px">
          <h4 style="margin:0"><span class="mono">${escapeHtml(t.ticker)}</span> · ${escapeHtml((t.company || '').slice(0, 48))}</h4>
          <button type="button" class="filter-btn" id="ticker-insights-drawer-close">Close</button>
          <button type="button" class="linkish" data-select-ticker="${escapeHtml(t.ticker)}">Open holding</button>
          <button type="button" class="linkish" data-insights-goto-consensus data-ticker="${escapeHtml(t.ticker)}">Open in Consensus</button>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">
          <span class="badge ${insightToneClass(e.status?.tone)}">${escapeHtml(e.status?.label || 'No insight')}</span>
          ${formatFreshnessDisplay(e.freshness_days).stale ? '<span class="badge badge-warn">Stale</span>' : ''}
        </div>
        ${gapReasons}
        ${trendHtml}
        ${renderInsightCompact(primary, escapeHtml, linkHtml, { emptyLabel: 'No signal' })}
        ${e.bull && e.bull.id !== primaryId ? `<div style="margin-top:8px"><span class="tier-sub">Bull case</span>${renderInsightCompact(e.bull, escapeHtml, linkHtml)}</div>` : ''}
        ${e.bear && e.bear.id !== primaryId ? `<div style="margin-top:8px"><span class="tier-sub">Bear / risk</span>${renderInsightCompact(e.bear, escapeHtml, linkHtml)}</div>` : ''}
        ${discussants.length ? renderLetterDiscussants(discussants, escapeHtml, linkHtml, ghRepo) : ''}
        ${eventRows ? `
        <h4 style="font-size:12px;color:var(--text-muted);margin:12px 0 6px">Recent events</h4>
        <table class="darwin-table">
          <thead><tr><th>Date</th><th>Source</th><th>Direction</th><th>Title</th></tr></thead>
          <tbody>${eventRows}</tbody>
        </table>` : ''}
      </div>`;
  }

  function renderTickerViewTabs(activeView, escapeHtml) {
    const views = [
      { id: 'scan', label: 'Scan' },
      { id: 'ownership', label: 'Ownership' },
      { id: 'trends', label: 'Trends' },
      { id: 'gaps', label: 'Gaps' },
    ];
    return `
      <nav class="source-pills" id="ticker-view-tabs" style="margin-bottom:8px">
        ${views.map(v => `<button type="button" class="filter-btn source-pill${activeView === v.id ? ' active' : ''}" data-ticker-view="${escapeHtml(v.id)}">${escapeHtml(v.label)}</button>`).join('')}
      </nav>`;
  }

  function renderTickerSortTabs(activeSort, escapeHtml) {
    const sorts = [
      { id: 'attention', label: 'Needs attention' },
      { id: 'fresh', label: 'Fresh' },
      { id: 'stale', label: 'Stale' },
      { id: 'alpha', label: 'A–Z' },
    ];
    return `
      <nav class="source-pills" id="ticker-sort-tabs" style="margin-bottom:10px">
        ${sorts.map(s => `<button type="button" class="filter-btn source-pill${activeSort === s.id ? ' active' : ''}" data-ticker-sort="${escapeHtml(s.id)}">${escapeHtml(s.label)}</button>`).join('')}
      </nav>`;
  }

  function renderTickerScanTable(rows, escapeHtml, linkHtml) {
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const status = e.status || {};
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const primary = pickPrimaryInsight(e);
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
            <div class="tier-sub">${escapeHtml((t.company || '').slice(0, 36))}</div>
          </td>
          <td><span class="badge ${insightToneClass(status.tone)}">${escapeHtml(status.label || 'No insight')}</span>${e.needs_work ? ' <span class="badge badge-warn" title="Needs work">!</span>' : ''}</td>
          <td class="insight-cell">${renderInsightCompact(primary, escapeHtml, linkHtml, { emptyLabel: 'No signal' })}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}${fresh.stale ? ' <span class="badge badge-warn">stale</span>' : ''}<div class="tier-sub">${renderTickerSourceMix(e, escapeHtml)}</div></td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Status</th><th>Signal</th><th>Fresh</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderTickerOwnershipTable(rows, escapeHtml, linkHtml) {
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const owner = e.owner;
      const d0 = (t.letter_discussants || [])[0];
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const fund = owner?.source_name || d0?.fund || '—';
      const action = d0?.action || owner?.event_type || '—';
      const quarter = d0?.quarter || '—';
      const commentary = owner?.summary || d0?.commentary || '';
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
            <div class="tier-sub">${escapeHtml((t.company || '').slice(0, 32))}</div>
          </td>
          <td style="font-size:11px">${escapeHtml(fund)}</td>
          <td><span class="badge ${STANCE_BADGE[action] || 'badge-us'}">${escapeHtml(action)}</span></td>
          <td class="mono" style="font-size:11px">${escapeHtml(quarter)}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}</td>
          <td class="insight-cell">${renderInsightCompact(owner, escapeHtml, linkHtml)}${commentary && !owner ? `<div class="tier-sub">${escapeHtml(commentary.slice(0, 100))}</div>` : ''}</td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Fund</th><th>Action</th><th>Quarter</th><th>Fresh</th><th>Letter</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderTickerTrendsTable(rows, escapeHtml) {
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const kt = t.kpi_trends || {};
      const metrics = (kt.metrics || []).filter(m => m.display !== false).slice(0, 2);
      const metricText = metrics.map(m => `${m.label || m.metric}: ${formatGrowth(m)}`).join(' · ') || '—';
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
          </td>
          <td>${renderTickerTrendBadges(kt, escapeHtml) || '<span class="tier-sub">—</span>'}</td>
          <td style="font-size:11px;max-width:280px">${escapeHtml(metricText)}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}</td>
          <td><span class="badge ${insightToneClass(e.status?.tone)}">${escapeHtml(e.status?.label || '—')}</span></td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Trend</th><th>Metrics</th><th>Fresh</th><th>Status</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function renderTickerGapsTable(rows, escapeHtml, linkHtml) {
    const body = rows.map(t => {
      const e = t.essential_insights || {};
      const fresh = formatFreshnessDisplay(e.freshness_days);
      const reasons = (e.needs_work_reasons || []).slice(0, 3);
      const primary = pickPrimaryInsight(e);
      return `
        <tr>
          <td>
            <button type="button" class="linkish mono" data-ticker-insight="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button>
            <div class="tier-sub">${escapeHtml((t.company || '').slice(0, 32))}</div>
          </td>
          <td style="font-size:11px">${reasons.length ? reasons.map(r => `<span class="badge badge-warn">${escapeHtml(r)}</span>`).join(' ') : '<span class="badge badge-warn">stale</span>'}</td>
          <td class="mono ${fresh.cls}">${escapeHtml(fresh.label)}</td>
          <td class="insight-cell">${renderInsightCompact(primary, escapeHtml, linkHtml)}</td>
        </tr>`;
    }).join('');
    return `
      <table class="darwin-table" id="insights-ticker-table">
        <thead><tr><th>Ticker</th><th>Gap</th><th>Fresh</th><th>Last signal</th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  function attachTickerInsightsHandlers(container, tickers, options) {
    const { onViewMode, onSortMode, onTickerSelect, onCloseDrawer, onGotoConsensus } = options || {};
    if (!container) return;
    container.querySelectorAll('[data-ticker-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onViewMode) onViewMode(btn.dataset.tickerView || 'scan');
      });
    });
    container.querySelectorAll('[data-ticker-sort]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onSortMode) onSortMode(btn.dataset.tickerSort || 'attention');
      });
    });
    container.querySelectorAll('[data-ticker-insight]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const ticker = btn.dataset.tickerInsight;
        if (ticker && onTickerSelect) onTickerSelect(ticker);
      });
    });
    const closeBtn = container.querySelector('#ticker-insights-drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', () => { if (onCloseDrawer) onCloseDrawer(); });
    container.querySelectorAll('[data-insights-goto-consensus]').forEach(btn => {
      btn.addEventListener('click', () => {
        const ticker = btn.dataset.ticker;
        if (ticker && onGotoConsensus) onGotoConsensus(ticker);
      });
    });
  }

  function renderTickerEssentials(tickers, escapeHtml, linkHtml, opts) {
    const sourceFilter = (opts && opts.sourceFilter) || 'ownership';
    const viewMode = (opts && opts.viewMode) || 'scan';
    const sortMode = (opts && opts.sortMode) || 'attention';
    const selectedTicker = opts && opts.selectedTicker;
    const ghRepo = (opts && opts.ghRepo) || '';
    let rows = filterTickerEssentials(tickers, opts);
    rows = filterTickerEssentialsForView(rows, viewMode);
    rows = sortTickerEssentialsRows(rows, sortMode).slice(0, 160);
    const sourceTabs = renderTickerSourceFilters(sourceFilter, escapeHtml);
    const viewTabs = renderTickerViewTabs(viewMode, escapeHtml);
    const sortTabs = renderTickerSortTabs(sortMode, escapeHtml);
    const tickerBySymbol = Object.fromEntries((tickers || []).map(t => [t.ticker, t]));
    const drawer = selectedTicker && tickerBySymbol[selectedTicker]
      ? renderTickerInsightsDrawer(tickerBySymbol[selectedTicker], escapeHtml, linkHtml, ghRepo)
      : '';
    if (!rows.length) {
      return `${drawer}${sourceTabs}${viewTabs}${sortTabs}<p class="subhead">No ticker essentials match this view.</p>`;
    }
    let table = '';
    if (viewMode === 'ownership') table = renderTickerOwnershipTable(rows, escapeHtml, linkHtml);
    else if (viewMode === 'trends') table = renderTickerTrendsTable(rows, escapeHtml);
    else if (viewMode === 'gaps') table = renderTickerGapsTable(rows, escapeHtml, linkHtml);
    else table = renderTickerScanTable(rows, escapeHtml, linkHtml);
    const viewHint = {
      scan: 'One signal per holding — click a ticker for full timeline.',
      ownership: 'Letter positioning from superinvestor disclosures.',
      trends: 'KPI inflections and SEC fundamentals where available.',
      gaps: 'Stale coverage, missing evidence, or needs-work flags.',
    }[viewMode] || '';
    return `
      ${drawer}
      <p class="tier-sub" style="margin-bottom:8px">
        Portfolio scan · for cross-fund positioning see <strong>Consensus</strong> · ${rows.length} row(s)
      </p>
      ${sourceTabs}
      ${viewTabs}
      ${sortTabs}
      <p class="tier-sub" style="margin-bottom:8px;color:var(--text-muted)">${escapeHtml(viewHint)}</p>
      ${table}`;
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

  function catalogSourceLabel(row) {
    return row?.source_label || CATALOG_SOURCE_LABEL[row?.source_type] || 'Other PDFs';
  }

  function sortDocumentCatalogRows(rows, opts) {
    const { search = '', knownTickers = [] } = opts || {};
    const q = SearchMatch.normalizeQuery(search);
    return [...(rows || [])].sort((a, b) => {
      if (q) {
        const scoreDelta = SearchMatch.documentCatalogMatchScore(b, q, knownTickers)
          - SearchMatch.documentCatalogMatchScore(a, q, knownTickers);
        if (scoreDelta) return scoreDelta;
      }
      const ad = a.document_date || '';
      const bd = b.document_date || '';
      if (ad && bd && ad !== bd) return bd.localeCompare(ad);
      if (ad && !bd) return -1;
      if (!ad && bd) return 1;
      const sp = (CATALOG_SOURCE_SORT[a.source_type] ?? 99) - (CATALOG_SOURCE_SORT[b.source_type] ?? 99);
      if (sp) return sp;
      const ta = (a.ticker || '').localeCompare(b.ticker || '');
      if (ta) return ta;
      return (a.title || '').localeCompare(b.title || '');
    });
  }

  function filterDocumentCatalog(catalog, opts) {
    const {
      search = '',
      quarter = 'all',
      bookOnly = false,
      period = null,
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
    } = opts || {};
    const q = SearchMatch.normalizeQuery(search);
    const knownTickers = SearchMatch.catalogKnownTickers(catalog);
    let rows = catalog?.documents || [];
    if (period && !period.all) {
      const fields = pdfTimeMode === 'upload'
        ? ['modified_at']
        : ['document_quarter', 'quarter', 'document_date'];
      rows = rows.filter(r => periodMatchesRecord(r, period, fields));
    } else if (quarter && quarter !== 'all') {
      const label = quarter.replace(/^(\d{4})Q([1-4])$/, '$1 Q$2');
      rows = rows.filter(r => r.document_quarter === quarter || r.quarter === label || r.quarter === quarter);
    }
    if (pdfSourceTab === 'letters') {
      rows = rows.filter(r => r.source_type === 'superinvestor_letter');
    } else if (pdfSourceTab === 'company') {
      rows = rows.filter(r => r.source_type === 'company_document');
    } else if (pdfSourceTab === 'third_party') {
      rows = rows.filter(r => r.source_type === 'third_party' || r.source_type === 'sumzero_research' || r.source_type === 'research');
    } else if (pdfSourceTab === 'unclassified') {
      rows = rows.filter(r => r.period_source === 'unknown' || r.source_type === 'pdf');
    }
    if (bookOnly) {
      rows = rows.filter(r => r.ticker);
    }
    if (q) {
      rows = rows.filter(r => SearchMatch.matchDocumentCatalogRow(r, q, knownTickers));
    }
    return sortDocumentCatalogRows(rows, { search: q, knownTickers });
  }

  function renderDocumentCatalog(catalog, escapeHtml, linkHtml, opts) {
    const {
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
    } = opts || {};
    const filtered = filterDocumentCatalog(catalog, opts);
    const rows = filtered.slice(0, 300);
    const summary = catalog?.summary || {};
    const labelCounts = {};
    (catalog?.documents || []).forEach(r => {
      const label = catalogSourceLabel(r);
      labelCounts[label] = (labelCounts[label] || 0) + 1;
    });
    const cards = Object.entries(labelCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([source, count]) => `<span class="badge badge-us">${escapeHtml(source)}: ${count}</span>`)
      .join('');
    const quarterCounts = {};
    (catalog?.documents || []).forEach(r => {
      const label = r.period_label && r.period_source !== 'unknown' ? r.period_label : null;
      if (label) quarterCounts[label] = (quarterCounts[label] || 0) + 1;
    });
    const quarterCards = Object.entries(quarterCounts)
      .sort((a, b) => String(b[0]).localeCompare(String(a[0])))
      .slice(0, 12)
      .map(([quarter, count]) => `<span class="badge badge-purple">${escapeHtml(quarter)}: ${count}</span>`)
      .join('');
    const sourceTabs = [
      { id: 'all', label: 'All PDFs' },
      { id: 'letters', label: 'Letters' },
      { id: 'company', label: 'Company docs' },
      { id: 'third_party', label: 'Third-party / VIC' },
      { id: 'unclassified', label: 'Unclassified' },
    ];
    const timeModes = [
      { id: 'period', label: 'Document period' },
      { id: 'upload', label: 'Recently uploaded' },
    ];
    if (!catalog) {
      return '<p class="subhead">PDF catalog not built. Run: python _system/scripts/build_dashboard_data.py</p>';
    }
    return `
      <div class="detail-section">
        <h3>PDF library</h3>
        <p class="tier-sub" style="margin-bottom:8px">
          ${summary.document_count || 0} documents · ${summary.uploaded_count || 0} uploaded · ${summary.pending_upload_count || 0} pending
          · showing ${rows.length} of ${filtered.length} matching
        </p>
        <nav class="source-pills" id="pdf-source-tabs" style="margin-bottom:8px">
          ${sourceTabs.map(t => `<button type="button" class="filter-btn source-pill${pdfSourceTab === t.id ? ' active' : ''}" data-pdf-source-tab="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <nav class="source-pills" id="pdf-time-mode-tabs" style="margin-bottom:8px">
          ${timeModes.map(t => `<button type="button" class="filter-btn source-pill${pdfTimeMode === t.id ? ' active' : ''}" data-pdf-time-mode="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <div class="source-card-badges" style="margin-bottom:6px">${cards}</div>
        ${quarterCards ? `<div class="source-card-badges" style="margin-bottom:10px">${quarterCards}</div>` : ''}
        <table class="darwin-table" id="insights-document-catalog">
          <thead><tr><th>Source</th><th>Ticker</th><th>Period</th><th>Title</th><th>Folder</th><th></th></tr></thead>
          <tbody>
            ${rows.map(r => `
              <tr>
                <td><span class="badge badge-us">${escapeHtml(catalogSourceLabel(r))}</span></td>
                <td class="mono">${escapeHtml(r.ticker || '—')}</td>
                <td class="mono">${escapeHtml(r.period_label || r.document_date || 'Unknown date')}</td>
                <td style="min-width:280px">${escapeHtml(r.title || 'Untitled')}</td>
                <td class="tier-sub">${escapeHtml(r.drive_folder_path || '')}</td>
                <td>${r.drive_web_view_link ? linkHtml(r.drive_web_view_link, 'PDF', 'source-open-link') : '—'}</td>
              </tr>`).join('')}
          </tbody>
        </table>
        ${filtered.length > rows.length ? `<p class="tier-sub">${filtered.length - rows.length} more documents outside the current table window.</p>` : ''}
      </div>`;
  }

  function renderMemoryLedger(memory, escapeHtml, linkHtml, opts) {
    const {
      search = '',
      bookOnly = false,
      period = null,
      knownTickers = [],
      biotechOnly = false,
      holdingsTickers = [],
      typeFilter = 'all',
      ghRepo = '',
    } = opts || {};
    const bookSet = new Set((holdingsTickers || []).map(t => String(t).toUpperCase()));
    let rows = memory?.claim_ledger || [];
    if (period && !period.all) {
      rows = rows.filter(r => periodMatchesRecord(r, period, ['quarter', 'date', 'as_of', 'source_date']));
    }
    if (bookOnly && bookSet.size) {
      rows = rows.filter(r => bookSet.has(String(r.ticker || '').toUpperCase()));
    }
    if (biotechOnly) {
      const biotechTickers = new Set(
        Object.entries(memory?.by_ticker || {})
          .filter(([, v]) => v?.biotech?.is_biotech_related)
          .map(([t]) => t.toUpperCase())
      );
      rows = rows.filter(r => biotechTickers.has(String(r.ticker || '').toUpperCase()));
    }
    if (typeFilter && typeFilter !== 'all') {
      rows = rows.filter(r => memoryClaimMatchesType(r, typeFilter));
    }
    if (search) {
      rows = rows.filter(r => SearchMatch.matchMemoryClaim(r, search, knownTickers));
    }
    const totalFiltered = rows.length;
    rows = rows.slice(0, 160);
    if (!rows.length) {
      return '<p class="subhead">No research-memory claims match this view. Try All history, clear filters, or switch type.</p>';
    }
    return `
      <table class="darwin-table" id="memory-claim-ledger">
        <thead><tr><th>Ticker</th><th>Type</th><th>Direction</th><th>Claim</th><th>Evidence</th></tr></thead>
        <tbody>${rows.map(r => {
          const cls = r.direction === 'bullish' ? 'badge-ok' : (r.direction === 'bearish' ? 'badge-bad' : 'badge-us');
          const evLabel = r.evidence_label || evidenceLabel(r.evidence_url, r.source_title);
          const evidenceCell = r.evidence_url
            ? evidenceLink(r.evidence_url, linkHtml, ghRepo, evLabel)
            : escapeHtml(r.source_title || r.source_type || 'source');
          return `<tr>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td><span class="badge badge-us">${escapeHtml(r.claim_type || 'claim')}</span></td>
            <td><span class="badge ${cls}">${escapeHtml(r.direction || 'neutral')}</span></td>
            <td style="min-width:320px">${escapeHtml(r.claim || '')}</td>
            <td style="min-width:140px">${evidenceCell}<div class="tier-sub">${escapeHtml(r.source_title || '')}</div></td>
          </tr>`;
        }).join('')}</tbody>
      </table>
      <p class="tier-sub" style="margin-top:8px">Showing ${rows.length} of ${totalFiltered} matching claim(s)${totalFiltered > rows.length ? ' (table capped at 160)' : ''}.</p>`;
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
            <td>${escapeHtml(r.reason || '')}${(r.reasons || []).length > 1 ? `<div class="tier-sub">${escapeHtml((r.reasons || []).join(' · '))}</div>` : ''}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>`;
  }

  function renderBiotechMemory(memory, escapeHtml, linkHtml, ghRepo) {
    const funds = memory?.biotech?.specialist_funds || [];
    const signals = memory?.biotech?.signals?.by_ticker || {};
    const tickers = Object.values(memory?.by_ticker || {}).filter(t => t.biotech?.is_biotech_related);
    const signalRows = Object.values(signals).sort((a, b) => (b.consensus_score || 0) - (a.consensus_score || 0));
    return `
      <div class="detail-section">
        <h3>Biotech specialist registry</h3>
        <p class="tier-sub" style="margin-bottom:8px">${funds.length} specialist funds tracked for 13F ingestion · ${tickers.length} biotech-related tickers in book/watchlist · ${memory?.summary?.ownership_record_count || 0} 13F records loaded.</p>
        <table class="darwin-table">
          <thead><tr><th>Fund</th><th>Specialty</th><th>Role</th><th>Notes</th></tr></thead>
          <tbody>${funds.slice(0, 28).map(f => `<tr>
            <td>${escapeHtml(f.fund || '')}</td>
            <td><span class="badge badge-purple">${escapeHtml(f.specialty || 'biotech')}</span></td>
            <td>${escapeHtml(f.signal_role || 'specialist_13f')}</td>
            <td class="tier-sub">${escapeHtml(f.notes || '')}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="detail-section">
        <h3>Biotech quant signals</h3>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Consensus</th><th>Core funds</th><th>All specialists</th><th>Net flow</th><th>Flags</th></tr></thead>
          <tbody>${signalRows.slice(0, 40).map(s => `<tr>
            <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(s.ticker)}">${escapeHtml(s.ticker)}</button></td>
            <td class="mono">${s.consensus_score ?? '—'}</td>
            <td class="mono">${s.core_fund_holder_count ?? 0}</td>
            <td class="mono">${s.specialist_holder_count ?? 0}</td>
            <td class="mono">${s.net_quarterly_change ?? 0}</td>
            <td>${[
              s.initiation_signal ? '<span class="badge badge-ok">initiation</span>' : '',
              s.exit_signal ? '<span class="badge badge-bad">exit</span>' : '',
              s.concentration_flag ? '<span class="badge badge-warn">concentration</span>' : '',
            ].filter(Boolean).join(' ') || '—'}</td>
          </tr>`).join('') || '<tr><td colspan="6" class="tier-sub">Run make specialist-13f-ingest to populate signals.</td></tr>'}</tbody>
        </table>
      </div>
      <div class="detail-section">
        <h3>Biotech-related ticker queue</h3>
        <table class="darwin-table">
          <thead><tr><th>Ticker</th><th>Claims</th><th>Evidence</th><th>13F status</th><th>Top claim</th></tr></thead>
          <tbody>${tickers.map(t => {
            const top = (t.top_claims || [])[0] || {};
            const loaded = (t.biotech?.ownership_records || []).length;
            return `<tr>
              <td><button type="button" class="linkish mono" data-select-ticker="${escapeHtml(t.ticker)}">${escapeHtml(t.ticker)}</button><div class="tier-sub">${escapeHtml(t.company || '')}</div></td>
              <td class="mono">${t.claim_count || 0}</td>
              <td class="mono">+${t.confirming_count || 0} / -${t.disconfirming_count || 0}</td>
              <td><span class="badge ${loaded ? 'badge-ok' : 'badge-warn'}">${loaded ? 'loaded' : 'pending'}</span></td>
              <td>${escapeHtml((top.claim || '').slice(0, 180))} ${top.evidence_url ? evidenceLink(top.evidence_url, linkHtml, ghRepo, top.evidence_label) : ''}</td>
            </tr>`;
          }).join('')}</tbody>
        </table>
      </div>`;
  }

  function filterLetterIndex(rows, opts) {
    const { quarter, search, bookOnly, period, knownTickers = [] } = opts || {};
    let list = rows || [];
    if (period && !period.all) {
      list = list.filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    } else if (quarter && quarter !== 'all') {
      list = list.filter(r => r.quarter === quarter);
    }
    if (bookOnly) {
      list = list.filter(r => (r.our_overlap || []).length > 0);
    }
    if (search) {
      list = list.filter(r => SearchMatch.matchLetterIndexRow(r, search, knownTickers));
    }
    return list;
  }

  function consensusSentimentChip(sentiment, escapeHtml) {
    const map = { accumulating: 'badge-ok', reducing: 'badge-bad', mixed: 'badge-warn', discussed: 'badge-us' };
    return `<span class="badge ${map[sentiment] || 'badge-us'}">${escapeHtml(sentiment || 'discussed')}</span>`;
  }

  function consensusTickerCell(row, escapeHtml, opts) {
    const interactive = !(opts && opts.static);
    const book = row.in_book ? '<span class="badge badge-ok" title="In our book" style="margin-left:4px">book</span>' : '';
    if (!interactive) {
      return `<span class="mono">${escapeHtml(row.ticker)}</span>${book}`;
    }
    return `<button type="button" class="linkish mono" data-consensus-ticker="${escapeHtml(row.ticker)}">${escapeHtml(row.ticker)}</button>${book}`;
  }

  function consensusSentimentFromCounts(buys, sells, shorts) {
    if (buys > sells + shorts) return 'accumulating';
    if (sells + shorts > buys) return 'reducing';
    return (buys || sells || shorts) ? 'mixed' : 'discussed';
  }

  function consensusFundSets(row) {
    const buy = new Set(row.buy_fund_names || []);
    const sell = new Set(row.sell_fund_names || []);
    const short = new Set(row.short_fund_names || []);
    const all = new Set(row.funds || []);
    if (!all.size && (row.fund_count || row.buy_funds || row.sell_funds)) {
      (row.funds || []).forEach(f => all.add(f));
    }
    return { buy, sell, short, all };
  }

  function consensusRowsToMap(rows) {
    const map = new Map();
    (rows || []).forEach(r => {
      if (r && r.ticker) map.set(r.ticker, r);
    });
    return map;
  }

  function formatConsensusDelta(value) {
    const n = Number(value || 0);
    if (!n) return '<span class="mono" style="color:var(--text-muted)">0</span>';
    const color = n > 0 ? 'var(--accent-green,#4ade80)' : 'var(--accent-red,#f87171)';
    return `<span class="mono" style="color:${color}">${n > 0 ? '+' : ''}${n}</span>`;
  }

  function priorConsensusPeriod(period, timeModel) {
    if (!period || period.all || !timeModel?.quarters?.length) return null;
    const allIds = timeModel.quarters.map(q => q.id);
    const windowSize = period.quarters.length;
    if (!windowSize) return null;
    if (period.id === 'latest' || windowSize === 1) {
      const qid = period.quarters[0];
      const idx = allIds.indexOf(qid);
      if (idx < 0 || idx >= allIds.length - 1) return null;
      const priorId = allIds[idx + 1];
      return {
        id: `prior:${priorId}`,
        label: `Prior: ${quarterLabel(priorId)}`,
        quarters: [priorId],
        quarterSet: new Set([priorId]),
        all: false,
        selectedYear: parseQuarter(priorId)?.year || period.selectedYear,
      };
    }
    const oldest = period.quarters[period.quarters.length - 1];
    const idx = allIds.indexOf(oldest);
    if (idx < 0) return null;
    const priorIds = allIds.slice(idx + 1, idx + 1 + windowSize);
    if (!priorIds.length) return null;
    return {
      id: `prior:${period.id}`,
      label: `Prior ${windowSize} quarter(s)`,
      quarters: priorIds,
      quarterSet: new Set(priorIds),
      all: false,
      selectedYear: parseQuarter(priorIds[0])?.year || period.selectedYear,
    };
  }

  function computeConsensusQoqShifts(currRows, prevRows) {
    const currMap = consensusRowsToMap(currRows);
    const prevMap = consensusRowsToMap(prevRows);
    const tickers = new Set([...currMap.keys(), ...prevMap.keys()]);
    const shifts = [];
    tickers.forEach(ticker => {
      const c = currMap.get(ticker);
      const p = prevMap.get(ticker);
      const cSets = c ? consensusFundSets(c) : { all: new Set(), buy: new Set(), sell: new Set(), short: new Set() };
      const pSets = p ? consensusFundSets(p) : { all: new Set(), buy: new Set(), sell: new Set(), short: new Set() };
      const newFunds = [...cSets.all].filter(f => !pSets.all.has(f));
      const droppedFunds = [...pSets.all].filter(f => !cSets.all.has(f));
      const cFc = c ? (cSets.all.size || c.fund_count || 0) : 0;
      const pFc = p ? (pSets.all.size || p.fund_count || 0) : 0;
      const cNet = c ? (cSets.buy.size - cSets.sell.size - cSets.short.size) : 0;
      const pNet = p ? (pSets.buy.size - pSets.sell.size - pSets.short.size) : 0;
      const deltaFunds = cFc - pFc;
      const deltaNet = cNet - pNet;
      const cSent = c ? (c.sentiment || consensusSentimentFromCounts(cSets.buy.size, cSets.sell.size, cSets.short.size)) : null;
      const pSent = p ? (p.sentiment || consensusSentimentFromCounts(pSets.buy.size, pSets.sell.size, pSets.short.size)) : null;
      const leanFlip = Boolean(cSent && pSent && cSent !== pSent);
      if (!deltaFunds && !deltaNet && !newFunds.length && !droppedFunds.length && !leanFlip) return;
      const ref = c || p;
      shifts.push({
        ticker,
        name: ref.name,
        in_book: ref.in_book,
        fund_count: cFc,
        prior_fund_count: pFc,
        delta_funds: deltaFunds,
        net: cNet,
        prior_net: pNet,
        delta_net: deltaNet,
        sentiment: cSent || 'discussed',
        prior_sentiment: pSent,
        lean_flip: leanFlip,
        new_funds: newFunds.slice(0, 12),
        dropped_funds: droppedFunds.slice(0, 12),
      });
    });
    return shifts.sort((a, b) => Math.abs(b.delta_net) - Math.abs(a.delta_net)
      || Math.abs(b.delta_funds) - Math.abs(a.delta_funds)
      || String(a.ticker).localeCompare(String(b.ticker)));
  }

  function mergeConsensusRows(rows) {
    const byTicker = new Map();
    rows.forEach(r => {
      const ticker = r.ticker;
      if (!ticker) return;
      const sets = consensusFundSets(r);
      const row = byTicker.get(ticker) || {
        ticker,
        name: r.name || ticker,
        in_book: Boolean(r.in_book),
        buy: new Set(),
        sell: new Set(),
        short: new Set(),
        all: new Set(),
      };
      row.name = row.name || r.name || ticker;
      row.in_book = row.in_book || Boolean(r.in_book);
      sets.buy.forEach(f => row.buy.add(f));
      sets.sell.forEach(f => row.sell.add(f));
      sets.short.forEach(f => row.short.add(f));
      sets.all.forEach(f => row.all.add(f));
      byTicker.set(ticker, row);
    });
    return Array.from(byTicker.values()).map(row => {
      const buyNames = Array.from(row.buy);
      const sellNames = Array.from(row.sell);
      const shortNames = Array.from(row.short);
      const funds = Array.from(row.all);
      const fundCount = funds.length;
      const net = buyNames.length - sellNames.length - shortNames.length;
      return {
        ticker: row.ticker,
        name: row.name,
        in_book: row.in_book,
        fund_count: fundCount,
        buy_funds: buyNames.length,
        sell_funds: sellNames.length,
        short_funds: shortNames.length,
        net,
        sentiment: consensusSentimentFromCounts(buyNames.length, sellNames.length, shortNames.length),
        funds,
        buy_fund_names: buyNames,
        sell_fund_names: sellNames,
        short_fund_names: shortNames,
      };
    });
  }

  function consensusBlockForPeriod(consensus, period, fallbackQuarter) {
    const byQuarter = consensus?.by_quarter || {};
    const qids = period?.quarters || [];
    if (!period || period.all) {
      return { block: byQuarter.all || {}, scope: 'all history' };
    }
    if (qids.length === 1 && byQuarter[qids[0]]) {
      return { block: byQuarter[qids[0]], scope: quarterLabel(qids[0]) };
    }
    if (!qids.length && fallbackQuarter && byQuarter[fallbackQuarter]) {
      return { block: byQuarter[fallbackQuarter], scope: quarterLabel(fallbackQuarter) };
    }
    const blocks = qids.map(qid => byQuarter[qid]).filter(Boolean);
    if (!blocks.length) {
      return { block: { letter_count: 0, most_discussed: [], biggest_changes: [], activity: [] }, scope: period.label };
    }
    const activity = blocks.flatMap(b => b.activity || [])
      .sort((a, b) => String(b.letter_date || '').localeCompare(String(a.letter_date || '')));
    const most = mergeConsensusRows(blocks.flatMap(b => b.most_discussed || []))
      .sort((a, b) => (b.fund_count - a.fund_count) || (Math.abs(b.net) - Math.abs(a.net)) || String(a.ticker).localeCompare(String(b.ticker)));
    const changes = most.filter(r => r.net !== 0)
      .sort((a, b) => (Math.abs(b.net) - Math.abs(a.net)) || (b.fund_count - a.fund_count));
    return {
      block: {
        letter_count: blocks.reduce((sum, b) => sum + Number(b.letter_count || 0), 0),
        most_discussed: most,
        biggest_changes: changes,
        activity,
      },
      scope: period.label,
    };
  }

  function consensusHeatmapCell(row) {
    if (!row) return '<td class="consensus-heat-cell" style="text-align:center;color:var(--text-muted)">·</td>';
    const colors = {
      accumulating: 'rgba(74,222,128,0.35)',
      reducing: 'rgba(248,113,113,0.35)',
      mixed: 'rgba(245,158,11,0.28)',
      discussed: 'rgba(148,163,184,0.18)',
    };
    const bg = colors[row.sentiment] || colors.discussed;
    const net = row.net > 0 ? `+${row.net}` : String(row.net || 0);
    return `<td class="consensus-heat-cell" title="${row.fund_count || 0} funds · net ${net}" style="text-align:center;background:${bg};font-size:10px">${net}</td>`;
  }

  function consensusQuarterlyRows(consensus, ticker, quarterIds) {
    const byQuarter = consensus?.by_quarter || {};
    return (quarterIds || []).map(qid => {
      const block = byQuarter[qid];
      const row = (block?.most_discussed || []).find(r => r.ticker === ticker) || null;
      return { qid, label: quarterLabel(qid), row };
    });
  }

  function renderConsensusTickerDrawer(ticker, consensus, escapeHtml, linkHtml, ghRepo, timeModel) {
    if (!ticker || !consensus) return '';
    const history = consensus.by_ticker?.[ticker] || [];
    const quarterIds = (timeModel?.quarters || []).slice(0, 12).map(q => q.id);
    const quarterly = consensusQuarterlyRows(consensus, ticker, quarterIds);
    const name = history[0]?.name || quarterly.find(q => q.row)?.row?.name || ticker;
    const timelineRows = history.map(r => `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
        <td class="mono" style="font-size:11px">${escapeHtml(r.quarter || '—')}</td>
        <td>${r.fund_id ? `<button type="button" class="linkish" data-consensus-fund-id="${escapeHtml(r.fund_id)}">${escapeHtml(r.fund)}</button>` : escapeHtml(r.fund)}</td>
        <td><span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action || '—')}</span></td>
        <td style="font-size:11px;max-width:300px">${escapeHtml((r.commentary || '').slice(0, 200))}</td>
        <td>${recordEvidenceLink(r, linkHtml, ghRepo)}</td>
      </tr>`).join('');
    const sparkCells = quarterly.slice().reverse().map(q => {
      if (!q.row) return `<span class="consensus-spark-dot" style="background:rgba(148,163,184,0.25)" title="${escapeHtml(q.label)}: no mention"></span>`;
      const color = q.row.sentiment === 'accumulating' ? '#4ade80'
        : q.row.sentiment === 'reducing' ? '#f87171'
          : q.row.sentiment === 'mixed' ? '#f59e0b' : '#94a3b8';
      return `<span class="consensus-spark-dot" style="background:${color}" title="${escapeHtml(q.label)}: ${escapeHtml(q.row.sentiment)} (${q.row.fund_count} funds)"></span>`;
    }).join('');
    return `
      <div id="consensus-ticker-drawer" class="detail-section" style="margin-bottom:14px;border:1px solid var(--border);border-radius:8px;padding:12px;background:rgba(255,255,255,0.02)">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <h4 style="margin:0"><span class="mono">${escapeHtml(ticker)}</span> · ${escapeHtml((name || '').slice(0, 48))}</h4>
          <button type="button" class="filter-btn" id="consensus-drawer-close">Close</button>
          <button type="button" class="filter-btn" id="consensus-export-csv" data-export-ticker="${escapeHtml(ticker)}">Export CSV</button>
          <button type="button" class="linkish" data-select-ticker="${escapeHtml(ticker)}">Open holding</button>
        </div>
        <div style="display:flex;align-items:center;gap:4px;margin-bottom:10px" title="Fund lean by quarter (oldest → newest)">${sparkCells}</div>
        ${timelineRows ? `<table class="darwin-table">
          <thead><tr><th>Date</th><th>Quarter</th><th>Fund</th><th>Action</th><th>Commentary</th><th>Source</th></tr></thead>
          <tbody>${timelineRows}</tbody>
        </table>` : '<p class="subhead">No letter mentions for this ticker.</p>'}
      </div>`;
  }

  function renderConsensusShifted(shifts, priorLabel, escapeHtml) {
    if (!shifts.length) {
      return '<p class="subhead">No meaningful shifts vs the prior period for this filter.</p>';
    }
    const rows = shifts.slice(0, 48).map(r => `
      <tr>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px">${escapeHtml((r.name || '').slice(0, 36))}</td>
        <td class="mono" style="text-align:center">${r.prior_fund_count ?? '—'} → ${r.fund_count ?? 0}</td>
        <td style="text-align:center">${formatConsensusDelta(r.delta_funds)}</td>
        <td class="mono" style="text-align:center">${r.prior_net > 0 ? '+' : ''}${r.prior_net ?? 0} → ${r.net > 0 ? '+' : ''}${r.net ?? 0}</td>
        <td style="text-align:center">${formatConsensusDelta(r.delta_net)}</td>
        <td>${r.lean_flip ? `${consensusSentimentChip(r.prior_sentiment, escapeHtml)} → ${consensusSentimentChip(r.sentiment, escapeHtml)}` : consensusSentimentChip(r.sentiment, escapeHtml)}</td>
        <td style="font-size:10px;color:var(--text-muted);max-width:200px">${r.new_funds?.length ? `+${r.new_funds.map(f => escapeHtml(f)).join(', ')}` : ''}${r.dropped_funds?.length ? `${r.new_funds?.length ? ' · ' : ''}−${r.dropped_funds.map(f => escapeHtml(f)).join(', ')}` : ''}</td>
      </tr>`).join('');
    return `
      <p class="tier-sub" style="margin-bottom:8px">Shifts vs <strong>${escapeHtml(priorLabel || 'prior period')}</strong> · new fund entrants and lean flips</p>
      <table class="darwin-table">
        <thead><tr><th>Ticker</th><th>Name</th><th>Funds</th><th>Δ Funds</th><th>Net</th><th>Δ Net</th><th>Lean</th><th>New / dropped</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function renderConsensusHeatmap(consensus, escapeHtml, opts) {
    const { period, timeModel, bookOnly, search, knownTickers, quarterIds } = opts || {};
    const heatQuarters = (quarterIds || timeModel?.quarters?.slice(0, 8) || []).map(q => q.id || q);
    const byQuarter = consensus?.by_quarter || {};
    const tickerSet = new Map();
    heatQuarters.forEach(qid => {
      (byQuarter[qid]?.most_discussed || []).forEach(r => {
        if (bookOnly && !r.in_book) return;
        if (search && !SearchMatch.matchConsensusRow(r, search, knownTickers)) return;
        const prev = tickerSet.get(r.ticker) || { ticker: r.ticker, name: r.name, in_book: r.in_book, total: 0 };
        prev.total += r.fund_count || 0;
        tickerSet.set(r.ticker, prev);
      });
    });
    const tickers = Array.from(tickerSet.values())
      .sort((a, b) => b.total - a.total || String(a.ticker).localeCompare(String(b.ticker)))
      .slice(0, 50);
    if (!tickers.length) return '<p class="subhead">No securities match this filter.</p>';
    const head = heatQuarters.map(qid => `<th class="mono" style="font-size:10px">${escapeHtml(quarterLabel(qid))}</th>`).join('');
    const body = tickers.map(t => {
      const cells = heatQuarters.map(qid => {
        const row = (byQuarter[qid]?.most_discussed || []).find(r => r.ticker === t.ticker) || null;
        return consensusHeatmapCell(row);
      }).join('');
      return `<tr>
        <td>${consensusTickerCell(t, escapeHtml)}</td>
        <td style="font-size:11px">${escapeHtml((t.name || '').slice(0, 28))}</td>
        ${cells}
      </tr>`;
    }).join('');
    return `
      <p class="tier-sub" style="margin-bottom:8px">Net fund lean by quarter (cell = net buy−sell funds; color = lean)</p>
      <div style="overflow-x:auto">
        <table class="darwin-table consensus-heatmap">
          <thead><tr><th>Ticker</th><th>Name</th>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function renderConsensusFundTrajectory(fundProfiles, letterIndex, escapeHtml, opts) {
    const { search, bookOnly, period, knownTickers, selectedFundId } = opts || {};
    let funds = Object.values(fundProfiles || {});
    if (search) {
      funds = funds.filter(f => SearchMatch.matchFundRegistryRow({
        fund: f.fund,
        fund_id: f.fund_id,
        manager: f.manager,
        quarter: (f.letters || [])[0]?.quarter,
        tickers: f.our_tickers,
      }, search, knownTickers));
    }
    if (bookOnly) {
      funds = funds.filter(f => (f.our_tickers || []).length > 0);
    }
    funds.sort((a, b) => String(a.fund || '').localeCompare(String(b.fund || '')));
    const profile = selectedFundId ? fundProfiles[selectedFundId] : null;
    const fundOptions = funds.slice(0, 200).map(f => {
      const sel = f.fund_id === selectedFundId ? ' selected' : '';
      return `<option value="${escapeHtml(f.fund_id)}"${sel}>${escapeHtml(f.fund || f.fund_id)}</option>`;
    }).join('');
    let trajectory = '';
    if (profile) {
      const letters = (profile.letters || []).filter(l => {
        if (period && !period.all && period.quarterSet?.size) {
          return period.quarterSet.has(l.quarter);
        }
        return true;
      });
      const rows = letters.flatMap(letter => {
        const positions = (letter.positions || []).filter(p => p.ticker && (!bookOnly || (profile.our_tickers || []).includes(String(p.ticker).toUpperCase())));
        return positions.map(p => ({
          quarter: letter.quarter,
          letter_date: letter.letter_date,
          ticker: p.ticker,
          action: p.action,
          commentary: p.commentary || p.thesis,
        }));
      }).sort((a, b) => String(b.letter_date || b.quarter || '').localeCompare(String(a.letter_date || a.quarter || '')));
      trajectory = rows.length ? `<table class="darwin-table">
        <thead><tr><th>Quarter</th><th>Date</th><th>Ticker</th><th>Action</th><th>Commentary</th></tr></thead>
        <tbody>${rows.slice(0, 150).map(r => `
          <tr>
            <td class="mono" style="font-size:11px">${escapeHtml(r.quarter || '—')}</td>
            <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
            <td><button type="button" class="linkish mono" data-consensus-ticker="${escapeHtml(r.ticker)}">${escapeHtml(r.ticker)}</button></td>
            <td><span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action || '—')}</span></td>
            <td style="font-size:11px">${escapeHtml((r.commentary || '').slice(0, 160))}</td>
          </tr>`).join('')}</tbody>
      </table>` : '<p class="subhead">No position commentary for this fund in the selected period.</p>';
    }
    return `
      <p class="tier-sub" style="margin-bottom:8px">Fund positioning over time from letter disclosures</p>
      <label class="tier-sub" style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        Fund
        <select id="consensus-fund-select" class="search" style="max-width:320px">
          <option value="">Select a fund…</option>
          ${fundOptions}
        </select>
      </label>
      ${trajectory}`;
  }

  function buildConsensusCsv(ticker, consensus, timeModel) {
    const quarterIds = (timeModel?.quarters || []).map(q => q.id);
    const quarterly = consensusQuarterlyRows(consensus, ticker, quarterIds);
    const history = consensus?.by_ticker?.[ticker] || [];
    const lines = ['section,quarter,date,fund,action,fund_count,buy_funds,sell_funds,net,sentiment,commentary'];
    quarterly.forEach(q => {
      const r = q.row;
      if (!r) return;
      lines.push([
        'quarterly',
        q.qid,
        '',
        '',
        '',
        r.fund_count,
        r.buy_funds,
        (r.sell_funds || 0) + (r.short_funds || 0),
        r.net,
        r.sentiment,
        '',
      ].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    });
    history.forEach(r => {
      lines.push([
        'mention',
        r.quarter || '',
        r.letter_date || '',
        r.fund || '',
        r.action || '',
        '',
        '',
        '',
        '',
        '',
        (r.commentary || '').slice(0, 500),
      ].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    });
    return lines.join('\n');
  }

  function attachConsensusHandlers(container, insights, options) {
    const {
      escapeHtml,
      timeModel,
      onViewMode,
      onFundSelect,
      onTickerSelect,
      onCloseDrawer,
    } = options || {};
    if (!container) return;
    container.querySelectorAll('[data-consensus-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onViewMode) onViewMode(btn.dataset.consensusView || 'table');
      });
    });
    container.querySelectorAll('[data-consensus-ticker]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const ticker = btn.dataset.consensusTicker;
        if (ticker && onTickerSelect) onTickerSelect(ticker);
      });
    });
    container.querySelectorAll('[data-consensus-fund-id]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = btn.dataset.consensusFundId;
        if (id && onFundSelect) onFundSelect(id, 'fund');
      });
    });
    const closeBtn = container.querySelector('#consensus-drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', () => { if (onCloseDrawer) onCloseDrawer(); });
    const exportBtn = container.querySelector('#consensus-export-csv');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const ticker = exportBtn.dataset.exportTicker;
        if (!ticker || !insights?.consensus) return;
        const csv = buildConsensusCsv(ticker, insights.consensus, timeModel);
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `consensus_${ticker}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      });
    }
    const fundSelect = container.querySelector('#consensus-fund-select');
    if (fundSelect) {
      fundSelect.addEventListener('change', () => {
        if (onFundSelect) onFundSelect(fundSelect.value || null, 'fund');
      });
    }
  }

  function renderConsensus(consensus, escapeHtml, linkHtml, ghRepo, opts) {
    const {
      quarter = 'last4',
      bookOnly = false,
      search = '',
      period = null,
      knownTickers = [],
      timeModel = null,
      viewMode = 'table',
      selectedTicker = null,
      selectedFundId = null,
      fundProfiles = null,
      letterIndex = null,
    } = opts || {};
    if (!consensus || !consensus.by_quarter) {
      return '<p class="subhead">No consensus built yet. Run <span class="mono">python _system/scripts/build_insights.py</span>.</p>';
    }
    const { block, scope } = consensusBlockForPeriod(consensus, period, quarter);
    const matchRow = r => !search || SearchMatch.matchConsensusRow(r, search, knownTickers);
    const bookRow = r => !bookOnly || r.in_book;
    const most = (block.most_discussed || []).filter(r => bookRow(r) && matchRow(r));
    const changes = (block.biggest_changes || []).filter(r => bookRow(r) && matchRow(r));
    const activity = (block.activity || []).filter(r => bookRow(r) && matchRow(r));
    const summary = consensus.summary || {};

    const priorPeriod = priorConsensusPeriod(period, timeModel);
    let qoqShifts = [];
    let priorLabel = '';
    if (priorPeriod) {
      const priorBlock = consensusBlockForPeriod(consensus, priorPeriod, quarter).block;
      qoqShifts = computeConsensusQoqShifts(block.most_discussed, priorBlock.most_discussed)
        .filter(r => bookRow(r) && matchRow(r));
      priorLabel = priorPeriod.label;
    } else if (period?.quarters?.length === 1 && consensus.qoq_by_quarter?.[period.quarters[0]]?.shifts?.length) {
      qoqShifts = (consensus.qoq_by_quarter[period.quarters[0]].shifts || [])
        .filter(r => bookRow(r) && matchRow(r));
      priorLabel = quarterLabel(consensus.qoq_by_quarter[period.quarters[0]].prior_quarter);
    }

    const qoqByTicker = consensusRowsToMap(qoqShifts);
    const showDelta = viewMode === 'table' && qoqShifts.length > 0;

    const viewTabs = [
      { id: 'table', label: 'Snapshot' },
      { id: 'shifted', label: 'What shifted' },
      { id: 'heatmap', label: '8Q heatmap' },
      { id: 'fund', label: 'Fund trajectory' },
    ];

    const mostRows = most.slice(0, 60).map((r, i) => {
      const qoq = qoqByTicker.get(r.ticker);
      const deltaCols = showDelta ? `
        <td style="text-align:center">${qoq ? formatConsensusDelta(qoq.delta_funds) : '<span class="mono" style="color:var(--text-muted)">—</span>'}</td>
        <td style="text-align:center">${qoq ? formatConsensusDelta(qoq.delta_net) : '<span class="mono" style="color:var(--text-muted)">—</span>'}</td>` : '';
      return `
      <tr>
        <td class="mono" style="color:var(--text-muted)">${i + 1}</td>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px;max-width:200px">${escapeHtml((r.name || '').slice(0, 40))}</td>
        <td class="mono" style="text-align:center">${r.fund_count}</td>
        <td class="mono" style="text-align:center;color:var(--accent-green,#4ade80)">${r.buy_funds || 0}</td>
        <td class="mono" style="text-align:center;color:var(--accent-red,#f87171)">${(r.sell_funds || 0) + (r.short_funds || 0)}</td>
        <td class="mono" style="text-align:center">${r.net > 0 ? '+' : ''}${r.net}</td>
        ${deltaCols}
        <td>${consensusSentimentChip(r.sentiment, escapeHtml)}</td>
        <td style="font-size:10px;color:var(--text-muted);max-width:220px">${(r.funds || []).slice(0, 6).map(f => escapeHtml(f)).join(', ')}</td>
      </tr>`;
    }).join('');

    const activityRows = activity.slice(0, 120).map(r => `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
        <td>${r.fund_id ? `<button type="button" class="linkish" data-consensus-fund-id="${escapeHtml(r.fund_id)}">${escapeHtml(r.fund)}</button>` : escapeHtml(r.fund)}</td>
        <td><span class="badge ${STANCE_BADGE[r.action] || 'badge-us'}">${escapeHtml(r.action)}</span></td>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px;max-width:340px">${escapeHtml((r.commentary || '').slice(0, 180))}</td>
        <td>${recordEvidenceLink(r, linkHtml, ghRepo)}</td>
      </tr>`).join('');

    const changesRows = changes.slice(0, 24).map(r => `
      <tr>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px">${escapeHtml((r.name || '').slice(0, 32))}</td>
        <td class="mono" style="text-align:center;color:${r.net >= 0 ? 'var(--accent-green,#4ade80)' : 'var(--accent-red,#f87171)'}">${r.net > 0 ? '+' : ''}${r.net}</td>
        <td>${consensusSentimentChip(r.sentiment, escapeHtml)}</td>
      </tr>`).join('');

    const drawer = selectedTicker
      ? renderConsensusTickerDrawer(selectedTicker, consensus, escapeHtml, linkHtml, ghRepo, timeModel)
      : '';

    let body = '';
    if (viewMode === 'shifted') {
      body = renderConsensusShifted(qoqShifts, priorLabel, escapeHtml);
    } else if (viewMode === 'heatmap') {
      body = renderConsensusHeatmap(consensus, escapeHtml, {
        period, timeModel, bookOnly, search, knownTickers,
        quarterIds: timeModel?.quarters?.slice(0, 8),
      });
    } else if (viewMode === 'fund') {
      body = renderConsensusFundTrajectory(fundProfiles, letterIndex, escapeHtml, {
        search, bookOnly, period, knownTickers, selectedFundId,
      });
    } else {
      body = `
      <h4 style="font-size:12px;color:var(--text-muted);margin:6px 0">MOST DISCUSSED</h4>
      ${most.length ? `<table class="darwin-table">
        <thead><tr><th>#</th><th>Ticker</th><th>Name</th><th title="Distinct funds">Funds</th><th title="Funds buying">Buy</th><th title="Funds selling/short">Sell</th><th title="Buy minus sell funds">Net</th>${showDelta ? '<th title="Change in fund count vs prior period">Δ Funds</th><th title="Change in net vs prior period">Δ Net</th>' : ''}<th>Lean</th><th>Who</th></tr></thead>
        <tbody>${mostRows}</tbody>
      </table>` : '<p class="subhead">No securities match this filter.</p>'}
      ${changes.length ? `
      <h4 style="font-size:12px;color:var(--text-muted);margin:18px 0 6px">BIGGEST NET MOVES (within period)</h4>
      <table class="darwin-table">
        <thead><tr><th>Ticker</th><th>Name</th><th title="Net buying funds minus selling funds">Net funds</th><th>Lean</th></tr></thead>
        <tbody>${changesRows}</tbody>
      </table>` : ''}
      ${activity.length ? `
      <h4 style="font-size:12px;color:var(--text-muted);margin:18px 0 6px">POSITION ACTIVITY (NEW · ADD · TRIM · EXIT · SHORT)</h4>
      <table class="darwin-table">
        <thead><tr><th>Date</th><th>Fund</th><th>Action</th><th>Ticker</th><th>Commentary</th><th>Source</th></tr></thead>
        <tbody>${activityRows}</tbody>
      </table>
      ${activity.length > 120 ? `<p class="tier-sub">${activity.length - 120} more — refine with search or quarter</p>` : ''}` : ''}`;
    }

    return `
      ${drawer}
      <p class="tier-sub" style="margin-bottom:6px">
        Superinvestor letter positioning (aggregated) · ${summary.fund_count || 0} funds · ${summary.tickers_covered || 0} securities · scope <strong>${escapeHtml(scope)}</strong>${bookOnly ? ' · our book only' : ''}
      </p>
      <p class="tier-sub" style="margin-bottom:10px;color:var(--text-muted)">
        Cross-fund consensus from letters only. For multi-source events (filings, news), use <strong>What changed</strong>. Click a ticker for history and CSV export.
      </p>
      <nav class="source-pills" id="consensus-view-tabs" style="margin-bottom:12px">
        ${viewTabs.map(t => `<button type="button" class="filter-btn source-pill${viewMode === t.id ? ' active' : ''}" data-consensus-view="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
      </nav>
      ${body}`;
  }

  function renderInsightsPanel(insights, options) {
    const {
      escapeHtml,
      linkHtml,
      ghRepo = 'magis-capital-partners/single-stock-investments',
      quarter = 'all',
      fundSearch = '',
      bookOnly = false,
      needsReviewOnly = false,
      selectedFundId = null,
      activeSection = 'letters',
      tickers = [],
      memory = null,
      documentCatalog = null,
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
      portfolioMacro = [],
      tickerSourceFilter = 'ownership',
      kpiTrends = null,
      inflectionTier = 'displayed',
      eventTier = 'signal',
      themesViewMode = 'snapshot',
    } = options || {};

    const profiles = insights?.fund_profiles || {};
    if (selectedFundId && profiles[selectedFundId]) {
      return renderFundDetail(profiles[selectedFundId], escapeHtml, linkHtml, ghRepo);
    }

    const byQ = insights?.theme_rankings_by_quarter || {};
    const letterIndex = insights?.letter_index || [];
    const timeModel = buildTimeModel(insights, documentCatalog);
    const periodQuarter = activeSection === 'consensus' ? (options?.consensusQuarter || quarter || 'last4') : quarter;
    const period = periodFromSelection(periodQuarter, timeModel);
    let themes = filterThemesForBook(
      themesForPeriod(byQ, insights?.theme_rankings || [], period),
      letterIndex,
      period,
      bookOnly,
    );
    const knownTickers = SearchMatch.catalogKnownTickers(documentCatalog);
    let funds = insights?.fund_registry || [];
    let letters = filterLetterIndex(letterIndex, { period, search: fundSearch, bookOnly, knownTickers });
    const coverage = periodCoverage(period, timeModel, letterIndex, insights?.fund_registry || []);

    if (fundSearch) {
      funds = funds.filter(f => SearchMatch.matchFundRegistryRow(f, fundSearch, knownTickers));
    }
    if (bookOnly) {
      funds = funds.filter(f => (f.our_ticker_count || 0) > 0);
    }
    if (period && !period.all) {
      funds = funds.filter(f => periodMatchesRecord(f, period, ['quarter', 'letter_date']));
    }

    const rangeTabs = [
      { id: 'latest', label: activeSection === 'documents' ? 'Latest catalog' : 'Latest' },
      { id: 'last4', label: 'Last 4Q' },
      { id: 'last8', label: 'Last 8Q' },
      { id: 'since2020', label: 'Since 2020' },
      { id: 'all', label: 'All history' },
    ];
    const yearSource = activeSection === 'documents'
      ? timeModel.years
      : (timeModel.indexedYears?.length ? timeModel.indexedYears : timeModel.years);
    const selectedYear = period.selectedYear || timeModel.latestYear;
    const yearTabs = yearSource.map(y => ({ id: `year:${y}`, label: String(y), year: y }));
    const quarterTabs = selectedYear
      ? [
          { id: `year:${selectedYear}`, label: 'Full year' },
          { id: `${selectedYear}Q1`, label: 'Q1' },
          { id: `${selectedYear}Q2`, label: 'Q2' },
          { id: `${selectedYear}Q3`, label: 'Q3' },
          { id: `${selectedYear}Q4`, label: 'Q4' },
        ]
      : [];
    const sections = [
      { id: 'letters', label: 'Letters' },
      { id: 'inflections', label: 'Inflections' },
      { id: 'overview', label: 'Overview' },
      { id: 'events', label: 'What changed' },
      { id: 'consensus', label: 'Consensus' },
      { id: 'funds', label: 'Funds' },
      { id: 'documents', label: 'PDF library' },
      { id: 'tickers', label: 'Ticker insights' },
      { id: 'memory', label: 'Research memory' },
      { id: 'themes', label: 'Themes' },
      { id: 'sources', label: 'Pipeline status' },
    ];

    let body = '';
    if (activeSection === 'inflections') {
      body = renderInflections(kpiTrends, escapeHtml, { search: fundSearch, bookOnly, inflectionTier });
    } else if (activeSection === 'overview') {
      body = renderSourceHealth(insights?.source_health || {}, escapeHtml);
    } else if (activeSection === 'events') {
      body = renderEventQueue(insights?.events || [], escapeHtml, linkHtml, ghRepo, {
        search: fundSearch,
        bookOnly,
        needsReviewOnly,
        period,
        knownTickers,
        eventTier,
        triageSummary: (insights?.provenance || {}).event_triage_summary || {},
      });
    } else if (activeSection === 'consensus') {
      body = renderConsensus(insights?.consensus, escapeHtml, linkHtml, ghRepo, {
        quarter: periodQuarter,
        period,
        bookOnly,
        search: fundSearch,
        knownTickers,
        timeModel,
        viewMode: options?.consensusViewMode || 'table',
        selectedTicker: options?.consensusSelectedTicker || null,
        selectedFundId: options?.consensusFundId || null,
        fundProfiles: insights?.fund_profiles || {},
        letterIndex,
      });
    } else if (activeSection === 'letters') {
      const prov = insights?.provenance || {};
      const posPct = prov.letters_with_positions_pct != null
        ? `${Math.round(Number(prov.letters_with_positions_pct) * 1000) / 10}% with disclosed positions`
        : '';
      const positionStats = [posPct, `${letters.length} letter(s)`, escapeHtml(period.label), bookOnly ? 'overlap with our book only' : ''].filter(Boolean).join(' · ');
      body = `<p class="tier-sub" style="margin-bottom:8px">${escapeHtml(period.label)}${bookOnly ? ' · overlap with our book only' : ''}</p>`
        + renderLetterIndex(letters, escapeHtml, linkHtml, ghRepo, true, positionStats, period, timeModel);
    } else if (activeSection === 'funds') {
      body = renderFundRegistry(funds, escapeHtml, linkHtml, ghRepo, bookOnly);
    } else if (activeSection === 'documents') {
      body = renderDocumentCatalog(documentCatalog, escapeHtml, linkHtml, {
        search: fundSearch,
        period,
        bookOnly,
        pdfSourceTab,
        pdfTimeMode,
      });
    } else if (activeSection === 'tickers') {
      body = renderPortfolioMacroStrip(portfolioMacro, escapeHtml, linkHtml)
        + renderTickerEssentials(tickers, escapeHtml, linkHtml, {
          search: fundSearch,
          bookOnly,
          sourceFilter: tickerSourceFilter,
          knownTickers,
          viewMode: options?.tickerViewMode || 'scan',
          sortMode: options?.tickerSortMode || 'attention',
          selectedTicker: options?.tickerSelectedTicker || null,
          ghRepo,
        });
    } else if (activeSection === 'memory') {
      const holdingsTickers = (tickers || []).filter(t => t.in_holdings).map(t => t.ticker);
      const memoryViewMode = options?.memoryViewMode || 'ledger';
      const memoryOpts = {
        search: fundSearch,
        bookOnly,
        period,
        knownTickers,
        holdingsTickers,
        biotechOnly: options?.memoryBiotechOnly || false,
        typeFilter: options?.memoryTypeFilter || 'all',
        memoryViewMode,
        memoryTypeFilter: options?.memoryTypeFilter || 'all',
        memoryBiotechOnly: options?.memoryBiotechOnly || false,
        ghRepo,
      };
      body = renderMemorySummary(memory, escapeHtml)
        + renderMemorySubNav(memoryViewMode, escapeHtml)
        + renderMemoryFilters(memoryOpts, escapeHtml);
      if (memoryViewMode === 'biotech') {
        body += renderBiotechMemory(memory, escapeHtml, linkHtml, ghRepo);
      } else if (memoryViewMode === 'review') {
        body += renderMemoryReviewQueue(memory, escapeHtml);
      } else {
        body += renderMemoryLedger(memory, escapeHtml, linkHtml, memoryOpts);
      }
    } else if (activeSection === 'themes') {
      body = renderThemeRankings(themes, escapeHtml, {
        period,
        timeModel,
        viewMode: themesViewMode,
        themeQoq: themeQoqForPeriod(insights?.theme_qoq_by_quarter || {}, period),
        search: fundSearch,
        glossary: insights?.theme_glossary || null,
      });
    } else {
      body = renderSourceHealth(insights?.source_health || {}, escapeHtml)
        + renderDataSourceCandidates(insights?.data_source_candidates || {}, escapeHtml);
    }

    const showPeriodControls = activeSection !== 'tickers' && activeSection !== 'inflections' && activeSection !== 'memory';
    const bookLabel = activeSection === 'tickers' ? 'Holdings only' : 'Our book overlap';

    return `
      <h2 style="font-size:18px;margin-bottom:6px">Insights</h2>
      <p class="subhead" style="margin-bottom:14px">
        Portfolio context only · ${insights?.event_count || 0} events · ${insights?.letter_count || 0} letters · ${insights?.front_record_count || 0} front records · ${insights?.archived_record_count || 0} archived
      </p>
      <nav class="view-tabs" id="insights-section-tabs" style="margin-bottom:10px">
        ${sections.map(s => `<button type="button" class="view-tab${activeSection === s.id ? ' active' : ''}" data-insights-section="${s.id}">${s.label}</button>`).join('')}
      </nav>
      <div class="detail-section" style="display:grid;gap:8px;margin-bottom:12px">
        ${showPeriodControls ? `<nav class="source-pills" id="insights-range-tabs" style="margin-bottom:0">
          ${rangeTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <nav class="source-pills" id="insights-year-tabs" style="margin-bottom:0">
          ${yearTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        ${quarterTabs.length ? `<nav class="source-pills" id="insights-quarter-tabs" style="margin-bottom:0">
          ${quarterTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>` : ''}` : `<p class="tier-sub">Ticker insights use ticker-specific signals by default. Macro indices appear once above the table.</p>`}
        <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
          <label class="tier-sub" style="display:flex;align-items:center;gap:6px">
            <input type="checkbox" id="insights-book-only" ${bookOnly ? 'checked' : ''} />
            ${escapeHtml(bookLabel)}
          </label>
          ${activeSection === 'events' ? `<label class="tier-sub" style="display:flex;align-items:center;gap:6px">
            <input type="checkbox" id="insights-needs-review" ${needsReviewOnly ? 'checked' : ''} />
            Needs review
          </label>` : ''}
          <input class="search" id="fund-registry-search" placeholder="Search ticker, event, fund, theme, source..." value="${escapeHtml(fundSearch)}" style="max-width:320px" />
        </div>
        ${showPeriodControls ? `<div class="tier-sub">
          Viewing ${escapeHtml(period.label)} &middot; ${coverage.quarters} quarter(s) &middot; ${coverage.letters} indexed letter(s)${coverage.drivePdfCount ? ` &middot; ${coverage.drivePdfCount} catalog PDF(s)` : ''} &middot; ${coverage.funds} fund row(s)${coverage.folderCount ? ` &middot; ${coverage.folderCount} Drive source folder(s)` : ''}${coverage.letters === 0 && coverage.drivePdfCount > 0 ? ' &middot; <span style="color:var(--accent-amber)">PDFs cataloged — run make letter-extract-text</span>' : ''}${period.id === 'latest' && timeModel.latestCatalogQuarter && timeModel.latestIndexedQuarter && timeModel.latestCatalogQuarter !== timeModel.latestIndexedQuarter ? ` &middot; <span style="color:var(--text-muted)">Latest indexed: ${escapeHtml(quarterLabel(timeModel.latestIndexedQuarter))}</span>` : ''}
        </div>` : ''}
      </div>
      ${body}`;
  }

  function attachThemesHandlers(root, opts) {
    const { onThemeDrill, onUseLatestQuarter, onViewMode } = opts || {};
    if (!root) return;
    root.querySelectorAll('[data-theme-drill]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onThemeDrill) onThemeDrill(btn.dataset.themeDrill || '');
      });
    });
    root.querySelectorAll('[data-use-latest-quarter]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onUseLatestQuarter) onUseLatestQuarter();
      });
    });
    root.querySelectorAll('[data-theme-view-mode]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (onViewMode) onViewMode(btn.dataset.themeViewMode || 'snapshot');
      });
    });
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
    renderTickerTrendBadges,
    renderInflections,
    filterInsights,
    attachFilingVerifyHandlers,
    attachConsensusHandlers,
    attachTickerInsightsHandlers,
    attachThemesHandlers,
    buildConsensusCsv,
    buildTimeModel,
    STANCE_BADGE,
  };
})(window);
