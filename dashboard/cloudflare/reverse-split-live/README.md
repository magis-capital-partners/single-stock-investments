# Reverse-split announcement service

This service monitors public disclosures and produces research screens. It has no broker, order, quote subscription, ThetaData, SSH, or NY4 dependency. Its isolated database and R2 bucket hold durable research jobs, announcements, immutable source objects, issuer financial caches, prior-action evidence, decision revisions and dashboard alerts. It never writes the portfolio command tables.

## Production resources

- Worker: `single-stock-reverse-split-live`, account `e1cac493b315c8fd7398500dd1bfd687`.
- D1: `single-stock-reverse-splits`; schema in `migrations/`.
- R2: `single-stock-reverse-splits-evidence`; no public bucket access.
- Queues: `reverse-split-analysis`, `reverse-split-analysis-failed`.
- Pages service binding: `REVERSE_SPLITS`; the owner-authenticated `/api/v1/reverse-splits/{health,events,events/:id}` proxy is the sole dashboard read path. Workers.dev and preview URLs are disabled. No public mutation endpoint exists.

The portable Node collector reads SEC 8-K/6-K and financial-report feeds plus PRNewswire and GlobeNewswire public feeds. It writes accession-deduplicated jobs before advancing each feed watermark. Capped feed windows remain explicitly incomplete. Runs during 08:00 UTC, or an explicit reconciliation run, repair the previous seven calendar days from SEC daily indexes. An indexed durable outbox dispatches priority jobs, including newest public filings first. Serial durable-job processing and an atomic SEC request slot limit this service to about 1.5 SEC requests/second. Other SEC applications must leave room in the shared per-user SEC budget.

403/429 responses trigger SEC-wide backoff. Source failures never appear as a healthy quiet feed. Queue send failures, duplicates, expired leases, process termination and retry exhaustion retain their jobs. Exhausted work stays in D1 even if a queue's retention expires. Content-limited reads reject oversized documents; unsupported content or instruments remain unresolved. An event is stored before financial enrichment. Financial outages produce an explicit unknown result and a bounded retry. No missing financial value becomes a passing gate.

## Rules and clocks

`core.mjs` contains the versioned live research policy. The six-component numerical score reproduces `net_edge_evidence.filing_rating`, including annual/matched fiscal YTD/four-quarter construction, weights, currency selection, 200-day freshness, and at least three measured components. Date-only facts wait until the following Eastern day. Unreported current debt remains zero in the inherited numerical formula and is disclosed separately. The inherited score has no industry-specific underwriting adjustment.

All discovered splits are retained: authorizations, cancellations, historical references, first documented splits, low scores and unsupported issuers. An actual upcoming action, a score ≥60 and at least one documented earlier completed split are required for a passing research screen. Missing history produces an unknown gate. Historical counts are lower bounds; separate actions on the same effective date are deduplicated by issuer. Multiple issuer securities require reconciliation. Historical evidence must have been public before the first observation of the announcement.

Publisher publication, first observation, financial cutoff and analysis time are separate. New publications and reanalysis preserve immutable decision revisions. Daily rescores expire entry windows and update financial availability. Research alerts are deduplicated by policy and event. No alert claims an executable position.

The live `observed_announcement_time` policy does not rewrite the frozen historical replay's filing-date-plus-one-day clock, selected five-session hold or any trading policy. Operational shadow evidence does not validate profitability.

## Deploy and verify

The owner chose Cloudflare Free on October 29, 2026. Financial parsing runs in `collector.mjs` on GitHub or an independent machine, not in a Free Worker. The Worker has no scheduled triggers or queue consumer in this deployment. Its private service binding serves the dashboard reads. The collector runs its durable work queue in local SQLite, saved atomically into two alternating private R2 checkpoint slots. D1 holds the lease, health summary and published announcement decisions. Cloudflare Queue resources from the initial provision are idle.

The GitHub recovery trigger is scheduled every five minutes, off the top of the hour; bounded continuous sessions now supply the in-process tick clock. GitHub may delay or skip scheduled runs; this is not a two-minute service guarantee. A bounded ten-minute lease prevents two runners or machines from collecting concurrently. Runner termination preserves or releases pending jobs. Each run has a time/job limit and does not rebuild or redeploy the dashboard. This repository is public, so the standard GitHub-hosted Linux runner is free. If the repository becomes private, runner usage may incur charges after included usage. No subscription was upgraded.

