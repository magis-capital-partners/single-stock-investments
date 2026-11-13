# Commodity evidence desk

The World Model retains its four commodity scenario cards and adds an evidence
desk covering oil, gas, power, copper, gold and silver. Company pages attach
reconciled SJT and WPM sensitivities. Everything is research context:
`in_base_irr=false`, `valuation_authority=none`. No approved valuation is updated.

## What changed

* Native monthly EIA STEO supply, demand, basin production, regional working gas,
  oil inventories, benchmark spreads and power-hub prices replace annual-only
  visibility. Reviewed November 2026 oil/gas anchors also refresh the existing
  engines. Forecast extensions retain their assumption labels.
* WGC quarterly gold demand is captured by sector, including Q3 2026 and revisions
  to preceding quarters. ETF flows, official buying, jewelry, recycling, mine
  production and the OTC residual have distinct roles. Monetary price sensitivities
  remain assumptions; a historical residual is not evidence of a causal premium.
  The Q3 above-ground stock anchor is refreshed to 224,200 tonnes and its dated
  quarter-end determines the intervening time in the stock projection.
* ERCOT's public native-load archive supplies measured representative profiles by
  month, local hour ending, weekday/weekend and weather zone. Source-hour counts
  retain settlement/DST weighting. The power calculator combines measured load
  with explicitly entered supply, heat-rate, scarcity and contract assumptions.
  It does not claim to reproduce nodal prices without renewables/congestion data.
  Dispatch uses every native settlement hour of the latest source month rather
  than profile averages. Local hour-ending labels and repeated DST occurrences
  are retained, preserving peak demand and scarcity effects.
* Copper keeps concentrate and refined balances separate. Matched preliminary
  ICSG refined balances and dated Cochilco exchange holdings retain their original
  scope. Mine/project calculations support throughput, grade, recovery, ramp,
  ownership and mine life. Smelter intake, SX-EW, TC/RC and available stocks stay
  unknown when not evidenced. Assumed prices cause scrap response in the existing
  engine; a refined surplus does not independently generate a price target.
* Silver PV demand has explicit production, technology share, intensity and net
  material yield calculations. The default equivalent intensity reconciles to
  the published survey anchor; it is not measured TOPCon/HJT engineering data.
  Production and installation timing are separate. ETP absorption is deducted
  once. Gross holdings, ETF ownership, warrants and available inventory remain
  distinct. The gold/silver ratio is an assumed comparator.
* Gas withdrawal/injection limits depend on working inventory. LNG imports use
  named columns, validate Bcf/day and location, distinguish in-service/commercial
  dates, and retain operators. LNG capacity paths show delay, ramp, utilization
  and fuel. Regional and asset paths remain cross-checks, preventing a second
  addition to the national balance.

## Evidence and publication

`commodity_observations.py` defines full observation identities, original-source
hashes, units/currency, economic period, vintage, publication, retrieval, review
and conservative `known_at`. Unknown publication dates remain null. Retrieval
dates establish availability, not an invented historical release date. Packed
datasets normalize repeated provenance while preserving every observation.

Readiness weights reflect decision importance. A current source with old economic
observations cannot earn freshness. Assumptions, changed unreviewed sources and
retained data after a failed request do not earn observed coverage. Core and
optional inputs are separate. Source changes compare matched observations, not
HTML hashes alone. The served model ID covers calculated results and company
terms; the reader displays its ID and fetch time. Failure retains the last
validated publication with a visible failed-refresh status.

`fetch_commodity_resolution.py` resolves the latest published EIA workbook, WGC
quarterly report and ERCOT archive. Parser checks and accounting reconcile each
capture before publication. It never buys or substitutes licensed data.
`review_commodity_references.py` is the separate explicit step that promotes
validated publisher tables to reviewed scenario anchors; normal collection does
not change scenario coefficients. EIA spot workbooks supply daily oil history
directly when FRED is unavailable. The broader dollar and real-yield histories
remain visibly unavailable if their source cannot be fetched.

The published JSON and filtered downloads retain original-source links and hashes.
Exact captured bytes, physical vintages and model vintages are preserved in the
private commodity object store and research vault. They are restored before the
next scheduled build. Annual/quarterly data never become purported monthly
observations through interpolation.

## Company reconciliation

SJT's August 2026 field revenue/costs and October declaration reconcile to its
reported gross deficit and 75% net profits interest. Gas represents **96.29%** of
reported field revenue. Scenarios apply field costs before NPI and pay accumulated
costs before trust reserve/debt hurdles. Future distributions are withheld because
future operator capital, credit interest and reserve timing are unknown.

