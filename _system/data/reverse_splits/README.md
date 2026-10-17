# Reverse-split research data

US listed and OTC reverse-split research: completed events and candidates with
an ex date, filing disclosures, FINRA positioning
context, the persisted shared-capital book runs and the append-only RSI-1.0
decision journal. Proposal:
`_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md` (Phase 3).
Process: `_system/frameworks/reverse_split_short_process.md`.
Code: `_system/scripts/reverse_splits/` (CLI
`python -m _system.scripts.reverse_splits.cli`).

This directory separates the **committed ledger** (JSONL beside this file) from
**local build artifacts** (`local/`, ignored by git: the 260 MB SQLite, raw
EDGAR and companyfacts caches, price history, reports). The ledger is what a
clean clone has; `import_ledger` rebuilds SQLite from it and `export_ledger`
writes it back. Files over 10 MB are divided into immutable year shards with
a checksum index (`name.parts.json`). Readers use `load_jsonl` to verify and
combine the shards. No old years are removed to meet the size limit.

| File | Content | Rows (2026-10-11) | Mutability |
|---|---|---:|---|
| `events.jsonl` | Completed or candidate reverse splits with an ex date (`status` seeded / edgar_candidate; `outcome` effective). One row per `(ticker, ex_date, split_from, split_to)`. | 632 | Rewritten by `export-ledger`; rows are upserted, never deleted, by the collectors |
| `announcements.jsonl` | 8-K/6-K reverse-split phrase hits that did not become a Yahoo split, with the parsed outcome where the filing text was read. Written sparse: an absent key is null. | 22,879 | Rewritten by `export-ledger`; the weekly `seed --since-days` rebuilds only its window |
| `finra_short_interest.jsonl` | FINRA consolidated short interest when files were present, else synthetic rows carrying average daily volume only (`source_file: synthetic_adv_only`). Sparse. | 17,223 | Rewritten by `export-ledger` |
| `book_runs.jsonl` | One row per persisted book run: label, assumptions (`config`), diagnostics (`analysis`), funnel, and the sha256 of its source manifest. | 118 | Append-only through the local `book` command |
| `book_source_manifests.jsonl` | Deduplicated source manifests (code hashes, SEC cache hashes, SSI source hashes) referenced from book runs. | 8 | Append-only |
| `decisions.jsonl` | RSI-1.0 decisions: review / pass / paper_ready with the frozen evidence, policy and evaluation. Hash-chained. **Michael owns these rows.** | 2 | Append-only, immutable; revisions append with `supersedes` |
| `ledger_manifest.json` | `exported_at`, per-file rows / bytes / sha256, caps applied, chain validity, the tables deliberately not exported. | | Rewritten by `export-ledger` |
| `config.toml` | Package configuration; paths resolve relative to this directory. | | Edited by hand |
| `local/` | SQLite (`reverse_splits.db`, `strategy_decisions.sqlite`), `raw/` caches, `reports/`. | | Ignored |

Not exported (reproducible from public sources or too large): `prices_daily`
(1.78 M Yahoo rows), `edgar_hits` (39.8 k phrase hits), `control_prices`,
`book_trades`, `book_equity`, `issuers` (names travel on the rows), `filings`,
`borrow_snapshots`, `backtest_*`.

## Expanded universe experiment (v3)

The Shorts → Reverse splits panel has a separate expanded study. It covers
2018-05-01 onward for prices and supports SEC discovery from 2005 onward.
The saved 118 book runs and Michael's decisions remain the frozen comparison.
`full_universe_complete` stays false while source or identity gaps remain.

### Published snapshot: 2026-10-13

Run `20261013T202808739318Z` covers events from 2018-05-01 through
2026-10-13, with complete daily price history available through 2026-10-12.

| Measure | Count |
|---|---:|
| Discovered filing accessions, 2005 onward | 128,077 |
| Parsed filing disclosures | 60,618 |
| Catalogue events and candidates | 7,069 |
| Distinct issuer keys in the catalogue | 4,978 |
| Verified actions: structured notices or matched primary schedules | 3,619 |
| Verified next-session / five-session entry and exit benchmarks | 665 |
| Distinct issuer keys with those benchmarks | 541 |
| Fixed account scenarios | 34 |

The 665 count establishes two benchmark prices, not an uninterrupted,
executable trading path. Unresolved issuer keys use the historical symbol;
identity review can join aliases later. The catalogue is approximately three
times the existing 2,330-row event ledger, with its provisional rows labeled.

All filing accessions inside the priced collection window were attempted;
two remain unavailable. Another 67,457 earlier accessions remain discovery
metadata awaiting text processing and licensed prices. The full-market price
scan retains unmatched candidates; its reconciled window is 2018-05-15 through
2026-10-05 because the detector requires surrounding sessions.

Nominal prices cover 2,736 symbols and 1,057,110 daily rows. Official auction
benchmarks come from 105 venue files, with 1,993,744 valid observations. SEC
fundamental sources were requested for 3,239 issuer IDs; 32 source files were
unavailable. Historical OTC prices, terminal obligations and dated security
identity remain incomplete. The optional Massive cross-check has no local
key and contributes no actions.