The exact same collector can run on an independent machine with `--watch --interval 15 --run-minutes 0`; credentials belong in a protected environment file, never arguments. Use a dedicated service account, a narrowly scoped Cloudflare token for this research database and bucket, a memory limit and restart backoff. NY4 is not the recommended host. Any NY4 deployment must additionally follow the root AGENTS coexistence rules (`Nice>=15`, CPU quota, idle I/O) and must never receive brokerage or ThetaData credentials.

Use the pinned `dashboard/cloudflare` Wrangler. Provision the named resources once, apply only this database's migrations, then deploy this configuration. The `Reverse-split live service` workflow tests and deploys changes on main; Pages deployments preserve the service binding through the shared deploy action. The collector caps its D1 usage at 500,000 read rows and 50,000 written rows per UTC day, reserving half the free write allowance and most of the read allowance for the other dashboard features. Ordinary filing scans do not archive non-candidate source bodies. The numerical resource identifiers are configuration, not credentials. All deployment credentials stay in the existing Cloudflare connection or GitHub secrets.

```powershell
node --test dashboard/cloudflare/test-reverse-split-live.mjs
# Collector credentials are supplied by the existing GitHub secrets or protected host environment.
node dashboard/cloudflare/reverse-split-live/collector.mjs
node dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js d1 migrations apply single-stock-reverse-splits --remote --config dashboard/cloudflare/reverse-split-live/wrangler.jsonc
node dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js deploy --config dashboard/cloudflare/reverse-split-live/wrangler.jsonc
```

Inspect `/health`: last completed tick, per-source success/coverage/backoff, oldest queued work, persistent failed jobs, last reconciliation and research result counts. Healthy requires a recent completed tick, healthy sources, no flagged source gap and no failed jobs. Confirm actual source documents and decisions before declaring a live rollout complete. The health view reports the collector heartbeat and configured cadence; it makes no upstream delivery guarantee. These public feeds do not establish complete global coverage; a licensed market-wide release feed can be added separately.

For a reversible operational stop, disable the GitHub collector workflow or stop the independent collector service. Reads and stored evidence remain available. The Free Worker intentionally remains `ENABLED=false` with no polling triggers. Roll back code with the existing deployment tooling; source objects and decision records must remain intact. Retry failed work only after correcting its cause by resetting the specific D1 job to pending with a new lease, preserving its prior error in the incident record.

## Consolidated dashboard

The single UI is `#/strategies/reverse-split/overview`; `live` and `research` are independently loadable sections. Old short-alpha/backtest routes redirect here. The unrelated systematic short lab is no longer loaded or navigable. Its historical source files are retained for offline reproducibility.

`build_reverse_split_research.py` exports split-count/magnitude statistics, fixed-size repeat-split filters, and the relevant captured-announcement fundamental comparisons. Announcement comparisons retain their separate 20-session/$100,000 target assumptions and explicitly show imputed-price exclusions and feature coverage. All retained cash/runway/dilution/score cases keep their original timing, costs, horizons and population. The SHA-256 manifest prevents mixed-file display. The existing 54 selected-strategy scenarios retain their hashes and trade reconciliations.

Browser QA uses explicitly labeled synthetic live responses only inside Playwright and checks all nine sections, live evidence, research controls, legacy redirects, exports and a 390px viewport. It never seeds synthetic events into production.


## Prospective intraday shadow tracking (November 4, 2026)

The dashboard route is `#/strategies/reverse-split/shadow`. It shows prospective decisions, simulated positions, immutable audit records, policy comparisons, daily observed model profit, source clocks, collector heartbeat, quote entitlement and unresolved execution evidence. The historical replay is unchanged. Browser alerts are opt-in and require an open dashboard; no Slack/email messages are sent by this service.

The primary version `rs_immediate.v1` uses the first supported quote after receipt and successful analysis during regular trading hours, with no artificial five-minute delay. Outside the regular session it waits for the next session. Comparison versions wait five minutes, wait until the next eligible open, enter on the split-day open, enter the following session, omit the score threshold, or require a third documented split. Each version is an independent simulated portfolio. Policies are registered immutably; a parameter change requires a new identifier. Announcements observed before registration are retrospective and never receive forward fills. Unresolved filters or quotes expire into explicit missed-entry records. Later evidence never backdates a decision.

