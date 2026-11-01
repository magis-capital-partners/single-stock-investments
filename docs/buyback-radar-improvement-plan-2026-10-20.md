# Buyback Radar Improvement Plan

Date: October 20, 2026

Make Buyback Radar a reliable way to answer three questions: which companies are reducing the ownership denominator, which repurchase events deserve attention now, and which former repurchasers have begun issuing shares again. Keep the existing three locations and give them one shared company record, methodology, evidence trail, and freshness policy.

The first release should repair calculation and event classification errors. Better sorting, charts, and grades should follow the corrected data. A recent build timestamp currently conceals old share observations and incomplete event extraction.

## Scope and audit baseline

The implementation inspected is on remote `main`. The local `shorts-phase0` checkout predates Buyback Radar and contains unrelated work in progress. Implement subsequent changes from the current feature version in an isolated branch or worktree; preserve existing local edits.

The baseline company and radar feeds were generated on October 18, 2026 at 17:55:46 UTC. The Special Situations feed was rebuilt on October 20 at 09:32:25 UTC, carrying the older buyback inputs. Findings below concern those committed artifacts and source code; a visual review of the deployed dashboard remains a rollout task.

| Baseline measure | Observed result | Implication |
| --- | ---: | --- |
| Company rows | 681 | These are ticker records, including aliases and multiple classes, rather than 681 proven distinct issuers. |
| Rows with a yield | 488 | A populated yield does not establish that its inputs are current or comparable. |
| Rows with a grade | 420 | Grades can survive unresolved share adjustments. |
| Share observation older than 180 calendar days on October 20 | 626 | Annual-only selection dominates. Age alone does not prove an annual filer is late. |
| Share observation older than 365 calendar days | 43 | These need explicit review; several observations date to 2010–2014. |
| Rows with split review flagged | 39 | Twenty-five still have a grade; ten still have a pace. |
| Rows with share review flagged | 80 | The UI drops this ambiguity from its compact data block. |
| Coverage gaps and skipped non-US entries | 122 and 50 | Show complete, reasoned coverage status, including held companies. |
| Events | 40 | Thirty-one ranked and nine history records. |
| Ranked events with an extracted end date | 0 of 31 | The current lifecycle logic defaults undated events to ranked. |
| Program mentions without market value | 15 of 20 | Unknown size is being placed under ordinary programs. |
| Issuing again signals | 2 | Both need context: OUST has a reverse split; NRG issued acquisition consideration. |

