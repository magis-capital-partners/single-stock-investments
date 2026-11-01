# Aggregates screener expansion

Prepared October 22, 2026. Planning deliverable; the new data pipeline and KPIs below are not implemented by this document.

## What to build

Extend the existing Ideas → Screens → Aggregates screen into a comparable view of quarry economics, reserves, local demand and valuation. Keep one screener and one company detail drawer. The main question is: **which producers are increasing profit per ton, protecting their local resource base, and converting those profits into cash at an attractive price?**

Start with unit economics and data correctness. Geographic mapping and more elaborate scoring come after those inputs are dependable.

## What already exists

The current implementation is `_system/scripts/build_rock_aggregates_screener.py`, its regression suite is `_system/scripts/test_rock_aggregates_screener.py`, and the screen is rendered by `renderWatchlistRockBody()` in `dashboard/index.html`. The seed list is `_system/reference/market-data/screens/rock_aggregates_seed.csv`.

The published file contains 11 companies: VMC, MLM, CRH, AMRZ, KNF, ACA, GVA, ROAD, EXP, USLM and CX. Ten currently have basic SEC coverage; CX is marked `pending_sec`. It already calculates revenue, an operating-income-plus-DD&A EBITDA proxy, FCF conversion, capex intensity, net debt/EBITDA, a simplified ROIC, EV/EBITDA and goodwill/intangibles relative to equity. FCF yield and market capitalization exist in the data but are not main table columns.

Every company's `reserve_life_years` and `cash_gross_profit_per_ton` is currently null. There are no comparable operating histories, segment mix measures, price/volume bridges, geography filters or source-linked metric drilldowns. The only industry filter is “aggregates only.” Its underlying `is_pure_rock` flag includes integrated producers such as GVA, ACA and CRH, so it does not actually mean pure play.

Reuse the existing builder, seed registry, watchlist action, filing inventory, market inputs, `aggregates_infrastructure` theme and company research views. Add filing-derived operations alongside SEC financial facts; the specialized KPIs cannot be recovered from generic companyfacts alone.

## Priority 0: make the existing comparisons reliable

| Issue in the current code | Required change |
|---|---|
| Flow facts are selected independently by their latest annual dates | Match revenue, operating income, DD&A, CFO and capex to the same fiscal period before calculating a ratio. Preserve the existing annual-duration checks. |
| Current equity/debt/cash are combined with FY operating income in ROIC | Label the existing measure as a simplified proxy. Add period-matched NOPAT / average invested capital when beginning and ending balances exist. |
| Missing cash can become zero in net debt; missing goodwill/intangibles can become zero | Preserve nulls unless an explicit filing establishes zero. Mark partial balances as incomplete. |
| Debt tags include concepts with different current/noncurrent coverage | Store concept scope and reconcile total debt without counting the current portion twice. Separate debt, leases, restricted cash and noncontrolling interests. |
| Price retrieval discards the quote timestamp | Retain quote time, currency, price basis and share-count date. Define an explicit close valuation date and flag mismatched inputs. |
| Latest share counts are assumed to match the traded instrument | Validate issuer, listing, share class, ADR/ADS multiplier and corporate actions, especially for CX and historical CRH data. Never assume a 1:1 ADS ratio. |
| An EBITDA proxy is presented alongside very different business mixes | Identify proxy versus issuer-reported adjusted EBITDA. Keep corporate and aggregates-segment metrics separate. |
| “Pure rock” includes integrated construction businesses | Replace with explicit peer groups: aggregates focused, integrated materials, contractors/asphalt, cement, and lime. Store aggregates revenue/profit mix where disclosed. |

Acceptance: no ratio uses incompatible fiscal periods, currencies, units or segment boundaries; missing facts remain missing; existing regression fixtures still pass.

## Priority 1: the operating KPIs that matter most

Backfill at least five fiscal years and twelve quarters where disclosed. Show annual and latest-quarter views first; admit TTM only after four non-overlapping comparable quarters can be assembled. Use year-over-year quarterly comparisons because shipments are seasonal.

