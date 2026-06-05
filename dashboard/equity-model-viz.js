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

  function renderKpiRow(bundle, escapeHtml) {
    const nc = (bundle.nowcast || {}).nowcast_jpym || {};
    const spec = bundle.spec || {};
    const bf = spec.base_fee || {};
    const pf = spec.perf_fee || {};
    const law = bundle.lawrence || {};
    const oos = (bundle.oos_metrics || {}).model || {};
    const naive = (bundle.oos_metrics || {}).naive_lastyear || {};
    const beats = naive.rmse_jpym != null && oos.rmse_jpym != null && oos.rmse_jpym < naive.rmse_jpym;

    return `
    <div class="model-kpi-row">
      <div class="summary-card"><div class="label">Nowcast revenue</div><div class="value" style="font-size:16px">${fmtYenM(nc.revenue)}</div><div class="sub">as of ${escapeHtml(bundle.as_of || '')}</div></div>
      <div class="summary-card"><div class="label">Nowcast net income</div><div class="value" style="font-size:16px">${fmtYenM(nc.net_income)}</div><div class="sub">${escapeHtml((bundle.nowcast || {}).fiscal_half || '')} window</div></div>
      <div class="summary-card"><div class="label">Base fee rate</div><div class="value" style="font-size:16px">${bf.base_rate_ann_est_pct != null ? (bf.base_rate_ann_est_pct * 100).toFixed(2) + '%/yr' : '—'}</div><div class="sub">effective on AUM</div></div>
      <div class="summary-card"><div class="label">Lawrence IRR</div><div class="value" style="font-size:16px;color:var(--accent-green)">${law.stance_gate_irr_pct != null ? law.stance_gate_irr_pct + '%/yr' : '—'}</div><div class="sub">stance gate · ${escapeHtml(law.stance || '')}</div></div>
      <div class="summary-card"><div class="label">OOS RMSE</div><div class="value" style="font-size:16px;color:${beats ? 'var(--accent-green)' : 'var(--accent-amber)'}">${oos.rmse_jpym != null ? fmtYenM(oos.rmse_jpym) : '—'}</div><div class="sub">${beats ? 'beats naive' : 'loses to naive ' + (naive.rmse_jpym != null ? fmtYenM(naive.rmse_jpym) : '')}</div></div>
    </div>`;
  }

  function renderSpecTable(bundle, escapeHtml) {
    const spec = bundle.spec || {};
    const bf = spec.base_fee || {};
    const pf = spec.perf_fee || {};
    return `
    <table class="darwin-table">
      <thead><tr><th>Block</th><th>Form</th></tr></thead>
      <tbody>
        <tr><td>Base fees</td><td class="mono" style="font-size:11px">${escapeHtml(bf.form || '')}</td></tr>
        <tr><td>Performance fees</td><td class="mono" style="font-size:11px">${escapeHtml(pf.form || '')}</td></tr>
        <tr><td>k H1 / H2</td><td class="mono">${pf.k_H1 ?? '—'} / ${pf.k_H2 ?? '—'}</td></tr>
      </tbody>
    </table>`;
  }

  function renderWalkForwardTable(wf, escapeHtml) {
    if (!wf || !wf.length) return '';
    return `
    <table class="darwin-table">
      <thead><tr><th>Period</th><th>Actual</th><th>Model</th><th>Naive YoY</th><th>Model err</th></tr></thead>
      <tbody>
        ${wf.map((r) => {
          const err = r.actual != null && r.model != null ? r.actual - r.model : null;
          return `<tr>
            <td class="mono">${escapeHtml(r.label)}</td>
            <td class="mono">${fmtYenM(r.actual)}</td>
            <td class="mono">${fmtYenM(r.model)}</td>
            <td class="mono">${fmtYenM(r.naive_lastyear)}</td>
            <td class="mono" style="color:${err > 0 ? 'var(--accent-amber)' : 'var(--text-secondary)'}">${err != null ? fmtYenM(err) : '—'}</td>
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
    const wfCanvas = document.getElementById('model-chart-walkforward');
    if (wfCanvas && wf.length) {
      makeChart(wfCanvas, {
        type: 'line',
        data: {
          labels: wf.map((w) => w.label),
          datasets: [
            { label: 'Actual', data: wf.map((w) => w.actual), borderColor: COLORS[2], tension: 0.2 },
            { label: 'Model', data: wf.map((w) => w.model), borderColor: COLORS[0], tension: 0.2 },
            { label: 'Naive same-half YoY', data: wf.map((w) => w.naive_lastyear), borderColor: COLORS[4], borderDash: [4, 4], tension: 0.2 },
          ],
        },
        options: { ...chartDefaults(), plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Walk-forward revenue (¥m)', color: '#8896ae' } } },
      });
    }

    const oos = bundle.oos_metrics || {};
    const oosCanvas = document.getElementById('model-chart-oos');
    if (oosCanvas) {
      const methods = [
        { k: 'model', label: 'Structural model', color: COLORS[0] },
        { k: 'naive_lastyear', label: 'Naive YoY', color: COLORS[4] },
        { k: 'naive_randomwalk', label: 'Random walk', color: COLORS[5] },
      ].filter((m) => oos[m.k]);
      makeChart(oosCanvas, {
        type: 'bar',
        data: {
          labels: methods.map((m) => m.label),
          datasets: [{ label: 'RMSE (¥m)', data: methods.map((m) => oos[m.k].rmse_jpym), backgroundColor: methods.map((m) => m.color) }],
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults(),
          plugins: { ...chartDefaults().plugins, title: { display: true, text: 'Out-of-sample RMSE (lower is better)', color: '#8896ae' } },
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

    return `
    <div class="detail-section model-section">
      <h3>Earnings model <span class="badge badge-ok" style="margin-left:6px">live</span></h3>
      ${renderLiquidityBanner(bundle.liquidity, escapeHtml)}
      <p class="subhead" style="margin-bottom:12px">Structural semiannual model · ${escapeHtml(bundle.as_of || '')}</p>
      ${renderKpiRow(bundle, escapeHtml)}
      <div class="model-charts">
        <div class="chart-box"><canvas id="model-chart-revenue"></canvas></div>
        <div class="chart-box"><canvas id="model-chart-walkforward"></canvas></div>
        <div class="chart-box split"><canvas id="model-chart-oos"></canvas></div>
        <div class="chart-box split"><canvas id="model-chart-shares"></canvas></div>
      </div>
      <h3 style="margin-top:14px">Model specification</h3>
      ${renderSpecTable(bundle, escapeHtml)}
      <h3 style="margin-top:14px">Walk-forward errors</h3>
      ${renderWalkForwardTable(bundle.walk_forward, escapeHtml)}
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
