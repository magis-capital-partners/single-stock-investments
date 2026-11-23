(function (global) {
  "use strict";

  const feed = "/api/v2/portfolio/rs-execution";
  const controllers = new WeakMap();
  const price = new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 4});
  const dollars = new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", signDisplay: "exceptZero"});
  const dateTime = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric",
    minute: "2-digit", second: "2-digit", timeZoneName: "short",
  });
  const eventLabels = {
    order_submitting: "Intent recorded", order_working: "Acknowledged",
    order_filled: "Order complete", order_cancelled: "Cancel confirmed",
    order_rejected: "Rejected", order_uncertain: "Unconfirmed",
    cancel_requested: "Cancel requested", short_fill: "Short filled", cover_fill: "Cover filled",
  };
  const states = {submitting: "Submitting", working: "Working", filled: "Filled",
    cancelled: "Cancelled", rejected: "Rejected", uncertain: "Unconfirmed"};
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]
  ));
  const date = value => Number.isFinite(Date.parse(value)) ? dateTime.format(new Date(value)) : "—";
  const valueText = (formatter, value) => Number.isFinite(value) ? formatter.format(value) : "—";
  const tone = value => value > 0 ? "rse-positive" : value < 0 ? "rse-negative" : "";
  const terminal = new Set(["filled", "rejected", "cancelled"]);

  function render() {
    return `<section class="rse" data-rs-execution aria-label="Reverse-split paper execution">
      <div class="rse-toolbar">
        <div class="rse-connection"><span class="rse-dot" data-rse-dot></span><span data-rse-status role="status">Connecting to paper feed</span></div>
        <div class="rse-tools"><label>Paper session <select data-rse-session><option value="">Latest session</option></select></label>
          <button type="button" data-rse-refresh>Refresh</button></div>
      </div>
      <div data-rse-content aria-busy="true"><p class="rse-empty">Loading paper execution.</p></div>
    </section>`;
  }

  function table(title, headings, rows, empty) {
    return `<section class="rse-panel"><h3>${title}</h3><div class="rse-table" tabindex="0" role="region" aria-label="${title}">
      <table><thead><tr>${headings.map(heading => `<th scope="col">${heading}</th>`).join("")}</tr></thead>
      <tbody>${rows.length ? rows.join("") : `<tr><td colspan="${headings.length}" class="rse-empty">${empty}</td></tr>`}</tbody></table>
      </div></section>`;
  }

  function metric(title, value, note, style = "") {
    return `<div><dt>${title}</dt><dd class="${style}">${value}</dd><small>${note}</small></div>`;
  }

  function renderSnapshot(snapshot, stale) {
    const pnl = snapshot.pnl;
    const orders = [...snapshot.orders].reverse();
    const fills = [...snapshot.fills].reverse();
    const positions = snapshot.positions;
    const refOrders = new Map(orders.map(order => [order.ref, order]));
    const lastKnown = stale && !snapshot.ended;
    const marked = lastKnown ? null : pnl.marked_before_borrow;
    const metrics = `<dl class="rse-metrics">
      ${metric("Marked paper P&L", valueText(dollars, marked),
        lastKnown ? "Feed stale" : marked === null ? "A current cover mark is missing" : positions.some(row => row.mark?.source === "delayed_ask") ? "Delayed paper mark · before borrow" : "After recorded commissions · before borrow", tone(marked))}
      ${metric("Realized gross", valueText(dollars, pnl.realized_gross), "Completed share covers · before fees", tone(pnl.realized_gross))}
      ${metric("Shares short", positions.reduce((sum, row) => sum + row.shares_short, 0), positions.length + " open positions")}
      ${metric("Working orders", orders.filter(row => !terminal.has(row.state)).length, fills.length + " broker executions")}
    </dl>`;
    const events = [...snapshot.events].reverse().map(event => {
      const order = refOrders.get(event.ref);
      const label = event.kind === "order_working" && event.filled > 0
        ? "Partially filled" : eventLabels[event.kind] || String(event.kind ?? "").replaceAll("_", " ");
      const side = order?.side === "BUY" ? "Cover" : "Short";
      const quantity = Number.isSafeInteger(event.shares) ? `${event.shares} @ ${valueText(price, event.price)}`
        : event.filled ? `${event.filled} / ${order?.shares ?? "—"} filled` : "";
      return `<tr><td>${date(event.at)}</td><td><strong>${esc(event.ticker)}</strong></td>
        <td><span class="rse-event">${esc(label)}</span></td><td>${side}</td><td>${esc(quantity || "—")}</td>
        <td><code>${esc(event.ref)}</code></td></tr>`;
    });
    return metrics + `<p class="rse-note">${pnl.commission_final ? "Broker-reported commissions" : "Recorded commissions include estimates"}:
      ${valueText(price, pnl.commission)}. ${snapshot.kill_latched ? "Paper kill latch is set." : ""}</p>`
      + table("Open positions", ["Symbol", "Shares short", "Entry", "Cover mark", "Gross unrealized"],
        positions.map(row => {
          const current = row.mark_current && !lastKnown;
          const mark = row.mark;
          return `<tr><td><strong>${esc(row.ticker)}</strong></td><td>${esc(row.shares_short)}</td>
            <td>${valueText(price, row.entry_price)}</td>
            <td>${valueText(price, mark?.ask)}${mark ? `<small>${mark.source === "live_ask" ? "Live ask" : "Delayed paper ask"}
              · ${date(mark.at)}${current ? "" : " · stale"}</small>` : ""}</td>
            <td class="${tone(current ? row.unrealized_gross : null)}">${valueText(dollars, current ? row.unrealized_gross : null)}</td></tr>`;
        }), "No open short positions.")
      + table("Event timeline", ["Time (ET)", "Symbol", "Event", "Action", "Execution", "Order reference"],
        events, "No order events have arrived.")
      + table("Orders", ["Symbol", "Action", "Status", "Filled", "Limit", "Broker order", "Submitted (ET)"], orders.map(row => (
        `<tr><td><strong>${esc(row.ticker)}</strong></td><td>${row.side === "BUY" ? "Cover" : "Short"}</td>
          <td>${esc(states[row.state] || row.state)}</td><td>${esc(row.filled)} / ${esc(row.shares)}</td>
          <td>${valueText(price, row.limit_price)}</td><td>${esc(row.order_id ?? "—")}<small><code>${esc(row.ref)}</code></small></td>
          <td>${date(row.at)}</td></tr>`
      )), "No paper orders have arrived.")
      + table("Fills", ["Time (ET)", "Symbol", "Action", "Shares", "Price", "Commission", "Execution ID"], fills.map(row => (
        `<tr><td>${date(row.at)}</td><td><strong>${esc(row.ticker)}</strong></td><td>${row.side === "BUY" ? "Cover" : "Short"}</td>
          <td>${esc(row.shares)}</td><td>${valueText(price, row.price)}</td><td>${valueText(price, row.commission)}
            ${row.commission_source !== "broker" ? "<small>Estimate / unverified</small>" : ""}</td>
          <td><code>${esc(row.exec_id)}</code></td></tr>`
      )), "No broker-confirmed paper fills have arrived.");
  }

  function attach(host) {
    if (!host || controllers.has(host)) return;
    const select = host.querySelector("[data-rse-session]");
    const status = host.querySelector("[data-rse-status]");
    const dot = host.querySelector("[data-rse-dot]");
    const content = host.querySelector("[data-rse-content]");
    const button = host.querySelector("[data-rse-refresh]");
    let timer, abort, disposed = false, cached = null, drawn = "", sessionOptions = "";

    function setStatus(text, state) {
      if (status.textContent !== text) status.textContent = text;
      dot.dataset.state = state;
    }
    function paint(error) {
      const snapshot = cached?.snapshot;
      const stale = snapshot && Date.now() - Date.parse(snapshot.observed_at) > 20_000;
      if (error) setStatus(`${error}${snapshot ? " · showing last received session" : ""}`, "stale");
      else if (!snapshot) setStatus("Waiting for a paper session", "idle");
      else if (snapshot.ended) setStatus("Paper session ended · " + date(snapshot.observed_at), "idle");
      else if (stale) setStatus("Paper feed stale · " + date(snapshot.observed_at), "stale");
      else setStatus("Paper feed current · " + date(snapshot.observed_at), "current");

      const sessions = cached?.sessions || [];
      const options = sessions.map(row => `<option value="${esc(row.session_id)}">${date(row.observed_at)}
        ${row.ended ? "· ended" : ""} · ${esc(row.session_id.slice(-6))}</option>`).join("");
      if (sessionOptions !== options && select !== document.activeElement) {
        const selection = select.value;
        select.innerHTML = '<option value="">Latest session</option>' + options;
        select.value = [...select.options].some(option => option.value === selection) ? selection : "";
        sessionOptions = options;
      }
      const display = snapshot ? renderSnapshot(snapshot, Boolean(stale || error))
        : `<p class="rse-empty">${error ? "The paper feed is unavailable." : "Paper orders, fills, and P&L will appear when the supervised paper session publishes its journal."}</p>`;
      if (display !== drawn) {
        const scrollOffsets = [...content.querySelectorAll(".rse-table")].map(node => node.scrollLeft);
        content.innerHTML = display;
        content.querySelectorAll(".rse-table").forEach((node, index) => {node.scrollLeft = scrollOffsets[index] ?? 0;});
        drawn = display;
      }
      content.setAttribute("aria-busy", "false");
    }

    async function refresh() {
      clearTimeout(timer);
      abort?.abort();
      if (!host.isConnected) { dispose(host); return; }
      const panel = host.closest(".portfolio-panel");
      if (panel && !panel.classList.contains("active")) {
        timer = setTimeout(refresh, 2_000);
        return;
      }
      const request = new AbortController();
      abort = request;
      try {
        const query = select.value ? "?session=" + encodeURIComponent(select.value) : "";
        const response = await fetch(feed + query, {cache: "no-store", signal: request.signal});
        if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "SSI owner access required" : "Paper feed unavailable");
        const next = await response.json();
        if (next.mode !== "paper" || (next.snapshot && next.snapshot.mode !== "paper")) throw new Error("Unexpected paper feed response");
        if (disposed || abort !== request) return;
        cached = next;
        paint();
      } catch (error) {
        if (!disposed && abort === request && error.name !== "AbortError") paint(error.message);
      } finally {
        if (!disposed && abort === request) timer = setTimeout(refresh, document.hidden ? 15_000 : 2_000);
      }
    }
    button.addEventListener("click", refresh);
    select.addEventListener("change", refresh);
    controllers.set(host, () => { disposed = true; clearTimeout(timer); abort?.abort(); });
    refresh();
  }

  function dispose(container) {
    const host = container?.matches("[data-rs-execution]") ? container : container?.querySelector("[data-rs-execution]");
    controllers.get(host)?.();
    if (host) controllers.delete(host);
  }
  global.ReverseSplitExecutionViz = {render, attach, dispose};
})(window);
