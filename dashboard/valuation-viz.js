/**
 * Valuation workbench / queue / decision-status UI for the new economic-value model.
 * Keeps facts, estimates, judgments, and evidence blockers visible; never invents decision-grade.
 */
(function (global) {
  'use strict';

  function decisionOf(t) {
    const d = t.valuation_decision || {};
    if (d.calculation_status && d.research_return_available === true) {
      const expiry = Date.parse(d.market_sync?.valid_until || '');
      if (d.market_sync?.status !== 'verified' || !Number.isFinite(expiry) || Date.now() >= expiry) {
        const empty = {low:null,base:null,high:null};
        return {...d,calculation_status:'sync_gap',research_return_available:false,
          value_per_share:empty,present_value_today_per_share:empty,margin_of_safety_pct:empty,
          upside_to_value_pct:empty,upside_downside_pct:empty,forward_return_at_price_pct:empty,
          annualized_return_at_price_pct:empty,forward_return_status:'withheld',
          calculation_reason:Number.isFinite(expiry)?'completed_session_quote_missing':'market_sync_expiry_unverified',
          market_sync:{...d.market_sync,status:'updating'}};
      }
    }
    return d;
  }

  function statusMeta(status) {
    const s = String(status || 'missing');
    if (s === 'decision_grade') return { label: 'decision-grade', cls: 'badge-ok' };
    if (s === 'evidence_blocked') return { label: 'evidence blocked', cls: 'badge-bad' };
    if (s === 'provisional') return { label: 'provisional', cls: 'badge-warn' };
    if (s === 'operating-only') return { label: 'operating-only', cls: 'badge-warn' };
    return { label: 'missing', cls: 'badge-warn' };
  }

  function modelLevelMeta(level, fallbackStatus) {
    const value = String(level || '').toLowerCase();
    if (value === 'owner_approved') return { label: 'owner approved', cls: 'badge-ok' };
    if (value === 'committee_reviewed') return { label: 'committee reviewed', cls: 'badge-ok' };
    if (value === 'stock_specific') return { label: 'stock-specific', cls: 'badge-ok' };
    if (value === 'screening_grade') return { label: 'screening only', cls: 'badge-warn' };
    if (value === 'evidence_blocked') return { label: 'evidence blocked', cls: 'badge-bad' };
    if (value === 'unmodeled') return { label: 'unmodeled', cls: 'badge-warn' };
    return statusMeta(fallbackStatus);
  }

  function tierMeta(t) {
    const tier = t.valuation_tier || decisionOf(t).universe_tier || {};
    const n = Number(tier.tier);
    if (![1, 2, 3].includes(n)) return { tier: null, label: null, cls: 'badge-warn' };
    return {
      tier: n,
      label: tier.label || `Tier ${n}`,
      cls: n === 1 ? 'badge-ok' : n === 2 ? 'badge-warn' : 'badge-warn',
    };
  }

  function workbenchStatusBadge(status, escapeHtml) {
    const text = String(status || 'pending').replace(/_/g, ' ');
    const good = ['outcome_tracking', 'ready_to_assemble', 'measured', 'complete', 'clear', 'decision_grade'];
    const bad = ['critical_gaps_open', 'due', 'evidence_blocked'];
    const cls = good.includes(status) ? 'badge-ok' : bad.includes(status) ? 'badge-bad' : 'badge-warn';
    return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
  }

  function renderValuationStatusCell(t, escapeHtml) {
    const d = decisionOf(t);
    const meta = modelLevelMeta(d.model_level, d.status);
    const tier = tierMeta(t);
    const crit = d.critical_gap_count;
    const open = d.open_gap_count;
    let sub = '';
    if (crit > 0) sub = `${crit} critical`;
    else if (open > 0) sub = `${open} open`;
    else if (d.model_level === 'screening_grade') sub = 'triage only';
    else if (d.model_level === 'stock_specific') sub = 'IC eligible';
    else if (d.status === 'decision_grade') sub = 'proof complete';
    else if (d.status === 'provisional') sub = 'first-pass';
    if (tier.label) sub = `${tier.label}${sub ? ` · ${sub}` : ''}`;
    return `<div class="valuation-status-cell"><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span>${sub ? `<div class="tier-sub">${escapeHtml(sub)}</div>` : ''}</div>`;
  }

  function renderValueRangeCell(t, fmtNum, units) {
    const d = decisionOf(t);
    if (d.calculation_status && d.research_return_available !== true) return '<span class="mono" style="color:var(--text-muted)">Model updating</span>';
    const r = d.value_per_share || t.component_valuation?.total_equity_value_per_share;
    if (!r || r.low == null || r.base == null || r.high == null) {
      return '<span class="mono" style="color:var(--text-muted)">incomplete</span>';
    }
    const prov = d.provisional || d.status === 'evidence_blocked' || d.status === 'provisional';
    return `<span class="mono">${fmtQuote(r.low, 0)}–${fmtQuote(r.high, 0)}<span class="irr-sub">base ${fmtQuote(r.base, 0)}${prov ? ' · provisional' : ''}</span></span>`;
  }

  function renderPriceToBaseCell(t, fmtPct) {
    const d = decisionOf(t);
    if (d.calculation_status && d.research_return_available !== true) return '<span class="mono" style="color:var(--text-muted)">—</span>';
    const pct = d.margin_of_safety_pct?.base;
    if (pct == null) {
      return '<span class="mono" style="color:var(--text-muted)">—</span>';
    }
    const cls = Number(pct) >= 0 ? 'irr-pass' : 'irr-fail';
    const title = 'Margin of safety = (intrinsic value today − market price) / intrinsic value today';
    return `<span class="irr-cell ${cls}" title="${title}">${Number(pct) > 0 ? '+' : ''}${fmtPct(pct)}<span class="irr-sub">margin of safety</span></span>`;
  }

  function claimList(items, escapeHtml, empty) {
    if (!items || !items.length) return `<div class="summary">${escapeHtml(empty)}</div>`;
    return `<ul class="workbench-checks">${items.map((row) => {
      if (typeof row === 'string') return `<li>${escapeHtml(row)}</li>`;
      const label = row.label || row.component_id || row.kind || 'item';
      const evidence = row.evidence || row.method || '';
      return `<li><strong>${escapeHtml(label)}</strong>${evidence ? `<div class="tier-sub">${escapeHtml(String(evidence).slice(0, 280))}</div>` : ''}</li>`;
    }).join('')}</ul>`;
  }

  function forecastGapLabel(reason) {
    const labels = {
      economic_review_required:'Economic assumptions need the updated independent review.',
      realization_timing_missing:'Asset or business cash flows need a realization date.',
      annual_operating_cash_flow_missing:'Annual operating cash flow is unavailable.',
      annual_capex_missing:'Annual capital spending is unavailable.',
      annual_diluted_share_count_missing:'A matching diluted share count is missing.',
      positive_normalized_owner_cash_not_established:'A cash-flow recovery model is needed.',
      parent_cashflow_attribution_missing:'Parent shareholder cash flow needs reconciliation.',
      annual_financial_inputs_expired:'Financial inputs need an update.',
      annual_period_or_currency_reconciliation_missing:'Financial periods or currencies need reconciliation.',
      holding_company_component_forecast_missing:'Holding-company assets need a cash-flow forecast.',
      method_specific_forecast_missing:'This business needs a model suited to its economics.',
      instrument_cashflow_schedule_missing:'The security needs a dated payment schedule.',
      issuer_forecast_missing:'An issuer cash-flow forecast is missing.',
      invalid_calculation_proof:'Valuation calculations need repair.',
      material_component_coverage_incomplete:'The valuation omits a material business or asset.',
      limited_liability_equity_waterfall_missing:'Debt and equity recoveries need a settlement model.',
      unique_shareholder_irr_unavailable:'Cash flows do not give a unique annual return.',
      fresh_sourced_quote_missing:'A recent sourced quote is unavailable.',
      corporate_action_history_unverified:'Split history is being refreshed.',
      corporate_action_history_invalid:'The corporate-action source needs reconciliation.',
      source_share_basis_unverified:'The source share basis needs verification.',
      pre_listing_share_basis_unverified:'Pre-listing shares need reconciliation with the listed security.',
      share_basis_date_outside_verified_history:'Split history does not yet cover every model input.',
      completed_session_quote_missing:'The latest completed market close is being refreshed.',
      market_sync_expiry_unverified:'Price freshness is being verified.',
      listing_calendar_or_completed_close_unverified:'The listing calendar or completed close needs verification.',
      financial_inputs_expired_or_undated:'The financial inputs need a dated source update.',
      model_assumptions_expired:'The model assumptions need a source-backed refresh.',
      new_financial_report_after_model:'A newer financial report needs to be incorporated into the model.',
      newer_balance_sheet_inputs_available:'Newer reported balance-sheet inputs need to be incorporated.',
      ordinary_and_listing_share_actions_unreconciled:'The ordinary-share and depositary-share adjustments need reconciliation.',
      quote_issuer_mismatch:'The price source identifies a different company.',
      dated_reporting_to_listing_fx_missing:'A recent currency conversion is unavailable.',
      forecast_date_missing_or_future:'The forecast date needs correction.',
      overlapping_additive_components:'The valuation counts an asset more than once.',
      proof_cashflow_reconciliation_failed:'Cash flows do not reconcile to the valuation.'
    };
    return [...new Set(String(reason||'').split(';').map(x=>x.trim()).filter(Boolean).map(x=>labels[x.split(':')[0]]||x.replace(/_/g,' ')))].join(' ');
  }

  function displayReturn(t) {
    const d = decisionOf(t);
    const value = d.forward_return_at_price_pct?.base;
    // New rows are exclusively governed by the shared forecast. A stale
    // legacy/automatic estimate cannot bypass a missing schedule or quote.
    const shared = Object.prototype.hasOwnProperty.call(d, 'calculation_status');
    const available = shared ? d.research_return_available === true : d.return_publishable === true;
    if (available && value != null && Number.isFinite(Number(value))) {
      return {pct:Number(value), label:'Forward IRR', source:shared ? 'shared_valuation_forecast' : 'contract_forward_return',
        sub:shared ? 'PV, IRR and entry prices use the same valuation forecast' : d.forward_return_reason || 'Dated shareholder cash flows'};
    }
    return {pct:null, label:'Forward return', source:'missing',
      sub:forecastGapLabel(d.calculation_reason) || d.forward_return_reason || 'Dated shareholder forecast unavailable'};
  }

  function renderMarketSyncCell(t, escapeHtml) {
    const d = decisionOf(t), dates = d.dates || {};
    const good = d.research_return_available === true && d.market_sync?.status === 'verified';
    const title = `Completed close ${dates.price_as_of || 'unavailable'}; financial inputs ${dates.financial_period || 'undated'}; model assumptions ${dates.model_as_of || 'undated'}. ${good ? 'Listing, currency and share basis verified.' : forecastGapLabel(d.calculation_reason)}`;
    return `<span class="badge ${good ? 'badge-ok' : 'badge-warn'}" title="${escapeHtml(title)}">${good ? 'Synced' : 'Model updating'}</span><div class="irr-sub">Close ${escapeHtml(dates.price_as_of || 'missing')}</div><div class="irr-sub">Model ${escapeHtml(dates.model_as_of || 'undated')}</div>`;
  }

  function primaryPowerZone(t, personaMeta) {
    const d = decisionOf(t);
    const wb = t.valuation_workbench || {};
    const decision = wb.decision || d;
    const explicit = d.primary_power_zone || decision.primary_power_zone;
    if (explicit) {
      const meta = (personaMeta || {})[explicit] || {};
      return {
        id: explicit,
        label: meta.label || String(explicit).replace(/_/g, ' '),
        source: 'decision',
        fit: null,
        score: null,
      };
    }
    const inZone = (t.power_zones && t.power_zones.in_zone) || [];
    if (inZone.length) {
      const id = inZone[0];
      const z = ((t.power_zones || {}).zones || {})[id] || {};
      const meta = (personaMeta || {})[id] || {};
      return {
        id,
        label: meta.label || String(id).replace(/_/g, ' '),
        source: 'persona',
        fit: z.fit,
        score: z.score,
      };
    }
    return { id: null, label: null, source: 'missing', fit: null, score: null };
  }

  function renderPowerZoneCell(t, escapeHtml, personaMeta) {
    const z = primaryPowerZone(t, personaMeta);
    if (!z.id) {
      return '<span class="mono" style="color:var(--text-muted)" title="No persona power zone">No zone</span>';
    }
    const fit = z.fit != null ? ` · ${Math.round(Number(z.fit) * 100)}% fit` : '';
    const title = z.source === 'persona'
      ? `Top persona power zone${fit}`
      : 'Primary power zone from valuation decision';
    return `<span class="zone-chip" title="${escapeHtml(title)}">⚡ ${escapeHtml(z.label)}</span>`;
  }

  function renderDecisionStrip(t, helpers) {
    const { escapeHtml, fmtNum, fmtPct, stanceBadgeClass, personaMeta } = helpers;
    const units = helpers.quoteUnitsOf ? helpers.quoteUnitsOf(t) : null;
    const fmtQuote = (v, d) => helpers.fmtQuote(v, units, d);
    const d = decisionOf(t);
    const wb = t.valuation_workbench || {};
    const decision = d;
    if (!t.valuation_workbench && !t.component_valuation && d.status === 'missing') return '';
    const meta = modelLevelMeta(d.model_level, d.status);
    const tier = tierMeta(t);
    const values = d.present_value_today_per_share || d.value_per_share
      || t.component_valuation?.total_equity_value_per_share || {};
    const price = d.price_per_share
      ?? t.component_valuation?.price_per_share;
    const margin = d.margin_of_safety_pct?.base;
    const ret = displayReturn(t);
    const zone = primaryPowerZone(t, personaMeta || {});
    const stance = t.classification?.stance || '—';
    const stanceCls = (stanceBadgeClass && stanceBadgeClass[stance]) || 'badge-warn';
    const dates = d.dates || {};
    const committee = wb.committee || {};
    const progress = committee.analysis_progress || {};
    const monitoring = (wb.valuation || {}).monitoring || {};
    const falsifiers = monitoring.falsifiers || [];
    const asOf = dates.model_as_of || wb.as_of || t.classification?.analysis_as_of || '—';
    const hasWorkbench = !!t.valuation_workbench;
    const crit = Number(d.critical_gap_count || 0);
    const open = Number(d.open_gap_count || 0);
    const provisional = !!(d.provisional || d.status === 'provisional' || d.status === 'evidence_blocked');

    let gapsHtml;
    if (hasWorkbench || crit > 0 || open > 0 || d.status === 'evidence_blocked') {
      gapsHtml = `<div class="metric"><div class="k">Critical / open gaps</div><div class="v mono">${crit} / ${open}</div></div>`;
    } else if (provisional) {
      gapsHtml = `<div class="metric"><div class="k">Gaps</div><div class="v" style="font-size:12px;line-height:1.35">Provisional component valuation — workbench not built</div></div>`;
    } else {
      gapsHtml = `<div class="metric"><div class="k">Gaps</div><div class="v mono" style="color:var(--text-muted)">None tracked</div></div>`;
    }

    const zoneLabel = zone.id
      ? `${zone.label}${zone.fit != null ? ` · ${Math.round(Number(zone.fit) * 100)}%` : ''}`
      : 'No persona zone';
    const retDisplay = ret.pct != null ? fmtPct(ret.pct) : 'not modeled';
    const marginCls = margin == null ? '' : (Number(margin) >= 0 ? 'irr-pass' : 'irr-fail');
    const rangeLow = values.low;
    const rangeHigh = values.high;
    const rangeBase = values.base;
    let trackHtml = '';
    if (rangeLow != null && rangeHigh != null && rangeHigh > rangeLow) {
      const span = Number(rangeHigh) - Number(rangeLow);
      const basePct = rangeBase != null
        ? Math.max(0, Math.min(100, ((Number(rangeBase) - Number(rangeLow)) / span) * 100))
        : 50;
      const pricePct = price != null
        ? Math.max(0, Math.min(100, ((Number(price) - Number(rangeLow)) / span) * 100))
        : null;
      trackHtml = `<div class="decision-range-track" title="Low ${fmtQuote(rangeLow)} · base ${fmtQuote(rangeBase)} · high ${fmtQuote(rangeHigh)}">
        <div class="decision-range-fill"></div>
        <div class="decision-range-mark base" style="left:${basePct}%"></div>
        ${pricePct != null ? `<div class="decision-range-mark price" style="left:${pricePct}%"></div>` : ''}
      </div>`;
    }

    const nextAction = d.next_action || decision.next_action
      || (provisional && !hasWorkbench
        ? 'Build valuation workbench or close provisional evidence before committee.'
        : 'Close evidence gaps before committee freeze.');

    const legacy = d.legacy_audit || {};
    const legacyBase = legacy.annualized_return_at_price_pct?.base;
    const legacyAudit = legacy.status
      ? `<details style="margin-top:9px"><summary class="tier-sub">Legacy calculation audit (non-actionable)</summary><div class="workbench-callout"><strong>Excluded result:</strong> ${legacyBase == null ? '—' : `${fmtPct(legacyBase)}/yr`}<br>${escapeHtml(legacy.reason_non_actionable || 'Legacy result is excluded from ranking and capital decisions.')}</div></details>`
      : '';

    const proofState = d.proof_status === 'decision_grade' || d.status === 'decision_grade'
      ? 'done'
      : d.status === 'evidence_blocked' ? 'blocked' : 'active';
    const committeeStatus = String(committee.status || 'not_started');
    const committeeState = ['owner_decision_pending', 'outcome_tracking'].includes(committeeStatus)
      ? 'done'
      : committeeStatus === 'evidence_blocked' || committeeStatus === 'parked'
        ? 'blocked'
        : committeeStatus === 'not_started' ? 'pending' : 'active';
    const ownerStatus = String(committee.owner_status || 'pending');
    const ownerState = ['complete', 'decided'].includes(ownerStatus) ? 'done' : 'pending';
    const railStep = (label, state, detail) => `<div class="decision-proof-step ${state}">
      <span class="decision-proof-dot" aria-hidden="true"></span>
      <div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail)}</small></div>
    </div>`;
    const proofRail = `<div class="decision-proof-rail" aria-label="Valuation decision authority">
      ${railStep('Valuation contract', proofState, String(d.proof_status || d.status || 'missing').replace(/_/g, ' '))}
      ${railStep('Independent committee', committeeState, `${Number(progress.completed || 0)}/${Number(progress.required || 0)} valid outputs · ${committeeStatus.replace(/_/g, ' ')}`)}
      ${railStep('Owner authority', ownerState, ownerState === 'done' ? String(committee.owner_decision || ownerStatus) : 'capital decision pending')}
    </div>`;
    const falsifierText = (row) => typeof row === 'string'
      ? row
      : row.falsifier || row.metric || row.label || row.id || JSON.stringify(row);
    const falsifierPreview = falsifiers.length
      ? `<div class="decision-falsifiers"><div class="decision-falsifiers-head"><strong>What breaks the case</strong><span>${falsifiers.length} monitored</span></div><ul>${falsifiers.slice(0, 3).map((row) => `<li>${escapeHtml(falsifierText(row))}</li>`).join('')}</ul></div>`
      : '<div class="decision-falsifiers empty"><div class="decision-falsifiers-head"><strong>What breaks the case</strong><span>not specified</span></div></div>';

    return `<div class="detail-section valuation-decision-strip decision-hero">
      <h3>Decision</h3>
      <div class="metric-grid metric-grid-3 decision-band">
        <div class="metric"><div class="k">Stance</div><div class="v"><span class="badge ${stanceCls}">${escapeHtml(stance)}</span></div></div>
        <div class="metric"><div class="k">Model readiness</div><div class="v"><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span></div></div>
        <div class="metric"><div class="k">Research tier</div><div class="v">${tier.label ? `<span class="badge ${tier.cls}">${escapeHtml(tier.label)}</span>` : '<span class="mono">—</span>'}</div></div>
      </div>
      <div class="metric-grid metric-grid-3 decision-band" style="margin-top:9px">
        <div class="metric"><div class="k">Price / PV today</div><div class="v mono">${fmtQuote(price)} / ${fmtQuote(rangeBase)}</div></div>
        <div class="metric"><div class="k">Margin of safety</div><div class="v mono ${marginCls}">${margin == null ? '—' : `${Number(margin) > 0 ? '+' : ''}${fmtPct(margin)}`}</div></div>
        <div class="metric"><div class="k">PV today low / high</div><div class="v mono">${fmtQuote(rangeLow)} / ${fmtQuote(rangeHigh)}</div></div>
      </div>
      ${trackHtml}
      ${proofRail}
      <div class="metric-grid metric-grid-3 decision-band" style="margin-top:9px">
        <div class="metric"><div class="k">${escapeHtml(ret.label)}</div><div class="v mono">${escapeHtml(retDisplay)}<div class="tier-sub">${escapeHtml(ret.sub)}</div></div></div>
        <div class="metric"><div class="k">Required return</div><div class="v mono">${d.required_return_pct == null ? '—' : fmtPct(d.required_return_pct)}<div class="tier-sub">${escapeHtml(String(d.output_basis || 'basis not declared').replace(/_/g, ' '))}</div></div></div>
        <div class="metric"><div class="k">Model / fact / price dates</div><div class="v mono" style="font-size:var(--font-caption,12px)">${escapeHtml(asOf)} / ${escapeHtml(dates.latest_fact_as_of || '—')} / ${escapeHtml(dates.price_as_of || '—')}</div></div>
      </div>
      <div class="metric-grid metric-grid-3 decision-band" style="margin-top:9px">
        ${gapsHtml}
        <div class="metric"><div class="k">Primary method</div><div class="v" style="font-size:12px">${escapeHtml(String(d.method_profile || (wb.method_fit || {}).profile_id || 'not declared').replace(/_/g, ' '))}<div class="tier-sub">${escapeHtml(zoneLabel)}</div></div></div>
        <div class="metric"><div class="k">Committee state</div><div class="v" style="font-size:12px">${workbenchStatusBadge(committee.status || 'not_started', escapeHtml)}<div class="tier-sub">${Number(progress.completed || 0)} / ${Number(progress.required || 0)} valid outputs</div></div></div>
      </div>
      ${falsifierPreview}
      <div class="workbench-callout"><strong>Next:</strong> ${escapeHtml(nextAction)}${d.next_gap_id ? `<div class="tier-sub" style="margin-top:4px">Next gap: ${escapeHtml(d.next_gap_id)}</div>` : ''}</div>
      ${legacyAudit}
      ${provisional ? '<p class="tier-sub" style="margin-top:8px">Ranges are provisional until acceptance tests are met. Do not treat them as IC-approved targets.</p>' : ''}
    </div>`;
  }

  function renderEconomicDiagnostics(t, helpers) {
    const d = t.shared_forecast?.economic_diagnostics;
    if (!d || t.shared_forecast?.economic_review_status !== 'passed') return '';
    const esc = helpers.escapeHtml;
    const number = (v) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toFixed(2);
    const pricing = displayReturn(t).pct == null ? {} : d.pricing || {};
    const base = pricing.cases?.base || {};
    const bridge = base.flat_cash_return_pct == null ? '' : `<table class="workbench-table"><tbody>
      <tr><th>Flat cash, unchanged valuation</th><td>${number(base.flat_cash_return_pct)}%</td></tr>
      <tr><th>Cash growth contribution</th><td>${number(base.cash_growth_effect_pp)} percentage points</td></tr>
      <tr><th>Valuation change contribution</th><td>${number(base.valuation_change_effect_pp)} percentage points</td></tr>
      <tr><th>Modeled forward return</th><td>${number(base.irr_pct)}%</td></tr>
      </tbody></table><p class="tier-sub">Sequential return scenarios: flat cash, forecast cash at unchanged valuation, then modeled exit valuation. Attribution depends on this order.</p>`;
    const reverse = pricing.reverse_expectations;
    const implied = reverse?.unit === 'ratio' ? number(reverse.implied_value*100)+'%' : number(reverse?.implied_value);
    const expectations = reverse ? `<p><strong>Price-implied ${esc(String(reverse.driver_ref).replace(/_/g, ' '))}:</strong> ${reverse.status === 'solved' ? implied : esc(String(reverse.status).replace(/_/g, ' '))}<span class="tier-sub"> · within declared evidence bounds</span></p>` : '';
    const tests = (d.structural_tests || []).map(x => `<tr><td>${esc(x.rationale || x.id)}</td><td>${x.values ? number(x.values.base) : 'incomplete'}</td><td>${esc([...new Set((x.financing_failures || []).map(f=>f.case))].join(', ')) || '—'}</td></tr>`).join('');
    const failures = (d.financing_failures || []).map(f=>`<li>${esc(f.case)} · ${esc(f.component_id)} · year ${number(f.year)}: ${number(f.resources/1e6)} million available against ${number(f.senior_due/1e6)} million due; ${number(f.unpaid_senior_claims/1e6)} million unpaid. Common ownership is extinguished.</li>`).join('');
    const outcomes = Object.entries(t.shared_forecast?.return_outcomes || {}).filter(([,v])=>v.outcome==='complete_loss').map(([c])=>`<p><strong>${esc(c)} case: complete loss of capital (−100% total return).</strong> IRR is undefined because no future cash is received.</p>`).join('');
    const hypotheses = (d.hypotheses || []).map(x => `<li><strong>${esc(x.explanation)}</strong><br>${esc(x.discriminating_observation)}</li>`).join('');
    const commitments = (d.forecast_commitments || []).map(x => `<tr><td>${esc(x.observation_field)}</td><td>${esc(x.period)}</td><td>${number(x.values?.low)} / ${number(x.values?.base)} / ${number(x.values?.high)} ${esc(x.unit)}</td></tr>`).join('');
    const allocations = (d.annual_bridges || []).map(x => { const b=x.cases?.base||{}; return `<tr><td>${esc(x.component_id)} · ${Number(x.year)}</td>${['cash_generation','maintenance','organic_growth','acquisitions','sbc_funding','distributions','retained_cash'].map(k=>`<td>${number(b[k] == null ? null : b[k]/1e6)}</td>`).join('')}</tr>`; }).join('');
    return `<div class="card" data-economic-review="passed"><h3>Economic assumptions and return drivers</h3>
      <p>Cash sources, capital allocation and liquidity reconcile across ${Number(d.bridges_reconciled || 0)} annual component bridges. Independent economic review passed; forecasts remain uncertain.</p>
      ${bridge}${expectations}${outcomes}
      ${failures ? `<details><summary>Financing failure paths</summary><p class="tier-sub">Amounts in ${esc(d.currency)}.</p><ul>${failures}</ul></details>` : ''}
      ${allocations ? `<details><summary>Annual cash allocation</summary><p class="tier-sub">Base case, millions of ${esc(d.currency)}. Compensation funding includes only amounts not already deducted from cash generation.</p><div style="overflow-x:auto"><table class="workbench-table"><thead><tr><th>Year</th><th>Cash generated</th><th>Maintenance</th><th>Organic growth</th><th>Acquisitions</th><th>Compensation</th><th>Distributions</th><th>Retained</th></tr></thead><tbody>${allocations}</tbody></table></div></details>` : ''}
      ${tests ? `<details><summary>Structural alternatives</summary><table class="workbench-table"><thead><tr><th>Alternative</th><th>Base value per share</th><th>Cases with equity loss from financing failure</th></tr></thead><tbody>${tests}</tbody></table></details>` : ''}
      ${hypotheses ? `<details><summary>Competing explanations and observations to watch</summary><ul>${hypotheses}</ul></details>` : ''}
      ${commitments ? `<details><summary>Operating forecasts to check later</summary><table class="workbench-table"><thead><tr><th>Metric</th><th>Period</th><th>Low / base / high</th></tr></thead><tbody>${commitments}</tbody></table></details>` : ''}
      </div>`;
  }

  function renderValuationWorkbench(t, helpers) {
    const { escapeHtml, fmtNum, fmtPct, fmtSignedDollar, linkHtml } = helpers;
    // Per-share figures below are quoted in this listing's currency, not USD.
    const units = helpers.quoteUnitsOf ? helpers.quoteUnitsOf(t) : null;
    const fmtQuote = (v, d) => helpers.fmtQuote(v, units, d);
    const fmtSignedQuote = (v) => helpers.fmtSignedQuote(v, units);
    const wb = t.valuation_workbench;
    if (!wb) return renderEconomicDiagnostics(t, helpers);
    const published = decisionOf(t);
    const decision = wb.decision || {};
    const business = wb.business || {};
    const valuation = wb.valuation || {};
    const optionality = wb.optionality || {};
    const committee = wb.committee || {};
    const evidence = wb.evidence || {};
    const method = wb.method_fit || {};
    const outcomes = wb.outcomes || {};
    const attribution = wb.attribution || {};
    const progress = committee.analysis_progress || {};
    const progressPct = progress.required ? Math.min(100, Number(progress.completed || 0) / Number(progress.required) * 100) : 0;
    const ic = t.investment_committee;
    const proofSummary = valuation.calculation_proof_summary || {};
    const publishedReturn = displayReturn(t);
    const publishedReturnText = publishedReturn.pct == null ? 'not modeled' : fmtPct(publishedReturn.pct);
    const readiness = modelLevelMeta(published.model_level || wb.model_level, published.status || decision.status);
    const modelDates = published.dates || wb.dates || {};
    const valueText = (row) => row.range_per_share?.base == null
      ? 'unpriced'
      : `${fmtQuote(row.range_per_share.low)} / ${fmtQuote(row.range_per_share.base)} / ${fmtQuote(row.range_per_share.high)}`;
    const sourceLink = (source) => {
      const ref = source?.ref || '';
      if (!ref) return '';
      const url = helpers.ghRepo ? `https://github.com/${helpers.ghRepo}/blob/main/${ref}` : ref;
      return linkHtml ? linkHtml(url, ref) : escapeHtml(ref);
    };
    const proofCards = (valuation.components || business.components || []).map((row) => {
      const proof = row.calculation_proof;
      const legacy = row.legacy_range_per_share;
      const traces = proof?.traces || {};
      const scenarios = ['low', 'base', 'high'].map((scenario) => {
        const steps = traces[scenario] || [];
        if (!steps.length) return '';
        return `<details style="margin-top:6px" ${scenario === 'base' ? 'open' : ''}><summary class="tier-sub">${escapeHtml(scenario)} case · ${fmtQuote(proof.outputs?.[scenario])}</summary>
          <table class="workbench-table"><thead><tr><th>Step</th><th>Value</th><th>Derivation</th></tr></thead><tbody>${steps.map((step) => `<tr>
            <td><strong>${escapeHtml(step.label || step.id)}</strong><div class="tier-sub">${escapeHtml(step.kind || '')} · ${escapeHtml(step.unit || '')}</div></td>
            <td class="mono">${fmtNum(step.value)}</td>
            <td>${step.substituted_formula ? `<span class="mono">${escapeHtml(step.substituted_formula)} = ${fmtNum(step.value)}</span>` : escapeHtml(step.rationale || 'Source-locked input')}
              ${step.source ? `<div class="tier-sub">${sourceLink(step.source)} · ${escapeHtml(step.source.locator || '')} · as of ${escapeHtml(step.source.as_of || '—')}</div>` : ''}</td>
          </tr>`).join('')}</tbody></table></details>`;
      }).join('');
      return `<div class="workbench-item" style="margin-top:9px">
        <div class="workbench-item-head"><div class="workbench-item-title">${escapeHtml(row.label || row.component_id)}</div>${workbenchStatusBadge(row.valuation_status || 'unpriced', escapeHtml)}</div>
        <p><strong>Production value:</strong> <span class="mono">${valueText(row)}</span></p>
        ${legacy ? `<p class="tier-sub"><strong>Legacy sensitivity, excluded:</strong> <span class="mono">${fmtQuote(legacy.low)} / ${fmtQuote(legacy.base)} / ${fmtQuote(legacy.high)}</span></p>` : ''}
        ${proof ? `<div class="tier-sub">Method ${escapeHtml(proof.method_id || row.method || '')}@${escapeHtml(proof.method_version || '—')} · proof ${escapeHtml(String(proof.proof_hash || '').slice(0, 12))}</div>${scenarios}` : '<p class="tier-sub">No valid calculation graph. This component remains outside the security value until its material inputs are evidenced.</p>'}
      </div>`;
    }).join('');

    const ownershipRows = (business.components || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong>
        <div class="tier-sub">${escapeHtml(row.category || '')} · ${escapeHtml(row.treatment || '')} · overlap ${escapeHtml(row.overlap_key || row.component_id || '')}</div>
        ${row.falsifier ? `<div class="tier-sub">Falsifier: ${escapeHtml(row.falsifier)}</div>` : ''}
      </td>
      <td>${escapeHtml(row.ownership_claim || '')}${row.evidence ? `<div class="tier-sub">${escapeHtml(String(row.evidence).slice(0, 220))}</div>` : ''}</td>
      <td class="mono">${valueText(row)}${row.legacy_range_per_share ? `<div class="tier-sub">legacy ${fmtQuote(row.legacy_range_per_share.low)} / ${fmtQuote(row.legacy_range_per_share.base)} / ${fmtQuote(row.legacy_range_per_share.high)}</div>` : ''}</td>
      <td>${workbenchStatusBadge(row.valuation_status || 'unpriced', escapeHtml)}<div class="tier-sub">${escapeHtml(row.assumption_type || row.evidence_level || '')}</div></td>
    </tr>`).join('');

    const scheduleRows = (valuation.components || business.components || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong><div class="tier-sub">${escapeHtml(row.method || '')}</div></td>
      <td class="mono">${row.range_per_share?.low == null ? '—' : fmtQuote(row.range_per_share.low)}</td>
      <td class="mono">${row.range_per_share?.base == null ? '—' : fmtQuote(row.range_per_share.base)}</td>
      <td class="mono">${row.range_per_share?.high == null ? '—' : fmtQuote(row.range_per_share.high)}</td>
      <td>${workbenchStatusBadge(row.valuation_status || 'unpriced', escapeHtml)}</td>
    </tr>`).join('');

    const valueDrivers = (valuation.scenario_contract?.top_value_drivers || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong>${row.scenario_assumptions ? `<div class="tier-sub">${escapeHtml(typeof row.scenario_assumptions === 'string' ? row.scenario_assumptions : JSON.stringify(row.scenario_assumptions).slice(0, 180))}</div>` : ''}</td>
      <td class="mono">${fmtQuote(row.base_per_share)}</td>
      <td class="mono">${fmtQuote(row.range_width_per_share)}</td>
    </tr>`).join('');

    const reverse = valuation.scenario_contract?.reverse_expectations;
    const reverseHtml = reverse
      ? `<div class="workbench-item" style="margin-top:10px"><div class="workbench-item-title">Reverse expectations</div><pre class="workbench-item-meta" style="white-space:pre-wrap">${escapeHtml(typeof reverse === 'string' ? reverse : JSON.stringify(reverse, null, 2).slice(0, 1200))}</pre></div>`
      : '';

    const optionRows = (optionality.options || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong></td>
      <td>${escapeHtml(row.method || '')}</td>
      <td class="mono">${fmtQuote(row.range_per_share?.low)} / ${fmtQuote(row.range_per_share?.base)} / ${fmtQuote(row.range_per_share?.high)}</td>
      <td>${escapeHtml(row.falsifier || '')}${row.probability_and_timing ? `<div class="tier-sub">${escapeHtml(JSON.stringify(row.probability_and_timing).slice(0, 160))}</div>` : ''}</td>
    </tr>`).join('');

    const gapRows = (evidence.gaps || []).map((gap) => `
      <div class="workbench-item">
        <div class="workbench-item-head">
          <div class="workbench-item-title">${escapeHtml(gap.question || gap.id)}</div>
          <span class="badge ${gap.priority === 'critical' ? 'badge-bad' : 'badge-warn'}">${escapeHtml(gap.priority || 'open')}</span>
        </div>
        <p><strong>Status:</strong> ${escapeHtml(gap.status || 'open')}${gap.progress_note ? ` — ${escapeHtml(gap.progress_note)}` : ''}</p>
        <p><strong>Need:</strong> ${escapeHtml(gap.evidence_required || 'Primary evidence required.')}</p>
        <p><strong>Close when:</strong> ${escapeHtml(gap.acceptance_test || 'Evidence is reconciled to the valuation.')}</p>
        ${gap.valuation_effect ? `<p><strong>Effect:</strong> ${escapeHtml(gap.valuation_effect)}</p>` : ''}
        <div class="workbench-item-meta">
          Value exposed: ${gap.base_value_exposure_per_share == null ? 'not isolated' : fmtQuote(gap.base_value_exposure_per_share) + ' / share'}
          ${(gap.component_ids || []).length ? ` · ${(gap.component_ids || []).map(escapeHtml).join(' · ')}` : ''}
          ${gap.evidence_path ? ` · ${helpers.linkHtml
            ? helpers.linkHtml(
              (helpers.ghRepo ? `https://github.com/${helpers.ghRepo}/blob/main/` : '') + gap.evidence_path,
              gap.evidence_path
            )
            : escapeHtml(gap.evidence_path)}` : ''}
        </div>
      </div>`).join('');

    const decisionPage = `${renderEconomicDiagnostics(t, helpers)}
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Model readiness</div><div class="v"><span class="badge ${readiness.cls}">${escapeHtml(readiness.label)}</span></div></div>
        <div class="metric"><div class="k">Price / PV today</div><div class="v mono">${fmtQuote(published.price_per_share ?? decision.price_per_share)} / ${fmtQuote(published.present_value_today_per_share?.base ?? published.value_per_share?.base ?? decision.value_per_share?.base)}</div></div>
        <div class="metric"><div class="k">Forward return</div><div class="v mono">${escapeHtml(publishedReturnText)}<div class="tier-sub">${escapeHtml(publishedReturn.sub)}</div></div></div>
      </div>
      <div class="metric-grid metric-grid-3" style="margin-top:9px">
        <div class="metric"><div class="k">PV today low / high</div><div class="v mono">${fmtQuote(published.value_per_share?.low ?? decision.value_per_share?.low)} / ${fmtQuote(published.value_per_share?.high ?? decision.value_per_share?.high)}</div></div>
        <div class="metric"><div class="k">Unvalued components</div><div class="v mono">${Number(decision.unvalued_component_count || 0)}</div></div>
        <div class="metric"><div class="k">Evidence blockers</div><div class="v mono">${Number(decision.unresolved_evidence_count || 0)}</div></div>
      </div>
      <div class="metric-grid metric-grid-3" style="margin-top:9px">
        <div class="metric"><div class="k">Calculation proof</div><div class="v mono">${fmtNum(decision.proof_complete_pct ?? proofSummary.proof_complete_pct ?? 0)}%</div></div>
        <div class="metric"><div class="k">Priced components</div><div class="v mono">${Number(proofSummary.priced_component_count || 0)} / ${Number(proofSummary.component_count || 0)}</div></div>
        <div class="metric"><div class="k">Model hash</div><div class="v mono" style="font-size:var(--font-caption,12px)">${escapeHtml(String(decision.model_hash || valuation.change_control?.model_hash || '—').slice(0, 12))}</div></div>
      </div>
      <div class="tier-sub" style="margin-top:8px">Model / latest fact / price dates: ${escapeHtml(modelDates.model_as_of || wb.as_of || '—')} / ${escapeHtml(modelDates.latest_fact_as_of || '—')} / ${escapeHtml(modelDates.price_as_of || '—')}</div>
      <div class="workbench-callout"><strong>Power zone:</strong> ${escapeHtml(decision.primary_power_zone || 'review required')}<br><strong>Next:</strong> ${escapeHtml(decision.next_action || 'Complete evidence and committee gates.')}</div>`;

    const businessPage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Ownership map</div><div class="v">${workbenchStatusBadge(business.status, escapeHtml)}</div></div>
        <div class="metric"><div class="k">Facts / estimates</div><div class="v mono">${(business.facts || []).length} / ${(business.estimates || []).length}</div></div>
        <div class="metric"><div class="k">Judgments</div><div class="v mono">${(business.judgments || []).length}</div></div>
      </div>
      <table class="workbench-table"><thead><tr><th>Component</th><th>Economic claim</th><th>Low / base / high</th><th>Input type</th></tr></thead><tbody>${ownershipRows}</tbody></table>
      <details style="margin-top:10px"><summary class="tier-sub">Facts (${(business.facts || []).length})</summary>${claimList(business.facts, escapeHtml, 'No facts classified yet.')}</details>
      <details style="margin-top:6px"><summary class="tier-sub">Estimates (${(business.estimates || []).length})</summary>${claimList(business.estimates, escapeHtml, 'No estimates classified yet.')}</details>
      <details style="margin-top:6px"><summary class="tier-sub">Judgments (${(business.judgments || []).length})</summary>${claimList(business.judgments, escapeHtml, 'No judgments classified yet.')}</details>`;

    const valuationPage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Market cap</div><div class="v mono">${valuation.market?.market_cap_m == null ? '—' : fmtQuote(valuation.market.market_cap_m) + 'm'}</div></div>
        <div class="metric"><div class="k">Base PV today</div><div class="v mono">${fmtQuote(published.present_value_today_per_share?.base ?? valuation.valuation?.present_value_today_per_share?.base ?? valuation.valuation?.value_per_share?.base)}</div></div>
        <div class="metric"><div class="k">Base margin of safety</div><div class="v mono">${fmtPct(published.margin_of_safety_pct?.base ?? valuation.valuation?.margin_of_safety_pct?.base)}</div></div>
      </div>
      <div class="tier-sub" style="margin-top:7px">Output basis: ${escapeHtml(String(published.output_basis || valuation.valuation?.output_basis || 'not declared').replace(/_/g, ' '))} · required return ${published.required_return_pct == null ? '—' : fmtPct(published.required_return_pct)}</div>
      <div class="workbench-callout">${escapeHtml(valuation.scenario_contract?.rule || '')}</div>
      ${scheduleRows ? `<h4 style="margin:13px 0 0">Component schedule</h4><table class="workbench-table"><thead><tr><th>Component</th><th>Low</th><th>Base</th><th>High</th><th>Status</th></tr></thead><tbody>${scheduleRows}</tbody></table>` : ''}
      ${proofCards ? `<h4 style="margin:13px 0 0">Show the math</h4><div class="workbench-list">${proofCards}</div>` : ''}
      ${valueDrivers ? `<h4 style="margin:13px 0 0">Largest uncertainty drivers</h4><table class="workbench-table"><thead><tr><th>Component</th><th>Base / share</th><th>Range width</th></tr></thead><tbody>${valueDrivers}</tbody></table>` : ''}
      ${reverseHtml}`;

    const optionalityPage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Optionality</div><div class="v">${workbenchStatusBadge(optionality.status, escapeHtml)}</div></div>
        <div class="metric"><div class="k">Explicit options</div><div class="v mono">${Number(optionality.option_count || 0)}</div></div>
      </div>
      <div class="workbench-callout">${escapeHtml(optionality.rule || '')}</div>
      ${optionRows ? `<table class="workbench-table"><thead><tr><th>Option</th><th>Method</th><th>Low / base / high</th><th>Falsifier / timing</th></tr></thead><tbody>${optionRows}</tbody></table>` : '<div class="summary" style="margin-top:10px">No separately material option has been identified; this is an explicit treatment, not an unvalued asset.</div>'}`;

    const evidencePage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Evidence status</div><div class="v">${workbenchStatusBadge(evidence.status, escapeHtml)}</div></div>
        <div class="metric"><div class="k">Open gaps</div><div class="v mono">${Number(evidence.open_count || 0)}</div></div>
        <div class="metric"><div class="k">Critical gaps</div><div class="v mono">${Number(evidence.critical_count || 0)}</div></div>
      </div>
      <div class="workbench-list">${gapRows || '<div class="summary">No open evidence gaps.</div>'}</div>`;

    const cohortRows = (method.validation_cohort || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.ticker || '—')}</strong></td>
      <td>${escapeHtml(String(row.archetype || '').replace(/_/g, ' '))}</td>
      <td>${escapeHtml(row.purpose || '')}</td>
      <td>${workbenchStatusBadge(row.status, escapeHtml)}</td>
    </tr>`).join('');

    const methodPage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Primary power zone</div><div class="v">${escapeHtml(method.label || 'Unclassified')}</div></div>
        <div class="metric"><div class="k">Primary personas</div><div class="v" style="font-size:var(--font-caption,12px)">${(method.primary_personas || []).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ') || '—'}</div></div>
        <div class="metric"><div class="k">Cross-check personas</div><div class="v" style="font-size:var(--font-caption,12px)">${(method.cross_check_personas || []).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ') || '—'}</div></div>
      </div>
      <div class="workbench-callout">${escapeHtml(method.rule || '')}</div>
      ${(method.routing_reasons || []).length ? `<div class="workbench-item" style="margin-top:10px"><div class="workbench-item-title">Routing reasons</div><ul class="workbench-checks">${method.routing_reasons.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>` : ''}
      ${(method.required_evidence || []).length ? `<div class="workbench-item" style="margin-top:8px"><div class="workbench-item-title">Required evidence</div><ul class="workbench-checks">${method.required_evidence.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>` : ''}
      ${(method.silent_personas || []).length ? `<div class="tier-sub" style="margin-top:8px"><strong>Silent personas:</strong> ${method.silent_personas.map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ')}</div>` : ''}
      ${(method.primary_methods || []).length ? `<div class="tier-sub" style="margin-top:4px"><strong>Primary methods:</strong> ${method.primary_methods.map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ')}</div>` : ''}
      <div class="workbench-item" style="margin-top:10px"><div class="workbench-item-title">Applicability tests</div><ol class="workbench-checks">${(method.applicability_tests || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ol></div>
      <div class="workbench-item" style="margin-top:8px"><div class="workbench-item-title">Known failure modes</div><ul class="workbench-checks">${(method.failure_modes || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>
      ${cohortRows ? `<h4 style="margin:13px 0 0">Cross-archetype validation queue</h4><table class="workbench-table"><thead><tr><th>Ticker</th><th>Archetype</th><th>What it tests</th><th>Status</th></tr></thead><tbody>${cohortRows}</tbody></table>` : ''}`;

    const unresolved = (committee.unresolved_items || (ic && ic.unresolved_items) || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('');
    const committeePage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Committee state</div><div class="v">${workbenchStatusBadge(committee.status, escapeHtml)}</div></div>
        <div class="metric"><div class="k">Independent outputs</div><div class="v mono">${Number(progress.completed || 0)} / ${Number(progress.required || 0)}</div><div class="workbench-progress"><span style="width:${progressPct}%"></span></div></div>
        <div class="metric"><div class="k">Owner decision</div><div class="v">${escapeHtml(committee.owner_decision || committee.owner_status || (ic && ic.owner_decision) || 'pending')}</div></div>
      </div>
      <div class="workbench-callout"><strong>Next action:</strong> ${escapeHtml(committee.next_action || 'Freeze evidence and begin independent review.')}</div>
      ${(committee.selected_raters || (ic && ic.selected_raters) || []).length ? `<div class="tier-sub" style="margin-top:9px"><strong>Independent methods:</strong> ${(committee.selected_raters || ic.selected_raters).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ')}</div>` : ''}
      ${(committee.missing_outputs || []).length ? `<details style="margin-top:9px"><summary class="tier-sub">Missing review outputs (${committee.missing_outputs.length})</summary><div class="workbench-item-meta mono">${committee.missing_outputs.map(escapeHtml).join('<br>')}</div></details>` : ''}
      ${unresolved ? `<div class="workbench-item" style="margin-top:10px"><div class="workbench-item-title">Unresolved items</div><ul class="workbench-checks">${unresolved}</ul></div>` : ''}
      ${committee.strongest_dissent || (ic && ic.strongest_dissent) ? `<div class="workbench-item" style="margin-top:10px"><div class="workbench-item-title">Strongest dissent</div><p>${escapeHtml(committee.strongest_dissent || ic.strongest_dissent)}</p></div>` : ''}
      ${ic ? `<div class="tier-sub" style="margin-top:8px">Packet as-of ${escapeHtml(ic.as_of || '—')} · state ${escapeHtml(ic.state || '—')}</div>` : ''}`;

    const outcomeRows = (outcomes.schedule || []).map((slot) => `<tr>
      <td>${Number(slot.horizon_months || 0)} months</td>
      <td class="mono">${escapeHtml(slot.target_date || 'starts after owner decision')}</td>
      <td>${workbenchStatusBadge(slot.status, escapeHtml)}</td>
      <td class="mono">${slot.total_return_pct == null ? '—' : fmtPct(slot.total_return_pct)}</td>
    </tr>`).join('');
    const outcomesPage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Tracking state</div><div class="v">${workbenchStatusBadge(outcomes.status, escapeHtml)}</div></div>
        <div class="metric"><div class="k">Recorded outcomes</div><div class="v mono">${Number(outcomes.recorded_outcome_count || 0)}</div></div>
        <div class="metric"><div class="k">Reweighting threshold</div><div class="v mono">${Number(outcomes.minimum_persona_outcomes_before_reweighting || 20)} / persona</div></div>
      </div>
      <table class="workbench-table"><thead><tr><th>Horizon</th><th>Target</th><th>Status</th><th>Total return</th></tr></thead><tbody>${outcomeRows}</tbody></table>
      <div class="workbench-callout">${escapeHtml(outcomes.weighting_rule || '')}</div>`;

    const attributionDrivers = (attribution.drivers || []).slice(0, 10).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong></td>
      <td class="mono">${fmtSignedQuote(row.change_per_share)}</td>
      <td>${(row.causes || []).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ')}</td>
    </tr>`).join('');
    const categoryRows = Object.entries(attribution.category_totals_per_share || {}).map(([key, value]) =>
      `<div class="metric"><div class="k">${escapeHtml(key.replace(/_/g, ' '))}</div><div class="v mono">${fmtSignedQuote(value)}</div></div>`).join('');
    const attributionPage = attribution.status === 'baseline_established' ? `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Current baseline</div><div class="v mono">${fmtQuote(attribution.current?.base)}</div></div>
        <div class="metric"><div class="k">As of</div><div class="v mono">${escapeHtml(attribution.current?.as_of || '—')}</div></div>
        <div class="metric"><div class="k">Attribution</div><div class="v">${workbenchStatusBadge(attribution.status, escapeHtml)}</div></div>
      </div>
      <div class="workbench-callout">${escapeHtml(attribution.explanation || '')}</div>` : `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Prior base</div><div class="v mono">${fmtQuote(attribution.prior?.base)}</div><div class="tier-sub">${escapeHtml(attribution.prior?.as_of || '—')}</div></div>
        <div class="metric"><div class="k">Current base</div><div class="v mono">${fmtQuote(attribution.current?.base)}</div><div class="tier-sub">${escapeHtml(attribution.current?.as_of || '—')}</div></div>
        <div class="metric"><div class="k">Base change</div><div class="v mono">${fmtSignedQuote(attribution.base_change_per_share)}</div><div class="tier-sub">${fmtPct(attribution.base_change_pct)}</div></div>
      </div>
      ${categoryRows ? `<div class="metric-grid" style="margin-top:9px">${categoryRows}</div>` : ''}
      ${attributionDrivers ? `<table class="workbench-table"><thead><tr><th>Component</th><th>Change / share</th><th>Observed cause</th></tr></thead><tbody>${attributionDrivers}</tbody></table>` : ''}
      <div class="tier-sub" style="margin-top:8px">Unexplained reconciliation: ${fmtSignedQuote(attribution.unexplained_per_share)} · ${escapeHtml(attribution.explanation || '')}</div>`;

    const tabs = [
      ['decision', 'Decision'],
      ['evidence', 'Evidence'],
      ['model', 'Model & proof'],
      ['history', 'History'],
    ];

    return `<div class="detail-section valuation-workbench">
      <div class="workbench-head">
        <div>
          <h3>Valuation workbench <span class="badge ${readiness.cls}">${escapeHtml(readiness.label)}</span></h3>
          <div class="tier-sub">Decision readiness, ownership map, evidence gaps, method fit, committee, and measured outcomes · ${escapeHtml(wb.as_of || '—')}</div>
        </div>
        ${wb.github_url ? `<a class="research-link" href="${wb.github_url}" target="_blank" rel="noopener">Audit file →</a>` : ''}
      </div>
      <div class="workbench-tabs" role="tablist">${tabs.map(([id, label], index) =>
        `<button type="button" role="tab" id="workbench-tab-${id}" aria-controls="workbench-page-${id}" aria-selected="${index === 0 ? 'true' : 'false'}" tabindex="${index === 0 ? '0' : '-1'}" class="workbench-tab ${index === 0 ? 'active' : ''}" data-workbench-tab="${id}">${label}</button>`).join('')}</div>
      <div class="workbench-page active" role="tabpanel" id="workbench-page-decision" aria-labelledby="workbench-tab-decision" data-workbench-page="decision">${decisionPage}${committeePage}</div>
      <div class="workbench-page" role="tabpanel" id="workbench-page-evidence" aria-labelledby="workbench-tab-evidence" data-workbench-page="evidence">${evidencePage}${businessPage}</div>
      <div class="workbench-page" role="tabpanel" id="workbench-page-model" aria-labelledby="workbench-tab-model" data-workbench-page="model">${valuationPage}${optionalityPage}${methodPage}</div>
      <div class="workbench-page" role="tabpanel" id="workbench-page-history" aria-labelledby="workbench-tab-history" data-workbench-page="history">${outcomesPage}${attributionPage}</div>
    </div>`;
  }

  function renderLegacyComponentNote(t, escapeHtml) {
    const cv = t.component_valuation;
    if (!cv || t.valuation_workbench) return '';
    return `<div class="detail-section">
      <h3>Component schedule <span class="badge badge-warn">legacy / provisional</span></h3>
      <p class="tier-sub">No valuation workbench yet. Treat this schedule as a first-pass inventory, not decision-grade.</p>
    </div>`;
  }

  function fmtQuoteCompact(n, units) {
    // Market caps and aggregates are in the listing currency too. window
    // access keeps this usable from the module's non-helper call sites.
    if (n == null || Number.isNaN(Number(n))) return '—';
    return window.DashboardFormat.compactQuote(Number(n), units || null);
  }

  function propertyUnitsLabel(units) {
    if (!units) return '';
    const parts = [];
    if (units.acres != null) parts.push(`${Number(units.acres).toLocaleString()} acres`);
    if (units.nra != null) parts.push(`${Number(units.nra).toLocaleString()} NRA`);
    if (units.acre_feet != null) parts.push(`${Number(units.acre_feet).toLocaleString()} AF`);
    if (units.sqft != null) parts.push(`${Number(units.sqft).toLocaleString()} sqft`);
    return parts.join(' · ');
  }

  function renderPropertiesPanel(t, helpers) {
    const { escapeHtml, fmtNum, tickerLookup } = helpers;
    const units = helpers.quoteUnitsOf ? helpers.quoteUnitsOf(t) : null;
    const fmtQuote = (v, d) => helpers.fmtQuote(v, units, d);
    const reg = t.properties;
    if (!reg || !(reg.properties || []).length) return '';
    const reconOk = reg.reconciliation_ok;
    const reconBadge = reconOk === true
      ? '<span class="badge badge-ok">reconciled</span>'
      : reconOk === false
        ? '<span class="badge badge-warn">needs review</span>'
        : '<span class="badge badge-warn">unchecked</span>';
    const rows = (reg.properties || []).map((p) => {
      const fv = p.fair_value_usd || {};
      const units = propertyUnitsLabel(p.units);
      const flags = (p.flags || []).length
        ? `<div class="tier-sub">${escapeHtml((p.flags || []).join(' · ').slice(0, 180))}</div>`
        : '';
      return `<tr>
        <td><strong>${escapeHtml(p.name || p.id || '—')}</strong>
          <div class="tier-sub">${escapeHtml((p.type || '').replace(/_/g, ' '))}${p.location ? ' · ' + escapeHtml(p.location) : ''}${units ? ' · ' + escapeHtml(units) : ''}</div>
          ${flags}
        </td>
        <td>${escapeHtml(p.status || '—')}</td>
        <td class="mono">${escapeHtml(p.nav_overlay_line || '—')}</td>
        <td class="mono">${fmtQuoteCompact(p.carrying_value_usd, units)}</td>
        <td class="mono">${fmtQuoteCompact(fv.low, units)} / ${fmtQuoteCompact(fv.base, units)} / ${fmtQuoteCompact(fv.high, units)}</td>
      </tr>`;
    }).join('');
    return `<div class="detail-section property-register">
      <div class="workbench-head">
        <div>
          <h3>Properties ${reconBadge}</h3>
          <div class="tier-sub">${Number(reg.property_count || 0)} assets · total fair value ${fmtQuoteCompact(reg.total_fair_value_usd, units)} · as of ${escapeHtml(reg.as_of || '—')}${reg.in_base_irr ? '' : ' · context / NAV inventory only'}</div>
        </div>
        ${reg.github_url ? `<a class="research-link" href="${reg.github_url}" target="_blank" rel="noopener">properties.json →</a>` : ''}
      </div>
      <p class="tier-sub" style="margin:0 0 10px">Maps to <code>nav_overlay</code> lines for reconciliation. Does not auto-inflate base IRR.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Property</th><th>Status</th><th>Overlay line</th><th>Carrying</th><th>Fair value L/B/H</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${(reg.unknown_targets || []).length ? `<p class="tier-sub" style="margin-top:8px">Unknown overlay targets: ${escapeHtml((reg.unknown_targets || []).join(', '))}</p>` : ''}
    </div>`;
  }

  function renderQueuePanel(queue, helpers) {
    const { escapeHtml, fmtNum, fmtPct } = helpers;
    // The queue mixes listings, so each row resolves its own units.
    const fmtQuote = (v, row, d) => helpers.fmtQuote(v, helpers.quoteUnitsOf(row), d);
    if (!queue || !(queue.items || []).length) {
      return '<div class="loading">Valuation queue empty. Run refresh_valuation_dashboard_rows.py after followups exist.</div>';
    }
    const counts = queue.counts || {};
    const tier1Readiness = queue.tier_1_readiness || {};
    const waves = queue.expansion_waves || {};
    const rows = (queue.items || []).map((row) => {
      const meta = modelLevelMeta(row.model_level, row.decision_status);
      const values = row.value_per_share || {};
      const valuationTier = row.valuation_tier || {};
      const tier = String(row.next_gap_progress_tier || '');
      const tierBadge = tier === 'partially_met'
        ? '<span class="badge badge-warn">partially met</span>'
        : tier === 'not_met'
          ? '<span class="badge badge-bad">not met</span>'
          : tier === 'met'
            ? '<span class="badge badge-ok">met</span>'
            : '';
      const progress = row.next_gap_progress_note
        ? `<div class="tier-sub">${tierBadge ? `${tierBadge} ` : ''}${escapeHtml(String(row.next_gap_progress_note).slice(0, 140))}</div>`
        : (tierBadge ? `<div class="tier-sub">${tierBadge}</div>` : '');
      const tickerRow = typeof tickerLookup === 'function' ? tickerLookup(row.ticker) : null;
      const technical = global.TechnicalViz && tickerRow
        ? global.TechnicalViz.renderSetupCell(tickerRow, escapeHtml)
        : '<span class="technical-empty">—</span>';
      const priority = row.priority || {};
      const readinessState = String(row.readiness_state || 'curated_followup');
      const readinessLabel = readinessState.replace(/_/g, ' ');
      const priorityClass = Number(priority.rank || 999) <= 20
        ? 'badge-bad'
        : Number(priority.rank || 999) <= 60
          ? 'badge-warn'
          : 'badge-neutral';
      const priceFreshness = (row.freshness || {}).price_as_of || {};
      const factFreshness = (row.freshness || {}).latest_fact_as_of || {};
      const freshnessText = row.queue_scope === 'tier_1'
        ? `price ${priceFreshness.age_days == null ? 'missing' : `${priceFreshness.age_days}d`} · facts ${factFreshness.age_days == null ? 'missing' : `${factFreshness.age_days}d`}`
        : 'curated follow-up';
      const margin = row.margin_of_safety_pct?.base;
      const committee = row.committee || {};
      const committeeText = committee.required
        ? `${Number(committee.completed || 0)}/${Number(committee.required || 0)}`
        : 'not started';
      return `<tr class="clickable-row" data-valuation-queue-ticker="${escapeHtml(row.ticker)}" tabindex="0" role="button" aria-label="Open ${escapeHtml(row.ticker)} evidence">
        <td><strong>${escapeHtml(row.ticker)}</strong><div class="tier-sub">${escapeHtml(row.company || '')}</div></td>
        <td>${escapeHtml(String(row.method_profile || '—').replace(/_/g, ' '))}</td>
        <td><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span><div class="tier-sub">${escapeHtml(valuationTier.label || (valuationTier.tier ? `Tier ${valuationTier.tier}` : 'tier not assigned'))}${row.in_validation_cohort ? ' · cohort' : ''}</div></td>
        <td><span class="badge ${priorityClass}">${escapeHtml(readinessLabel)}</span><div class="tier-sub">${escapeHtml(String(priority.bucket || '').replace(/_/g, ' '))} · ${escapeHtml(freshnessText)}</div></td>
        <td class="mono">${Number(row.critical_gap_count || 0)} / ${Number(row.open_gap_count || 0)}<div class="tier-sub">${Number((row.blocker_codes || []).length)} blockers</div></td>
        <td>${escapeHtml(row.next_action || row.next_gap_question || row.next_gap_id || '—')}${progress}</td>
        <td class="mono">${row.price_per_share == null ? '—' : fmtQuote(row.price_per_share, row, 0)} / ${values.base == null ? '—' : fmtQuote(values.base, row, 0)}</td>
        <td class="mono ${margin == null ? '' : Number(margin) >= 0 ? 'irr-pass' : 'irr-fail'}">${margin == null ? '—' : `${Number(margin) > 0 ? '+' : ''}${fmtPct(margin)}`}</td>
        <td><span class="mono">${committeeText}</span><div class="tier-sub">${escapeHtml(String(committee.current_phase || committee.status || 'pending').replace(/_/g, ' '))}</div></td>
        <td>${technical}</td>
      </tr>`;
    }).join('');
    const waveCards = Object.entries(waves).map(([id, w]) => `
      <div class="summary-card">
        <div class="label">${escapeHtml((w.label || id).replace(/_/g, ' '))}</div>
        <div class="value" style="font-size:16px">${escapeHtml(w.status || 'queued')}</div>
        <div class="sub">${(w.tickers || w.candidate_tickers || []).length || 0} tickers</div>
      </div>`).join('');
    return `
      <div class="metric-grid" style="margin-bottom:14px">
        <div class="metric"><div class="k">Tier 1 names</div><div class="v mono">${Number(counts.tier_1 || 0)}</div></div>
        <div class="metric"><div class="k">Research blocked</div><div class="v mono">${Number(tier1Readiness.research_blocked_count || 0)}</div></div>
        <div class="metric"><div class="k">Need model depth</div><div class="v mono">${Number(counts.model_deepening_required || 0)}</div></div>
        <div class="metric"><div class="k">Committee ready</div><div class="v mono">${Number(counts.committee_ready || 0)}</div></div>
      </div>
      ${waveCards ? `<div class="summary-strip" style="margin-bottom:14px">${waveCards}</div>` : ''}
      <p class="subhead">Tier 1 is ordered by evidence, model depth, freshness, then independent review. Curated Tier 2/3 followups remain below it. Click a row to open its Evidence tab.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Ticker</th><th>Method</th><th>Model</th><th>Readiness priority</th><th>Crit / open</th><th>Next action</th><th>Price / base</th><th>MoS</th><th>Committee</th><th>Technical setup</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function matchesValuationFilter(t, valuationFilter) {
    if (!valuationFilter || valuationFilter === 'ALL') return true;
    const d = decisionOf(t);
    if (valuationFilter === 'evidence-blocked') return d.status === 'evidence_blocked';
    if (valuationFilter === 'decision-grade') return d.status === 'decision_grade';
    if (valuationFilter === 'provisional') return d.status === 'provisional' || d.provisional;
    if (valuationFilter === 'cohort') return !!d.in_validation_cohort;
    if (valuationFilter === 'phase2') return String(d.rollout_wave || '').startsWith('phase2');
    if (valuationFilter === 'tier-1') return Number((t.valuation_tier || d.universe_tier || {}).tier) === 1;
    if (valuationFilter === 'tier-2') return Number((t.valuation_tier || d.universe_tier || {}).tier) === 2;
    if (valuationFilter === 'tier-3') return Number((t.valuation_tier || d.universe_tier || {}).tier) === 3;
    if (valuationFilter === 'screening-grade') return d.model_level === 'screening_grade';
    if (valuationFilter === 'stock-specific') return ['stock_specific', 'committee_reviewed', 'owner_approved'].includes(d.model_level);
    if (valuationFilter.startsWith('profile:')) {
      return d.method_profile === valuationFilter.slice('profile:'.length);
    }
    return true;
  }

  global.ValuationViz = {
    decisionOf,
    statusMeta,
    modelLevelMeta,
    tierMeta,
    displayReturn,
    forecastGapLabel,
    renderMarketSyncCell,
    primaryPowerZone,
    renderPowerZoneCell,
    renderValuationStatusCell,
    renderValueRangeCell,
    renderPriceToBaseCell,
    renderDecisionStrip,
    renderValuationWorkbench,
    renderEconomicDiagnostics,
    renderLegacyComponentNote,
    renderPropertiesPanel,
    renderQueuePanel,
    matchesValuationFilter,
    workbenchStatusBadge,
  };
})(typeof window !== 'undefined' ? window : globalThis);
