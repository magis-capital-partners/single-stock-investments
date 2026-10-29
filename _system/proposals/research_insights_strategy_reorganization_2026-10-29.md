# Research Insights and Strategy Reorganization Plan

**Date:** 2026-10-29
**Status:** Dashboard migration, research engine, source audit, and frozen paper infrastructure implemented. Empirical validation remains gated on audited historical inputs and future independent observations.
**Scope:** Research Memory and Ticker Insights simplification, a dedicated Biotech Quant strategy, and separation of Systematic Shorts from fundamental short research.

The dashboard will give systematic investment programs their own homes under Strategies. Ticker Insights will prioritize material company developments, and Research Memory will explain current claims and their evidence. Biotech Quant moves out of Research Memory in full. The quantitative short research and backtest workspace moves out of Short Ideas; fundamental short research stays in its current location.

## Strategy Navigation

Final order, left to right:

1. SPX 0DTE
2. LS Algo
3. Systematic Shorts
4. Darwin CC
5. Biotech Quant

Biotech Quant is immediately to the right of Darwin CC. The additional Systematic Shorts tab is immediately to its left. These two additions produce five strategies in total.

| Workspace | Canonical entry route | Purpose |
|---|---|---|
| Systematic Shorts | `#/strategies/systematic-shorts/overview` | Quantitative signals, registered rules, backtests, portfolio simulation, execution assumptions, and forward paper evidence |
| Biotech Quant | `#/strategies/biotech-quant/overview` | Sector factor strategy, ranked universe, portfolio construction, validation, and supporting research |
| Fundamental Shorts | Existing `#/ideas/short-alpha` | Qualitative frameworks, company theses, adversarial research, discretionary decisions, and actual short-position records |
| Research Memory | Existing `#/insights/memory` | General company claims, supporting evidence, conflicts, and review work |
| Ticker Insights | Existing `#/insights/tickers` | Material developments and unresolved company research issues |

## Content Ownership

### Move the Entire Biotech Quant Workspace

Move the methodology library, factor scoreboard, methodology claims, knowledge changes, specialist fund registry, quant universe and filters, ranked signals, long and short candidate lists, paper portfolio, and biotech quant ticker queue into Biotech Quant.

Use six views within the strategy:

| View | Default content |
|---|---|
| Overview | Strategy hypothesis, research or paper status, material changes, input freshness, and validation progress |
| Signals | Ranked biotech universe, factor coverage, long and short candidates, and company detail |
| Portfolio | Proposed weights, rebalance changes, exposure, turnover, and paper portfolio history |
| Backtest | Registered experiments, benchmark comparisons, costs, sensitivity, and out-of-sample results |
| Risk and Data | Concentration, liquidity, cash runway, catalyst exposure, borrow assumptions, freshness, and missing inputs |
| Research | Source library, factor definitions, specialist registry, and methodology evidence |

Remove the Biotech subtab and quant-specific counters, filters, and tables from Research Memory. Replace full duplicate strategy panels on company pages with a small strategy link and relevant context. Individual biotech company claims remain searchable in the general evidence index and company detail; the strategy is the sole home of the quant workspace. Preserve source files and stable evidence IDs.

### Move Systematic Short Research

Move the complete backtest workspace, including the current short profit program and earlier reverse-split portfolio and execution studies. Preserve the existing financing, listing-stress, reverse-split, net-edge, capacity, borrow, cost, corporate-action, and forward-monitoring work.

| Move to Systematic Shorts | Keep under Fundamental Shorts |
|---|---|
| Quant screens and factor rankings used to select systematic candidates | Qualitative framework board and discretionary thesis development |
| Registered hypotheses, mechanical entry and exit rules, and experiment versions | Company research, fraud or accounting concerns, and adversarial analysis |
| Historical event datasets and quantitative financing or issuance signals | Company-specific issuance evidence needed to understand an individual thesis |
| Returns, equity curves, drawdowns, portfolio replays, and attribution | Actual discretionary short-position ledger, notes, and decisions |
| Systematic execution, capacity, settlement, borrow, and liability simulations | Position-level borrow and risk context needed for an actual fundamental position |
| Frozen forward policies, paper outcomes, abstentions, and systematic event ledgers | Human investment review and decisions |

Use Overview, Signals, Backtest, Portfolio and Risk, Forward Paper, and Research and Data views. Place the existing experiment families and earlier versions within these views rather than creating another main navigation tab for each historical version.

