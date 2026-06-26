/** Equity model charts + detail panel (Chart.js). */
(function (global) {
  const COLORS = [
    '#3b82f6', '#06b6d4', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444',
    '#ec4899', '#14b8a6', '#a855f7',
  ];

  let charts = [];

  function destroyCharts() {
    charts.forEach((c) => { try { c.destroy(); } catch (_) { /* noop */ } });
    charts = [];
  }

  function fmtYenM(v) {
    if (v == null || Number.isNaN(v)) return '—';
    const n = Number(v);
    if (Math.abs(n) >= 1000) return `¥${(n / 1000).toFixed(2)}bn`;
    return `¥${n.toFixed(0)}m`;
  }

  function fmtPct(v) {
    if (v == null) return '—';
    return `${(Number(v) * 100).toFixed(1)}%`;
  }

  function fmtR2(v) {
    if (v == null || Number.isNaN(v)) return '—';
    const n = Number(v);
    const color = n < 0 ? 'var(--accent-red)' : n < 0.3 ? 'var(--accent-amber)' : 'var(--accent-green)';
    return `<span style="color:${color}">${n.toFixed(3)}</span>`;
  }

  function chartDefaults() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8896ae', font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: '#566580', maxRotation: 45 }, grid: { color: '#1e2d46' } },
        y: { ticks: { color: '#566580' }, grid: { color: '#1e2d46' } },
      },
    };
  }

  function makeChart(canvas, config) {
    if (!canvas || typeof Chart === 'undefined') return null;
    const ch = new Chart(canvas, config);
    charts.push(ch);
    return ch;
  }

  function prod(bundle) {
    return bundle.production || {};
  }

  function productionSpec(bundle) {
    return prod(bundle).spec || bundle.production_spec || 'v1';
  }

  function walkForwardKey(bundle) {
    return prod(bundle).walk_forward_key || 'model_v5';
  }

  function walkForwardPred(row, key) {
    if (row[key] != null && !Number.isNaN(Number(row[key]))) return row[key];
    return row.model;
  }

  function renderHowItWorks(bundle, escapeHtml) {
    const p = prod(bundle);
    const spec = productionSpec(bundle);
    const revRmse = p.revenue_oos_rmse;
    const perfRmse = p.perf_fee_h2_oos_rmse;
    const v1Perf = p.v1_perf_fee_h2_oos_rmse;
    const v2Rev = p.v2_revenue_oos_rmse;
    const v2Perf = p.v2_perf_fee_h2_oos_rmse;
    const nc = (bundle.nowcast || {}).nowcast_jpym || {};
    return `
    <details class="model-explainer" open>
      <summary>How this model works <span class="spec-badge">${escapeHtml(spec)} production</span></summary>
      <div class="model-explainer-body">
        <p><strong>What we forecast.</strong> Semiannual revenue ≈ base fee + performance fee + ~¥200m other.
        Japanese FY ends March; <strong>H2 revenue is often 2–3× H1</strong> when perf fees crystallize.</p>
        <p><strong>How ${escapeHtml(spec)} works.</strong></p>
        <ol class="model-explainer-steps">
          <li><strong>Base fees</strong> — split effective rate on non-listed sleeve (~81%) vs listed ETF sleeve (~19%) from filings.</li>
          <li><strong>Perf fees</strong> — sum fund-level crystallization (Value Up, Orka, PBR ETFs) from mandate NAV scrape; Jan–Mar window on H2.</li>
          <li><strong>AUM path</strong> — roll forward with JITA-scaled industry flows and JPX ETF creation/redemption units.</li>
          <li><strong>Live nowcast</strong> — mark filing AUM sleeves to Nikkei + ETF basket; apply fitted coefficients${nc.revenue ? ` (current H1 ≈ ${fmtYenM(nc.revenue)})` : ''}.</li>
        </ol>
        <p class="model-explainer-gate"><strong>Why ${escapeHtml(spec)} is production.</strong>
          Gate = lowest <em>perf-fee H2</em> walk-forward RMSE that does not worsen vs v1.
          ${perfRmse != null && v1Perf != null ? `${escapeHtml(spec)} perf H2 OOS ${fmtYenM(perfRmse)} vs v1 ${fmtYenM(v1Perf)}.` : ''}
          ${v2Rev != null && revRmse != null ? ` v2 wins <em>revenue level</em> (${fmtYenM(v2Rev)} vs ${fmtYenM(revRmse)}) but fails perf gate${v2Perf != null ? ` (${fmtYenM(v2Perf)})` : ''}.` : ''}
        </p>
        <p class="model-explainer-note">Negative revenue R² is normal here — the edge is seasonal perf crystallization and pre-report nowcast, not beating same-half-last-year on total revenue every half.</p>
      </div>
    </details>`;
  }

  function renderLiquidityBanner(liq, escapeHtml) {
    if (!liq || liq.tier === 'standard') return '';
    const lp = liq.last_print || {};
    return `
    <div class="liquidity-banner">
      <strong>${escapeHtml(liq.exchange || 'Illiquid')}</strong>
      ${liq.warning ? `<p>${escapeHtml(liq.warning)}</p>` : ''}
      ${lp.date ? `<p class="mono" style="margin-top:6px;font-size:11px">Last print: ¥${lp.price_jpy} × ${lp.volume_shares} sh (${lp.date})</p>` : ''}
    </div>`;
  }

  function renderPmKpiRow(bundle, escapeHtml) {
    const diag = bundle.diagnostics || {};
    const targets = diag.targets || {};
    const perf = targets.perf_fee_h2_positive || {};
    const rev = targets.revenue_total || {};
    const perfOos = perf.out_of_sample || {};
    const revOos = rev.out_of_sample || {};
    const gap = rev.overfit_gap;
    const gapAmber = gap != null && gap > 0.15;
    const spec = productionSpec(bundle);
    const naive = (rev.benchmarks_oos || {}).naive_lastyear || {};
    return `
    <div class="model-kpi-row pm-kpi-row">
      <div class="summary-card"><div class="label">Perf fee H2+ OOS R²</div><div class="value" style="font-size:18px">${fmtR2(perfOos.r2)}</div><div class="sub">primary KPI · n=${perfOos.n ?? '—'}</div></div>
      <div class="summary-card"><div class="label">Revenue OOS R²</div><div class="value" style="font-size:16px">${fmtR2(revOos.r2)}</div><div class="sub">RMSE ${revOos.rmse_jpym != null ? fmtYenM(revOos.rmse_jpym) : '—'}</div></div>
      <div class="summary-card"><div class="label">IS vs OOS gap</div><div class="value" style="font-size:16px;color:${gapAmber ? 'var(--accent-amber)' : 'var(--text-primary)'}">${gap != null ? gap.toFixed(3) : '—'}</div><div class="sub">revenue overfit gap</div></div>
      <div class="summary-card"><div class="label">Production spec</div><div class="value" style="font-size:16px">${escapeHtml(spec)}<span class="spec-badge">active</span></div><div class="sub">${naive.beats_model ? 'naive LY wins level' : 'model wins level'}</div></div>
    </div>`;
  }

  function renderDiagnosticsBanner(bundle, escapeHtml) {
    const spec = productionSpec(bundle);
    const p = prod(bundle);
    return `<div class="pm-diagnostics-banner">
      <strong>${escapeHtml(spec)} is production</strong> — selected on perf-fee H2 OOS RMSE
      ${p.perf_fee_h2_oos_rmse != null ? `(${fmtYenM(p.perf_fee_h2_oos_rmse)}` : ''}
      ${p.v1_perf_fee_h2_oos_rmse != null ? ` vs v1 ${fmtYenM(p.v1_perf_fee_h2_oos_rmse)})` : p.perf_fee_h2_oos_rmse != null ? ')' : '.'}
      Revenue level may still trail seasonal naive; PM scorecard uses structural v1 fit metrics for comparison.
    </div>`;
  }

  function renderScorecardTable(diag, escapeHtml) {
    const targets = diag.targets || {};
    const order = ['perf_fee_h2_positive', 'revenue_total', 'revenue_h2_only', 'base_fee', 'perf_fee', 'ordinary_profit', 'net_income'];
    const labels = {
      perf_fee_h2_positive: 'Perf fee (H2, perf>0)',
      revenue_total: 'Revenue total',
      revenue_h2_only: 'Revenue H2 only',
      base_fee: 'Base fee',
      perf_fee: 'Perf fee',
      ordinary_profit: 'Ordinary profit',
      net_income: 'Net income',
    };
    const rows = order.filter((k) => targets[k]).map((k) => {
      const t = targets[k];
      const isR = t.in_sample?.r2;
      const oosR = t.out_of_sample?.r2;
      const naive = (t.benchmarks_oos || {}).naive_lastyear;
      return `<tr>
        <td>${escapeHtml(labels[k] || k)}</td>
        <td class="mono">${isR != null ? Number(isR).toFixed(3) : '—'}</td>
        <td class="mono">${oosR != null ? Number(oosR).toFixed(3) : '—'}</td>
        <td class="mono">${t.out_of_sample?.rmse_jpym != null ? fmtYenM(t.out_of_sample.rmse_jpym) : '—'}</td>
        <td class="mono">${naive?.beats_model === true ? 'Naive' : naive?.beats_model === false ? 'Model' : '—'}</td>
      </tr>`;
    }).join('');
    if (!rows) return '';
    return `<table class="darwin-table">
      <thead><tr><th>Target</th><th>IS R²</th><th>OOS R²</th><th>OOS RMSE</th><th>Level winner</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  }

  function renderSpecLeaderboard(spec, escapeHtml) {
    const lb = (spec && spec.leaderboard) || [];
    if (!lb.length) return '';
    return `<table class="darwin-table">
      <thead><tr><th>Spec</th><th>Rev OOS RMSE</th><th>Rev OOS R²</th><th>Perf H2 RMSE</th><th>Default</th><th>Note</th></tr></thead>
      <tbody>${lb.map((r) => `<tr class="${r.production_default ? 'spec-row-active' : ''}">
        <td class="mono">${escapeHtml(r.spec)}${r.production_default ? ' <span class="spec-badge">active</span>' : ''}</td>
        <td class="mono">${r.revenue_oos_rmse != null ? fmtYenM(r.revenue_oos_rmse) : '—'}</td>
        <td class="mono">${r.revenue_oos_r2 != null ? Number(r.revenue_oos_r2).toFixed(3) : '—'}</td>
        <td class="mono">${r.perf_fee_h2_oos_rmse != null ? fmtYenM(r.perf_fee_h2_oos_rmse) : '—'}</td>
        <td>${r.production_default ? '<span class="badge badge-ok">yes</span>' : '—'}</td>
        <td style="font-size:11px;color:var(--text-secondary)">${escapeHtml(r.note || '')}</td>
      </tr>`).join('')}</tbody>
    </table>`;
  }

  function renderAttributionTable(diag, escapeHtml) {
    const rows = diag.residual_attribution || [];
    if (!rows.length) return '';
    return `<table class="darwin-table">
      <thead><tr><th>Period</th><th>Actual</th><th>Fitted</th><th>Residual</th><th>Note</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td class="mono">${escapeHtml(r.label)}</td>
        <td class="mono">${fmtYenM(r.actual)}</td>
        <td class="mono">${fmtYenM(r.fitted)}</td>
        <td class="mono" style="color:var(--accent-amber)">${fmtYenM(r.residual)}</td>
        <td style="font-size:11px">${escapeHtml(r.note || '')}</td>
      </tr>`).join('')}</tbody>
    </table>`;
  }

  function renderCoeffTable(coeff, escapeHtml) {
    if (!coeff || !Object.keys(coeff).length) return '';
    return `<table class="darwin-table">
      <thead><tr><th>Coefficient</th><th>Point</th><th>p05</th><th>p95</th></tr></thead>
      <tbody>${Object.entries(coeff).map(([k, v]) => `<tr>
        <td class="mono">${escapeHtml(k)}</td>
        <td class="mono">${v.point ?? '—'}</td>
        <td class="mono">${v.p05 ?? '—'}</td>
        <td class="mono">${v.p95 ?? '—'}</td>
      </tr>`).join('')}</tbody>
    </table>`;
  }

  function renderKpiRow(bundle, escapeHtml) {
    const nc = (bundle.nowcast || {}).nowcast_jpym || {};
    const specForms = bundle.spec || {};
    const bf = specForms.base_fee || {};
    const pf = specForms.perf_fee || {};
    const split = pf.split_base_rates || {};
    const law = bundle.lawrence || {};
    const p = prod(bundle);
    const prodOos = p.oos_revenue || (bundle.oos_metrics_v5 || {}).model_v5 || {};
    const naive = (bundle.oos_metrics || {}).naive_lastyear || {};
    const revRmse = prodOos.rmse_jpym != null ? prodOos.rmse_jpym : p.revenue_oos_rmse;
    const beatsRev = naive.rmse_jpym != null && revRmse != null && revRmse < naive.rmse_jpym;
    const spec = productionSpec(bundle);
    const baseRateLabel = split.rate_nonlisted_ann != null
      ? `NL ${(split.rate_nonlisted_ann * 100).toFixed(2)}% · ETF ${(split.rate_etf_ann * 100).toFixed(2)}%`
      : (bf.base_rate_ann_est_pct != null ? (bf.base_rate_ann_est_pct * 100).toFixed(2) + '%/yr' : '—');

    return `
    <div class="model-kpi-row">
      <div class="summary-card"><div class="label">Nowcast revenue</div><div class="value" style="font-size:16px">${fmtYenM(nc.revenue)}</div><div class="sub">${escapeHtml(spec)} · ${escapeHtml((bundle.nowcast || {}).fiscal_half || '')}</div></div>
      <div class="summary-card"><div class="label">Nowcast net income</div><div class="value" style="font-size:16px">${fmtYenM(nc.net_income)}</div><div class="sub">as of ${escapeHtml(bundle.as_of || bundle.nowcast?.asof || '')}</div></div>
      <div class="summary-card"><div class="label">Base fee rate</div><div class="value" style="font-size:14px">${baseRateLabel}</div><div class="sub">${split.rate_nonlisted_ann != null ? 'split base (v5)' : 'effective on AUM'}</div></div>
      <div class="summary-card"><div class="label">Lawrence IRR</div><div class="value" style="font-size:16px;color:var(--accent-green)">${law.stance_gate_irr_pct != null ? law.stance_gate_irr_pct + '%/yr' : '—'}</div><div class="sub">stance gate · ${escapeHtml(law.stance || '')}</div></div>
      <div class="summary-card metric-gate"><div class="label">Perf H2 OOS RMSE</div><div class="value" style="font-size:16px;color:var(--accent-green)">${p.perf_fee_h2_oos_rmse != null ? fmtYenM(p.perf_fee_h2_oos_rmse) : '—'}</div><div class="sub">production gate · ${escapeHtml(spec)}${p.v1_perf_fee_h2_oos_rmse != null ? ' · v1 ' + fmtYenM(p.v1_perf_fee_h2_oos_rmse) : ''}</div></div>
      <div class="summary-card"><div class="label">Revenue OOS RMSE</div><div class="value" style="font-size:16px;color:${beatsRev ? 'var(--accent-green)' : 'var(--accent-amber)'}">${revRmse != null ? fmtYenM(revRmse) : '—'}</div><div class="sub">${beatsRev ? 'beats naive' : 'loses to naive ' + (naive.rmse_jpym != null ? fmtYenM(naive.rmse_jpym) : '')} · ${escapeHtml(spec)}</div></div>
    </div>`;
  }

  function renderSpecTable(bundle, escapeHtml) {
    const specForms = bundle.spec || {};
    const bf = specForms.base_fee || {};
    const pf = specForms.perf_fee || {};
    const split = pf.split_base_rates || {};
    const spec = productionSpec(bundle);
    const v1 = bundle.spec_v1 || {};
    const v1pf = v1.perf_fee || {};
    const splitRow = split.rate_nonlisted_ann != null ? `
        <tr><td>Split base (v5)</td><td class="mono" style="font-size:11px">non-listed ${(split.rate_nonlisted_ann * 100).toFixed(3)}%/yr · ETF ${(split.rate_etf_ann * 100).toFixed(3)}%/yr</td></tr>` : '';
    return `
    <table class="darwin-table">
      <thead><tr><th>Block</th><th>Form (${escapeHtml(spec)} production)</th></tr></thead>
      <tbody>
        <tr><td>Base fees</td><td class="mono" style="font-size:11px">${escapeHtml(bf.form || '')}</td></tr>
        ${splitRow}
        <tr><td>Performance fees</td><td class="mono" style="font-size:11px">${escapeHtml(pf.form || '')}</td></tr>
        <tr><td>k scale / H1·H2</td><td class="mono">${pf.k_scale != null ? 'k_scale ' + pf.k_scale : (v1pf.k_H1 ?? '—') + ' / ' + (v1pf.k_H2 ?? '—')}</td></tr>
        <tr><td>March window</td><td class="mono">${pf.use_march === true ? 'yes (H2 crystallization)' : pf.use_march === false ? 'no' : '—'}</td></tr>
      </tbody>
    </table>`;
  }

  function renderWalkForwardTable(wf, bundle, escapeHtml) {
    if (!wf || !wf.length) return '';
    const key = walkForwardKey(bundle);
    const spec = productionSpec(bundle);
    const label = spec.toUpperCase();
    return `
    <table class="darwin-table">
      <thead><tr><th>Period</th><th>Actual</th><th>${label}</th><th>Naive YoY</th><th>${label} err</th><th>v1 (legacy)</th></tr></thead>
      <tbody>
        ${wf.map((r) => {
          const pred = walkForwardPred(r, key);
          const err = r.actual != null && pred != null ? r.actual - pred : null;
          return `<tr>
            <td class="mono">${escapeHtml(r.label)}</td>
            <td class="mono">${fmtYenM(r.actual)}</td>
            <td class="mono">${fmtYenM(pred)}</td>
            <td class="mono">${fmtYenM(r.naive_lastyear)}</td>
            <td class="mono" style="color:${err > 0 ? 'var(--accent-amber)' : 'var(--text-secondary)'}">${err != null ? fmtYenM(err) : '—'}</td>
            <td class="mono" style="color:var(--text-muted)">${fmtYenM(r.model)}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
  }

  function renderForecastsTable(forecasts, escapeHtml) {
    if (!forecasts || !forecasts.length) return '';
    return `
    <table class="darwin-table">
      <thead><tr><th>Horizon</th><th>Scenario</th><th>Nikkei</th><th>Revenue</th><th>Net income</th></tr></thead>
      <tbody>
        ${forecasts.map((r) => `<tr>
          <td class="mono">${escapeHtml(r.horizon)}</td>
          <td>${escapeHtml(r.scenario)}</td>
          <td class="mono">${fmtPct(r.nikkei_ret)}</td>
          <td class="mono">${fmtYenM(r.revenue_m)}</td>
          <td class="mono">${fmtYenM(r.net_income_m)}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  }

  function renderCharts(bundle) {
    const panel = bundle.panel || [];
    const labels = panel.map((p) => p.label);
    const baseFees = panel.map((p) => p.base_fee);
    const perfFees = panel.map((p) => p.perf_fee);
    const revenues = panel.map((p) => p.revenue);

    const revCanvas = document.getElementById('model-chart-revenue');
    if (revCanvas) {
      const hasDecomp = baseFees.some((v) => v != null) || perfFees.some((v) => v != null);
      if (hasDecomp) {
        makeChart(revCanvas, {
          type: 'bar',
          data: {
            labels,
            datasets: [
              { label: 'Base fee', data: baseFees, backgroundColor: COLORS[0], stack: 'fees' },
              { label: 'Performance fee', data: perfFees, backgroundColor: COLORS[4], stack: 'fees' },
            ],
          },
          options: {
            ...chartDefaults(),
            plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Revenue decomposition (¥m)', color: '#8896ae' } },
            scales: { ...chartDefaults().scales, x: { ...chartDefaults().scales.x, stacked: true }, y: { ...chartDefaults().scales.y, stacked: true } },
          },
        });
      } else {
        makeChart(revCanvas, {
          type: 'bar',
          data: { labels, datasets: [{ label: 'Revenue', data: revenues, backgroundColor: COLORS[0] }] },
          options: { ...chartDefaults(), plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Revenue (¥m)', color: '#8896ae' } } },
        });
      }
    }

    const wf = bundle.walk_forward || [];
    const wfKey = walkForwardKey(bundle);
    const wfSpec = productionSpec(bundle).toUpperCase();
    const wfCanvas = document.getElementById('model-chart-walkforward');
    if (wfCanvas && wf.length) {
      makeChart(wfCanvas, {
        type: 'line',
        data: {
          labels: wf.map((w) => w.label),
          datasets: [
            { label: 'Actual', data: wf.map((w) => w.actual), borderColor: COLORS[2], tension: 0.2 },
            { label: wfSpec, data: wf.map((w) => walkForwardPred(w, wfKey)), borderColor: COLORS[0], borderWidth: 2, tension: 0.2 },
            { label: 'Naive same-half YoY', data: wf.map((w) => w.naive_lastyear), borderColor: COLORS[4], borderDash: [4, 4], tension: 0.2 },
            { label: 'v1 (legacy)', data: wf.map((w) => w.model), borderColor: COLORS[5], borderDash: [2, 2], tension: 0.2, hidden: true },
          ],
        },
        options: { ...chartDefaults(), plugins: { ...chartDefaults().plugins, title: { display: true, text: `Walk-forward revenue · ${wfSpec} (¥m)`, color: '#8896ae' } } },
      });
    }

    const oos = bundle.oos_metrics || {};
    const prodOos = prod(bundle).oos_revenue || (bundle.oos_metrics_v5 || {}).model_v5 || {};
    const oosCanvas = document.getElementById('model-chart-oos');
    if (oosCanvas) {
      const specLabel = productionSpec(bundle).toUpperCase();
      const methods = [
        { rmse: prodOos.rmse_jpym, label: `${specLabel} revenue`, color: COLORS[0] },
        { rmse: (oos.naive_lastyear || {}).rmse_jpym, label: 'Naive YoY', color: COLORS[4] },
        { rmse: (oos.model || {}).rmse_jpym, label: 'v1 revenue', color: COLORS[5] },
      ].filter((m) => m.rmse != null);
      makeChart(oosCanvas, {
        type: 'bar',
        data: {
          labels: methods.map((m) => m.label),
          datasets: [{ label: 'Revenue OOS RMSE (¥m)', data: methods.map((m) => m.rmse), backgroundColor: methods.map((m) => m.color) }],
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Revenue OOS RMSE · perf H2 gate in spec chart', color: '#8896ae' } },
        },
      });
    }

    const diag = bundle.diagnostics || {};
    const targets = diag.targets || {};
    const r2Canvas = document.getElementById('model-chart-r2-bars');
    if (r2Canvas && Object.keys(targets).length) {
      const order = ['perf_fee_h2_positive', 'revenue_total', 'revenue_h2_only', 'base_fee', 'perf_fee'];
      const labels = order.filter((k) => targets[k]).map((k) => k.replace(/_/g, ' '));
      const isData = order.filter((k) => targets[k]).map((k) => targets[k].in_sample?.r2 ?? null);
      const oosData = order.filter((k) => targets[k]).map((k) => targets[k].out_of_sample?.r2 ?? null);
      makeChart(r2Canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'IS R²', data: isData, backgroundColor: COLORS[5] },
            { label: 'OOS R²', data: oosData, backgroundColor: COLORS[0] },
          ],
        },
        options: {
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'IS vs OOS R² by target', color: '#8896ae' } },
        },
      });
    }

    const spec = bundle.spec_comparison || {};
    const specCanvas = document.getElementById('model-chart-spec-leaderboard');
    if (specCanvas && (spec.leaderboard || []).length) {
      const lb = spec.leaderboard;
      const prodColors = lb.map((r) => (r.production_default ? COLORS[0] : COLORS[4]));
      makeChart(specCanvas, {
        type: 'bar',
        data: {
          labels: lb.map((r) => r.spec),
          datasets: [
            { label: 'Revenue OOS RMSE (¥m)', data: lb.map((r) => r.revenue_oos_rmse), backgroundColor: prodColors },
            { label: 'Perf H2 OOS RMSE (¥m)', data: lb.map((r) => r.perf_fee_h2_oos_rmse), backgroundColor: COLORS[2] },
          ],
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Spec leaderboard · production = min perf H2 RMSE ≤ v1', color: '#8896ae' } },
        },
      });
    }

    const residuals = (bundle.residuals || []).filter((r) => r.target === 'revenue_total' && r.is_oos === 1);
    const scatterCanvas = document.getElementById('model-chart-actual-fitted');
    if (scatterCanvas && residuals.length) {
      makeChart(scatterCanvas, {
        type: 'scatter',
        data: {
          datasets: [{
            label: 'OOS revenue',
            data: residuals.map((r) => ({ x: r.actual, y: r.fitted })),
            backgroundColor: COLORS[0],
          }],
        },
        options: {
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Actual vs fitted revenue (OOS · v1 structural)', color: '#8896ae' } },
          scales: {
            x: { ...chartDefaults().scales.x, title: { display: true, text: 'Actual ¥m', color: '#566580' } },
            y: { ...chartDefaults().scales.y, title: { display: true, text: 'Fitted ¥m', color: '#566580' } },
          },
        },
      });
    }

    const resOos = (bundle.residuals || []).filter((r) => r.target === 'revenue_total' && r.is_oos === 1);
    const resCanvas = document.getElementById('model-chart-residuals');
    if (resCanvas && resOos.length) {
      makeChart(resCanvas, {
        type: 'bar',
        data: {
          labels: resOos.map((r) => r.label),
          datasets: [{ label: 'Residual ¥m', data: resOos.map((r) => r.residual), backgroundColor: COLORS[5] }],
        },
        options: {
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'OOS revenue residuals', color: '#8896ae' } },
        },
      });
    }

    const tornado = diag.tornado || [];
    const torCanvas = document.getElementById('model-chart-tornado');
    if (torCanvas && tornado.length) {
      makeChart(torCanvas, {
        type: 'bar',
        data: {
          labels: tornado.map((t) => t.driver),
          datasets: [{ label: 'NI delta %', data: tornado.map((t) => t.ni_delta_pct), backgroundColor: COLORS[2] }],
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Tornado: H2 net income sensitivity', color: '#8896ae' } },
        },
      });
    }

    const shares = (bundle.shares || {}).series || [];
    const shCanvas = document.getElementById('model-chart-shares');
    if (shCanvas && shares.length) {
      makeChart(shCanvas, {
        type: 'line',
        data: {
          labels: shares.map((s) => s.date),
          datasets: [{ label: 'Split-adj shares', data: shares.map((s) => s.split_adjusted_shares / 1e6), borderColor: COLORS[3], tension: 0.1 }],
        },
        options: {
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Shares outstanding (split-adj, millions)', color: '#8896ae' } },
        },
      });
    }
  }

  function renderSection(bundle, helpers) {
    const { escapeHtml, linkHtml } = helpers;
    if (!bundle || !bundle.model_ready) return '';

    const links = bundle.links || {};
    const linkItems = [
      ['Model report', links.model_report],
      ['Data dictionary', links.data_dictionary],
      ['Forecasts CSV', links.forecasts_csv],
      ['Skeptical report', links.skeptical_report],
    ].filter(([, u]) => u);

    const specLabel = productionSpec(bundle);
    return `
    <div class="detail-section model-section">
      <h3>Earnings model <span class="spec-badge">${escapeHtml(specLabel)}</span> <span class="badge badge-ok" style="margin-left:6px">live</span></h3>
      ${renderLiquidityBanner(bundle.liquidity, escapeHtml)}
      <p class="subhead" style="margin-bottom:8px">${escapeHtml(bundle.headline || `Structural semiannual model · ${bundle.as_of || ''}`)}</p>
      ${renderHowItWorks(bundle, escapeHtml)}
      ${renderKpiRow(bundle, escapeHtml)}
      <div class="model-charts">
        <div class="chart-box"><canvas id="model-chart-revenue"></canvas></div>
        <div class="chart-box"><canvas id="model-chart-walkforward"></canvas></div>
        <div class="chart-box split"><canvas id="model-chart-oos"></canvas></div>
        <div class="chart-box split"><canvas id="model-chart-shares"></canvas></div>
      </div>
      ${bundle.diagnostics_ready ? `
      <h3 style="margin-top:18px">Model diagnostics <span class="spec-badge">${escapeHtml(specLabel)}</span></h3>
      ${renderDiagnosticsBanner(bundle, escapeHtml)}
      ${renderPmKpiRow(bundle, escapeHtml)}
      <div class="model-diagnostics-charts">
        <div class="chart-box wide"><canvas id="model-chart-r2-bars"></canvas></div>
        <div class="chart-box"><canvas id="model-chart-spec-leaderboard"></canvas></div>
        <div class="chart-box"><canvas id="model-chart-actual-fitted"></canvas></div>
        <div class="chart-box"><canvas id="model-chart-residuals"></canvas></div>
        <div class="chart-box wide"><canvas id="model-chart-tornado"></canvas></div>
      </div>
      <h3 style="margin-top:14px">PM scorecard</h3>
      ${renderScorecardTable(bundle.diagnostics, escapeHtml)}
      <h3 style="margin-top:14px">Spec comparison</h3>
      ${renderSpecLeaderboard(bundle.spec_comparison, escapeHtml)}
      <h3 style="margin-top:14px">Residual attribution</h3>
      ${renderAttributionTable(bundle.diagnostics, escapeHtml)}
      <h3 style="margin-top:14px">Coefficient bootstrap CIs</h3>
      ${renderCoeffTable(bundle.coefficient_bootstrap, escapeHtml)}
      ` : ''}
      <h3 style="margin-top:14px">Model specification</h3>
      ${renderSpecTable(bundle, escapeHtml)}
      <h3 style="margin-top:14px">Walk-forward errors</h3>
      ${renderWalkForwardTable(bundle.walk_forward, bundle, escapeHtml)}
      ${bundle.forecasts && bundle.forecasts.length ? `<h3 style="margin-top:14px">Scenarios</h3>${renderForecastsTable(bundle.forecasts, escapeHtml)}` : ''}
      ${(bundle.triangulation || []).length ? `
      <h3 style="margin-top:14px">Triangulation</h3>
      <ul class="dev-list">${bundle.triangulation.map((t) => `<li><div class="dev-label">${escapeHtml(t)}</div></li>`).join('')}</ul>` : ''}
      ${(bundle.caveats || []).length ? `
      <h3 style="margin-top:14px">Caveats</h3>
      <ul class="dev-list">${bundle.caveats.map((c) => `<li><div class="dev-label" style="color:var(--accent-amber)">${escapeHtml(c)}</div></li>`).join('')}</ul>` : ''}
      <div style="margin-top:12px;display:flex;flex-wrap:wrap;gap:12px">
        ${linkItems.map(([label, url]) => `<a class="research-link" href="${url}" target="_blank" rel="noopener">${escapeHtml(label)} →</a>`).join('')}
      </div>
    </div>`;
  }

  function afterRender(bundle) {
    destroyCharts();
    if (bundle && bundle.model_ready) {
      requestAnimationFrame(() => renderCharts(bundle));
    }
  }

  global.EquityModelViz = { renderSection, afterRender, destroyCharts };
})(typeof window !== 'undefined' ? window : globalThis);