The primary signal remains a scheduled upcoming split, at least one documented earlier completed split, distress score >=60, three measured components, and financial period age <=200 days. A release already more than 15 minutes old when the filters first resolve is recorded as late. Pre-split versions require a remaining pre-split entry session. The selected hold is five sessions including entry. Covering begins in the last minute of session five; unavailable/partial covers retain liabilities and carry. No price stop or profit target is introduced.

Simulation sells at bid less 10 basis points and covers at ask plus 10 basis points, with the declared per-share/minimum commission and 50% annual assumed borrow on rounded collateral for at least one modeled calendar day. Notional is capped by the $25k target, the reference account's price-shock reserve and three-name limit, and 5% of observed displayed size. A new timestamp alone never replenishes previously consumed size at that price. Freshness, issuer, common-share type, currency and identity continuity must pass. These are conservative quote-based counterfactuals, not broker fills or proof of replenishment, impact, halt status, margin or lendability. Regulatory, locate, dividend, cash settlement and forced-buy-in fees remain unobserved. Known marked P&L excludes unresolved marks, reports stale marks separately and is not account NAV.

Massive/Polygon HTTPS NBBO and issuer-reference endpoints use the existing `POLYGON_API_KEY` GitHub secret. No subscription is upgraded. Quote access is probed, and denied/delayed/stale responses remain explicit. The provider news endpoint adds discovery coverage; unsupported or secondary summaries require primary-source verification. Public IBKR short-stock inventory is checked at most every five minutes for active names, with file checksum, row-count and source-time validation. It uses the public FTP report, not a brokerage account/API. Inventory never becomes an approved locate. The model's fixed assumed APR remains separate from observed indications.

`import-evidence.mjs FILE.json` appends owner-supplied locate, SSR, margin or corporate-action observations to the isolated research database. The file envelope is `{"schema":"reverse_split_shadow_evidence.v1","records":[...]}`. Every record needs `event_id`, `kind`, `observed_at`, `valid_until`, `source_url` and `reference`. Locates additionally need `approved`, `shares`, and decimal `apr`; SSR needs boolean `restricted`; margin needs `approved` and `available_notional`; corporate actions need `execution_date`, `split_from`, and `split_to`. Credentials come only from the protected environment. Imported evidence does not send or approve an order. The continuous runner incorporates observations at its next evidence refresh.

### Continuous free runner

GitHub now runs `collector.mjs --watch --interval 15 --run-minutes 270` inside a bounded four-and-a-half-hour Linux job. This is continuous polling within a running process; the five-minute cron is a recovery trigger, not the tick clock. After normal completion a separate job with repository-dispatch permission queues the next bounded session. A lease prevents overlap with fallback jobs or another host. Queueing/startup gaps remain possible and are visible through the heartbeat; no arrival-time guarantee is claimed. Source processing, public-source backoff and work backlog can exceed the target cadence. Latest announcements and existing positions take priority over historical work. Financial feeds are polled on a slower cadence.

The runner keeps its scan database open, saves the authoritative two-slot checkpoint before publishing changed dashboard rows, and renews its lease. A failed dashboard publication retries from the committed state without erasing simulated positions. It checkpoints at least each minute and after event decisions. The research process pauses new work before the daily database budget is exhausted. Cloudflare remains Free and the Worker remains read-only, with no scheduled heavy processing.

An independent machine can run the same command with `--run-minutes 0` indefinitely using the prepared service. The service template is for a separate machine; it is not an NY4 deployment. No NY4 upgrade, gateway session, ThetaData login or live order is part of this rollout. Stop the monitor by cancelling its active GitHub run and disabling the workflow; disable/stop an independent service separately. Existing evidence and liabilities must remain intact.

Review operations immediately; review investment results only after sufficient prospective opportunities, distinct issuers and complete exit/cost evidence. There is no automatic promotion to live trading. Missing evidence, funding failures and source outages remain part of the opportunity denominator.


### Databento live Mini cohort

The external runner supports the existing licensed `EQUS.MINI` subscription using
`DATABENTO_API_KEY` from GitHub Actions secrets or its protected process environment.
The official Python SDK is pinned to 0.82.0. One child process maintains one live
`mbp-1` session; the startup AAPL subscription checks access, and relevant issuers
are added as decisions become due. The session is bounded to 128 explicitly
validated raw symbols. Symbols requiring an unverified spelling conversion are
refused. The child receives only the data credential, never storage or broker
credentials. There is no runtime import from DC-Execution.