Do not move a component solely because its filename contains `fundamental` or `framework`. For example, the backtest's historical fundamental-feature study and `ShortFrameworkViz` protocol workspace belong with Systematic Shorts; the qualitative framework board in `ShortAlphaViz` stays with Short Ideas. A data field can support both workspaces through a shared source and a small company reference without duplicating the full screen.

Remove the embedded backtest teaser, systematic tables, and backtest subnavigation from the fundamental page. Retain a simple link to the systematic strategy. Keep the biotech short sleeve inside Biotech Quant; it can reuse common cost and borrow tools without becoming a duplicate Systematic Shorts portfolio.

## Resources Available for Biotech Strategy Development

The following describes saved local artifacts inspected on 2026-10-29. Generation timestamps describe builds, not necessarily the observation date or the date information became public.

| Resource | Current evidence | Strategy use and work required |
|---|---|---|
| Verdad research library | Primary paper, local text, synthesis, factor specification, secondary digests, and methodology proposals | Specify testable economic hypotheses. External reported returns remain source research, separate from our results. |
| Specialist ownership pipeline | Latest signals cover 235 biotech issuers, including 24 marked in the book; 20 specialist funds; signal quarter 2026Q2 | Reuse holdings and fund classification. Reconstruct historical fund membership and filing availability before testing. |
| Historical specialist records | Full-table dated records currently show 2026Q1 and 2026Q2; additional latest and cached files are not extra quarters | Extend history and audit completeness. Two quarters cannot support a credible long-horizon strategy evaluation. |
| Broader 13F archive | 2,163 full-book CSV files under `ownership/13f/positions/` across the broader manager archive | Audit manager overlap, periods, acceptance clocks, and security mapping before treating these files as usable biotech history. |
| Spend value | 229 of 235 current signal rows have spend-value fields | Audit filing periods, spend definition, capital structure, and prices available at each historical decision date. |
| Insider scores | Score fields are populated for 235 current signal rows | Distinguish actual purchases, zero eligible purchases, incomplete observation windows, and missing source coverage. |
| Short interest | Current signal fields populated for 215 of 235 issuers; source artifact built 2026-07-09 | Verify settlement and publication dates, refresh freshness, and reconstruct historical releases. Short interest is distinct from borrow availability. |
| Clinical profiles and peer momentum | Clinical artifact is marked partial; none of the 235 current signal rows has `peer_momentum_12m` | Develop and validate peer returns from historical clinical descriptions. Do not present the factor as populated because the specification calls it live. |
| Composite and paper book | Composite scores exist; saved 25-long and 25-short list is dated 2026-07-09 | Treat the list as candidate selection. Add weights, capital, dated rebalances, returns, costs, and a full portfolio ledger. |
| Existing short research infrastructure | Event clocks, SEC financial data, corporate-action handling, price caches, cost models, borrow indications, and forward protocols | Reuse appropriate components after checking biotech identity, market coverage, licensing, and period coverage. |
| Company research and broader source library | Deep dives, filings, letters, podcasts, and adversarial claims | Explain signals and review failures. Historical discretionary annotations need their own availability clocks if tested as features. |

The source specification's `live` label currently indicates an implemented pipeline component. The new UI must separately describe implementation, coverage, freshness, historical validation, paper observation, and any future trading status.

## Biotech Strategy Research Plan

### Define the Mandate and Universe

Start with the hypothesis that specialist ownership and spend-based value can improve diversified biotech selection. Treat insider buying and clinical peer momentum as separately testable additions. Preserve the existing ban on using P/E, EV/EBIT, or the company's own momentum as substitutes for the specified biotech factors.

Define the investable universe independently of specialist holdings. Include eligible biotech companies with zero specialist ownership so the strategy can test weak-consensus shorts and compare owned versus unowned companies. Classify issuers and fund specialists using information available at the time. Deduplicate affiliated managers and share classes according to a frozen rule.

Document listing, minimum liquidity, issuer size, price, corporate-action, and cash-runway rules. Select thresholds in the research protocol before examining validation results. Preserve delisted, acquired, failed, and renamed companies in historical cohorts; current holdings cannot define the historical universe.

### Build History with Availability Dates

Create a coverage matrix by quarter, issuer, and factor. Target at least five years spanning different biotech conditions where approved data permits; report the history actually available. A limited recent dataset can support forward paper research while the longer study remains incomplete.