Baseline references: [radar feed](https://github.com/magis-capital-partners/single-stock-investments/blob/main/dashboard/data/buyback_radar.json), [company feed](https://github.com/magis-capital-partners/single-stock-investments/blob/main/dashboard/data/buyback_companies.json), and [Special Situations feed](https://github.com/magis-capital-partners/single-stock-investments/blob/main/dashboard/data/special_situations.json).

## Confirmed defects and immediate repairs

| Priority | Finding | Required repair and proof |
| --- | --- | --- |
| P0 | AMCX is displayed as an $87 million ASR. Its cited filing states a $30 million ASR and $87 million of authorization remaining. | Associate each number with its clause and economic meaning. Preserve $30 million as the agreement amount and $87 million as remaining authorization. Capture the expected fourth-quarter completion window. [Filing](https://www.sec.gov/Archives/edgar/data/1514991/000151499126000086/amcx-73026ex991.htm). |
| P0 | MSTR is displayed as a $1 billion ASR. The cited filing announces an authorization and lists ASRs as one permitted execution method. | Reclassify the common-stock authorization; record the separate preferred-security authorization separately. Permitted methods must not create executed agreements. [Filing](https://www.sec.gov/Archives/edgar/data/1050446/000119312526286871/mstr-20260629.htm). |
| P0 | BKNG has a 122.63% yield using 31,673,346 shares observed February 10, 2026 and an October price. Its April 2, 2026 25-for-1 split is absent from that latest annual observation. | Reconcile shares and quote to one split basis before market value or yield is published. The approximately 25-fold denominator mismatch explains the scale of the anomaly; recompute the final yield using current verified inputs. [Split disclosure](https://www.sec.gov/Archives/edgar/data/1075531/000107553126000037/R9.htm). |
| P0 | Ford's chosen share observation is February 14, 2011, although locally cached companyfacts contains diluted-share observations through 2026. | An obsolete preferred tag must not win over current evidence. Read current filing contexts and keep actual shares and weighted shares as distinct series. |
| P0 | BKRB, BRK-B, and BRK.B repeat the same 2011 Berkshire count. BRK-B and BRK.B get market values around $496 million from that count. | Resolve aliases, share classes, and equivalent-share conversion. Never multiply a class A count by a class B price. |
| P0 | OUST shows 83.74% retired and qualifies as issuing again while `split_review` is true. | Apply the documented 1-for-10 reverse split before calculating historical shrink. Reassess eligibility using comparable history and evidence of actual repurchases. [Issuer disclosure](https://investors.ouster.com/news-releases/news-release-details/ousters-1-10-reverse-stock-split-becomes-effective). |
| P0 | `_fy_key` groups facts by filing fiscal year. `_collapse_share_rows` may sum different values from that filing as presumed share classes. | Identify observations by their economic period and context. Ford's cached 2025 filing includes weighted counts for 2023, 2024, and 2025 under `fy=2025`; these are separate periods, not classes to add. |
| P0 | A full refresh drops unavailable companies and can remove their shard blocks. Offline or skipped event discovery produces empty event arrays. A partial run with `--write` can replace the global feed with its subset. | Publish explicit per-issuer update results, merge partial updates, and preserve valid prior records on retrieval failure with a visible age. Offline and partial work must not silently erase unrelated data or event history. |
| P1 | NRG's issuing-again signal has no causal explanation. | Attach acquisition issuance as the explanation. Separate primary issuance from the later secondary sale, which generated no proceeds for NRG. [Issuer disclosure](https://investors.nrg.com/news-releases/news-release-details/nrg-energy-announces-pricing-upsized-secondary-common-stock). |
| P1 | News Corp's selected share date is June 2013, while its yield uses a fiscal 2015 cash figure and an October 2026 price. | Require explicit periods on each numerator and denominator; withhold a current yield when historical compatibility fails. |

During the initial repair release, mark affected metrics as under review and remove them from positive rankings. Preserve the raw evidence and previous values for comparison. Do not fix extreme yields by clipping them to a numerical ceiling: investigate the source, class, currency, and split basis.

## Shared company and evidence model

Use one canonical issuer model to generate Coverage summaries, Special Situations events, Shorts signals, and agent views. Existing feed names can remain as compatibility outputs during migration.

| Record | Required contents |
| --- | --- |
| Issuer and security identity | Stable issuer ID, CIK where applicable, security ID, class, listing, ticker aliases, currency, ADR ratio, instrument type, and dated identity changes. |
| Share observation | Actual observation date, fiscal period where relevant, count, unit, class scope, actual or weighted basis, source accession, filing date, context, and adjustment basis. |
| Repurchase and issuance flow | Period start and end, common or preferred security, cash amount or share quantity, currency, gross or net definition, source, and whether it is reported or derived. |
| Corporate action | Effective date, action type, ratio, affected classes, source, and which historical facts already reflect the adjustment. |
| Program and event | Stable event ID, issuer and security, event type, announcement date, status, terms, amendment chain, size, remaining capacity, date precision, and evidence for each material field. |
| Derived metric | Value, unit, formula version, input references, measurement period, observation dates, confidence, eligibility, and reason when unavailable. |
| Publication manifest | Snapshot ID, source cutoffs, calculation version, component health, coverage counts, and dependency hashes. |

Represent reported zero, unavailable, unsupported, stale, and ambiguous as distinct states. Keep confidence separate from economic attractiveness. A value can be precisely reported and economically unattractive; an attractive-looking value can be unusable.

Resolve ticker aliases before discovery and calculation. Fetch companyfacts once per issuer, then map results to the relevant securities. Aggregate market value across economically relevant classes or use documented common-equivalent counts. For Alphabet, Berkshire, and similar structures, prohibit adding a reported total to its component classes.

Store raw facts separately from normalized observations and calculations. Retain accessions and observation-level provenance in published detail data; the current annual history export loses them. Support both revised history for current research and filing-date cutoffs for historical evaluation.

## Financial calculation repairs

### Select comparable share observations

Use the latest valid actual outstanding count from annual or interim filings. Prefer current, correctly scoped evidence over a stale preferred tag. Parse the underlying filing when companyfacts omits the required class context or custom concept. SEC documentation states that its aggregated XBRL APIs cover non-custom taxonomy facts applying to the entire entity, so companyfacts cannot be the only parser for every issuer. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

Maintain separate histories for actual outstanding shares, weighted basic shares, and weighted diluted shares. Do not splice them into one ownership series based on a 25% overlap tolerance. Weighted diluted counts remain useful for per-share economics, but cannot silently replace actual ownership counts.

Deduplicate by issuer, security scope, concept, economic period, unit, and compatible context. A revised fact supersedes the same historical observation; its filing fiscal year does not redefine the observation's period. Resolve class ambiguity from the filing rather than by summing similarly sized values.

Use documented splits, reverse splits, ADR changes, reorganizations, and class conversions. Ratio heuristics should open review tasks, never establish corporate actions. Apply adjustments consistently to outstanding counts, repurchased-share flows, issuance flows, and prices. Detect already-restated history to prevent double adjustment. Split-only transformations must leave market value and retirement economics unchanged.

### Publish explicit metrics

| Metric | Definition and display rule |
| --- | --- |
| Net shares reduced over one year | `100 × (1 − current comparable actual shares / comparable shares about one year earlier)`. Positive means shrink; label both dates. |
| Three-year and five-year reduction | Same basis over the stated window; include annualized pace using actual elapsed time. Use configurable comparable-date tolerances. |
| Shares down from observed peak | Historical context only, with peak date and history start. Avoid implying that all decline was caused by buybacks or legal cancellation. |
| Gross repurchase cash ratio | Common-stock repurchase cash over the stated FY or trailing twelve months divided by compatible current equity market value. Label FY versus TTM prominently. |
| Net cash repurchase ratio | Repurchase cash less common-equity cash proceeds over the same period, divided by market value. Identify issuance categories included. |
| Net retirement efficiency | Net decline in comparable shares divided by gross shares repurchased over exactly matching intervals. Show acquisition and other issuance separately. Leave unavailable when gross quantities cannot be established. |
| Remaining authorization | Last reported remaining capacity and its report date. Express as a percentage of dated current market value only when compatible inputs exist. |
| Execution pace | Actual repurchases and net share change over comparable recent intervals, alongside an earlier baseline. An authorization alone does not count as execution. |

Derive TTM flows from nonoverlapping periods. Where statements report cumulative year-to-date cash flows, use a validated FY plus current YTD minus comparable prior YTD construction. Preserve fiscal calendars and 52/53-week years; do not add annual and YTD totals together.

Whitelist cash-flow tags by economic meaning. Total-equity and treasury-acquisition facts require proof that they represent the intended common-stock cash expenditure. Preserve explicit zeros, conflicting disclosures, and noncash transactions rather than automatically replacing zero with another positive tag. Grade inputs and displayed yield must use the same validated flow model.

A cash amount of stock compensation is not a count of shares issued. Do not subtract compensation expense from buyback dollars and label the result net retirement. Reconcile the share bridge: beginning outstanding, repurchases, compensation issuance, acquisition issuance, conversions, other changes, and ending outstanding. Leave a residual when the bridge does not reconcile.

For a program's initial 10% classification, use unrounded size against verified market value near the announcement. Separately show remaining capacity against today's market value. This prevents an old program becoming a supposedly new large event merely because its stock falls. Missing market value means size unknown, not small authorization.

### Replace the opaque grade

Show separate assessments for execution, funding, and valuation. Execution asks whether gross repurchases reduced shares after issuance. Funding compares the same periods' repurchases with cash generation, liquidity, and leverage changes. Valuation requires a dated valuation input or an explicitly limited price-paid comparison; a higher nominal repurchase price than several years earlier does not establish value destruction.

Retain an A–E summary only after its rubric and evidence requirements are explicit. The current mapping can give four points a B when the price component is missing and a C when that component is present and scores zero. Missing evidence must never improve a grade. Do not estimate gross shares repurchased from net share decline to calculate price paid.

Any composite should show its components, coverage period, and confidence. Withhold a comparable grade when critical inputs are ambiguous. Adapt funding measures for banks and insurers rather than applying industrial cash-flow tests universally. Distinguish ETF creation/redemption from genuine closed-end fund repurchases, operating REIT repurchases, and holding-company repurchases through explicit instrument policies.

## Research Coverage improvements

Keep the Buyback column compact. Lead with the recent net share reduction and a small quality or confidence indicator; put gross cash yield and pace on the second line. Move since-peak shrink into expanded detail. Show the measurement period or an age badge where a value could otherwise appear current.

Add sortable choices for net reduction, gross repurchase ratio, execution pace, remaining authorization, and evidence quality. Add filters for verified reducers, accelerating execution, dilution offsetting repurchases, active events, and data requiring review. Preserve holdings and watchlist scope. Exclude unavailable values from numeric ranking in both sort directions.

The shared ticker Buyback section should contain:

1. A concise explanation of what changed, what caused it, and the evidence date.
2. Actual and weighted diluted share charts, clearly distinguished, with split and acquisition annotations.
3. A share bridge and quarterly repurchase-versus-issuance history.
4. Program utilization, remaining authorization, active event status, and the next meaningful date.
5. Execution, funding, and valuation assessments with expandable calculations.
6. Source links and a correction history available beside each material metric.

Reuse existing chart conventions. Load detailed history only when the section opens; load the compact summary early enough for Coverage sorting. Use prose and charts in the main flow, with XBRL tags and context IDs inside the evidence view.

## Special Situations improvements

Retain `#/ideas/situations/buyback-events` and the existing distinction between significant events and ordinary authorizations. Add separate views for active verified events, terms requiring review, completed or expired events, and program mentions. Unknown-size programs belong in review.

Require an actual agreement for ASRs. Require the issuer to be buying the relevant security; exclude third-party takeovers, debt tenders, and preferred repurchases from common-share event economics. Parse full terms and relevant exhibits, not just the first matching text window. Select amounts by their relationship to the action, rather than the largest dollar value near a keyword.

| Event | Main row | Expanded terms |
| --- | --- | --- |
| Issuer tender | Security, tender price or range, current premium, capacity, expiration, verified status | Odd-lot eligibility, proration rules, withdrawal terms, conditions, amendment history, and source clauses. |
| ASR | Agreement amount, agreement date, initial delivery, expected settlement interval, remaining settlement status | Counterparty, pricing formula, delivery stages, completion evidence, and linkage to the parent authorization. |
| Large authorization | Incremental and total authorization, announcement-date size, last reported remaining capacity, execution since announcement | Replacement or additive terms, expiration policy, reporting date, and execution history. |

Represent exact dates, explicit quarter or month windows, and no fixed expiration separately. AMCX's expected fourth-quarter settlement is useful without inventing an exact day. An authorization can legitimately have no fixed expiration; show that policy and its last verification date. An actionable tender requires verified expiration terms.

Track each program or agreement with a durable event ID. Append amendments and results; do not collapse all events for a ticker and type into one latest record. Repeated mentions of old ASRs update existing history. Completion and cancellation must close events explicitly, while ambiguous status enters review. Events must not disappear when they leave a rolling discovery lookback.

Separate corporate repurchase economics from a tendering shareholder's payoff. Show gross premium only with fresh compatible prices. Any tender scenario must expose acceptance assumptions, unaccepted-share value, fees, settlement timing, and downside. Do not present a certain or annualized return from the headline premium.

Make ordinary program mentions searchable and collapsible, with dates and reported size. Apply the same query and issuer filters as the event table; the current mention list ignores the search query. Replace the generic next step with concrete tasks such as verify expiry, read amendment, resolve market value, or confirm settlement.

## Shorts improvements

Keep Issuing again visible under All and dilution and financing. Turn the current unlinked list into a dated, sortable investigation queue linked to the same ticker Buyback section.

Require verified prior net shrink across several comparable observations and evidence of repurchase activity before describing a company as a former repurchaser. The existing five-year decline of at least 10% and latest-year rise of at least 2% can remain initial screening parameters only after normalization. Version and evaluate thresholds; apply a confidence gate before inclusion.

Each signal should show prior shrink, latest net issuance, observation dates, gross repurchases, and the evidenced cause: compensation, acquisition consideration, primary capital raising, conversion, or unresolved change. Distinguish confirmed persistence from a first observation. A secondary shareholder sale does not itself increase outstanding shares.

OUST must be re-evaluated after its reverse split is correctly normalized. NRG should explain acquisition consideration and its concurrent repurchase activity. Neither should inherit a financing-distress inference from share-count arithmetic.

Support disposition through existing short-research workflows: investigate, explained, monitor, or dismiss with a dated reason. Reopen a dismissed signal only for a material new observation. Candidate creation remains an explicit research action; a dilution flag alone does not create a ranked short. Respect the active text query, framework, and appropriate signal-specific controls, with counts matching visible rows.

## Cohesion across the three locations

All surfaces should use one reusable summary, detail, freshness, and evidence component. A company must have the same underlying figures and reasons wherever it appears. Keep economic state, confidence, and data status visually distinct; use the dashboard's existing design tokens and accessible text labels.

Provide links between Coverage, the company's event list, and its issuance investigation. Extend existing hashes with a documented Buyback section and event focus parameter while preserving existing ticker routes. Support direct load, refresh, back, and forward, and return users to their previous filters and scroll position.

Show what changed since the prior snapshot: newly confirmed event, faster actual repurchases, issuance reversal, completion, and corrected historical data. Corrections must be labeled as corrections instead of new economic signals. Aggregate by issuer so ticker aliases do not inflate counts. A single source click should explain a displayed number.

## Refresh publication and health

Replace independent file stamping with one deterministic build graph: discover and ingest, normalize, calculate, validate, project to existing feeds, then publish a coherent snapshot. Each output should carry the same snapshot ID and the buyback source cutoff. Downstream rebuild time must not reset upstream freshness.

Make the radar builder the owner of canonical buyback records. The Shorts and Special Situations builders should consume those records rather than being edited as side effects. Agent shards should be generated from the same projection. Detect mixed snapshots in the client and show degraded status while recovering.

| Work | Proposed cadence and initial freshness rule |
| --- | --- |
| New filings and amendments | Every business day, with more frequent bounded HTTPS discovery for held names and near-expiry tenders if existing pipeline capacity allows. |
| Active tender and ASR verification | Each business day; near-term tender terms verified within the prior 24 hours. |
| Company financial facts | Refresh after a new relevant filing; daily check for held names; weekly full-universe reconciliation. |
| Prices and derived market value | Revalue after the daily close. Flag beyond two completed trading sessions and withhold current-price rankings beyond five sessions. |
| Share observation freshness | Compare with the issuer's latest relevant filing and reporting cadence. Start with a 150-day review threshold for quarterly filers and 450 days for annual-only filers, then use explicit market policies. |
| Historical corrections | Rebuild affected issuers when amendments or corporate actions arrive; perform a full weekly consistency check. |

These are proposed operating thresholds, to be versioned in configuration. A normal annual disclosure lag is different from a parser missing an already-filed interim update. A recently downloaded file is not proof its selected fact is current.

Use submission metadata and reusable SEC caches to avoid refetching hundreds of unchanged issuers. Paginate or partition discovery until complete, record source totals and truncation, and fail the completeness check if a result cap hides filings. The current tender search reaches its 200-hit cap. Track failed document reads as well as companyfacts failures, with bounded retries and backoff.

Publish per-issuer success, failure, unsupported status, and last successful observation. Preserve a last known good record only when its identity and adjustment basis remain valid, and expose its age. Invalid records remain quarantined. A failed fetch cannot become a reported zero; a partial refresh cannot delete other issuers. Publish only after validation, with a manifest or staged snapshot that prevents partial output from appearing complete.

Measure collection health, economic-data freshness, parsing completeness, and metric eligibility separately. The current healthy flag mostly reflects request failures and does not catch old observations or wrong financial relationships. Include the full gap list, not only a 25-name sample, and prioritize held names such as FRMO, OTCM, BN, and the held international names.

The current weekly job runs Monday at 15:13 UTC, although the builder docstring describes a different time. Put cadence in one configuration and keep documentation aligned. Add an explicit manual repair entry point. Scheduled research uses HTTPS and committed artifacts under the existing Gateway rules.

## Validation and release criteria

Build regression fixtures from the actual defects, alongside broader invariants. Existing tests cover basic splits, thresholds, small synthetic event excerpts, and workflow presence; they do not establish the correctness of these production cases.

| Test group | Required cases and passing result |
| --- | --- |
| Financial periods | Multiple comparative periods with the same filing fiscal year remain separate; amended periods update the correct observation; TTM YTD arithmetic has no overlap. |
| Share identity | Berkshire class conversion, Alphabet totals and classes, ticker aliases, ADR ratios, new listings, and predecessor issuers resolve without duplicate economic counts. |
| Corporate actions | BKNG's split and OUST's reverse split preserve market value and remove artificial retirement; splits plus real issuance or repurchase are handled; already-restated facts are not adjusted twice. |
| Fact selection | Ford's obsolete cover tag cannot masquerade as current shares. Weighted and actual counts remain separate. Unavailable and reported zero stay distinct. |
| Event extraction | AMCX is $30 million, not $87 million. MSTR authorization is not an ASR agreement. Old mentions, completed agreements, debt and preferred tenders, multiple amounts, ranges, and quarter windows classify correctly. |
| Lifecycle | Amendments preserve event identity, results close tenders, unknown status enters review, and multiple independent agreements coexist. |
| Grading | Missing inputs never improve a score; net/gross periods and split bases match; unresolved critical inputs prevent a comparable grade. |
| Refresh resilience | SEC failures preserve valid prior state with age; offline and partial runs preserve unrelated records; pagination overflow and mixed snapshots are detected. |
| UI behavior | Shared values agree; deep links, search, sorting, empty states, stale states, keyboard navigation, and mobile tables work across all three locations. |

Before release, reconcile every current holding and every event promoted into the active verified book against its primary evidence. Use a diverse minimum 30-issuer reference set for class, split, sector, and calendar coverage. Human-review all 31 currently ranked events during the initial backfill, and retain an explicit outcome for each of the 40 baseline events and 20 mentions.

Release gates:

- Every holding has a verified result or a specific visible gap; no generic blank conceals missing coverage.
- Every displayed metric has a period, basis, source lineage, and eligibility state.
- Every active event has verified identity, action type, amount or terms, lifecycle status, and the appropriate date or explicit expiration policy.
- All confirmed P0 cases pass; no unresolved class or split problem remains in a positive ranking.
- Coverage, detail, Shorts, Special Situations, and agent outputs agree on snapshot and metric values.
- Recovery tests demonstrate preservation of valid prior records without presenting old inputs as new.
- Reference-set amounts reconcile to source precision; rounded display differences are tested separately from calculation precision.
- The compact radar summary remains under the existing 100 KB budget. Detailed histories load on demand, and the UI adds no material initial-render regression.

After launch, measure correction rate, missed material events, false event classifications, held-name coverage, elapsed time from filing to usable update, and stale ranked records. Evaluate economic research outcomes only from snapshots frozen before the outcome; corrections must not leak backward into historical screening results.

## Delivery sequence and code ownership

Estimated core effort is 16–25 working days for one experienced developer, including backfill and verification. Parsing difficult issuers or expanding international sources may extend this estimate. Deliver the P0 containment release before the full redesign.

| Milestone | Effort | Deliverable and dependency |
| --- | --- | --- |
| 1 Baseline and containment | 1–2 days | Freeze the audit cohort, capture regression fixtures, surface invalid states, and remove confirmed bad rankings. |
| 2 Identity and financial engine | 4–6 days | Period-aware facts, current actual shares, class and split normalization, explicit FY/TTM metrics, and score components. Depends on baseline fixtures. |
| 3 Event registry and extraction | 3–5 days | Correct AMCX/MSTR, retain amendments and lifecycle, verify market-value sizing, and reconcile all baseline events. Reuses identity and price rules. |
| 4 Publication and recovery | 2–3 days | One snapshot contract, deterministic projections, complete pagination, freshness status, and safe partial updates. |
| 5 All three dashboard locations | 4–6 days | Compact Coverage column, shared evidence detail, useful event terms, explained issuance queue, links, filters, and responsive behavior. Uses validated v2 projections. |
| 6 Backfill and staged release | 2–3 days | Reconcile holdings and reference set, compare v1 and v2 with reasoned differences, verify deployed routes, and cut over with rollback available. |

| Existing area | Planned change |
| --- | --- |
| `_system/scripts/build_buyback_radar.py` | Separate collection, identity, facts, corporate actions, calculations, event extraction, and projection responsibilities. Retain a thin compatible CLI. |
| `_system/data/buyback_radar/` | Add versioned normalized observations, event history, corrections, refresh results, and a complete gap register. Keep reproducible raw caches out of committed public payloads. |
| `dashboard/data/buyback_radar.json` and `buyback_companies.json` | Introduce versioned metric eligibility and snapshot metadata; keep compact summaries and add lazy detail shards. |
| `_system/scripts/build_special_situations.py` | Consume verified event states, preserve typed terms and upstream freshness, and keep unknown-size authorizations in review. |
| `_system/scripts/build_short_alpha_dashboard.py` | Consume normalized issuance signals, causes, dates, and dispositions. Remove dependence on side-effect stamping. |
| `dashboard/buyback-viz.js` | Become the shared summary, detail, freshness, evidence, and cross-link component. |
| `dashboard/index.html` | Integrate explicit sort/filter choices, lazy details, canonical issuer lookups, and durable navigation. Preserve unrelated local changes. |
| `dashboard/special-situations-viz.js` | Render event-specific terms, lifecycle, queries, and dated program mentions. |
| `dashboard/short-alpha-viz.js` | Render explained, filterable signals linked to the shared company view and existing research workflow. |
| `.github/workflows/data-pipeline.yml` and rebuild/publish orchestration | Add daily incremental work, weekly reconciliation, validators, manual repair, and coherent publish behavior. |
| `_system/scripts/tests/test_buyback_radar.py` and UI tests | Add production regression fixtures and invariant, lifecycle, recovery, navigation, and rendering checks. |

Run the new engine in shadow mode first. Classify every material v1-to-v2 change as new disclosure, corrected period, corrected security scope, corporate action, changed metric definition, or unresolved gap. Cut over only after the release gates pass, preserving the previous version for reproducibility and rollback. Route implementation through the repository's normal pull-request workflow.

## Later expansion

After the core is dependable, add market-specific adapters for held non-US issuers, IFRS concepts, home-exchange disclosures, treasury-share rules, and local currencies. Foreign issuers with valid EDGAR filings should not be excluded simply because their registry market is non-US. Every unsupported market should already have a visible coverage reason in the core release.

Then add saved screens, an in-dashboard change digest, and research outcome tracking. Optional valuation scenarios can illustrate the mechanical effect of retiring shares under explicit earnings and issuance assumptions. Do not add gross buyback yield mechanically to an existing per-share return model, which can double-count the same benefit.

Do not depend on the vacated 2023 SEC daily-repurchase disclosure amendments to promise daily execution data. Daily discovery can find new disclosures; actual execution observations remain limited by the issuer's reporting. [SEC technical amendments reflecting vacatur](https://www.sec.gov/rules-regulations/2024/03/s7-21-21).

## Source versions

Remote files inspected on October 20, 2026 include:

| File | Git blob SHA |
| --- | --- |
| `_system/scripts/build_buyback_radar.py` | `fe51c2fcdf3c9db655e0503d7dd8b4e980b0b2ed` |
| `dashboard/data/buyback_radar.json` | `aa5d888263f7b65cff02ca838dd8b1053e34343d` |
| `dashboard/data/buyback_companies.json` | `0a0daa8c2b8add7f2faf2a67047eae1c590d119f` |
| `dashboard/buyback-viz.js` | `3447a85e7beb838e4060663635038c5cc95c612b` |
| `dashboard/special-situations-viz.js` | `a41e18cc493f35ce648984d5d76509bd285f68ed` |
| `dashboard/short-alpha-viz.js` | `cf9eacaacb2d489e57c6932590a6c445ca9ac070` |
| `_system/scripts/tests/test_buyback_radar.py` | `0a1eb04cfad0ffce74cdecd6f8a701879c1d3c5f` |

Local Ford, Berkshire, and Ouster companyfacts were used to inspect historical fact structure and selection failure modes. These cached documents are evidence of parser behavior, not substitutes for a current source refresh.
