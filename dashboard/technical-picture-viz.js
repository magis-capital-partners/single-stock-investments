(function (global) {
  'use strict';

  const base = global.TechnicalViz || {};

  function finite(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function whole(value) {
    const number = finite(value);
    return number == null ? '—' : Math.round(number);
  }

  function pct(value, digits) {
    const number = finite(value);
    if (number == null) return '—';
    return `${number > 0 ? '+' : ''}${number.toFixed(digits == null ? 1 : digits)}%`;
  }

  function compact(value) {
    const number = finite(value);
    if (number == null) return '—';
    if (Math.abs(number) >= 1e9) return `${(number / 1e9).toFixed(2)}B`;
    if (Math.abs(number) >= 1e6) return `${(number / 1e6).toFixed(1)}M`;
    if (Math.abs(number) >= 1e3) return `${(number / 1e3).toFixed(1)}K`;
    return Math.round(number).toLocaleString();
  }

  // v3 phases are descriptive. Market-driven selloffs have held up better than
  // company-specific ones; in large caps, stock-specific panics in a calm market
  // kept underperforming. Retired v2 phases keep a neutral tone for preserved snapshots.
  function tone(value) {
    return {
      company_selloff: 'picture-negative',
      market_selloff: 'picture-warning',
      lagging_downtrend: 'picture-negative',
      distribution: 'picture-negative',
      deeply_oversold: 'picture-warning',
      oversold: 'picture-warning',
      trend_intact: 'picture-positive',
      leading_uptrend: 'picture-positive',
      accumulation: 'picture-positive',
    }[String(value || '')] || 'picture-neutral';
  }

  // finite(null) is 0 (Number(null)); missing must stay missing, not read as zero
  function present(value) {
    return value === null || value === undefined || value === '' ? null : finite(value);
  }

  function pctText(value, digits, signed) {
    const number = present(value);
    if (number == null) return '—';
    const text = `${(number * 100).toFixed(digits == null ? 1 : digits)}%`;
    return signed && number > 0 ? `+${text}` : text;
  }

  const RISK_BAND_LABEL = { low: 'Low', normal: 'Normal', elevated: 'Elevated', high: 'High' };

  function outlookStrip(technicals, escapeHtml) {
    const outlook = technicals.outlook || {};
    const risk = outlook.risk || null;
    const rebound = outlook.rebound || null;
    const context = technicals.context || {};
    if (!risk && !rebound) return '';
    const beta = present(context.beta_252d);
    const mkt = present(context.market_move_20d_pct);
    const co = present(context.company_move_20d_pct);
    const moveRead = mkt == null || co == null
      ? 'Market/company split pending'
      : `20-day move: ${mkt > 0 ? '+' : ''}${mkt.toFixed(1)}% market · ${co > 0 ? '+' : ''}${co.toFixed(1)}% company`;
    return `<section class="technical-outlook" aria-label="Calibrated outlook">
      <div><span>Drop risk · 63 sessions</span>
        <strong>${risk ? escapeHtml(pctText(risk.p_drop15_63d, 0)) : '—'}${risk ? ` <small style="display:inline">${escapeHtml(RISK_BAND_LABEL[risk.band] || '')}</small>` : ''}</strong>
        <small>Chance of falling another 15% within three months. Calibrated on 1990–2017; holdout AUC 0.66 vs 0.52 for panic alone.</small></div>
      <div><span>Expected volatility · next month</span>
        <strong>${risk && present(risk.expected_vol_21d_pct) != null ? `${escapeHtml(present(risk.expected_vol_21d_pct).toFixed(0))}%` : '—'}</strong>
        <small>${escapeHtml(moveRead)}${beta == null ? '' : ` · beta ${escapeHtml(beta.toFixed(2))}`}</small></div>
      <div><span>Risk-adjusted rank · US stocks</span>
        <strong>${rebound && present(rebound.score) != null ? `${escapeHtml(Math.round(present(rebound.score)).toString())}<small style="display:inline"> / 100</small>` : '—'}</strong>
        <small>${rebound ? 'Expected next-month return after removing the stock’s market (beta) part. Holdout 2018–26: top tenth beat bottom tenth ~1.4%/month on that basis, before ~1.2% costs. Leans to lower-beta names; it does not predict beating SPY in a rising market.' : 'US stocks with three years of history only.'}</small></div>
    </section>`;
  }

  const PHASE_RECORD_LABEL = {
    company_selloff: 'company-specific selloffs', market_selloff: 'market-driven selloffs', trend_intact: 'intact uptrends',
    oversold_watch: 'oversold readings', indeterminate: 'no decisive setup',
  };
  const VERDICT_TEXT = {
    positive: 'In this stock’s own history, high fear has reliably preceded outperformance.',
    negative: 'In this stock’s own history, high fear has reliably preceded further underperformance.',
    none: 'In this stock’s own history, the fear score has had no reliable link to what came next.',
    too_short: 'This stock’s history is too short to judge the fear score on its own.',
  };

  function trackRecordLine(ticker, technicals, trackRecord, escapeHtml) {
    if (!trackRecord) return '';
    const phase = String((technicals.setup || {}).phase || '');
    const full = trackRecord.backtest?.full_1990_2026?.stock_phase?.[phase];
    const hold = trackRecord.backtest?.holdout_2018_2026?.stock_phase?.[phase];
    const live = trackRecord.live?.stock_phase?.[phase];
    const base = trackRecord.backtest?.full_1990_2026?.all?.all;
    const mine = trackRecord.by_ticker?.[String(ticker.ticker || '').toUpperCase()];
    const parts = [];
    if (full && full.h63) {
      parts.push(`Since 1990, US stocks in <b>${escapeHtml(PHASE_RECORD_LABEL[phase] || phase.replace(/_/g, ' '))}</b> returned ${escapeHtml(pctText(full.h63.mean_excess, 1, true))} vs SPY over the next 63 sessions (all stock-days ${escapeHtml(pctText(base?.h63?.mean_excess, 1, true))}), beat SPY ${escapeHtml(pctText(full.h63.hit, 0))} of the time, and ${escapeHtml(pctText(full.p_drop15_63d, 0))} fell another 15%.`);
      if (hold && hold.h63) parts.push(`2018–2026: ${escapeHtml(pctText(hold.h63.mean_excess, 1, true))} vs SPY.`);
    }
    const graded = present(live?.h63?.graded) || 0;
    parts.push(graded
      ? `Live since ${escapeHtml(trackRecord.tracking?.live_since || '—')}: ${escapeHtml(pctText(live.h63.mean_excess, 1, true))} vs SPY on ${escapeHtml(String(graded))} graded signals.`
      : `Live tracking since ${escapeHtml(trackRecord.tracking?.live_since || 'its first run')}; 63-session outcomes are graded as they mature.`);
    if (mine) parts.push(escapeHtml(VERDICT_TEXT[mine.verdict] || ''));
    return `<p class="technical-record"><b>Track record.</b> ${parts.join(' ')}</p>`;
  }

  function priceChart(history, escapeHtml) {
    const points = (history || [])
      .map((row) => [String(row[0] || ''), finite(row[1])])
      .filter((row) => row[0] && row[1] != null);
    if (points.length < 2) {
      return '<div class="technical-chart-empty">Price history will appear after the nightly refresh.</div>';
    }
    const width = 620;
    const height = 102;
    const values = points.map((row) => row[1]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    const path = points.map((row, index) => {
      const x = index / (points.length - 1) * width;
      const y = height - (row[1] - low) / span * (height - 14) - 7;
      return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const change = values[0] > 0 ? (values[values.length - 1] / values[0] - 1) * 100 : null;
    return `<figure class="technical-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="One-year adjusted price history">
        <title>Adjusted close from ${escapeHtml(points[0][0])} to ${escapeHtml(points[points.length - 1][0])}</title>
        <path class="technical-chart-baseline" d="M0,${height - 8} L${width},${height - 8}"></path>
        <path class="technical-chart-line" d="${path}"></path>
      </svg>
      <figcaption><span>${escapeHtml(points[0][0])}</span><strong>${pct(change)}</strong><span>${escapeHtml(points[points.length - 1][0])}</span></figcaption>
    </figure>`;
  }

  function shortChart(structure, escapeHtml) {
    const points = (structure.history || [])
      .map((row) => {
        const value = finite(row.short_percent_float);
        return [String(row.date || ''), value == null ? null : value * 100];
      })
      .filter((row) => row[0] && row[1] != null);
    if (points.length < 2) {
      return '<p class="market-structure-empty">History starts with each reported short-interest refresh.</p>';
    }
    const width = 330;
    const height = 48;
    const values = points.map((row) => row[1]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    const path = points.map((row, index) => {
      const x = index / (points.length - 1) * width;
      const y = height - (row[1] - low) / span * (height - 12) - 6;
      return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<figure class="short-history-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Reported short interest as a percentage of float over time">
        <title>Reported short interest from ${escapeHtml(points[0][0])} to ${escapeHtml(points[points.length - 1][0])}</title>
        <path d="${path}"></path>
      </svg>
      <figcaption><span>${escapeHtml(points[0][0])}</span><strong>${values[values.length - 1].toFixed(1)}% of float</strong><span>${escapeHtml(points[points.length - 1][0])}</span></figcaption>
    </figure>`;
  }

  function valuationRead(ticker) {
    const decision = ticker.valuation_decision || {};
    const values = decision.value_per_share || ticker.component_valuation?.total_equity_value_per_share || {};
    const price = finite(decision.price_per_share ?? ticker.component_valuation?.market_price_per_share);
    const low = finite(values.low);
    const valueBase = finite(values.base);
    const high = finite(values.high);
    if (price == null || (valueBase == null && high == null)) {
      return { label: 'Valuation incomplete', detail: decision.status || 'No usable value range', tone: 'picture-neutral' };
    }
    if (high != null && high > 0 && price > high) {
      return { label: 'Above modeled range', detail: `${pct((high / price - 1) * 100)} to high case`, tone: 'picture-negative' };
    }
    if (valueBase != null && valueBase > 0 && price < valueBase) {
      return { label: 'Below base value', detail: `${pct((valueBase / price - 1) * 100)} to base`, tone: 'picture-positive' };
    }
    if (low != null && low > 0 && price < low) {
      return { label: 'Below modeled range', detail: 'Price is below the low case', tone: 'picture-positive' };
    }
    return { label: 'Inside modeled range', detail: decision.status || 'Valuation available', tone: 'picture-neutral' };
  }

  function businessRead(ticker) {
    const momentum = ticker.kpi_trends?.business_momentum || {};
    const leadership = ticker.kpi_trends?.leadership_risk || {};
    const latest = ticker.essential_insights?.latest || {};
    const direction = String(momentum.direction || '');
    return {
      label: momentum.label || 'Business trend not scored',
      detail: leadership.label || latest.title || 'No fresh material insight',
      tone: direction === 'accelerating'
        ? 'picture-positive'
        : direction === 'decelerating'
          ? 'picture-warning'
          : 'picture-neutral',
    };
  }

  function macroRead(marketContext) {
    const internal = marketContext?.internal || {};
    const panic = finite(internal.scores?.panic);
    const state = String(internal.state || 'pending').replace(/_/g, ' ');
    return {
      label: internal.state ? `Market ${state}` : 'Macro refresh pending',
      detail: panic == null ? 'Waiting for the latest SPY benchmark calculation' : `SPY panic ${Math.round(panic)}/100`,
      tone: panic != null && panic >= 70 ? 'picture-warning' : 'picture-neutral',
    };
  }

  // v3 copy follows the study: the tape describes risk and context, not timing.
  // Market-driven selloffs have held up better than company-specific ones (but
  // with higher volatility); company-specific ones have been no better than
  // average, and in large caps with a calm market they kept underperforming.
  function synthesis(setup, valuation, business, macro) {
    if (valuation.tone === 'picture-negative' && setup.phase === 'company_selloff') {
      return 'Fear is not margin of safety here: price remains above modeled value during a company-specific selloff. Those have done no better than average afterwards, and in large caps with a calm market they kept underperforming. Reconcile valuation inputs before acting.';
    }
    if (valuation.tone === 'picture-positive' && setup.phase === 'market_selloff') {
      return 'Fundamental discount during a market-driven selloff. Historically these have held up better than company-specific drops, but expect high volatility. Define an entry range and keep evidence gates intact.';
    }
    if (valuation.tone === 'picture-positive' && setup.phase === 'company_selloff') {
      return 'The valuation gap is attractive, but the decline is company-specific. Those have done no better than average afterwards, and in large caps with a calm market they kept lagging. Establish what changed in the business before sequencing an entry.';
    }
    if (business.tone === 'picture-warning' && setup.participation === 'distribution') {
      return 'Fading business momentum and distribution reinforce one another. Elevate thesis review before treating oversold conditions as opportunity.';
    }
    if (macro.tone === 'picture-warning' && setup.direction === 'lagging_downtrend') {
      return 'Broad fear and stock-specific underperformance are both active. Separate macro beta from company-specific deterioration before acting.';
    }
    return 'Valuation, business evidence, tape, and macro are not strongly aligned. Keep the stance evidence-led and use the technical setup only for timing and risk.';
  }

  function investmentPicture(ticker, setup, marketContext, escapeHtml) {
    const valuation = valuationRead(ticker);
    const business = businessRead(ticker);
    const macro = macroRead(marketContext);
    const tape = {
      label: setup.phase_label || 'Setup calculation pending',
      detail: `${setup.direction_label || 'Direction not yet scored'} · ${setup.participation_label || 'participation not yet scored'}`,
      tone: tone(setup.phase),
    };
    const lanes = [
      ['Valuation', valuation],
      ['Business', business],
      ['Tape', tape],
      ['Macro', macro],
    ];
    return `<section class="investment-picture" aria-label="Integrated investment picture">
      <div class="investment-picture-head">
        <div><span>Decision picture</span><strong>What agrees, what conflicts</strong></div>
        <p>${escapeHtml(synthesis(setup, valuation, business, macro))}</p>
      </div>
      <div class="investment-picture-grid">
        ${lanes.map(([name, row]) => `<div class="picture-lane ${row.tone}">
          <span>${name}</span><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.detail)}</small>
        </div>`).join('')}
      </div>
    </section>`;
  }

  function setupPillar(name, label, detail, read, value) {
    return `<div class="setup-pillar ${tone(value)}">
      <span>${name}</span>
      <strong>${label}</strong>
      <small>${detail}</small>
      <p>${read}</p>
    </div>`;
  }

  function marketStructure(structure, ticker, escapeHtml) {
    if (!structure || (!structure.float_shares && !structure.short_interest_shares)) {
      const market = String(ticker.market || '').toUpperCase();
      const reason = market && market !== 'US'
        ? `The free provider does not consistently publish float and exchange-reported short interest for ${market} listings. Price technicals remain fully usable.`
        : 'The free provider has not returned a reported float or short-interest snapshot for this security. Price technicals remain fully usable.';
      return `<section class="market-structure">
        <div class="section-kicker">Crowding & liquidity</div>
        <p class="market-structure-empty">${escapeHtml(reason)}</p>
      </section>`;
    }
    const shortFloat = finite(structure.short_percent_float);
    const crowdLabel = shortFloat == null
      ? 'Short percentage not reported'
      : shortFloat >= 20
        ? 'Heavily shorted'
        : shortFloat >= 10
          ? 'Elevated short interest'
          : 'Light short interest';
    const crowdTone = shortFloat != null && shortFloat >= 20
      ? 'picture-warning'
      : 'picture-neutral';
    return `<section class="market-structure ${crowdTone}">
      <div class="market-structure-head">
        <div><span>Crowding & liquidity</span><strong>${crowdLabel}</strong></div>
        <span class="market-structure-date">${structure.as_of ? `Reported ${escapeHtml(structure.as_of)}` : 'Reporting date not supplied'}</span>
      </div>
      <div class="market-structure-grid">
        <div><span>Float</span><strong>${compact(structure.float_shares)}</strong><small>${pct(structure.float_percent_outstanding)} of shares outstanding</small></div>
        <div><span>Shares short</span><strong>${compact(structure.short_interest_shares)}</strong><small>${shortFloat == null ? '—' : shortFloat.toFixed(1) + '%'} of float</small></div>
        <div><span>Change</span><strong>${pct(structure.short_change_pct)}</strong><small>versus prior report</small></div>
        <div><span>Days to cover</span><strong>${finite(structure.days_to_cover) == null ? '—' : finite(structure.days_to_cover).toFixed(1)}</strong><small>reported short ratio</small></div>
        <div class="market-structure-history">${shortChart(structure, escapeHtml)}</div>
      </div>
      <p class="market-structure-note">Reported short interest is a twice-monthly position snapshot. It is not FINRA daily short-sale volume.</p>
    </section>`;
  }

  function fearRail(label, value) {
    const number = finite(value);
    const width = number == null ? 0 : Math.max(0, Math.min(100, number));
    return `<div class="fear-rail">
      <div class="fear-rail-head"><span>${label}</span><strong>${whole(number)}</strong></div>
      <div class="fear-rail-track" aria-label="${label}: ${whole(number)} out of 100"><span style="width:${width}%"></span></div>
    </div>`;
  }

  function confirmations(values) {
    const rows = [
      ['Positive session', values.positive_session],
      ['Closed in upper half', values.closed_upper_half],
      ['Reclaimed prior high', values.reclaimed_prior_high],
      ['Volume cooled after climax', values.volume_cooled],
    ];
    return rows.map(([label, passed]) =>
      `<li class="${passed ? 'confirmation-pass' : 'confirmation-wait'}"><span aria-hidden="true">${passed ? '✓' : '○'}</span>${label}</li>`
    ).join('');
  }

  function renderPanel(ticker, helpers) {
    const escapeHtml = helpers.escapeHtml;
    const marketContext = helpers.marketContext || {};
    const technicals = ticker.technicals;
    if (!technicals) {
      return `<details class="detail-section technical-panel">
        <summary>Stock setup · awaiting first refresh</summary>
        <p class="tier-sub" style="margin-top:9px">The free-price job has not produced a snapshot for this security yet.</p>
      </details>`;
    }
    const setup = technicals.setup || {};
    const indicators = setup.indicators || {};
    const capitulation = technicals.capitulation || {};
    const scores = capitulation.scores || {};
    const families = capitulation.families || {};
    const measures = technicals.measures || {};
    const fear = base.fearMeta ? base.fearMeta(capitulation.state) : { label: capitulation.state || 'not yet scored', cls: 'fear-normal', marker: '·' };
    const directionRead = `${pct(indicators.price_vs_50d_pct)} vs 50d · ${pct(indicators.price_vs_200d_pct)} vs 200d · ${pct(measures.relative_return_60d_pct)} vs SPY`;
    const pressureRead = `RSI ${finite(indicators.rsi_14) == null ? '—' : finite(indicators.rsi_14).toFixed(0)} · panic ${whole(scores.panic)}/100 · exhaustion ${whole(scores.exhaustion)}/100`;
    const participationRead = `CMF ${finite(indicators.chaikin_money_flow_20d) == null ? '—' : finite(indicators.chaikin_money_flow_20d).toFixed(2)} · volume ${finite(indicators.relative_volume_20d) == null ? '—' : finite(indicators.relative_volume_20d).toFixed(1) + '×'} normal · ATR ${pct(indicators.atr_20d_pct)}`;
    return `<details class="detail-section technical-panel" open>
      <summary>Stock setup · <span class="${fear.cls}">${escapeHtml(setup.phase_label || fear.label)}</span></summary>
      <div class="technical-panel-body">
        ${investmentPicture(ticker, setup, marketContext, escapeHtml)}
        ${outlookStrip(technicals, escapeHtml)}
        ${trackRecordLine(ticker, technicals, helpers.trackRecord || null, escapeHtml)}
        <section class="stock-setup">
          <div class="stock-setup-head ${fear.cls}">
            <div><span aria-hidden="true">${fear.marker}</span><strong>${escapeHtml(setup.phase_label || fear.label)}</strong></div>
            <p>${escapeHtml(capitulation.interpretation || technicals.regime?.interpretation || 'No unusual technical condition')}</p>
            <span class="setup-confidence">${escapeHtml(technicals.data_grade || '—')} grade · ${whole(scores.confidence)}% coverage</span>
          </div>
          <div class="stock-setup-grid">
            ${setupPillar('Direction', escapeHtml(setup.direction_label || 'Not yet scored'), escapeHtml(setup.explainers?.direction || ''), directionRead, setup.direction)}
            ${setupPillar('Pressure', escapeHtml(setup.pressure_label || 'Not yet scored'), escapeHtml(setup.explainers?.pressure || ''), pressureRead, setup.pressure)}
            ${setupPillar('Participation', escapeHtml(setup.participation_label || 'Not yet scored'), escapeHtml(setup.explainers?.participation || ''), participationRead, setup.participation)}
          </div>
        </section>
        ${marketStructure(technicals.market_structure, ticker, escapeHtml)}
        ${priceChart(technicals.history, escapeHtml)}
        <details class="technical-diagnostics">
          <summary>Why the model says ${escapeHtml(fear.label)} · detailed diagnostics</summary>
          <div class="fear-monitor-grid">
            <div class="fear-family-rails">
              ${fearRail('Price dislocation', families.price_dislocation)}
              ${fearRail('Selling climax', families.selling_climax)}
              ${fearRail('Volatility stress', families.volatility_stress)}
              ${fearRail('Relative / path stress', families.relative_path_stress)}
            </div>
            <div class="fear-confirmation">
              <span class="fear-section-label">What would confirm exhaustion</span>
              <ul>${confirmations(capitulation.confirmation || {})}</ul>
              <p>Extreme fear is not a bottom. Confirmation requires stabilization after climactic selling.</p>
            </div>
          </div>
          <div class="technical-metric-grid">
            <div class="technical-metric"><span>20-day return</span><strong>${pct(measures.return_20d_pct)}</strong></div>
            <div class="technical-metric"><span>60-day vs SPY</span><strong>${pct(measures.relative_return_60d_pct)}</strong></div>
            <div class="technical-metric"><span>1-year drawdown</span><strong>${pct(measures.drawdown_1y_pct)}</strong></div>
            <div class="technical-metric"><span>Realized volatility</span><strong>${pct(measures.realized_volatility_20d_pct)}</strong></div>
            <div class="technical-metric"><span>Pressure</span><strong>${whole(scores.pressure)}/100</strong></div>
            <div class="technical-metric"><span>Exhaustion</span><strong>${whole(scores.exhaustion)}/100</strong></div>
          </div>
        </details>
        <div class="technical-foot">
          <span>${escapeHtml(technicals.data_grade_reason || 'Data grade will be assigned by the current technical refresh')}</span>
          <span class="mono">${escapeHtml(technicals.as_of || '—')} · ${escapeHtml(technicals.source || 'source pending')} · benchmark ${escapeHtml(technicals.benchmark || '—')}</span>
        </div>
        <div class="technical-references">
          <span>Method references:</span>
          <a href="https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators" target="_blank" rel="noopener">StockCharts indicators</a>
          <a href="https://www.finra.org/investors/insights/short-interest" target="_blank" rel="noopener">FINRA short interest</a>
        </div>
        <p class="technical-policy">Timing and risk overlay only. It cannot upgrade valuation readiness, clear evidence blockers, or change stance automatically.</p>
      </div>
    </details>`;
  }

  global.TechnicalViz = Object.assign({}, base, {
    renderPanel,
  });
})(typeof window !== 'undefined' ? window : globalThis);