Store observation period, publication or SEC acceptance time, first usable trading session, source identity, amendment vintage, and missing-data reason. Use 13F holdings only after the actual filing became available. Filings are generally due within 45 days after quarter-end, and Form 13F does not disclose short equity positions; it is not evidence of the manager's complete net exposure. [SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f)

Apply equivalent availability rules to financial filings, Form 4 transactions, short-interest releases, and clinical profiles. A modern clinical profile cannot be backdated into a historical peer group. Investigate ticker reuse, CUSIP changes, mergers, split adjustments, and delisting returns before calculating performance.

Audit whether specialist density has a complete denominator. A denominator consisting only of the ingested specialists or selected managers is not the fraction of all institutional holders. Use a clearly named available measure until the required broader coverage exists.

### Establish Factor Baselines

Test each factor separately before blending: specialist count or concentration; spend relative to market value; eligible non-CEO open-market insider purchases; and, once available, clinical-peer momentum. Evaluate short interest separately as a signal and a crowding/cost consideration.

Create a versioned baseline from factors with adequate data. The existing specification's weights are candidate settings, not fitted or validated estimates. Reconcile the different composite implementations into one documented calculation. Define required inputs and minimum coverage explicitly; a peer-cluster identifier is not an observed momentum value. Do not silently substitute a partially populated model for the complete factor specification.

Compare available-factor cohorts, missing-factor cohorts, factor distributions, rank turnover, and stale observations. Distinguish missing values from measured zeros. Record each feature's role and expected direction, including how high short interest affects long selection and short selection.

### Compare Portfolio Designs

| Candidate | Research purpose |
|---|---|
| Diversified long-only factor portfolio | Establish whether stock selection adds value before short financing and availability complicate the result. |
| Same longs with an XBI hedge | Test whether sector exposure explains the result and whether a simple hedge improves the risk profile after costs. |
| Diversified stock long/short portfolio | Test whether selecting individual shorts adds value after borrow, execution, recalls, and squeeze losses. |

Benchmark against XBI and a comparable eligible-universe portfolio. Use identical dates and account for differences in beta, size, liquidity, and exposure. Predeclare a limited rebalance comparison, such as monthly versus quarterly, and fixed exposure and position limits. Show turnover, liquidity participation, indication and trial-stage concentration, catalyst clustering, financing risk, and tail-loss stresses.

