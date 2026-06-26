/** Darwin tab charts + Deutsch explanation (Chart.js). */
(function (global) {
  const DARWIN_METHOD_LABELS = {
    ira_marvin: 'IRA Marvin',
    equal_weight: 'Equal weight',
    irr_ranked: 'IRR ranked',
    risk_parity_vol: 'Risk parity',
    genetic: 'Genetic',
    ppo: 'PPO',
    ensemble: 'Ensemble',
    champion: 'Champion (live)',
    spy: 'SPY',
  };

  const CHART_COLORS = [
    '#3b82f6', '#06b6d4', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444',
    '#ec4899', '#14b8a6', '#a855f7', '#84cc16', '#f97316', '#6366f1', '#64748b',
  ];

  let equityChart = null;
  let holdingsChart = null;

  function stripMd(s) {
    return String(s || '').replace(/\*\*/g, '');
  }

  function destroyCharts() {
    if (equityChart) { equityChart.destroy(); equityChart = null; }
    if (holdingsChart) { holdingsChart.destroy(); holdingsChart = null; }
  }

  function renderExplanation(ex, escapeHtml) {
    if (!ex) return '';
    const dc = ex.deutsch_checks || {};
    const checks = [
      ['Hard to vary', dc.hard_to_vary],
      ['Falsifiable', dc.falsifiable],
      ['Not instrumentalist', dc.not_instrumentalist],
      ['Reach', true],
    ];
    return `
    <div class="detail-section">
      <h3>Why this portfolio (Deutsch / Popper)</h3>
      <div class="deutsch-box">
        <p class="lead">${escapeHtml(stripMd(ex.summary))}</p>
        <p>${escapeHtml(ex.mechanism || '')}</p>
        <div class="deutsch-checks">
          ${checks.map(([label, ok]) => `
            <div class="deutsch-check ${ok ? 'pass' : 'fail'}">${escapeHtml(label)}: ${ok ? 'pass' : 'review'}</div>
          `).join('')}
        </div>
        ${(ex.flags || []).length ? `<ul style="margin-top:12px;padding-left:18px;color:var(--accent-amber);font-size:12px">${ex.flags.map(f => `<li>${escapeHtml(f)}</li>`).join('')}</ul>` : ''}
        <p style="margin-top:12px;font-size:11px;color:var(--text-muted)">Reach: ${escapeHtml(dc.reach || '')}</p>
      </div>
      <table class="darwin-table">
        <thead><tr><th>Driver</th><th>Role</th></tr></thead>
        <tbody>${(ex.drivers || []).map(dr => `<tr><td>${escapeHtml(dr.factor)}</td><td>${escapeHtml(dr.role)}</td></tr>`).join('')}</tbody>
      </table>
      <h3 style="margin-top:14px">What would change our mind (Popper)</h3>
      <ul class="dev-list">${(ex.popper_falsifiers || []).slice(0, 6).map(f => `<li><div class="dev-label">${escapeHtml(f)}</div></li>`).join('')}</ul>
    </div>`;
  }

  function renderPerfTable(viz, escapeHtml) {
    const methods = viz?.methods || {};
    const rows = Object.keys(methods).filter(k => !methods[k].error).sort();
    return `
    <div class="detail-section">
      <h3>Performance by method (in-sample sim)</h3>
      <table class="darwin-table">
        <thead><tr><th>Method</th><th>Cum ret</th><th>Ann vol</th><th>Max DD</th><th>Sharpe</th><th>Turnover</th></tr></thead>
        <tbody>${rows.map(k => {
          const s = methods[k].stats || {};
          const cum = s.cumulative_return != null ? (s.cumulative_return * 100).toFixed(1) + '%' : '—';
          const vol = s.volatility_annualized != null ? (s.volatility_annualized * 100).toFixed(1) + '%' : '—';
          const dd = s.max_drawdown_pct != null ? (s.max_drawdown_pct * 100).toFixed(1) + '%' : '—';
          return `<tr><td class="mono">${escapeHtml(DARWIN_METHOD_LABELS[k] || k)}</td><td class="mono">${cum}</td><td class="mono">${vol}</td><td class="mono">${dd}</td><td class="mono">${s.sharpe_annualized ?? '—'}</td><td class="mono">${s.avg_turnover_one_way != null ? (s.avg_turnover_one_way * 100).toFixed(1) + '%' : '—'}</td></tr>`;
        }).join('')}</tbody>
      </table>
    </div>`;
  }

  function renderChartsHtml() {
    return `
    <div class="darwin-charts split">
      <div class="chart-card">
        <h4>Cumulative return by method</h4>
        <div class="chart-wrap"><canvas id="darwin-equity-chart"></canvas></div>
      </div>
      <div class="chart-card">
        <h4>Holdings over time</h4>
        <div class="chart-toolbar">
          <label style="font-size:11px;color:var(--text-muted)">Method</label>
          <select id="darwin-method-select"></select>
        </div>
        <div class="chart-wrap"><canvas id="darwin-holdings-chart"></canvas></div>
      </div>
    </div>`;
  }

  function mountCharts(viz, defaultMethod) {
    if (!viz || typeof Chart === 'undefined') return;
    const methods = viz.methods || {};
    const keys = Object.keys(methods).filter(k => methods[k].dates?.length);
    if (!keys.length) return;

    const methodSel = document.getElementById('darwin-method-select');
    const holdingsCanvas = document.getElementById('darwin-holdings-chart');
    const equityCanvas = document.getElementById('darwin-equity-chart');
    if (!holdingsCanvas || !equityCanvas) return;

    function drawHoldings(methodKey) {
      const m = methods[methodKey];
      if (holdingsChart) { holdingsChart.destroy(); holdingsChart = null; }
      if (!m) return;
      const snaps = m.holdings_snapshots || [];
      if (!snaps.length) return;
      const labels = snaps.map(s => s.date);
      const tickers = [...new Set(snaps.flatMap(s => (s.weights || []).map(w => w.ticker)))];
      const datasets = tickers.map((t, i) => ({
        label: t,
        data: labels.map((_, li) => {
          const row = (snaps[li].weights || []).find(w => w.ticker === t);
          return row ? row.weight_pct : 0;
        }),
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
        stack: 'holdings',
      }));
      holdingsChart = new Chart(holdingsCanvas, {
        type: 'bar',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { color: '#8896ae', boxWidth: 10, font: { size: 10 } } } },
          scales: {
            x: { stacked: true, ticks: { color: '#8896ae', maxRotation: 45 }, grid: { color: '#1e2d46' } },
            y: { stacked: true, max: 100, ticks: { color: '#8896ae', callback: v => v + '%' }, grid: { color: '#1e2d46' } },
          },
        },
      });
    }

    const datasets = keys.map((k, i) => {
      const m = methods[k];
      const start = m.equity_index?.[0] || 1;
      return {
        label: DARWIN_METHOD_LABELS[k] || k,
        data: (m.equity_index || []).map(v => ((v / start) - 1) * 100),
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        backgroundColor: 'transparent',
        borderWidth: k === defaultMethod ? 2.5 : 1.5,
        pointRadius: 0,
        tension: 0.2,
      };
    });
    const longest = keys.reduce((a, k) => ((methods[k].dates || []).length > (methods[a].dates || []).length ? k : a), keys[0]);
    equityChart = new Chart(equityCanvas, {
      type: 'line',
      data: { labels: methods[longest].dates || [], datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { color: '#8896ae', boxWidth: 10, font: { size: 10 } } },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } },
        },
        scales: {
          x: { ticks: { color: '#8896ae', maxRotation: 45 }, grid: { color: '#1e2d46' } },
          y: { ticks: { color: '#8896ae', callback: v => v + '%' }, grid: { color: '#1e2d46' } },
        },
      },
    });

    if (methodSel) {
      methodSel.innerHTML = keys.filter(k => (methods[k].holdings_snapshots || []).length).map(k =>
        `<option value="${k}" ${k === defaultMethod ? 'selected' : ''}>${DARWIN_METHOD_LABELS[k] || k}</option>`
      ).join('');
      methodSel.onchange = () => drawHoldings(methodSel.value);
    }
    drawHoldings(methodSel?.value || defaultMethod || keys[0]);
  }

  global.DarwinViz = {
    destroyCharts,
    renderExplanation,
    renderPerfTable,
    renderChartsHtml,
    mountCharts,
  };
})(window);
