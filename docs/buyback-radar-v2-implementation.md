
# Buyback Radar v2 implementation and release status

Date: 2026-10-20. Patch source baseline: remote main commit 45a3c8ba1b47b12dffad26035d8d624950a3aed2. Initial implementation source: 75eb759faf8e66d819c6e703ba99b4adb7f59454.

The core implementation is prepared in an isolated local repository. It has not been pushed, merged, or deployed. The original dirty checkout was preserved. This is a containment and research-data implementation; fresh backfill and the complete release reconciliation remain open.

## Implemented

| Area | Result |
| --- | --- |
| Financial facts | Economic-period deduplication; latest filings for the same fact; separate actual/basic/diluted histories; explicit zero versus unavailable; ambiguity and filing-date cutoffs. |
| Identity | CIK issuer grouping, ticker aliases, official SEC ticker-map refresh, explicit class reconciliation and common-equivalent policies. Missing class contexts withhold ranks. Foreign EDGAR filers remain eligible for supported data. |
| Corporate actions | Documented BKNG and OUST actions; no ratio-derived splits; unresolved historical restatements enter review. Share flows use the same action policy. |
| Ratios and assessments | Comparable 1/3/5-year actual-share reduction and elapsed-time annualization; FY/TTM cash flows; dated denominator lineage; currency and price-age gates; matched share-bridge efficiency; separate execution, funding, valuation. No grade from incomplete evidence. |
| Event ledger | Clause-related amounts; agreement versus authorization; AMCX and MSTR corrections; announcement-date size gates; exact dates versus fiscal-quarter windows; durable amendments and completion notices; unresolved status in review. |
| Publication | Immutable normalized details, content-derived snapshot IDs, component/detail checksums, manifest-last publication, three-snapshot retention, validated rollback, partial-update preservation, compressed raw caches, and checkpoint advancement after publication. |
| Coverage | Recent net reduction and dates; explicit quality states; null-last sorting; six filters; saved named buyback screens; snapshot change digest; source-linked metrics; separate share charts; share bridge; reported cash-flow periods; authorization capacity; EPS scenario; frozen research notes and export. |
| Special Situations | Typed terms, active/review/history/mention projections, corrections and primary evidence, explicit tender payoff assumptions, cross-links. |
| Shorts | Verified repurchase/shrink prerequisites, issuer deduplication, cause and observation dates, gross repurchases, first/multiple-observation context, query/framework/stage filtering, sort/disposition controls, dated reasons, material-observation reopening. |
| Consumers | Shorts, Special Situations, UI ticker shards and agent shards each own their projection refresh. They read the manifest's immutable snapshot and preserve unrelated research. |
| Operations | Weekday incremental discovery, Monday full refresh, bounded SEC retries, submission and filing caches, complete pagination/partitioning, manual repair dispatch, feed and lane health wiring, separate regression workflow. |

All records remain research only and excluded from base IRR. Tender scenarios expose acceptance, unaccepted-share value, fees and settlement days without annualizing the result.

## Verification completed locally

- 109 buyback financial, event, collector, publication, checksum, rollback and producer tests (164 tests across the four relevant suites).
- 21 Node UI and routing contract tests.
- 18 existing Special Situations tests and 16 existing dashboard shard tests.
- Headless Chromium desktop and 390px mobile checks: lazy history, saved screens, reason-required dispositions, tender scenario and no page errors.
- All inline dashboard scripts compile. The modified workflows parse as YAML and pass schedule, projection ownership and commit-gate checks.
- The lane registry computes a 102-hour one-skipped-run-plus-jitter window for the new weekday cadence; monitoring uses that value.
- Offline full-universe build and published-snapshot checks pass.

The browser smoke test exercises the shared components in an isolated page. Deployed-route visual verification and the complete repository CI suite have not run. The local interpreter lacks PyYAML, so the existing separation wiring suite could not import; YAML structure was checked independently with a real YAML parser.

## Backfill status and release gaps

The committed manifest and coverage shard contain the precise current counts and every per-issuer result. The offline run uses available local filing evidence. A build timestamp does not certify a new SEC retrieval.

- All 40 baseline events and 20 baseline mentions are retained as review records. None is promoted to the active verified book without current status evidence. The frozen legacy review register records an explicit outcome for each baseline item.
- AMCX's agreement amount is corrected to $30 million; $87 million is identified as remaining authorization. MSTR's common-stock program is reclassified from ASR to authorization.
- Ford and Berkshire class counts require current filing-context reconciliation. Their old counts cannot create positive rankings or yields. BKNG and OUST do not receive heuristic adjustments or clipped anomalous yields.
- Every included holding/watchlist issuer has a result or a reasoned gap. These visible gaps are not a claim that the current holding has been manually reconciled.
- The minimum 30-issuer primary-source reference review, complete holding reconciliation, and human review of the 31 previously ranked events remain release gates.
- Market-specific home-exchange/local-currency adapters remain an expansion item. Unsupported records have explicit reasons. US quote-age checks use a sourced 2025–2028 cash-equity calendar, including full holidays and the 2025 national day of mourning. Early closes count as sessions. Unsupported calendar years and listings with no supported calendar withhold current-price metrics.
- Share-bridge attribution remains unresolved where exact compensation, acquisition, conversion or other issuance quantities are not reported. Missing tender/ASR terms remain unverified.
- Full repository CI, deployed-route review and production rollout remain open.

