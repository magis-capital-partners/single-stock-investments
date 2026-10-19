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

  function renderManagersPage() {
    return `<div id="managers-page"><p class="tier-sub">Loading 13F managers…</p></div>`;
  }

  function managerLine(row) {
    const weight = row.top_weight_pct != null ? `${escapeHtml(row.top_weight_pct)}% in ${escapeHtml(row.top_ticker || row.top_issuer || "")}` : "";
    return `<button type="button" class="hr-line" data-manager="${escapeHtml(row.manager_id)}" style="display:block;width:100%;text-align:left;background:none;border:0;padding:4px 0;cursor:pointer"><strong>${escapeHtml(row.name)}</strong> · ${escapeHtml(row.quarter || "")} · ${row.positions || 0} positions · ${row.ssi_overlap || 0} in this book${weight ? ` · top ${weight}` : ""}</button>`;
  }

  function fillManagersPage() {
    const root = document.getElementById("managers-page");
    if (!root) return;
    Promise.all([
      fetch(dataUrl("data/holdings/managers_index.json")).then((response) => (response.ok ? response.json() : null)),
      fetch(dataUrl("data/holdings/feed.json")).then((response) => (response.ok ? response.json() : null)),
    ]).then(([index, feed]) => {
      if (!document.getElementById("managers-page")) return;
      const managers = (index && index.managers) || [];
      const consensus = ((feed && feed.consensus) || []).slice(0, 20).map((row) =>
        `<div class="hr-line"><strong>${escapeHtml(row.ticker)}</strong> · ${(row.managers || []).slice(0, 8).map(escapeHtml).join(", ")}</div>`
      ).join("");
      const changes = ((feed && feed.changes) || []).slice(0, 40).map((row) =>
        `<div class="hr-line">${escapeHtml(row.name)} · ${escapeHtml(row.change_type)} ${escapeHtml(row.ticker)}${row.shares_delta_pct != null ? ` · ${escapeHtml(row.shares_delta_pct)}%` : ""}</div>`
      ).join("");
      const outside = ((feed && feed.outside_book) || []).slice(0, 20).map((row) =>
        `<div class="hr-line"><strong>${escapeHtml(row.ticker)}</strong> ${escapeHtml(row.issuer || "")} · ${(row.managers || []).map((item) => escapeHtml(item.name)).join(", ")}</div>`
      ).join("");
      root.innerHTML = `
        <p class="tier-sub">${escapeHtml((feed && feed.context) || (index && index.context) || "")}</p>
        <h3>Consensus</h3>
        <p class="tier-sub">SSI names where at least three managers added or started a position in ${escapeHtml((feed && feed.quarter) || "")}.</p>
        ${consensus || '<p class="tier-sub">None this quarter.</p>'}
        <h3>Changes</h3>
        ${changes || '<p class="tier-sub">No SSI changes on file.</p>'}
        <h3>Outside this book</h3>
        <p class="tier-sub">New positions of at least 3 percent of a manager's book, held by two or more managers, and not in the SSI book.</p>
        ${outside || '<p class="tier-sub">None this quarter.</p>'}
        <h3>Managers</h3>
        <div id="manager-list">${managers.map(managerLine).join("")}</div>
        <div id="manager-detail"></div>`;
      root.querySelectorAll("[data-manager]").forEach((button) => {
        button.addEventListener("click", () => {
          const id = button.getAttribute("data-manager");
          const detail = document.getElementById("manager-detail");
          if (!detail || !id) return;
          detail.textContent = "Loading…";
          fetch(dataUrl(`data/holdings/by_manager/${encodeURIComponent(id)}.json`))
            .then((response) => (response.ok ? response.json() : null))
            .then((page) => {
              if (!page) {
                detail.textContent = "No page for that manager.";
                return;
              }
              const rows = (page.positions || []).map((row) =>
                `<div class="hr-line">${escapeHtml(row.ticker || row.issuer)} · ${shares(row.shares)} shares · ${money(row.value_usd)} · ${row.weight_pct != null ? `${escapeHtml(row.weight_pct)}%` : ""}</div>`
              ).join("");
              const moved = (page.ssi_changes || []).slice(0, 12).map((row) =>
                `<div class="hr-line">${escapeHtml(row.change_type)} ${escapeHtml(row.ticker)}</div>`
              ).join("");
              detail.innerHTML = `<h3>${escapeHtml(page.name)}</h3><p class="tier-sub">${escapeHtml(page.quarter || "")} · <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${escapeHtml(page.cik || "")}&type=13F-HR" target="_blank" rel="noopener">SEC filings</a></p>${rows}${moved ? `<h3>SSI changes</h3>${moved}` : ""}`;
            })
            .catch(() => { detail.textContent = "Could not load that manager."; });
        });
      });
    }).catch(() => {
      const node = document.getElementById("managers-page");
      if (node) node.textContent = "Manager filings could not be loaded.";
    });
  }

  ensureSummary();
  window.FundHoldings = { renderTicker, fillTicker, badgeHtml, ensureSummary, renderManagersPage, fillManagersPage };
})();
