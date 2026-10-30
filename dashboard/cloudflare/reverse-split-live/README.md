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

The GitHub collector is scheduled every five minutes, off the top of the hour. GitHub may delay or skip scheduled runs; this is not a two-minute service guarantee. A bounded five-minute lease prevents two runners or machines from collecting concurrently. Runner termination preserves or releases pending jobs. Each run has a time/job limit and does not rebuild or redeploy the dashboard. This repository is public, so the standard GitHub-hosted Linux runner is free. If the repository becomes private, runner usage may incur charges after included usage. No subscription was upgraded.

The exact same collector can run on an independent machine with `--watch --interval 60`; credentials belong in a protected environment file, never arguments. Use a dedicated service account, a narrowly scoped Cloudflare token for this research database and bucket, a memory limit and restart backoff. NY4 is not the recommended host. Any NY4 deployment must additionally follow the root AGENTS coexistence rules (`Nice>=15`, CPU quota, idle I/O) and must never receive brokerage or ThetaData credentials.

Use the pinned `dashboard/cloudflare` Wrangler. Provision the named resources once, apply only this database's migrations, then deploy this configuration. The `Reverse-split live service` workflow tests and deploys changes on main; Pages deployments preserve the service binding through the shared deploy action. The collector caps its D1 usage at 500,000 read rows and 50,000 written rows per UTC day, reserving half the free write allowance and most of the read allowance for the other dashboard features. Ordinary filing scans do not archive non-candidate source bodies. The numerical resource identifiers are configuration, not credentials. All deployment credentials stay in the existing Cloudflare connection or GitHub secrets.

```powershell
node --test dashboard/cloudflare/test-reverse-split-live.mjs
# Collector credentials are supplied by the existing GitHub secrets or protected host environment.
node dashboard/cloudflare/reverse-split-live/collector.mjs
node dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js d1 migrations apply single-stock-reverse-splits --remote --config dashboard/cloudflare/reverse-split-live/wrangler.jsonc
node dashboard/cloudflare/node_modules/wrangler/bin/wrangler.js deploy --config dashboard/cloudflare/reverse-split-live/wrangler.jsonc
```

Inspect `/health`: last completed tick, per-source success/coverage/backoff, oldest queued work, persistent failed jobs, last reconciliation and research result counts. Healthy requires a recent completed tick, healthy sources, no flagged source gap and no failed jobs. Confirm actual source documents and decisions before declaring a live rollout complete. The health view reports the configured five-minute cadence plus runner delays; it makes no upstream delivery guarantee. These public feeds do not establish complete global coverage; a licensed market-wide release feed can be added separately.

For a reversible operational stop, disable the GitHub collector workflow or stop the independent collector service. Reads and stored evidence remain available. The Free Worker intentionally remains `ENABLED=false` with no polling triggers. Roll back code with the existing deployment tooling; source objects and decision records must remain intact. Retry failed work only after correcting its cause by resetting the specific D1 job to pending with a new lease, preserving its prior error in the incident record.

## Consolidated dashboard

The single UI is `#/strategies/reverse-split/overview`; `live` and `research` are independently loadable sections. Old short-alpha/backtest routes redirect here. The unrelated systematic short lab is no longer loaded or navigable. Its historical source files are retained for offline reproducibility.

`build_reverse_split_research.py` exports split-count/magnitude statistics, fixed-size repeat-split filters, and the relevant captured-announcement fundamental comparisons. Announcement comparisons retain their separate 20-session/$100,000 target assumptions and explicitly show imputed-price exclusions and feature coverage. All retained cash/runway/dilution/score cases keep their original timing, costs, horizons and population. The SHA-256 manifest prevents mixed-file display. The existing 54 selected-strategy scenarios retain their hashes and trade reconciliations.

Browser QA uses explicitly labeled synthetic live responses only inside Playwright and checks all nine sections, live evidence, research controls, legacy redirects, exports and a 390px viewport. It never seeds synthetic events into production.
