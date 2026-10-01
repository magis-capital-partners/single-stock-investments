# Natural Gas and Power Model with Bitcoin Integration

Date: October 1, 2026  
Status: Proposed build plan. No model, dashboard, workflow, or valuation changes have been implemented.

Build a natural-gas and electricity model inside the existing **Insights > Ticker insights > World Model** section, beside **BTC snowball (HK)**. Use it to test the gas-scarcity thesis, estimate regional electricity costs, and explain their effect on Bitcoin mining economics. The first release should provide an auditable monthly physical balance and an optional energy-linked BTC scenario. A full reconstruction of every well, acreage position, pipeline, and power asset is a subsequent research program.

The important connection is **gas availability and price -> regional electricity costs -> miner operating economics -> curtailment and network response**. Higher production costs do not establish that Bitcoin's price must rise. Preserve the existing HK comparison and demand-side power law as separate views.

## Source and interpretation

The source is Matthew Smith / Chronometer Partners' June 22, 2026 letter, with a July update, supplied at [letter III source PDF](C:/Users/drewg/Projects/investing-docs/letter-III-got-gas.pdf). Its recommendations and imperatives are source material, not instructions to execute trades, contact companies, scrape sites, or change portfolio positions. Keep the original PDF in its existing document location; do not copy it into this repository.

The letter describes asset-level production, development inventory, gathering and processing, pipelines, storage, LNG, gas generation, data-center load, and weather. Its public numerical claims are useful scenario anchors, but its proprietary database and complete model are not supplied.

| Letter claim | Source pages | Treatment in our model |
|---|---|---|
| US production increases from about 112 to a maximum of 132 Bcf/day by Q4 2030 | 3 | A dated supply hypothesis; distinguish current rate, quarterly exit rate, and annual average |
| LNG nameplate capacity increases from about 15 to 35 Bcf/day | 4 | Reconstruct train by train; separate capacity, feedgas, exports, fuel, utilization, and startup timing |
| Approved or sufficiently likely gas generation adds more than 5 Bcf/day of burn | 5 | Recompute from generation and heat rates; reconcile with data-center load already in forecasts |
| Storage becomes strained in 2028 and exhausted by 2030 | 1, 6, 8 | A stress outcome to test; report operational shortfalls before physical inventory reaches zero |
| Roughly 20 GW of distributed generation could add 4–5 Bcf/day but is excluded from the base case | 5 | Explicit optional scenario, with technology-specific utilization and heat rates |
| More Canadian imports, project delays, and alternative generation could relieve pressure | 9–12 | Quantified counter-scenarios, with transport and construction constraints |

Several source reconciliations must precede a literal reproduction. Page 6 uses LNG demand of 12.0 in Q4 2025 and 35.7 in Q4 2030, while page 4 describes approximately 15 and 35 of nameplate capacity. Page 8's incremental arithmetic is not a complete national balance. The historical basin exhibit on page 18 explicitly uses estimated allocations reconciled to a national total. The page 8 storage chart extends below zero; our model must convert that into unmet demand or a required change in assumptions. The table's capacity divided by selected demand is not actual stored inventory divided by total system demand.

