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

  function evidenceLabel(ref, fallback) {
    const clean = (ref || '').split('#')[0].toLowerCase();
    const url = String(ref || '');
    if (url.includes('drive.google.com/drive/folders/')) return 'Drive folder';
    if (url.includes('drive.google.com')) return 'PDF';
    if (clean.includes('drive.google.com')) return 'PDF';
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

  function buildTimeModel(insights, documentCatalog) {
    const map = new Map();
    const timePeriods = documentCatalog?.time_periods || {};
    (timePeriods.available_quarters || []).forEach(q => {
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
      .forEach(([q, count]) => addQuarter(map, q, { document_count: count }));

    let quarters = Array.from(map.values()).sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    if (quarters.length && quarters.length < 12) {
      const latestYear = quarters[0].year;
      for (let year = latestYear - 1; year >= latestYear - 12; year -= 1) {
        for (let q = 4; q >= 1; q -= 1) addQuarter(map, `${year}Q${q}`, {});
      }
      quarters = Array.from(map.values()).sort((a, b) => (b.year - a.year) || (b.quarter - a.quarter));
    }
    const years = Array.from(new Set(quarters.map(q => q.year))).sort((a, b) => b - a);
    const byId = Object.fromEntries(quarters.map(q => [q.id, q]));
    return {
      quarters,
      years,
      byId,
      latestQuarter: timePeriods.latest_quarter || quarters[0]?.id || null,
      latestYear: quarters[0]?.year || null,
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

  function recordQuarter(record, fields) {
    for (const field of fields) {
      const q = parseQuarter(record?.[field]);
      if (q) return q.id;
    }
    return null;
  }

  function periodMatchesRecord(record, period, fields) {
    if (!period || period.all) return true;
    const qid = recordQuarter(record, fields);
    return qid ? period.quarterSet.has(qid) : false;
  }

  function periodCoverage(period, timeModel, letterIndex, funds) {
    const letters = (letterIndex || []).filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    const fundRows = (funds || []).filter(r => periodMatchesRecord(r, period, ['quarter', 'letter_date']));
    const folderCount = period.all
      ? timeModel.quarters.reduce((sum, q) => sum + (q.source_folder_count || 0), 0)
      : period.quarters.reduce((sum, id) => sum + (timeModel.byId[id]?.source_folder_count || 0), 0);
    return {
      letters: letters.length,
      funds: fundRows.length,
      quarters: period.all ? timeModel.quarters.length : period.quarters.length,
      folderCount,
    };
  }

  function filterEvents(events, opts) {
    const { search, bookOnly, period } = opts || {};
    let list = events || [];
    if (period && !period.all) {
      list = list.filter(e => periodMatchesRecord(e, period, ['quarter', 'observed_at', 'date', 'as_of']));
    }
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

  function catalogSourceLabel(row) {
    return row?.source_label || CATALOG_SOURCE_LABEL[row?.source_type] || 'Other PDFs';
  }

  function sortDocumentCatalogRows(rows) {
    return [...(rows || [])].sort((a, b) => {
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
    const q = search.toLowerCase();
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
      rows = rows.filter(r => [
        r.ticker,
        r.title,
        r.source_label,
        r.source_type,
        r.quarter,
        r.period_label,
        r.document_date,
        r.drive_folder_path,
      ].join(' ').toLowerCase().includes(q));
    }
    return sortDocumentCatalogRows(rows);
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
    const { search = '', bookOnly = false, period = null } = opts || {};
    const q = search.toLowerCase();
    let rows = memory?.claim_ledger || [];
    if (period && !period.all) {
      rows = rows.filter(r => periodMatchesRecord(r, period, ['quarter', 'date', 'as_of', 'source_date']));
    }
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
    const { quarter, search, bookOnly, period } = opts || {};
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

  function consensusSentimentChip(sentiment, escapeHtml) {
    const map = { accumulating: 'badge-ok', reducing: 'badge-bad', mixed: 'badge-warn', discussed: 'badge-us' };
    return `<span class="badge ${map[sentiment] || 'badge-us'}">${escapeHtml(sentiment || 'discussed')}</span>`;
  }

  function consensusTickerCell(row, escapeHtml) {
    const book = row.in_book ? '<span class="badge badge-ok" title="In our book" style="margin-left:4px">book</span>' : '';
    return `<button type="button" class="linkish mono" data-select-ticker="${escapeHtml(row.ticker)}">${escapeHtml(row.ticker)}</button>${book}`;
  }

  function consensusSentimentFromCounts(buys, sells, shorts) {
    if (buys > sells + shorts) return 'accumulating';
    if (sells + shorts > buys) return 'reducing';
    return (buys || sells || shorts) ? 'mixed' : 'discussed';
  }

  function mergeConsensusRows(rows) {
    const byTicker = new Map();
    rows.forEach(r => {
      const ticker = r.ticker;
      if (!ticker) return;
      const row = byTicker.get(ticker) || {
        ticker,
        name: r.name || ticker,
        in_book: Boolean(r.in_book),
        fund_count: 0,
        buy_funds: 0,
        sell_funds: 0,
        short_funds: 0,
        net: 0,
        funds: new Set(),
      };
      row.name = row.name || r.name || ticker;
      row.in_book = row.in_book || Boolean(r.in_book);
      row.fund_count += Number(r.fund_count || 0);
      row.buy_funds += Number(r.buy_funds || 0);
      row.sell_funds += Number(r.sell_funds || 0);
      row.short_funds += Number(r.short_funds || 0);
      (r.funds || []).forEach(f => row.funds.add(f));
      byTicker.set(ticker, row);
    });
    return Array.from(byTicker.values()).map(row => {
      const funds = Array.from(row.funds);
      const fundCount = funds.length || row.fund_count;
      const net = row.buy_funds - row.sell_funds - row.short_funds;
      return {
        ...row,
        fund_count: fundCount,
        net,
        sentiment: consensusSentimentFromCounts(row.buy_funds, row.sell_funds, row.short_funds),
        funds: funds.slice(0, 10),
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

  function renderConsensus(consensus, escapeHtml, linkHtml, ghRepo, opts) {
    const { quarter = 'all', bookOnly = false, search = '', period = null } = opts || {};
    if (!consensus || !consensus.by_quarter) {
      return '<p class="subhead">No consensus built yet. Run <span class="mono">python _system/scripts/build_insights.py</span>.</p>';
    }
    const { block, scope } = consensusBlockForPeriod(consensus, period, quarter);
    const q = (search || '').toLowerCase();
    const matchRow = r => !q
      || (r.ticker || '').toLowerCase().includes(q)
      || (r.name || '').toLowerCase().includes(q)
      || (r.fund || '').toLowerCase().includes(q);
    const bookRow = r => !bookOnly || r.in_book;
    const most = (block.most_discussed || []).filter(r => bookRow(r) && matchRow(r));
    const changes = (block.biggest_changes || []).filter(r => bookRow(r) && matchRow(r));
    const activity = (block.activity || []).filter(r => bookRow(r) && matchRow(r));
    const summary = consensus.summary || {};

    const mostRows = most.slice(0, 60).map((r, i) => `
      <tr>
        <td class="mono" style="color:var(--text-muted)">${i + 1}</td>
        <td>${consensusTickerCell(r, escapeHtml)}</td>
        <td style="font-size:11px;max-width:200px">${escapeHtml((r.name || '').slice(0, 40))}</td>
        <td class="mono" style="text-align:center">${r.fund_count}</td>
        <td class="mono" style="text-align:center;color:var(--accent-green,#4ade80)">${r.buy_funds || 0}</td>
        <td class="mono" style="text-align:center;color:var(--accent-red,#f87171)">${(r.sell_funds || 0) + (r.short_funds || 0)}</td>
        <td class="mono" style="text-align:center">${r.net > 0 ? '+' : ''}${r.net}</td>
        <td>${consensusSentimentChip(r.sentiment, escapeHtml)}</td>
        <td style="font-size:10px;color:var(--text-muted);max-width:220px">${(r.funds || []).slice(0, 6).map(f => escapeHtml(f)).join(', ')}</td>
      </tr>`).join('');

    const activityRows = activity.slice(0, 120).map(r => `
      <tr>
        <td class="mono" style="font-size:11px">${escapeHtml(r.letter_date || '—')}</td>
        <td>${r.fund_id ? `<button type="button" class="linkish" data-fund-id="${escapeHtml(r.fund_id)}">${escapeHtml(r.fund)}</button>` : escapeHtml(r.fund)}</td>
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

    return `
      <p class="tier-sub" style="margin-bottom:6px">
        Dataroma-style cross-fund consensus from superinvestor letters · ${summary.fund_count || 0} funds · ${summary.tickers_covered || 0} securities · scope <strong>${escapeHtml(scope)}</strong>${bookOnly ? ' · our book only' : ''}
      </p>
      <p class="tier-sub" style="margin-bottom:12px;color:var(--text-muted)">
        Only high-confidence mentions (explicit ticker syntax or verified company name) are counted. Buy = new/added; sell = trimmed/exited/short.
      </p>
      <h4 style="font-size:12px;color:var(--text-muted);margin:6px 0">MOST DISCUSSED</h4>
      ${most.length ? `<table class="darwin-table">
        <thead><tr><th>#</th><th>Ticker</th><th>Name</th><th title="Distinct funds">Funds</th><th title="Funds buying">Buy</th><th title="Funds selling/short">Sell</th><th title="Buy minus sell funds">Net</th><th>Lean</th><th>Who</th></tr></thead>
        <tbody>${mostRows}</tbody>
      </table>` : '<p class="subhead">No securities match this filter.</p>'}
      ${changes.length ? `
      <h4 style="font-size:12px;color:var(--text-muted);margin:18px 0 6px">BIGGEST NET MOVES</h4>
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

  function renderInsightsPanel(insights, options) {
    const {
      escapeHtml,
      linkHtml,
      ghRepo = 'magis-capital-partners/single-stock-investments',
      quarter = 'all',
      fundSearch = '',
      bookOnly = false,
      selectedFundId = null,
      activeSection = 'events',
      tickers = [],
      memory = null,
      documentCatalog = null,
      pdfSourceTab = 'all',
      pdfTimeMode = 'period',
    } = options || {};

    const profiles = insights?.fund_profiles || {};
    if (selectedFundId && profiles[selectedFundId]) {
      return renderFundDetail(profiles[selectedFundId], escapeHtml, linkHtml, ghRepo);
    }

    const byQ = insights?.theme_rankings_by_quarter || {};
    const letterIndex = insights?.letter_index || [];
    const timeModel = buildTimeModel(insights, documentCatalog);
    const period = periodFromSelection(quarter, timeModel);
    const themes = themesForPeriod(byQ, insights?.theme_rankings || [], period);
    let funds = insights?.fund_registry || [];
    let letters = filterLetterIndex(letterIndex, { period, search: fundSearch, bookOnly });
    const coverage = periodCoverage(period, timeModel, letterIndex, insights?.fund_registry || []);

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
    if (period && !period.all) {
      funds = funds.filter(f => periodMatchesRecord(f, period, ['quarter', 'letter_date']));
    }

    const rangeTabs = [
      { id: 'latest', label: 'Latest' },
      { id: 'last4', label: 'Last 4Q' },
      { id: 'last8', label: 'Last 8Q' },
      { id: 'since2020', label: 'Since 2020' },
      { id: 'all', label: 'All history' },
    ];
    const selectedYear = period.selectedYear || timeModel.latestYear;
    const yearTabs = timeModel.years.map(y => ({ id: `year:${y}`, label: String(y), year: y }));
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
      { id: 'overview', label: 'Overview' },
      { id: 'events', label: 'What changed' },
      { id: 'consensus', label: 'Consensus' },
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
      body = renderEventQueue(insights?.events || [], escapeHtml, linkHtml, ghRepo, { search: fundSearch, bookOnly, period });
    } else if (activeSection === 'consensus') {
      body = renderConsensus(insights?.consensus, escapeHtml, linkHtml, ghRepo, { quarter, period, bookOnly, search: fundSearch });
    } else if (activeSection === 'letters') {
      body = `<p class="tier-sub" style="margin-bottom:8px">${letters.length} letter(s) &middot; ${escapeHtml(period.label)}${bookOnly ? ' &middot; overlap with our book only' : ''}</p>`
        + renderLetterIndex(letters, escapeHtml, linkHtml, ghRepo, true);
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
      body = renderTickerEssentials(tickers, escapeHtml, linkHtml, { search: fundSearch, bookOnly });
    } else if (activeSection === 'memory') {
      body = renderMemoryLedger(memory, escapeHtml, linkHtml, { search: fundSearch, bookOnly, period })
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
      <div class="detail-section" style="display:grid;gap:8px;margin-bottom:12px">
        <nav class="source-pills" id="insights-range-tabs" style="margin-bottom:0">
          ${rangeTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        <nav class="source-pills" id="insights-year-tabs" style="margin-bottom:0">
          ${yearTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>
        ${quarterTabs.length ? `<nav class="source-pills" id="insights-quarter-tabs" style="margin-bottom:0">
          ${quarterTabs.map(t => `<button type="button" class="filter-btn source-pill${period.id === t.id ? ' active' : ''}" data-insights-quarter="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`).join('')}
        </nav>` : ''}
        <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
          <label class="tier-sub" style="display:flex;align-items:center;gap:6px">
            <input type="checkbox" id="insights-book-only" ${bookOnly ? 'checked' : ''} />
            Our book overlap
          </label>
          <input class="search" id="fund-registry-search" placeholder="Search ticker, event, fund, theme, source..." value="${escapeHtml(fundSearch)}" style="max-width:320px" />
        </div>
        <div class="tier-sub">
          Viewing ${escapeHtml(period.label)} &middot; ${coverage.quarters} quarter(s) &middot; ${coverage.letters} indexed letter(s) &middot; ${coverage.funds} fund row(s)${coverage.folderCount ? ` &middot; ${coverage.folderCount} Drive source folder(s)` : ''}
        </div>
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
