# Reverse-split backtests: why n is small and how to raise it

**Date:** 2026-10-12
**Status:** proposal. Nothing here has been collected, bought or rerun. This file authorizes no data purchase and no provider contact.
**Readers:** Drew; Michael (owns reverse-split strategy decisions and `_system/data/reverse_splits/decisions.jsonl`).
**Builds on:** `reverse-split-short-research/docs/DATA_EXPANSION_PLAN.md` (2026-10-11). Its rules stand: keep sub-$1 names in scope through specific feasibility checks, adjudicate episodes, preserve the frozen v1 result, and never lower a threshold to reach a count. This file adds what that plan did not have: the measured funnel, five defects, the data sources with prices, and an order of work that lands in SSI.

## The answer in four lines

1. **The "announce" trade is dated wrong, which is what the $1 floor then removes.** The announce date is the earliest 8-K that mentions a reverse split in the year before the split: median 223 days early in SSI's ledger (586 dated events; 50 within a week). Entered months before the split, the stock is still pre-split and sub-$1, so `below_min_price` drops 326 of 475 completed listed splits.
2. **Only 3% of the filing evidence has been read.** 1,322 of 39,786 EDGAR hits were text-parsed when the verified pool (216) was built. An `expansion_v2` run in the old repo's local copy has since processed 20,475 and found 1,447 scheduled actions and 2,620 provisional episodes across 1,388 issuers (`coverage.json`, 2026-10-12 19:44Z, unadjudicated).
3. **The universe is five years of survivors.** `years_back = 5` (events from 2021-10). Events are seeded from yfinance split history for tickers that EDGAR hits produced, and all 475 listed completed-split tickers are alive today. Names that delisted after splitting, plausibly the best shorts, never enter.
4. **Strict borrow is zero by construction.** There are no historical locates, so `no_fresh_locate_and_fee` removes every name. More events cannot fix that; borrow evidence can.

Capacity is not the problem: removing `max_names` and cash limits adds 4 completed-split trades and 9 verified trades.

## Where the trades go (measured 2026-10-12)

Reproduced exactly against the old repo's DB (1.78M price rows, read-only copy) with SSI's package code. Event-level counts are from `summarize_unconstrained` (`run_book.py:295-313`), which writes `backtest.json` but not `book_runs.jsonl`.

**Completed listed splits, 2021-10 to 2026-10:**

| Entry signal | Floor | Eligible n |
|---|---|---:|
| announce (as built) | $1 printed open | 128 |
| announce | $0.50 | 279 |
| announce | none | 431 |
| day before ex | $1 | 32 |
| ex close | $1 | 446 |
| ex + 1 / + 5 / + 10 sessions | $1 | 451 / 446 / 447 |
| first proxy | $1 | 99 |
| vote / ratio set | $1 | 0 (dates never filled) |

**Verified announcement pool:** 216 parsed hits with a ratio → 180 listed → 75 eligible (136 without the floor) → 69 with 20 prior sessions → 48 after the SSR proxy → 33-40 taken, or 0 under strict borrow.

| Drop | n | Cause | Kind |
|---|---:|---|---|
| `below_min_price` | 61 verified / 326 completed | Printed open of a pre-split entry bar (`book.py:250-254`). `adjust.py` direction is correct: 461 of 473 splits show no jump, Yahoo is pre-adjusted, the code restores printed prices. | Rule, aggravated by defect 1 |
| `ssr_proxy_excluded` | 21 | Prior-day low or entry gap ≥10% below prior close (`realism.py:113-120`). Rule 201 permits shorts above the national best bid; exclusion is the only treatment. | Rule |
| `no_exit_bar` | 21 | 20 filings dated 2026-09-22 to 10-08; prices end 2026-10-08. | Stale data |
| `no_prices` | 17 | Seven symbols that later changed (ENTO→GRDX, CJJD→RDGT, SYTA→CHAI, JFBR→NEXR, SLRX→DCOY, PSTV→CNSY, EVTV→AZIO); prices exist only under the new ticker. | Identity gap |
| `less_than_20_prior_sessions` | 6 | Price window starts too late (ex date −120 days). | Data window |
| `no_fresh_locate_and_fee` | 48 (all) | No historical borrow. | Evidence gap |
| Not verified | 523 of 632 completed splits | Filing read, no ratio found (371); ratio hit dropped (75); no CIK (56); no 8-K/6-K in window (21). | Data gap, mostly defect 1 |
| `fundamental_60` | 48 → 4 | 20 unscored (16 with fewer than three signals, 4 non-operating), 28 scored, 4 at ≥60. SSI has no `local/raw/companyfacts`, so a rerun here scores 0. | Coverage and threshold |

## Defects to fix before adding data

More events through a mis-dated pipeline only add mis-dated trades. Fix these first.