Automated fresh SEC collection remains unavailable in this session. On the continuation attempt, GitHub branch creation reached the API but failed with HTTP 403: Resource not accessible by integration. No remote branch, pull request, push or merge was created. These restrictions and the unfinished primary reviews prevent calling the overall plan complete.

## Refresh and repair

Use a normal clean repository checkout with source access. Preserve unrelated local changes.

~~~powershell
python _system/scripts/build_buyback_radar.py --refresh
python _system/scripts/build_buyback_radar.py --check
python _system/scripts/build_special_situations.py --refresh-buyback-projection
python _system/scripts/build_short_alpha_dashboard.py --refresh-buyback-projection
python _system/scripts/build_progressive_shards.py --refresh-buyback-projection
python _system/scripts/build_dashboard_shards.py --refresh-buyback-projection
~~~

A targeted repair uses --tickers BKNG,F,BRK-B,OUST --write. It preserves other issuers. --offline and --skip-events preserve the event ledger. --strict is a diagnostic requiring complete current evidence; it deliberately rejects the present degraded backfill. Historical evaluation must use write=False or a separate output root and cannot overwrite a newer production snapshot.

Raw companyfacts and filing HTML are compressed under _system/data/buyback_radar/cache and filings. They are excluded from Git and restored through the workflow cache. Normalized published histories retain accession-level evidence.

To roll back, run build_buyback_radar.py --activate-snapshot SNAPSHOT_ID, followed by the four projection commands above. Activation validates every component and detail checksum before moving the manifest. The current event ledger is retained for subsequent reconciliation.

## Navigation and research storage

Existing locations are retained; there is no standalone Buyback Radar page.

- #/research/coverage/TICKER?section=buyback opens the shared detail.
- #/ideas/situations/buyback-events/TICKER focuses the issuer's event rows.
- #/ideas/short-alpha?buyback=TICKER focuses dilution research.

Saved screens, issuance dispositions and research outcomes are browser-local. Research outcomes freeze the snapshot, metric inputs, observation date and save time, and can be exported as JSON. They do not create ranked candidates or modify the canonical research ledger.

## Handoff and merge

The implementation patch is based on the pinned source version above. The isolated repository also contains baseline-only commits because the original checkout's Git metadata was read-only; do not push that isolated history to replace main.

Apply the implementation patch to a fresh branch from current main with git apply --3way --index, resolve any intervening changes, then create a normal implementation commit. Run the listed tests, refresh/reconcile the data, and use the repository's normal pull-request workflow. The user's request authorizes push and merge, but this session cannot perform those remote writes.

## Continuation verification

- Class-sensitive issuers now collect up to six years of periodic filings from SEC recent and historical submissions pages, with bounded requests, date cutoffs, accession deduplication and explicit incomplete/truncated diagnostics. Archive coverage changes invalidate the metadata cache; historical filing HTML is reused by accession.
- Missing or conflicting current class counts remain ambiguous observations. A more recent incomplete context cannot silently fall back to an older complete class total. Additional segment dimensions cannot become entity-wide class counts.
- Quote freshness now counts US equity sessions against the dated exchange calendar. The legacy business-day field is retained as a compatibility alias and explicitly labelled trading-session fields carry the calendar identity and primary sources. Date-only cutoffs are end-of-day dates.
- Current main was checked at 45a3c8ba1b47b12dffad26035d8d624950a3aed2, eleven commits after the original source baseline. Nineteen of twenty modified existing paths were unchanged. The operating KPI additions in build_progressive_shards.py were reconciled with the buyback projection changes; build-only imports remain inside build_all.
- The refreshed offline snapshot is 5a16e2579828153d73a6. It retains the same 877 security results, 83 verified records, 77 rank-eligible records, 41 cash ratios, 60 review events and 794 visible gaps. No fresh source retrieval or primary review is implied by this rebuild.

Calendar evidence: [NYSE 2026–2028 calendar](https://www.nyse.com/trade/hours-calendars), [2025 calendar](https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx), [January 9 closure](https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx), [Nasdaq calendar](https://nasdaqtrader.com/Trader.aspx?id=Calendar). SEC archive pagination follows the [submissions API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