Mini aggregates selected proprietary venues; it is **not SIP NBBO**. Seven new
`*_mini.v1` policies mirror the seven original timing/filter variants, with a
separate registration clock and separate portfolios. The original registered
parameters remain identical and still require full-market consolidated quotes.
Mini quotes cannot fill or mark those portfolios. When Databento is configured,
the dashboard initially selects the immediate Mini policy; each row, policy,
quote and audit retains the coverage distinction. Earlier announcements remain
retrospective for the new registration, even if eligible for an older policy.

The SDK uses only live subscriptions with no replay start. Neither Historical
nor Reference requests, license activation, subscription purchases, nor billing
changes are implemented. Existing Massive reference endpoints provide CIK,
share-class identity, common-share type, currency and split actions; a missing
identity blocks simulation. An unavailable action feed still freezes marks
across unresolved splits. Mini does not supply approved locates or broker
feasibility. No broker or ThetaData connection is used.

The transport preserves capture/event nanoseconds and local receipt times,
converts fixed prices by 1e9 and retains sizes in shares. Undefined/one-sided/
crossed books, bad-book/capture-clock flags and stale/future timestamps invalidate
the cached quote. It publishes at most four quote records per second per symbol.
The collector samples the latest supported quote during its bounded tick or
announcement callback; it is not a tick-by-tick execution simulator and cannot
promise every transient BBO. Signal timestamps, quote timestamps and simulation
timestamps remain distinct.

Disconnects clear quotes before reconnecting with 30–300 second backoff, capped
at twelve attempts per bounded process. Authentication/licensing rejection stops
that helper. The collector and source ledger continue; absent quotes never become
synthetic fills. The parent closes the stream when its leased collector exits.
GitHub queue/handoff gaps and source-analysis delays remain visible limitations.

Local offline checks: `node --test dashboard/cloudflare/test-reverse-split*.mjs`
and `python -m unittest discover -s dashboard/cloudflare/reverse-split-live -p test_databento_live.py`.
A successful subscription acknowledgement proves access, not a fresh book outside
trading hours. The first real session must verify quotes, identity and both entry
and exit audits prospectively.

Execution also requires a quote received at or after the planned entry clock, or at or after the exit request for a cover. A still-fresh cached book received earlier remains a dated observation and cannot generate a fill. Capture time, receipt time and the decision clock are retained separately. This guard applies equally to the original and Mini policies without changing registered parameters.

The external watch retries temporary storage/network failures at most three times with 15/30 second backoff. Each retry restores the committed checkpoint and receives only the time remaining in the original bounded run. It does not extend the GitHub job deadline or take over a competing lease. Policy/configuration/credential failures still stop immediately. The data stream remains a single child session across an in-process recovery.
# IBKR capacity, executable shadow and November 5 validation

Free-plan write conservation: a ten-minute collector lease renews at most once
every two minutes; the dashboard heartbeat updates once a minute; routine
source-health rows publish every five minutes. Decisions, fills and checkpoints
keep their immediate/minute cadence while a name is armed or held. With no active names, routine checkpoints publish every two minutes; the heartbeat and quote-feed status still update every minute. The immutable first executable-registration
UTC day has a one-time 70k research row-write budget to cover historical cohort
enrollment; later UTC days return to 40k. This is below the account's 100k/day
Free limit and does not reset or conceal consumed usage. The budget remains a
fail-closed stop; it is not an unlimited production-service guarantee.

The eight `rs_ibkr_{capacity|executable}_{10|25|50|100}bps.v1` cohorts are
separately registered forward experiments. The original fourteen policies,
their $1m reference portfolio, fixed 50% borrow assumption and results remain
unchanged. No cohort can submit an order, accept a loan, or contact a Gateway.

The original name ceiling is `equity × allowed_loss_fraction / adverse_shock`:
`1m × .005 / 2 = $2,500`. Raising that ceiling to $25k while retaining the +200%
shock means accepting a $50k modeled name loss (5% of the reference portfolio);
$100k notional means $200k (20%). Reducing the assumed shock merely changes the
model; it does not reduce a stock's possible rise. The new capacity cohorts
have no fixed dollar, equity, three-name or sleeve stress ceilings. Their
reported size is conditional on liquidity, price, inventory and eligibility,
not an approved live allocation or a real maximum loss.

