# Dashboard cleanup and market risk freshness

Prepared October 22, 2026. This records the current audit, the bounded UI fixes in this change, and remaining work. Scheduling proposals below have not been deployed.

## Buyback radar

The buyback screen previously opened on all companies, rendered the entire result set, and gave saved-screen editing and evidence controls the same prominence as the results. Its evidence pipeline already provides a shared atomic snapshot for Coverage, Events and Shorts; reuse it.

Implemented locally in this change:

- A dedicated radar header, three concise coverage statistics, clearer table hierarchy and a contained mobile table.
- A focused default shortlist: verified/rank-eligible evidence; net share reduction of at least 5% over 1Y; positive net reduction over 3Y; and positive reported repurchase cash ratio. This is a research filter, not a buy rating or proof that all reductions came from repurchases.
- Search, a preset selector, a sort selector, reset, and 30-row pagination. Existing saved screens remain behind an expandable control.
- One-time migration of the old default All filter to Focused; subsequent deliberate All selections and saved screens remain available.
- Existing cross-links to company evidence, verified events and issuance research. The filter applies to the radar and does not silently filter Research coverage.

Remaining refinement: show only two headline share-reduction metrics in the company card; fold the extensive cash-flow bridge, source history, scenarios and research outcomes into clearly named detail sections. Leave event terms and their verification visible where an event is actually actionable. No new authorization should be ranked as a completed buyback.

## What Managers and Data Health currently mean

Managers is the raw 13F holdings browser. `dashboard/holdings-viz.js` loads `holdings/managers_index.json` and `holdings/feed.json`, then displays Consensus, Changes, Outside this book and a long manager list. It duplicates ideas already represented by the Insights consensus/fund tools and puts the selected manager below the entire list. The attached screenshot's text shows this unstructured holdings/consensus surface.

Data Health is the internal source/refresh diagnostics page. Its source section in `dashboard/insights-viz.js` concatenates dashboard feeds, source-health records and potential data-provider candidates. It also inherits the generic Insights navigation/period controls, even though a quarterly content filter does not help diagnose a broken feed.

## Recommended navigation and redundancy reduction

| Current surface | Destination and behavior |
|---|---|
| Insights → Managers, plus consensus and fund views | One Insights → Investors workspace with two views: Signals and Directory. Signals owns consensus/additions/exits/outside-book ideas. Directory owns manager search and filing histories. |
| Long manager list and detail at the bottom | Searchable compact directory, sorted by portfolio overlap by default; selected-manager drawer or detail route; one quarter selector and a visible holdings-date/filing-date distinction. |
| Data Health as a research-content tab | A small global “Data status” link beside the dashboard timestamp; expand an exceptions-first panel with links to full diagnostics. Keep legacy deep links working. |
| Dashboard-feed table plus source-health table | One source registry keyed by feed ID, with observation date, last successful build, expected cadence, state and next action. Expand pipeline/receipt details on demand. |
| Provider-candidate registry inside health | Put planned integrations in developer documentation; show only active data sources in the product's data-status view. |
| Repeated timestamps, raw API paths and lane jargon | One compact source/date indicator on each analytical surface; full transport and pipeline details in diagnostics. |
| Buyback screening repeated across unrelated surfaces | The radar owns screening, Coverage owns company evidence, Special Situations owns verified event terms, and Shorts owns issuance research. All read the same record. |

Keep the existing six primary workspaces. Introduce no new top-level research tab for internal diagnostics. Preserve old `#/insights/managers` and `#/insights/data-health` routes as aliases during migration. Changes to investor navigation and the diagnostics page are proposed, not implemented in this bounded UI change.

Acceptance: one canonical consensus result set, one manager directory, no duplicate source tables, selection never puts company/manager detail below hundreds of rows, accessible keyboard controls, and no whole-page horizontal overflow at a 390px viewport.

## Why market risk values look stale

This diagnosis is from the checked-out files and code, not a live production-API inspection.

1. `.github/workflows/market-risk-components.yml` runs at `19 22 * * 1-5`: 18:19 Eastern during daylight time and 17:19 during standard time. It does not start at the close.
2. The separate technical/volatility refresh is scheduled at 02:17 UTC. It builds SPX surface, volatility metrics and daily capitulation separately from the component publisher.
3. `_system/scripts/build_vol_metrics.py` deliberately admits a same-day daily candle only after 18:00 America/New_York. Moving a cron to 16:10 without changing close validation would still return the previous day's volatility data.
4. The committed component file in this checkout was generated October 22 at 00:45 UTC but includes October 20 closing flows, VIX, borrow and breadth, alongside October 21 SPX options inputs. A build timestamp does not make those observations current.
5. The local `vol_metrics_latest.json` is newer and covers October 21, while the component snapshot's VIX covers October 20. These are two publication paths with different update times.
6. The browser takes API components when present and consults the static fallback only when the API component array is empty. A successful API response is not necessarily fresher than an available file.
7. The static component fallback has a once-per-UTC-day commit gate. An early publish can prevent a later, improved same-day fallback from being committed.
8. Component freshness previously used a fixed two-calendar-day limit that disagreed with the producer's cadence/weekday thresholds. This change aligns the browser thresholds and prevents a normal weekend from making Friday's daily data stale. It still uses weekdays, not a full exchange holiday calendar.