1. **Announce date.** `filings.py` marks a hit "substantive" on any `announc|effect a reverse|reverse stock split` match, and `choose_announce` takes the earliest substantive 8-K/6-K up to 365 days before the split. Fix: classify the lifecycle stage (proposal, authorization, ratio set, final schedule, effective) as `expansion_v2` already does, and date each cohort by its own stage.
2. **Placeholder split dates.** 22 `edgar_search` events take the filing date as the split date (`ingest_splits.py:557-578`). With no price jump they are labelled "already adjusted" and every earlier bar is multiplied by the ratio: GDC's history is scaled by 0.004; SPRC has duplicate rows and is scaled twice. Ten tickers are distorted. Fix: never adjust prices on an unconfirmed split date.
3. **Survivorship at seeding.** The event list comes from yfinance split history, so it can only contain tickers that still trade. Fix: discover from SEC filings and an independent corporate-action list, then fetch prices from a source with delisted coverage (Phase 2).
4. **Funnel order.** SSR and the 20-session check are printed after `taken_pool` but applied before it (`realism.py:107-147`); 48 is the post-SSR count and 75 the eligible pool. Fix the order so the dashboard reads true.
5. **The ledger hides the event study.** `book_runs.jsonl` records capacity-constrained `taken`, which made n look smaller than the evidence. Export the unconstrained per-event counts and returns beside each book run.

Separately, a hazard, now removed: the old repo's local copy had `src/rsdb/ibkr_borrow.py` (imports `ib_insync`) with `client_id = 17` in its `config.toml`, the SPX live executor's id. The SSI port had deleted this path; the old copy is cleaned too (decision 6).

## Levers, ranked

| # | Lever | n effect | Cost | Phase |
|---|---|---|---|---|
| 1 | Fix the announce date and add post-split entry cohorts (ex close, ex + 1, ex + 5) | Completed listed splits: 128 → about 446-451 eligible, all already priced | Code only | 1 |
| 2 | Finish the filing backlog (19,311 hits pending in `expansion_v2`) and adjudicate | Verified: 216 parsed leads → up to 1,447 scheduled actions across 1,388 issuers, before eligibility | Code, SEC requests | 0-1 |
| 3 | Replace the $1 floor with feasibility checks (FINRA 4210 $2.50/share minimum, spread, size) | 75 → up to 136 verified eligible; 128 → up to 431 completed | Code only | 1 |
| 4 | Discovery independent of today's tickers, plus delisted prices | Unknown; measured in the pilot by diffing a vendor split list for 2021-2026 against our 475 | $199-630/yr | 2 |
| 5 | Extend history to 2015 (then 2005 if comparable) | Several hundred listed events (Nasdaq alone processed 94 reverse splits in 2020 and 196 in 2022); the pilot's count replaces this guess | Same vendor | 2 |
| 6 | SSR as delayed entry or worse fill, derived from unadjusted bars | +21 verified | Code only | 1 |
| 7 | Refresh prices past 2026-10-08; map CIK to the current ticker | +20; +17 | Code only | 0 |
| 8 | Drop the placeholder splits | +8 completed, and correct prices for 10 tickers | Code only | 0 |
| 9 | Borrow history | Makes strict nonzero: forward from 2026-10-12 for free; back to 2018-04 with a paid licence | $0, or a licence | 3 |
| 10 | Fundamentals cache in SSI | `fundamental_60` from 0 (in SSI today) back to 4, then the expanded pool | data.sec.gov requests | 4 |

## Plan

### Phase 0: consolidate and fix (no new data)

- Land `expansion_v2` in SSI's `_system/scripts/reverse_splits/`. Today it lives uncommitted on branch `realism-book` in the archived repo's local copy, beside modified `enrich_edgar.py`, `replay.py` and `rerun.py`. Two engines are drifting, and the one doing the work is in a place nothing backs up.
- Fix defects 1, 2, 4 and 5 in the SSI package, with tests that pin the 223-day gap, the GDC scaling and the funnel order.
- Refresh prices past 2026-10-08 and add a CIK-to-current-ticker map.
- Freeze v1 (`fundamentals_v1`) as the comparator, as the expansion plan requires.

**Done when:** SSI's package reproduces the v1 funnels from a clean clone plus `import-ledger` and a prices pull, and `book_runs.jsonl` carries event-level n.

### Phase 1: use the evidence already in hand

- Finish the 19,311 pending hits, then proxies and information statements, at the shared four-requests-a-second SEC limiter.
- Pre-register cohorts before any replay: scheduled action, authorization/proposal, board action, ex close, ex + 1, ex + 5. Each is reported separately, with issuer counts.
- Replace the $1 floor with the expansion plan's specific checks; keep price bands as diagnostics.
- Treat SSR as a restriction on fill price, not an exclusion.