Entry size uses the currently observed selected-venue bid and its displayed
shares. Positive displayed additions are counted in the Python helper BEFORE
four-per-second transport throttling. A timestamp change alone adds no shares;
reconnection does not reset consumed capacity. Each cohort consumes its own
book credits and cannot reuse another event for the same issuer. This is an
upper-bound study of observed L1 liquidity, not proof that the whole displayed
book would remain available to our order. There is no invented deeper book,
queue priority, trading volume or calibrated causal market-impact model.

The budget is deterioration of the accumulated entry VWAP from the first
eligible quote's midpoint, including spread and 10 bps modeled slippage. Wide
spreads can prevent entry even with a generous dollar allocation. There is no
declared optimal budget yet. After 30 observed entry sessions and 20 issuers,
the dashboard identifies the smallest tested budget retaining 90% of observed
conditional notional as a RESEARCH candidate; separate execution-impact
validation is still required. These thresholds are research design choices.

Only IBKR borrow data is used. `borrow-service.mjs` reads IBKR's existing public
FTP file, validates its declared row count, clock and checksum, and archives
matching rows privately. Every resolved event ticker receives a record,
including absent symbols, missing fields and failed daily coverage. All names
are captured daily overnight, after 08:35 and after 16:15 ET. New or newly active
names refresh immediately; active names refresh every five minutes. Runner handoffs preserve
the cadence state. Missing rates are never treated as zero, quotes expire
after 30 minutes for entry, and a newer missing/unavailable observation
supersedes an earlier valid indication. Public FTP is indicative, unauthenticated
inventory data, not an account-specific borrow reservation or approved locate.

The executable lane additionally requires source-dated, unexpired IBKR
reverse-split evidence for locate quantity/APR, allocated margin notional, SSR
and halt status. A shared `allocation_id` prevents double counting the same
locate or margin allocation inside a cohort. Unknown checks block adding;
covers remain possible and unavailable cover liquidity never erases a short.
SSR-restricted marketable bid sales are conservatively blocked.

Import owner-supplied evidence with `import-execution-evidence.mjs FILE.json`,
using a private `ibkr_reverse_split_evidence.v1` envelope and `records` array.
Every record needs `broker: IBKR`, `scope: reverse_split`, an existing
`event_id`, `kind`, `observed_at`, `source_url` and `reference`. Locate/margin/SSR
also use the existing evidence fields and `valid_until`; locate and margin
need `allocation_id`. `trading_status` needs `halted` and `valid_until`.
No browser endpoint accepts evidence or orders. A public availability record
does not meet this contract. Supplied documents are not verified broker fills.

The optional read-only Flex adapter uses only the fixed HTTPS reporting
`SendRequest` and `GetStatement` endpoints. Configure existing GitHub secrets
`IBKR_FLEX_BORROW_TOKEN` and `IBKR_FLEX_BORROW_QUERY_ID`. The query must return
XML, USD stock detail rows, unambiguous ISO/compact dates, and Borrow Fee
Details (enabled by request at IBKR). Do not rotate another system's token or
change its query. Unknown report schemas fail closed. Full account statements
and account numbers are not archived: only matching normalized borrow rows,
an account-scope hash and the report digest are retained. An actual charged
rate for a held position is separate evidence, not proof of a new locate or
an actual charge on a paper position. With no configured token/query, the
dashboard explicitly reports `not_configured`; no actual rate is invented.

Estimated P&L keeps proceeds, partial covers, ask marks, modeled commissions,
daily borrow rows and an open-cover fee/slippage reserve. Daily borrow uses
that day's observed annual fee and modeled maximum outstanding daily shares
on rounded 102% USD collateral, /360. This is a conservative research accrual,
not IBKR's final settlement ledger. Missing marks/rates remain missing costs.
Accruals after entry are labelled ex-post; they never change the entry decision
or borrow-cutoff eligibility. Split ratios preserve share liabilities and
fractional remainders; uncertain actions or identity changes freeze P&L.

Complete reconciled paper net P&L requires a CLOSED position and a dated
`cost_reconciliation` evidence record for its exact `policy_id`, with
`covers_fills_through` covering the last fill, `basis: estimated|documented`,
and explicit finite `costs` for commissions, borrow, regulatory, locate,
dividends, cash_settlement, buyin and short_proceeds_interest. Interest credits are negative costs; extra or nonnumeric cost fields are rejected. Signed adjustments can be documented;
an absent cost is not zero. Actual broker P&L stays null because no real fills
exist. Original baseline P&L remains separate. The annual-rate cutoff table
uses the rate known at entry (10/25/50/100/200% and no cutoff), never the best
future rate; it does not automatically choose a live trading cutoff.