The existing `docs/market-risk-component-pipeline.md` also described an obsolete half-hour schedule and a retired trading-repository dependency. That documentation is corrected with this audit.

## Why “disagree” appears

The two leveraged-ETF tiles estimate a related mechanical flow using different return inputs. Both are models; the closing tile is not observed trading or a known realized flow.

`letfReconciliation()` calculated a sign/difference verdict even when its own date check found mismatched dates. In this checkout the intraday observation covers October 21 and the closing estimate October 20, so an agreement verdict is inappropriate.

Implemented locally: select market-scope observations, compare explicit session/trading dates where available and otherwise New York dates, withhold direction/gap judgments for unmatched or stale data, and call both figures estimates. Same-session differences still appear with their actual dates and method explanation. This fixes the misleading verdict; it does not establish model accuracy or repair an upstream stale input.

Remaining: attach an explicit `session_date` and covered universe to each source in the publisher, retain paired forecast/close history, and show daily error/bias only for matching date/universe pairs. Data corrections and different modeling assumptions must have different labels.

## Earlier end-of-day updates

Yes: target an initial post-close release around 16:10–16:20 Eastern, followed by reconciliation. An exact immediate/final 16:00 print cannot be promised for every upstream source.

| Stage | Target, America/New_York | Behavior |
|---|---|---|
| Initial close | 16:13 on trading days | Collect available completed-session price/vol/breadth inputs; label provisional observations; leave slower feeds explicitly dated/pending. |
| Reconciliation | 16:43 | Retry only pending/mismatched inputs and publish changed observations. Prefer an upstream completion event to a blind extra fetch. |
| Settled refresh | 18:19 | Reconcile delayed official/vendor values; record which fields are still delayed. Do not call a release final while required inputs are unresolved. |

Implementation sequence:

1. Add a shared exchange-session calendar, including holidays and early closes. Do not use an always-16:00 rule as the truth about every session.
2. Change the volatility builder's blanket 18:00 gate to per-observation completion checks: expected trading date, timestamp after relevant market close/delay, provider status, and valid bar fields. Keep preliminary and settled states separate; never admit a partial intraday candle just because the date matches.
3. Establish one fast close-data workflow for this repo's price/vol/breadth inputs. Avoid duplicating the full nightly download/research workload. Rebuild components after the upstream artifacts are available.
4. Coordinate completion signals from ETF and borrow data publishers. A component publisher cannot manufacture a fresh external snapshot by running more often.
5. Use `timezone: America/New_York` on supported Actions schedules and explicit session guards. The repository's existing comment claiming Actions ignores timezone is outdated; current official documentation supports it.
6. Prefer a coherent source batch, retaining observation dates per component. Select newer valid API/static observations by `(component,scope,symbol)` instead of assuming API means newest. Preserve lineage and disclose a mixed-source recovery.
7. Replace the fallback's once-per-day gate with change/session-aware idempotency: allow a newer source observation or an improved verification state later the same day, skip identical publications.
8. Show one compact freshness line: “Session Oct 22 · 7/9 inputs current · 2 pending · next reconciliation 16:43 ET.” Details show source observation and build/publish times separately. Do not use an API transport-success badge as the data freshness verdict.
9. Measure close-to-visible latency and session coverage after rollout. Alert on missed required snapshots through existing operations monitoring; do not add another research navigation surface.

GitHub explicitly warns scheduled runs can be delayed or dropped under load. These are target windows, not a guaranteed delivery SLA. A stricter deadline would need the existing non-Gateway publishing runtime or another reliable event/scheduler path, while preserving the same source-completion checks. No repeating brokerage/Gateway access is required or permitted.

Acceptance: test daylight/standard-time schedules, holidays, early closes, missing providers, a delayed official print, a fresh API with stale observations, a newer static fallback, two changed releases in one day, and both matching/mismatching model comparisons. The initial release must not relabel yesterday's data as today's.

Source: [GitHub Actions schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), checked October 22, 2026.