For example, the next-session fundamental-score-60 case with a five-session
hold and assumed 100% annual borrow fees has 91 modeled entries across 89
issuer keys, including two unresolved positions. The strict evidence case
has zero trades because its required dated execution evidence is unavailable.
These are conditional research results, not demonstrated tradable profits.

The latest public borrow archive contains 4,599 inventory indications as of
2026-10-13 20:28:29 UTC. It supplies no approved locates. The daily archive
workflow builds future evidence; it cannot reconstruct historical approvals.

### How to read the expanded backtest

1. **Find the names.** Search filings and official OTC action notices, and scan
   historical exchange prices for split-like jumps. This includes names that
   later stopped trading. Unmatched price detections remain searchable candidates.
2. **Identify what happened.** Distinguish permission to split, a board decision,
   a scheduled split, a historical mention and a cancellation. Repeated filings
   are grouped provisionally; they do not automatically become extra trades.
3. **Confirm the action.** A filing's schedule alone does not prove completion.
   Confirmed actions, provisional schedules and unresolved candidates have
   separate counts. Security class and ticker history still need review.
4. **Measure the price move.** Compare official auction prices at the split-day
   open or close, the next session, or five sessions later, with closes after
   5, 10 or 20 sessions. This answers how prices moved before trading costs.
5. **Apply the trading rules.** The separate account replay considers score,
   available history, share quantity, liquidity, margin, spread and capital.
   Sub-$1 stocks are included when the modeled economics allow them.
6. **Charge costs and handle restrictions.** Conditional cases assume 100% or
   300% annual borrow fees, plus spread and commissions. Observed short-sale
   restrictions can delay entry. Unknown evidence remains labeled unknown.
7. **Keep unfinished trades visible.** Missing prices or incomplete covers do
   not create a winning exit. Residual positions and their liabilities remain
   in the account. A strict case requires actual dated execution evidence.
8. **Report the denominator.** Read discovered events, confirmed actions,
   benchmarked events, modeled trades and distinct issuers separately. Running
   several settings on the same company does not increase independent evidence.

The fee rates are assumptions used for sensitivity analysis. Today's public
borrow file cannot tell us whether a stock was borrowable years ago. The
expanded results are exploratory research, not demonstrated executable returns.

The committed files are:

| File | Purpose |
|---|---|
| `expansion_summary.json` | Coverage funnel, source gaps, aggregate event returns and every declared account scenario |
| `expansion_events.jsonl` or `.parts.json` | Event identities, exact action dates/ratios, sources, verification tiers and missing price-path reasons |
| `expansion_disclosures.jsonl` or `.parts.json` | Filing accessions, availability clock, lifecycle stage, ratio and schedule |
| `expansion_discovery.jsonl` or `.parts.json` | All discovered filing-hit identities, including the earlier unpriced inventory; restored on a clean checkout |
| `expansion_episodes.jsonl` or `.parts.json` | Provisional links among repeated disclosures; different schedules or known ratios remain separate |
| `expansion_manifest.json` | Checksums linking one published snapshot to its immutable local input manifest |
| `borrow_history/` | Timestamped public IBKR inventory/fee indications; never approved locates |

Discovery uses three sources independent of today's live ticker list:
all-symbol venue histories (including securities that stopped trading), SEC
full-text windows and quarterly filing inventories, and FINRA's public OTC
Daily List. Every search page is exhausted or recorded as incomplete; large
result windows subdivide. Unknown OTC ratios, unresolved CIKs and security
classes remain candidates. A filing schedule alone is not proof that the
action happened. A price jump alone is not a verified corporate action.

Filings are classified as proposal/authorization, board action, scheduled
action, historical reference, cancellation or unresolved. The parser examines
bounded clauses around split language, including exhibits. Unless a sourced
public release timestamp is supplied, the filing becomes usable at midnight
after its filing day. This prevents a later disclosure from moving a trade
back in time.
Cached complete submission files are retained. For uncached proxies and
information statements, collection resolves the official primary document
and relevant linked exhibits; this is labeled separately from a complete
submission archive, and unlinked exhibits remain an evidence gap.

