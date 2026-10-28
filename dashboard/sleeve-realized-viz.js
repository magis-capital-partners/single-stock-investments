(function (global) {
  'use strict';
  const esc = value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  const money = value => value == null || value === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value));
  const amount = value => value == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 }).format(Number(value));
  const color = value => value == null || Number(value) === 0 ? '' : Number(value) > 0 ? 'sleeve-pnl-up' : 'sleeve-pnl-down';
  const settlementLabel = state => ({ pending: 'Pending', date_reached: 'Date reached', unknown: 'Unknown' }[state] || 'Unknown');
  const states = new Map();

  function shell() {
    return `<section class="sleeve-section sleeve-realized" data-sleeve-realized aria-label="Realized P&L and closed positions">
      <div class="sleeve-section-head"><h3>Realized P&amp;L / Closed positions</h3><span data-realized-through></span></div>
      <p class="realized-copy">One row per ticker. Click a ticker to see its separate closed lots and broker adjustments. Partial sales remain here while their remaining shares stay in Holdings.</p>
      <form class="realized-filters" data-realized-form>
        <label>Period<select name="period"><option value="ytd">Year to date</option><option value="previous">Previous year</option><option value="all">All available history</option><option value="custom">Custom dates</option></select></label>
        <label>From<input type="date" name="from" required></label><label>Through<input type="date" name="to" required></label>
        <label>Date basis<select name="basis"><option value="trade_date">Realization date</option><option value="settlement_date">Settlement target date</option></select></label>
        <label>Settlement<select name="settlement"><option value="all">All statuses</option><option value="date_reached">Date reached</option><option value="pending">Pending</option><option value="unknown">Unknown</option></select></label>
        <label>Ticker<input name="ticker" placeholder="All names" maxlength="100" aria-label="Exact underlying ticker"></label>
        <button type="submit">Apply</button><button type="button" data-realized-refresh>Refresh latest data</button><button type="button" data-realized-export>Export CSV</button>
      </form>
      <div data-realized-status role="status" aria-live="polite">Loading realized history…</div>
      <div data-realized-results></div>
    </section>`;
  }

  function rowHtml(row) {
    const allocation = row.confidence === 'legacy_inferred' ? 'Historical policy inference' : row.confidence === 'explicit_override' ? 'Documented ownership allocation' : 'Opening order evidence';
    const details = [
      ['Opening date', row.opening_date || 'Not supplied by broker'],
      ['Closed-lot match', row.lot_matched ? 'Broker matched' : 'Execution / booking record'],
      ['Native realized P&L', `${amount(row.realized_native)} ${row.currency}`],
      ['Reported basis', `${amount(row.cost_basis)} ${row.currency}`],
      ['FX to USD', row.fx_rate || 'Unavailable'],
      ['Ownership', `${allocation} · ${row.allocation_reason}`],
      ['Activity', row.record_kind === 'cancellation_adjustment' ? 'Broker accounting adjustment on a canceled/rebooked execution' : row.record_kind === 'reported_realization' ? 'Reported realization; opening/closing allocation not supplied' : row.notes?.join(', ') || row.event_type],
      ['Evidence', `Report ${row.report_id.slice(0, 12)} · ${row.record_id}`],
    ].map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('');
    return `<tr><td><details><summary><strong class="mono">${esc(row.contract_label)}</strong></summary>
      <dl class="realized-detail">${details}</dl></details><small>${esc(row.description || row.ticker)}${row.contract_held_now ? ' · Contract also held now' : ''}</small></td>
      <td class="mono">${esc(row.trade_date)}</td><td class="sleeve-num mono">${amount(row.quantity)}</td>
      <td class="mono">${esc(row.settlement_date || '—')}<small>${settlementLabel(row.settlement_status)}</small></td>
      <td class="sleeve-num mono ${color(row.realized_usd)}">${money(row.realized_usd)}${row.realized_usd == null ? '<small>USD amount unavailable</small>' : ''}</td></tr>`;
  }

  function renderResults(payload) {
    const summary = payload.summary;
    const coverage = payload.coverage || {};
    const warnings = [];
    if (payload.is_current === false) warnings.push('A newer data version is available. Refresh latest data to replace these results.');
    if (payload.ownership_mismatch) warnings.push('Positions and realized history are updating to the same ownership version. Compare them after the update completes.');
    if (summary.inferred_count) warnings.push(`${summary.inferred_count} records use historical ownership policy; expand a row to see its basis.`);
    if (summary.missing_usd) warnings.push(`${summary.missing_usd} records lack a USD amount and are excluded from the USD total.`);
    if (payload.unresolved?.count) warnings.push(`${payload.unresolved.count} account records (${money(payload.unresolved.realized_usd)}) have unresolved ownership and are excluded from both owner totals.`);
    if (!coverage.closed_lots_available) warnings.push('Closed Lots detail has not been received. Shared holdings require broker lot matches before ownership can be assigned.');
    if (coverage.gaps?.length) warnings.push(`${coverage.gaps.length} gaps exist in the available report coverage.`);
    if (coverage.observed_from && coverage.from && coverage.observed_from < coverage.from) warnings.push(`Broker restatements include activity dated back to ${coverage.observed_from}. Complete report coverage starts ${coverage.from}; earlier years are incomplete.`);
    if (payload.reconciliation?.unmatched_action_count) warnings.push(`${payload.reconciliation.unmatched_action_count} corporate or option actions lack a linked reported realization and require reconciliation.`);
    if (payload.reconciliation?.status === 'needs_review') warnings.push(`Account reconciliation needs review (${payload.reconciliation.difference_count || 0} differences; ${payload.reconciliation.exception_count || 0} exceptions). ${payload.reconciliation.owner_difference_counts?.[payload.owner] ?? 'Unknown'} differences involve this owner’s identified contracts. Results shown are reported amounts for the identified records.`);
    return `<div class="realized-totals"><div><span>Realized P&amp;L · selected period</span><strong class="mono ${color(summary.realized_usd)}">${money(summary.realized_usd)}</strong><small>${summary.count} records · commissions already included where reported by IBKR</small></div>
      <div><span>Available history</span><strong class="mono">${esc(coverage.from || '—')} → ${esc(coverage.through || '—')}</strong><small>Realized P&amp;L is separate from current unrealized gains and account cash.</small></div></div>
      ${warnings.length ? `<details class="realized-quality" open><summary>Coverage and accounting notes</summary>${warnings.map(w => `<p>${esc(w)}</p>`).join('')}</details>` : ''}
      <p class="realized-copy">“Date reached” means the broker’s settlement target is on or before the completed statement date. It is not confirmation of cash settlement. Unknown settlement dates are omitted when filtering by settlement target date.</p>
      ${payload.view === 'tickers' ? `<div class="sleeve-table-wrap"><table class="sleeve-table realized-table realized-tickers"><thead><tr><th>Ticker</th><th>Separate lots</th><th>Selected dates</th><th class="sleeve-num">Realized P&amp;L · USD</th></tr></thead><tbody data-realized-rows>${payload.groups.map(groupHtml).join('') || '<tr><td colspan="4">No realized activity matches this selection.</td></tr>'}</tbody></table></div>` : `<div class="sleeve-table-wrap">${lotsTable(payload.records, true)}</div>`}
      <button type="button" data-realized-more ${payload.next_cursor ? '' : 'hidden'}>Show more</button>`;
  }

  function lotsTable(rows, main = false) {
    return `<table class="sleeve-table realized-table"><thead><tr><th>Position / contract</th><th>Realization date</th><th class="sleeve-num">Quantity closed</th><th>Settlement target</th><th class="sleeve-num">Realized P&amp;L · USD</th></tr></thead><tbody ${main ? 'data-realized-rows' : ''}>${rows.map(rowHtml).join('') || '<tr><td colspan="5">No realized activity matches this selection.</td></tr>'}</tbody></table>`;
  }

  function groupHtml(group) {
    const key = encodeURIComponent(group.ticker), count = group.summary.count;
    return `<tr class="realized-ticker-row"><td><button type="button" class="realized-ticker" data-realized-ticker="${esc(key)}" aria-expanded="false" aria-controls="realized-lots-${esc(key)}" ${group.ticker ? '' : 'disabled'}><span aria-hidden="true">▸</span> <strong class="mono">${esc(group.ticker || 'Unidentified')}</strong></button></td><td>${count} lot${count === 1 ? '' : 's'}<small>Includes broker adjustments</small></td><td class="mono">${esc(group.from)}${group.from === group.through ? '' : ` → ${esc(group.through)}`}</td><td class="sleeve-num mono ${color(group.summary.realized_usd)}">${money(group.summary.realized_usd)}${group.summary.missing_usd ? `<small>${group.summary.missing_usd} USD amounts unavailable</small>` : ''}</td></tr><tr class="realized-lots-row" id="realized-lots-${esc(key)}" data-realized-lots="${esc(key)}" hidden><td colspan="4"><div data-realized-lot-content></div></td></tr>`;
  }

  async function request(owner, params, signal) {
    const query = new URLSearchParams({ owner, ...params });
    const response = await fetch(`/api/v1/sleeves/realized?${query}`, { credentials: 'same-origin', cache: 'no-store', signal });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Realized history could not be loaded.');
    return payload;
  }

  function csvCell(value) {
    let text = String(value ?? '');
    if (/^[=+@\t\r]/.test(text) || /^-[^\d]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  }

  function csv(rows) {
    const fields = ['ticker', 'contract_label', 'record_kind', 'trade_date', 'opening_date', 'quantity', 'settlement_date', 'settlement_status', 'currency', 'realized_native', 'fx_rate', 'realized_usd', 'confidence', 'allocation_reason', 'record_id', 'report_id', 'ownership_version'];
    return [fields.join(','), ...rows.map(row => fields.map(k => csvCell(row[k])).join(','))].join('\r\n');
  }

  async function attach(container, owner, ownershipVersion = null) {
    const root = container.querySelector('[data-sleeve-realized]');
    if (!root || root.dataset.attached) return;
    root.dataset.attached = 'true';
    const form = root.querySelector('[data-realized-form]'), status = root.querySelector('[data-realized-status]'), results = root.querySelector('[data-realized-results]');
    let payload, params = states.get(owner) || {}, controller;
    const lotPages = new Map();
    const field = key => form.elements.namedItem(key);

    function periodDates(period) {
      if (!payload) return;
      const year = Number(payload.through.slice(0, 4));
      if (period === 'ytd') { field('from').value = `${year}-01-01`; field('to').value = payload.through; }
      if (period === 'previous') { field('from').value = `${year - 1}-01-01`; field('to').value = `${year - 1}-12-31`; }
      if (period === 'all') { field('from').value = payload.coverage.observed_from || payload.coverage.from; field('to').value = payload.through; }
    }

    async function load(next = false) {
      controller?.abort(); controller = new AbortController();
      const requestController = controller;
      if (!next) {
        for (const entry of lotPages.values()) entry.controller?.abort();
        lotPages.clear(); payload = null; results.innerHTML = '';
      }
      status.textContent = next ? 'Loading more records…' : 'Loading realized history…';
      try {
        const selected = next ? { ...params, view: 'tickers', generation: payload.generation_id, cursor: payload.next_cursor } : { ...params, view: 'tickers' };
        const nextPayload = await request(owner, selected, requestController.signal);
        nextPayload.ownership_mismatch = Boolean(ownershipVersion && nextPayload.ownership_version !== ownershipVersion);
        if (!root.isConnected || controller !== requestController) return;
        if (next && nextPayload.is_current === false) { await load(); return; }
        if (nextPayload.status !== 'available') {
          status.textContent = 'Realized history has not been published yet. Current holdings remain available.';
          results.innerHTML = ''; return;
        }
        if (next) {
          root.querySelector('[data-realized-rows]').insertAdjacentHTML('beforeend', nextPayload.view === 'tickers' ? nextPayload.groups.map(groupHtml).join('') : nextPayload.records.map(rowHtml).join(''));
          payload = { ...nextPayload, records: [...payload.records, ...nextPayload.records], groups: [...(payload.groups || []), ...(nextPayload.groups || [])] };
          root.querySelector('[data-realized-more]').hidden = !payload.next_cursor;
        } else {
          payload = nextPayload; results.innerHTML = renderResults(payload);
          for (const key of ['from', 'to', 'basis', 'settlement', 'ticker']) field(key).value = payload[key] || '';
          root.querySelector('[data-realized-more]')?.addEventListener('click', () => load(true));
        }
        const updated = payload.published_at && new Date(payload.published_at.includes('T') ? payload.published_at : payload.published_at.replace(' ', 'T') + 'Z');
        root.querySelector('[data-realized-through]').textContent = `Statement through ${payload.through}${updated && !Number.isNaN(updated.getTime()) ? ` · Updated ${updated.toLocaleString()}` : ''}`;
        status.textContent = payload.view === 'tickers' ? `${payload.groups.length} of ${payload.group_count} tickers · ${payload.summary.count} lots and adjustments. Click a ticker to see its lots.` : `${payload.records.length} of ${payload.summary.count} records shown.`;
      } catch (error) {
        if (error.name !== 'AbortError' && root.isConnected && controller === requestController) status.textContent = error.message;
      }
    }

    async function loadLots(key, next = false) {
      if (!payload) return;
      const row = root.querySelector(`[data-realized-lots="${key}"]`), button = root.querySelector(`[data-realized-ticker="${key}"]`);
      if (!row || !button) return;
      if (!next && !row.hidden) { row.hidden = true; button.setAttribute('aria-expanded', 'false'); return; }
      row.hidden = false; button.setAttribute('aria-expanded', 'true');
      const body = row.querySelector('[data-realized-lot-content]');
      let entry = lotPages.get(key);
      if (entry?.loading || (!next && entry?.records)) return;
      entry = entry || { records: null }; lotPages.set(key, entry);
      entry.loading = true; entry.controller = new AbortController();
      const generation = payload.generation_id;
      body.innerHTML = '<p class="realized-copy" role="status">Loading separate lots…</p>';
      try {
        const selection = { from: payload.from, to: payload.to, basis: payload.basis, settlement: payload.settlement,
          ticker: decodeURIComponent(key), view: 'lots', generation, limit: '50', ...(next ? { cursor: entry.next_cursor } : {}) };
        const part = await request(owner, selection, entry.controller.signal);
        if (!root.isConnected || payload?.generation_id !== generation) return;
        if (part.is_current === false) { await load(); return; }
        entry.records = [...(next ? entry.records || [] : []), ...part.records]; entry.next_cursor = part.next_cursor;
        body.innerHTML = `<div class="realized-lot-heading"><strong>${esc(part.ticker)} · separate lots</strong><span>${entry.records.length} of ${part.summary.count} shown</span></div>${lotsTable(entry.records)}${part.next_cursor ? `<button type="button" data-realized-lots-more="${esc(key)}">Show more lots</button>` : ''}`;
      } catch (error) {
        if (error.name !== 'AbortError' && root.isConnected) body.innerHTML = `<p role="status">${esc(error.message)}</p><button type="button" data-realized-lots-retry="${esc(key)}">Retry lots</button>`;
      } finally { entry.loading = false; }
    }
    results.addEventListener('click', event => {
      const tickerButton = event.target.closest?.('[data-realized-ticker]');
      const more = event.target.closest?.('[data-realized-lots-more]');
      const retry = event.target.closest?.('[data-realized-lots-retry]');
      if (tickerButton) loadLots(tickerButton.dataset.realizedTicker);
      else if (more) loadLots(more.dataset.realizedLotsMore, true);
      else if (retry) {
        const key = retry.dataset.realizedLotsRetry;
        lotPages.delete(key);
        root.querySelector(`[data-realized-lots="${key}"]`).hidden = true;
        loadLots(key);
      }
    });
    root.querySelector('[data-realized-refresh]')?.addEventListener('click', () => {
      params = { ...params }; delete params.generation; delete params.cursor;
      load();
    });
    form.addEventListener('submit', event => {
      event.preventDefault();
      params = Object.fromEntries(['from', 'to', 'basis', 'settlement', 'ticker'].map(k => [k, field(k).value]));
      states.set(owner, params); load();
    });
    field('period').addEventListener('change', () => periodDates(field('period').value));
    for (const key of ['from', 'to']) field(key).addEventListener('input', () => { field('period').value = 'custom'; });
    root.querySelector('[data-realized-export]').addEventListener('click', async event => {
      if (!payload) return;
      const button = event.currentTarget; button.disabled = true;
      try {
        const selected = { from: payload.from, to: payload.to, basis: payload.basis, settlement: payload.settlement, ticker: payload.ticker, view: 'lots', generation: payload.generation_id, limit: '100' };
        let part = await request(owner, selected), rows = [...part.records];
        if (part.is_current === false) { await load(); throw new Error('New history loaded. Export again to use the latest data.'); }
        while (part.next_cursor && rows.length < 100_000) {
          part = await request(owner, { ...selected, cursor: part.next_cursor }); rows.push(...part.records);
          if (part.is_current === false) { await load(); throw new Error('New history loaded. Export again to use the latest data.'); }
        }
        if (part.next_cursor) throw new Error('Export is too large. Select a shorter period.');
        const url = URL.createObjectURL(new Blob([csv(rows)], { type: 'text/csv;charset=utf-8' }));
        const link = document.createElement('a'); link.href = url; link.download = `${owner}-realized-${payload.from}-${payload.to}.csv`; link.click(); URL.revokeObjectURL(url);
        status.textContent = `Exported ${rows.length} records.`;
      } catch (error) { status.textContent = error.message; }
      finally { button.disabled = false; }
    });
    await load();
  }

  global.SleeveRealized = { shell, attach, renderResults, rowHtml, groupHtml, csv };
})(window);