Validation plan `rs_live_path_2026-11-05.v2` runs in the existing continuous
GitHub collector on November 5 from **09:25–16:10 America/New_York**
(14:25–21:10 UTC). AAPL, SPY and IWM are benchmark subscriptions in the SAME
Databento live Mini session; active reverse-split names are checked separately.
ETF benchmark identity permission is isolated from common-share entry checks.
No historical request, paid feed upgrade, replay, NY4, ThetaData, TWS or broker
socket is used. GitHub can delay/skip scheduled recovery triggers; the runner
heartbeat and sample coverage expose such gaps and this is not a production
execution SLA. Standard runner clocks are not precision clock-synchronized.

The report records capture-to-runner receipt, quote age, receipt-to-evaluation,
exchange-to-capture when available, share units, spreads, clocks and errors.
Targets: p95 delivery ≤2s, age ≤5s, evaluation delay ≤15s, at least 100 distinct
regular-session quotes per benchmark and ≤5% failed attempts. Entry still
requires a quote no older than 15s received AFTER its decision clock. Raw
samples are archived to private R2 in minute batches; the dashboard receives
only summaries. A missing session cannot pass. A benchmark pass does not
validate the first new reverse-split news-to-entry path or execution impact.
Forward announcement clocks are reported separately as they occur.

Owner-only reads: `/shadow/executable`, `/shadow/executable/tracks`, paginated
`/shadow/executable/tracks/{id}`, `/shadow/borrow?ticker=...`, and
`/shadow/validation`. Borrow and audit exports page through the full private
history, bounded to 10k rows per browser export with an explicit error rather
than a silently incomplete download. All schemas live only in the isolated
reverse-split D1/R2 resources. Cloudflare stays Free; heavy calculations stay
in the external collector. The Gateway registry and SPX execution are untouched.


The existing IBKR reporting credentials were located in the local ls-algo configuration and copied to protected reporting secrets without changing that query or token. Its Borrow Fee Details output can exceed 32 MB, so the isolated adapter accepts bounded 128 MB reports, filters to the strategy tickers and the last 35 report days, and deduplicates stable account/security/day/loan observations across later downloads. Previously collected older dates remain in the immutable history. Daily generation begins after 08:35 ET, uses one reference at a time and at most twelve reporting calls spaced at least a minute apart, with extra rate-limit backoff. Large downloads/normalization run as a bounded background task; shutdown joins it before closing the local ledger. No raw full-account statement is archived or published.

Daily paper carry is reconciled when reported account fee rates become available for the SAME IBKR conid and day with an unambiguous account scope (or explicitly scoped evidence). Multiple loan rows are value-weighted and later restatements replace their earlier rate proxy, with an audit record. Ambiguous accounts and security mismatches cannot silently replace a quote. This uses an actual reported rate as an ex-post COST PROXY on hypothetical shares, not a guaranteed rate for a new loan or an actual charge on a paper trade. Entry-known rate cutoffs and fills are unchanged. Non-session days may carry the last supported position mark and closing share liability, explicitly flagged; absent rates remain missing.

The v2 validation plan supersedes and archives the unsampled v1 plan before the market window. The transport retains the FIRST benchmark receipt in each five-second interval and drains it at the next processing pass. Current-book age is measured separately from receipt-to-evaluation latency; a newly received quote cannot hide earlier unprocessed updates. A pass requires at least 95% of regular-session minutes covered for EACH benchmark, at least 100 distinct current quotes and 100 timed receipts each, no evaluation gap over 60 seconds, and the registered latency/error targets. Queue overflow is an explicit failure. A plan with existing samples or an underway market window cannot be replaced.

Owner-supplied eligibility evidence is imported using a kind/time index, excluding public-inventory rows that the collector already owns locally. This prevents a growing public borrow archive from being repeatedly scanned/re-imported. The new index is isolated to the research database.

Flex loan rows are aggregated as a complete account/conid/day snapshot before deduplication. Their original signed fee amounts and component records are retained in private evidence; only compact daily aggregates enter D1. This prevents a loan removed from a later statement from surviving as an orphaned rate component. The reporting URL returned by IBKR is accepted only if it exactly matches one of its two documented fixed HTTPS reporting endpoints; redirects and arbitrary hosts are rejected.