An optional `reference` collector cross-checks Massive's structured reverse
split endpoint inside its documented two-year Basic window. It uses an
existing `MASSIVE_API_KEY` or `POLYGON_API_KEY`, records access gaps, and never
buys or upgrades a subscription. Older history needs an entitlement decision.
See [Massive's split coverage](https://massive.com/knowledge-base/article/does-massive-support-normal-and-reverse-splits).

The broad event study compares official listing-venue auction entry prices
with closes after
5, 10 and 20 trading sessions. Entry cohorts are split-day open, split-day
close, the next session and five sessions later. Known subsequent splits
change the share quantity; unverified actions block the path. Missing exits
stay unavailable. Returns are gross price behavior, with no assumption of
borrow or executable fills. Each cohort reports distinct events and issuer
keys, plus uncertainty clustered by issuer and calendar year.

The account study uses one hypothetical $50,000 account, the existing
fundamental score floor of 60 and minimum three observed signals. Scheduled,
authorization and board disclosures and next-session entries have separate
declared cases. Sub-$1 prices remain in scope; margin per share, integer
quantity, participation, spread, fees, commissions, economic cost budgets and
conservative stress sizing determine whether a modeled trade fits. Observed
short-sale restrictions delay entry at most two sessions. Missing status
remains unknown. Repeated settings do not increase the independent sample.
Partial covers and missing terminal prices remain residual liabilities.

Companyfacts are filtered by historical filing availability before the SSI
extractor runs. Missing/custom/foreign financial facts remain unscored.
Strict execution requires dated security identity, thesis, house margin,
known unrestricted status, fresh quotes and an approved locate with a
reference. Public inventory indications satisfy none of the locate-approval
requirement. Conditional fee scenarios use fixed 100% and 300% annual fee
assumptions; annualized performance claims are withheld.

Each local run writes its plan before calculating returns, then freezes both
SQLite inputs, companyfacts, code hashes and source hashes under
`local/expansion/expansion_v2/runs/<run-id>/`. Licensed bars, quotes and
individual price-derived returns remain local. Public feeds contain metadata
and aggregate research. Forward validation starts the day after the frozen
cutoff; the existing history is exploratory.
Older immutable content shards can remain alongside the current version;
the `.parts.json` index selects the active rows and checks their hashes.

### Run or resume the expansion

Install `_system/scripts/requirements-reverse-splits.txt` and import the ledger.
Fetch licensed venue files separately with `databento-pull --max-cost 0`;
every new request is quoted before download. The expansion command never
logs into a broker or ThetaData.

```powershell
python -m _system.scripts.reverse_splits.cli import-ledger
python -m _system.scripts.reverse_splits.cli expand all --discovery-start 2005-01-01 --start 2018-05-01 --end 2026-10-13
```

Collection is resumable. Individual steps are `discover`, `discover-ads`, `filings`,
`reclassify`, `fundamentals`, `otc`, `study` and `publish`. `--offline` uses
archived sources and records missing sources. `--pilot` / `--limit` can bound
a collection run; its incomplete coverage is still reported. A denied SEC
request stops that collector; it never changes identity to bypass a denial.
All SEC collectors share one four-requests-per-second budget.

Existing local research can be migrated once with
`expand bootstrap --legacy-root <archived-research-directory>`. This makes a
consistent SQLite snapshot and retains immutable caches without modifying
the old workbench. CSV evidence templates come from `expand templates`;
`expand import --kind <kind> --input <file.csv>` accepts sourced dated
security, action, nominal price, quote, borrow approval, margin, fact, thesis,
decision, holdings and NAV records. Historical evidence vintages cannot be
silently overwritten. Fact and whole-portfolio imports remain review inputs;
the published experiment is the isolated sleeve, not total SSI performance.

The weekday `Reverse-split borrow indications` workflow archives the public
IBKR file before the open, validates its checksum and record count, and
retains the file's actual timestamp. It never backdates availability and
never contacts TWS or an IB Gateway. Historical borrow, OTC price histories,
cash-in-lieu, dividends and terminal obligations still need sourced evidence.

Official auction prices come from the venue `statistics` files, obtained with
`databento-pull --schemas statistics --max-cost 0`. Daily UTC OHLCV alone does
not establish an official open or close. The benchmark follows the listing
venue in dated definitions; missing auction prices remain missing.
See [Databento's statistics definition](https://databento.com/docs/schemas-and-data-formats/statistics).

## Original ledger schemas

### Historical execution evidence

`execution_research.json` contains aggregate costs measured from Databento's
historical quotes for the published 671 one-day price events, plus MBP-10
depth for the original 35 account entries. Licensed books, individual results,
historical symbols, source hashes and request/cost receipts remain in
`local/execution_research/`. The original frozen experiments stay intact.

The dashboard's execution section supersedes the daily-range spread proxy as
an execution estimate. The proxy remains explicitly labeled as an uncalibrated
stress scenario. Quoted spread, displayed depth, price changes relative to
auction benchmarks, commissions, assumed borrowing and additional latency/
impact sensitivities are reported separately.

Measurements use entry at 1 and 30 seconds after the scheduled open and cover
one second before the scheduled close, including early closes. Timestamp and
book-gap flags are rejected; MBP books require completed events. Account
comparisons require affirmative cached Nasdaq trading status at both times
and unrestricted SSR at entry. Quotes alone do not establish an approved
locate or a broker fill. The multi-venue sensitivity combines the listing
venue, NYSE Arca and Cboe EDGX where available, falling back to one valid
venue when necessary. It must not be described as full NBBO.

The original entries and share quantities remain fixed in this comparison.
The previous daily-volume cap delayed six partial covers; the new study
estimates full same-session covers only where displayed depth supports the
quantity. Missing exit books or insufficient depth remain disclosed. This
comparison does not replay whole-account selection or margin after changing
the fills. Additional 0/5/10/25 basis points per side are explicitly unmeasured
latency/impact sensitivities.

The latency diagnostic compares quantity-adjusted quoted execution prices
at the decision time and 10/100/500 milliseconds later on both legs. It
reports signed mean, median and 90th-percentile changes, including price
improvements. This measures background market movement without our orders;
it cannot establish causal market impact or actual broker fill delays.

`capital_risk` adds returns on gross exposure and required margin for the
price cohorts, individual cost components and execution scenarios. The
main house assumption is 100%, with 50% and 200% sensitivities. Initial and
FINRA per-share maintenance floors remain in all sensitivities. Encumbered
short proceeds are not required equity. Summed entry capital is reused over
the historical dates: P&L divided by it is a weighted capital return, not
an annual portfolio result. Simultaneous entry margin and $50k account
drawdown are shown separately. Historical broker margin schedules remain
unknown; these calculations cannot establish a broker-approved margin rate.

Tail statistics show worst losses, empirical 95% loss percentiles and the
average worst 5% of observations. 99% estimates are withheld below 100
observations. Listing-venue `ohlcv-1m` bars restrict the adverse-price
diagnostics to the regular session. Full entry/exit minute highs are bounds;
interior-minute highs omit the ambiguous boundary minutes. These are marks,
not covers. Missing intraday paths remain missing.

Explicit stress cases raise prices by 25%, 50%, 100%, 200% and 500%. The
combined stress also raises house margin to 200%, triples the original
case's annual borrowing assumption, holds seven calendar days and assumes
a 5% adverse cover cost. Borrow accrues on rounded collateral at the
stressed price for the whole delay. Results show loss on gross and original
margin, stressed margin demand and a conservative loss-plus-margin reserve.
The three-largest-position basket is hypothetical; it does not claim the
positions historically overlapped. No stress probability or finite maximum
short loss is asserted. Add `--intraday` to collect missing minute bars;
that collection uses its own `--max-cost` reservation budget.

With a Databento key supplied securely in the process environment:

```powershell
python -m _system.scripts.reverse_splits.execution_research --source-run _system/data/reverse_splits/local/expansion/expansion_v2/runs/20261013T224003582762Z --offline --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Omit `--offline` to download missing windows; each request is priced first.
`--max-cost` defaults to zero and caps new quoted-cost reservations per
collection. `--routing` also collects the two additional venues, with its
own collection budget. Metadata requests are limited to six per second.
Completed files are checksum-verified and reused. Raw market data is never
published.

### Full-sample costs, stops and funded portfolios

`portfolio_protocol.json` declares the account, comparison rules and scenario
matrix before calculating results. `portfolio_research.json` and its manifest
publish aggregate model results. The dashboard builder also exports all scalar scenario metrics to `dashboard/data/reverse_splits_portfolios.csv` (returns are fractions, dollars are USD). Licensed books, quote paths, individual
outcomes and daily account records remain in ignored `local/portfolio_research/`.
The original frozen studies and forward-validation protocol are preserved.

The primary account starts with $50,000 on 2018-05-01 and ends 2026-10-13.
It compounds sizes up to 2.5% of opening equity, admits at most three issuers,
requires $100 minimum notional, caps shares at 0.1% of prior split-adjusted
venue ADV and reserves 40% of opening equity beyond its entry-margin budget. The ADV proxy uses the preceding 20 exchange sessions; unknown volume adds no verified capacity, producing a conservative lower bound rather than assuming unknown returns are zero.
Admission ranking uses prior dollar volume. It never screens on the future
exit book, realized return or full-day volume. Margin requirements retain
initial and FINRA per-share floors and exclude encumbered short-sale proceeds.

Full-session one-second BBO observations combine up to 15 distinct exchange
feeds where their dated histories are available. These are not consolidated
NBBO. Fresh mutually consistent venue states are combined; stale conflicting
states are omitted. Midpoint stops at 5%, 10%
and 20% are monitored after entry; covers use a subsequent quote after a
100ms modeled response. Other cases cover after 15 or 60 minutes or before
the scheduled close, including early closes. Event-level depth is requested
at entry and close and for thinner risk exits. One-second top snapshots
remain where adequate or when deeper books are unavailable; subsecond moves
between sampled observations remain unknown. Missing venue books can
contribute their valid sampled top quote without duplicating the same venue.
Unchanged valid BBO states persist within a complete session until updated or invalidated; absent interval records do not expire resting quotes. Bad timestamps, crossed books and provider book-gap flags reset validity and are rejected. The 30-second event-book lookup is separate from full-session BBO state.

Cached national trading/SSR transitions gate entries. A restriction that
activates during the entry delay can prevent a fill. A stop during a halt
queues until a subsequent tradable quote where observed. Missing or
insufficient-depth covers are estimated and counted, never removed from the
results. Quotes during known nontrading states are excluded from cost calibration; intraday marks fall back to completed trade prices. Same-session completion of those estimates remains a conditional
assumption; delayed-exit and correlated squeeze stresses show additional
capital demands without assuming a stop can fill at its threshold.

For missing execution costs, match the entry price, prior dollar ADV, order
size, prior volatility, year and listing venue, together with entry timing and exit rule. Use
one nearest observation from each of up to 40 other issuers. The base is
the arithmetic mean of paired spread/depth costs; paired empirical cost
percentiles provide sensitivities. Donor dates and feature scaling use past
observations where at least 20 other issuers exist. During warmup, retrospective
issuer holdouts are labeled and permitted only for conditional cost accounting;
they cannot admit a trade through the expected-cost screen. Validation reports
entry half-spread errors and separate round-trip cost forecast errors by exit rule, including past-only comparisons and warmup counts. Measured pairs require sufficient observed depth; they do not identify missing liquidity or historical broker fills.

Every original price event gets standardized $125/$500/$1,250 target-exposure
outcomes, with at least one whole share, separately from account admissions.
Those hypothetical outcomes assume borrowing and complete covers and ignore
SSR/capital admission restrictions. The account replays separately compare
known-before-entry events, the unchanged fundamental score >=60 screen,
cost limits, fixed sizing and 2.5%/5%/10% equity caps per name, margin, residual execution cost, borrowing assumptions,
early and recent periods. Current-rate exclusions are retrospective illustrations.

Ordinary matched same-day settlement is modeled with zero billed borrowing
days and no separate pre-borrow charge. One-billed-day rates are sensitivities,
not historical invoices or an overnight price strategy. Commissions retain
the disclosed fixed per-share/minimum/cap assumptions; dated broker invoices,
historical house margins, approved locates and all other broker charges remain
unavailable. Cash interest is zero.

CAGR uses funded account equity and calendar elapsed years. Sharpe and Sortino
use all exchange sessions, including idle sessions; the main risk-free/target
rate is zero. A constant 4% Sharpe alternative is explicitly hypothetical.
Full-period Calmar and trailing 36-month Calmar each use matching CAGR and
drawdown windows. Also report serial-dependence sensitivity, volatility,
profit factor, expectancy, win rate, daily/trade loss tails, intraday marked
drawdowns, margin usage, turnover, exposure and year-by-year results. ROG and
ROM divide P&L by summed entry exposure/equity requirements; they are not
annualized portfolio growth. Year-block uncertainty is conditional on the
modeled account and observed history, not independent future evidence. Intraday marks include the immediate post-fill spread and fully costed closing equity. Margin breaches are reported without assuming a successful forced liquidation; such cases are unconstrained conditional paths.

A recovery pass checks incomplete auctions with a unique dated security
identity. Only observed entry/exit quote pairs enter the separately labeled
expanded comparison; the original 671-event definition remains fixed.
Unresolved identities and unpriced events remain coverage gaps. Authenticated
dataset metadata confirms that the configured venue history starts in May
2018; the user has no older Massive Advanced, TAQ or CRSP entitlement. No
pre-2018 returns are invented, and the sample is not a complete split census.

With the existing Databento key supplied securely in the process environment:

```powershell
python -m _system.scripts.reverse_splits.portfolio_data --stage access
python -m _system.scripts.reverse_splits.portfolio_data --stage sessions --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_data --stage supplemental --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_data --stage paths
python -m _system.scripts.reverse_splits.portfolio_data --stage depth --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_data --stage books
python -m _system.scripts.reverse_splits.portfolio_repair --max-cost 5
python -m _system.scripts.reverse_splits.portfolio_research --publish
python _system/scripts/build_reverse_splits_dashboard.py
```

Collections reuse checksum-verified caches and quote each new request.
The cumulative research-download budget is $5 across session/supplement/depth/recovery
collections; metadata is free. No Theta terminal, IB Gateway, order API,
subscription upgrade or paid-data automation is involved.

### Event row

```json
{"ticker": "BRTX", "cik": "0001505497", "company": "BioRestorative Therapies, Inc.",
 "exchange": "Nasdaq", "exchange_class": "listed",
 "split_from": 4000.0, "split_to": 1.0, "ratio": 0.00025,
 "first_proxy_date": "2022-08-05", "announce_date": "2021-10-26", "vote_date": null,
 "ratio_set_date": null, "effective_date": "2021-10-27", "ex_date": "2021-10-27",
 "prior_rs_count": 0, "cohort": "first", "status": "seeded", "confidence": 0.5,
 "needs_review": 0, "source": "yfinance", "outcome": "effective", "vote_path": "board",
 "accept_time": "2021-10-26T21:09:51.000Z", "announced_ex_date": null, "announced_ratio": 0.25,
 "jump_status": null, "jump_observed": null, "date_quality": "filing_text",
 "accession": null, "form": null, "created_at": "2026-10-09 03:14:38", "updated_at": "2026-10-09 04:04:43"}
```

`ratio` is new/old shares (0.1 is a 1-for-10). `cohort` in `first | second |
third_plus` counts prior splits by CIK, else by ticker. `exchange_class` in
`listed | otc | unknown`. `date_quality` in `search_hit | acceptance_time |
filing_text`; only `filing_text` means the announcement clause was read.
`accession` and `form` identify the EDGAR filing for `edgar_candidate` rows;
Yahoo-seeded rows carry none.

### Announcement row (sparse)

```json
{"accept_time": "2026-10-08T20:30:17.000Z", "accession": "000121390026107822",
 "announce_date": "2026-10-08", "announced_ex_date": "2026-10-09", "announced_ratio": 0.02,
 "cik": "0001966750", "company": "Zhibao Technology Inc.", "date_quality": "filing_text",
 "exchange": "Nasdaq", "exchange_class": "listed", "form": "6-K", "outcome": "announced_only",
 "ticker": "ZBAO"}
```

`outcome` in `announced_only | mention | cancelled`: `mention` is
reverse-split language with no action, `cancelled` an abandonment, both known
only where the text was parsed. Keys that are always the collector constants
(`source: edgar_search`, `confidence: 0.4`, `needs_review: 1`, `ex_date` =
`announce_date`) are not written; the importer restores them. Absent
`first_proxy_date`, `announced_ex_date`, `announced_ratio`, `vote_path`,
`company` or `exchange` mean null.

### FINRA row (sparse)

```json
{"ticker": "AACG", "settlement_date": "2023-12-15", "avg_daily_volume": 6540.9, "source_file": "synthetic_adv_only"}
```

`short_interest` and `days_to_cover` are present only when a real FINRA file
was ingested. Short interest is positioning, never a locate, and never sets a
share count.

### Book run row

```json
{"id": 118, "created_at": "2026-10-11 23:18:48", "label": "fundamental_60",
 "config": {"signal": "announce", "horizon_days": 5, "fee_annual": 1.0, "borrow_policy": "assumed_fee", "...": "..."},
 "analysis": {"waterfall": {"raw_price_pnl": 617.9, "spread_and_slippage": 331.5, "gross_after_fills": 286.4, "borrow": 124.7, "commission": 21.1, "net": 140.7}, "profit_factor": 1.34, "...": "..."},
 "funnel": [{"stage": "evidence_pool", "n": 48}, {"stage": "raw_asof_score_at_least_60", "n": 4}, {"stage": "taken", "n": 4}],
 "source_manifest_sha256": "..."}
```

`analysis` is `diagnostics()` from `reverse_splits/analysis.py`; `funnel`
counts the admission stages. Trades and equity curves stay local.

### Decision row

```json
{"id": "b99be6f0-...", "recorded_at": "2026-10-09T15:29:12.833239+00:00", "ticker": "DFLI",
 "previous_hash": "", "record_hash": "<sha256>",
 "record": {"id": "...", "recorded_at": "...", "ticker": "DFLI", "decision": "pass", "reason": "...",
            "supersedes": null, "prospective": true, "policy": {"version": "RSI-1.0", "...": "..."},
            "fundamental_snapshot": {}, "announcement_snapshot": {}, "inputs": {}, "evaluation": {},
            "research_plan": {}, "furnace_drafts": [], "previous_hash": "", "record_hash": "<sha256>",
            "source_system": "reverse_split_research", "usage": "research decision; not an order or realized return"}}
```

`record_hash` is the sha256 of the canonical JSON (`sort_keys`, compact
separators) of `record` without `record_hash`; `previous_hash` is the prior
row's `record_hash` (empty for the first). `check_reverse_splits.py` fails on
any break. A `paper_ready` row is a plan, not an order or a fill.

## Rebuilding SQLite from the ledger

```bash
python -m _system.scripts.reverse_splits.cli import-ledger          # JSONL -> local/reverse_splits.db (+ decisions sqlite)
python -m _system.scripts.reverse_splits.cli seed --since-days 21   # EDGAR + yfinance for the recent window
python -m _system.scripts.reverse_splits.cli classify-exchanges
python -m _system.scripts.reverse_splits.cli clocks --since-days 21 # accept clocks + announcement text for new hits
python -m _system.scripts.reverse_splits.cli prices                 # Yahoo OHLCV (local only; ~1.8 M rows)
python -m _system.scripts.reverse_splits.cli finra                  # FINRA files in local/raw/finra, else ADV rows
python -m _system.scripts.reverse_splits.cli book                   # books, reports, local/reports/public/backtest.json
python -m _system.scripts.reverse_splits.cli export-ledger          # SQLite -> JSONL
python _system/scripts/build_reverse_splits_dashboard.py            # ledger -> dashboard/data/reverse_splits.json
python _system/scripts/check_reverse_splits.py --strict
```

`seed` and `clocks` without `--since-days` scan the full `years_back` window
(hours of SEC requests). With it, `seed` rebuilds only announcements filed in
the window and leaves older ledger rows alone; `clocks` leaves effective events
whose announcement predates the window alone (the earliest-filing rule means no
newer hit can replace them). The book, prices, controls and the frozen rerun
are local research steps; CI runs import, seed, clocks, export, build and
check only.

Borrow evidence: `borrow-csv path/to/export.csv` imports a Client Portal
Short-Securities Availability export (keeps the export's own timestamp,
divides percent quotes by 100). The same command reads IBKR's public
`usa.txt` (`ftp2.interactivebrokers.com`, user `shortstock`), one snapshot row
per symbol at the file's `#BOF` time, through SSI's
`refresh_short_alpha_borrow.parse_public_ftp`. One file is one point in time;
it is not a historical locate. There is no broker connection anywhere in the
package; the original tool's live snapshot path was deleted (it used the SPX
executor's client id). See `CLAUDE.md`, IB Gateway rules.

## Databento venue files and the split detector (local)

`databento-pull` fetches Databento's venue datasets (`XNAS.ITCH`, `XNYS.PILLAR`,
`XASE.PILLAR`; they begin 2018-05-01) into `local/raw/databento/`: quarterly
all-symbol daily bars, monthly `definition` snapshots (issue type and listing
venue) and quarterly `status` (Reg SHO 201 state and halts). It needs
`DATABENTO_API_KEY`. Every request is priced first with `metadata.get_cost`
and refused above `--max-cost` (default $0.00, which the current plan quotes
for all of these). Reruns skip complete files. Venue files carry every
instrument that traded, including names that later delisted, at printed
prices. The data is licensed to us and SSI is public, so the files stay under
the gitignored `local/`; only derived event facts may enter the ledger.

`detect-splits` reads those files and finds reverse splits in printed prices:
a session that opens (or closes) at least 1.8x the prior close, within 30% of
a common ratio (15% for 1:2 and 1:3), with the median share volume of the
next five sessions at most 0.8x (0.6x for 1:2 and 1:3) of the five before.
A news move of the same size comes with rising volume and fails the rule.
Detections of one symbol within ten days are one event (a venue with no print
on the split day sees the jump at its next print), dated by the earliest
session. Events are classified with the definitions: only common, ordinary and
ADS shares listed on Nasdaq, NYSE or NYSE American count, and exchange test
symbols (`ZJZZT` and friends) never do. An event is `corroborated` when the
listing exchange saw it or at least two venues did. A lone print on a venue that
is not the listing market is weak evidence: on 2026-10-12, 10 of 20 such events
in a random sample were confirmed by an SEC filing, against 30 of 40
corroborated ones. Count only corroborated events. Calibration: the same
filing search confirmed 14 of 15 events the ledger already had. The result is reconciled against `events.jsonl` (same ticker, ex dates
within five days) and written to `local/reports/split_detections.csv` and
`local/reports/split_detection_reconciliation.json`:

- `matched`: in the ledger and in prices.
- `detector_only`: a discovery gap. Verify it against the filing before it
  enters the ledger.
- `ledger_only`: detector work, such as a ticker renamed since the split (the ledger keeps today's ticker; the venue file has the one in use then), an OTC
  name, or a first session below the jump threshold.

The ratio is inferred from prices and labelled so; the filing's ratio wins.

### Filing checks, the rename join, and adding detections to the ledger

`check-filings` asks EDGAR full-text search, for every corroborated
detector-only event, for a filing between 200 days before and 45 days after
the detected session that says reverse stock split, reverse split, reverse
share split, share consolidation or ADS ratio, together with the ticker.
EDGAR display names carry an issuer's *current* tickers, so there are two
ways to match:

- `display_ticker`: the issuer lists the ticker today.
- `ticker_text`: the issuer's own filings (8-K, 6-K, 10-Q/K, 20-F, proxies;
  never a prospectus) carry the ticker in their text. This is how a renamed or
  delisted company is found. It is weaker, needs two filings from a company
  showing another live ticker, and is skipped for tickers under three letters.

`check-filings` also runs the rename join. Every listed ledger event the
detector missed is matched to a detection within five days, with the same
ratio, whose issuer has the ledger event's CIK. Results are cached in
`reports/filing_checks.json` and `reports/rename_joins.json`.

`import-detections` adds the corroborated detector-only events to the ledger:
it imports the ledger into a scratch SQLite, upserts the rows, recomputes
cohorts per issuer (touching only rows that change) and writes the ledger with
`export_ledger`. Each row is `source = databento_price_jump` with
`needs_review = 1`, and its `status` and `confidence` are:

| `status` | Meaning | `confidence` |
|---|---|---|
| `filing_ratio` | Issuer confirmed, and the filing's own ratio agrees with the printed jump within 35% | 0.5 |
| `filing_confirmed` | Issuer confirmed, ratio inferred from prices | 0.4 |
| `filing_not_found` | No filing found | 0.3 |

A detection the rename join tied to an existing event, or one within ten days
of a ledger event with the same CIK, is that event and is skipped. Price data
never enters the ledger.

### Databento prices and Rule 201 in the book

`databento-prices` loads printed bars into `prices_daily` for every listed
ledger event (ex date -120 to +60 days). OHLC comes from the highest-volume
venue among XNAS, XNYS and XASE; volume is the sum of the three, which is less
than consolidated volume. A renamed ticker is priced under the symbol it
carried at the split. `ssr_flags` holds every (ticker, day) restricted at the
open: the last explicit Y/N in Nasdaq's `status` feed at or before 09:30 New
York time.

`[execution] ssr_policy` sets how the book treats a restricted entry bar:

- `ignore` (the default): existing books are unchanged.
- `exclude`: the entry is dropped (funnel stage `ssr_restricted`).
- `delay`: the entry moves to the next unrestricted session, at most two
  sessions later.

A short may still fill above the national best bid while restricted, so
`exclude` is the conservative reading and `delay` the faithful one for an
order at the open.

## Dashboard payload (`dashboard/data/reverse_splits.json`)

Built from the JSONL alone (CI has no SQLite). Schema `reverse_splits.v1`:
`counts` (events, announcements, by_cohort, by_exchange_class, by_year,
announcements_by_outcome), `recent_announcements` (last 90 days, newest first,
at most 100), `upcoming_effective` (known or announced ex dates on or after
today, `basis` event / announcement, at most 50), `repeat_splitters` (cohort
second / third_plus, at most 50), `book` (latest run, latest batch, honest
limits), `process` (RSI-1.0 rules, gates, policy text), `decisions_summary`,
`health` (`status`, `structural_errors`, `problems`) and the research-only
authority fields. `health.status` is `unhealthy` when the ledger manifest is
older than ten days or the feed is older than 100 hours; the P6 feed registry
asserts `health.status not_in [unhealthy]` and `health.structural_errors`
empty.

## Honest limits

### One-session research and the October 14 validation cohort

The v4 study adds a primary benchmark: short at the official opening auction
of the session after a verified split and cover at that session's official
closing auction. It holds zero overnights. Gross return is `1 - close/open`,
with equal weight per event. Split-day open/close, closing-to-closing overnight
benchmarks and longer holds are shown separately. Account cases retain capital,
liquidity, spread, commission, collateral fees and unresolved obligations.

The historical financial screen remains score >=60, three numeric signals,
an operating-company profile and latest-period age <=200 days. A one-day entry
is skipped when observed SSR would delay it. Unknown SSR remains conditional.
Missing exit prices do not exclude an otherwise observable opening entry from
the account replay; the obligation remains open. Only complete benchmark pairs
enter the descriptive gross-return denominator.

`action_reviews.json` preserves ACON's rejected April 8, 2025 price-jump
candidate with the archived primary-source hash. It was a lone non-listing-venue
print; the June quarterly report identifies January and March splits. The
rejection corrects share/price reconciliation and never creates an earlier
entry signal. DBGI's issuer filing establishes the December 18, 2024 Nasdaq
suspension and expected OTC quotation; it supplies neither an OTC exit price
nor an end to the borrowing obligation. The exit audit retains every residual
path from the earlier published run and classifies remaining evidence gaps.

Current IBKR public inventory is archived with its timestamp, checksum and
quantity/rate indications. The dashboard reports median, mean and 90th
percentile annual rates for the current archive, priced one-day names and
financially screened names. These determine flat-rate sensitivities before
account replay. A separate illustration applies per-name current rates <=50%
and the 1% expected-cost screen to historical prices. **That illustration uses
current availability and is not a tradable historical selection rule.** Missing
quotes are not zero fees; public inventory is never an approved locate.

No private IBKR statement connection or Flex token is configured in this
research session. The import templates accept `borrow_fee` (dated broker annual
rates), `loan_event` (recall, return or buy-in records), `action_review` and
`forward_observation` in addition to prices, quotes, margin and actual locates.
Broker-statement rates replace scenario rates on their effective dates when a
verified dated security identity joins them. Unsupplied dates stay assumptions.
The minimum intraday borrowing charge is one calendar day. A missing prior
close uses an explicitly recorded entry-price collateral proxy, not NaN or a
zero fee. Actual loan termination requires broker evidence.

`forward_protocol.json` freezes the initial paper version before October 14:
next-session open to same close, unchanged fundamental screen, approved locate,
fresh quote, dated margin/security/thesis, <=50% annual borrowing rate and <=1%
estimated total cost. Sizing uses <=0.1% of prior ADV, <=2.5% of equity, three
names and a 0.5% name-loss budget under a +200% price stress, triple fees and
seven calendar days of exit delay. These are research budgets, not guaranteed
loss limits. One overnight is a comparator rather than the frozen primary rule.

Controls use different weak issuers, same current SIC division, score within
15, prior price within factor 2 and prior dollar volume within factor 3. Choose
up to three by pre-entry distance, never by subsequent return. The current
historical control pool is partial and event-derived. Its +/-30-day action
exclusion is retrospective, so excess return is diagnostic rather than causal.

The registry retains provisional future disclosures and first-recorded times.
They need action, identity and execution verification before becoming eligible
paper trades. The first result review needs at least 100 completed events and
60 issuers with cost/exit evidence; neither threshold guarantees a representative
sample. There are no completed new-cohort outcomes before October 14.

```powershell
python -m _system.scripts.reverse_splits.cli expand templates
python -m _system.scripts.reverse_splits.cli expand import --kind borrow_fee --input path/to/dated_fees.csv
python -m _system.scripts.reverse_splits.cli expand import --kind loan_event --input path/to/loan_returns.csv
python -m _system.scripts.reverse_splits.cli expand forward --end YYYY-MM-DD
python -m _system.scripts.reverse_splits.cli expand study --start 2018-05-01 --end YYYY-MM-DD
python -m _system.scripts.reverse_splits.cli expand publish
python _system/scripts/build_reverse_splits_dashboard.py
```

The forward collector uses SEC public sources and IBKR public FTP. It never
connects to ThetaData or the IB Gateway, places orders or purchases data. A
weekday 17:30 Eastern thread follow-up checks meaningful changes; absent
licensed price updates and broker records, it reports evidence gaps rather
than invented paper fills. Full immutable history snapshots are manual because
disk space is limited. Repeated companyfacts use hash-checked hardlinks only
from a completed immutable snapshot; mutable databases are separately frozen.

- Historical approved locates are not supplied by the public availability
  file. The strict book needs a dated approval reference, quantity and fee,
  plus the other execution evidence.
- Assumed fees are flat annual rates, not the fee the street quoted that day.
- A phrase hit in an 8-K is not an announcement until the filing text is
  parsed (`date_quality: filing_text`). Most announcement rows are accept-clock
  phrase hits.
- The original $50k completed-split comparator lost about $14,286 on 124
  trades. The 2026-10-11 filing and corporate-action audit superseded the
  preliminary four-trade rerun gains (ASTI was a historical reference; PALI and
  IBO fell under the $1 floor once split factors were repaired); the corrected
  rerun leaves one candidate, EDBL, losing about $150 over five sessions. The
  persisted `fundamental_60` book run predates that audit. Nothing here
  establishes an edge.
- Current SEC exchange maps and Yahoo history are not a contemporaneous
  security master; delisted names and failed exit paths are censored.
- Issuer names come from the SEC ticker map at collection time; about 13% of
  announcement rows have none.

Do not edit the JSONL files by hand. Run
`python _system/scripts/check_reverse_splits.py` after any change.