| KPI | Definition and comparability rule | Main use |
|---|---|---|
| Aggregates shipments | Million short tons, with source unit retained; keep production, total sales, external sales and internal transfers distinct | Volume and operating leverage |
| Organic shipment growth | Same perimeter year-over-year; use issuer-disclosed same-store/organic growth or an evidenced acquisition/disposal bridge | Separate demand from purchased growth |
| Freight-adjusted selling price / ton | Aggregates revenue excluding freight/pass-throughs divided by matching saleable tons, only when numerator and denominator reconcile | Pricing power |
| Organic price growth | Disclosed like-for-like price growth with geography/product mix basis | Underlying pricing versus favorable mix |
| Cash gross profit / ton | Issuer-reported segment cash gross profit / matching shipment tons; retain the issuer's non-GAAP reconciliation | Quarry profitability |
| Cash operating cost / ton | Freight-adjusted price less comparable cash gross profit / ton, where both measures share the same basis | Cost discipline |
| Price less cost change | Change in dollars per ton of comparable price minus change in dollars per ton of comparable cash cost | Whether pricing exceeds cost inflation |
| Aggregates segment EBITDA and margin | Reported segment measure with corporate allocations identified; do not substitute consolidated EBITDA | Compare actual rock economics |
| Incremental margin | Change in comparable segment profit / change in segment revenue; suppress when revenue change is zero or the denominator is too small for interpretation | Operating leverage |
| Organic versus acquired profit growth | Disclosed acquisition/divestiture/FX contributions separated from continuing operations; residuals remain unexplained | Quality of growth |

Vulcan's FY2025 release explicitly supplies shipments, freight-adjusted selling price, cash gross profit per ton and a unit cash cost definition. That is a practical first extraction fixture, not a definition to impose on every issuer. [Primary source](https://www.vulcanmaterials.com/news-and-events/press-releases/2026/vulcan-reports-fourth-quarter-and-full-year-2025-results-122499).

Never divide consolidated revenue or consolidated EBITDA by aggregates tons for an integrated producer. Never equate reported price growth with a pure price effect when mix changes are unresolved. Keep “reported” and “derived” visible in the detail drawer.

## Priority 2: reserves and the local moat

| KPI or evidence | Definition / source | Limits |
|---|---|---|
| Proven and probable reserves | Filing reserve tables by material and location, with tons and reporting basis | Keep resource estimates, reserves, owned deposits and leased deposits separate |
| Reserve life | Comparable reserves / annual production from the same perimeter; prefer an issuer-reported figure and show its definition | Production is not necessarily shipments; company-wide life is not a permit term |
| Permitted reserve life | Only an explicit disclosure of permitted, economically accessible reserves and relevant restrictions | Never rename geological reserve life as permitted life |
| Reserve replacement | Disclosed additions versus depletion; identify acquired reserves and revisions | A balance change alone is not an organic replacement rate |
| Quarry network | Operating quarries, processing sites, terminals, rail/barge access, lease status and disclosed capacities | Counts need an active-site definition; do not mix plants and quarries |
| Geographic concentration | Shipment/revenue exposure by state/region where disclosed; top markets and exposure to public infrastructure | Site-count weights are an explicitly labeled fallback, not revenue weights |
| Local competitive structure | Verified competing sites, distances and transport links around named assets | A map is a screening aid, not proof of pricing power or market share |
| Permitting and environmental commitments | Disclosed permit expiries, reclamation/asset retirement obligations, litigation and expansion constraints | Capture dated events and conditions rather than a subjective regulatory score |