Confirmed, dated IBKR corporate-action evidence can resolve an unavailable vendor action feed; conflicting applied ratios freeze P&L instead of adjusting twice. Corporate-action imports require `execution_confirmed: true`. A cost reconciliation may include `fractional_settlement: {shares, price, security_id}` to close an exit-pending fractional liability from an explicit cash-price reference. It must match the entire remaining fraction and security and cover the settlement observation time. Principal enters cover cost, additional fees stay in the reconciled cost components, repeated evidence is idempotent, and actual broker P&L remains null. Without that evidence, the fractional liability is retained.

The existing large Flex query was observed still pending nearly an hour after issuance. Its twelve-call daily limit is therefore spread with exponential retry spacing from one minute up to thirty minutes, reusing the same reference across checkpoints and runner handoffs. Rate-limit responses impose at least five minutes without shortening a longer backoff. A later successful report can complete without burning every allowed call during the first twelve minutes.
# Primary financial coverage

The independent `reverse-split-financials.yml` process checks every resolved issuer in the announcement ledger, starting with upcoming actions and unscored companies. It uses public SEC submissions, annual/quarterly reports, foreign interim exhibits, entity-wide iXBRL/custom concepts, and conservative comparative-table extraction. PDF tables use pinned PyMuPDF; scanned text uses Tesseract and remains a review candidate when columns cannot be verified. An issuer website can be followed only from CIK-matched reference metadata, with public-address checks and source identity validation. Existing market-data credentials optionally provide a comparison; vendor zeros and restated records are never automatically accepted as missing filed values.

Captured documents, normalized financial ledgers, source locators, currency/scale, publication/observation clocks and immutable profile versions are stored in the private evidence bucket. A source conflict blocks automatic eligibility. Missing values remain missing; genuine zero values require an explicit reported amount. The numerical formula and its 200-day freshness/three-component gates are unchanged. Older complete statements have a separately labelled diagnostic score. Funds and other instruments outside the operating-company strategy are classified separately.

The live collector warms changed evidence in a background task, then records a new decision at the current time. Earlier decisions, registrations and fills are immutable; retrospective tracks never acquire a backdated entry. Newly observed financial disclosures enter the source queue without blocking quote processing. Failed downloads use bounded timeouts, backoff and a separate renewable lease. The primary quote/announcement collector and the document collector have different workflow concurrency groups. Neither uses NY4, ThetaData or an IB Gateway connection.

On **Reverse-split short → Announcement monitor / Intraday shadow tracking**, expand **Financial data coverage**. Filter companies, inspect every input/component and its captured filing, and review a missing or conflicting amount. Reviews require the signed-in owner, same-origin submission, a captured company source, explicit units/periods and a reason. The immutable review takes effect in a subsequent calculation. It cannot change earlier fills. Source downloads are attachments, never active filing HTML on the dashboard origin.

Private service routes: `GET /fundamentals`, `/fundamentals/summary`, `/fundamentals/<CIK>`, `/fundamentals/<CIK>/source/<SHA256>`; `POST /fundamentals/reviews` is available only through the authenticated owner proxy. All other mutation routes remain disabled. The Worker remains service-only with no public route or background cron.

Continuous research publication uses the private checkpoint and derived read views rather than repeatedly updating thousands of database rows. The checkpoint commits before any displayed fill is published. Sparse database state retains the lease, heartbeat, checkpoint pointer and owner review signals; the Free database write guard no longer suspends detection, exits or latency measurement. A stale/paused/degraded runtime is displayed honestly. The missed morning portion of the November 5 validation remains a gap and cannot be represented as a successful full-session test.

## November 6–13 prospective observation and AWS hold

`review-service.mjs` registers and archives `rs_shadow_review_2026-11-06.v1`
before the first session. AWS remains deferred for the owner's review after
the observation week. Five consecutive complete sessions must meet the v3
market-data criteria (95% minute coverage, gap at most 60s, p95 receipt-to-
evaluation at most 5s, existing delivery/age/error limits). Operating success,
conditional capacity, IBKR evidence-gated simulations and actual execution
are separate conclusions. A quiet week cannot validate trading returns.
The initial review is November 13 at 16:30 New York; positions still open and
unreported costs require subsequent follow-up. No hosting upgrade or live
order is automatically authorized by a passing report.

