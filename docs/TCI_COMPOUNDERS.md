# Core compounder research workflow

The canonical names and configurable hurdle bands are in
`_system/reference/core_compounders.json`. `TOI.V` is Topicus; `TOI` is a
different issuer. `BRK.B` is the registry key. Sleeve or stance changes are
separate owner decisions.

## Valuation and authority

`tci_return_bridge.py` uses the existing seven-year Lawrence cash-flow math
for diagnostic yield, per-share cash growth, multiple change, exact IRR and
the reconciliation gap. Ten years is a separate sensitivity. All returns
are percent per year; the gap is percentage points. Hohn's four-year persona
horizon is a business-fit lens, not a change to the contract horizon.

Non-full methods retain their approved issuer/NAV/payoff economics. Missing
cash, causal growth attribution, reinvestment funding or exit assumptions
remain gaps. A full-distribution legacy schedule cannot simultaneously fund
the acquisitions or reinvestment used to justify its growth.

The bridge is optional in `magis.valuation.v3`; old v2 records retain their
original validation requirements. Cards with the optional quality assessment
use version 3.0. Unmeasured quality remains unscored. Facts, calculated
inferences and qualitative opinions retain their source classification.

Every model migration is submitted through `agent_proposals.py`. The payload
includes a candidate ledger, quality assessment, dated cash schedule and
change log. It never writes human decisions or approved reviews. Before
promotion, the owner must reconcile primary source facts, fully diluted
ownership, funded reinvestment, causal cases, typed v3 moat falsifiers and
component proof. Prior valuation snapshots are preserved, including multiple
revisions on the same model date.

An approved dated-schedule method may opt into
`valuation_methodology.schedule_generator = "tci_return_bridge@1.0"`.
The universal contract then regenerates the schedule from the approved input
path. The existing proof, ownership, method and maturity checks still govern
publication. The generator does not approve itself. The required discount
return is an explicit underwriting input, distinct from the hurdle grid.

`human_decision → investment_committee → valuation_contract → legacy_reference`
remains the authority order. These changes introduce no broker, execution or
ThetaData access.

## Buy bands

`build_contract_pricing()` prices only eligible dated future economics.
Present values, blocked proof and screening models publish no bands.
The dashboard also rejects an old pricing file whose contract hash differs
from the current contract, and never presents legacy numeric grids as current.

The configured defaults are base 12%, base 15%, and the lower of base 18%
and bear 8%. Prices are derived from the existing schedule NPV function.
Royalty-watch rules corroborate bands; they do not define them.

The CLI now defaults to contract pricing:

```powershell
python _system/scripts/build_power_zone_pricing.py CME ICE
```

## Operating observations

Pure parsers and bounded fetchers live in `operating_kpis/`. CME uses issuer
releases on PR Newswire plus earnings 8-K RPC. ICE uses its public Q4 content
feed and statistics workbook. FNV, WPM, RGLD and TPL use filing exhibits;
PrairieSky uses its public IR posts. SEC requests use the existing polite
client. A blocked source preserves previous observations.

The one store remains
`_system/reference/market-data/operating_kpis/{TICKER}.json`.
Partial refreshes retain history. Revisions preserve the old observation.
Monthly, quarterly and annual periods remain distinct. Guidance has no YoY.
Ledger `operating:` sources use the observation period, not the date a script
last checked it, to determine staleness.

Import a dated mirror without executing any of its scripts or using the network:

```powershell
python _system/scripts/fetch_operating_kpis.py --import-mirror C:/path/to/magis_box_mirror
```

Mirror imports retain the source URL/document, original unit/key, content hash
and date. They are unverified inferences until primary-source reconciliation;
they never populate source-locked valuation facts. Known aliases map to one
series. Explicit unit/precision reconciliation preserves both originals;
unresolved conflicts retain the repo observation and queue review.

## Existing scheduled lanes

No schedule or manual dispatch surface is added:

- Nightly `full`: operating fetch → trends → core monitor/proposals → cards → dashboard.
- Power Zone Universe: contract → workbench → pricing → core monitor → existing dashboard refresh.
- Weekly World Model: ledger actuals, gates and fail/stale reviews → core monitor.
- Price-only contract refresh: pricing and core view update without new assumptions.

`refresh_core_compounders.py` writes derived state to
`_system/data/core_compounder_state.json`, proposals to the existing inbox,
review notes to the existing pending queue and alerts to fundamentals briefs.
The existing detail shards, L1 shards and context packs carry the derived view.
There is no additional dashboard or KPI store.

```powershell
python _system/scripts/refresh_core_compounders.py --write --propose
python _system/scripts/refresh_core_compounders.py --tickers CME --as-of 2026-10-23
```

The second command is read-only. Initial backfill establishes a quiet baseline.
Subsequent changes produce events. Unknown/stale quotes do not clear an active
band. IRR alerts compare canonical contract returns with the last alert anchor;
price/FCF/growth/multiple counterfactuals explain comparable full-model changes.
The default threshold is two percentage points and is configurable.

Briefs retain other desk items, acknowledge durable events, deduplicate crash
replays and keep overflow for later briefs. Alerts are research review requests.
Every item cites its source date and fact/inference/opinion classification.

The omission check carries filing/model lag, overdue calendars, source
disagreements, open questions, evidence gaps, persona dissents, unresolved
falsifiers and the latest-pointer adversarial source. Hohn-specific 13F history
and live Box digest posting state were absent from the supplied mirror. They
remain explicit gaps; the biotech specialist book is not a substitute, and no
external message is posted from an archived mirror.

## Validation

Run the core, pricing, contract, dashboard, operating-parser and governance
tests before review. The initial checkout already had stale dashboard bundles
and a CME latest-pointer hash mismatch. Rebuild derived views/pointers and
rerun validation; do not weaken schemas or proof rules to make them pass.

Implementation snapshot, 2026-10-24:

- All 37 names have monitoring views, pricing availability records and pending
  model proposals in the existing review queue.
- Thirteen existing full models support diagnostic return bridges; the other
  24 retain explicit input or method gaps. None of these changes approves a
  model. All 37 production buy-band outputs are withheld by current proof,
  model maturity or economic-basis requirements.
- Nine core issuers have operating observations: CBOE, MIAX, CME, ICE, FNV,
  WPM, RGLD, TPL and PSK.TO. CME and ICE live fetches succeeded. Remaining
  issuer-specific operating coverage is identified in each pending proposal.
- The repository's `scripts/tests` suite passed 1,387 tests with five skips;
  a subsequent focused valuation, pricing, operating, persona and UI run
  passed 63 tests and 21 subtests. Dashboard validation, all 37 agent-data
  checks, desk-brief validation, evidence-integrity ratchets and currency
  mismatch checks passed. Currency checks still report their existing
  unverifiable and non-companyfacts coverage gaps.
- Graph invariants report an unrelated stale podcast feed as a hard failure;
  the lens ratchet has no regressions. No baseline or freshness requirement
  was relaxed. Hohn 13F history and live Box digest posting remain missing
  inputs, documented in the derived views.

The changes are local and await review; no pull request has been opened.
