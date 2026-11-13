(function (global) {
  "use strict";
  const esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const human = (s) => String(s ?? "").replace(/_/g, " ");
  const fmt = (n) =>
    typeof n === "number" && Number.isFinite(n)
      ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n)
      : "Unknown";
  const link = (url, label) =>
    /^https:\/\//.test(url || "")
      ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`
      : esc(label);
  const state = {
    view: "changes",
    commodity: "gold",
    region: "all",
    horizon: "all",
    company: "all",
  };
  let cached = null;
  const fetchedTimes = new WeakMap(),
    openedTimes = new WeakMap();
  function recordFetch(doc, at = new Date().toISOString()) {
    if (doc) fetchedTimes.set(doc, at);
  }
  function rows(doc) {
    return (doc.datasets || []).flatMap((d) =>
      d.values.map(([period, value, basis]) => ({
        ...d,
        values: undefined,
        period,
        value,
        basis,
      })),
    );
  }
  function table(items, cols, limit = 120) {
    if (!items.length)
      return '<p class="cm-muted">No matching dated rows. Missing inputs remain visible in the coverage and source audit.</p>';
    return `<div class="cm-table" tabindex="0"><table><thead><tr>${cols.map((c) => `<th scope="col">${esc(c[1])}</th>`).join("")}</tr></thead><tbody>${items
      .slice(-limit)
      .map(
        (r) =>
          `<tr>${cols.map(([k]) => `<td>${typeof r[k] === "number" ? fmt(r[k]) : esc(human(r[k]))}</td>`).join("")}</tr>`,
      )
      .join(
        "",
      )}</tbody></table></div>${items.length > limit ? `<p class="cm-muted">Showing the latest ${limit} of ${fmt(items.length)} rows. Download includes all filtered rows.</p>` : ""}`;
  }
  function chart(items) {
    const periods = [...new Set(items.map((r) => r.period))].sort();
    if (periods.length < 2) return "";
    const lo = Math.min(...items.map((r) => r.value)),
      hi = Math.max(...items.map((r) => r.value));
    const x = (p) => 50 + (periods.indexOf(p) * 590) / (periods.length - 1),
      y = (v) => 170 - ((v - lo) * 140) / (hi - lo || 1);
    const groups = [
      ["observed", "#68c6dc", ""],
      ["published_forecast", "#d6ac62", "6 3"],
      ["assumed", "#b0a5ca", "2 4"],
    ];
    return `<svg class="cm-chart" viewBox="0 0 680 210" role="img" aria-label="Dated observations and publisher forecasts in ${esc(items[0].unit)}"><path d="M50 20V170H650" fill="none" stroke="#53647a"/><text x="2" y="30" fill="#a6b1c4" font-size="11">${fmt(hi)}</text><text x="2" y="170" fill="#a6b1c4" font-size="11">${fmt(lo)}</text>${groups
      .map(([basis, color, dash]) => {
        const rs = items
          .filter((r) =>
            basis === "observed"
              ? r.basis.startsWith("observed")
              : basis === "assumed"
                ? !r.basis.startsWith("observed") &&
                  r.basis !== "published_forecast"
                : r.basis === basis,
          )
          .sort((a, b) => a.period.localeCompare(b.period));
        return `<path d="${rs.map((r, i) => `${i ? "L" : "M"}${x(r.period)} ${y(r.value)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2" stroke-dasharray="${dash}"/>`;
      })
      .join(
        "",
      )}<text x="50" y="195" fill="#a6b1c4" font-size="11">${esc(periods[0])}</text><text x="575" y="195" fill="#a6b1c4" font-size="11">${esc(periods.at(-1))}</text></svg><p class="cm-muted">Cyan solid: reported history or estimates · Gold dashed: publisher forecast · Purple dotted: assumptions. ${esc(items[0].unit)}</p>`;
  }
  function filtered(doc) {
    return rows(doc).filter(
      (r) =>
        r.commodity === state.commodity &&
        (state.region === "all" || r.region === state.region) &&
        (state.horizon === "all" ||
          (state.horizon === "history"
            ? r.basis.startsWith("observed")
            : !r.basis.startsWith("observed"))),
    );
  }
  function changes(doc) {
    return `<h4>Changes since the prior published model</h4><p class="cm-muted">Revisions compare the same economic series and period across captured vintages. A first capture is labeled new.</p>${table(
      doc.changes.filter((r) => r.commodity === state.commodity),
      [
        ["period", "Period"],
        ["metric", "Metric"],
        ["region", "Region"],
        ["before", "Prior"],
        ["after", "Current"],
        ["change", "Change"],
        ["unit", "Unit"],
        ["kind", "Kind"],
      ],
    )}<details><summary>Original sources and capture dates · ${doc.sources.length}</summary><div class="cm-grid">${doc.sources.map((s) => `<div class="cm-box"><strong>${link(s.url, human(s.id))}</strong><p>${esc(human(s.state))}</p><p class="cm-muted">Published ${esc(s.published_at || "Unknown; availability bounded by retrieval")}<br>Retrieved ${esc(s.retrieved_at)}<br>Parser reviewed ${esc(s.reviewed_at)}<br>SHA ${esc(s.sha256.slice(0, 12))}</p></div>`).join("")}</div></details>`;
  }
  function tight(doc) {
    const ready = doc.readiness[state.commodity];
    const data = filtered(doc);
    const metrics = [...new Set(data.map((r) => r.metric))];
    const metric =
      state.region !== "all"
        ? metrics[0]
        : {
            crude: "papr_world",
            gas: "NGWG_SC",
            power: "ELWHU_TX",
            gold: "central_bank",
          }[state.commodity] || metrics[0];
    return `<div class="cm-score">${fmt(ready?.weighted_pct)}% decision-weighted evidence</div><p class="cm-muted">${esc(ready?.basis)} ${ready?.core_ready ? "Core inputs available." : "Core evidence remains incomplete."}</p>${table(
      ready?.items || [],
      [
        ["title", "Input"],
        ["weight", "Importance weight"],
        ["ready", "Ready"],
        ["latest_period", "Latest period"],
        ["reason", "Gap"],
      ],
    )}<h4>${esc(human(metric))}</h4>${chart(data.filter((r) => r.metric === metric))}${table(
      data,
      [
        ["period", "Period"],
        ["product", "Product"],
        ["region", "Region"],
        ["value", "Value"],
        ["unit", "Unit"],
        ["basis", "Basis"],
        ["known_at", "Known since"],
      ],
    )}<button type="button" data-cm-download="observations">Download filtered observations</button>${state.commodity === "silver" ? "<p>Gross vault holdings do not measure freely available supply. No depletion date is inferred.</p>" : ""}`;
  }
  function scenarios(doc) {
    const wiring = doc.driver_wiring[state.commodity] || {};
    let detail = "";
    if (state.commodity === "crude")
      detail = `<h4>Native monthly publisher baseline</h4>${table(
        doc.oil_monthly.rows,
        [
          ["period", "Month"],
          ["brent", "Brent $/bbl"],
          ["wti", "WTI $/bbl"],
          ["spread", "Spread"],
          ["production_mbd", "Supply mb/d"],
          ["consumption_mbd", "Use mb/d"],
          ["balance_mbd", "Balance mb/d"],
          ["oecd_stock_mb", "OECD stocks mb"],
          ["basis", "Basis"],
        ],
      )}<p>${esc(doc.oil_monthly.note)}</p>${doc.oil_monthly.scenarios
        .map(
          (s) =>
            `<details><summary>${esc(s.label)} · monthly physical stress</summary>${table(
              s.rows,
              [
                ["period", "Month"],
                ["balance_mbd", "Balance mb/d"],
                ["lagged_supply_response_mbd", "Lagged response mb/d"],
                ["brent", "Brent $/bbl"],
                ["price_status", "Price basis"],
              ],
            )}</details>`,
        )
        .join("")}`;
    if (state.commodity === "gold")
      detail = `<h4>Quarterly gold flows · tonnes unless price</h4>${table(
        doc.gold_quarters,
        [
          ["period", "Quarter"],
          ["mine", "Mine"],
          ["recycling", "Recycling"],
          ["jewellery", "Jewellery fabrication"],
          ["etf", "ETF absorption"],
          ["central_bank", "Official buying"],
          ["otc_other", "OTC / residual"],
          ["price", "Bullion $/oz"],
        ],
      )}`;
    if (state.commodity === "silver")
      detail = `<p>${esc(doc.solar.note)}</p>${doc.solar.scenarios
        .map(
          (s) =>
            `<details><summary>${esc(s.label)}</summary>${table(s.rows, [
              ["period", "Year"],
              ["production_gw", "Cell production GW"],
              ["weighted_mg_per_watt", "Net mg/W"],
              ["pv_moz", "PV Moz"],
              ["balance_less_etp_moz", "Balance after ETP Moz"],
            ])}</details>`,
        )
        .join(
          "",
        )}<form class="cm-calculator" data-cm-solar><h4>Solar manufacturing sensitivity</h4><p class="cm-muted">User assumptions; net intensity includes thrifting and recovered process scrap. Cell production and installations are different.</p><label>Cell production GW <input name="gw" type="number" min="0" value="800" required></label><label>Net silver mg/W <input name="intensity" type="number" min="0" step="0.1" value="${doc.solar.baseline_mg_per_watt.toFixed(3)}" required></label><button type="submit">Calculate silver demand</button><output aria-live="polite"></output></form>`;
    if (state.commodity === "gas")
      detail = `<p>${esc(doc.energy?.regional_storage_basis || "Basin marketed gas and regional working storage are separate accounting bases.")}</p><p>${esc(doc.energy?.national_accounting || "Regional and asset paths are cross-checks, not additive national demand.")}</p>${(
        doc.energy?.lng || []
      )
        .map(
          (s) =>
            `<details><summary>${esc(human(s.id))} · LNG ramp and feedgas</summary>${table(
              s.rows,
              [
                ["period", "Month"],
                ["output_bcf_day", "LNG output Bcf/d"],
                ["feedgas_bcf_day", "Feedgas incl fuel Bcf/d"],
              ],
            )}</details>`,
        )
        .join("")}`;
    if (state.commodity === "power") detail = powerCalculator(doc);
    return `<p class="cm-status">Named stresses carry no probability. A balanced physical equation does not establish price-forecasting skill.</p><ul>${Object.entries(
      wiring,
    )
      .map(([k, v]) => `<li><strong>${esc(human(k))}:</strong> ${esc(v)}</li>`)
      .join(
        "",
      )}</ul>${detail}<details><summary>Dependent shocks · counted once</summary><p>These are named sensitivities without probabilities or calibrated physical price responses.</p>${(
      doc.joint_stresses || []
    )
      .map(
        (s) =>
          `<h4>${esc(s.name)}</h4><p class="cm-muted">${esc(s.period_basis || "")}</p>${table(
            Object.entries(s.effects).map(([metric, effect]) => ({
              metric,
              effect,
            })),
            [
              ["metric", "Affected quantity / unit"],
              ["effect", "Change"],
            ],
          )}<ul>${s.lineage.map((l) => `<li>${esc(human(l.driver))}: ${esc(l.evidence)}</li>`).join("")}</ul>`,
      )
      .join(
        "",
      )}</details><details><summary>Reviewed operating cases · ${(doc.operating_cases || []).length}</summary>${(doc.operating_cases || []).map((c) => `<h4>${esc(c.name)}</h4><pre>${esc(JSON.stringify(c, null, 2))}</pre>`).join("") || "<p>No fully evidenced asset case has been promoted. Missing data are listed under Falsifiers.</p>"}</details><details><summary>Cost definitions and disclosed sample</summary><p>Cash, sustaining, new-project incentive and required-return costs are separate. Missing costs stay unknown. Percentiles describe only the disclosed sample; publisher ownership exceptions remain unresolved.</p>${table(
      doc.cost_curves,
      [
        ["kind", "Cost"],
        ["currency", "Currency"],
        ["period", "Period"],
        ["sample_assets", "Assets"],
        ["sample_production", "Production oz"],
        ["weighted_average", "Weighted cost /oz"],
        ["coverage_pct", "Global coverage %"],
      ],
    )}</details><details><summary>Forecast evidence</summary><p>${esc(doc.forecast_validation.status)} · Structural skill: ${esc(doc.forecast_validation.structural_skill)}.</p><p>${esc(doc.forecast_validation.actuals_basis)} ${esc(doc.forecast_validation.futures_baseline)}</p>${table(
      doc.forecast_validation.summary,
      [
        ["commodity", "Commodity"],
        ["metric", "Metric"],
        ["model", "Model"],
        ["horizon", "Horizon months"],
        ["regime", "Regime"],
        ["n", "Cases"],
        ["mae", "MAE"],
        ["rmse", "RMSE"],
      ],
    )}</details>`;
  }
  function companies(doc, download = true) {
    return `<p class="cm-muted">Revenue coverage and verified future cash-flow coverage are separate. Scenarios never alter approved valuation or base IRR.</p>${doc.companies
      .filter((c) => state.company === "all" || c.ticker === state.company)
      .map(
        (c) =>
          `<div class="cm-box"><h4>${esc(c.ticker)} · ${esc(human(c.kind))}</h4><p>${fmt(c.revenue_sensitivity_coverage_pct)}% of reported revenue mapped · ${fmt(c.contract_cashflow_coverage_pct)}% future contract cash-flow coverage verified</p><p>${link(c.source_url, `${c.period} disclosure`)} · Published ${esc(c.published_at)} · Reviewed ${esc(c.reviewed_at)}</p><p>${esc(c.volume_basis)}. ${esc(c.base.basis)}</p>${
            c.ticker === "SJT"
              ? table(c.cases, [
                  ["gas_multiplier", "Gas price multiple"],
                  ["field_net_usd", "Field net $"],
                  ["gross_deficit_usd", "Remaining gross deficit $"],
                  [
                    "royalty_cash_before_trust_hurdles_usd",
                    "NPI cash before trust hurdles $",
                  ],
                  [
                    "cash_after_known_hurdles_before_interest_usd",
                    "Cash after known hurdles, before interest $",
                  ],
                ])
              : table(c.cases, [
                  ["price_multiplier", "Gold & silver price multiple"],
                  ["revenue_usd", "Revenue $"],
                  ["cash_margin_usd", "Cash operating margin $"],
                  ["fcf_usd", "FCF $"],
                ])
          }<details><summary>Reconciliation and unknowns</summary><p>Maximum disclosure reconciliation residual: $${fmt(Math.max(...Object.values(c.reconciliation_usd).map(Math.abs)))}.</p><ul>${c.unknowns.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></details></div>`,
      )
      .join(
        "",
      )}${download ? '<button type="button" data-cm-download="companies">Download company bridges</button>' : ""}`;
  }
  function falsifiers(doc) {
    return `<h4>What would invalidate the current interpretation?</h4><ul>${doc.unknowns.map((s) => `<li>${esc(s)}</li>`).join("")}</ul><p>Price paths remain scenarios until rolling-origin results beat no-change, seasonal and dated publisher/futures benchmarks across normal and shock periods.</p><h4>Coverage audit beyond the current engines</h4>${table(
      doc.coverage_audit.map((r) => ({
        ...r,
        registered_issuers: r.registered_issuers.join(", "),
      })),
      [
        ["commodity", "Commodity"],
        ["registered_issuers", "Research issuers"],
        ["model_status", "Model"],
        ["position_weight", "Funded exposure"],
      ],
    )}<p class="cm-muted">Registry membership does not establish a funded position. Capital-weighted priority awaits reconciled position reports.</p><ul>${doc.entitlements.map((e) => `<li>${esc(e.dataset)} · ${esc(human(e.status))}</li>`).join("")}</ul>`;
  }
  function powerProfiles(doc) {
    const native = rows(doc).filter(
      (r) => r.metric === "native_hourly_load" && r.region === "ERCOT",
    );
    const profile = native.length
      ? native
      : rows(doc).filter(
          (r) => r.metric === "hourly_load" && r.region === "ERCOT",
        );
    const latest = profile
      .map((r) => r.period.slice(0, 7))
      .sort()
      .at(-1);
    return profile.filter((r) => r.period.startsWith(latest));
  }
  function powerCase(profiles, p) {
    if (
      Object.values(p).some((v) => !Number.isFinite(v) || v < 0) ||
      p.fixed > 1
    )
      throw Error(
        "Enter nonnegative assumptions; fixed contract share must be 0–1.",
      );
    let cost = 0,
      weight = 0,
      unserved = 0;
    for (const hour of profiles) {
      const remaining = Math.max(0, hour.value - p.nonGas),
        shortfall = Math.max(0, remaining - p.gasMW);
      const merchant = shortfall
        ? p.scarcity
        : remaining
          ? p.gas * p.heat + p.variable
          : 0;
      const price = (1 - p.fixed) * merchant + p.fixed * p.contract;
      cost += price * hour.weight_hours;
      weight += hour.weight_hours;
      unserved += shortfall * hour.weight_hours;
    }
    return { price: weight ? cost / weight : null, unserved, hours: weight };
  }
  function powerCalculator(doc) {
    const profile = powerProfiles(doc);
    if (!profile.length)
      return "<p>Measured hourly load is unavailable. Dispatch is withheld.</p>";
    return `<p>Measured ERCOT load · ${esc(profile[0].period.slice(0, 7))} · ${fmt(profile.length)} ${profile[0].metric === "native_hourly_load" ? "native settlement hours" : "representative month/hour/day-type cells"}. Weather-zone profiles and monthly ERCOT/PJM hub prices are available in Where tight.</p><p class="cm-status">Conditional dispatch using measured load and your supply assumptions. Renewable output, outages and congestion are not inferred from annual totals; this is not a verified nodal price forecast.</p>${table(
      profile,
      [
        ["period", "Local settlement-hour group"],
        ["value", "Average load MW"],
        ["weight_hours", "Source hours"],
      ],
    )}<form class="cm-calculator" data-cm-power><h4>Firm supply and contract sensitivity</h4><div class="cm-grid">${[
      ["nonGas", "Assumed available non-gas supply MW", 20000],
      ["gasMW", "Available gas generation MW", 50000],
      ["gas", "Gas $/MMBtu", 3],
      ["heat", "Gas heat rate MMBtu/MWh", 7.5],
      ["variable", "Other gas operating cost $/MWh", 5],
      ["scarcity", "Assumed scarcity price $/MWh", 5000],
      ["fixed", "Fixed contract fraction (0–1)", 0.5],
      ["contract", "Fixed contract price $/MWh", 60],
    ]
      .map(
        ([key, label, value]) =>
          `<label>${label}<input name="${key}" type="number" min="0" ${key === "fixed" ? 'max="1"' : ""} step="any" value="${value}" required></label>`,
      )
      .join(
        "",
      )}</div><button type="submit">Calculate conditional power cost</button><output aria-live="polite"></output></form><p class="cm-muted">The assumed non-gas supply includes any available renewable generation. A fixed supply value does not establish renewable or firm capacity. No demand is added to the national gas balance.</p>`;
  }
  function renderCompany(doc, ticker) {
    if (!doc?.companies?.some((c) => c.ticker === ticker)) return "";
    const selection = state.company;
    state.company = ticker;
    const html = companies(
      { ...doc, companies: doc.companies.filter((c) => c.ticker === ticker) },
      false,
    );
    state.company = selection;
    return `<section class="cm-workspace">${html}</section>`;
  }
  function render(doc) {
    if (!doc) return "";
    cached = doc;
    if (!openedTimes.has(doc)) openedTimes.set(doc, new Date().toISOString());
    const reader = {
      label: fetchedTimes.has(doc)
        ? "Retrieved by this reader"
        : "First opened in this reader",
      time: fetchedTimes.get(doc) || openedTimes.get(doc),
    };
    const regions = [
      ...new Set(
        rows(doc)
          .filter((r) => r.commodity === state.commodity)
          .map((r) => r.region),
      ),
    ].sort();
    if (state.region !== "all" && !regions.includes(state.region))
      state.region = "all";
    const views = {
      changes: ["What changed", changes],
      tight: ["Where tight", tight],
      scenarios: ["Scenarios", scenarios],
      companies: ["Company exposure", companies],
      falsifiers: ["Falsifiers", falsifiers],
    };
    return `<section class="cm-workspace" data-cm-workspace><div class="cm-heading"><h3>Commodity evidence desk</h3><span class="cm-muted">Served model ${esc(doc.publication.model_id)} · Built ${esc(doc.publication.as_of)}</span></div><p class="cm-status">${esc(human(doc.publication.status))} · Context only; excluded from base IRR.</p><div class="cm-tabs" role="tablist" aria-label="Commodity research views">${Object.entries(
      views,
    )
      .map(
        ([id, [label]]) =>
          `<button type="button" role="tab" aria-selected="${state.view === id}" tabindex="${state.view === id ? 0 : -1}" data-cm-view="${id}">${label}</button>`,
      )
      .join(
        "",
      )}</div><div class="cm-filters"><label>Commodity <select data-cm-filter="commodity">${["crude", "gas", "power", "copper", "gold", "silver"].map((k) => `<option value="${k}" ${state.commodity === k ? "selected" : ""}>${esc(human(k))}</option>`).join("")}</select></label><label>Region / series <select data-cm-filter="region"><option value="all">All</option>${regions.map((r) => `<option value="${esc(r)}" ${state.region === r ? "selected" : ""}>${esc(human(r))}</option>`).join("")}</select></label><label>Horizon <select data-cm-filter="horizon">${[
      ["all", "All"],
      ["history", "Reported history"],
      ["forward", "Publisher forecast"],
    ]
      .map(
        ([k, v]) =>
          `<option value="${k}" ${state.horizon === k ? "selected" : ""}>${v}</option>`,
      )
      .join(
        "",
      )}</select></label><label>Company <select data-cm-filter="company"><option value="all">All pilots</option>${doc.companies.map((c) => `<option value="${esc(c.ticker)}" ${state.company === c.ticker ? "selected" : ""}>${esc(c.ticker)}</option>`).join("")}</select></label></div><div role="tabpanel" aria-live="polite">${views[state.view][1](doc)}</div><p class="cm-muted">${reader.label} ${esc(reader.time)}. Original publication, observation, review and build dates remain distinct. ${link("data/commodity_models.json", "Download full published model")}</p></section>`;
  }
  function bind(root) {
    root?.querySelectorAll("[data-cm-workspace]").forEach((host) => {
      if (host.dataset.bound) return;
      host.dataset.bound = "1";
      host.querySelectorAll("[data-cm-filter]").forEach((select) => {
        const key = select.dataset.cmFilter;
        const active =
          key === "company"
            ? state.view === "companies"
            : key === "commodity"
              ? !["companies", "falsifiers"].includes(state.view)
              : state.view === "tight";
        select.closest("label").hidden = !active;
      });
      const redraw = (focus) => {
        host.outerHTML = render(cached);
        bind(root);
        root.querySelector(focus)?.focus();
      };
      host.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-cm-view]");
        if (btn) {
          state.view = btn.dataset.cmView;
          redraw(`[data-cm-view="${state.view}"]`);
        }
        const dl = e.target.closest("[data-cm-download]");
        if (dl) {
          const content =
            dl.dataset.cmDownload === "observations"
              ? filtered(cached)
              : cached.companies.filter(
                  (c) => state.company === "all" || c.ticker === state.company,
                );
          const a = global.document.createElement("a");
          const url = URL.createObjectURL(
            new Blob([JSON.stringify(content, null, 2)], {
              type: "application/json",
            }),
          );
          a.href = url;
          a.download = `commodity-${dl.dataset.cmDownload}-${cached.publication.model_id}.json`;
          a.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
      });
      host.addEventListener("change", (e) => {
        const key = e.target.dataset.cmFilter;
        if (key) {
          state[key] = e.target.value;
          redraw(`[data-cm-filter="${key}"]`);
        }
      });
      host.addEventListener("keydown", (e) => {
        if (
          !e.target.matches("[data-cm-view]") ||
          !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
        )
          return;
        e.preventDefault();
        const tabs = [...host.querySelectorAll("[data-cm-view]")];
        const i = tabs.indexOf(e.target);
        const next =
          e.key === "Home"
            ? 0
            : e.key === "End"
              ? tabs.length - 1
              : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) %
                tabs.length;
        state.view = tabs[next].dataset.cmView;
        redraw(`[data-cm-view="${state.view}"]`);
      });
      host.addEventListener("submit", (e) => {
        if (e.target.matches("[data-cm-power]")) {
          e.preventDefault();
          const values = Object.fromEntries(
            [...new FormData(e.target)].map(([k, v]) => [k, Number(v)]),
          );
          try {
            const result = powerCase(powerProfiles(cached), values);
            e.target.querySelector("output").textContent =
              `Conditional delivered cost ${fmt(result.price)} $/MWh · Unserved load ${fmt(result.unserved)} MWh across ${fmt(result.hours)} measured hours. User supply assumptions; no forecast probability.`;
          } catch (error) {
            e.target.querySelector("output").textContent = error.message;
          }
          return;
        }
        if (!e.target.matches("[data-cm-solar]")) return;
        e.preventDefault();
        const f = new FormData(e.target);
        const gw = Number(f.get("gw")),
          intensity = Number(f.get("intensity"));
        e.target.querySelector("output").textContent =
          Number.isFinite(gw) &&
          Number.isFinite(intensity) &&
          gw >= 0 &&
          intensity >= 0
            ? `${fmt((gw * intensity) / 31.1034768)} million troy ounces of solar silver demand`
            : "Enter nonnegative finite assumptions.";
      });
    });
  }
  global.CommodityResolution = {
    render,
    renderCompany,
    bind,
    rows,
    chart,
    powerCase,
    powerProfiles,
    recordFetch,
  };
})(window);