WPM's Q3 2026 attributable gold/silver **sales** map **97.28%** of reported revenue.
Sales are separate from production. Cash purchase costs reconcile to reported
cash operating margin; the difference to reported operating cash is explicit.
Other metals are an identified residual. Historical cash costs held fixed are a
named sensitivity, not a projection of every streaming agreement. Asset payment
formulas, escalation, future tax/working capital and growth funding remain unknown.

Revenue sensitivity coverage does not equal verified future contract cash-flow
coverage. The latter remains 0% for these portfolio-level pilot projections. The
generic asset calculator supports ownership, basis/quality, transport, hedges, FX,
producer/royalty/stream terms, variable/fixed costs, sustaining capital, tax and
working capital. Missing contract/cost inputs return no cash-flow estimate.

## Detailed operating cases

`commodity_operating_cases.py` accepts a named case with separately declared
`evidence`, `assumptions`, `in_base_irr=false` and an explicit as-of date. It runs:

* Regional directed pipeline capacity/outage and inventory-dependent gas storage.
* Weather-normalized demand with labeled HDD/CDD coefficients.
* Representative-hour dispatch, generation availability, scarcity and contracts.
* Data-center milestones: proposed, funded, connected and operating. Proposed MW
  never become operating demand, and incremental national load requires a baseline
  reconciliation.
* Refinery product yields, explicit volume gain, imports/exports/use and inventory.
* Copper concentrate/refined balances and dated mine/project output.
* Gold absorption and stock transfers, silver technology demand and warehouse scope.
* Comparable production-weighted cost samples and individual company contracts.
* Canonical joint shocks. Repeating a driver fails; copper/silver coproduct losses
  and gas/power fuel effects propagate once. No probability is assigned.

Reviewed cases can be supplied in
`_system/reference/market-data/commodities/operating_cases.json` under `cases` and
are included in the published model. No invented asset inventory is installed.
For an individual case:

```powershell
python _system/scripts/commodity_operating_cases.py --case path/to/case.json --as-of 2026-11-13 --output path/to/result.json
```

Cost output separates cash, sustaining, new-project and required-return costs;
currencies, periods and byproduct bases do not mix. Negative costs from byproduct
credits remain valid. Sample weights are disclosed production, including the
publisher's ownership exceptions. Global coverage stays unknown without a matched
denominator; sample quantiles are never labeled global percentiles.

## Forecast standards and remaining evidence

Captured monthly vintages generate rolling origins at 1/3/6/12 months, with
no-change and seasonal baselines, separate units/metrics and shock-regime scores.
Archived EIA publisher price forecasts retain their existing benchmark evaluation.
New structural models cannot acquire historical skill by assigning today's
retrieval date to old observations. New captures accumulate future out-of-sample
evidence. Actuals use latest revised outcomes, explicitly labeled; overlapping
horizons are not independent. Calibrated probabilities/intervals and structural
price skill remain unvalidated. Conservation tests are accounting tests.

The UI exposes remaining blockers instead of presenting them as completed data:

* Full matched concentrate/smelter intake, TC/RC, unreported stock bounds and free
  physical inventory; detailed ICSG/LME data may require approved entitlements.
* Aligned hourly renewables, outages, congestion and verified customer contracts.
* Measured PV technology production/intensity and future project milestones.
* Complete issuer contract terms and future cost/capital/tax/working-capital paths.
* Historical licensed futures settlements for the futures benchmark.

The additional-commodity audit matches iron ore/pellets, met coal, timber/lumber
and uranium names against the research registry. Registry membership is not a
funded holding. Priority by capital requires current reconciled Flex positions;
no broker socket or market-data terminal is used.

## Refresh and verification

```powershell
python _system/scripts/fetch_commodity_resolution.py
python _system/scripts/review_commodity_references.py
python _system/scripts/refresh_energy_model.py
python _system/scripts/refresh_commodity_models.py
python _system/scripts/validate_commodity_models.py
python -m pytest -q _system/scripts/tests/test_commodity_resolution.py _system/scripts/tests/test_commodity_models.py _system/scripts/tests/test_commodity_inputs.py _system/scripts/tests/test_commodity_free_sources.py _system/scripts/tests/test_energy_model.py
node --test _system/scripts/tests/test_commodity_resolution_ui.cjs _system/scripts/tests/test_research_desk_ui.cjs
```

The normal weekly lane already calls the refreshers. Its optional mode permits
other research outputs to publish after a commodity failure; the commodity
payload retains its failure/partial status, core gaps and original dates. The
dedicated research workflow runs the new accounting, lineage, response and UI
contracts before merge.