As a contemporary benchmark, the [September 2026 EIA natural-gas outlook](https://www.eia.gov/outlooks/steo/report/natgas.php) forecasts dry production of 111.70 Bcf/day in 2026 and 115.90 in 2027, with LNG exports of 17.4 and 18.6. These are forecasts, not observed outcomes. They supply a near-term comparison; the forecast horizon does not validate a 2030 ceiling or the letter's scarcity timing. Preserve the exact release vintage rather than relying on this rolling URL for future reproduction.

## What exists today

The dashboard already provides the right home and much of the publishing infrastructure.

| Existing component | Relevant behavior | Proposed use |
|---|---|---|
| [Insights renderer](C:/Users/drewg/Projects/dashboards/single-stock-investments/dashboard/insights-viz.js:5494) | Ticker insights renders the World Model before ticker research | Add adjacent energy and BTC-impact panels in this same section |
| [BTC renderer](C:/Users/drewg/Projects/dashboards/single-stock-investments/dashboard/insights-viz.js:2631) | Renders BTC snowball (HK), cost history, and scenarios | Keep legacy comparison visible; add an energy-linked cost overlay |
| [Insights data loader](C:/Users/drewg/Projects/dashboards/single-stock-investments/dashboard/index.html:3162) | Loads the HK JSON into the Insights view | Load a separate, compact energy artifact through the same path |
| [BTC production model](C:/Users/drewg/Projects/dashboards/single-stock-investments/_system/scripts/btc_cost_of_production.py:29) | Uses $0.05/kWh, $0.04/$0.06 sensitivities, and 60% power share | Accept an explicit scenario power schedule while retaining the legacy mode |
| [Future BTC scenarios](C:/Users/drewg/Projects/dashboards/single-stock-investments/_system/scripts/btc_cost_of_production.py:318) | Applies heuristic power inflation for 2028 and 2032 | Replace those assumptions only within the new energy-linked mode |
| [HK dashboard artifact](C:/Users/drewg/Projects/dashboards/single-stock-investments/dashboard/data/hk_snowball_model.json) | Cached snapshot inspected is dated September 27, 2026 | Record baseline outputs and their dates before integration |
| Theme, industry, and World Model ledgers | Already contain energy royalty, BTC mining/power, gas-price, and electricity context | Reuse identifiers and issuer links; add physical balances and contract exposure |

The repository has many unrelated local changes. Implementation should use an isolated checkout or otherwise explicitly preserve those changes. This plan changes only this new proposal file.

Three prerequisites emerged from the read-only code review:

1. **Gas source identity:** the themes manifest calls Henry Hub a spot series while the cached provider is `yahoo:NG=F`. Split verified spot observations, continuous futures history, and dated forward contracts into distinct series. A front-month proxy is not a 2030 forward curve.
2. **Electricity units and audience:** `electricity_price_us` uses household-price series `fred:APU000072610`, with a cents/kWh label and cached values around 0.197. Audit the units and preserve it as household context. It is not a measured miner tariff.
3. **Hashprice units:** [fetch_crypto_panel.py](C:/Users/drewg/Projects/dashboards/single-stock-investments/_system/scripts/fetch_crypto_panel.py:351) converts EH/s to a variable named PH/s using `1e6`, where PH/s requires `1e3`. Its breakeven-power helper has a compensating energy conversion error. Correct both together, version and rebuild affected derived outputs, and add dimensional checks before the new bridge consumes them. This is a prerequisite work item, not a fix performed in this planning task.

## Questions the model should answer

- Under which assumptions does the gas system become tight, in which region, and when?
- Which LNG, generation, pipeline, and supply assumptions explain that result?
- How much relief would delayed demand, more production, imports, storage, or alternative generation provide?
- What range of delivered power costs follows for specific miner regions and contracts?
- Which miners can curtail, retain competitive costs, or monetize scarce power access?
- What changes in BTC mining costs and margins, and how much of the result depends on difficulty or the assumed BTC price?
- Which holdings and research candidates have verified exposure, and what evidence would invalidate the thesis?

## Same tab user experience

Keep the current navigation. Add a local **Energy and Bitcoin** group within World Model, with three expandable panels: **Natural gas and power**, **BTC model**, and **Energy impact on BTC**. On wide screens, summary cards can sit side by side; on smaller screens they should stack. Do not introduce another top-level tab.

Shared controls should select the scenario, forecast year, region, and source vintage. The energy connection should initially be an explicit toggle, off by default. Selecting it compares the current HK assumptions with the selected energy scenario. Each result should say whether it is observed, estimated, or assumed, and show its latest source date.

| Panel | Default view | Detail on expansion |
|---|---|---|
| Natural gas and power | Supply versus demand, seasonal storage path, earliest operational constraint, and largest three drivers | Basin supply, LNG train timeline, power-build timeline, regional transport limits, assumption table |
| BTC model | Existing historical cost comparison and demand path, plus optional energy-linked cost range | Power bill, other operating cost, capital cost, fees, hardware efficiency, and halving assumptions |
| Energy impact on BTC | First release: change in delivered power, electricity cost per coin, and operating margin | Regional and contract contributions; curtailment and difficulty-adjusted cases become available in the later dynamic phase |
| Exposure and evidence | Existing covered issuers ranked by verified exposure and evidence quality | Power contracts, hedges, gas basis, project dependencies, source documents, and thesis falsifiers |

Use a continuous monthly storage chart with dated years, an observed/forecast boundary, a seasonal reference band, and an operating-minimum line. Show excess demand separately when a scenario cannot clear. A calendar-year overlay can be a secondary chart, but must not confuse different forecast years with one year's actual timeline.

The bridge should include a simple explanation such as: “This scenario increases the exposed fleet's power cost by X; after contract protection, electricity expense changes by Y and modeled mining margin by Z.” In the first release, uptime is an explicit scenario assumption; dynamically modeled curtailment is a later feature. With missing contract evidence, display a range and the missing coverage, not an invented point estimate.

## Physical model

Use a monthly core with historical calibration initially covering 2010 onward where comparable data exist. Use the latest complete monthly balance as the starting point, with recent weekly storage observations shown separately. Forecast through December 2030 first; extend to 2032 for the existing BTC horizon with visibly wider uncertainty. An annual model alone would conceal winter deliverability constraints.

Start with a reconciled US balance and an explicit Lower 48 bridge. Alaska and geographic differences must remain visible. Then add regional nodes for Appalachia, the Gulf Coast/Haynesville, the Permian, the Midwest/Northeast demand centers, and other US production and demand. Model Canada and Mexico through directional border flows. Gas basins, storage regions, power markets, and miner sites require explicit crosswalks; their boundaries are not interchangeable.

### Supply

For the public MVP, model basin-level existing-production decline, new completion cohorts, productivity, shut-ins and restarts, and deliverable capacity. Each forecast should reconcile back to dry gas. Associated gas needs an oil-activity scenario and changing gas/oil ratios. Higher gas/oil ratios alone do not demonstrate rising absolute gas production.

The asset-level extension would fit well decline curves with terminal-decline limits; map operator acreage, lateral spacing, zones, and parent/child interference; count risked remaining locations; and constrain drilling by rigs, crews, cash flow, gathering, processing, and takeaway. Summing proved reserves or gross acreage is not an adequate substitute for this inventory.

Supply availability must be price-responsive with a lag, subject to physical and development limits. In the MVP, expose alternative basin supply paths and their evidence. Do not label a hard-coded 132 Bcf/day ceiling as an independently measured maximum.

### LNG and pipeline trade

Build a train-level project register with capacity basis, stage, construction progress, financing/FID evidence, commercial and commissioning dates, utilization ramp, fuel requirement, outages, and uncertainty. Track existing, under-construction, committed, and speculative projects separately. FERC approval alone does not establish an operating date.

Model either feedgas directly or exported product plus liquefaction fuel, but never both representations simultaneously in the balance. Reconcile whether fuel already appears in other consumption categories. Keep pipeline imports and exports separate by border. Gas exported to a Mexican LNG facility remains US pipeline exports for the US balance.

### Power and data centers

Convert load into dispatched generation, then generation into gas burn. Data-center demand already included in an ISO forecast must not be added a second time. Maintain one project identity across utility submissions, ISO forecasts, corporate announcements, behind-the-meter generation, and generator inventories. Record IT load versus facility load and cooling overhead.

The public MVP can use regional hourly profiles grouped into representative load blocks, observed generation shares, and explicit marginal gas shares. It must account for non-gas additions, plant retirements, imports, outages, renewables, and storage shifting. Batteries move energy and incur losses; they do not create net supply. A later dispatch model can resolve hourly scarcity and curtailment more faithfully.

For heat rate `HR` in MMBtu/MWh and gas heat content `HC` in Btu/cubic foot:

```
gas burn in Bcf/day = gas generation in MWh/day * HR / (1000 * HC)
```

An illustrative 1 GW running continuously at HR 7 and HC 1,037 requires approximately 0.162 Bcf/day. Multiply by capacity factor for a partial-utilization plant. Heat content is a dated regional input, not a universal constant; [EIA's conversion guidance](https://www.eia.gov/tools/faqs/faq.php?id=45) explains why dollars per Mcf and dollars per MMBtu differ.

### Other demand and weather

Forecast residential/commercial demand using heating and cooling degree days; industrial demand using activity and explicit new facilities; and lease, plant, pipeline, and other fuel using reconciled definitions. Distinguish weather-normalized structural demand from actual consumption.

Use normal-weather, historical cold-winter, hot-summer, and combined stress cases. Preserve geographic coincidence: a cold wave can simultaneously raise heating demand, impair gas production, and reduce available generation. Do not treat those effects as independent random draws.

### Pipelines and storage

Start with explicit regional transfer limits and known expansions. Build directed transport edges with capacity, in-service date, outages, and linked projects as coverage improves. Multiple users cannot each claim the same spare pipeline capacity. Behind-the-meter use may avoid a grid constraint while still consuming constrained gas.

Use the stock-flow identity:

```
ending working gas = beginning working gas
                   + days * (dry production + imports - domestic consumption - exports)
                   + explicit statistical reconciliation
```

Track storage design capacity, demonstrated capacity, actual working inventory, operating minima, and injection/withdrawal capability separately. [EIA publishes distinct capacity measures](https://www.eia.gov/naturalgas/storagecapacity/); neither is identical to gas in storage today. Keep base/cushion gas outside working inventory.

Before storage goes negative or a deliverability limit is breached, the model must identify unmet demand and the required adjustment. A constant 5 Bcf/day deficit over 365 days equals 1,825 Bcf, but actual deficits must use monthly paths. Never silently clip inventory at zero or hide the resulting imbalance.

## Scenarios and price formation

Ship four named cases without assigning unsupported probabilities:

| Case | Purpose | Main assumptions |
|---|---|---|
| Public reference | Independent working baseline | Published data, latest forecast vintage, documented committed projects, normal weather |
| Letter replication | Reproduce the author's disclosed arithmetic | Stated supply ceiling and demand ramps, with unresolved definitions visibly flagged |
| Supply and demand relief | Test how scarcity could be avoided | Stronger supply, Canadian imports within transport limits, LNG/load delays, more non-gas generation |
| Tight supply and weather | Test adverse combinations | Weaker completions, project bottlenecks, higher utilization, adverse weather and outages |

Treat the letter's “at least 50% likely” inclusion rule separately from probability weighting. A threshold inclusion rule is neither an expected value nor a calibrated P50 system outcome. Later simulations may sample project dates and activity with correlated dependencies. Label scenario ranges as such until probabilities are supportable.

The MVP should take dated gas-price paths as explicit inputs and show the physical consequences. Distinguish a real contract forward curve from EIA's spot-price forecast and our analyst assumptions. Obtain a licensed forward curve only if existing rights support it; otherwise display “not available” and use labeled scenario paths.

The next stage can iterate price, production response, generation dispatch, LNG utilization, industrial demand, and imports until balances clear, subject to operational limits. Historical storage/price regressions can help calibrate ranges but cannot reliably extrapolate unprecedented shortages into a precise price. If the model cannot find a plausible clearing outcome, publish the unsatisfied volume and binding constraint.

## Regional power costs

For a gas generator, fuel cost is delivered gas price times heat rate. A $1/MMBtu increase at a 7 MMBtu/MWh heat rate increases fuel cost by $7/MWh, or 0.7 cents/kWh. That is a generator calculation; passing it fully into a miner's bill is an additional assumption.

Build two distinct layers:

1. **Market electricity:** regional gas benchmark/basis, marginal heat rate, non-gas dispatch, transmission congestion, scarcity, and other relevant market components.
2. **Miner delivered cost:** energy contract, fixed/spot exposure, renewal dates, transmission/distribution, demand charges, hosting components, taxes, hedges, and realized curtailment credits.

Model ERCOT first because it provides an actionable regional mining case, then PJM and the other regions material to covered assets. Global BTC calculations need additional regional and contract cohorts, including hydro and other low-cost supply. Geographic hashrate is only a starting prior; the [Cambridge mining-map methodology](https://ccaf.io/cbnsi/cbeci/mining_map/methodology) relies on sample extrapolation and location assumptions. Do not present an old map as today's measured gas exposure.

Calculate the fleet's effective power price using actual energy weights, which depend on hash share, efficiency, PUE, and operating hours. A simple hashrate-weighted tariff can misstate costs when fleet efficiencies differ. Unknown regions and contracts remain an explicit residual with a sensitivity range.

## How energy informs the BTC model

Implement the bridge in increasing levels of complexity.

### First release with fixed network assumptions

Pass a versioned monthly power-cost schedule into a new BTC scenario mode. Hold network hashrate, hardware mix, fees, and the chosen BTC price path fixed to isolate energy sensitivity. Produce electricity cost per issued coin, total cost, revenue per unit of hashrate, and margin. Keep the existing fixed 5-cent history and HK reference calculations available for comparison.

For an aggregate fleet whose effective efficiency already includes facility overhead:

```
electricity cost per issued BTC =
    network EH/s * 1,000,000 * effective J/TH * 24 / 1000
    * effective dollars/kWh / issued BTC per day
```

For heterogeneous cohorts, calculate and sum their individual energy bills before dividing by network issuance. Apply PUE once: the current ASIC fleet calculation can already include it. Keep fees as miner revenue rather than newly issued BTC, and label cost-per-issued-coin versus revenue breakeven explicitly. Future halving dates are estimates; the subsidy event is defined by block height.

Declare whether each hashrate input is installed capacity or realized active hashrate. Apply availability to installed capacity to derive active hashrate; never apply uptime a second time to an already realized series. The static bridge uses normal block production as an explicit assumption. It does not claim to simulate issuance during a sudden network shutdown.

Separate electricity, other operating expenses, depreciation/replacement capex, and required return. The legacy `electricity / 0.60` identity is suitable for an HK-comparable view, but applying it to a power-price shock raises all non-power costs proportionally too.

For forward horizons, forecast non-power costs in dollars per day and divide by that horizon's BTC output. Do not freeze a dollar-per-coin residual across halvings. The residual inferred from the current legacy model is an initial assumption, not independently measured overhead. Distinguish capital replacement expense from required return to avoid counting either twice.

For example, in the inspected September 27 snapshot, electricity is approximately $39,920 per coin and the legacy total is $66,534. Raising power from 5 to 6 cents increases electricity to roughly $47,904. Holding other costs fixed produces roughly $74,518 total, a 12% increase. The legacy gross-up produces roughly $79,840, a 20% increase. These are illustrative changes to cached model outputs, not current observed mining costs or BTC targets.

### Miner behavior and network response

Add cohort-level hardware efficiency, available hash capacity, contracts, uptime, power credits, and avoidable operating costs. Mines compare incremental mining revenue with the cost of running and the available curtailment alternative. Lost mining output and credited power must be computed for the same hours; the model cannot award both activities on the same capacity simultaneously.

Distinguish immediate response at fixed difficulty from the later adjustment. During a sudden hash decline, block production can slow until difficulty adjusts. Do not model instantaneous relief and simultaneously assume fixed normal issuance. Subsequently, surviving miners can earn more BTC per unit of hash, and investment or relocation can change the fleet again. Add this simulation after the static bridge is validated.

The display should show effects on exposed miners, the global fleet, and BTC as separate outputs. A US energy shock can hurt an exposed miner while benefiting a low-cost competitor. Scarce interconnection can also create an AI-hosting opportunity, but value it only with conversion capex, timing, contracts, and displaced mining cash flow. Do not count the same MW as both mining and AI capacity.

### Relationship to valuation

Retain the existing demand power law independently. Energy does not mechanically change its adoption exponent, and a higher mining cost does not establish a guaranteed price floor. Keep any 1.75-times-cost reference visibly identified as an inherited assumption. Do not automatically lift that implied price because gas is expensive.

All new outputs initially retain `in_base_irr: false`. Energy and BTC scenarios can support issuer research, but incorporation into a stock valuation requires issuer-specific evidence and the repository's existing decision process. BTC treasury holders, miners, and power landlords have different economic exposures.

## Data acquisition and maintenance

| Source | Inputs and cadence | Main limitation |
|---|---|---|
| [EIA Open Data](https://www.eia.gov/opendata/) and [natural gas tables](https://www.eia.gov/naturalgas/data.php) | Monthly production, demand, trade; weekly storage; selected prices and regional electricity data | Definitions, revisions, release lags, and geography require reconciliation |
| [EIA STEO](https://www.eia.gov/outlooks/steo/report/natgas.php) | Monthly independent near-term benchmark | A forecast, with a shorter horizon than the thesis |
| [EIA 860M](https://www.eia.gov/electricity/data/eia860m/) | Monthly operating, planned, and retired generator inventory | Preliminary and revisable; reported capacity is not a commitment |
| [EIA 923](https://www.eia.gov/electricity/data/eia923/index.php) | Plant generation, fuel use and costs | Lags, monthly sample coverage, and cogeneration allocation |
| [FERC LNG project register](https://www.ferc.gov/media/us-lng-export-terminals-existing-approved-not-yet-built-and-proposed) | Project stages and links to project evidence | Approval is not construction, financing, or utilization |
| [ERCOT load forecasts](https://www.ercot.com/gridinfo/load/forecast/index.html) and [PJM forecast process](https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process) | Load paths, weather cases, large-load adjustments | Submitted load can differ from realized or risk-adjusted load |
| [NOAA degree days](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/) | Daily observations and aggregated weather normalization | Preserve region, weights, and climatology vintage |
| Operator filings and investor materials | Quarterly production, costs, contracts, hedge books, asset/project details | Reported costs often use incompatible definitions; coverage is incomplete |
| State and provincial well records; optional licensed datasets | Well histories, acreage, infrastructure and remaining inventory | Large normalization effort; access, licensing, and coverage must be established |
| [Cambridge BTC methodology](https://ccaf.io/cbnsi/cbeci/methodology) and existing crypto sources | Network energy/efficiency comparisons and network history | Model estimates and sampled exposures are not measured mine tariffs |

Use public sources for the initial release. The letter names licensed Enverus, Yes Energy, Wood Mackenzie/Genscape and other data; this plan does not assume we have access or purchase any subscription. Before the full asset build, evaluate sample coverage and incremental value, then obtain actual vendor quotes and rights. Storage, licensing, research labor, and normalization will dominate that extension more than UI work.

Refresh weekly storage after the source release and publish the regular dashboard update through the existing World Model lane. Refresh structural balances and the near-term forecast monthly, issuer contracts quarterly, and project changes when new evidence arrives. The current workflow runs World Model weekly even though one step still says monthly. Add freshness-aware fetching rather than repeatedly downloading unchanged files. A daily pricing view is optional, not required for this structural model.

No ThetaData seat or IB Gateway is required for this design. Use public HTTPS data and approved existing research sources. Do not introduce any protected-resource polling or credential session.

## Implementation map and data contracts

The following new names are proposed, not existing components. Keep calculation separate from acquisition and from rendering.

| Component | Proposed responsibility |
|---|---|
| `_system/scripts/energy_model_config.json` | Units, geography, sources, scenario definitions, freshness limits, model version |
| `_system/reference/market-data/energy/` | Normalized time series and small source/vintage manifests |
| `_system/reference/energy/assets/` | Project, capacity, regional crosswalk, and miner contract registries |
| `_system/scripts/fetch_energy_panel.py` | Incremental public-source acquisition; cached/offline operation |
| `_system/scripts/energy_balance.py` | Pure monthly gas, storage, and regional flow calculations |
| `_system/scripts/power_cost_model.py` | Regional electricity scenarios and miner delivered-cost cohorts |
| `_system/scripts/energy_btc_bridge.py` | Convert energy scenarios into the existing BTC input contract |
| `_system/scripts/build_energy_model.py` | Assemble and validate scenario artifacts |
| `dashboard/data/energy_model.json` | Compact summary and time-series results for the same tab |
| `dashboard/data/energy_btc_bridge.json` | BTC power inputs, comparison outputs, coverage and provenance |
| `dashboard/energy-model-viz.js` | Focused energy renderer and scenario controls, called from the existing World Model section |
| Existing BTC builder and Insights loader/renderer | Optional bridge consumption and UI rendering |

Time-series records need period, unit, geography, observation date, publication date, retrieval time, provider series ID, actual/estimate/forecast status, revision vintage, and quality flags. Project records need stable asset IDs, aliases, owner, location, capacity basis, status, expected date range, sources, dependency IDs, and a duplicate-resolution record. Miner contracts need region/site, pricing basis, effective dates, covered energy, renewal assumptions, and evidence quality.

The bridge contract needs scenario ID, model version, source vintage, monthly dates, miner cohorts, effective dollars/kWh, operating-hours assumptions, PUE treatment, coverage share, staleness, and provenance. BTC outputs should carry both their crypto snapshot date and energy vintage. Reject incompatible units and date ranges. A missing or stale energy file must leave the legacy BTC view working and explicitly mark the energy overlay unavailable.

Store raw source snapshots privately or in the established data/document store with hashes; publish only compact derived data and permitted evidence links. Browser code must not contain source API keys or licensed raw datasets. Use atomic output replacement, last-known-good artifacts, bounded retries, and partial-source warnings. Never treat missing data as zero.

Suggested build dependency order: source refresh -> normalized energy data -> physical balance -> power scenarios -> BTC bridge -> BTC scenario build -> World Model/dashboard publication. Ensure both sides use the same scenario version. No circular dependency in the MVP; a later BTC-demand feedback loop must be explicit and converged.

Implement that dependency in the existing `_system/scripts/ci_rebuild_profile.py` lane. The World Model builder also attempts a companion BTC rebuild today; make both calls consume the same immutable snapshot or remove redundant work within the integration change. Keep the current static dashboard and Cloudflare publication path; this feature does not require a new backend, database, or hosting system.

Historical joins require particular care. The BTC builder has a time-varying power hook, but its matching behavior and all input cutoffs need an audit before monthly energy paths or historical replays use it. Join on the latest observation published by the evaluation date, with an explicit expiry; an `as_of` label alone does not prevent later observations from entering the calculation. Keep historical observations separate from forward scenario periods.

## Validation and acceptance

Validation should establish whether the model explains the physical system and whether its outputs are useful, rather than merely whether the interface renders.

1. **Units and conservation:** test Bcf/Mcf/MMcf, dollars/MWh versus dollars/kWh, MW/MWh, gas heat content, EH/PH/TH, and PUE. National and regional balances must close to numerical tolerance, with source statistical differences visible. Test the existing hashprice and breakeven conversions together.
2. **Historical reconstruction:** reconcile monthly supply, demand, trade, and storage changes to the same EIA definitions and vintage. Publish residuals and attribution rather than fitting them away with an unexplained adjustment.
3. **Forecast performance:** use rolling historical cutoffs and archived data vintages when available. Without historical vintages, label results retrospective fits. Compare storage and regional power-cost errors against seasonal and latest-public-forecast baselines; evaluate improvements on held-out periods.
4. **Stress episodes:** test cold weather, supply outages, LNG outages, hot summers, and high-price periods. Do not calibrate a model only to normal years. Inspect specific episodes such as 2021 Texas disruption and 2022 gas stress using contemporaneous inputs where available.
5. **Project reconciliation:** unique trains and generators; no duplicate data-center load; approved versus operating status; no supply before dependent infrastructure; probabilities and dates reproducible.
6. **Storage feasibility:** no unreported negative inventory, no flows beyond available injection/withdrawal/transport capacity, and no hidden deficit after clipping.
7. **BTC calibration:** verify power and mining expense against disclosed miner figures with consistent treatment of credits, hosting, depreciation, fees, and production. Check the illustrative cost sensitivity above. For the first release, disclose fixed network and uptime assumptions. In the later dynamic phase, validate immediate and adjusted-difficulty cases separately before displaying them.
8. **Regression and failure behavior:** legacy mode reproduces the accepted baseline except for separately documented unit corrections; bridge off/missing/stale behaves predictably; unknown inputs do not gain false precision; base IRR remains unchanged.
9. **User acceptance:** selecting a scenario updates energy and BTC panels consistently; every headline can be traced to assumptions and dated sources; desktop and narrow-screen layouts remain usable; normal Insights loading remains lightweight.

Before promoting energy-linked costs to a default view, require reconciled historical balances, no critical unit gaps, explicit exposure coverage, out-of-sample evidence against baselines, and at least one full monthly source-refresh cycle observed without silent drift. Set numerical forecast-error and coverage thresholds after measuring baseline performance and record them before evaluating the holdout sample.

## Delivery sequence

Indicative effort assumes one developer with part-time research support and accessible public data. These are planning ranges, not commitments; vendor procurement and manual contract research are excluded.

| Stage | Deliverable | Exit condition | Estimated working days |
|---|---|---|---|
| 0 | Source/units audit, source-claim ledger, fixed BTC baseline, panel wireframe | Reconcile definitions and correct the hashprice/breakeven pair with documented expected output changes | 2–3 |
| 1 | Public monthly US balance, scenario inputs, seasonal storage chart in the existing tab | Historical balance closes; forecast infeasibility is explicit; three counter-cases work | 5–8 |
| 2 | LNG/generation register, regional constraints, first regional power model | Capacity becomes actual flow/energy; duplicate load removed; delivered miner cost is separate | 5–8 |
| 3 | Static energy-to-BTC bridge, old/new cost comparison, contract sensitivities | Legacy mode works; power shock affects appropriate cost components; sources and coverage visible | 4–6 |
| 4 | Initial covered-issuer exposure table, historical validation, scheduled publication and QA | Failure recovery, vintage tracking, holdout results, and responsive UI accepted | 3–5 |

A useful gas dashboard should emerge after stages 0–1. The complete first integrated release is roughly four to six working weeks under those assumptions, with some UI and research work in parallel. Dynamic difficulty/curtailment modeling and comprehensive well/acreage reconstruction follow as separate extensions; a credible national asset model is a multi-month research effort.

Implement in small reviewable changes: data audit; national energy artifact; same-tab UI; regional power engine; BTC bridge; validation and publication. Do not combine unrelated repository cleanup or valuation changes with these releases.

## Investment research use and falsification

Begin issuer exposure with existing covered names and verified assets. Candidate groups include gas producers and royalties, constrained midstream assets, merchant generation, miners, BTC treasury owners, and owners of power/interconnection rights. Examples already present in the repository include EQT/EXE, KMI/WMB, CEG/VST, MARA/RIOT/CLSK/IREN, and FRMO/CMSG/MSTR; each still needs current entity and segment verification. Cross-border symbols require exchange-aware identity checks.

For producers, assess unhedged realized price, inventory quality, capital intensity, basis and takeaway. For midstream, separate contracted tariffs from throughput growth and expansion returns. For generators, distinguish merchant exposure from hedges and retail obligations. For miners, map actual contracts and renewal dates. For treasury owners, retain BTC price exposure separately from mining expense. Avoid importing the letter's winners and losers as automatic ratings.

Add a visible “What would change our view?” register: faster productivity/supply growth, lower LNG utilization, delayed load, new import capacity, more non-gas generation, improved storage, and stronger demand response. Each item needs a metric, threshold or condition, source, and review date. A useful model must identify when the scarcity thesis is weakening as clearly as when it is strengthening.

The recommended starting scope is therefore the public physical balance, the same-tab energy panel, and a static energy-to-BTC comparison. That directly tests the letter and improves an existing assumption while preserving a clear path to a much deeper asset model.
