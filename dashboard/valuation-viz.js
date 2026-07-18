/**
 * Valuation workbench / queue / decision-status UI for the new economic-value model.
 * Keeps facts, estimates, judgments, and evidence blockers visible; never invents decision-grade.
 */
(function (global) {
  'use strict';

  function decisionOf(t) {
    return t.valuation_decision || {};
  }

  function statusMeta(status) {
    const s = String(status || 'missing');
    if (s === 'decision_grade') return { label: 'decision-grade', cls: 'badge-ok' };
    if (s === 'evidence_blocked') return { label: 'evidence blocked', cls: 'badge-bad' };
    if (s === 'provisional') return { label: 'provisional', cls: 'badge-warn' };
    if (s === 'operating-only') return { label: 'operating-only', cls: 'badge-warn' };
    return { label: 'missing', cls: 'badge-warn' };
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
    const meta = statusMeta(d.status);
    const crit = d.critical_gap_count;
    const open = d.open_gap_count;
    let sub = '';
    if (crit > 0) sub = `${crit} critical`;
    else if (open > 0) sub = `${open} open`;
    else if (d.status === 'decision_grade') sub = 'ready';
    else if (d.status === 'provisional') sub = 'first-pass';
    return `<div class="valuation-status-cell"><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span>${sub ? `<div class="tier-sub">${escapeHtml(sub)}</div>` : ''}</div>`;
  }

  function renderValueRangeCell(t, fmtNum) {
    const d = decisionOf(t);
    const r = d.value_per_share || t.component_valuation?.total_equity_value_per_share;
    if (!r || r.low == null || r.base == null || r.high == null) {
      return '<span class="mono" style="color:var(--text-muted)">incomplete</span>';
    }
    const prov = d.provisional || d.status === 'evidence_blocked' || d.status === 'provisional';
    return `<span class="mono">$${fmtNum(r.low, 0)}–$${fmtNum(r.high, 0)}<span class="irr-sub">base $${fmtNum(r.base, 0)}${prov ? ' · provisional' : ''}</span></span>`;
  }

  function renderPriceToBaseCell(t, fmtPct) {
    const d = decisionOf(t);
    const pct = d.upside_downside_pct?.base ?? t.component_valuation?.upside_downside_pct?.base;
    if (pct == null) return '<span class="mono" style="color:var(--text-muted)">—</span>';
    const cls = pct >= 0 ? 'irr-pass' : 'irr-fail';
    const title = (d.provisional || d.status === 'evidence_blocked')
      ? 'Not decision-grade while evidence-blocked'
      : 'Price vs base component value';
    return `<span class="irr-cell ${cls}" title="${title}">${pct > 0 ? '+' : ''}${fmtPct(pct)}</span>`;
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

  function renderDecisionStrip(t, helpers) {
    const { escapeHtml, fmtNum, fmtPct } = helpers;
    const d = decisionOf(t);
    const wb = t.valuation_workbench || {};
    const decision = wb.decision || d;
    if (!t.valuation_workbench && !t.component_valuation && d.status === 'missing') return '';
    const meta = statusMeta(d.status || decision.status);
    const values = decision.value_per_share || d.value_per_share || {};
    const returns = decision.annualized_return_at_price_pct || {};
    return `<div class="detail-section valuation-decision-strip">
      <h3>Valuation decision</h3>
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Readiness</div><div class="v"><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span></div></div>
        <div class="metric"><div class="k">Price / base</div><div class="v mono">$${fmtNum(decision.price_per_share || d.price_per_share)} / $${fmtNum(values.base)}</div></div>
        <div class="metric"><div class="k">Base return at price</div><div class="v mono">${fmtPct(returns.base)}</div></div>
      </div>
      <div class="metric-grid metric-grid-3" style="margin-top:9px">
        <div class="metric"><div class="k">Low / high</div><div class="v mono">$${fmtNum(values.low)} / $${fmtNum(values.high)}</div></div>
        <div class="metric"><div class="k">Critical / open gaps</div><div class="v mono">${Number(d.critical_gap_count || 0)} / ${Number(d.open_gap_count || 0)}</div></div>
        <div class="metric"><div class="k">Power zone</div><div class="v" style="font-size:12px">${escapeHtml(d.primary_power_zone || decision.primary_power_zone || '—')}</div></div>
      </div>
      <div class="workbench-callout"><strong>Next:</strong> ${escapeHtml(d.next_action || decision.next_action || 'Close evidence gaps before committee freeze.')}${d.next_gap_id ? `<div class="tier-sub" style="margin-top:4px">Next gap: ${escapeHtml(d.next_gap_id)}</div>` : ''}</div>
      ${(d.provisional || d.status === 'evidence_blocked') ? '<p class="tier-sub" style="margin-top:8px">Ranges are provisional until acceptance tests are met. Do not treat them as IC-approved targets.</p>' : ''}
    </div>`;
  }

  function renderValuationWorkbench(t, helpers) {
    const { escapeHtml, fmtNum, fmtPct, fmtSignedDollar, linkHtml } = helpers;
    const wb = t.valuation_workbench;
    if (!wb) return '';
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

    const ownershipRows = (business.components || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong>
        <div class="tier-sub">${escapeHtml(row.category || '')} · ${escapeHtml(row.treatment || '')} · overlap ${escapeHtml(row.overlap_key || row.component_id || '')}</div>
        ${row.falsifier ? `<div class="tier-sub">Falsifier: ${escapeHtml(row.falsifier)}</div>` : ''}
      </td>
      <td>${escapeHtml(row.ownership_claim || '')}${row.evidence ? `<div class="tier-sub">${escapeHtml(String(row.evidence).slice(0, 220))}</div>` : ''}</td>
      <td class="mono">$${fmtNum(row.range_per_share?.low)} / $${fmtNum(row.range_per_share?.base)} / $${fmtNum(row.range_per_share?.high)}</td>
      <td>${escapeHtml(row.assumption_type || row.evidence_level || '')}</td>
    </tr>`).join('');

    const scheduleRows = (valuation.components || business.components || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong><div class="tier-sub">${escapeHtml(row.method || '')}</div></td>
      <td class="mono">$${fmtNum(row.range_per_share?.low)}</td>
      <td class="mono">$${fmtNum(row.range_per_share?.base)}</td>
      <td class="mono">$${fmtNum(row.range_per_share?.high)}</td>
      <td>${escapeHtml(row.assumption_type || '')}</td>
    </tr>`).join('');

    const valueDrivers = (valuation.scenario_contract?.top_value_drivers || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong>${row.scenario_assumptions ? `<div class="tier-sub">${escapeHtml(typeof row.scenario_assumptions === 'string' ? row.scenario_assumptions : JSON.stringify(row.scenario_assumptions).slice(0, 180))}</div>` : ''}</td>
      <td class="mono">$${fmtNum(row.base_per_share)}</td>
      <td class="mono">$${fmtNum(row.range_width_per_share)}</td>
    </tr>`).join('');

    const reverse = valuation.scenario_contract?.reverse_expectations;
    const reverseHtml = reverse
      ? `<div class="workbench-item" style="margin-top:10px"><div class="workbench-item-title">Reverse expectations</div><pre class="workbench-item-meta" style="white-space:pre-wrap">${escapeHtml(typeof reverse === 'string' ? reverse : JSON.stringify(reverse, null, 2).slice(0, 1200))}</pre></div>`
      : '';

    const optionRows = (optionality.options || []).map((row) => `<tr>
      <td><strong>${escapeHtml(row.label || row.component_id)}</strong></td>
      <td>${escapeHtml(row.method || '')}</td>
      <td class="mono">$${fmtNum(row.range_per_share?.low)} / $${fmtNum(row.range_per_share?.base)} / $${fmtNum(row.range_per_share?.high)}</td>
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
          Value exposed: ${gap.base_value_exposure_per_share == null ? 'not isolated' : '$' + fmtNum(gap.base_value_exposure_per_share) + ' / share'}
          ${(gap.component_ids || []).length ? ` · ${(gap.component_ids || []).map(escapeHtml).join(' · ')}` : ''}
          ${gap.evidence_path ? ` · ${helpers.linkHtml
            ? helpers.linkHtml(
              (helpers.ghRepo ? `https://github.com/${helpers.ghRepo}/blob/main/` : '') + gap.evidence_path,
              gap.evidence_path
            )
            : escapeHtml(gap.evidence_path)}` : ''}
        </div>
      </div>`).join('');

    const decisionPage = `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Decision readiness</div><div class="v">${workbenchStatusBadge(decision.status, escapeHtml)}</div></div>
        <div class="metric"><div class="k">Price / base value</div><div class="v mono">$${fmtNum(decision.price_per_share)} / $${fmtNum(decision.value_per_share?.base)}</div></div>
        <div class="metric"><div class="k">Base annual return</div><div class="v mono">${fmtPct(decision.annualized_return_at_price_pct?.base)}</div></div>
      </div>
      <div class="metric-grid metric-grid-3" style="margin-top:9px">
        <div class="metric"><div class="k">Low / high value</div><div class="v mono">$${fmtNum(decision.value_per_share?.low)} / $${fmtNum(decision.value_per_share?.high)}</div></div>
        <div class="metric"><div class="k">Unvalued components</div><div class="v mono">${Number(decision.unvalued_component_count || 0)}</div></div>
        <div class="metric"><div class="k">Evidence blockers</div><div class="v mono">${Number(decision.unresolved_evidence_count || 0)}</div></div>
      </div>
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
        <div class="metric"><div class="k">Market cap</div><div class="v mono">${valuation.market?.market_cap_m == null ? '—' : '$' + fmtNum(valuation.market.market_cap_m) + 'm'}</div></div>
        <div class="metric"><div class="k">Base value</div><div class="v mono">$${fmtNum(valuation.valuation?.value_per_share?.base)}</div></div>
        <div class="metric"><div class="k">Low-case downside</div><div class="v mono">${fmtPct(valuation.valuation?.downside_to_low_pct)}</div></div>
      </div>
      <div class="workbench-callout">${escapeHtml(valuation.scenario_contract?.rule || '')}</div>
      ${scheduleRows ? `<h4 style="margin:13px 0 0">Component schedule</h4><table class="workbench-table"><thead><tr><th>Component</th><th>Low</th><th>Base</th><th>High</th><th>Type</th></tr></thead><tbody>${scheduleRows}</tbody></table>` : ''}
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
        <div class="metric"><div class="k">Primary personas</div><div class="v" style="font-size:11px">${(method.primary_personas || []).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ') || '—'}</div></div>
        <div class="metric"><div class="k">Cross-check personas</div><div class="v" style="font-size:11px">${(method.cross_check_personas || []).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ') || '—'}</div></div>
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
      <td class="mono">${fmtSignedDollar(row.change_per_share)}</td>
      <td>${(row.causes || []).map((x) => escapeHtml(String(x).replace(/_/g, ' '))).join(' · ')}</td>
    </tr>`).join('');
    const categoryRows = Object.entries(attribution.category_totals_per_share || {}).map(([key, value]) =>
      `<div class="metric"><div class="k">${escapeHtml(key.replace(/_/g, ' '))}</div><div class="v mono">${fmtSignedDollar(value)}</div></div>`).join('');
    const attributionPage = attribution.status === 'baseline_established' ? `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Current baseline</div><div class="v mono">$${fmtNum(attribution.current?.base)}</div></div>
        <div class="metric"><div class="k">As of</div><div class="v mono">${escapeHtml(attribution.current?.as_of || '—')}</div></div>
        <div class="metric"><div class="k">Attribution</div><div class="v">${workbenchStatusBadge(attribution.status, escapeHtml)}</div></div>
      </div>
      <div class="workbench-callout">${escapeHtml(attribution.explanation || '')}</div>` : `
      <div class="metric-grid metric-grid-3">
        <div class="metric"><div class="k">Prior base</div><div class="v mono">$${fmtNum(attribution.prior?.base)}</div><div class="tier-sub">${escapeHtml(attribution.prior?.as_of || '—')}</div></div>
        <div class="metric"><div class="k">Current base</div><div class="v mono">$${fmtNum(attribution.current?.base)}</div><div class="tier-sub">${escapeHtml(attribution.current?.as_of || '—')}</div></div>
        <div class="metric"><div class="k">Base change</div><div class="v mono">${fmtSignedDollar(attribution.base_change_per_share)}</div><div class="tier-sub">${fmtPct(attribution.base_change_pct)}</div></div>
      </div>
      ${categoryRows ? `<div class="metric-grid" style="margin-top:9px">${categoryRows}</div>` : ''}
      ${attributionDrivers ? `<table class="workbench-table"><thead><tr><th>Component</th><th>Change / share</th><th>Observed cause</th></tr></thead><tbody>${attributionDrivers}</tbody></table>` : ''}
      <div class="tier-sub" style="margin-top:8px">Unexplained reconciliation: ${fmtSignedDollar(attribution.unexplained_per_share)} · ${escapeHtml(attribution.explanation || '')}</div>`;

    const tabs = [
      ['decision', 'Decision'],
      ['business', 'Business'],
      ['valuation', 'Valuation'],
      ['optionality', 'Optionality'],
      ['evidence', 'Evidence'],
      ['method', 'Method fit'],
      ['committee', 'Committee'],
      ['outcomes', 'Outcomes'],
      ['attribution', 'Value changes'],
    ];

    return `<div class="detail-section valuation-workbench">
      <div class="workbench-head">
        <div>
          <h3>Valuation workbench ${workbenchStatusBadge(decision.status || committee.status, escapeHtml)}</h3>
          <div class="tier-sub">Decision readiness, ownership map, evidence gaps, method fit, committee, and measured outcomes · ${escapeHtml(wb.as_of || '—')}</div>
        </div>
        ${wb.github_url ? `<a class="research-link" href="${wb.github_url}" target="_blank" rel="noopener">Audit file →</a>` : ''}
      </div>
      <div class="workbench-tabs" role="tablist">${tabs.map(([id, label], index) =>
        `<button type="button" class="workbench-tab ${index === 0 ? 'active' : ''}" data-workbench-tab="${id}">${label}</button>`).join('')}</div>
      <div class="workbench-page active" data-workbench-page="decision">${decisionPage}</div>
      <div class="workbench-page" data-workbench-page="business">${businessPage}</div>
      <div class="workbench-page" data-workbench-page="valuation">${valuationPage}</div>
      <div class="workbench-page" data-workbench-page="optionality">${optionalityPage}</div>
      <div class="workbench-page" data-workbench-page="evidence">${evidencePage}</div>
      <div class="workbench-page" data-workbench-page="method">${methodPage}</div>
      <div class="workbench-page" data-workbench-page="committee">${committeePage}</div>
      <div class="workbench-page" data-workbench-page="outcomes">${outcomesPage}</div>
      <div class="workbench-page" data-workbench-page="attribution">${attributionPage}</div>
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

  function fmtUsdCompact(n, fmtNum) {
    if (n == null || Number.isNaN(Number(n))) return '—';
    const v = Number(n);
    if (Math.abs(v) >= 1e9) return '$' + fmtNum(v / 1e9, 2) + 'B';
    if (Math.abs(v) >= 1e6) return '$' + fmtNum(v / 1e6, 1) + 'M';
    if (Math.abs(v) >= 1e3) return '$' + fmtNum(v / 1e3, 0) + 'K';
    return '$' + fmtNum(v, 0);
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
    const { escapeHtml, fmtNum } = helpers;
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
        <td class="mono">${fmtUsdCompact(p.carrying_value_usd, fmtNum)}</td>
        <td class="mono">${fmtUsdCompact(fv.low, fmtNum)} / ${fmtUsdCompact(fv.base, fmtNum)} / ${fmtUsdCompact(fv.high, fmtNum)}</td>
      </tr>`;
    }).join('');
    return `<div class="detail-section property-register">
      <div class="workbench-head">
        <div>
          <h3>Properties ${reconBadge}</h3>
          <div class="tier-sub">${Number(reg.property_count || 0)} assets · total fair value ${fmtUsdCompact(reg.total_fair_value_usd, fmtNum)} · as of ${escapeHtml(reg.as_of || '—')}${reg.in_base_irr ? '' : ' · context / NAV inventory only'}</div>
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
    const { escapeHtml, fmtNum } = helpers;
    if (!queue || !(queue.items || []).length) {
      return '<div class="loading">Valuation queue empty. Run refresh_valuation_dashboard_rows.py after followups exist.</div>';
    }
    const counts = queue.counts || {};
    const waves = queue.expansion_waves || {};
    const rows = (queue.items || []).map((row) => {
      const meta = statusMeta(row.decision_status);
      const values = row.value_per_share || {};
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
      return `<tr class="clickable-row" data-valuation-queue-ticker="${escapeHtml(row.ticker)}">
        <td><strong>${escapeHtml(row.ticker)}</strong><div class="tier-sub">${escapeHtml(row.company || '')}</div></td>
        <td>${escapeHtml(String(row.method_profile || '—').replace(/_/g, ' '))}</td>
        <td><span class="badge ${meta.cls}">${escapeHtml(meta.label)}</span>${row.in_validation_cohort ? '<div class="tier-sub">cohort</div>' : ''}</td>
        <td class="mono">${Number(row.critical_gap_count || 0)} / ${Number(row.open_gap_count || 0)}</td>
        <td>${escapeHtml(row.next_gap_id || '—')}${row.next_gap_question ? `<div class="tier-sub">${escapeHtml(String(row.next_gap_question).slice(0, 120))}</div>` : ''}${progress}</td>
        <td class="mono">${values.base == null ? '—' : '$' + fmtNum(values.base, 0)}</td>
      </tr>`;
    }).join('');
    const waveCards = Object.entries(waves).map(([id, w]) => `
      <div class="summary-card">
        <div class="label">${escapeHtml((w.label || id).replace(/_/g, ' '))}</div>
        <div class="value" style="font-size:16px">${escapeHtml(w.status || 'queued')}</div>
        <div class="sub">${(w.tickers || w.candidate_tickers || []).length || 0} tickers</div>
      </div>`).join('');
    return `
      <div class="metric-grid metric-grid-3" style="margin-bottom:14px">
        <div class="metric"><div class="k">Queue tickers</div><div class="v mono">${Number(counts.tickers || 0)}</div></div>
        <div class="metric"><div class="k">Evidence blocked</div><div class="v mono">${Number(counts.evidence_blocked || 0)}</div></div>
        <div class="metric"><div class="k">Critical gaps</div><div class="v mono">${Number(counts.critical_gaps || 0)}</div></div>
      </div>
      ${waveCards ? `<div class="summary-strip" style="margin-bottom:14px">${waveCards}</div>` : ''}
      <p class="subhead">One ticker + one acceptance test at a time. Click a row to open the holdings detail Evidence tab.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Ticker</th><th>Method</th><th>Status</th><th>Crit / open</th><th>Next gap</th><th>Base / sh</th></tr></thead>
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
    if (valuationFilter.startsWith('profile:')) {
      return d.method_profile === valuationFilter.slice('profile:'.length);
    }
    return true;
  }

  global.ValuationViz = {
    decisionOf,
    statusMeta,
    renderValuationStatusCell,
    renderValueRangeCell,
    renderPriceToBaseCell,
    renderDecisionStrip,
    renderValuationWorkbench,
    renderLegacyComponentNote,
    renderPropertiesPanel,
    renderQueuePanel,
    matchesValuationFilter,
    workbenchStatusBadge,
  };
})(typeof window !== 'undefined' ? window : globalThis);
