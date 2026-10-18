/* Held-by panel. 13F context only. It does not feed the base return. */
(function () {
  let summary = null;
  let summaryPromise = null;

  function dataUrl(path) {
    const base = window.location.pathname.replace(/\/index\.html$/i, "").replace(/\/$/, "");
    return `${base}/${path}`;
  }

  function ensureSummary() {
    if (summary) return Promise.resolve(summary);
    if (!summaryPromise) {
      summaryPromise = fetch(dataUrl("data/fund_holdings_summary.json"))
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
          summary = payload;
          return payload;
        })
        .catch(() => null);
    }
    return summaryPromise;
  }

  function badgeHtml(ticker) {
    const row = summary && summary.tickers && summary.tickers[ticker];
    if (!row || !row.holder_count) return "";
    const mark = row.net === "add" ? "▲" : row.net === "trim" ? "▼" : "";
    const title = "Tracked 13F holders. Context only. Not an input to the base return.";
    return ` <span class="badge" title="${title}">H:${row.holder_count}${mark}</span>`;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));
  }

  function secLink(url) {
    if (!/^https:\/\/(www\.)?sec\.gov\//.test(url || "")) return "";
    return ` · <a href="${escapeHtml(url)}" target="_blank" rel="noopener">SEC filing</a>`;
  }

  function money(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    if (Math.abs(number) >= 1e9) return `$${(number / 1e9).toFixed(1)}b`;
    if (Math.abs(number) >= 1e6) return `$${(number / 1e6).toFixed(1)}m`;
    return `$${Math.round(number).toLocaleString("en-US")}`;
  }

  function shares(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    return number.toLocaleString("en-US");
  }

  function renderTicker(ticker, escapeHtml) {
    const safe = escapeHtml(ticker);
    return `<details class="detail-section" id="held-by" data-ticker="${safe}"><summary>Held by</summary><div class="held-by-body" style="margin-top:10px">Loading 13F holders…</div></details>`;
  }

  function fillTicker(ticker) {
    const slot = document.querySelector("#held-by .held-by-body");
    const root = document.getElementById("held-by");
    if (!slot || !root || root.dataset.ticker !== ticker) return;
    fetch(dataUrl(`data/holdings/by_ticker/${encodeURIComponent(ticker)}.json`))
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (root.dataset.ticker !== ticker) return;
        if (!payload || !(payload.holders || []).length) {
          slot.textContent = "No tracked manager reported this stock in the latest 13F books on file.";
          return;
        }
        const lines = payload.holders.slice(0, 25).map((holder) => {
          const change = holder.change_type ? ` · ${escapeHtml(holder.change_type)}` : "";
          const weight = holder.weight_pct != null ? ` · ${escapeHtml(holder.weight_pct)}% of book` : "";
          const when = holder.period_end ? ` · as of ${escapeHtml(holder.period_end)}` : "";
          const filed = holder.filed_at ? `, filed ${escapeHtml(holder.filed_at)}` : "";
          return `<div class="hr-line"><strong>${escapeHtml(holder.name)}</strong> · ${shares(holder.shares)} shares · ${money(holder.value_usd)}${weight}${change}${when}${filed}${secLink(holder.source_url)}</div>`;
        });
        const extra = payload.holders.length > 25 ? `<div class="tier-sub">${payload.holders.length - 25} more holders in the file.</div>` : "";
        slot.innerHTML = `<p class="tier-sub">${payload.context || ""}</p>${lines.join("")}${extra}`;
      })
      .catch(() => {
        if (root.dataset.ticker === ticker) slot.textContent = "13F holders could not be loaded.";
      });
  }

  ensureSummary();
  window.FundHoldings = { renderTicker, fillTicker, badgeHtml, ensureSummary };
})();
