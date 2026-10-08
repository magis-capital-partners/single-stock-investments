/* Holder overlap on the coverage page. Research only. */
(function () {
  const SCOPES = [
    ["universe", "Universe"],
    ["owned", "Owned book"],
    ["michael", "Michael sleeve"],
    ["drew", "Drew sleeve"],
  ];
  let panel = null;
  let scope = "universe";
  let loading = false;

  function mount() {
    const host = document.getElementById("overlap-panel");
    if (!host || host.dataset.ready === "1") return;
    host.dataset.ready = "1";
    host.innerHTML = shell();
    host.querySelectorAll("[data-overlap-scope]").forEach((button) => {
      button.addEventListener("click", () => {
        scope = button.getAttribute("data-overlap-scope");
        load();
      });
    });
    load();
  }

  function shell() {
    const buttons = SCOPES.map(([id, label]) => (
      `<button type="button" class="filter-btn" data-overlap-scope="${id}">${label}</button>`
    )).join("");
    return `<h3 style="margin:0 0 6px">Who else holds these names</h3>
      <p class="subhead" id="overlap-note"></p>
      <div class="overlap-scopes">${buttons}</div>
      <div id="overlap-body"><p class="subhead">Loading holder overlap.</p></div>`;
  }

  async function load() {
    if (loading) return;
    loading = true;
    const body = document.getElementById("overlap-body");
    if (body) body.innerHTML = `<p class="subhead">Loading holder overlap.</p>`;
    try {
      const response = await fetch(`/api/v1/research/overlap?scope=${encodeURIComponent(scope)}`, { credentials: "same-origin" });
      if (response.status === 401) {
        panel = null;
        if (body) body.innerHTML = `<p class="subhead">This scope needs the portfolio sign-in. Universe stays available.</p>`;
        return;
      }
      if (!response.ok) throw new Error(String(response.status));
      panel = await response.json();
      paint();
      fillTicker(document.getElementById("overlap-ticker")?.dataset.ticker);
    } catch (error) {
      if (body) body.innerHTML = `<p class="subhead">Holder overlap did not load (${escapeText(error.message)}).</p>`;
    } finally {
      loading = false;
      markScope();
    }
  }

  function paint() {
    const note = document.getElementById("overlap-note");
    const body = document.getElementById("overlap-body");
    if (!panel || !body) return;
    if (note) note.textContent = panel.coverage?.holder_set_note || "";
    const hubs = panel.rows.filter((row) => row.hub_name && !row.omitted).slice(0, 25);
    const stress = panel.stress
      ? `<p>${escapeText(panel.stress.sentence || panel.stress.reason || "")}</p>
         <p>${escapeText(panel.stress.disclaimer || "")}</p>
         ${stressLine(panel.stress)}`
      : `<p class="subhead">Universe scope has no book value and no dollar stress.</p>`;
    body.innerHTML = `${stress}
      <h4>Hub names</h4>
      ${table(hubs)}
      <h4>Holder pairs</h4>
      <p class="subhead">Overlap dollars are the smaller reported market value on each shared name. A pair of specialists who both report the same thin book ranks on that overlap. A pair of large complexes ranks because both report a long list of giant companies. The two are not the same kind of crowd.</p>
      ${pairTable(panel.pairs || [])}`;
  }

  function stressLine(stress) {
    if (!stress.hub_holder) return "";
    const hub = `${stress.hub_holder.name}: ${(stress.hub_holder.overlap_share * 100).toFixed(1)}% of this book`;
    if (!stress.random_holder || stress.difference == null) {
      return `<p>${escapeText(hub)}. ${escapeText(stress.reason || "")}</p>`;
    }
    const random = `${stress.random_holder.name}: ${(stress.random_holder.overlap_share * 100).toFixed(1)}%`;
    const gap = `${(stress.difference * 100).toFixed(1)} percentage points`;
    return `<p>Hub holder ${escapeText(hub)}. One other holder, picked from this quarter and this book's date, ${escapeText(random)}. Difference ${escapeText(gap)}.</p>`;
  }

  function table(rows) {
    if (!rows.length) return `<p class="subhead">No hub name in this scope.</p>`;
    const lines = rows.map((row) => `<tr>
      <td class="mono">${escapeText(row.ticker)}</td>
      <td>${escapeText(row.company || "")}</td>
      <td>${escapeText(row.top_holder || "")}</td>
      <td>${row.top_share == null ? "" : `${(row.top_share * 100).toFixed(1)}%`}</td>
      <td>${row.holder_count}</td>
      <td>${escapeText(row.leverage_text || "")}</td>
      <td>${(row.index_tags || []).join(", ")}</td>
    </tr>`).join("");
    return `<table class="overlap-table"><thead><tr>
      <th>Name</th><th>Company</th><th>Largest holder</th><th>Share of reported value</th><th>Holders</th><th>Leverage</th><th>Index tag</th>
    </tr></thead><tbody>${lines}</tbody></table>`;
  }

  function pairTable(pairs) {
    if (!pairs.length) return `<p class="subhead">No shared names among the holders on file.</p>`;
    const lines = pairs.slice(0, 25).map((pair) => `<tr>
      <td>${escapeText(pair.left.name)}</td>
      <td>${escapeText(pair.right.name)}</td>
      <td>${pair.shared_names}</td>
      <td>${Math.round(pair.overlap_dollars).toLocaleString("en-US")}</td>
    </tr>`).join("");
    return `<table class="overlap-table"><thead><tr>
      <th>Holder</th><th>Holder</th><th>Shared names</th><th>Overlap dollars</th>
    </tr></thead><tbody>${lines}</tbody></table>`;
  }

  function renderTicker(ticker, escapeHtml) {
    const safe = escapeHtml(ticker);
    return `<details class="detail-section" id="overlap-ticker" data-ticker="${safe}" open>
      <summary>Who else holds ${safe}</summary>
      <div id="overlap-ticker-body"><p class="subhead">Loading holder overlap.</p></div>
    </details>`;
  }

  function fillTicker(ticker) {
    const host = document.getElementById("overlap-ticker-body");
    const slot = document.getElementById("overlap-ticker");
    if (!host || !slot || !ticker || slot.dataset.ticker !== ticker) return;
    if (!panel) {
      host.innerHTML = `<p class="subhead">Loading holder overlap.</p>`;
      return;
    }
    const row = (panel.rows || []).find((item) => item.ticker === ticker);
    if (!row) {
      host.innerHTML = `<p class="subhead">This name is not in the research universe file.</p>`;
      return;
    }
    if (row.omitted === "not_on_13f") {
      host.innerHTML = `<p>No US CUSIP is on file, so this name is not on the 13F join.</p>`;
      return;
    }
    if (row.omitted === "not_stock") {
      host.innerHTML = `<p>This line is not a common stock, so it is left off the holder map.</p>`;
      return;
    }
    if (!row.holder_count) {
      host.innerHTML = `<p>No holder on file.</p>`;
      return;
    }
    const floatLine = row.top_float_share != null
      ? `<p>Largest holder shares are ${(row.top_float_share * 100).toFixed(1)}% of shares in the public float.</p>`
      : (row.float_note ? `<p>${escapeText(row.float_note)}.</p>` : "");
    const shortLine = row.short_percent_float != null
      ? `<p>Short interest is ${(row.short_percent_float * 100).toFixed(1)}% of float. That column is not a 13F holder.</p>`
      : "";
    const lines = (row.holders || []).slice(0, 12).map((holder) => `<li>${escapeText(holder.name)} · ${escapeText(holder.leverage || "not reported")}${holder.above_threshold ? " · above the threshold" : ""}</li>`).join("");
    host.innerHTML = `<p>${row.hub_name ? "Hub name. " : ""}${escapeText(row.top_holder || "The largest holder")} reports ${row.top_share == null ? "" : `${(row.top_share * 100).toFixed(1)}%`} of the market value on file. ${row.holder_count} holders on file.</p>
      ${floatLine}${shortLine}
      <ul>${lines}</ul>`;
  }

  function markScope() {
    document.querySelectorAll("[data-overlap-scope]").forEach((button) => {
      button.classList.toggle("active", button.getAttribute("data-overlap-scope") === scope);
    });
  }

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[char]));
  }

  window.OverlapViz = { mount, renderTicker, fillTicker };
})();