`reverse-split-review.yml` independently checks HTTPS heartbeat, checkpoint
freshness, source failures and sample overflow twice an hour during the
observation day. Results go to the workflow summary and private
`review/monitor/` archive. Scheduling can be delayed by GitHub; these checks
do not provide a guaranteed alert time. Existing browser alerts still require
the dashboard to be open. No new external messaging integration is enabled.

The collector now restores same-day verified score caches, loads an announced
issuer directly with an abortable four-second storage budget, and warms twelve
enhanced profiles per background pass. The separate nightly preparation uses
SEC exchange-listed candidates plus Company Facts bulk data, with bounded,
checksum-verified shards. Missing XBRL, foreign issuers and non-common-share
candidates retain explicit unresolved/inapplicable states; complete processing
does not imply complete fundamental availability. Full filing extraction remains
the independent coverage process. Prior-split and security verification remain
entry requirements.

Price evaluation is serialized and quote-triggered, with a one-second fallback;
source polling targets 15 seconds independently of filing work. Business Wire
joins the configured SEC, PR Newswire and GlobeNewswire feeds. A blocked
publisher article may use only its identified primary RSS excerpt and still
requires issuer, ratio and date verification. Reconciliation stays a recovery
path and does not establish the first public release time. `/shadow/readiness`
and `/prepared` are owner-only views. Daily validation v3 archives complete raw
sessions before scheduling the next full exchange session; November 5 v2 stays
unchanged and downloadable.

The 900-second original entry expiry is not a waiting period. Eliminating
actual latency requires continuous collection, prepared inputs, measured feed
delivery and eventually direct publisher/licensed news delivery where public
feeds prove late. Same-day financial filing availability is still the inherited
next-Eastern-day rule. Any timestamp-aware same-day alternative must be a
separate prospective policy, never a rewrite of original results. A 30/60/300s
entry-delay and 10/25/50/100bps cost sensitivity audit is required in the review;
those scenarios do not become measured results merely because they are in
the plan. Mini quotes cannot measure market impact, queue position, full-market
NBBO, recalls or guaranteed loan availability.

Oversized SEC submission bundles and embedded PDF exhibits use the official,
CIK/accession-bound filing index. The collector downloads only the primary
report and EX-99 disclosures (at most twelve documents, 24 MiB each and 48 MiB
in aggregate). Each captured document keeps its actual URL/hash. Pinned
PyMuPDF extracts bounded selectable PDF text in a credential-free child;
scanned, encrypted, over-limit and unreadable documents stay unresolved.
The new reader reopens previous size-limit failures once, preserving their
original filing/receipt clocks. Historical discoveries cannot gain forward
fills. SEC catch-up includes unresolved gaps within the last month, archives
the retrieved daily-index proof and never closes publisher gaps from filing
indexes. Source/quote work remains independent of this historical queue.

# Database allowance incident — November 6, 2026

Cloudflare account analytics attributed 4,827,240 scanned rows (2,006 calls,
2,406 rows/call) to the dashboard's retrospective per-policy list query. The
shadow database accounted for 4,902,997 reads; the other account database
accounted for 373,543. The account's 5 million/day Free allowance was exhausted
at approximately 08:28 UTC, stopping collection and financial preparation.
This outage must remain in the review record; missed announcements cannot be
converted into original-clock forward fills by subsequent backfill.

Dashboard track lists now use content-addressed private R2 pages (100 cards
per page) for both historical and forward records. Main snapshots and the
independent monitor read the private heartbeat without a D1 publication-mode
lookup. Older snapshots explicitly report `awaiting_snapshot_rebuild` for
history rather than falling back to the expensive query. Fallback SQL indexes
are idempotently applied at the first collector start after the UTC reset if
the deployment-time migration was blocked. The Free plan remains unchanged.

Recovery: the included daily allowance resets at 00:00 UTC (19:00 Eastern on
November 6). Existing scheduled jobs attempt resumption, but GitHub scheduling
is not an arrival-time guarantee. Verify the actual collector heartbeat,
committed checkpoint, publication, source catch-up and quote validation before
claiming recovery. The November 6 session cannot pass its original complete
session criteria after the market-hours outage. Do not alter the registered
review policy to hide this failure. No NY4, Gateway, ThetaData or AWS action is
part of this repair.