Use 10-K Item 2, mining/property exhibits, technical report summaries where applicable, issuer site lists and state permitting records. Inspect [Martin Marietta annual reports](https://ir.martinmarietta.com/reports-filings/annual-reports-and-proxies) and [Knife River annual reports](https://investors.kniferiver.com/financials/annual-reports/default.aspx) for extraction coverage before promising a field for the whole universe.

Replace the current blanket “25-mile” economic-haul assertion with location-specific evidence. Truck, rail and barge markets have different delivered economics. If delivered-price or freight data is absent, show that limit explicitly.

## Priority 3: cash, capital allocation and valuation

| Addition | Calculation / presentation |
|---|---|
| FCF yield | Expose the existing CFO less capex / market-cap metric, with separate financial and valuation dates |
| Maintenance and growth capex | Disclosed amounts and definitions; do not estimate maintenance capex as depreciation |
| Maintenance FCF | CFO minus maintenance capex only when the split is evidenced; show total-capex FCF beside it |
| Cash conversion history | Annual and TTM FCF/EBITDA plus working-capital movements and unusual tax items |
| ROIC / incremental ROIC | Period-matched NOPAT and average invested capital; incremental return only with a usable multi-year capital bridge |
| Acquisition intensity | Acquisition cash outlays / operating cash flow; distinguish growth capex, reserve purchases and M&A |
| Deal quality | Purchase price, disclosed acquired EBITDA, reserves and integration milestones; no invented deal multiple |
| Financial resilience | Net debt/EBITDA, debt maturities, fixed/floating mix, interest coverage and liquidity where disclosed |
| Shareholder returns | Link the existing buyback record and dividends; keep gross repurchases separate from actual net share reduction |
| Valuation history | EV/EBITDA and FCF yield versus the company's own history and compatible peers; identify FY, TTM and guidance bases |
| Through-cycle view | Five-year volume, price, margin and cash history; optional scenario controls after actual-history coverage is established |

Knife River's FY2025 release separates maintenance/improvement spending from organic growth and acquisitions. Use such issuer disclosures directly rather than applying a common maintenance percentage to every company. [Primary source](https://investors.kniferiver.com/news/news-details/2026/Knife-River-Corporation-Reports-Fourth-Quarter-and-Full-Year-2025-Financial-Results/default.aspx).

Do not attach total corporate enterprise value to aggregates segment EBITDA without a documented sum-of-the-parts bridge. No earnings uplift from buybacks is automatically added to base returns.

## Priority 4: demand context tied to the footprint

Reuse the existing `aggregates_infrastructure` theme rather than creating a second macro panel. Link its observations to each company's disclosed regions.

- Public demand: FHWA/state DOT obligations, awards and lettings; distinguish funding authority, obligated funds and actual spending.
- Private demand: Census state building permits, construction spending and relevant nonresidential categories; identify monthly/quarterly cadence and revisions.
- Industry context: USGS aggregates shipments and pricing series with their publication dates, material categories and geographic coverage.
- Integrated producers: awarded backlog, expected conversion period and disclosed bid margins for KNF/GVA/ROAD; contracting backlog is not an aggregates order book.
- Weather: optional NOAA precipitation/workday disruption context for heavily exposed regions; do not attribute a volume decline to weather without evidence.

Use official provider documentation and release calendars during implementation. State exposure must be disclosed or transparently estimated before calculating a weighted demand indicator. Keep this contextual until its incremental value is demonstrated.

## Data contract and ingestion

Every new observation should carry `issuer_id`, `ticker`, `metric`, `value`, `unit`, `currency`, `period_start`, `period_end`, `period_type`, `filed_at`/`published_at`, `retrieved_at`, `business_segment`, `geography`, `product`, `freight_basis`, `sales_scope`, `perimeter_basis`, `status`, `confidence`, `source_url`, filing accession/document reference, table/page locator, and extraction/formula version. Derived metrics point to their exact inputs.

Status distinguishes reported, derived, unavailable, not disclosed, stale and conflicting. Preserve restated observations with effective/publication dates instead of overwriting history. Convert metric tonnes to short tons only with explicit unit metadata, and use the matching $/ton conversion. Preserve original currencies and do not combine reporting currencies without dated FX evidence.

1. Discover new 10-K/10-Q/20-F filings and issuer earnings releases through the existing evidence pipeline.
2. Reuse downloaded filing artifacts and source inventories; cache by accession and document hash.
3. Extract deterministic table candidates first. Model-assisted extraction may propose candidates with source spans; it cannot silently turn unsupported text into verified numbers.
4. Normalize each issuer through a small metric-definition adapter. Unsupported issuer definitions remain separate.
5. Validate period alignment, unit scaling, non-GAAP reconciliations, shipment scopes and prior-period continuity.
6. Publish a compact screener summary plus per-company history/evidence shards atomically; retain the last validated snapshot if publication fails.
7. Refresh prices after the close; refresh fundamentals on filings and operations on earnings releases. Show observation dates separately from the screener build timestamp.

Suggested additions: `aggregates_facts.py` for normalization/validation; `aggregates_operating_metrics.py` for formulas; an issuer-adapter configuration; an evidence ledger under `_system/data/aggregates/`; compact detail shards under `dashboard/data/aggregates/`; and an extracted `dashboard/aggregates-viz.js`/stylesheet. Continue publishing the existing screener filename for route compatibility.

## UI and filtering

Keep the current route. Present one compact screener with a short description, a visible observation-period selector, search, peer-group filter and column presets. Avoid another standalone dashboard tab.

The default overview should have roughly nine columns: company/peer group, EV/EBITDA, FCF yield, freight-adjusted price growth, organic volume growth, cash gross profit/ton, year-over-year profit/ton change, net debt/EBITDA, and evidence status. Reserve life replaces an overview column only once coverage is useful; otherwise it belongs in the detail view. Make columns user-selectable rather than showing every KPI at once.

Column presets: Overview, Unit economics, Reserves and markets, Cash and capital. A company drawer contains operating history, valuation/capital allocation, footprint/reserves and sources. Keep VMC/MLM visible as selectable benchmarks even when already held. Reuse existing watchlist and company-research links.

Suggested presets, with user-adjustable thresholds:

| Preset | Logic |
|---|---|
| Aggregates peers | Aggregates-focused and integrated materials, explicitly labeled; require verified operating evidence for KPI ranking |
| Pricing power | Positive comparable organic price growth and positive cash profit/ton change, same year-over-year period |
| Improving economics | Positive price-minus-cost dollar spread and improving segment profit/ton; organic volume displayed alongside |
| Cash and resilience | Positive FCF, acceptable user-selected leverage and verified balances |
| Value to investigate | Lower compatible EV/EBITDA with positive cash generation; display missing operating evidence and business-mix limits |
| Reserve strength | Verified disclosed/derived reserve life above a user-selected threshold; preserve the production and permission basis |
| Research gaps | Missing/conflicting observations with a concrete source/task to resolve them |

Nulls never pass numeric thresholds and always sort last. A missing value is not a zero, an industry minimum or a low-quality company. Filters show their definitions, matched count and excluded-for-missing-data count. Start with transparent metric sorting; postpone a composite score until completeness and comparability are good enough to justify weights.

## Delivery sequence and acceptance

| Milestone | Scope | Completion evidence |
|---|---|---|
| 1. Financial contract | Period/currency alignment, null propagation, debt scope, identity, quote dates, peer labels | Regression fixtures cover mismatched years, overlapping debt, missing cash and ADS units |
| 2. Core operating history | VMC and MLM first; KNF and ACA next; all available five-year/twelve-quarter history | Each supported price/volume/profit observation links to an exact primary-source location; manual reconciliation of a full FY and two quarters per issuer |
| 3. Useful default screen | Search, comparable sorting, period selector, presets, company evidence/history drawer | Desktop/mobile browser checks; keyboard use; nulls and unavailable sources cannot rank as zero |
| 4. Broader peers and reserves | CRH/AMRZ, then integrated/adjacent producers; reserve and footprint disclosures | Report metric coverage by company; financial versus operating segment differences explicit; CX either supported or visibly pending |
| 5. Local demand and history | Official contextual data, disclosed geographic weights, valuation history | Reproducible vintages, release dates, methodology and source cadence; no hidden forward fill |

Prioritize complete, reconciled operating coverage for the core companies over superficial coverage of more tickers. The first useful release should answer whether price and unit profit are improving and whether the stock is reasonably valued; reserves, maps and contextual demand then explain durability.

## Source references checked for this plan

- [Vulcan FY2025 results and operating KPI definitions](https://www.vulcanmaterials.com/news-and-events/press-releases/2026/vulcan-reports-fourth-quarter-and-full-year-2025-results-122499).
- [Knife River FY2025 results, segment discussion and capital allocation](https://investors.kniferiver.com/news/news-details/2026/Knife-River-Corporation-Reports-Fourth-Quarter-and-Full-Year-2025-Financial-Results/default.aspx).
- [Martin Marietta annual-report inventory](https://ir.martinmarietta.com/reports-filings/annual-reports-and-proxies).
- [Knife River annual-report inventory](https://investors.kniferiver.com/financials/annual-reports/default.aspx).

These verify that the proposed extraction has primary-source starting points. They are not a claim that every proposed KPI is disclosed by every issuer. All screen thresholds above are proposed product defaults, not investment recommendations.