**Done when:** at least 100 verified episodes from 50 issuers (the expansion plan's first milestone), with a funnel in which every drop is invalid evidence, economically rejected, or evidence unavailable.

### Phase 2: remove survivorship and extend history

- Discovery from SEC quarterly indexes and full-text search (2001 onward), independent of today's ticker map, cross-checked against Massive's splits endpoint (records from 1978; SSI already has `POLYGON_API_KEY`, but the free tier returns 2 years, so confirm the plan first). Item 5.03 8-Ks exist from mid-2004.
- A 20-event delisted-price pilot (retired tickers, sub-$1, repeat splitters, ticker changes) on two vendors before any annual purchase. The same pilot measures the survivorship gap directly.
- Extend to 2015-2020 under the same definitions; go earlier only if prices, identity and fundamentals hold up.

**Done when:** a coverage table by year, venue and issuer status, with the survivor-only share of the 2021-2026 sample stated as a number.

### Phase 3: borrow evidence

- **Forward, free, starting now.** A daily lane that pulls IBKR's public `usa.txt` (`ftp2.interactivebrokers.com`, user `shortstock`; ftp3 does not answer from the workstation), checks the MD5 and `#EOF` count, and stores the rows for tickers with a reverse-split event or announcement in the past year plus the Short Alpha ledger. Both importers read the file as of 2026-10-12. From the first run, the strict book has a real locate and fee for every new event.
- **Historical.** QuantRocket's IBKR borrow-fee and shortable-share history from 2018-04-16 is the closest match to the live source (paid; price behind a login; no redistribution). iBorrowDesk's JSON has daily IBKR history from about 2017, but it is unofficial, has no published terms, and may drop delisted names. Use it for nothing without a decision. Before 2018, only proxies exist: SEC fails-to-deliver (2004+), Nasdaq threshold lists (2005+), and the FINRA short interest already in the ledger. They are covariates, never fees.

**Done when:** strict and assumed-fee books run on the same events, with strict n reported for 2018+ and forward cohorts.

### Phase 4: fundamentals coverage

Fetch the companyfacts cache into SSI's workbench and score every verified lead, including those that fail trading checks. Keep `≥60` as the rule. A lower threshold is reported as a diagnostic: 40 would give 18 of today's 48, but that is a different rule, not more evidence.

## Data sources (public pages read 2026-10-12)

| Need | Source | History | Cost | Caveat |
|---|---|---|---|---|
| Events | SEC full-text search; quarterly indexes | 2001; 1994 | Free | About 10 requests a second per IP; use the shared limiter at 4 |
| Events, cross-check | Massive (Polygon) splits | 1978 | $29-199/mo; key exists | Delisted coverage not stated in the docs |
| Events, Nasdaq | Nasdaq Daily List | 1998-99 | Paid | Nasdaq only |
| Delisted prices | EODHD Historian | 30+ years | $199/yr | Splits only for names delisted after 2018 |
| Delisted prices | Norgate Platinum | 1990 | $630/yr | Windows updater; personal licence |
| Delisted prices | Sharadar SEP | 1998 | Behind a login | Professional licence if managing money |
| Borrow history | QuantRocket (IBKR) | 2018-04 | Paid licence | No redistribution |
| Borrow history | iBorrowDesk | about 2017 | Free / $10 tier | Unofficial; no terms |
| Borrow proxies | FTD, threshold lists, FINRA SI | 2004; 2005 | Free | Not fees |
| SSR | Derived from unadjusted daily bars | 2011-02 | Free | Low ≤ 90% of prior close restricts that day and the next |

Not used: ThetaData (the seat rule in `~/.claude/CLAUDE.md`; its docs show stock history from 2012 for Nasdaq and 2020 for NYSE, with nothing on delisted symbols), yfinance for anything delisted, Stooq (HTML with HTTP 200 since about 2026-06), and the IB Gateway (rule 9).

## Guardrails

- A count target never changes a definition. Report verified episodes, eligible trades, fundamental-qualified trades and evidence-supported trades separately.
- Intervals cluster by issuer and calendar block. Ten splits by one serial splitter are one issuer.
- Every cohort and rule is saved before its replay. Do not search configurations and present the best.
- Historical results stay conditional on assumed borrow until borrow evidence exists for those dates.

## Decisions needed

1. **Where `expansion_v2` lands.** Bring it into SSI now (recommended), or finish it in the old copy first and port once. Either way, commit it somewhere backed up today.
2. **The delisted-price pilot.** Approve a 20-event pilot on EODHD and Norgate, and check which Massive plan the existing key is on.
3. **Historical borrow.** Price QuantRocket's licence, or run forward-only.
4. **The daily borrow lane.** Commit the filtered daily rows to SSI (small; IBKR's redistribution terms for the public file are unstated), or keep raw files in the private research vault.
5. **Post-split entry cohorts.** These are a strategy change, so Michael decides whether they become RSI cohorts.
6. **The old copy's Gateway borrow path.** Done 2026-10-12: the old repo's local branch `realism-book` commit `3ab0ec9` removes the TWS/Gateway snapshot functions, the `[ibkr]` block with `client_id = 17`, the `ib_insync` dependency and the instructions that described it. The CSV importer and sizing cap stay; its 86 tests pass. The GitHub copy is archived, so this commit is local only.