Cash in lieu of an ineligible position, excluded securities, failed locates, and omitted factors require explicit rules. Present any modeled historical borrow separately from observed dated borrow. Public indications are not a documented locate; execution readiness requires the appropriate broker evidence. [SEC Regulation SHO overview](https://www.sec.gov/investor/pubs/regsho.htm)

### Validate and Freeze

Pre-register factor definitions, portfolio rules, costs, success measures, failure criteria, and the experiment budget. Use chronological training and validation windows, a genuinely untouched final test period, and forward paper outcomes. If a period has already influenced decisions, label it exploratory and choose new independent evidence rather than calling it untouched.

Report gross and net returns, benchmark-relative performance, volatility, maximum drawdown, tail loss, turnover, capacity, costs, coverage, and uncertainty. Break out longs, shorts, hedge, factors, market regimes, and issuer-size groups. Check dependence on a few trial successes, takeovers, extreme shorts, and excluded or missing firms. Report the number of variants tested and compare simple baselines before adding complexity.

Freeze the chosen rules and publish a reproducible run manifest. A candidate advances only with adequate input coverage, credible results after costs outside the development sample, and acceptable concentration and tail risks under the predeclared criteria. Record rejection and abstention decisions as outcomes.

### Establish a Forward Paper Portfolio

Replace the static candidate list with dated weights, simulated orders and fills, cash, open positions, liabilities, costs, benchmark returns, and rebalance history. Separate simulated fills from observed fills. Keep unresolved positions and short liabilities in returns and risk.

Begin with the simplest supported portfolio, then compare a hedge and individual shorts only when their data and costs are supported. Record data failures, missed entries, and paper abstentions. The plan does not assume that the stock-short variant will outperform the simpler alternatives.

After independent forward evidence, prepare a mandate describing capital, position and exposure limits, liquidity, broker requirements, and stopping rules for a separate owner decision. Creating a Strategy tab or a paper model does not establish trading authority.

## Preserve and Improve Systematic Shorts

Perform the navigation and component extraction before changing research rules. Preserve dataset versions, protocol hashes, frozen policies, result values, research-versus-forward labels, cost assumptions, exclusions, and remaining obligations. Do not rerun or tune studies as a side effect of moving them.

The saved short profit program spans financing, listing stress, and reverse splits. The saved 2026-10-23 forward status reports zero independent outcomes and incomplete coverage. Its new Overview must retain that distinction between historical research, paper monitoring, and observed outcomes.

The new strategy should answer, in order: what rules are being tested; what evidence supports them; what survives costs; what portfolio risk remains; and what independent forward evidence exists. Put the long source ledger, event registry, and earlier experiment versions behind Research and Data. Keep borrowed-stock obligations visible in the relevant portfolio results.

Reuse the existing systematic modules and data manifests rather than copying them into a second application. Fundamental Shorts retains its company ledger and framework work. Shared source data, company identifiers, and cost helpers can serve both pages while strategy results retain their own versioned authority.

## Revised Research Memory and Ticker Insights Cleanup

These changes amend the earlier review: Biotech Quant will have no dedicated subtab or full quant panels inside Research Memory. Biotech strategy research, methodology, and paper portfolios move together into Strategies.

| Area | Remaining work |
|---|---|
| Research Memory header | Remove global source-volume totals and biotech counters. Lead with current claims, material unresolved issues, and relevant changes. |
| Research operations | Move forecast, knowledge-decision, owner-outcome, and adjudication counters into a process view. |
| Claim ledger | Group related statements by company/topic, show a concise claim and dated evidence, expand full wording, and distinguish current, disputed, superseded, and historical claims. |
| Claim controls | Separate claim topics from source types; eliminate the hidden inherited date filter; apply search and holdings scope consistently. |
| Evidence quality | Show source independence and the actual disagreement instead of treating claim counts as votes. Keep raw confidence scores in details. |
| Review Queue | Prioritize material unresolved thesis challenges, link the evidence, show age and a next action, consolidate repeated reasons, and avoid making every ordinary known risk an urgent task. |
| Ticker Insights context | Move full macro, World Model, energy, and BTC work into a context view. Keep a concise collapsed summary; show a specific relevant exception instead of automatically expanding unrelated panels. |
| Ticker Insights scan | Default to material company developments across sources. Lead with what changed and why it matters, separating research coverage from investment significance. |
| Controls and counts | Consolidate toolbars, honor selected sorting in every mode, count actual visible matches, and provide pagination rather than an inaccessible 160-row cutoff. |
| Freshness | Date the displayed signal itself and distinguish publication, ingestion, source age, and overall ticker update. |
| Company detail | Use one shared detail panel across Insights, Memory, and the strategies, preserving list position and evidence links. |
| Shared presentation | Reduce repeated badges and source metadata, use readable text, wrap useful summaries, label controls, preserve URL state, and provide clear empty, unavailable, and stale states. |
| Row pruning | Collapse repetitive extracts; archive superseded and resolved material from default views; retain useful older evidence in search; flag uncertain ticker/source mappings for review. |

## Implementation Sequence and Acceptance Criteria

| Phase | Deliverable | Complete when |
|---|---|---|
| 1 | Inventory and freeze existing surfaces | Every biotech and systematic-short panel, dataset, saved preference, and deep link has a destination; existing study values and versions are recorded. |
| 2 | Five-strategy navigation and routes | Order matches this plan; both new strategies select the Strategies parent; reload, browser back, nested routes, and narrow-screen navigation work. |
| 3 | Extract Systematic Shorts | Its full quantitative workspace is reachable independently; the fundamental page retains theses, decisions, and actual position records without embedded backtest tables. Existing published study values are unchanged. |
| 4 | Extract Biotech Quant | All quant panels and their reference material are available in the new strategy; Research Memory loses the quant workspace; all general company evidence remains discoverable. |
| 5 | Simplify Insights and Memory | Hidden date filtering, ignored sort controls, inconsistent review filters, misleading counts, and inaccessible rows are corrected; tables and details follow the reduced layouts. |
| 6 | Audit and version biotech data | Universe, historical coverage, availability clocks, score calculation, missing inputs, source freshness, and evidence status are explicit. |
| 7 | Biotech research and paper portfolio | Registered baselines and portfolio comparisons produce reproducible results; unsupported variants stay research-only; frozen forward paper records start with declared rules. |

Do phases 1–5 as a UI and content migration. Phases 6–7 develop and validate the biotech strategy separately, so reorganizing the dashboard does not imply that a proven strategy already exists.

## Implementation Notes

- Update strategy navigation, route parsing, parent selection, route synchronization, and initial loading in `dashboard/index.html`. Preserve SPX, LS Algo, and Darwin CC behavior.
- Give both new strategy workspaces independent render and mount entry points. Systematic Shorts must load without first rendering the fundamental Short Ideas page.
- Extract biotech rendering from `dashboard/insights-viz.js` into a dedicated strategy module. Publish a compact biotech payload from the existing canonical ownership inputs so the strategy does not require the general memory ledger. Keep shared source IDs stable.
- Reuse `short-profit-program.js`, `short-framework-viz.js`, `short-sleeve-viz.js`, `reverse-splits-viz.js`, `reverse-splits-portfolio-viz.js`, and the related quantitative study modules where appropriate. Preserve archival comparisons under an explicit history disclosure.
- Canonicalize the old `#/ideas/short-alpha/backtest` link to Systematic Shorts and update internal links. Handle saved memory Biotech preferences and former biotech-entry controls by opening the new strategy; keep general Memory links working.
- Preserve meaningful selected records and filters in routes or migrated saved state. Support browser back without losing the company or experiment being reviewed.
- Add focused route and extraction checks, fixed-input comparisons of study values before and after migration, and interaction checks for the known filter/count issues. Visually review both new strategies and fundamental Shorts at desktop and narrow widths.
- Follow the current publish workflow. This plan adds no Gateway connection, collector, account, execution process, or order authority. Use local artifacts for migration; evaluate any later data refresh against its permitted source, licensing, and cost before running it. No ThetaData or Gateway access is required for this plan.

## Source Map

- `dashboard/index.html`: current three-strategy navigation, route handling, lazy loading, and mounted short workspace.
- `dashboard/insights-viz.js`: current memory, biotech, and ticker rendering.
- `dashboard/short-alpha-viz.js`: fundamental short workspace and current backtest entry.
- `dashboard/short-profit-program.js` and `dashboard/reverse-splits-viz.js`: quantitative workspace and preserved earlier studies.
- `_system/reference/biotech-quant/FACTOR_SPEC.json` and `SYNTHESIS.md`: factor hypotheses and library.
- `_system/reference/market-data/ownership/`: ownership, factor inputs, history, and saved paper list.
- `_system/scripts/build_specialist_13f_signals.py`, `build_biotech_composite.py`, `build_biotech_paper_book.py`, and `validate_biotech_quant.py`: existing signal, composite, candidate-book, and validation logic.
- `verdad_biotech_quant_methodology_2026-07-09.md` and `biotech_specialist_13f_2026-07-08.md`: historical biotech implementation plans; this document updates the destination and strategy-development work.
- `shorts_alpha_program_2026-10-18.md`: prior systematic short research program; its historical performance statements are not re-certified by this navigation plan.


## Implementation record — 2026-10-29

The five-strategy navigation, legacy-route migration, complete systematic workspace
extraction, biotech workbench, grouped Research Memory, review workflow, and
paginated Ticker Insights are implemented. Macro context has its own view.
Fundamental short theses and positions remain in Short Ideas. Existing short-study
publications and current ownership publications are unchanged.

The public SEC history now spans 20 dated quarters, with fund-level coverage gaps
reported in the strategy. The importer can extend history without overwriting
current publications and compares each period only with earlier periods. This
supersedes the two-quarter inventory above; it does not establish an audited
historical feature panel.

The baseline protocol, availability gates, percentile ties, missing-factor policy,
three portfolio variants, two benchmarks, costs, borrow carry, liability handling,
clinical-peer computation, risk diagnostics, reproducible manifests, immutable
protocol registry, and append-only paper accounting are implemented. Current
ambiguous ticker mappings and out-of-scope insurers are excluded from ranking.

The initial paper event records abstention and cash because verified historical
features and entry marks are not yet supplied. No independent forward outcomes
exist on the start date. A software migration cannot manufacture the missing
spend-value vintages, clinical returns, independent universe history, security
mappings, borrow evidence, or future observations. These are explicit data gates
in the workbench and operator documentation, rather than completed validation.
